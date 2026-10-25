import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

import database

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def hours(n: int) -> datetime:
    return NOW + timedelta(hours=n)


def sql(path: str, query: str, params: tuple = ()) -> list:
    """Прямой запрос к БД для проверки результата и подготовки данных."""
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute(query, params).fetchall()
        conn.commit()
    return rows


def fetch_row(query: str) -> sqlite3.Row:
    """Одна строка из временной in-memory БД (для проверки конвертеров)."""
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(query).fetchone()


async def make_task(path, user_id=1, title="Лаба", deadline=None, reminders=()):
    await database.get_or_create_user(path, user_id)
    return await database.add_task(
        path, user_id, title, deadline or hours(48), list(reminders)
    )


@pytest.fixture
async def db(db_path):
    await database.init_db(db_path)
    return db_path


# ---------- служебные функции ----------

def test_to_str_converts_to_utc():
    msk = timezone(timedelta(hours=3))
    dt = datetime(2026, 10, 28, 23, 59, tzinfo=msk)
    assert database._to_str(dt) == "2026-10-28T20:59:00+00:00"


def test_to_str_drops_microseconds():
    assert database._to_str(NOW.replace(microsecond=500)) == "2026-10-23T12:00:00+00:00"


def test_to_str_rejects_naive():
    with pytest.raises(ValueError):
        database._to_str(datetime(2026, 10, 28, 23, 59))


def test_from_str_returns_aware_utc():
    dt = database._from_str("2026-10-28T20:59:00+00:00")
    assert dt == datetime(2026, 10, 28, 20, 59, tzinfo=timezone.utc)
    assert dt.utcoffset() == timedelta(0)


def test_user_to_dict_parses_created_at():
    row = fetch_row("SELECT 5 AS id, '2026-10-23T12:00:00+00:00' AS created_at")
    user = database._user_to_dict(row)
    assert user == {"id": 5, "created_at": NOW}


def test_task_to_dict_parses_dates_and_keeps_none():
    query = (
        "SELECT '2026-10-24T12:00:00+00:00' AS deadline, "
        "'2026-10-23T12:00:00+00:00' AS created_at, {} AS completed_at"
    )
    open_task = database._task_to_dict(fetch_row(query.format("NULL")))
    assert open_task["deadline"] == hours(24)
    assert open_task["created_at"] == NOW
    assert open_task["completed_at"] is None
    done = database._task_to_dict(
        fetch_row(query.format("'2026-10-23T13:00:00+00:00'"))
    )
    assert done["completed_at"] == hours(1)


async def test_connect_sets_pragma_and_row_factory(db_path):
    async with database._connect(db_path) as conn:
        cursor = await conn.execute("PRAGMA foreign_keys")
        assert (await cursor.fetchone())[0] == 1
        cursor = await conn.execute("SELECT 1 AS x")
        assert (await cursor.fetchone())["x"] == 1


# ---------- init_db ----------

async def test_init_db_creates_dir_and_tables(tmp_path):
    path = tmp_path / "data" / "nested" / "bot.db"
    await database.init_db(str(path))
    assert path.exists()
    names = {r[0] for r in sql(str(path), "SELECT name FROM sqlite_master")}
    assert {"users", "tasks", "reminders"} <= names
    assert {"idx_reminders_due", "idx_tasks_user_status"} <= names


async def test_init_db_with_bare_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    await database.init_db("bot.db")
    assert (tmp_path / "bot.db").exists()


async def test_init_db_is_idempotent(db):
    await database.get_or_create_user(db, 1)
    await database.init_db(db)
    assert sql(db, "SELECT COUNT(*) FROM users") == [(1,)]


# ---------- пользователи ----------

async def test_get_or_create_user_defaults(db):
    user = await database.get_or_create_user(db, 5)
    assert user["id"] == 5
    assert user["timezone"] == "Europe/Moscow"
    assert user["reminder_offsets"] == "1440,60"
    assert user["morning_digest"] == 0
    assert user["created_at"].utcoffset() == timedelta(0)


async def test_get_or_create_user_no_duplicates(db):
    first = await database.get_or_create_user(db, 5)
    second = await database.get_or_create_user(db, 5)
    assert second == first
    assert sql(db, "SELECT COUNT(*) FROM users") == [(1,)]


