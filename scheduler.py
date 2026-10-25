"""Фоновые задачи: отправка напоминаний и закрытие просроченных задач."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup

import config
import database
import keyboards
import texts
import utils

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    """Текущее время в UTC (единственное место в jobs; в тестах подменяется)."""
    return datetime.now(timezone.utc)


async def _send_message(
    bot: Bot, user_id: int, text: str, reply_markup: InlineKeyboardMarkup
) -> str:
    """Отправляет сообщение; возвращает "sent", "forbidden" или "failed"."""
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup)
    except TelegramForbiddenError:
        logger.warning("Пользователь %s заблокировал бота", user_id)
        return "forbidden"
    except TelegramRetryAfter as error:
        logger.warning(
            "Лимит Telegram, повтор позже: user_id=%s, retry_after=%s",
            user_id,
            error.retry_after,
        )
        return "failed"
    except TelegramNetworkError:
        logger.warning("Сеть Telegram недоступна: user_id=%s", user_id)
        return "failed"
    except Exception:
        logger.exception("Не удалось отправить сообщение: user_id=%s", user_id)
        return "failed"
    return "sent"


async def _process_reminder(bot: Bot, reminder: dict, now: datetime) -> None:
    """Обрабатывает одно напоминание: отправляет и помечает отправленным."""
    reminder_id = reminder["reminder_id"]
    if reminder["deadline"] <= now:
        await database.mark_reminder_sent(config.DB_PATH, reminder_id)
        return
    late = now - reminder["remind_at"] > timedelta(minutes=config.LATE_REMINDER_MINUTES)
    text = texts.reminder(
        reminder["title"],
        utils.format_deadline(reminder["deadline"], reminder["timezone"], now),
        utils.format_time_left(reminder["deadline"] - now),
        late,
    )
    result = await _send_message(
        bot, reminder["user_id"], text, keyboards.reminder_keyboard(reminder["task_id"])
    )
    if result == "failed":
        return
    await database.mark_reminder_sent(config.DB_PATH, reminder_id)
    if result == "sent":
        logger.info(
            "Отправлено напоминание reminder_id=%s, user_id=%s",
            reminder_id,
            reminder["user_id"],
        )


async def check_reminders(bot: Bot) -> None:
    """Отправляет все наступившие напоминания; ошибка одного не мешает остальным."""
    now = _now_utc()
    for reminder in await database.get_due_reminders(config.DB_PATH, now):
        try:
            await _process_reminder(bot, reminder, now)
        except Exception:
            logger.exception(
                "Ошибка обработки напоминания reminder_id=%s", reminder["reminder_id"]
            )
        await asyncio.sleep(config.SEND_PAUSE_SECONDS)


async def expire_overdue_tasks(bot: Bot) -> None:
    """Закрывает просроченные задачи и один раз сообщает об этом пользователям."""
    expired = await database.expire_overdue_tasks(config.DB_PATH, _now_utc())
    for task in expired:
        logger.info(
            "Задача просрочена: task_id=%s, user_id=%s", task["task_id"], task["user_id"]
        )
        await _send_message(
            bot,
            task["user_id"],
            texts.task_expired(task["title"]),
            keyboards.expired_keyboard(task["task_id"]),
        )
        await asyncio.sleep(config.SEND_PAUSE_SECONDS)