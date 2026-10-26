import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

import config
import database
import keyboards
import scheduler
import texts

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def sql(path, query, params=()):
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute(query, params).fetchall()
        conn.commit()
    return rows


def forbidden():
    return TelegramForbiddenError(method=MagicMock(), message="bot was blocked by the user")


def retry_after():
    return TelegramRetryAfter(method=MagicMock(), message="Flood control", retry_after=7)


def network_error():
    return TelegramNetworkError(method=MagicMock(), message="connection lost")


@pytest.fixture
async def env(db_path, monkeypatch):
    await database.init_db(db_path)
    monkeypatch.setattr(scheduler, "_now_utc", lambda: NOW)
    monkeypatch.setattr(config, "SEND_PAUSE_SECONDS", 0)
    return db_path


async def add(path, user_id=1, title="Лаба", deadline=None, reminders=()):
    await database.get_or_create_user(path, user_id)
    deadline = deadline or NOW + timedelta(hours=1)
    return await database.add_task(path, user_id, title, deadline, list(reminders))


def sent_flags(path):
    return [row[0] for row in sql(path, "SELECT sent FROM reminders ORDER BY id")]


def messages(caplog, level):
    return [r.getMessage() for r in caplog.records if r.levelno == level]


# ---------- _now_utc ----------

def test_now_utc_is_aware_and_current():
    before = datetime.now(timezone.utc)
    value = scheduler._now_utc()
    after = datetime.now(timezone.utc)
    assert value.utcoffset() == timedelta(0)
    assert before <= value <= after


# ---------- _send_message ----------

async def test_send_message_success(fake_bot):
    markup = keyboards.expired_keyboard(5)
    result = await scheduler._send_message(fake_bot, 42, "текст", markup)
    assert result == "sent"
    fake_bot.send_message.assert_awaited_once_with(42, "текст", reply_markup=markup)


async def test_send_message_forbidden(fake_bot, caplog):
    fake_bot.send_message.side_effect = forbidden()
    with caplog.at_level(logging.WARNING):
        result = await scheduler._send_message(fake_bot, 42, "т", None)
    assert result == "forbidden"
    assert any("42" in m and "заблокировал" in m for m in messages(caplog, logging.WARNING))


@pytest.mark.parametrize("make_error", [retry_after, network_error, lambda: RuntimeError("boom")])
async def test_send_message_temporary_failures(fake_bot, caplog, make_error):
    fake_bot.send_message.side_effect = make_error()
    with caplog.at_level(logging.WARNING):
        result = await scheduler._send_message(fake_bot, 42, "т", None)
    assert result == "failed"
    assert any("42" in r.getMessage() for r in caplog.records)


async def test_send_message_unexpected_error_is_logged_with_traceback(fake_bot, caplog):
    fake_bot.send_message.side_effect = RuntimeError("boom")
    with caplog.at_level(logging.ERROR):
        await scheduler._send_message(fake_bot, 42, "т", None)
    assert [r for r in caplog.records if r.levelno == logging.ERROR and r.exc_info]


# ---------- check_reminders: успех ----------

async def test_check_reminders_sends_and_marks(env, fake_bot, caplog):
    task_id = await add(env, reminders=[NOW - timedelta(minutes=1)])
    with caplog.at_level(logging.INFO):
        await scheduler.check_reminders(fake_bot)

    expected = texts.reminder("Лаба", "23.10 в 16:00", "через 1 ч.", False)
    fake_bot.send_message.assert_awaited_once_with(
        1, expected, reply_markup=keyboards.reminder_keyboard(task_id)
    )
    assert sent_flags(env) == [1]
    reminder_id = sql(env, "SELECT id FROM reminders")[0][0]
    assert any(
        f"reminder_id={reminder_id}" in m and "user_id=1" in m
        for m in messages(caplog, logging.INFO)
    )


async def test_check_reminders_nothing_due(env, fake_bot):
    await add(env, reminders=[NOW + timedelta(minutes=10)])
    await scheduler.check_reminders(fake_bot)
    fake_bot.send_message.assert_not_awaited()
    assert sent_flags(env) == [0]


async def test_check_reminders_skips_inactive_tasks(env, fake_bot):
    done_id = await add(env, title="done", reminders=[NOW - timedelta(minutes=1)])
    await add(env, title="live", reminders=[NOW - timedelta(minutes=1)])
    await database.mark_task_done(env, done_id, 1, NOW)
    await scheduler.check_reminders(fake_bot)
    assert fake_bot.send_message.await_count == 1
    assert "live" in fake_bot.send_message.await_args.args[1]


