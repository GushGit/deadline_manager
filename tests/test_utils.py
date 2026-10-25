from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

import config
import texts
import utils

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
MSK = "Europe/Moscow"
NSK = "Asia/Novosibirsk"
BER = "Europe/Berlin"


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def local_text(dt_utc: datetime, tz: str) -> str:
    return dt_utc.astimezone(ZoneInfo(tz)).strftime("%d.%m.%Y %H:%M")


# ---------- parse_user_datetime ----------

@pytest.mark.parametrize("text, expected", [
    ("28.10 23:59", utc(2026, 10, 28, 20, 59)),
    ("28.10.2026 23:59", utc(2026, 10, 28, 20, 59)),
    ("28.10.26 23:59", utc(2026, 10, 28, 20, 59)),
    ("1.11 9:05", utc(2026, 11, 1, 6, 5)),
    ("28/10 23:59", utc(2026, 10, 28, 20, 59)),
    ("28-10 23:59", utc(2026, 10, 28, 20, 59)),
    ("  28.10    23:59  ", utc(2026, 10, 28, 20, 59)),
    ("1.1.27 0:00", utc(2026, 12, 31, 21, 0)),
    ("29.02.2028 10:00", utc(2028, 2, 29, 7, 0)),
])
def test_parse_valid_formats(text, expected):
    result = utils.parse_user_datetime(text, MSK, NOW)
    assert result == expected
    assert result.utcoffset() == timedelta(0)


@pytest.mark.parametrize("text", [
    "", "   ", "abc", "завтра в 18:00", "28.10", "23:59",
    "28.10.202 23:59", "28.10 9:5", "28.10 24:00", "28.10 23:60",
    "32.13 25:61", "31.02 10:00", "31.04 10:00", "29.02.2027 10:00",
    "00.10 10:00", "01.00 10:00",
])
def test_parse_garbage_returns_none(text):
    assert utils.parse_user_datetime(text, MSK, NOW) is None


def test_parse_timezones_differ_by_four_hours():
    msk = utils.parse_user_datetime("28.10 23:59", MSK, NOW)
    nsk = utils.parse_user_datetime("28.10 23:59", NSK, NOW)
    assert msk - nsk == timedelta(hours=4)


def test_parse_past_returns_none():
    assert utils.parse_user_datetime("22.10.2026 10:00", MSK, NOW) is None
    assert utils.parse_user_datetime("01.01.0001 00:00", MSK, NOW) is None


def test_parse_must_be_strictly_later_than_now():
    assert utils.parse_user_datetime("23.10 15:00", MSK, NOW) is None
    assert utils.parse_user_datetime("23.10 15:01", MSK, NOW) == utc(2026, 10, 23, 12, 1)


def test_parse_without_year_today_time_passed():
    assert utils.parse_user_datetime("23.10 14:59", MSK, NOW) is None


def test_parse_without_year_earlier_date_goes_to_next_year():
    result = utils.parse_user_datetime("22.10 10:00", MSK, NOW)
    assert result == utc(2027, 10, 22, 7, 0)


def test_parse_without_year_uses_local_date_of_user():
    now = utc(2026, 12, 31, 22, 0)  # в Москве уже 01.01.2027
    assert utils.parse_user_datetime("01.01 12:00", MSK, now) == utc(2027, 1, 1, 9, 0)


def test_parse_leap_day_without_year():
    assert utils.parse_user_datetime("29.02 10:00", MSK, NOW) is None
    now = utc(2027, 10, 23, 12, 0)
    assert utils.parse_user_datetime("29.02 10:00", MSK, now) == utc(2028, 2, 29, 7, 0)


def test_parse_max_deadline_boundary():
    limit = NOW + timedelta(days=config.MAX_DEADLINE_DAYS)
    assert utils.parse_user_datetime(local_text(limit, MSK), MSK, NOW) == limit
    too_far = limit + timedelta(minutes=1)
    assert utils.parse_user_datetime(local_text(too_far, MSK), MSK, NOW) is None
    assert utils.parse_user_datetime("01.01.2029 10:00", MSK, NOW) is None


