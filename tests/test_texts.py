import texts


def test_add_summary_with_all_parts():
    text = texts.add_summary(
        "Лаба", "28.10 в 23:59", "через 5 дн.", ["за 1 день", "за 1 час"], ["за 3 дня"]
    )
    assert text.split("\n") == [
        "Проверь задачу:",
        "Название: <b>Лаба</b>",
        "Дедлайн: 28.10 в 23:59",
        "Осталось: через 5 дн.",
        "Напомню: за 1 день, за 1 час",
        "Пропущу, время уже прошло: за 3 дня",
    ]


def test_add_summary_escapes_html_in_title():
    text = texts.add_summary("<script>a & b</script>", "d", "l", ["за 1 час"], [])
    assert "&lt;script&gt;a &amp; b&lt;/script&gt;" in text
    assert "<script>" not in text


def test_add_summary_without_skipped_has_no_skipped_line():
    text = texts.add_summary("t", "d", "l", ["за 1 час"], [])
    assert "Пропущу" not in text


def test_add_summary_without_reminders_shows_warning():
    text = texts.add_summary("t", "d", "l", [], ["за 1 день", "за 1 час"])
    assert texts.ADD_NO_REMINDERS in text
    assert "Напомню" not in text
    assert "Пропущу, время уже прошло: за 1 день, за 1 час" in text


def test_add_saved_with_and_without_reminders():
    assert texts.add_saved(["за 1 день", "за 1 час"]) == (
        "Сохранено ✅ Напомню за 1 день, за 1 час"
    )
    assert "Напоминаний не будет" in texts.add_saved([])


def test_templates_with_limit_placeholder_are_formattable():
    for template in (texts.ADD_TITLE_TOO_LONG, texts.ADD_LIMIT_REACHED):
        formatted = template.format(limit=100)
        assert "100" in formatted
        assert "{" not in formatted




def test_task_list_format():
    text = texts.task_list(
        [("Лаба", "28.10 в 23:59", "через 2 дн. 3 ч."), ("Курсовая", "29.10 в 10:00", "через 3 дн.")],
        0,
    )
    assert text == (
        "1. <b>Лаба</b>\n    28.10 в 23:59 (через 2 дн. 3 ч.)\n\n"
        "2. <b>Курсовая</b>\n    29.10 в 10:00 (через 3 дн.)"
    )


def test_task_list_escapes_title():
    text = texts.task_list([("<i>a</i> & b", "d", "l")], 0)
    assert "&lt;i&gt;a&lt;/i&gt; &amp; b" in text
    assert "<i>" not in text


def test_task_list_extra_line_only_when_needed():
    rows = [("a", "d", "l")]
    assert "…и ещё" not in texts.task_list(rows, 0)
    assert texts.task_list(rows, 3).endswith("…и ещё 3. Заверши или удали часть задач")


def test_delete_confirm_escapes_title():
    assert texts.delete_confirm("Лаба") == "Удалить «Лаба»?"
    assert texts.delete_confirm("<b>&") == "Удалить «&lt;b&gt;&amp;»?"



def test_reminder_format():
    text = texts.reminder("Сдать лабу", "28.10 в 23:59", "через 1 ч.", False)
    assert text.split("\n") == [
        "⏰ Напоминание!",
        "Задача: Сдать лабу",
        "Дедлайн: 28.10 в 23:59 (через 1 ч.)",
    ]


def test_reminder_late_adds_warning_line():
    text = texts.reminder("Лаба", "d", "l", True)
    assert text.split("\n")[-1] == "⚠️ (бот был недоступен, напоминание опоздало)"
    assert "опоздало" not in texts.reminder("Лаба", "d", "l", False)


def test_reminder_escapes_title():
    text = texts.reminder("<b>x</b> & y", "d", "l", False)
    assert "Задача: &lt;b&gt;x&lt;/b&gt; &amp; y" in text
    assert "<b>" not in text


def test_task_expired_text_and_escaping():
    assert texts.task_expired("Лаба") == "Дедлайн по задаче «Лаба» прошёл"
    assert texts.task_expired("<i>&") == "Дедлайн по задаче «&lt;i&gt;&amp;» прошёл"



def test_timezone_saved_text_and_escaping():
    assert texts.timezone_saved("Europe/Berlin") == (
        "Часовой пояс: Europe/Berlin. Теперь добавь дедлайн через /add"
    )
    assert "&lt;b&gt;" in texts.timezone_saved("<b>")


def test_deadline_shifted_text():
    assert texts.deadline_shifted("28.10 в 23:59") == "Дедлайн перенесён на 28.10 в 23:59"


def test_start_text_mentions_timezone_choice():
    assert "часовой пояс" in texts.START



def test_settings_menu_text_and_escaping():
    text = texts.settings_menu("Europe/Moscow", "за 1 день, за 1 час")
    assert text.split("\n") == [
        "⚙️ Настройки",
        "Часовой пояс: Europe/Moscow",
        "Напоминания: за 1 день, за 1 час",
    ]
    assert "&lt;b&gt;" in texts.settings_menu("<b>", "x")


def test_offsets_menu_mentions_current_and_new_tasks_only():
    text = texts.offsets_menu("за 1 час")
    assert "Сейчас: за 1 час" in text
    assert "только новых задач" in text


def test_offsets_saved_mentions_label_and_new_tasks_only():
    text = texts.offsets_saved("только за 1 час")
    assert "напомню только за 1 час" in text
    assert "только новых задач" in text


def test_simple_texts_are_not_empty():
    for value in (texts.TODAY_HEADER, texts.WEEK_HEADER, texts.TODAY_EMPTY,
                  texts.WEEK_EMPTY, texts.ERROR_GENERIC, texts.CHOOSE_TIMEZONE):
        assert value.strip()
    assert "/help" in texts.FALLBACK
