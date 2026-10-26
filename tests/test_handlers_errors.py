import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import texts
from handlers import errors


def make_error():
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        return exc


def make_event(message=None, callback_query=None, exception=None):
    update = SimpleNamespace(message=message, callback_query=callback_query)
    return SimpleNamespace(update=update, exception=exception or make_error())


async def test_error_in_message_handler_answers_via_message():
    message = AsyncMock()
    result = await errors.on_error(make_event(message=message))
    message.answer.assert_awaited_once_with(texts.ERROR_GENERIC)
    assert result is True


async def test_error_in_callback_handler_answers_via_callback_alert():
    callback = AsyncMock()
    result = await errors.on_error(make_event(callback_query=callback))
    callback.answer.assert_awaited_once_with(texts.ERROR_GENERIC, show_alert=True)
    assert result is True


async def test_error_prefers_callback_over_message():
    message, callback = AsyncMock(), AsyncMock()
    await errors.on_error(make_event(message=message, callback_query=callback))
    callback.answer.assert_awaited_once()
    message.answer.assert_not_awaited()


async def test_error_for_update_without_message_or_callback_is_silent():
    result = await errors.on_error(make_event())
    assert result is True


async def test_error_is_logged_with_traceback(caplog):
    error = make_error()
    with caplog.at_level(logging.ERROR):
        await errors.on_error(make_event(message=AsyncMock(), exception=error))
    records = [r for r in caplog.records if r.levelno == logging.ERROR and r.exc_info]
    assert records
    assert records[0].exc_info[1] is error
    assert records[0].exc_info[2] is not None


async def test_failure_while_answering_message_is_swallowed(caplog):
    message = AsyncMock()
    message.answer.side_effect = RuntimeError("telegram is down")
    with caplog.at_level(logging.ERROR):
        result = await errors.on_error(make_event(message=message))
    assert result is True
    assert any("Не удалось отправить" in r.getMessage() for r in caplog.records)


async def test_failure_while_answering_callback_is_swallowed(caplog):
    callback = AsyncMock()
    callback.answer.side_effect = RuntimeError("telegram is down")
    with caplog.at_level(logging.ERROR):
        result = await errors.on_error(make_event(callback_query=callback))
    assert result is True
    assert any("Не удалось отправить" in r.getMessage() for r in caplog.records)