def test_parse_uses_config_max_deadline_days(monkeypatch):
    monkeypatch.setattr(config, "MAX_DEADLINE_DAYS", 10)
    assert utils.parse_user_datetime("02.11.2026 12:00", MSK, NOW) is not None
    assert utils.parse_user_datetime("03.11.2026 12:00", MSK, NOW) is None


def test_parse_berlin_nonexistent_time_is_rejected():
    assert utils.parse_user_datetime("28.03.2027 02:30", BER, NOW) is None
    assert utils.parse_user_datetime("28.03.2027 03:30", BER, NOW) == utc(2027, 3, 28, 1, 30)


def test_parse_berlin_ambiguous_time_takes_first_occurrence():
    result = utils.parse_user_datetime("31.10.2027 02:30", BER, NOW)
    assert result == utc(2027, 10, 31, 0, 30)


def test_parse_accepts_zoneinfo_object():
    result = utils.parse_user_datetime("28.10 23:59", ZoneInfo(MSK), NOW)
    assert result == utc(2026, 10, 28, 20, 59)


def test_parse_far_future_beyond_datetime_range():
    assert utils.parse_user_datetime("31.12.9999 23:59", "America/New_York", NOW) is None


def test_parse_naive_now_raises():
    with pytest.raises(ValueError):
        utils.parse_user_datetime("28.10 23:59", MSK, datetime(2026, 10, 23, 12, 0))


# ---------- explain_datetime_error ----------

EXPLAIN_CASES = [
    ("abc", MSK, texts.ERR_DT_FORMAT),
    ("", MSK, texts.ERR_DT_FORMAT),
    ("28.10 25:00", MSK, texts.ERR_DT_FORMAT),
    ("32.13 25:61", MSK, texts.ERR_DT_FORMAT),
    ("31.02 10:00", MSK, texts.ERR_DT_DATE),
    ("29.02.2027 10:00", MSK, texts.ERR_DT_DATE),
    ("29.02 10:00", MSK, texts.ERR_DT_DATE),
    ("22.10.2026 10:00", MSK, texts.ERR_DT_PAST),
    ("23.10 15:00", MSK, texts.ERR_DT_PAST),
    ("01.01.0001 00:00", MSK, texts.ERR_DT_PAST),
    ("01.01.2029 10:00", MSK, texts.ERR_DT_FAR),
    ("31.12.9999 23:59", "America/New_York", texts.ERR_DT_FAR),
    ("28.03.2027 02:30", BER, texts.ERR_DT_GAP),
]


@pytest.mark.parametrize("text, tz, expected", EXPLAIN_CASES)
def test_explain_returns_reason(text, tz, expected):
    assert utils.explain_datetime_error(text, tz, NOW) == expected


def test_explain_reasons_are_distinct_and_mention_cause():
    assert "формат" in texts.ERR_DT_FORMAT
    assert "не существует" in texts.ERR_DT_DATE
    assert "уже прошла" in texts.ERR_DT_PAST
    assert "2 года" in texts.ERR_DT_FAR
    assert "не бывает" in texts.ERR_DT_GAP
    reasons = {case[2] for case in EXPLAIN_CASES}
    assert len(reasons) == 5


def test_explain_valid_input_returns_empty_string():
    assert utils.explain_datetime_error("28.10 23:59", MSK, NOW) == ""


def test_explain_consistent_with_parser():
    samples = [(case[0], case[1]) for case in EXPLAIN_CASES]
    samples += [("28.10 23:59", MSK), ("1.11 9:05", NSK), ("31.10.2027 02:30", BER)]
    for text, tz in samples:
        parsed = utils.parse_user_datetime(text, tz, NOW)
        reason = utils.explain_datetime_error(text, tz, NOW)
        assert (parsed is None) == (reason != ""), text


