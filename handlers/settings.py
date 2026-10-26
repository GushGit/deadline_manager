"""Команда /settings: часовой пояс и интервалы напоминаний."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import config
import database
import keyboards
import texts
import utils
from handlers.tasks import edit_text

router = Router()


def _offsets_text(offsets: tuple[int, ...]) -> str:
    """Интервалы словами: «за 1 день, за 1 час»."""
    return ", ".join(utils.format_offset(minutes) for minutes in offsets)


def _current_preset_key(offsets: tuple[int, ...]) -> str | None:
    """Ключ пресета, совпадающего с интервалами пользователя, или None."""
    for key, (minutes, _label) in config.OFFSET_PRESETS.items():
        if minutes == offsets:
            return key
    return None


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    """Показывает меню настроек с текущими значениями."""
    user = await database.get_or_create_user(config.DB_PATH, message.from_user.id)
    offsets = utils.parse_offsets(user["reminder_offsets"])
    await message.answer(
        texts.settings_menu(user["timezone"], _offsets_text(offsets)),
        reply_markup=keyboards.settings_keyboard(),
    )


@router.callback_query(F.data == "settings_tz")
async def settings_timezone(callback: CallbackQuery) -> None:
    """Повторно показывает выбор часового пояса (кнопки tz: из /start)."""
    await edit_text(
        callback, texts.CHOOSE_TIMEZONE, reply_markup=keyboards.timezone_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "settings_off")
async def settings_offsets(callback: CallbackQuery) -> None:
    """Показывает пресеты интервалов; текущий отмечен галочкой."""
    user = await database.get_or_create_user(config.DB_PATH, callback.from_user.id)
    offsets = utils.parse_offsets(user["reminder_offsets"])
    await edit_text(
        callback,
        texts.offsets_menu(_offsets_text(offsets)),
        reply_markup=keyboards.offsets_keyboard(_current_preset_key(offsets)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("off:"))
async def choose_offsets(callback: CallbackQuery) -> None:
    """Сохраняет выбранный пресет; действует только для новых задач."""
    key = callback.data.partition(":")[2]
    preset = config.OFFSET_PRESETS.get(key)
    if preset is None:
        await callback.answer(texts.BAD_BUTTON, show_alert=True)
        return
    minutes, label = preset
    user_id = callback.from_user.id
    await database.get_or_create_user(config.DB_PATH, user_id)
    await database.update_user_offsets(config.DB_PATH, user_id, minutes)
    await edit_text(callback, texts.offsets_saved(label))
    await callback.answer()