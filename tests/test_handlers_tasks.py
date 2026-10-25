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
from handlers import tasks
from states import AddTask

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
DEADLINE_ISO = "2026-10-28T20:59:00+00:00"

def sql(path, query, params=()):
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute(query, params).fetchall()
        conn.commit()
    return rows


@pytest.fixture
async def env(db_path, monkeypatch):
    await database.init_db(db_path)
    monkeypatch.setattr(tasks, "_now_utc", lambda: NOW)
    return db_path


async def to_state(fsm, state, **data):
    await fsm.set_state(state)
    if data:
        await fsm.update_data(**data)


def answered(message):
    return message.answer.await_args.args[0]


# ---------- вспомогательные функции ----------

def test_now_utc_is_aware_and_current():
    before = datetime.now(timezone.utc)
    value = tasks._now_utc()
    after = datetime.now(timezone.utc)
    assert value.utcoffset() == timedelta(0)
    assert before <= value <= after


@pytest.mark.parametrize("text, raw_state, expected", [
    ("/add", "AddTask:waiting_title", True),
    ("/help extra", "AddTask:waiting_deadline", True),
    ("привет", "AddTask:waiting_title", False),
    ("/add", None, False),
    (None, "AddTask:waiting_title", False),
    (None, None, False),
])
def test_is_command_in_dialog(fake_message, text, raw_state, expected):
    fake_message.text = text
    assert tasks.is_command_in_dialog(fake_message, raw_state) is expected


def test_reminder_plan_all_in_future():
    deadline = NOW + timedelta(days=3)
    assert tasks._reminder_plan(deadline, (1440, 60), NOW) == ([1440, 60], [])


def test_reminder_plan_some_skipped():
    deadline = NOW + timedelta(hours=5)
    assert tasks._reminder_plan(deadline, (1440, 60), NOW) == ([60], [1440])


def test_reminder_plan_all_skipped():
    deadline = NOW + timedelta(minutes=30)
    assert tasks._reminder_plan(deadline, (1440, 60), NOW) == ([], [1440, 60])


async def test_edit_text_edits_message(fake_callback):
    await tasks.edit_text(fake_callback, "текст")
    fake_callback.message.edit_text.assert_awaited_once_with("текст")


async def test_edit_text_passes_reply_markup(fake_callback):
    markup = keyboards.confirm_keyboard()
    await tasks.edit_text(fake_callback, "текст", reply_markup=markup)
    fake_callback.message.edit_text.assert_awaited_once_with("текст", reply_markup=markup)


async def test_edit_text_swallows_bad_request(fake_callback):
    fake_callback.message.edit_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="message is not modified"
    )
    await tasks.edit_text(fake_callback, "текст")
    fake_callback.message.edit_text.assert_awaited_once()

# ---------- /cancel и команды в диалоге ----------

async def test_cancel_without_dialog(fake_message, fsm):
    await tasks.cmd_cancel(fake_message, fsm)
    fake_message.answer.assert_awaited_once_with(texts.NOTHING_TO_CANCEL)
    assert await fsm.get_state() is None


async def test_cancel_clears_state_and_data(fake_message, fsm):
    await to_state(fsm, AddTask.waiting_deadline, title="Лаба")
    await tasks.cmd_cancel(fake_message, fsm)
    fake_message.answer.assert_awaited_once_with(texts.CANCELLED)
    assert await fsm.get_state() is None
    assert await fsm.get_data() == {}


async def test_command_in_dialog_asks_to_finish(fake_message):
    await tasks.command_in_dialog(fake_message)
    fake_message.answer.assert_awaited_once_with(texts.FINISH_DIALOG)


# ---------- /add ----------

async def test_cmd_add_starts_dialog_and_creates_user(env, fake_message, fsm):
    await fsm.update_data(junk="старое")
    await tasks.cmd_add(fake_message, fsm)
    assert await fsm.get_state() == AddTask.waiting_title.state
    assert await fsm.get_data() == {}
    fake_message.answer.assert_awaited_once_with(texts.ADD_ASK_TITLE)
    assert sql(env, "SELECT id FROM users") == [(1,)]


async def test_cmd_add_blocked_by_limit(env, fake_message, fsm, monkeypatch):
    monkeypatch.setattr(config, "MAX_ACTIVE_TASKS", 2)
    await database.get_or_create_user(env, 1)
    for i in range(2):
        await database.add_task(env, 1, f"t{i}", NOW + timedelta(days=5), [])
    await tasks.cmd_add(fake_message, fsm)
    fake_message.answer.assert_awaited_once_with(texts.ADD_LIMIT_REACHED.format(limit=2))
    assert await fsm.get_state() is None


