"""Кнопки под сообщениями: удаление задачи с подтверждением."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

import config
import database
import keyboards
import texts
from handlers.tasks import edit_text

logger = logging.getLogger(__name__)
router = Router()


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


async def _answer_not_found(callback: CallbackQuery, task_id: int) -> None:
    """Одинаковый ответ для чужой и несуществующей задачи; пишет WARNING."""
    logger.warning(
        "Задача не найдена или чужая: user_id=%s, task_id=%s",
        callback.from_user.id,
        task_id,
    )
    await callback.answer(texts.TASK_NOT_FOUND, show_alert=True)


async def _load_own_task(callback: CallbackQuery) -> dict | None:
    """Возвращает задачу пользователя или None (ответ уже отправлен)."""
    task_id = await _read_task_id(callback)
    if task_id is None:
        return None
    task = await database.get_task(config.DB_PATH, task_id, callback.from_user.id)
    if task is None:
        await _answer_not_found(callback, task_id)
    return task


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