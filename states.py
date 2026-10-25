"""Состояния FSM."""
from aiogram.fsm.state import State, StatesGroup


class AddTask(StatesGroup):
    """Диалог /add: название, дедлайн, подтверждение."""

    waiting_title = State()
    waiting_deadline = State()
    waiting_confirm = State()