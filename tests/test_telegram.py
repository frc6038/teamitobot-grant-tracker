"""Telegram behavior characterization tests for GRANT-05.

Tests cover:
- Command handlers
- Button routing
- Turkish responses
- Notification batching
- Markdown edge cases
- Send failure behavior
- Duplicate commands
- Polling configuration
- Application-level handler registration

All external Telegram interactions are mocked.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import Update
from telegram.ext import CommandHandler, MessageHandler

from bot import (
    handle_text,
    help_command,
    main,
    next_check,
    scrape_and_notify_loop,
    start,
    stats,
    status,
)
from tests.fakes.telegram_fakes import create_fake_notification

# ==========================================
# TEST HELPERS
# ==========================================


def run_async(coroutine):
    """Run an async test helper from a synchronous pytest test."""
    return asyncio.run(coroutine)


async def wait_for_send_count(
    fake_application,
    expected_count: int,
    attempts: int = 100,
    interval: float = 0.01,
) -> None:
    """Wait until the fake bot sends the expected number of messages.

    Raises AssertionError instead of silently continuing when the expected
    event never occurs.
    """
    for _ in range(attempts):
        if len(fake_application.bot.send_message_calls) >= expected_count:
            return

        await asyncio.sleep(interval)

    actual_count = len(fake_application.bot.send_message_calls)

    raise AssertionError(
        f"Expected at least {expected_count} send_message call(s), "
        f"but received {actual_count}."
    )


async def wait_for_send_attempts(
    send_count: list[int],
    expected_count: int,
    attempts: int = 100,
    interval: float = 0.01,
) -> None:
    """Wait until the fake send_message function has been called enough times."""
    for _ in range(attempts):
        if send_count[0] >= expected_count:
            return

        await asyncio.sleep(interval)

    raise AssertionError(
        f"Expected at least {expected_count} send attempt(s), "
        f"but received {send_count[0]}."
    )


async def cancel_task(task: asyncio.Task) -> None:
    """Cancel a running asyncio task and wait for its cancellation."""
    task.cancel()

    with suppress(asyncio.CancelledError):
        await task


async def run_loop_until_messages(
    fake_application,
    expected_count: int,
) -> None:
    """Run the scraping loop until the expected messages are sent."""
    task = asyncio.create_task(scrape_and_notify_loop(fake_application))

    try:
        await wait_for_send_count(
            fake_application=fake_application,
            expected_count=expected_count,
        )
    finally:
        await cancel_task(task)

def assert_standard_message_options(call: dict) -> None:
    """Verify common Telegram message options used by the bot."""
    assert call["parse_mode"] == "Markdown"
    assert call["disable_web_page_preview"] is True


def assert_single_reply(fake_update_obj) -> str:
    """Assert that exactly one reply was sent and return its text."""
    assert len(fake_update_obj.message.reply_text_calls) == 1

    message = fake_update_obj.message.reply_text_calls[0]["text"]

    assert isinstance(message, str)
    assert message.strip()

    return message


def assert_single_sent_message(fake_application) -> dict:
    """Assert that exactly one Telegram message was sent."""
    assert len(fake_application.bot.send_message_calls) == 1
    return fake_application.bot.send_message_calls[0]


def create_scrape_loop_patches(fake_notifications):
    """Return the common patches used by notification-loop tests."""
    return (
        patch(
            "bot.DB.get_pending_notifications",
            return_value=fake_notifications,
        ),
        patch("bot.DB.mark_notification_sent", return_value=True),
        patch("bot.DB.increment_notifications"),
        patch("bot.DB.update_user_count"),
        patch("bot.Scraper.scrape", return_value=[]),
        patch("bot.DB.increment_scrapes"),
        patch("bot.DB.get_all_grants", return_value=[]),
        patch("bot.config.CHECK_INTERVAL", 0),
    )


def create_fake_application_for_main():
    """Create a fake Telegram application used by main() tests."""
    fake_app = MagicMock()
    fake_app.initialize = AsyncMock()
    fake_app.start = AsyncMock()
    fake_app.stop = AsyncMock()

    fake_updater = MagicMock()
    fake_updater.running = False
    fake_updater.start = AsyncMock()
    fake_updater.stop = AsyncMock()
    fake_updater.start_polling = AsyncMock(
        side_effect=asyncio.CancelledError
    )

    fake_app.updater = fake_updater

    async def fake_aenter(self):
        return fake_app


    async def fake_aexit(self, exc_type, exc_value, traceback):
        return False


    fake_app.__aenter__ = fake_aenter
    fake_app.__aexit__ = fake_aexit

    return fake_app, fake_updater


class FakeApplicationBuilder:
    """Minimal Application.builder() replacement for main() tests."""

    def __init__(self, fake_app):
        self.fake_app = fake_app
        self.received_token = None

    def token(self, token: str):
        assert isinstance(token, str)
        assert token.strip()

        self.received_token = token
        return self

    def build(self):
        return self.fake_app


# ==========================================
# COMMAND HANDLER TESTS (T1-T4)
# ==========================================


def test_start_command_new_user(fake_update, fake_context):
    """T1: Test /start command with new user."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
    )

    fake_user = MagicMock()
    fake_user.chat_id = 123
    fake_user.username = "testuser"

    with patch(
        "bot.DB.add_or_get_user",
        return_value=fake_user,
    ) as mock_db:

        async def run_handler():
            await start(fake_update_obj, fake_context)

        run_async(run_handler())

        mock_db.assert_called_once_with(123, "testuser")

    message = assert_single_reply(fake_update_obj)

    assert "Hoşgeldiniz" in message
    assert "İtobot" in message