async def test_cmd_add_limit_counts_only_active(env, fake_message, fsm, monkeypatch):
    monkeypatch.setattr(config, "MAX_ACTIVE_TASKS", 1)
    await database.get_or_create_user(env, 1)
    task_id = await database.add_task(env, 1, "t", NOW + timedelta(days=5), [])
    await database.mark_task_done(env, task_id, 1, NOW)
    await tasks.cmd_add(fake_message, fsm)
    assert await fsm.get_state() == AddTask.waiting_title.state


# ---------- название ----------

async def test_process_title_saves_stripped_title(fake_message, fsm):
    await to_state(fsm, AddTask.waiting_title)
    fake_message.text = "  Сдать лабу  "
    await tasks.process_title(fake_message, fsm)
    assert (await fsm.get_data())["title"] == "Сдать лабу"
    assert await fsm.get_state() == AddTask.waiting_deadline.state
    fake_message.answer.assert_awaited_once_with(texts.ADD_ASK_DEADLINE)


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
async def test_process_title_rejects_empty(fake_message, fsm, text):
    await to_state(fsm, AddTask.waiting_title)
    fake_message.text = text
    await tasks.process_title(fake_message, fsm)
    fake_message.answer.assert_awaited_once_with(texts.ADD_TITLE_EMPTY)
    assert await fsm.get_state() == AddTask.waiting_title.state
    assert await fsm.get_data() == {}


async def test_process_title_rejects_too_long(fake_message, fsm):
    await to_state(fsm, AddTask.waiting_title)
    fake_message.text = "я" * (config.MAX_TITLE_LENGTH + 1)
    await tasks.process_title(fake_message, fsm)
    expected = texts.ADD_TITLE_TOO_LONG.format(limit=config.MAX_TITLE_LENGTH)
    fake_message.answer.assert_awaited_once_with(expected)
    assert await fsm.get_state() == AddTask.waiting_title.state


async def test_process_title_accepts_max_length(fake_message, fsm):
    await to_state(fsm, AddTask.waiting_title)
    fake_message.text = "я" * config.MAX_TITLE_LENGTH
    await tasks.process_title(fake_message, fsm)
    assert await fsm.get_state() == AddTask.waiting_deadline.state


# ---------- дедлайн ----------

async def test_process_deadline_shows_summary(env, fake_message, fsm):
    await to_state(fsm, AddTask.waiting_deadline, title="Лаба")
    fake_message.text = "28.10 23:59"
    await tasks.process_deadline(fake_message, fsm)

    expected = texts.add_summary(
        "Лаба", "28.10 в 23:59", "через 5 дн. 8 ч.", ["за 1 день", "за 1 час"], []
    )
    assert answered(fake_message) == expected
    markup = fake_message.answer.await_args.kwargs["reply_markup"]
    assert markup == keyboards.confirm_keyboard()
    assert await fsm.get_state() == AddTask.waiting_confirm.state
    assert (await fsm.get_data())["deadline"] == DEADLINE_ISO


async def test_process_deadline_escapes_title_in_summary(env, fake_message, fsm):
    await to_state(fsm, AddTask.waiting_deadline, title="<b>x</b> & y")
    fake_message.text = "28.10 23:59"
    await tasks.process_deadline(fake_message, fsm)
    text = answered(fake_message)
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in text
    assert (await fsm.get_data())["title"] == "<b>x</b> & y"


@pytest.mark.parametrize("text, reason", [
    ("abc", texts.ERR_DT_FORMAT),
    ("31.02 10:00", texts.ERR_DT_DATE),
    ("22.10.2026 10:00", texts.ERR_DT_PAST),
    ("01.01.2030 10:00", texts.ERR_DT_FAR),
])
async def test_process_deadline_reports_reason(env, fake_message, fsm, text, reason):
    await to_state(fsm, AddTask.waiting_deadline, title="Лаба")
    fake_message.text = text
    await tasks.process_deadline(fake_message, fsm)
    fake_message.answer.assert_awaited_once_with(reason)
    assert await fsm.get_state() == AddTask.waiting_deadline.state
    assert "deadline" not in await fsm.get_data()