async def test_update_user_timezone(db):
    await database.get_or_create_user(db, 1)
    await database.get_or_create_user(db, 2)
    await database.update_user_timezone(db, 1, "Asia/Novosibirsk")
    assert (await database.get_or_create_user(db, 1))["timezone"] == "Asia/Novosibirsk"
    assert (await database.get_or_create_user(db, 2))["timezone"] == "Europe/Moscow"


async def test_update_user_offsets(db):
    await database.get_or_create_user(db, 1)
    await database.update_user_offsets(db, 1, (4320, 1440, 60))
    user = await database.get_or_create_user(db, 1)
    assert user["reminder_offsets"] == "4320,1440,60"


async def test_count_active_tasks_counts_only_active_of_user(db):
    ids = [await make_task(db, title=f"t{i}") for i in range(4)]
    await make_task(db, user_id=2)
    sql(db, "UPDATE tasks SET status = 'done' WHERE id = ?", (ids[0],))
    sql(db, "UPDATE tasks SET status = 'expired' WHERE id = ?", (ids[1],))
    assert await database.count_active_tasks(db, 1) == 2
    assert await database.count_active_tasks(db, 2) == 1
    assert await database.count_active_tasks(db, 99) == 0


# ---------- add_task, get_task ----------

async def test_add_task_creates_task_and_reminders(db):
    task_id = await make_task(db, reminders=[hours(24), hours(47)])
    assert isinstance(task_id, int)
    task = await database.get_task(db, task_id, 1)
    assert task["title"] == "Лаба"
    assert task["status"] == "active"
    assert task["deadline"] == hours(48)
    assert task["completed_at"] is None
    rows = sql(db, "SELECT remind_at, sent FROM reminders WHERE task_id = ? ORDER BY remind_at", (task_id,))
    assert rows == [("2026-10-24T12:00:00+00:00", 0), ("2026-10-25T11:00:00+00:00", 0)]


async def test_add_task_without_reminders(db):
    task_id = await make_task(db, reminders=[])
    assert sql(db, "SELECT COUNT(*) FROM reminders WHERE task_id = ?", (task_id,)) == [(0,)]


async def test_add_task_stores_title_verbatim(db):
    title = "x'); DROP TABLE tasks;--"
    task_id = await make_task(db, title=title)
    assert (await database.get_task(db, task_id, 1))["title"] == title


async def test_add_task_unknown_user_violates_foreign_key(db):
    with pytest.raises(sqlite3.IntegrityError):
        await database.add_task(db, 404, "t", hours(48), [hours(1)])
    assert sql(db, "SELECT COUNT(*) FROM tasks") == [(0,)]
    assert sql(db, "SELECT COUNT(*) FROM reminders") == [(0,)]


async def test_get_task_own_foreign_and_missing(db):
    task_id = await make_task(db, user_id=1)
    await database.get_or_create_user(db, 2)
    assert (await database.get_task(db, task_id, 1))["id"] == task_id
    assert await database.get_task(db, task_id, 2) is None
    assert await database.get_task(db, 9999, 1) is None


async def test_get_task_dates_are_aware_utc(db):
    task_id = await make_task(db)
    task = await database.get_task(db, task_id, 1)
    for key in ("deadline", "created_at"):
        assert task[key].utcoffset() == timedelta(0)


# ---------- get_active_tasks ----------

async def test_get_active_tasks_sorted_and_only_active(db):
    await make_task(db, title="c", deadline=hours(72))
    await make_task(db, title="a", deadline=hours(24))
    done_id = await make_task(db, title="done", deadline=hours(30))
    expired_id = await make_task(db, title="exp", deadline=hours(31))
    await make_task(db, user_id=2, title="other", deadline=hours(25))
    await make_task(db, title="b", deadline=hours(48))
    sql(db, "UPDATE tasks SET status = 'done' WHERE id = ?", (done_id,))
    sql(db, "UPDATE tasks SET status = 'expired' WHERE id = ?", (expired_id,))
    tasks = await database.get_active_tasks(db, 1)
    assert [t["title"] for t in tasks] == ["a", "b", "c"]