def test_start_command_existing_user(fake_update, fake_context):
    """T2: Test /start command with existing user."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
    )

    fake_user = MagicMock()
    fake_user.chat_id = 123
    fake_user.username = "testuser"

    with patch(
        "bot.DB.add_or_get_user",
        return_value=fake_user,
    ) as mock_db:

        async def run_handler():
            await start(fake_update_obj, fake_context)

        run_async(run_handler())

        mock_db.assert_called_once_with(123, "testuser")

    assert_single_reply(fake_update_obj)


def test_help_command(fake_update, fake_context):
    """T3: Test /help command."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
    )

    async def run_handler():
        await help_command(fake_update_obj, fake_context)

    run_async(run_handler())

    message = assert_single_reply(fake_update_obj)

    assert "İtobot Komutları" in message
    assert "Abone Ol" in message
    assert "Yardım" in message


def test_status_command(fake_update, fake_context):
    """T4: Test /status command."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
    )

    with (
        patch(
            "bot.DB.get_stats_dict",
            return_value={
                "users": 10,
                "scrapes": 5,
                "started": None,
                "last_scrape": None,
            },
        ),
        patch("bot.DB.is_subscribed", return_value=True),
    ):

        async def run_handler():
            await status(fake_update_obj, fake_context)

        run_async(run_handler())

    message = assert_single_reply(fake_update_obj)

    assert "İtobot Durumu" in message
    assert "10" in message
    assert "5" in message
    assert "Aktif" in message


# ==========================================
# BUTTON ROUTING TESTS (T5-T11)
# ==========================================


def test_subscribe_button(fake_update, fake_context):
    """T5: Test subscribe button."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
        text="📨 Abone Ol",
    )

    with patch(
        "bot.DB.subscribe_user",
        return_value="subscribed",
    ):

        async def run_handler():
            await handle_text(fake_update_obj, fake_context)

        run_async(run_handler())

    message = assert_single_reply(fake_update_obj)

    assert "Başarıyla Abone Oldunuz" in message


def test_unsubscribe_button(fake_update, fake_context):
    """T6: Test unsubscribe button."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
        text="❌ Abone Olmaktan Çık",
    )

    with patch(
        "bot.DB.unsubscribe_user",
        return_value="unsubscribed",
    ):

        async def run_handler():
            await handle_text(fake_update_obj, fake_context)

        run_async(run_handler())

    message = assert_single_reply(fake_update_obj)

    assert "Abonelikten Çıkıldı" in message


def test_status_button(fake_update, fake_context):
    """T7: Test status button."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
        text="🟢 Durum",
    )

    with (
        patch(
            "bot.DB.get_stats_dict",
            return_value={
                "users": 10,
                "scrapes": 5,
                "started": None,
                "last_scrape": None,
            },
        ),
        patch("bot.DB.is_subscribed", return_value=False),
    ):

        async def run_handler():
            await handle_text(fake_update_obj, fake_context)

        run_async(run_handler())

    assert_single_reply(fake_update_obj)


