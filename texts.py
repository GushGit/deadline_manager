"""Тексты сообщений бота."""

import html

START = (
    "Привет! Я помогу не забыть про дедлайны.\n\n"
    "Добавь задачу через /add, и я напомню о ней заранее: "
    "по умолчанию за сутки и за час.\n"
    "Все команды: /help\n\n"
    "Сначала выбери свой часовой пояс, чтобы напоминания приходили вовремя:"
)

HELP = (
    "Что я умею:\n"
    "/start: приветствие\n"
    "/add: добавить дедлайн\n"
    "/list: активные дедлайны\n"
    "/today: дедлайны на сегодня\n"
    "/week: дедлайны на 7 дней\n"
    "/delete: удалить дедлайн\n"
    "/settings: часовой пояс и интервалы напоминаний\n"
    "/cancel: прервать диалог\n"
    "/help: этот список"
)

ERR_DT_FORMAT = "Не понял формат. Напиши дату и время так: 28.10 23:59"
ERR_DT_DATE = "Такой даты не существует. Проверь день и месяц"
ERR_DT_PAST = "Эта дата уже прошла. Укажи время в будущем"
ERR_DT_FAR = "Дедлайн не может быть дальше чем через 2 года"
ERR_DT_GAP = "Такого времени в твоём поясе не бывает (переход на летнее время). Выбери другое"


ADD_ASK_TITLE = "Как называется задача?"
ADD_TITLE_EMPTY = "Название не может быть пустым. Напиши, как называется задача"
ADD_TITLE_TOO_LONG = (
    "Слишком длинное название: максимум {limit} символов. Сократи, пожалуйста"
)
ADD_ASK_DEADLINE = (
    "Когда дедлайн? Напиши дату и время в формате ДД.ММ ЧЧ:ММ, "
    "например: 28.10 23:59"
)
ADD_LIMIT_REACHED = "У тебя уже {limit} активных дедлайнов. Заверши или удали часть задач"
ADD_NO_REMINDERS = "Напоминаний не будет, дедлайн слишком близко"
ADD_CONFIRM_WAIT = "Нажми «Сохранить» или «Отмена», либо отправь /cancel"
ADD_DEADLINE_PASSED = "Пока ты думал, дедлайн уже прошёл. Начни заново через /add"
TEXT_ONLY = "Жду текст"
FINISH_DIALOG = "Сначала закончи диалог или отправь /cancel"
CANCELLED = "Отменено"
NOTHING_TO_CANCEL = "Нечего отменять"
BUTTON_OUTDATED = "Эта кнопка устарела. Начни заново через /add"


def add_summary(
    title: str,
    deadline_text: str,
    left_text: str,
    kept: list[str],
    skipped: list[str],
) -> str:
    """Сводка перед сохранением; название экранируется."""
    lines = [
        "Проверь задачу:",
        f"Название: <b>{html.escape(title)}</b>",
        f"Дедлайн: {deadline_text}",
        f"Осталось: {left_text}",
    ]
    if kept:
        lines.append("Напомню: " + ", ".join(kept))
    else:
        lines.append("⚠️ " + ADD_NO_REMINDERS)
    if skipped:
        lines.append("Пропущу, время уже прошло: " + ", ".join(skipped))
    return "\n".join(lines)


def add_saved(kept: list[str]) -> str:
    """Сообщение после сохранения задачи."""
    if kept:
        return "Сохранено ✅ Напомню " + ", ".join(kept)
    return "Сохранено ✅ Напоминаний не будет: дедлайн слишком близко"


LIST_EMPTY = "Активных дедлайнов нет. Добавь первый через /add"
LIST_MORE = "…и ещё {count}. Заверши или удали часть задач"
DELETE_PROMPT = "Какую задачу удалить? Нажми на её номер."
DELETE_DONE = "Удалено 🗑"
DELETE_KEPT = "Хорошо, задача осталась в списке"
TASK_NOT_FOUND = "Задача не найдена"
BAD_BUTTON = "Некорректная кнопка"


def task_list(rows: list[tuple[str, str, str]], extra: int) -> str:
    """Нумерованный список; rows это (название, дедлайн, сколько осталось)."""
    parts = [
        f"{number}. <b>{html.escape(title)}</b>\n    {deadline_text} ({left_text})"
        for number, (title, deadline_text, left_text) in enumerate(rows, start=1)
    ]
    text = "\n\n".join(parts)
    if extra > 0:
        text += "\n\n" + LIST_MORE.format(count=extra)
    return text


def delete_confirm(title: str) -> str:
    """Вопрос перед удалением; название экранируется."""
    return f"Удалить «{html.escape(title)}»?"



def reminder(title: str, deadline_text: str, left_text: str, late: bool) -> str:
    """Текст напоминания; late добавляет пометку об опоздании."""
    lines = [
        "⏰ Напоминание!",
        f"Задача: {html.escape(title)}",
        f"Дедлайн: {deadline_text} ({left_text})",
    ]
    if late:
        lines.append("⚠️ (бот был недоступен, напоминание опоздало)")
    return "\n".join(lines)


def task_expired(title: str) -> str:
    """Уведомление о просроченной задаче."""
    return f"Дедлайн по задаче «{html.escape(title)}» прошёл"



ASK_TIMEZONE = "Напиши название часового пояса в формате Europe/Berlin или отправь /cancel"
TIMEZONE_INVALID = (
    "Не нашёл такой часовой пояс. Напиши в формате Europe/Berlin или отправь /cancel"
)
DONE_OK = "Молодец! Задача выполнена ✅"
DONE_NOT_FOUND = "Задача не найдена или уже выполнена"
SNOOZE_TOO_FAR = "Нельзя перенести дедлайн дальше чем на 2 года вперёд"


def timezone_saved(tz_name: str) -> str:
    """Сообщение после выбора часового пояса."""
    return f"Часовой пояс: {html.escape(tz_name)}. Теперь добавь дедлайн через /add"


def deadline_shifted(deadline_text: str) -> str:
    """Сообщение после переноса дедлайна."""
    return f"Дедлайн перенесён на {deadline_text}"



TODAY_HEADER = "Дедлайны на сегодня:"
WEEK_HEADER = "Дедлайны на ближайшие 7 дней:"
TODAY_EMPTY = "На сегодня дедлайнов нет. Можно выдохнуть 🙂"
WEEK_EMPTY = "На ближайшие 7 дней дедлайнов нет"
ERROR_GENERIC = "Что-то пошло не так, попробуй ещё раз"
FALLBACK = "Не понял. Список команд: /help"
CHOOSE_TIMEZONE = "Выбери часовой пояс:"


def settings_menu(tz_name: str, offsets_text: str) -> str:
    """Главное сообщение /settings с текущими значениями."""
    return (
        "⚙️ Настройки\n"
        f"Часовой пояс: {html.escape(tz_name)}\n"
        f"Напоминания: {offsets_text}"
    )


def offsets_menu(offsets_text: str) -> str:
    """Сообщение с выбором интервалов напоминаний."""
    return (
        "Когда напоминать?\n"
        f"Сейчас: {offsets_text}\n"
        "Изменение касается только новых задач, уже добавленные не меняются."
    )


def offsets_saved(label: str) -> str:
    """Сообщение после выбора пресета интервалов."""
    return (
        f"Готово: напомню {label}.\n"
        "Это касается только новых задач, уже добавленные не меняются."
    )