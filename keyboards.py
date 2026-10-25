"""Фабрики inline-клавиатур."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Кнопки подтверждения в /add: сохранить или отменить."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сохранить ✅", callback_data="add_save"),
                InlineKeyboardButton(text="Отмена ❌", callback_data="add_cancel"),
            ]
        ]
    )