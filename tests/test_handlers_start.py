import texts
from handlers import start


async def test_cmd_start_sends_greeting(fake_message):
    await start.cmd_start(fake_message)
    fake_message.answer.assert_awaited_once_with(texts.START)


async def test_cmd_help_lists_all_commands(fake_message):
    await start.cmd_help(fake_message)
    fake_message.answer.assert_awaited_once()
    text = fake_message.answer.await_args.args[0]
    for command in ("/start", "/help", "/add", "/list", "/delete",
                    "/cancel", "/today", "/week", "/settings"):
        assert command in text