async def test_get_active_tasks_date_range_is_half_open(db):
    for h in (10, 20, 30):
        await make_task(db, title=f"h{h}", deadline=hours(h))
    both = await database.get_active_tasks(db, 1, hours(10), hours(30))
    assert [t["title"] for t in both] == ["h10", "h20"]
    only_from = await database.get_active_tasks(db, 1, date_from=hours(20))
    assert [t["title"] for t in only_from] == ["h20", "h30"]
    only_to = await database.get_active_tasks(db, 1, date_to=hours(20))
    assert [t["title"] for t in only_to] == ["h10"]


async def test_get_active_tasks_empty(db):
    await database.get_or_create_user(db, 1)
    assert await database.get_active_tasks(db, 1) == []


# ---------- delete_task ----------

async def test_delete_task_removes_task_and_reminders(db):
    task_id = await make_task(db, reminders=[hours(1), hours(2)])
    assert await database.delete_task(db, task_id, 1) is True
    assert await database.get_task(db, task_id, 1) is None
    assert sql(db, "SELECT COUNT(*) FROM reminders") == [(0,)]


async def test_delete_task_foreign_and_missing(db):
    task_id = await make_task(db, user_id=1, reminders=[hours(1)])
    await database.get_or_create_user(db, 2)
    assert await database.delete_task(db, task_id, 2) is False
    assert await database.delete_task(db, 9999, 1) is False
    assert await database.get_task(db, task_id, 1) is not None
    assert sql(db, "SELECT COUNT(*) FROM reminders") == [(1,)]


# ---------- mark_task_done ----------

async def test_mark_task_done_sets_status_and_drops_unsent(db):
    task_id = await make_task(db, reminders=[hours(1), hours(2)])
    first = sql(db, "SELECT id FROM reminders ORDER BY id")[0][0]
    await database.mark_reminder_sent(db, first)
    assert await database.mark_task_done(db, task_id, 1, hours(5)) is True
    task = await database.get_task(db, task_id, 1)
    assert task["status"] == "done"
    assert task["completed_at"] == hours(5)
    assert sql(db, "SELECT id, sent FROM reminders") == [(first, 1)]


async def test_mark_task_done_twice_returns_false(db):
    task_id = await make_task(db)
    assert await database.mark_task_done(db, task_id, 1, NOW) is True
    assert await database.mark_task_done(db, task_id, 1, hours(1)) is False
    assert (await database.get_task(db, task_id, 1))["completed_at"] == NOW


async def test_mark_task_done_works_for_expired(db):
    task_id = await make_task(db)
    sql(db, "UPDATE tasks SET status = 'expired' WHERE id = ?", (task_id,))
    assert await database.mark_task_done(db, task_id, 1, NOW) is True
    assert (await database.get_task(db, task_id, 1))["status"] == "done"


async def test_mark_task_done_foreign_and_missing(db):
    task_id = await make_task(db, user_id=1, reminders=[hours(1)])
    await database.get_or_create_user(db, 2)
    assert await database.mark_task_done(db, task_id, 2, NOW) is False
    assert await database.mark_task_done(db, 9999, 1, NOW) is False
    task = await database.get_task(db, task_id, 1)
    assert task["status"] == "active"
    assert sql(db, "SELECT COUNT(*) FROM reminders") == [(1,)]


# ---------- shift_task_deadline ----------

async def test_shift_task_deadline_replaces_unsent_reminders(db):
    task_id = await make_task(db, reminders=[hours(24), hours(36)])
    first = sql(db, "SELECT id FROM reminders ORDER BY id")[0][0]
    await database.mark_reminder_sent(db, first)
    ok = await database.shift_task_deadline(db, task_id, 1, hours(72), [hours(60)])
    assert ok is True
    assert (await database.get_task(db, task_id, 1))["deadline"] == hours(72)
    rows = sql(db, "SELECT remind_at, sent FROM reminders ORDER BY remind_at")
    assert rows == [("2026-10-24T12:00:00+00:00", 1), ("2026-10-26T00:00:00+00:00", 0)]


