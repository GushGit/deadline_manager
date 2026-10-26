"""Ответ на непонятные сообщения вне диалога (подключается последним)."""
from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.types import Message

import texts

router = Router()


@router.message(StateFilter(None))
async def unknown_message(message: Message) -> None:
    """Подсказывает про /help, если сообщение не распознано."""
    await message.answer(texts.FALLBACK)