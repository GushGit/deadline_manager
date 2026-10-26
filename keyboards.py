"""Фабрики inline-клавиатур."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Кнопки подтверждения в /add: сохранить или отменить."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сохранить ✅", callback_data="add_save"),
                InlineKeyboardButton(text="Отмена ❌", callback_data="add_cancel"),
            ]
        ]
    )


def tasks_keyboard(tasks: list[dict]) -> InlineKeyboardMarkup:
    """Для каждой задачи строка [✅ №N] [🗑 №N]; N это номер в списке."""
    rows = [
        [
            InlineKeyboardButton(text=f"✅ №{number}", callback_data=f"done:{task['id']}"),
            InlineKeyboardButton(text=f"🗑 №{number}", callback_data=f"del:{task['id']}"),
        ]
        for number, task in enumerate(tasks, start=1)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_keyboard(tasks: list[dict]) -> InlineKeyboardMarkup:
    """Для каждой задачи строка с одной кнопкой [🗑 №N]."""
    rows = [
        [InlineKeyboardButton(text=f"🗑 №{number}", callback_data=f"del:{task['id']}")]
        for number, task in enumerate(tasks, start=1)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления: [Да, удалить] [Нет]."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data=f"delyes:{task_id}"),
                InlineKeyboardButton(text="Нет", callback_data=f"delno:{task_id}"),
            ]
        ]
    )


def reminder_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Кнопки под напоминанием: выполнено, +1 час, +1 день."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data=f"done:{task_id}"),
                InlineKeyboardButton(text="⏳ +1 час", callback_data=f"snooze_h:{task_id}"),
                InlineKeyboardButton(text="📅 +1 день", callback_data=f"snooze_d:{task_id}"),
            ]
        ]
    )


def expired_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Кнопка под уведомлением о просрочке."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Всё-таки выполнено", callback_data=f"done:{task_id}")]
        ]
    )


def timezone_keyboard() -> InlineKeyboardMarkup:
    """Популярные часовые пояса по два в ряд и кнопка «Другой»."""
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"tz:{iana}")
        for label, iana in config.POPULAR_TIMEZONES.items()
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="Другой", callback_data="tz_other")])
    return InlineKeyboardMarkup(inline_keyboard=rows)