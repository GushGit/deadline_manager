"""Диалог /add (FSM) и команда /cancel."""
import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import database
import keyboards
import texts
import utils
from states import AddTask

logger = logging.getLogger(__name__)
router = Router()


def _now_utc() -> datetime:
    """Текущее время в UTC (в тестах подменяется через monkeypatch)."""
    return datetime.now(timezone.utc)


def is_command_in_dialog(message: Message, raw_state: str | None = None) -> bool:
    """True, если идёт диалог (есть состояние FSM) и пришла команда."""
    text = message.text or ""
    return raw_state is not None and text.startswith("/")


def _reminder_plan(
    deadline: datetime, offsets: tuple[int, ...], now: datetime
) -> tuple[list[int], list[int]]:
    """Делит интервалы на те, что ещё в будущем, и уже пропущенные."""
    kept = [m for m in offsets if utils.calc_reminder_times(deadline, (m,), now)]
    skipped = [m for m in offsets if m not in kept]
    return kept, skipped


async def _edit_text(callback: CallbackQuery, text: str) -> None:
    """Редактирует сообщение с кнопкой; устаревшее или то же самое глушит."""
    try:
        await callback.message.edit_text(text)
    except TelegramBadRequest:
        logger.info("Не удалось отредактировать сообщение")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Прерывает любой диалог."""
    if await state.get_state() is None:
        await message.answer(texts.NOTHING_TO_CANCEL)
        return
    await state.clear()
    await message.answer(texts.CANCELLED)


@router.message(is_command_in_dialog)
async def command_in_dialog(message: Message) -> None:
    """Команда посреди диалога: просим закончить его или отменить."""
    await message.answer(texts.FINISH_DIALOG)


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    """Начинает диалог добавления дедлайна."""
    user_id = message.from_user.id
    await database.get_or_create_user(config.DB_PATH, user_id)
    active = await database.count_active_tasks(config.DB_PATH, user_id)
    if active >= config.MAX_ACTIVE_TASKS:
        await message.answer(
            texts.ADD_LIMIT_REACHED.format(limit=config.MAX_ACTIVE_TASKS)
        )
        return
    await state.clear()
    await state.set_state(AddTask.waiting_title)
    await message.answer(texts.ADD_ASK_TITLE)


@router.message(AddTask.waiting_title, F.text)
async def process_title(message: Message, state: FSMContext) -> None:
    """Принимает название задачи."""
    title = message.text.strip()
    if not title:
        await message.answer(texts.ADD_TITLE_EMPTY)
        return
    if len(title) > config.MAX_TITLE_LENGTH:
        await message.answer(
            texts.ADD_TITLE_TOO_LONG.format(limit=config.MAX_TITLE_LENGTH)
        )
        return
    await state.update_data(title=title)
    await state.set_state(AddTask.waiting_deadline)
    await message.answer(texts.ADD_ASK_DEADLINE)


@router.message(AddTask.waiting_deadline, F.text)
async def process_deadline(message: Message, state: FSMContext) -> None:
    """Разбирает дедлайн и показывает сводку для подтверждения."""
    user = await database.get_or_create_user(config.DB_PATH, message.from_user.id)
    tz = user["timezone"]
    now = _now_utc()
    deadline = utils.parse_user_datetime(message.text, tz, now)
    if deadline is None:
        await message.answer(utils.explain_datetime_error(message.text, tz, now))
        return
    offsets = utils.parse_offsets(user["reminder_offsets"])
    kept, skipped = _reminder_plan(deadline, offsets, now)
    data = await state.get_data()
    await state.update_data(deadline=deadline.isoformat())
    await state.set_state(AddTask.waiting_confirm)
    summary = texts.add_summary(
        data["title"],
        utils.format_deadline(deadline, tz, now),
        utils.format_time_left(deadline - now),
        [utils.format_offset(m) for m in kept],
        [utils.format_offset(m) for m in skipped],
    )
    await message.answer(summary, reply_markup=keyboards.confirm_keyboard())


@router.message(AddTask.waiting_title)
@router.message(AddTask.waiting_deadline)
async def expect_text(message: Message) -> None:
    """Стикер, фото и т. п. там, где ждали текст."""
    await message.answer(texts.TEXT_ONLY)


@router.message(AddTask.waiting_confirm)
async def expect_button(message: Message) -> None:
    """Текст на шаге подтверждения: напоминаем про кнопки."""
    await message.answer(texts.ADD_CONFIRM_WAIT)


@router.callback_query(F.data == "add_save")
async def add_save(callback: CallbackQuery, state: FSMContext) -> None:
    """Сохраняет задачу после подтверждения."""
    if await state.get_state() != AddTask.waiting_confirm.state:
        await callback.answer(texts.BUTTON_OUTDATED, show_alert=True)
        return
    data = await state.get_data()
    user_id = callback.from_user.id
    user = await database.get_or_create_user(config.DB_PATH, user_id)
    active = await database.count_active_tasks(config.DB_PATH, user_id)
    if active >= config.MAX_ACTIVE_TASKS:
        await state.clear()
        await _edit_text(
            callback, texts.ADD_LIMIT_REACHED.format(limit=config.MAX_ACTIVE_TASKS)
        )
        await callback.answer()
        return

    now = _now_utc()
    deadline = datetime.fromisoformat(data["deadline"])
    if deadline <= now:
        await state.clear()
        await _edit_text(callback, texts.ADD_DEADLINE_PASSED)
        await callback.answer()
        return

    offsets = utils.parse_offsets(user["reminder_offsets"])
    remind_times = utils.calc_reminder_times(deadline, offsets, now)
    kept, _skipped = _reminder_plan(deadline, offsets, now)
    task_id = await database.add_task(
        config.DB_PATH, user_id, data["title"], deadline, remind_times
    )
    await state.clear()
    logger.info("Добавлена задача task_id=%s, user_id=%s", task_id, user_id)
    await _edit_text(callback, texts.add_saved([utils.format_offset(m) for m in kept]))
    await callback.answer()


@router.callback_query(F.data == "add_cancel")
async def add_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Отменяет добавление на шаге подтверждения."""
    if await state.get_state() != AddTask.waiting_confirm.state:
        await callback.answer(texts.BUTTON_OUTDATED, show_alert=True)
        return
    await state.clear()
    await _edit_text(callback, texts.CANCELLED)
    await callback.answer()