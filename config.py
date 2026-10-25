"""Настройки бота: чтение .env и константы проекта."""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "data/bot.db")
LOG_PATH = os.getenv("LOG_PATH", "logs/bot.log")

DEFAULT_TIMEZONE = "Europe/Moscow"
CHECK_INTERVAL_SECONDS = 30
EXPIRE_INTERVAL_SECONDS = 300
MAX_TITLE_LENGTH = 100
MAX_ACTIVE_TASKS = 50
MAX_DEADLINE_DAYS = 730
LATE_REMINDER_MINUTES = 5
LIST_PAGE_SIZE = 10

POPULAR_TIMEZONES = {
    "Москва": "Europe/Moscow",
    "Калининград": "Europe/Kaliningrad",
    "Самара": "Europe/Samara",
    "Екатеринбург": "Asia/Yekaterinburg",
    "Омск": "Asia/Omsk",
    "Новосибирск": "Asia/Novosibirsk",
    "Красноярск": "Asia/Krasnoyarsk",
    "Иркутск": "Asia/Irkutsk",
    "Якутск": "Asia/Yakutsk",
    "Владивосток": "Asia/Vladivostok",
}

OFFSET_PRESETS = {
    "d1h1": ((1440, 60), "за 1 день и за 1 час"),
    "d3d1h1": ((4320, 1440, 60), "за 3 дня, за 1 день и за 1 час"),
    "h1": ((60,), "только за 1 час"),
    "d1": ((1440,), "только за 1 день"),
}


def require_token() -> str:
    """Возвращает токен бота или завершает программу, если он не задан."""
    token = BOT_TOKEN.strip()
    if not token:
        print("Укажи BOT_TOKEN в файле .env")
        sys.exit(1)
    return token