def test_stats_button(fake_update, fake_context):
    """T8: Test stats button."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
        text="📈 İstatistik",
    )

    with (
        patch(
            "bot.DB.get_user_stats",
            return_value={
                "scrapes": 3,
                "notifications": 7,
                "subscribed": True,
            },
        ),
        patch(
            "bot.DB.get_stats_dict",
            return_value={
                "users": 10,
                "scrapes": 5,
                "started": None,
                "last_scrape": None,
            },
        ),
    ):

        async def run_handler():
            await stats(fake_update_obj, fake_context)

        run_async(run_handler())

    message = assert_single_reply(fake_update_obj)

    assert "İstatistikler" in message
    assert "7" in message


def test_next_check_button(fake_update, fake_context):
    """T9: Test next check button."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
        text="⏱️ Sonraki Tarama",
    )

    import bot

    original_last_scrape_time = bot.last_scrape_time

    with patch("bot.config.CHECK_INTERVAL", 900):
        bot.last_scrape_time = bot.time.time() - 100

        try:

            async def run_handler():
                await next_check(fake_update_obj, fake_context)

            run_async(run_handler())

            message = assert_single_reply(fake_update_obj)

            assert "Sonraki Otomatik Tarama" in message
        finally:
            bot.last_scrape_time = original_last_scrape_time


def test_help_button(fake_update, fake_context):
    """T10: Test help button."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
        text="❓ Yardım",
    )

    async def run_handler():
        await handle_text(fake_update_obj, fake_context)

    run_async(run_handler())

    message = assert_single_reply(fake_update_obj)

    assert "İtobot Komutları" in message


def test_unknown_text(fake_update, fake_context):
    """T11: Test unknown text."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
        text="random text",
    )

    async def run_handler():
        await handle_text(fake_update_obj, fake_context)

    run_async(run_handler())

    assert len(fake_update_obj.message.reply_text_calls) == 0


# ==========================================
# NOTIFICATION BATCHING TESTS (T12-T13)
# ==========================================