def test_explain_naive_now_raises():
    with pytest.raises(ValueError):
        utils.explain_datetime_error("28.10 23:59", MSK, datetime(2026, 10, 23))


# ---------- calc_reminder_times ----------

def test_calc_reminder_times_deadline_in_three_days():
    deadline = NOW + timedelta(days=3)
    result = utils.calc_reminder_times(deadline, (1440, 60), NOW)
    assert result == [deadline - timedelta(days=1), deadline - timedelta(hours=1)]


def test_calc_reminder_times_five_hours_keeps_only_hour_before():
    deadline = NOW + timedelta(hours=5)
    assert utils.calc_reminder_times(deadline, (1440, 60), NOW) == [
        deadline - timedelta(hours=1)
    ]


def test_calc_reminder_times_thirty_minutes_gives_empty():
    assert utils.calc_reminder_times(NOW + timedelta(minutes=30), (1440, 60), NOW) == []


def test_calc_reminder_times_only_strictly_future():
    assert utils.calc_reminder_times(NOW + timedelta(minutes=60), (60,), NOW) == []


def test_calc_reminder_times_sorted_ascending_for_any_input_order():
    deadline = NOW + timedelta(days=5)
    result = utils.calc_reminder_times(deadline, (60, 4320, 1440), NOW)
    assert result == sorted(result)
    assert len(result) == 3


# ---------- to_user_tz, format_deadline ----------

def test_to_user_tz_converts_by_name_and_zoneinfo():
    dt = utc(2026, 10, 28, 20, 59)
    local = utils.to_user_tz(dt, MSK)
    assert (local.hour, local.minute) == (23, 59)
    assert local.utcoffset() == timedelta(hours=3)
    assert utils.to_user_tz(dt, ZoneInfo(NSK)).hour == 3


def test_to_user_tz_rejects_naive_and_unknown_zone():
    with pytest.raises(ValueError):
        utils.to_user_tz(datetime(2026, 10, 28, 20, 59), MSK)
    with pytest.raises(ZoneInfoNotFoundError):
        utils.to_user_tz(utc(2026, 10, 28, 20, 59), "No/Such_Zone")


def test_format_deadline_without_year():
    assert utils.format_deadline(utc(2026, 10, 28, 20, 59), MSK, NOW) == "28.10 в 23:59"


def test_format_deadline_with_year_when_differs():
    assert utils.format_deadline(utc(2027, 10, 28, 20, 59), MSK, NOW) == "28.10.2027 в 23:59"


def test_format_deadline_uses_local_year_of_deadline():
    deadline = utc(2026, 12, 31, 22, 0)  # в Москве уже 01.01.2027
    assert utils.format_deadline(deadline, MSK, NOW) == "01.01.2027 в 01:00"


def test_format_deadline_compares_with_local_now_year():
    now = utc(2026, 12, 31, 22, 0)  # в Москве уже 2027 год
    assert utils.format_deadline(utc(2027, 1, 5, 9, 0), MSK, now) == "05.01 в 12:00"


# ---------- format_time_left ----------

@pytest.mark.parametrize("delta, expected", [
    (timedelta(0), "просрочено"),
    (timedelta(minutes=-5), "просрочено"),
    (timedelta(seconds=0.5), "менее минуты"),
    (timedelta(seconds=59.9), "менее минуты"),
    (timedelta(minutes=1), "через 1 мин."),
    (timedelta(minutes=45), "через 45 мин."),
    (timedelta(minutes=59), "через 59 мин."),
    (timedelta(minutes=59, seconds=59), "через 59 мин."),
    (timedelta(minutes=60), "через 1 ч."),
    (timedelta(hours=3), "через 3 ч."),
    (timedelta(hours=3, minutes=15), "через 3 ч. 15 мин."),
    (timedelta(hours=23, minutes=59), "через 23 ч. 59 мин."),
    (timedelta(hours=24), "через 1 дн."),
    (timedelta(days=2), "через 2 дн."),
    (timedelta(days=2, hours=3), "через 2 дн. 3 ч."),
    (timedelta(days=2, hours=3, minutes=40), "через 2 дн. 3 ч."),
])
def test_format_time_left(delta, expected):
    assert utils.format_time_left(delta) == expected


