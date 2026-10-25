"""Общие фикстуры: БД во временной папке, заглушки Telegram, FSM."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

import config


@pytest.fixture
def db_path(tmp_path, monkeypatch) -> str:
    """Путь к временной БД; подменяет config.DB_PATH."""
    path = str(tmp_path / "t.db")
    monkeypatch.setattr(config, "DB_PATH", path)
    return path


@pytest.fixture
def fake_message() -> AsyncMock:
    """Message без сети: user_id=1, text пустой (для стикера задай None)."""
    message = AsyncMock()
    message.from_user = MagicMock(id=1)
    message.text = ""
    return message


@pytest.fixture
def fake_callback() -> AsyncMock:
    """CallbackQuery без сети: user_id=1, data задаётся в тесте."""
    callback = AsyncMock()
    callback.from_user = MagicMock(id=1)
    callback.data = ""
    callback.message = AsyncMock()
    return callback


@pytest.fixture
def fake_bot() -> AsyncMock:
    """Bot без сети: send_message это AsyncMock, ошибки через side_effect."""
    return AsyncMock()


@pytest.fixture
def fsm() -> FSMContext:
    """FSMContext на MemoryStorage."""
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=MemoryStorage(), key=key)