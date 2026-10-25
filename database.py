"""Вся работа с SQLite: чистый SQL, только параметризованные запросы."""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY,
    timezone          TEXT NOT NULL DEFAULT 'Europe/Moscow',
    reminder_offsets  TEXT NOT NULL DEFAULT '1440,60',
    morning_digest    INTEGER NOT NULL DEFAULT 0,
    digest_time       TEXT NOT NULL DEFAULT '08:00',
    last_digest_date  TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    deadline      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    completed_at  TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    remind_at  TEXT NOT NULL,
    sent       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(sent, remind_at);
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status, deadline);
"""


def _to_str(dt: datetime) -> str:
    """Aware-datetime в строку UTC ISO-8601 без долей секунды."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime запрещён, нужен aware")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _from_str(value: str) -> datetime:
    """Строка ISO-8601 из БД в aware-datetime (UTC)."""
    return datetime.fromisoformat(value)


def _user_to_dict(row) -> dict:
    """Строка таблицы users в словарь."""
    user = dict(row)
    user["created_at"] = _from_str(user["created_at"])
    return user


def _task_to_dict(row) -> dict:
    """Строка таблицы tasks в словарь с датами-datetime."""
    task = dict(row)
    task["deadline"] = _from_str(task["deadline"])
    task["created_at"] = _from_str(task["created_at"])
    if task["completed_at"] is not None:
        task["completed_at"] = _from_str(task["completed_at"])
    return task