async def test_process_deadline_skips_past_reminders(env, fake_message, fsm):
    await to_state(fsm, AddTask.waiting_deadline, title="Лаба")
    fake_message.text = "23.10 17:30"  # через 2 ч. 30 мин.
    await tasks.process_deadline(fake_message, fsm)
    expected = texts.add_summary(
        "Лаба", "23.10 в 17:30", "через 2 ч. 30 мин.", ["за 1 час"], ["за 1 день"]
    )
    assert answered(fake_message) == expected
    assert await fsm.get_state() == AddTask.waiting_confirm.state


async def test_process_deadline_without_any_reminders_still_allows_save(
    env, fake_message, fsm
):
    await to_state(fsm, AddTask.waiting_deadline, title="Лаба")
    fake_message.text = "23.10 15:30"  # через 30 минут
    await tasks.process_deadline(fake_message, fsm)
    text = answered(fake_message)
    assert texts.ADD_NO_REMINDERS in text
    assert "за 1 день, за 1 час" in text
    assert await fsm.get_state() == AddTask.waiting_confirm.state


async def test_process_deadline_uses_user_timezone_and_offsets(env, fake_message, fsm):
    await database.get_or_create_user(env, 1)
    await database.update_user_timezone(env, 1, "Asia/Novosibirsk")
    await database.update_user_offsets(env, 1, (4320, 1440, 60))
    await to_state(fsm, AddTask.waiting_deadline, title="Лаба")
    fake_message.text = "28.10 23:59"
    await tasks.process_deadline(fake_message, fsm)
    expected = texts.add_summary(
        "Лаба", "28.10 в 23:59", "через 5 дн. 4 ч.",
        ["за 3 дня", "за 1 день", "за 1 час"], [],
    )
    assert answered(fake_message) == expected
    assert (await fsm.get_data())["deadline"] == "2026-10-28T16:59:00+00:00"


# ---------- не текст и текст на шаге подтверждения ----------

async def test_expect_text_for_non_text_message(fake_message):
    fake_message.text = None
    await tasks.expect_text(fake_message)
    fake_message.answer.assert_awaited_once_with(texts.TEXT_ONLY)


async def test_expect_button_keeps_state(fake_message, fsm):
    await to_state(fsm, AddTask.waiting_confirm, title="Лаба", deadline=DEADLINE_ISO)
    await tasks.expect_button(fake_message)
    fake_message.answer.assert_awaited_once_with(texts.ADD_CONFIRM_WAIT)
    assert await fsm.get_state() == AddTask.waiting_confirm.state


# ---------- add_save ----------

async def confirm_state(fsm, title="Лаба", deadline=DEADLINE_ISO):
    await to_state(fsm, AddTask.waiting_confirm, title=title, deadline=deadline)


async def test_add_save_creates_task_and_reminders(env, fake_callback, fsm):
    await confirm_state(fsm)
    await tasks.add_save(fake_callback, fsm)

    saved = await database.get_active_tasks(env, 1)
    assert [t["title"] for t in saved] == ["Лаба"]
    assert saved[0]["deadline"] == datetime(2026, 10, 28, 20, 59, tzinfo=timezone.utc)
    rows = sql(env, "SELECT remind_at, sent FROM reminders ORDER BY remind_at")
    assert rows == [("2026-10-27T20:59:00+00:00", 0), ("2026-10-28T19:59:00+00:00", 0)]
    assert await fsm.get_state() is None
    fake_callback.message.edit_text.assert_awaited_once_with(
        texts.add_saved(["за 1 день", "за 1 час"])
    )
    fake_callback.answer.assert_awaited_once_with()


