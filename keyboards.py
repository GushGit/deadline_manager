"""Фабрики inline-клавиатур."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


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