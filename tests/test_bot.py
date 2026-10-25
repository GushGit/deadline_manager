import logging
import logging.handlers

import pytest
from aiogram import Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import bot
import config
from handlers import start, tasks
from scheduler import check_reminders, expire_overdue_tasks

LIB_LOGGERS = ("aiogram", "aiohttp")


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    old_level = root.level
    old_lib_levels = {n: logging.getLogger(n).level for n in LIB_LOGGERS}
    yield
    for handler in list(root.handlers):
        if handler not in old_handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(old_level)
    for name, level in old_lib_levels.items():
        logging.getLogger(name).setLevel(level)


def test_setup_logging_creates_handlers(tmp_path, monkeypatch, restore_logging):
    log_path = tmp_path / "logs" / "bot.log"
    monkeypatch.setattr(config, "LOG_PATH", str(log_path))
    root = logging.getLogger()
    before = list(root.handlers)

    bot.setup_logging()

    new = [h for h in root.handlers if h not in before]
    assert log_path.parent.is_dir()
    assert len(new) == 2
    files = [h for h in new if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(files) == 1
    assert files[0].baseFilename == str(log_path)
    assert files[0].maxBytes == 1_000_000
    assert files[0].backupCount == 3
    assert any(type(h) is logging.StreamHandler for h in new)
    assert root.level == logging.INFO


def test_setup_logging_library_levels(tmp_path, monkeypatch, restore_logging):
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "bot.log"))
    bot.setup_logging()
    for name in LIB_LOGGERS:
        assert logging.getLogger(name).level >= logging.INFO


def test_setup_logging_does_not_leak_token(tmp_path, monkeypatch, restore_logging):
    log_path = tmp_path / "bot.log"
    monkeypatch.setattr(config, "LOG_PATH", str(log_path))
    monkeypatch.setattr(config, "BOT_TOKEN", "123456:SECRET")
    bot.setup_logging()
    logging.getLogger("test").info("Бот запускается")
    for handler in logging.getLogger().handlers:
        handler.flush()
    text = log_path.read_text(encoding="utf-8")
    assert "Бот запускается" in text
    assert "SECRET" not in text


def test_build_dispatcher_includes_routers():
    dp = bot.build_dispatcher()
    assert isinstance(dp, Dispatcher)
    assert dp.sub_routers == [tasks.router, start.router]


async def test_setup_scheduler_creates_two_jobs(fake_bot):
    sched = bot.setup_scheduler(fake_bot)
    assert isinstance(sched, AsyncIOScheduler)
    assert not sched.running
    jobs = {job.id: job for job in sched.get_jobs()}
    assert set(jobs) == {"check_reminders", "expire_overdue_tasks"}

    check = jobs["check_reminders"]
    assert check.func is check_reminders
    assert check.trigger.interval.total_seconds() == config.CHECK_INTERVAL_SECONDS
    expire = jobs["expire_overdue_tasks"]
    assert expire.func is expire_overdue_tasks
    assert expire.trigger.interval.total_seconds() == config.EXPIRE_INTERVAL_SECONDS
    for job in jobs.values():
        assert job.args == (fake_bot,)
        assert job.max_instances == 1
        assert job.coalesce is True