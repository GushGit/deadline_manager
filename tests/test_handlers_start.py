import sqlite3
from contextlib import closing
from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest

import config
import database
import keyboards
import texts
from handlers import start
from states import SetTimezone


def sql(path, query, params=()):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(query, params).fetchall()


@pytest.fixture
async def env(db_path):
    await database.init_db(db_path)
    return db_path


async def timezone_of(path, user_id=1):
    return (await database.get_or_create_user(path, user_id))["timezone"]


# ---------- /start и /help ----------

async def test_cmd_start_creates_user_and_shows_timezone_keyboard(env, fake_message):
    await start.cmd_start(fake_message)
    fake_message.answer.assert_awaited_once_with(
        texts.START, reply_markup=keyboards.timezone_keyboard()
    )
    assert sql(env, "SELECT id, timezone FROM users") == [(1, config.DEFAULT_TIMEZONE)]


async def test_cmd_start_twice_does_not_duplicate_or_reset_timezone(env, fake_message):
    await start.cmd_start(fake_message)
    await database.update_user_timezone(env, 1, "Asia/Novosibirsk")
    await start.cmd_start(fake_message)
    assert sql(env, "SELECT COUNT(*) FROM users") == [(1,)]
    assert await timezone_of(env) == "Asia/Novosibirsk"


async def test_cmd_help_lists_all_commands(fake_message):
    await start.cmd_help(fake_message)
    fake_message.answer.assert_awaited_once()
    text = fake_message.answer.await_args.args[0]
    for command in ("/start", "/help", "/add", "/list", "/delete",
                    "/cancel", "/today", "/week", "/settings"):
        assert command in text


# ---------- _is_valid_timezone ----------

@pytest.mark.parametrize("name", ["Europe/Berlin", "Asia/Novosibirsk", "UTC", "America/New_York"])
def test_is_valid_timezone_accepts_real_names(name):
    assert start._is_valid_timezone(name) is True


@pytest.mark.parametrize("name", [
    "", "Mars/Phobos", "Europe", "Berlin", "../etc/passwd", "/etc/passwd", "Europe/Berlin\x00",
])
def test_is_valid_timezone_rejects_bad_names(name):
    assert start._is_valid_timezone(name) is False


# ---------- tz:<IANA> ----------

@pytest.mark.parametrize("iana", list(config.POPULAR_TIMEZONES.values()))
async def test_choose_timezone_saves_every_popular_zone(env, fake_callback, iana):
    fake_callback.data = f"tz:{iana}"
    await start.choose_timezone(fake_callback)
    assert await timezone_of(env) == iana
    fake_callback.message.edit_text.assert_awaited_once_with(texts.timezone_saved(iana))
    fake_callback.answer.assert_awaited_once_with()


async def test_choose_timezone_creates_missing_user(env, fake_callback):
    fake_callback.data = "tz:Asia/Omsk"
    await start.choose_timezone(fake_callback)
    assert sql(env, "SELECT id, timezone FROM users") == [(1, "Asia/Omsk")]


@pytest.mark.parametrize("data", ["tz:", "tz:Mars/Phobos", "tz:Europe", "tz:../x", "tz"])
async def test_choose_timezone_rejects_bad_data(env, fake_callback, data):
    await database.get_or_create_user(env, 1)
    fake_callback.data = data
    await start.choose_timezone(fake_callback)
    fake_callback.answer.assert_awaited_once_with(texts.BAD_BUTTON, show_alert=True)
    fake_callback.message.edit_text.assert_not_awaited()
    assert await timezone_of(env) == config.DEFAULT_TIMEZONE


async def test_choose_timezone_survives_edit_error(env, fake_callback):
    fake_callback.data = "tz:Asia/Omsk"
    fake_callback.message.edit_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="message is not modified"
    )
    await start.choose_timezone(fake_callback)
    assert await timezone_of(env) == "Asia/Omsk"
    fake_callback.answer.assert_awaited_once_with()


# ---------- tz_other и ввод текстом ----------

async def test_ask_timezone_sets_state(fake_callback, fsm):
    fake_callback.data = "tz_other"
    await start.ask_timezone(fake_callback, fsm)
    assert await fsm.get_state() == SetTimezone.waiting_timezone.state
    fake_callback.message.edit_text.assert_awaited_once_with(texts.ASK_TIMEZONE)
    fake_callback.answer.assert_awaited_once_with()


async def test_process_timezone_valid_name_saves_and_clears_state(env, fake_message, fsm):
    await fsm.set_state(SetTimezone.waiting_timezone)
    fake_message.text = "  Europe/Berlin  "
    await start.process_timezone(fake_message, fsm)
    assert await timezone_of(env) == "Europe/Berlin"
    assert await fsm.get_state() is None
    fake_message.answer.assert_awaited_once_with(texts.timezone_saved("Europe/Berlin"))


@pytest.mark.parametrize("text", ["Mars/Phobos", "Europe", "берлин", "../x"])
async def test_process_timezone_invalid_name_keeps_state(env, fake_message, fsm, text):
    await database.get_or_create_user(env, 1)
    await fsm.set_state(SetTimezone.waiting_timezone)
    fake_message.text = text
    await start.process_timezone(fake_message, fsm)
    fake_message.answer.assert_awaited_once_with(texts.TIMEZONE_INVALID)
    assert await fsm.get_state() == SetTimezone.waiting_timezone.state
    assert await timezone_of(env) == config.DEFAULT_TIMEZONE


async def test_process_timezone_retry_after_error(env, fake_message, fsm):
    await fsm.set_state(SetTimezone.waiting_timezone)
    fake_message.text = "Nowhere/City"
    await start.process_timezone(fake_message, fsm)
    fake_message.text = "Asia/Omsk"
    await start.process_timezone(fake_message, fsm)
    assert await timezone_of(env) == "Asia/Omsk"
    assert await fsm.get_state() is None


async def test_expect_timezone_text_for_non_text_message(fake_message, fsm):
    fake_message.text = None
    await start.expect_timezone_text(fake_message)
    fake_message.answer.assert_awaited_once_with(texts.TEXT_ONLY)