def test_notification_batching_5(fake_application):
    """T12: Test batching with 5 notifications."""
    fake_notifications = [
        create_fake_notification(
            notification_id,
            123,
            f"Grant {notification_id}",
            f"http://example.com/{notification_id}",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )
        for notification_id in range(1, 6)
    ]

    mark_sent_calls = []

    def fake_mark_sent(notification_id):
        mark_sent_calls.append(notification_id)
        return True

    import bot

    original_last_scrape_time = bot.last_scrape_time

    patches = create_scrape_loop_patches(fake_notifications)

    with (
        patches[0],
        patch(
            "bot.DB.mark_notification_sent",
            side_effect=fake_mark_sent,
        ),
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        bot.last_scrape_time = bot.time.time() - 1000

        try:
            async def run_test():
                await run_loop_until_messages(
                    fake_application=fake_application,
                    expected_count=1,
                )

            run_async(run_test())

            call = assert_single_sent_message(fake_application)
            message = call["text"]

            assert len(mark_sent_calls) == 5
            assert "1." in message
            assert "5." in message

            assert_standard_message_options(call)
        finally:
            bot.last_scrape_time = original_last_scrape_time


def test_notification_batching_11(fake_application):
    """T13: Test batching with 11 notifications - 5/5/1 distribution."""
    fake_notifications = [
        create_fake_notification(
            notification_id,
            123,
            f"Grant {notification_id}",
            f"http://example.com/{notification_id}",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )
        for notification_id in range(1, 12)
    ]

    mark_sent_calls = []

    def fake_mark_sent(notification_id):
        mark_sent_calls.append(notification_id)
        return True

    import bot

    original_last_scrape_time = bot.last_scrape_time

    patches = create_scrape_loop_patches(fake_notifications)

    with (
        patches[0],
        patch(
            "bot.DB.mark_notification_sent",
            side_effect=fake_mark_sent,
        ),
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        bot.last_scrape_time = bot.time.time() - 1000

        try:
            async def run_test():
                await run_loop_until_messages(
                    fake_application=fake_application,
                    expected_count=3,
                )

            run_async(run_test())

            calls = fake_application.bot.send_message_calls

            assert len(calls) == 3
            assert len(mark_sent_calls) == 11

            for call in calls:
                assert_standard_message_options(call)

            first_message = calls[0]["text"]
            second_message = calls[1]["text"]
            third_message = calls[2]["text"]

            assert "1." in first_message
            assert "5." in first_message
            assert "Grant 1" in first_message
            assert "Grant 5" in first_message

            assert "1." in second_message
            assert "5." in second_message
            assert "Grant 6" in second_message
            assert "Grant 10" in second_message

            assert "1." in third_message
            assert "Grant 11" in third_message
        finally:
            bot.last_scrape_time = original_last_scrape_time


# ==========================================
# MARKDOWN EDGE CASE TESTS (T14-T16)
# ==========================================


def test_title_truncation(fake_application):
    """T14: Test title truncation at 80 characters."""
    long_title = "A" * 100

    fake_notifications = [
        create_fake_notification(
            1,
            123,
            long_title,
            "http://example.com/1",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )
    ]

    import bot

    original_last_scrape_time = bot.last_scrape_time

    patches = create_scrape_loop_patches(fake_notifications)

    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        bot.last_scrape_time = bot.time.time() - 1000

        try:
            async def run_test():
                await run_loop_until_messages(
                    fake_application=fake_application,
                    expected_count=1,
                )

            run_async(run_test())

            call = assert_single_sent_message(fake_application)
            message = call["text"]

            assert "..." in message

            expected_truncated_title = "A" * 77 + "..."
            assert expected_truncated_title in message

            assert_standard_message_options(call)
        finally:
            bot.last_scrape_time = original_last_scrape_time


def test_markdown_special_chars(fake_application):
    """T15: Test markdown special characters are preserved."""
    special_title = "Test*Grant_With`Special`Chars"

    fake_notifications = [
        create_fake_notification(
            1,
            123,
            special_title,
            "http://example.com/1",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )
    ]

    import bot

    original_last_scrape_time = bot.last_scrape_time

    patches = create_scrape_loop_patches(fake_notifications)

    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        bot.last_scrape_time = bot.time.time() - 1000

        try:
            async def run_test():
                await run_loop_until_messages(
                    fake_application=fake_application,
                    expected_count=1,
                )

            run_async(run_test())

            call = assert_single_sent_message(fake_application)
            message = call["text"]

            assert "*" in message
            assert "_" in message
            assert "`" in message

            assert_standard_message_options(call)
        finally:
            bot.last_scrape_time = original_last_scrape_time


def test_missing_optional_fields(fake_application):
    """T16: Test missing URL and date fields."""
    fake_notifications = [
        create_fake_notification(
            1,
            123,
            "Grant 1",
            None,
            None,
            None,
        )
    ]

    import bot

    original_last_scrape_time = bot.last_scrape_time

    patches = create_scrape_loop_patches(fake_notifications)

    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        bot.last_scrape_time = bot.time.time() - 1000

        try:
            async def run_test():
                await run_loop_until_messages(
                    fake_application=fake_application,
                    expected_count=1,
                )

            run_async(run_test())

            call = assert_single_sent_message(fake_application)
            message = call["text"]

            assert "🔗" not in message
            assert "📅" not in message

            assert_standard_message_options(call)
        finally:
            bot.last_scrape_time = original_last_scrape_time


# ==========================================
# FAILURE/DUPLICATE TESTS (T17-T20)
# ==========================================


def test_send_failure_behavior(fake_application):
    """T17: Test send failure - notifications remain pending, loop continues."""
    fake_notifications = [
        create_fake_notification(
            1,
            123,
            "Grant 1",
            "http://example.com/1",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )
    ]

    mark_sent_calls = []

    def fake_mark_sent(notification_id):
        mark_sent_calls.append(notification_id)
        return True

    send_count = [0]

    async def fake_send_message(*args, **kwargs):
        send_count[0] += 1

        if send_count[0] == 1:
            raise Exception("Telegram API error")

        return MagicMock()

    fake_application.bot.send_message = fake_send_message

    import bot

    original_last_scrape_time = bot.last_scrape_time

    patches = create_scrape_loop_patches(fake_notifications)

    with (
        patches[0],
        patch(
            "bot.DB.mark_notification_sent",
            side_effect=fake_mark_sent,
        ),
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        bot.last_scrape_time = bot.time.time() - 1000

        try:
            async def run_test():
                task = asyncio.create_task(
                    scrape_and_notify_loop(fake_application)
                )

                try:
                    await wait_for_send_attempts(
                        send_count=send_count,
                        expected_count=1,
                    )
                finally:
                    await cancel_task(task)

            run_async(run_test())

            assert send_count[0] >= 1
            assert len(mark_sent_calls) == 0
        finally:
            bot.last_scrape_time = original_last_scrape_time


def test_duplicate_subscribe(fake_update, fake_context):
    """T18: Test duplicate subscribe command."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
        text="📨 Abone Ol",
    )

    with patch(
        "bot.DB.subscribe_user",
        return_value="already_subscribed",
    ):

        async def run_handler():
            await handle_text(fake_update_obj, fake_context)

        run_async(run_handler())

    message = assert_single_reply(fake_update_obj)

    assert "Zaten Abonesiniz" in message


def test_duplicate_unsubscribe(fake_update, fake_context):
    """T19: Test duplicate unsubscribe command."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
        text="❌ Abone Olmaktan Çık",
    )

    with patch(
        "bot.DB.unsubscribe_user",
        return_value="already_unsubscribed",
    ):

        async def run_handler():
            await handle_text(fake_update_obj, fake_context)

        run_async(run_handler())

    message = assert_single_reply(fake_update_obj)

    assert "Zaten Abone Değilsiniz" in message


def test_polling_configuration():
    """T20: Test polling configuration parameters."""
    fake_app, fake_updater = create_fake_application_for_main()
    builder = FakeApplicationBuilder(fake_app)

    start_polling_calls = []

    async def fake_start_polling(*args, **kwargs):
        start_polling_calls.append((args, kwargs))
        raise asyncio.CancelledError()

    fake_updater.start_polling = fake_start_polling

    async def fake_scrape_loop(app):
        return None

    with (
        patch(
            "bot.Application.builder",
            return_value=builder,
        ),
        patch("bot.init_db"),
        patch("bot.DB.get_or_create_stats"),
        patch("bot.DB.reset_started_at"),
        patch("threading.Thread"),
        patch("signal.signal"),
        patch(
            "bot.scrape_and_notify_loop",
            side_effect=fake_scrape_loop,
        ),
    ):
        with suppress(asyncio.CancelledError):
            run_async(main())

    assert builder.received_token is not None
    assert builder.received_token.strip()

    assert len(start_polling_calls) == 1

    _, kwargs = start_polling_calls[0]

    assert kwargs["allowed_updates"] == Update.ALL_TYPES
    assert kwargs["timeout"] == 30
    assert kwargs["drop_pending_updates"] is True


# ==========================================
# APPLICATION-LEVEL REGISTRATION TESTS (T21-T23)
# ==========================================


def test_application_handler_registration():
    """T21: Verify exact command and text handler mappings."""
    fake_app, fake_updater = create_fake_application_for_main()
    builder = FakeApplicationBuilder(fake_app)

    registered_handlers = []

    def fake_add_handler(handler):
        registered_handlers.append(handler)

    fake_app.add_handler = fake_add_handler

    async def fake_scrape_loop(app):
        return None

    with (
        patch(
            "bot.Application.builder",
            return_value=builder,
        ),
        patch("bot.init_db"),
        patch("bot.DB.get_or_create_stats"),
        patch("bot.DB.reset_started_at"),
        patch("threading.Thread"),
        patch("signal.signal"),
        patch(
            "bot.scrape_and_notify_loop",
            side_effect=fake_scrape_loop,
        ),
    ):
        with suppress(asyncio.CancelledError):
            run_async(main())

    assert len(registered_handlers) == 4

    command_handlers = [
        handler
        for handler in registered_handlers
        if isinstance(handler, CommandHandler)
    ]

    message_handlers = [
        handler
        for handler in registered_handlers
        if isinstance(handler, MessageHandler)
    ]

    assert len(command_handlers) == 3
    assert len(message_handlers) == 1

    mapping = {}

    for handler in command_handlers:
        for command in handler.commands:
            mapping[command] = handler.callback

    assert mapping == {
        "start": start,
        "help": help_command,
        "status": status,
    }

    assert message_handlers[0].callback is handle_text


def test_start_command_keyboard(fake_update, fake_context):
    """T22: Verify /start sends ReplyKeyboardMarkup with correct buttons."""
    fake_update_obj = fake_update(
        chat_id=123,
        username="testuser",
    )

    fake_user = MagicMock()
    fake_user.chat_id = 123
    fake_user.username = "testuser"

    with patch(
        "bot.DB.add_or_get_user",
        return_value=fake_user,
    ):

        async def run_handler():
            await start(fake_update_obj, fake_context)

        run_async(run_handler())

    assert len(fake_update_obj.message.reply_text_calls) == 1

    call = fake_update_obj.message.reply_text_calls[0]
    reply_markup = call["reply_markup"]

    assert reply_markup is not None

    keyboard = reply_markup.keyboard

    assert len(keyboard) == 3
    assert len(keyboard[0]) == 2
    assert len(keyboard[1]) == 2
    assert len(keyboard[2]) == 2

    button_texts_row0 = [button.text for button in keyboard[0]]
    button_texts_row1 = [button.text for button in keyboard[1]]
    button_texts_row2 = [button.text for button in keyboard[2]]

    assert button_texts_row0 == [
        "📨 Abone Ol",
        "❌ Abone Olmaktan Çık",
    ]

    assert button_texts_row1 == [
        "⏱️ Sonraki Tarama",
        "📈 İstatistik",
    ]

    assert button_texts_row2 == [
        "🟢 Durum",
        "❓ Yardım",
    ]

    assert reply_markup.resize_keyboard is True
    assert reply_markup.one_time_keyboard is False


def test_send_failure_then_success_second_cycle(fake_application):
    """T23: Verify loop survives first-cycle send failure and succeeds later."""
    fake_notifications = [
        create_fake_notification(
            1,
            123,
            "Grant 1",
            "http://example.com/1",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )
    ]

    mark_sent_calls = []

    def fake_mark_sent(notification_id):
        mark_sent_calls.append(notification_id)
        return True

    send_count = [0]
    second_send_kwargs = {}

    async def fake_send_message(*args, **kwargs):
        send_count[0] += 1

        if send_count[0] == 1:
            raise Exception("Telegram API error")

        second_send_kwargs.update(kwargs)
        return MagicMock()

    fake_application.bot.send_message = fake_send_message

    import bot

    original_last_scrape_time = bot.last_scrape_time

    patches = create_scrape_loop_patches(fake_notifications)

    with (
        patches[0],
        patch(
            "bot.DB.mark_notification_sent",
            side_effect=fake_mark_sent,
        ),
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        bot.last_scrape_time = bot.time.time() - 1000

        try:
            async def run_test():
                task = asyncio.create_task(
                    scrape_and_notify_loop(fake_application)
                )

                try:
                    await wait_for_send_attempts(
                        send_count=send_count,
                        expected_count=2,
                        attempts=600,
                    )
                finally:
                    await cancel_task(task)

            run_async(run_test())

            assert send_count[0] >= 2
            assert len(mark_sent_calls) == 1

            assert second_send_kwargs["parse_mode"] == "Markdown"
            assert second_send_kwargs["disable_web_page_preview"] is True
        finally:
            bot.last_scrape_time = original_last_scrape_time