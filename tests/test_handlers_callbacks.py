import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest

import database
import keyboards
import texts
from handlers import callbacks, tasks

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def sql(path, query, params=()):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(query, params).fetchall()


@pytest.fixture
async def env(db_path):
    await database.init_db(db_path)
    return db_path


async def make_task(path, user_id=1, title="Лаба", reminders=()):
    await database.get_or_create_user(path, user_id)
    return await database.add_task(
        path, user_id, title, NOW + timedelta(days=3), list(reminders)
    )


def warnings(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def assert_not_found_alert(callback, caplog, user_id, task_id):
    callback.answer.assert_awaited_once_with(texts.TASK_NOT_FOUND, show_alert=True)
    callback.message.edit_text.assert_not_awaited()
    assert any(
        f"user_id={user_id}" in w and f"task_id={task_id}" in w for w in warnings(caplog)
    )


# ---------- parse_task_id ----------

@pytest.mark.parametrize("data, expected", [
    ("del:12", 12),
    ("delyes:7", 7),
    ("delno:0", 0),
    ("done:1000000000000", 1_000_000_000_000),
    ("del:abc", None),
    ("del:", None),
    ("del", None),
    ("", None),
    ("del:1:2", None),
    ("del:1.5", None),
])
def test_parse_task_id(data, expected):
    assert callbacks.parse_task_id(data) == expected


# ---------- del:<id> ----------

async def test_ask_delete_shows_confirmation(env, fake_callback):
    task_id = await make_task(env, title="Сдать лабу")
    fake_callback.data = f"del:{task_id}"
    await callbacks.ask_delete(fake_callback)
    fake_callback.message.edit_text.assert_awaited_once_with(
        texts.delete_confirm("Сдать лабу"),
        reply_markup=keyboards.delete_confirm_keyboard(task_id),
    )
    fake_callback.answer.assert_awaited_once_with()
    assert await database.get_task(env, task_id, 1) is not None


async def test_ask_delete_escapes_title(env, fake_callback):
    task_id = await make_task(env, title="<b>x</b>")
    fake_callback.data = f"del:{task_id}"
    await callbacks.ask_delete(fake_callback)
    text = fake_callback.message.edit_text.await_args.args[0]
    assert "&lt;b&gt;x&lt;/b&gt;" in text


@pytest.mark.parametrize("data", ["del:abc", "del:", "del"])
async def test_ask_delete_bad_id(env, fake_callback, data):
    fake_callback.data = data
    await callbacks.ask_delete(fake_callback)
    fake_callback.answer.assert_awaited_once_with(texts.BAD_BUTTON, show_alert=True)
    fake_callback.message.edit_text.assert_not_awaited()


async def test_ask_delete_missing_task(env, fake_callback, caplog):
    await database.get_or_create_user(env, 1)
    fake_callback.data = "del:999"
    with caplog.at_level(logging.WARNING):
        await callbacks.ask_delete(fake_callback)
    assert_not_found_alert(fake_callback, caplog, 1, 999)


async def test_ask_delete_foreign_task_same_answer_and_untouched(env, fake_callback, caplog):
    foreign = await make_task(env, user_id=2, title="чужая")
    await database.get_or_create_user(env, 1)
    fake_callback.data = f"del:{foreign}"
    with caplog.at_level(logging.WARNING):
        await callbacks.ask_delete(fake_callback)
    assert_not_found_alert(fake_callback, caplog, 1, foreign)
    assert (await database.get_task(env, foreign, 2))["title"] == "чужая"


async def test_ask_delete_survives_edit_error(env, fake_callback):
    task_id = await make_task(env)
    fake_callback.data = f"del:{task_id}"
    fake_callback.message.edit_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="message is not modified"
    )
    await callbacks.ask_delete(fake_callback)
    fake_callback.answer.assert_awaited_once_with()


# ---------- delyes:<id> ----------

async def test_confirm_delete_removes_task_and_reminders(env, fake_callback):
    task_id = await make_task(env, reminders=[NOW + timedelta(days=1)])
    fake_callback.data = f"delyes:{task_id}"
    await callbacks.confirm_delete(fake_callback)
    assert await database.get_task(env, task_id, 1) is None
    assert sql(env, "SELECT COUNT(*) FROM reminders") == [(0,)]
    fake_callback.message.edit_text.assert_awaited_once_with(texts.DELETE_DONE)
    fake_callback.answer.assert_awaited_once_with()


