"""Глобальный обработчик необработанных исключений."""
import logging

from aiogram import Router
from aiogram.types import ErrorEvent

import texts

logger = logging.getLogger(__name__)
router = Router()


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    """Пишет ошибку в лог со стектрейсом и вежливо отвечает пользователю."""
    logger.error("Необработанная ошибка в хендлере", exc_info=event.exception)
    update = event.update
    try:
        if update.callback_query is not None:
            await update.callback_query.answer(texts.ERROR_GENERIC, show_alert=True)
        elif update.message is not None:
            await update.message.answer(texts.ERROR_GENERIC)
    except Exception:
        logger.exception("Не удалось отправить сообщение об ошибке")
    return True