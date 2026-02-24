import pytest

from chat.telegram_adapter import TelegramAdapter


class _Message:
    def __init__(self, message_id: int):
        self.message_id = message_id


@pytest.mark.asyncio
async def test_send_post_for_approval_success(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    adapter = TelegramAdapter()

    class _Bot:
        async def send_message(self, **kwargs):
            assert "approve_post:thread-1" in str(kwargs.get("reply_markup"))
            return _Message(123)

    adapter.bot = _Bot()
    adapter._bot_initialized = True

    message_id = await adapter.send_post_for_approval(
        user_id="1",
        post_content="Generated post text",
        post_id="thread-1",
        chat_id="1",
    )

    assert message_id == "123"


@pytest.mark.asyncio
async def test_send_notification_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    adapter = TelegramAdapter()

    class _Bot:
        def __init__(self):
            self.calls = 0

        async def send_message(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient failure")
            return _Message(456)

    bot = _Bot()
    adapter.bot = bot
    adapter._bot_initialized = True

    ok = await adapter.send_notification(
        user_id="1",
        notification_type="info",
        message="hello",
        chat_id="1",
    )

    assert ok is True
    assert bot.calls == 2