async def test_confirm_delete_keeps_other_tasks(env, fake_callback):
    first = await make_task(env, title="первая")
    second = await make_task(env, title="вторая")
    fake_callback.data = f"delyes:{first}"
    await callbacks.confirm_delete(fake_callback)
    assert await database.get_task(env, second, 1) is not None


async def test_confirm_delete_bad_id(env, fake_callback):
    fake_callback.data = "delyes:x"
    await callbacks.confirm_delete(fake_callback)
    fake_callback.answer.assert_awaited_once_with(texts.BAD_BUTTON, show_alert=True)


async def test_confirm_delete_missing_task(env, fake_callback, caplog):
    await database.get_or_create_user(env, 1)
    fake_callback.data = "delyes:999"
    with caplog.at_level(logging.WARNING):
        await callbacks.confirm_delete(fake_callback)
    assert_not_found_alert(fake_callback, caplog, 1, 999)


async def test_confirm_delete_foreign_task_is_not_deleted(env, fake_callback, caplog):
    foreign = await make_task(env, user_id=2, title="чужая", reminders=[NOW + timedelta(days=1)])
    await database.get_or_create_user(env, 1)
    fake_callback.data = f"delyes:{foreign}"
    with caplog.at_level(logging.WARNING):
        await callbacks.confirm_delete(fake_callback)
    assert_not_found_alert(fake_callback, caplog, 1, foreign)
    assert await database.get_task(env, foreign, 2) is not None
    assert sql(env, "SELECT COUNT(*) FROM reminders") == [(1,)]


async def test_confirm_delete_second_press_reports_not_found(env, fake_callback, caplog):
    task_id = await make_task(env)
    fake_callback.data = f"delyes:{task_id}"
    await callbacks.confirm_delete(fake_callback)
    fake_callback.answer.reset_mock()
    fake_callback.message.edit_text.reset_mock()
    with caplog.at_level(logging.WARNING):
        await callbacks.confirm_delete(fake_callback)
    assert_not_found_alert(fake_callback, caplog, 1, task_id)


async def test_confirm_delete_survives_edit_error(env, fake_callback):
    task_id = await make_task(env)
    fake_callback.data = f"delyes:{task_id}"
    fake_callback.message.edit_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="message to edit not found"
    )
    await callbacks.confirm_delete(fake_callback)
    assert await database.get_task(env, task_id, 1) is None
    fake_callback.answer.assert_awaited_once_with()


# ---------- delno:<id> ----------

async def test_cancel_delete_keeps_task(env, fake_callback):
    task_id = await make_task(env)
    fake_callback.data = f"delno:{task_id}"
    await callbacks.cancel_delete(fake_callback)
    fake_callback.message.edit_text.assert_awaited_once_with(texts.DELETE_KEPT)
    fake_callback.answer.assert_awaited_once_with()
    assert await database.get_task(env, task_id, 1) is not None


async def test_cancel_delete_bad_id(env, fake_callback):
    fake_callback.data = "delno:"
    await callbacks.cancel_delete(fake_callback)
    fake_callback.answer.assert_awaited_once_with(texts.BAD_BUTTON, show_alert=True)


async def test_cancel_delete_missing_and_foreign(env, fake_callback, caplog):
    foreign = await make_task(env, user_id=2)
    await database.get_or_create_user(env, 1)
    for task_id in (999, foreign):
        fake_callback.reset_mock()
        fake_callback.data = f"delno:{task_id}"
        with caplog.at_level(logging.WARNING):
            await callbacks.cancel_delete(fake_callback)
        assert_not_found_alert(fake_callback, caplog, 1, task_id)


# ---------- сценарий /list -> удаление ----------

async def test_list_to_delete_flow(env, fake_message, fake_callback, monkeypatch):
    monkeypatch.setattr(tasks, "_now_utc", lambda: NOW)
    keep = await make_task(env, title="оставить")
    drop = await make_task(env, title="удалить")
    await tasks.cmd_delete(fake_message)
    rows = fake_message.answer.await_args.kwargs["reply_markup"].inline_keyboard
    assert [r[0].callback_data for r in rows] == [f"del:{keep}", f"del:{drop}"]

    fake_callback.data = rows[1][0].callback_data
    await callbacks.ask_delete(fake_callback)
    fake_callback.data = f"delyes:{drop}"
    await callbacks.confirm_delete(fake_callback)

    left = await database.get_active_tasks(env, 1)
    assert [t["title"] for t in left] == ["оставить"]