# ---------- plural_ru, format_offset ----------

@pytest.mark.parametrize("n, expected", [
    (0, "дней"), (1, "день"), (2, "дня"), (4, "дня"), (5, "дней"),
    (11, "дней"), (12, "дней"), (14, "дней"), (21, "день"), (22, "дня"),
    (25, "дней"), (100, "дней"), (101, "день"), (111, "дней"), (112, "дней"),
])
def test_plural_ru(n, expected):
    assert utils.plural_ru(n, "день", "дня", "дней") == expected


@pytest.mark.parametrize("minutes, expected", [
    (30, "за 30 мин."),
    (60, "за 1 час"),
    (120, "за 2 часа"),
    (300, "за 5 часов"),
    (1500, "за 25 часов"),
    (1440, "за 1 день"),
    (4320, "за 3 дня"),
    (7200, "за 5 дней"),
    (90, "за 1 ч. 30 мин."),
    (150, "за 2 ч. 30 мин."),
])
def test_format_offset(minutes, expected):
    assert utils.format_offset(minutes) == expected


# ---------- parse_offsets, offsets_to_str ----------

def test_parse_offsets():
    assert utils.parse_offsets("1440,60") == (1440, 60)
    assert utils.parse_offsets("60") == (60,)
    assert utils.parse_offsets(" 1440 , 60 ") == (1440, 60)
    assert utils.parse_offsets("") == ()


def test_parse_offsets_invalid_raises():
    with pytest.raises(ValueError):
        utils.parse_offsets("abc")


def test_offsets_to_str():
    assert utils.offsets_to_str((1440, 60)) == "1440,60"
    assert utils.offsets_to_str(()) == ""


def test_offsets_roundtrip_for_all_presets():
    for minutes, _label in config.OFFSET_PRESETS.values():
        assert utils.parse_offsets(utils.offsets_to_str(minutes)) == minutes


# ---------- day_bounds_utc ----------

def test_day_bounds_moscow_today():
    assert utils.day_bounds_utc(MSK, NOW, 1) == (
        utc(2026, 10, 22, 21, 0), utc(2026, 10, 23, 21, 0),
    )


def test_day_bounds_novosibirsk_today():
    assert utils.day_bounds_utc(NSK, NOW, 1) == (
        utc(2026, 10, 22, 17, 0), utc(2026, 10, 23, 17, 0),
    )


def test_day_bounds_local_day_changes_with_timezone():
    now = utc(2026, 10, 23, 18, 0)  # в Москве 21:00, в Новосибирске уже 24.10
    assert utils.day_bounds_utc(MSK, now, 1)[0] == utc(2026, 10, 22, 21, 0)
    assert utils.day_bounds_utc(NSK, now, 1)[0] == utc(2026, 10, 23, 17, 0)


def test_day_bounds_week():
    start, end = utils.day_bounds_utc(MSK, NOW, 7)
    assert start == utc(2026, 10, 22, 21, 0)
    assert end == utc(2026, 10, 29, 21, 0)


def test_day_bounds_are_local_midnights_across_dst_change():
    now = utc(2026, 10, 24, 12, 0)  # 25.10.2026 в Берлине переход на зимнее время
    start, end = utils.day_bounds_utc(BER, now, 2)
    assert start == utc(2026, 10, 23, 22, 0)
    assert end == utc(2026, 10, 25, 23, 0)
    assert end - start == timedelta(hours=49)


def test_day_bounds_accepts_zoneinfo_and_returns_aware_utc():
    start, end = utils.day_bounds_utc(ZoneInfo(MSK), NOW, 1)
    assert start.utcoffset() == timedelta(0) and end.utcoffset() == timedelta(0)