async def test_add_save_recalculates_reminders_with_current_time(
    env, fake_callback, fsm, monkeypatch
):
    later = datetime(2026, 10, 27, 22, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(tasks, "_now_utc", lambda: later)
    await confirm_state(fsm)
    await tasks.add_save(fake_callback, fsm)
    assert sql(env, "SELECT remind_at FROM reminders") == [("2026-10-28T19:59:00+00:00",)]
    fake_callback.message.edit_text.assert_awaited_once_with(texts.add_saved(["за 1 час"]))


async def test_add_save_with_no_reminders_left(env, fake_callback, fsm, monkeypatch):
    later = datetime(2026, 10, 28, 20, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(tasks, "_now_utc", lambda: later)
    await confirm_state(fsm)
    await tasks.add_save(fake_callback, fsm)
    assert sql(env, "SELECT COUNT(*) FROM reminders") == [(0,)]
    assert len(await database.get_active_tasks(env, 1)) == 1
    fake_callback.message.edit_text.assert_awaited_once_with(texts.add_saved([]))


async def test_add_save_deadline_passed_while_thinking(
    env, fake_callback, fsm, monkeypatch
):
    later = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(tasks, "_now_utc", lambda: later)
    await confirm_state(fsm)
    await tasks.add_save(fake_callback, fsm)
    fake_callback.message.edit_text.assert_awaited_once_with(texts.ADD_DEADLINE_PASSED)
    assert await database.get_active_tasks(env, 1) == []
    assert await fsm.get_state() is None
    fake_callback.answer.assert_awaited_once_with()


async def test_add_save_rechecks_limit(env, fake_callback, fsm, monkeypatch):
    monkeypatch.setattr(config, "MAX_ACTIVE_TASKS", 1)
    await database.get_or_create_user(env, 1)
    await database.add_task(env, 1, "уже есть", NOW + timedelta(days=9), [])
    await confirm_state(fsm)
    await tasks.add_save(fake_callback, fsm)
    fake_callback.message.edit_text.assert_awaited_once_with(
        texts.ADD_LIMIT_REACHED.format(limit=1)
    )
    assert len(await database.get_active_tasks(env, 1)) == 1
    assert await fsm.get_state() is None


async def test_add_save_outdated_button_without_state(env, fake_callback, fsm):
    await tasks.add_save(fake_callback, fsm)
    fake_callback.answer.assert_awaited_once_with(texts.BUTTON_OUTDATED, show_alert=True)
    fake_callback.message.edit_text.assert_not_awaited()
    assert sql(env, "SELECT COUNT(*) FROM tasks") == [(0,)]


async def test_add_save_button_pressed_in_other_step(env, fake_callback, fsm):
    await to_state(fsm, AddTask.waiting_title)
    await tasks.add_save(fake_callback, fsm)
    fake_callback.answer.assert_awaited_once_with(texts.BUTTON_OUTDATED, show_alert=True)
    assert await fsm.get_state() == AddTask.waiting_title.state
    assert sql(env, "SELECT COUNT(*) FROM tasks") == [(0,)]


async def test_add_save_survives_edit_error(env, fake_callback, fsm):
    fake_callback.message.edit_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="message to edit not found"
    )
    await confirm_state(fsm)
    await tasks.add_save(fake_callback, fsm)
    assert len(await database.get_active_tasks(env, 1)) == 1
    fake_callback.answer.assert_awaited_once_with()


# ---------- add_cancel ----------

async def test_add_cancel_clears_state(env, fake_callback, fsm):
    await confirm_state(fsm)
    await tasks.add_cancel(fake_callback, fsm)
    fake_callback.message.edit_text.assert_awaited_once_with(texts.CANCELLED)
    fake_callback.answer.assert_awaited_once_with()
    assert await fsm.get_state() is None
    assert await fsm.get_data() == {}
    assert sql(env, "SELECT COUNT(*) FROM tasks") == [(0,)]


async def test_add_cancel_outdated_button(fake_callback, fsm):
    await to_state(fsm, AddTask.waiting_title)
    await tasks.add_cancel(fake_callback, fsm)
    fake_callback.answer.assert_awaited_once_with(texts.BUTTON_OUTDATED, show_alert=True)
    assert await fsm.get_state() == AddTask.waiting_title.state


# ---------- сценарий целиком ----------

async def test_full_add_flow(env, fake_message, fake_callback, fsm):
    await tasks.cmd_add(fake_message, fsm)
    fake_message.text = "Сдать лабу"
    await tasks.process_title(fake_message, fsm)
    fake_message.text = "28.10 23:59"
    await tasks.process_deadline(fake_message, fsm)
    await tasks.add_save(fake_callback, fsm)

    saved = await database.get_active_tasks(env, 1)
    assert [(t["title"], t["deadline"]) for t in saved] == [
        ("Сдать лабу", datetime(2026, 10, 28, 20, 59, tzinfo=timezone.utc))
    ]
    assert await fsm.get_state() is None
    due = await database.get_due_reminders(env, datetime(2026, 10, 28, 20, 0, tzinfo=timezone.utc))
    assert len(due) == 2


# ---------- /list и /delete ----------

async def add_tasks(path, user_id, titles, start_hours=24):
    await database.get_or_create_user(path, user_id)
    ids = []
    for i, title in enumerate(titles):
        deadline = NOW + timedelta(hours=start_hours + i)
        ids.append(await database.add_task(path, user_id, title, deadline, []))
    return ids


async def test_list_empty(env, fake_message):
    await tasks.cmd_list(fake_message)
    fake_message.answer.assert_awaited_once_with(texts.LIST_EMPTY)
    assert sql(env, "SELECT id FROM users") == [(1,)]


async def test_list_shows_tasks_with_keyboard(env, fake_message):
    await add_tasks(env, 1, ["Лаба", "Курсовая"], start_hours=30)
    await tasks.cmd_list(fake_message)

    expected = texts.task_list(
        [
            ("Лаба", "24.10 в 21:00", "через 1 дн. 6 ч."),
            ("Курсовая", "24.10 в 22:00", "через 1 дн. 7 ч."),
        ],
        0,
    )
    assert answered(fake_message) == expected
    saved = await database.get_active_tasks(env, 1)
    markup = fake_message.answer.await_args.kwargs["reply_markup"]
    assert markup == keyboards.tasks_keyboard(saved)


async def test_list_shows_only_own_active_tasks(env, fake_message):
    mine = await add_tasks(env, 1, ["моя", "сделанная", "просроченная"])
    await add_tasks(env, 2, ["чужая"])
    await database.mark_task_done(env, mine[1], 1, NOW)
    sql(env, "UPDATE tasks SET status = 'expired' WHERE id = ?", (mine[2],))
    await tasks.cmd_list(fake_message)
    text = answered(fake_message)
    assert "моя" in text
    assert "чужая" not in text and "сделанная" not in text and "просроченная" not in text


async def test_list_more_than_page_size(env, fake_message):
    titles = [f"t{i:02d}" for i in range(12)]
    await add_tasks(env, 1, titles)
    await tasks.cmd_list(fake_message)
    text = answered(fake_message)
    assert "t09" in text and "t10" not in text
    assert text.endswith(texts.LIST_MORE.format(count=2))
    markup = fake_message.answer.await_args.kwargs["reply_markup"]
    assert len(markup.inline_keyboard) == config.LIST_PAGE_SIZE


async def test_list_exactly_page_size_has_no_more_line(env, fake_message):
    await add_tasks(env, 1, [f"t{i}" for i in range(config.LIST_PAGE_SIZE)])
    await tasks.cmd_list(fake_message)
    assert "…и ещё" not in answered(fake_message)


async def test_list_escapes_title(env, fake_message):
    await add_tasks(env, 1, ["<b>x</b> & y"])
    await tasks.cmd_list(fake_message)
    text = answered(fake_message)
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in text
    assert "<b>x</b>" not in text


async def test_list_uses_user_timezone(env, fake_message):
    await add_tasks(env, 1, ["Лаба"], start_hours=30)
    await database.update_user_timezone(env, 1, "Asia/Novosibirsk")
    await tasks.cmd_list(fake_message)
    assert "25.10 в 01:00" in answered(fake_message)


async def test_list_buttons_numbers_match_list(env, fake_message):
    ids = await add_tasks(env, 1, ["a", "b", "c"])
    await tasks.cmd_list(fake_message)
    rows = fake_message.answer.await_args.kwargs["reply_markup"].inline_keyboard
    assert [row[1].text for row in rows] == ["🗑 №1", "🗑 №2", "🗑 №3"]
    assert [row[1].callback_data for row in rows] == [f"del:{i}" for i in ids]


async def test_delete_empty(env, fake_message):
    await tasks.cmd_delete(fake_message)
    fake_message.answer.assert_awaited_once_with(texts.LIST_EMPTY)


async def test_delete_shows_list_with_delete_buttons_only(env, fake_message):
    ids = await add_tasks(env, 1, ["Лаба", "Курсовая"])
    await tasks.cmd_delete(fake_message)
    text = answered(fake_message)
    assert text.startswith(texts.DELETE_PROMPT)
    assert "1. <b>Лаба</b>" in text and "2. <b>Курсовая</b>" in text
    rows = fake_message.answer.await_args.kwargs["reply_markup"].inline_keyboard
    assert [[b.callback_data for b in row] for row in rows] == [[f"del:{i}"] for i in ids]


async def test_delete_limits_to_page_size(env, fake_message):
    await add_tasks(env, 1, [f"t{i:02d}" for i in range(12)])
    await tasks.cmd_delete(fake_message)
    assert answered(fake_message).endswith(texts.LIST_MORE.format(count=2))
    rows = fake_message.answer.await_args.kwargs["reply_markup"].inline_keyboard
    assert len(rows) == config.LIST_PAGE_SIZE