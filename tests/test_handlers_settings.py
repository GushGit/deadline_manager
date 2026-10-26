import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest

import config
import database
import keyboards
import texts
from handlers import settings

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def sql(path, query, params=()):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(query, params).fetchall()


@pytest.fixture
async def env(db_path):
    await database.init_db(db_path)
    return db_path


async def offsets_of(path, user_id=1):
    return (await database.get_or_create_user(path, user_id))["reminder_offsets"]


# ---------- вспомогательные функции ----------

@pytest.mark.parametrize("offsets, expected", [
    ((1440, 60), "за 1 день, за 1 час"),
    ((4320, 1440, 60), "за 3 дня, за 1 день, за 1 час"),
    ((30,), "за 30 мин."),
    ((), ""),
])
def test_offsets_text(offsets, expected):
    assert settings._offsets_text(offsets) == expected


@pytest.mark.parametrize("offsets, expected", [
    ((1440, 60), "d1h1"),
    ((4320, 1440, 60), "d3d1h1"),
    ((60,), "h1"),
    ((1440,), "d1"),
    ((30,), None),
    ((60, 1440), None),
    ((), None),
])
def test_current_preset_key(offsets, expected):
    assert settings._current_preset_key(offsets) == expected


# ---------- /settings ----------

async def test_cmd_settings_shows_defaults(env, fake_message):
    await settings.cmd_settings(fake_message)
    fake_message.answer.assert_awaited_once_with(
        texts.settings_menu("Europe/Moscow", "за 1 день, за 1 час"),
        reply_markup=keyboards.settings_keyboard(),
    )
    assert sql(env, "SELECT id FROM users") == [(1,)]


async def test_cmd_settings_shows_current_values(env, fake_message):
    await database.get_or_create_user(env, 1)
    await database.update_user_timezone(env, 1, "Asia/Novosibirsk")
    await database.update_user_offsets(env, 1, (4320, 1440, 60))
    await settings.cmd_settings(fake_message)
    text = fake_message.answer.await_args.args[0]
    assert "Asia/Novosibirsk" in text
    assert "за 3 дня, за 1 день, за 1 час" in text


# ---------- settings_tz ----------

async def test_settings_timezone_shows_timezone_keyboard(fake_callback):
    fake_callback.data = "settings_tz"
    await settings.settings_timezone(fake_callback)
    fake_callback.message.edit_text.assert_awaited_once_with(
        texts.CHOOSE_TIMEZONE, reply_markup=keyboards.timezone_keyboard()
    )
    fake_callback.answer.assert_awaited_once_with()


async def test_settings_timezone_survives_edit_error(fake_callback):
    fake_callback.message.edit_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="message is not modified"
    )
    await settings.settings_timezone(fake_callback)
    fake_callback.answer.assert_awaited_once_with()


# ---------- settings_off ----------

async def test_settings_offsets_marks_default_preset(env, fake_callback):
    fake_callback.data = "settings_off"
    await settings.settings_offsets(fake_callback)
    fake_callback.message.edit_text.assert_awaited_once_with(
        texts.offsets_menu("за 1 день, за 1 час"),
        reply_markup=keyboards.offsets_keyboard("d1h1"),
    )
    fake_callback.answer.assert_awaited_once_with()


async def test_settings_offsets_marks_other_preset(env, fake_callback):
    await database.get_or_create_user(env, 1)
    await database.update_user_offsets(env, 1, (60,))
    await settings.settings_offsets(fake_callback)
    markup = fake_callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert markup == keyboards.offsets_keyboard("h1")


async def test_settings_offsets_without_matching_preset_marks_nothing(env, fake_callback):
    await database.get_or_create_user(env, 1)
    await database.update_user_offsets(env, 1, (30,))
    await settings.settings_offsets(fake_callback)
    args = fake_callback.message.edit_text.await_args
    assert "Сейчас: за 30 мин." in args.args[0]
    assert args.kwargs["reply_markup"] == keyboards.offsets_keyboard(None)


# ---------- off:<key> ----------

@pytest.mark.parametrize("key", list(config.OFFSET_PRESETS))
async def test_choose_offsets_saves_every_preset(env, fake_callback, key):
    minutes, label = config.OFFSET_PRESETS[key]
    fake_callback.data = f"off:{key}"
    await settings.choose_offsets(fake_callback)
    assert await offsets_of(env) == ",".join(str(m) for m in minutes)
    fake_callback.message.edit_text.assert_awaited_once_with(texts.offsets_saved(label))
    fake_callback.answer.assert_awaited_once_with()


async def test_choose_offsets_message_says_only_new_tasks_are_affected(env, fake_callback):
    fake_callback.data = "off:h1"
    await settings.choose_offsets(fake_callback)
    text = fake_callback.message.edit_text.await_args.args[0]
    assert "только новых задач" in text


@pytest.mark.parametrize("data", ["off:nope", "off:", "off", "off:D1H1"])
async def test_choose_offsets_unknown_key(env, fake_callback, data):
    await database.get_or_create_user(env, 1)
    fake_callback.data = data
    await settings.choose_offsets(fake_callback)
    fake_callback.answer.assert_awaited_once_with(texts.BAD_BUTTON, show_alert=True)
    fake_callback.message.edit_text.assert_not_awaited()
    assert await offsets_of(env) == "1440,60"


async def test_choose_offsets_does_not_touch_existing_reminders(env, fake_callback):
    await database.get_or_create_user(env, 1)
    deadline = NOW + timedelta(days=3)
    await database.add_task(env, 1, "Лаба", deadline, [deadline - timedelta(days=1)])
    before = sql(env, "SELECT remind_at, sent FROM reminders")
    fake_callback.data = "off:h1"
    await settings.choose_offsets(fake_callback)
    assert sql(env, "SELECT remind_at, sent FROM reminders") == before


async def test_choose_offsets_creates_missing_user(env, fake_callback):
    fake_callback.data = "off:d1"
    await settings.choose_offsets(fake_callback)
    assert await offsets_of(env) == "1440"


async def test_choose_offsets_survives_edit_error(env, fake_callback):
    fake_callback.data = "off:d1"
    fake_callback.message.edit_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="message to edit not found"
    )
    await settings.choose_offsets(fake_callback)
    assert await offsets_of(env) == "1440"
    fake_callback.answer.assert_awaited_once_with()