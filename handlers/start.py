"""Команды /start и /help."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import texts

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Отправляет приветствие."""
    await message.answer(texts.START)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Отправляет список команд."""
    await message.answer(texts.HELP)