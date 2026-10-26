import pytest
from aiogram.filters import StateFilter

import texts
from handlers import fallback


async def test_unknown_message_suggests_help(fake_message):
    fake_message.text = "абракадабра"
    await fallback.unknown_message(fake_message)
    fake_message.answer.assert_awaited_once_with(texts.FALLBACK)


async def test_unknown_message_for_non_text(fake_message):
    fake_message.text = None
    await fallback.unknown_message(fake_message)
    fake_message.answer.assert_awaited_once_with(texts.FALLBACK)


def registered_state_filters():
    handlers = fallback.router.message.handlers
    assert len(handlers) == 1
    return [f.callback for f in handlers[0].filters]


def test_fallback_has_exactly_one_state_filter():
    filters = registered_state_filters()
    assert len(filters) == 1
    assert isinstance(filters[0], StateFilter)


async def test_fallback_filter_passes_outside_fsm(fake_message):
    (state_filter,) = registered_state_filters()
    assert await state_filter(fake_message, raw_state=None)


@pytest.mark.parametrize("raw_state", [
    "AddTask:waiting_title",
    "AddTask:waiting_deadline",
    "AddTask:waiting_confirm",
    "SetTimezone:waiting_timezone",
])
async def test_fallback_filter_blocks_inside_fsm(fake_message, raw_state):
    (state_filter,) = registered_state_filters()
    assert not await state_filter(fake_message, raw_state=raw_state)