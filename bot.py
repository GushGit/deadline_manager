"""Точка входа: логи, диспетчер, планировщик, polling."""
import asyncio
import logging
import logging.handlers
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database
from handlers import callbacks, errors, fallback, settings, start, tasks
from scheduler import check_reminders, expire_overdue_tasks

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Настраивает логи: консоль и файл с ротацией (~1 МБ, 3 файла)."""
    os.makedirs(os.path.dirname(config.LOG_PATH) or ".", exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file_handler)
    for name in ("aiogram", "aiohttp"):
        logging.getLogger(name).setLevel(logging.INFO)


def build_dispatcher() -> Dispatcher:
    """Создаёт диспетчер и подключает роутеры (fallback последним)."""
    dp = Dispatcher()
    dp.include_router(tasks.router)
    dp.include_router(callbacks.router)
    dp.include_router(settings.router)
    dp.include_router(start.router)
    dp.include_router(errors.router)
    dp.include_router(fallback.router)
    return dp


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создаёт планировщик с двумя jobs, но не запускает его."""
    sched = AsyncIOScheduler()
    sched.add_job(
        check_reminders,
        "interval",
        seconds=config.CHECK_INTERVAL_SECONDS,
        args=[bot],
        id="check_reminders",
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        expire_overdue_tasks,
        "interval",
        seconds=config.EXPIRE_INTERVAL_SECONDS,
        args=[bot],
        id="expire_overdue_tasks",
        max_instances=1,
        coalesce=True,
    )
    return sched


async def main() -> None:  # pragma: no cover (нужен реальный Telegram)
    """Запускает бота в режиме long polling."""
    token = config.require_token()
    setup_logging()
    await database.init_db(config.DB_PATH)
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    sched = setup_scheduler(bot)
    try:
        await bot.delete_webhook()
        await expire_overdue_tasks(bot)
        sched.start()
        logger.info("Бот запущен")
        await dp.start_polling(bot)
    finally:
        if sched.running:
            sched.shutdown(wait=False)
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass