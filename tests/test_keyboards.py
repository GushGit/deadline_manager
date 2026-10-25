import keyboards


def test_confirm_keyboard_layout():
    markup = keyboards.confirm_keyboard()
    assert len(markup.inline_keyboard) == 1
    row = markup.inline_keyboard[0]
    assert [b.text for b in row] == ["Сохранить ✅", "Отмена ❌"]
    assert [b.callback_data for b in row] == ["add_save", "add_cancel"]


def test_confirm_keyboard_callback_data_fits_telegram_limit():
    for button in keyboards.confirm_keyboard().inline_keyboard[0]:
        assert len(button.callback_data.encode("utf-8")) <= 64



TASKS = [{"id": 11}, {"id": 25}, {"id": 1_000_000_000_000}]


def test_tasks_keyboard_rows_match_list_numbers():
    markup = keyboards.tasks_keyboard(TASKS)
    assert len(markup.inline_keyboard) == 3
    for number, (row, task) in enumerate(zip(markup.inline_keyboard, TASKS), start=1):
        assert [b.text for b in row] == [f"✅ №{number}", f"🗑 №{number}"]
        assert [b.callback_data for b in row] == [f"done:{task['id']}", f"del:{task['id']}"]


def test_tasks_keyboard_empty_has_no_rows():
    assert keyboards.tasks_keyboard([]).inline_keyboard == []


def test_delete_keyboard_one_button_per_row():
    markup = keyboards.delete_keyboard(TASKS)
    assert [len(row) for row in markup.inline_keyboard] == [1, 1, 1]
    assert [row[0].text for row in markup.inline_keyboard] == ["🗑 №1", "🗑 №2", "🗑 №3"]
    assert [row[0].callback_data for row in markup.inline_keyboard] == [
        "del:11", "del:25", "del:1000000000000",
    ]


def test_delete_confirm_keyboard():
    markup = keyboards.delete_confirm_keyboard(42)
    assert len(markup.inline_keyboard) == 1
    row = markup.inline_keyboard[0]
    assert [b.text for b in row] == ["Да, удалить", "Нет"]
    assert [b.callback_data for b in row] == ["delyes:42", "delno:42"]


def test_list_keyboards_callback_data_fit_telegram_limit():
    for markup in (
        keyboards.tasks_keyboard(TASKS),
        keyboards.delete_keyboard(TASKS),
        keyboards.delete_confirm_keyboard(1_000_000_000_000),
    ):
        for row in markup.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode("utf-8")) <= 64



def test_reminder_keyboard_buttons():
    markup = keyboards.reminder_keyboard(42)
    assert len(markup.inline_keyboard) == 1
    row = markup.inline_keyboard[0]
    assert [b.text for b in row] == ["✅ Выполнено", "⏳ +1 час", "📅 +1 день"]
    assert [b.callback_data for b in row] == ["done:42", "snooze_h:42", "snooze_d:42"]


def test_expired_keyboard_button():
    markup = keyboards.expired_keyboard(42)
    assert len(markup.inline_keyboard) == 1
    row = markup.inline_keyboard[0]
    assert [b.text for b in row] == ["✅ Всё-таки выполнено"]
    assert [b.callback_data for b in row] == ["done:42"]


def test_reminder_keyboards_callback_data_fit_telegram_limit():
    for markup in (
        keyboards.reminder_keyboard(1_000_000_000_000),
        keyboards.expired_keyboard(1_000_000_000_000),
    ):
        for button in markup.inline_keyboard[0]:
            assert len(button.callback_data.encode("utf-8")) <= 64