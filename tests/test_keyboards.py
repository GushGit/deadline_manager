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