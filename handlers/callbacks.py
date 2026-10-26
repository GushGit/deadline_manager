"""Кнопки под сообщениями: выполнено, перенос дедлайна, удаление задачи."""
import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery

import config
import database
import keyboards
import texts
import utils
from handlers.tasks import edit_text

logger = logging.getLogger(__name__)
router = Router()


def _now_utc() -> datetime:
    """Текущее время в UTC (в тестах подменяется через monkeypatch)."""
    return datetime.now(timezone.utc)


def parse_task_id(data: str) -> int | None:
    """Достаёт id из callback_data вида 'del:12'; None, если формат неверный."""
    try:
        return int(data.split(":", 1)[1])
    except (IndexError, ValueError):
        return None


async def _read_task_id(callback: CallbackQuery) -> int | None:
    """Разбирает id из кнопки; при ошибке сама отвечает пользователю."""
    task_id = parse_task_id(callback.data)
    if task_id is None:
        await callback.answer(texts.BAD_BUTTON, show_alert=True)
    return task_id


async def _answer_not_found(
    callback: CallbackQuery, task_id: int, text: str = texts.TASK_NOT_FOUND
) -> None:
    """Одинаковый ответ для чужой и несуществующей задачи; пишет WARNING."""
    logger.warning(
        "Задача не найдена или чужая: user_id=%s, task_id=%s",
        callback.from_user.id,
        task_id,
    )
    await callback.answer(text, show_alert=True)


async def _load_own_task(callback: CallbackQuery) -> dict | None:
    """Возвращает задачу пользователя или None (ответ уже отправлен)."""
    task_id = await _read_task_id(callback)
    if task_id is None:
        return None
    task = await database.get_task(config.DB_PATH, task_id, callback.from_user.id)
    if task is None:
        await _answer_not_found(callback, task_id)
    return task


async def _snooze(callback: CallbackQuery, shift: timedelta) -> None:
    """Переносит дедлайн активной задачи и пересоздаёт напоминания."""
    task = await _load_own_task(callback)
    if task is None:
        return
    if task["status"] != "active":
        await _answer_not_found(callback, task["id"])
        return
    user_id = callback.from_user.id
    user = await database.get_or_create_user(config.DB_PATH, user_id)
    now = _now_utc()
    new_deadline = task["deadline"] + shift
    if new_deadline - now > timedelta(days=config.MAX_DEADLINE_DAYS):
        await callback.answer(texts.SNOOZE_TOO_FAR, show_alert=True)
        return
    offsets = utils.parse_offsets(user["reminder_offsets"])
    remind_times = utils.calc_reminder_times(new_deadline, offsets, now)
    shifted = await database.shift_task_deadline(
        config.DB_PATH, task["id"], user_id, new_deadline, remind_times
    )
    if not shifted:
        await _answer_not_found(callback, task["id"])
        return
    logger.info("Дедлайн перенесён: task_id=%s, user_id=%s", task["id"], user_id)
    deadline_text = utils.format_deadline(new_deadline, user["timezone"], now)
    await edit_text(callback, texts.deadline_shifted(deadline_text))
    await callback.answer()


@router.callback_query(F.data.startswith("done:"))
async def mark_done(callback: CallbackQuery) -> None:
    """Отмечает задачу выполненной (в том числе уже просроченную)."""
    task_id = await _read_task_id(callback)
    if task_id is None:
        return
    user_id = callback.from_user.id
    done = await database.mark_task_done(config.DB_PATH, task_id, user_id, _now_utc())
    if not done:
        await _answer_not_found(callback, task_id, texts.DONE_NOT_FOUND)
        return
    logger.info("Задача выполнена: task_id=%s, user_id=%s", task_id, user_id)
    await edit_text(callback, texts.DONE_OK)
    await callback.answer()


@router.callback_query(F.data.startswith("snooze_h:"))
async def snooze_hour(callback: CallbackQuery) -> None:
    """Переносит дедлайн на час."""
    await _snooze(callback, timedelta(hours=1))


@router.callback_query(F.data.startswith("snooze_d:"))
async def snooze_day(callback: CallbackQuery) -> None:
    """Переносит дедлайн на сутки."""
    await _snooze(callback, timedelta(days=1))


@router.callback_query(F.data.startswith("del:"))
async def ask_delete(callback: CallbackQuery) -> None:
    """Спрашивает подтверждение удаления."""
    task = await _load_own_task(callback)
    if task is None:
        return
    await edit_text(
        callback,
        texts.delete_confirm(task["title"]),
        reply_markup=keyboards.delete_confirm_keyboard(task["id"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delyes:"))
async def confirm_delete(callback: CallbackQuery) -> None:
    """Удаляет задачу после подтверждения."""
    task_id = await _read_task_id(callback)
    if task_id is None:
        return
    user_id = callback.from_user.id
    if not await database.delete_task(config.DB_PATH, task_id, user_id):
        await _answer_not_found(callback, task_id)
        return
    logger.info("Удалена задача task_id=%s, user_id=%s", task_id, user_id)
    await edit_text(callback, texts.DELETE_DONE)
    await callback.answer()


@router.callback_query(F.data.startswith("delno:"))
async def cancel_delete(callback: CallbackQuery) -> None:
    """Отменяет удаление, задача остаётся."""
    task = await _load_own_task(callback)
    if task is None:
        return
    await edit_text(callback, texts.DELETE_KEPT)
    await callback.answer()