@asynccontextmanager
async def _connect(db_path: str):
    """Открывает соединение с foreign_keys и row_factory=Row."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db


async def init_db(db_path: str) -> None:
    """Создаёт каталог для БД и таблицы."""
    folder = os.path.dirname(db_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    async with _connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def get_or_create_user(db_path: str, user_id: int) -> dict:
    """Возвращает пользователя; если его нет, создаёт с настройками по умолчанию."""
    created_at = _to_str(datetime.now(timezone.utc))
    async with _connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (id, created_at) VALUES (?, ?)",
            (user_id, created_at),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
    return _user_to_dict(row)


async def update_user_timezone(db_path: str, user_id: int, tz_name: str) -> None:
    """Меняет часовой пояс пользователя."""
    async with _connect(db_path) as db:
        await db.execute(
            "UPDATE users SET timezone = ? WHERE id = ?", (tz_name, user_id)
        )
        await db.commit()


async def update_user_offsets(
    db_path: str, user_id: int, offsets: tuple[int, ...]
) -> None:
    """Сохраняет интервалы напоминаний строкой вида '1440,60'."""
    value = ",".join(str(minutes) for minutes in offsets)
    async with _connect(db_path) as db:
        await db.execute(
            "UPDATE users SET reminder_offsets = ? WHERE id = ?", (value, user_id)
        )
        await db.commit()


async def count_active_tasks(db_path: str, user_id: int) -> int:
    """Считает активные задачи пользователя (для лимита)."""
    async with _connect(db_path) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'active'",
            (user_id,),
        )
        row = await cursor.fetchone()
    return row[0]


async def add_task(
    db_path: str,
    user_id: int,
    title: str,
    deadline_utc: datetime,
    remind_times: list[datetime],
) -> int:
    """Создаёт задачу и напоминания в одной транзакции, возвращает task_id."""
    created_at = _to_str(datetime.now(timezone.utc))
    async with _connect(db_path) as db:
        cursor = await db.execute(
            "INSERT INTO tasks (user_id, title, deadline, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, title, _to_str(deadline_utc), created_at),
        )
        task_id = cursor.lastrowid
        await db.executemany(
            "INSERT INTO reminders (task_id, remind_at) VALUES (?, ?)",
            [(task_id, _to_str(moment)) for moment in remind_times],
        )
        await db.commit()
    return task_id


async def get_task(db_path: str, task_id: int, user_id: int) -> dict | None:
    """Возвращает задачу; None, если её нет или она чужая."""
    async with _connect(db_path) as db:
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        row = await cursor.fetchone()
    return _task_to_dict(row) if row else None


async def get_active_tasks(
    db_path: str,
    user_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """Активные задачи по возрастанию дедлайна; диапазон [date_from, date_to)."""
    start = _to_str(date_from) if date_from is not None else None
    end = _to_str(date_to) if date_to is not None else None
    async with _connect(db_path) as db:
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND status = 'active' "
            "AND (? IS NULL OR deadline >= ?) AND (? IS NULL OR deadline < ?) "
            "ORDER BY deadline ASC, id ASC",
            (user_id, start, start, end, end),
        )
        rows = await cursor.fetchall()
    return [_task_to_dict(row) for row in rows]


async def delete_task(db_path: str, task_id: int, user_id: int) -> bool:
    """Удаляет свою задачу (напоминания каскадом); True, если удалено."""
    async with _connect(db_path) as db:
        cursor = await db.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def mark_task_done(
    db_path: str, task_id: int, user_id: int, now_utc: datetime
) -> bool:
    """Ставит active/expired задаче статус done и убирает неотправленные напоминания."""
    async with _connect(db_path) as db:
        cursor = await db.execute(
            "UPDATE tasks SET status = 'done', completed_at = ? "
            "WHERE id = ? AND user_id = ? AND status IN ('active', 'expired')",
            (_to_str(now_utc), task_id, user_id),
        )
        if cursor.rowcount == 0:
            return False
        await db.execute(
            "DELETE FROM reminders WHERE task_id = ? AND sent = 0", (task_id,)
        )
        await db.commit()
        return True


async def shift_task_deadline(
    db_path: str,
    task_id: int,
    user_id: int,
    new_deadline: datetime,
    remind_times: list[datetime],
) -> bool:
    """Меняет дедлайн активной задачи и пересоздаёт неотправленные напоминания."""
    async with _connect(db_path) as db:
        cursor = await db.execute(
            "UPDATE tasks SET deadline = ? "
            "WHERE id = ? AND user_id = ? AND status = 'active'",
            (_to_str(new_deadline), task_id, user_id),
        )
        if cursor.rowcount == 0:
            return False
        await db.execute(
            "DELETE FROM reminders WHERE task_id = ? AND sent = 0", (task_id,)
        )
        await db.executemany(
            "INSERT INTO reminders (task_id, remind_at) VALUES (?, ?)",
            [(task_id, _to_str(moment)) for moment in remind_times],
        )
        await db.commit()
        return True


async def get_due_reminders(db_path: str, now_utc: datetime) -> list[dict]:
    """Наступившие неотправленные напоминания активных задач."""
    async with _connect(db_path) as db:
        cursor = await db.execute(
            "SELECT r.id AS reminder_id, r.task_id, t.user_id, t.title, "
            "t.deadline, r.remind_at, u.timezone "
            "FROM reminders r "
            "JOIN tasks t ON t.id = r.task_id "
            "JOIN users u ON u.id = t.user_id "
            "WHERE r.sent = 0 AND r.remind_at <= ? AND t.status = 'active' "
            "ORDER BY r.remind_at ASC, r.id ASC",
            (_to_str(now_utc),),
        )
        rows = await cursor.fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["deadline"] = _from_str(item["deadline"])
        item["remind_at"] = _from_str(item["remind_at"])
        result.append(item)
    return result


async def mark_reminder_sent(db_path: str, reminder_id: int) -> None:
    """Помечает напоминание отправленным."""
    async with _connect(db_path) as db:
        await db.execute(
            "UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,)
        )
        await db.commit()


async def expire_overdue_tasks(db_path: str, now_utc: datetime) -> list[dict]:
    """Помечает просроченные активные задачи expired и возвращает их один раз."""
    async with _connect(db_path) as db:
        cursor = await db.execute(
            "SELECT id, user_id, title, deadline FROM tasks "
            "WHERE status = 'active' AND deadline < ? "
            "ORDER BY deadline ASC, id ASC",
            (_to_str(now_utc),),
        )
        rows = await cursor.fetchall()
        await db.executemany(
            "UPDATE tasks SET status = 'expired' WHERE id = ? AND status = 'active'",
            [(row["id"],) for row in rows],
        )
        await db.commit()
    return [
        {
            "task_id": row["id"],
            "user_id": row["user_id"],
            "title": row["title"],
            "deadline": _from_str(row["deadline"]),
        }
        for row in rows
    ]