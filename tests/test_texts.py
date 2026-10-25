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