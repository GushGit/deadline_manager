"""Чистые функции работы со временем и текстом (без БД, сети и часов)."""
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import config
import texts

_DATETIME_RE = re.compile(
    r"^(\d{1,2})[./-](\d{1,2})(?:[./-](\d{4}|\d{2}))?"
    r" (\d{1,2}):(\d{2})$"
)


def _zone(tz: str | ZoneInfo) -> ZoneInfo:
    """Принимает имя пояса (IANA) или готовый ZoneInfo."""
    return tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)


def _resolve(
    text: str, tz: str | ZoneInfo, now_utc: datetime
) -> tuple[datetime | None, str | None]:
    """Разбор и проверки: возвращает (дата UTC, None) или (None, текст причины)."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc должен быть aware-datetime")
    zone = _zone(tz)
    match = _DATETIME_RE.match(" ".join(text.split()))
    if not match:
        return None, texts.ERR_DT_FORMAT
    day, month, year_text, hour, minute = match.groups()
    day, month, hour, minute = int(day), int(month), int(hour), int(minute)
    if hour > 23 or minute > 59:
        return None, texts.ERR_DT_FORMAT

    now_local = now_utc.astimezone(zone)
    if year_text is None:
        year = now_local.year
        if (month, day) < (now_local.month, now_local.day):
            year += 1
    elif len(year_text) == 2:
        year = 2000 + int(year_text)
    else:
        year = int(year_text)

    try:
        local = datetime(year, month, day, hour, minute, tzinfo=zone)
        utc = local.astimezone(timezone.utc)
    except ValueError:
        return None, texts.ERR_DT_DATE
    except OverflowError:
        # дата у границы datetime: слишком давняя или слишком далёкая
        past = year < now_local.year
        return None, texts.ERR_DT_PAST if past else texts.ERR_DT_FAR

    if utc.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
        return None, texts.ERR_DT_GAP
    if utc <= now_utc:
        return None, texts.ERR_DT_PAST
    if utc - now_utc > timedelta(days=config.MAX_DEADLINE_DAYS):
        return None, texts.ERR_DT_FAR
    return utc, None


def parse_user_datetime(
    text: str, tz: str | ZoneInfo, now_utc: datetime
) -> datetime | None:
    """Разбирает ввод пользователя в aware-UTC или возвращает None."""
    return _resolve(text, tz, now_utc)[0]


def explain_datetime_error(
    text: str, tz: str | ZoneInfo, now_utc: datetime
) -> str:
    """Причина, по которой ввод не принят; для корректного ввода пустая строка."""
    return _resolve(text, tz, now_utc)[1] or ""


def calc_reminder_times(
    deadline_utc: datetime, offsets: tuple[int, ...], now_utc: datetime
) -> list[datetime]:
    """Времена напоминаний (дедлайн минус интервал), только строго будущие."""
    times = [deadline_utc - timedelta(minutes=minutes) for minutes in offsets]
    return sorted(moment for moment in times if moment > now_utc)


def to_user_tz(dt_utc: datetime, tz: str | ZoneInfo) -> datetime:
    """Переводит aware-datetime в часовой пояс пользователя."""
    if dt_utc.tzinfo is None:
        raise ValueError("нужен aware-datetime")
    return dt_utc.astimezone(_zone(tz))


def format_deadline(dt_utc: datetime, tz: str | ZoneInfo, now_utc: datetime) -> str:
    """«28.10 в 23:59»; с годом, если он не совпадает с текущим локальным."""
    local = to_user_tz(dt_utc, tz)
    if local.year != to_user_tz(now_utc, tz).year:
        return f"{local:%d.%m.%Y} в {local:%H:%M}"
    return f"{local:%d.%m} в {local:%H:%M}"


def format_time_left(delta: timedelta) -> str:
    """Сколько осталось: «через 2 дн. 3 ч.», округление вниз."""
    total = delta.total_seconds()
    if total <= 0:
        return "просрочено"
    seconds = int(total)
    if seconds < 60:
        return "менее минуты"
    minutes = seconds // 60
    if minutes < 60:
        return f"через {minutes} мин."
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"через {hours} ч. {minutes} мин." if minutes else f"через {hours} ч."
    days, hours = divmod(hours, 24)
    return f"через {days} дн. {hours} ч." if hours else f"через {days} дн."


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    """Форма слова для числа: 1 день, 2 дня, 5 дней (возвращает только слово)."""
    n = abs(n)
    if 11 <= n % 100 <= 14:
        return many
    if n % 10 == 1:
        return one
    if 2 <= n % 10 <= 4:
        return few
    return many


def format_offset(minutes: int) -> str:
    """Интервал напоминания: «за 1 час», «за 3 дня», «за 1 ч. 30 мин.»."""
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"за {days} {plural_ru(days, 'день', 'дня', 'дней')}"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"за {hours} {plural_ru(hours, 'час', 'часа', 'часов')}"
    if minutes < 60:
        return f"за {minutes} мин."
    hours, rest = divmod(minutes, 60)
    return f"за {hours} ч. {rest} мин."


def parse_offsets(s: str) -> tuple[int, ...]:
    """'1440,60' в (1440, 60); пустая строка даёт пустой кортеж."""
    return tuple(int(part) for part in s.split(",") if part.strip())


def offsets_to_str(offsets: tuple[int, ...]) -> str:
    """(1440, 60) в '1440,60'; обратная к parse_offsets."""
    return ",".join(str(minutes) for minutes in offsets)


def day_bounds_utc(
    tz: str | ZoneInfo, now_utc: datetime, days: int
) -> tuple[datetime, datetime]:
    """Начало локального дня и начало дня через days суток, обе границы в UTC."""
    zone = _zone(tz)
    today = to_user_tz(now_utc, zone).date()
    start = datetime.combine(today, time.min, tzinfo=zone)
    end = datetime.combine(today + timedelta(days=days), time.min, tzinfo=zone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)