async def test_check_reminders_uses_user_timezone_and_escapes_title(env, fake_bot):
    await add(env, title="<b>x</b>", reminders=[NOW - timedelta(minutes=1)])
    await database.update_user_timezone(env, 1, "Asia/Novosibirsk")
    await scheduler.check_reminders(fake_bot)
    text = fake_bot.send_message.await_args.args[1]
    assert "23.10 в 20:00" in text
    assert "&lt;b&gt;x&lt;/b&gt;" in text and "<b>x</b>" not in text


# ---------- опоздавшие и просроченные напоминания ----------

async def test_check_reminders_marks_late_reminder(env, fake_bot):
    await add(env, reminders=[NOW - timedelta(minutes=config.LATE_REMINDER_MINUTES + 1)])
    await scheduler.check_reminders(fake_bot)
    assert "опоздало" in fake_bot.send_message.await_args.args[1]


async def test_check_reminders_exact_late_threshold_is_not_late(env, fake_bot):
    await add(env, reminders=[NOW - timedelta(minutes=config.LATE_REMINDER_MINUTES)])
    await scheduler.check_reminders(fake_bot)
    assert "опоздало" not in fake_bot.send_message.await_args.args[1]


async def test_check_reminders_deadline_passed_marks_without_sending(env, fake_bot):
    await add(env, deadline=NOW - timedelta(minutes=1), reminders=[NOW - timedelta(hours=2)])
    await scheduler.check_reminders(fake_bot)
    fake_bot.send_message.assert_not_awaited()
    assert sent_flags(env) == [1]


async def test_check_reminders_deadline_equal_now_marks_without_sending(env, fake_bot):
    await add(env, deadline=NOW, reminders=[NOW - timedelta(minutes=1)])
    await scheduler.check_reminders(fake_bot)
    fake_bot.send_message.assert_not_awaited()
    assert sent_flags(env) == [1]


# ---------- ошибки отправки ----------

async def test_check_reminders_forbidden_marks_sent(env, fake_bot, caplog):
    await add(env, reminders=[NOW - timedelta(minutes=1)])
    fake_bot.send_message.side_effect = forbidden()
    with caplog.at_level(logging.WARNING):
        await scheduler.check_reminders(fake_bot)
    assert sent_flags(env) == [1]
    assert any("заблокировал" in m for m in messages(caplog, logging.WARNING))
    assert not any("Отправлено" in m for m in messages(caplog, logging.INFO))


@pytest.mark.parametrize("make_error", [retry_after, network_error, lambda: RuntimeError("boom")])
async def test_check_reminders_temporary_error_keeps_unsent(env, fake_bot, make_error):
    await add(env, reminders=[NOW - timedelta(minutes=1)])
    fake_bot.send_message.side_effect = make_error()
    await scheduler.check_reminders(fake_bot)
    assert sent_flags(env) == [0]


@pytest.mark.parametrize("make_error", [forbidden, retry_after, network_error, lambda: RuntimeError("boom")])
async def test_check_reminders_error_does_not_stop_others(env, fake_bot, make_error):
    await add(env, title="первая", reminders=[NOW - timedelta(minutes=2)])
    await add(env, user_id=2, title="вторая", reminders=[NOW - timedelta(minutes=1)])
    fake_bot.send_message.side_effect = [make_error(), None]
    await scheduler.check_reminders(fake_bot)
    assert fake_bot.send_message.await_count == 2
    assert sent_flags(env)[1] == 1


async def test_check_reminders_db_error_on_one_record_does_not_stop_others(
    env, fake_bot, monkeypatch, caplog
):
    await add(env, title="первая", reminders=[NOW - timedelta(minutes=2)])
    await add(env, user_id=2, title="вторая", reminders=[NOW - timedelta(minutes=1)])
    real_mark = database.mark_reminder_sent
    calls = []

    async def flaky(path, reminder_id):
        calls.append(reminder_id)
        if len(calls) == 1:
            raise RuntimeError("db is locked")
        await real_mark(path, reminder_id)

    monkeypatch.setattr(scheduler.database, "mark_reminder_sent", flaky)
    with caplog.at_level(logging.ERROR):
        await scheduler.check_reminders(fake_bot)
    assert sent_flags(env) == [0, 1]
    assert any("reminder_id" in m for m in messages(caplog, logging.ERROR))


async def test_check_reminders_pauses_between_sends(env, fake_bot, monkeypatch):
    await add(env, title="a", reminders=[NOW - timedelta(minutes=2)])
    await add(env, user_id=2, title="b", reminders=[NOW - timedelta(minutes=1)])
    monkeypatch.setattr(config, "SEND_PAUSE_SECONDS", 0.05)
    sleep = AsyncMock()
    monkeypatch.setattr(scheduler.asyncio, "sleep", sleep)
    await scheduler.check_reminders(fake_bot)
    assert sleep.await_count == 2
    sleep.assert_awaited_with(0.05)


