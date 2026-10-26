"""Команды /start и /help, выбор часового пояса."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import database
import keyboards
import texts
from handlers.tasks import edit_text
from states import SetTimezone

router = Router()


def _is_valid_timezone(name: str) -> bool:
    """Проверяет, что имя есть в базе часовых поясов."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Регистрирует пользователя и предлагает выбрать часовой пояс."""
    await database.get_or_create_user(config.DB_PATH, message.from_user.id)
    await message.answer(texts.START, reply_markup=keyboards.timezone_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Отправляет список команд."""
    await message.answer(texts.HELP)


@router.callback_query(F.data.startswith("tz:"))
async def choose_timezone(callback: CallbackQuery) -> None:
    """Сохраняет часовой пояс, выбранный кнопкой."""
    tz_name = callback.data.partition(":")[2]
    if not _is_valid_timezone(tz_name):
        await callback.answer(texts.BAD_BUTTON, show_alert=True)
        return
    user_id = callback.from_user.id
    await database.get_or_create_user(config.DB_PATH, user_id)
    await database.update_user_timezone(config.DB_PATH, user_id, tz_name)
    await edit_text(callback, texts.timezone_saved(tz_name))
    await callback.answer()


@router.callback_query(F.data == "tz_other")
async def ask_timezone(callback: CallbackQuery, state: FSMContext) -> None:
    """Просит ввести часовой пояс текстом."""
    await state.set_state(SetTimezone.waiting_timezone)
    await edit_text(callback, texts.ASK_TIMEZONE)
    await callback.answer()


@router.message(SetTimezone.waiting_timezone, F.text)
async def process_timezone(message: Message, state: FSMContext) -> None:
    """Принимает название часового пояса, введённое текстом."""
    tz_name = message.text.strip()
    if not _is_valid_timezone(tz_name):
        await message.answer(texts.TIMEZONE_INVALID)
        return
    user_id = message.from_user.id
    await database.get_or_create_user(config.DB_PATH, user_id)
    await database.update_user_timezone(config.DB_PATH, user_id, tz_name)
    await state.clear()
    await message.answer(texts.timezone_saved(tz_name))


@router.message(SetTimezone.waiting_timezone)
async def expect_timezone_text(message: Message) -> None:
    """Стикер, фото и т. п. там, где ждали название пояса."""
    await message.answer(texts.TEXT_ONLY)