async def test_shift_task_deadline_foreign_missing_and_not_active(db):
    task_id = await make_task(db, user_id=1, reminders=[hours(24)])
    await database.get_or_create_user(db, 2)
    assert await database.shift_task_deadline(db, task_id, 2, hours(72), []) is False
    assert await database.shift_task_deadline(db, 9999, 1, hours(72), []) is False
    sql(db, "UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
    assert await database.shift_task_deadline(db, task_id, 1, hours(72), []) is False
    assert (await database.get_task(db, task_id, 1))["deadline"] == hours(48)
    assert sql(db, "SELECT COUNT(*) FROM reminders") == [(1,)]


# ---------- напоминания ----------

async def test_get_due_reminders_only_due_unsent_active(db):
    task_id = await make_task(db, reminders=[hours(-2), hours(-1), hours(0), hours(1)])
    ids = [r[0] for r in sql(db, "SELECT id FROM reminders ORDER BY remind_at")]
    await database.mark_reminder_sent(db, ids[1])
    due = await database.get_due_reminders(db, NOW)
    assert [d["reminder_id"] for d in due] == [ids[0], ids[2]]
    first = due[0]
    assert first["task_id"] == task_id
    assert first["user_id"] == 1
    assert first["title"] == "Лаба"
    assert first["timezone"] == "Europe/Moscow"
    assert first["deadline"] == hours(48)
    assert first["remind_at"] == hours(-2)


async def test_get_due_reminders_skips_inactive_tasks(db):
    done_id = await make_task(db, title="done", reminders=[hours(-1)])
    expired_id = await make_task(db, title="exp", reminders=[hours(-1)])
    await make_task(db, title="active", reminders=[hours(-1)])
    sql(db, "UPDATE tasks SET status = 'done' WHERE id = ?", (done_id,))
    sql(db, "UPDATE tasks SET status = 'expired' WHERE id = ?", (expired_id,))
    due = await database.get_due_reminders(db, NOW)
    assert [d["title"] for d in due] == ["active"]


async def test_get_due_reminders_uses_user_timezone(db):
    await make_task(db, reminders=[hours(-1)])
    await database.update_user_timezone(db, 1, "Asia/Novosibirsk")
    due = await database.get_due_reminders(db, NOW)
    assert due[0]["timezone"] == "Asia/Novosibirsk"


async def test_mark_reminder_sent_removes_from_due(db):
    await make_task(db, reminders=[hours(-1)])
    reminder_id = (await database.get_due_reminders(db, NOW))[0]["reminder_id"]
    await database.mark_reminder_sent(db, reminder_id)
    assert await database.get_due_reminders(db, NOW) == []
    assert sql(db, "SELECT sent FROM reminders WHERE id = ?", (reminder_id,)) == [(1,)]


# ---------- expire_overdue_tasks ----------

async def test_expire_overdue_tasks_marks_and_returns_once(db):
    past = await make_task(db, title="past", deadline=hours(-1))
    other = await make_task(db, user_id=2, title="other", deadline=hours(-3))
    await make_task(db, title="future", deadline=hours(5))
    result = await database.expire_overdue_tasks(db, NOW)
    assert [r["task_id"] for r in result] == [other, past]
    assert result[1] == {
        "task_id": past, "user_id": 1, "title": "past", "deadline": hours(-1),
    }
    statuses = dict(sql(db, "SELECT title, status FROM tasks"))
    assert statuses == {"past": "expired", "other": "expired", "future": "active"}
    assert await database.expire_overdue_tasks(db, NOW) == []


async def test_expire_overdue_tasks_deadline_equal_now_is_not_overdue(db):
    await make_task(db, title="edge", deadline=NOW)
    assert await database.expire_overdue_tasks(db, NOW) == []
    assert sql(db, "SELECT status FROM tasks") == [("active",)]


async def test_expire_overdue_tasks_ignores_done_and_not_counted_as_active(db):
    done_id = await make_task(db, title="done", deadline=hours(-1))
    await make_task(db, title="late", deadline=hours(-2))
    await database.mark_task_done(db, done_id, 1, NOW)
    result = await database.expire_overdue_tasks(db, NOW)
    assert [r["title"] for r in result] == ["late"]
    assert (await database.get_task(db, done_id, 1))["status"] == "done"
    assert await database.count_active_tasks(db, 1) == 0