async def test_check_reminders_second_run_does_not_duplicate(env, fake_bot):
    await add(env, reminders=[NOW - timedelta(minutes=1)])
    await scheduler.check_reminders(fake_bot)
    await scheduler.check_reminders(fake_bot)
    assert fake_bot.send_message.await_count == 1


# ---------- expire_overdue_tasks ----------

async def test_expire_notifies_once_with_button(env, fake_bot):
    task_id = await add(env, deadline=NOW - timedelta(minutes=1))
    await scheduler.expire_overdue_tasks(fake_bot)
    fake_bot.send_message.assert_awaited_once_with(
        1, texts.task_expired("Лаба"), reply_markup=keyboards.expired_keyboard(task_id)
    )
    assert sql(env, "SELECT status FROM tasks") == [("expired",)]

    await scheduler.expire_overdue_tasks(fake_bot)
    assert fake_bot.send_message.await_count == 1


async def test_expire_nothing_overdue(env, fake_bot):
    await add(env, title="future", deadline=NOW + timedelta(hours=1))
    await add(env, title="edge", deadline=NOW)
    await scheduler.expire_overdue_tasks(fake_bot)
    fake_bot.send_message.assert_not_awaited()
    assert sql(env, "SELECT status FROM tasks ORDER BY id") == [("active",), ("active",)]


async def test_expire_escapes_title(env, fake_bot):
    await add(env, title="<i>x</i>", deadline=NOW - timedelta(minutes=1))
    await scheduler.expire_overdue_tasks(fake_bot)
    text = fake_bot.send_message.await_args.args[1]
    assert "&lt;i&gt;x&lt;/i&gt;" in text and "<i>" not in text


@pytest.mark.parametrize("make_error", [forbidden, retry_after, network_error, lambda: RuntimeError("boom")])
async def test_expire_send_error_does_not_break_job(env, fake_bot, make_error):
    await add(env, title="первая", deadline=NOW - timedelta(minutes=2))
    await add(env, user_id=2, title="вторая", deadline=NOW - timedelta(minutes=1))
    fake_bot.send_message.side_effect = [make_error(), None]
    await scheduler.expire_overdue_tasks(fake_bot)
    assert fake_bot.send_message.await_count == 2
    assert sql(env, "SELECT status FROM tasks ORDER BY id") == [("expired",), ("expired",)]


async def test_expire_failed_notification_is_not_repeated(env, fake_bot):
    await add(env, deadline=NOW - timedelta(minutes=1))
    fake_bot.send_message.side_effect = network_error()
    await scheduler.expire_overdue_tasks(fake_bot)
    await scheduler.expire_overdue_tasks(fake_bot)
    assert fake_bot.send_message.await_count == 1


async def test_expire_pauses_between_sends(env, fake_bot, monkeypatch):
    await add(env, title="a", deadline=NOW - timedelta(minutes=2))
    await add(env, user_id=2, title="b", deadline=NOW - timedelta(minutes=1))
    monkeypatch.setattr(config, "SEND_PAUSE_SECONDS", 0.05)
    sleep = AsyncMock()
    monkeypatch.setattr(scheduler.asyncio, "sleep", sleep)
    await scheduler.expire_overdue_tasks(fake_bot)
    assert sleep.await_count == 2


async def test_expired_task_disappears_from_due_reminders(env, fake_bot):
    await add(env, deadline=NOW - timedelta(minutes=1), reminders=[NOW - timedelta(hours=1)])
    await scheduler.expire_overdue_tasks(fake_bot)
    fake_bot.send_message.reset_mock()
    await scheduler.check_reminders(fake_bot)
    fake_bot.send_message.assert_not_awaited()



# ---------- служебная функция _process_reminder ----------

async def first_due(path):
    return (await database.get_due_reminders(path, NOW))[0]


async def test_process_reminder_sends_and_marks(env, fake_bot):
    await add(env, reminders=[NOW - timedelta(minutes=1)])
    await scheduler._process_reminder(fake_bot, await first_due(env), NOW)
    fake_bot.send_message.assert_awaited_once()
    assert sent_flags(env) == [1]


async def test_process_reminder_failed_send_keeps_unsent(env, fake_bot):
    await add(env, reminders=[NOW - timedelta(minutes=1)])
    fake_bot.send_message.side_effect = network_error()
    await scheduler._process_reminder(fake_bot, await first_due(env), NOW)
    assert sent_flags(env) == [0]


async def test_process_reminder_passed_deadline_marks_without_sending(env, fake_bot):
    await add(env, deadline=NOW + timedelta(minutes=1), reminders=[NOW - timedelta(hours=1)])
    reminder = await first_due(env)
    later = NOW + timedelta(minutes=5)
    await scheduler._process_reminder(fake_bot, reminder, later)
    fake_bot.send_message.assert_not_awaited()
    assert sent_flags(env) == [1]