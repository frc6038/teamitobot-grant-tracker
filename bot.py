"""
İtobot - FIRST Robotics Grant Tracker
Türkiye FRC takımları için otomatik hibe takip botu
"""

import asyncio
import signal
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import config
from database import init_db, DB
from scraper import Scraper
from smtp_notifier import build_smtp_notifier

from adapters.telegram.renderer import (
    GrantNotification,
    group_by_message_length,
    render_group,
)

import pytz
from datetime import datetime

TURKEY_TZ = pytz.timezone("Europe/Istanbul")

# Global state
last_scrape_time = time.time()
smtp_notifier = build_smtp_notifier(config)

def persist_new_grants_and_notifications(new_grants):
    """
    Persist newly discovered grants and fan out notification intents
    to the current subscribed-user snapshot.

    Each DB operation commits independently. This intentionally preserves
    the legacy behavior where a fan-out failure can leave a grant committed
    while some recipients never receive notification intents.
    """

    if not new_grants:
        return

    subscribed_users = DB.get_subscribed_users()

    for grant in new_grants:
        grant_id = DB.add_grant(
            title=grant["title"],
            start_date=grant["start_date"],
            end_date=grant["end_date"],
            url=grant["url"],
        )

        for chat_id in subscribed_users:
            DB.create_pending_notification(
                chat_id,
                grant_id,
            )


async def send_grant_email_best_effort(grant):
    """Send optional email without affecting the Telegram delivery path."""
    if smtp_notifier is None:
        return False

    try:
        return await asyncio.to_thread(smtp_notifier.send_grant, grant)
    except Exception as error:
        # Defensive boundary for injected/custom notifiers. Never log payloads or
        # credentials because provider errors can contain sensitive context.
        print(
            f"❌ SMTP grant notification failed "
            f"({type(error).__name__})"
        )
        return False


# ==========================================
# HTTP HEALTH CHECK (For Render)
# ==========================================

class HealthHandler(BaseHTTPRequestHandler):
    """Health check handler"""

    def _send_health_response(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self._send_health_response()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()

    def do_POST(self):
        self._send_health_response()

    def log_message(self, format, *args):
        pass


def start_health_server():
    """Start health check server"""
    try:
        server = HTTPServer(("0.0.0.0", config.PORT), HealthHandler)

        print(f"🟢 Health check server started on port {config.PORT}")
        server.serve_forever()

    except Exception as e:
        print(f"❌ Health server error: {e}")


# ==========================================
# TELEGRAM BOT HANDLERS
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - User registration"""

    chat_id = update.effective_chat.id
    username = update.effective_user.username

    DB.add_or_get_user(chat_id, username)

    keyboard = [
        ["📨 Abone Ol", "❌ Abone Olmaktan Çık"],
        ["⏱️ Sonraki Tarama", "📈 İstatistik"],
        ["🟢 Durum", "❓ Yardım"],
    ]

    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

    message = (
        "🤖 *İtobot Telegram Hibe Takipçisi'ne Hoşgeldiniz!*\n\n"
        "FIRST Robotics Competition hibe fırsatlarını otomatik olarak takip etmek için "
        "bu bot 7/24 kesintisiz çalışmaktadır.\n\n"
        "Yeni bir hibe duyurusu yapıldığında anında bildirim alacaksınız.\n\n"
        "Aşağıdaki butonları kullanarak başlayın! 👇"
    )

    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

    print(f"✅ User {chat_id} started bot")


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscribe command"""

    chat_id = update.effective_chat.id

    result = DB.subscribe_user(chat_id)

    if result == "subscribed":
        message = (
            "✅ *Başarıyla Abone Oldunuz!*\n\n"
            "Artık FIRST hibe duyurularını anında alacaksınız.\n"
            "Bildirimleri durdurmak için *❌ Abone Olmaktan Çık* "
            "butonuna tıklayın."
        )

        print(f"✅ User {chat_id} subscribed")

    elif result == "already_subscribed":
        message = (
            "ℹ️ *Zaten Abonesiniz!*\n\n"
            "Yeni hibe duyurularını almaya devam edeceksiniz."
        )

    else:
        message = (
            "❌ Kullanıcı kaydı bulunamadı.\n\n"
            "Lütfen önce /start komutunu gönderin."
        )

    await update.message.reply_text(
        message,
        parse_mode="Markdown"
    )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unsubscribe command"""

    chat_id = update.effective_chat.id

    result = DB.unsubscribe_user(chat_id)

    if result == "unsubscribed":
        message = (
            "✅ *Abonelikten Çıkıldı*\n\n"
            "Artık hibe bildirimlerini almayacaksınız.\n"
            "Tekrar bildirim almak için *📨 Abone Ol* "
            "butonuna tıklayabilirsiniz."
        )

        print(f"✅ User {chat_id} unsubscribed")

    elif result == "already_unsubscribed":
        message = (
            "ℹ️ *Zaten Abone Değilsiniz!*\n\n"
            "Şu anda hibe bildirimi almıyorsunuz."
        )

    else:
        message = (
            "❌ Kullanıcı kaydı bulunamadı.\n\n"
            "Lütfen önce /start komutunu gönderin."
        )

    await update.message.reply_text(
        message,
        parse_mode="Markdown"
    )


def format_duration(delta_seconds: float) -> str:
    """Format a duration in seconds as a human-readable Turkish string"""

    total_seconds = int(max(0, delta_seconds))

    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    parts = []

    if days:
        parts.append(f"{days} gün")

    if hours or days:
        parts.append(f"{hours} saat")

    parts.append(f"{minutes} dk")

    return " ".join(parts)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command - Show bot status."""

    chat_id = update.effective_chat.id

    system_stats = DB.get_stats_dict()
    is_subscribed = DB.is_subscribed(chat_id)

    message = (
        "🟢 *İtobot Durumu*\n\n"
        f"👥 *Aktif Kullanıcı:* `{system_stats['users']}` kişi\n"
        f"🔍 *Toplam Başarılı Tarama:* `{system_stats['scrapes']}` kez\n"
        f"🔔 *Abonelik Durumu:* "
        f"{'✅ Aktif' if is_subscribed else '❌ Pasif'}\n"
        "⚙️ *Sistem:* 🟢 Çalışıyor"
    )

    await update.message.reply_text(
        message,
        parse_mode="Markdown"
    )


async def next_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle next check time request"""

    global last_scrape_time

    current_time = time.time()
    elapsed = current_time - last_scrape_time

    remaining = max(0, config.CHECK_INTERVAL - elapsed)

    mins, secs = divmod(int(remaining), 60)

    interval_minutes = config.CHECK_INTERVAL // 60

    if interval_minutes >= 1:
        interval_text = f"{interval_minutes} dakika"
    else:
        interval_text = f"{config.CHECK_INTERVAL} saniye"

    message = (
        "⏳ *Bir Sonraki Otomatik Tarama*\n\n"
        f"⏱️ *Kalan Süre:* `{mins:02d} dk {secs:02d} sn`\n\n"
        f"💡 *Bilgi:* Site {interval_text}da bir "
        "taranıp yeni hibe var mı kontrol ediliyor."
    )

    await update.message.reply_text(
        message,
        parse_mode="Markdown"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle personal statistics."""

    chat_id = update.effective_chat.id

    user_stats = DB.get_user_stats(chat_id)
    system_stats = DB.get_stats_dict()

    # Bot çalışma süresini hesapla
    uptime_text = "Bilinmiyor"

    if system_stats["started"]:
        started_at = system_stats["started"]

        if started_at.tzinfo is None:
            started_at = TURKEY_TZ.localize(started_at)

        uptime_seconds = (
            datetime.now(TURKEY_TZ) - started_at
        ).total_seconds()

        uptime_text = format_duration(uptime_seconds)

    # Son tarama zamanını Türkiye saatine çevir
    last_scrape_text = "Henüz tarama yapılmadı"

    if system_stats["last_scrape"]:
        last_scrape = system_stats["last_scrape"]

        # Veritabanındaki zaman UTC ise Türkiye saatine çevir
        if last_scrape.tzinfo is None:
            last_scrape = pytz.utc.localize(last_scrape)

        last_scrape = last_scrape.astimezone(TURKEY_TZ)

        last_scrape_text = last_scrape.strftime(
            "%d.%m.%Y %H:%M:%S"
        )

    message = (
        "📊 *İstatistikler*\n\n"
        "👤 *Kişisel İstatistikleriniz*\n"
        f"📨 Aldığınız Hibe Bildirimi: "
        f"`{user_stats['notifications']}` adet\n\n"
        "🤖 *Bot İstatistikleri*\n"
        f"🕐 Son Tarama: `{last_scrape_text}`\n"
        f"⏱️ Çalışma Süresi: `{uptime_text}`"
    )

    await update.message.reply_text(
        message,
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help command"""

    message = (
        "🤖 *İtobot Komutları:*\n\n"
        "🔹 *📨 Abone Ol* - Yeni hibe bildirimlerini almaya başla\n"
        "🔹 *❌ Abone Olmaktan Çık* - Bildirimler almayı durdur\n"
        "🔹 *⏱️ Sonraki Tarama* - Bir sonraki site kontrolüne kalan süreyi göster\n"
        "🔹 *📈 İstatistik* - Kişisel istatistiklerini göster\n"
        "🔹 *🟢 Durum* - Botun genel çalışma durumunu göster\n"
        "🔹 *❓ Yardım* - Bu yardım menüsünü görüntüle\n\n"
        "💡 Herhangi bir sorunla karşılaşırsan lütfen bot yöneticisine bildir."
    )

    await update.message.reply_text(
        message,
        parse_mode="Markdown"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages from buttons"""

    text = update.message.text

    if text == "📨 Abone Ol":
        await subscribe(update, context)

    elif text == "❌ Abone Olmaktan Çık":
        await unsubscribe(update, context)

    elif text == "⏱️ Sonraki Tarama":
        await next_check(update, context)

    elif text == "📈 İstatistik":
        await stats(update, context)

    elif text == "🟢 Durum":
        await status(update, context)

    elif text == "❓ Yardım":
        await help_command(update, context)


# ==========================================
# GRANT SCRAPING & NOTIFICATION LOOP
# ==========================================

async def scrape_and_notify_loop(application):
    """Main grant scraping and notification loop"""

    global last_scrape_time

    last_scrape_time = time.time()

    while True:
        try:
            current_time = time.time()

            if current_time - last_scrape_time >= config.CHECK_INTERVAL:

                print(
                    f"🔍 Starting grant scrape cycle at "
                    f"{datetime.now(TURKEY_TZ).strftime('%H:%M:%S')}"
                )

                # ==========================================
                # SCRAPE CURRENT GRANTS
                # ==========================================

                current_grants = Scraper.scrape()

                if current_grants is None:
                    print(
                        "⚠ Scrape başarısız oldu. "
                        "Bu tarama istatistiklere eklenmeyecek."
                    )
                else:
                    # Sadece başarıyla tamamlanan taramayı say
                    DB.increment_scrapes()

                # Tarama başarılı veya başarısız olsun,
                # bir sonraki tarama için süreyi yeniden başlat.
                last_scrape_time = current_time

                new_grants = []

                if current_grants:

                    known_grants = {
                        (
                            grant.title,
                            grant.start_date,
                            grant.end_date
                        )
                        for grant in DB.get_all_grants()
                        if grant.title
                    }

                    new_grants = [
                        grant
                        for grant in current_grants
                        if (
                            grant["title"],
                            grant["start_date"],
                            grant["end_date"]
                        ) not in known_grants
                    ]

                    # ==========================================
                    # CREATE NEW GRANTS + PENDING NOTIFICATIONS
                    # ==========================================

                    if new_grants:

                        print(
                            f"🚨 Found {len(new_grants)} new grants!"
                        )

                        persist_new_grants_and_notifications(new_grants)

                    else:

                        print("✅ No new grants found")

                # ==========================================
                # SEND PENDING NOTIFICATIONS
                # ==========================================

                pending_notifications = DB.get_pending_notifications()

                if pending_notifications:

                    notifications_by_user = {}

                    for notification in pending_notifications:

                        chat_id = notification["chat_id"]

                        if chat_id not in notifications_by_user:
                            notifications_by_user[chat_id] = []

                        notifications_by_user[chat_id].append(
                            notification
                        )

                    for chat_id, notifications in notifications_by_user.items():

                        for start_index in range(
                            0,
                            len(notifications),
                            5
                        ):

                            batch = notifications[
                                start_index:start_index + 5
                            ]

                            grant_notifications = [
                                GrantNotification(
                                    title=notification["grant_title"],
                                    url=notification["grant_url"],
                                    start_date=notification["start_date"],
                                    end_date=notification["end_date"],
                                )
                                for notification in batch
                            ]

                            groups = group_by_message_length(
                                grant_notifications
                            )

                            batch_succeeded = True

                            logical_cursor = 0

                            for group_index, group in enumerate(groups):

                                text = render_group(
                                    group,
                                    start_logical_index=logical_cursor + 1,
                                    include_header=(group_index == 0),
                                )

                                logical_cursor += len(group)

                                start = sum(len(g) for g in groups[:group_index])
                                covered_notifications = batch[
                                    start:start + len(group)
                                ]

                                try:

                                    await application.bot.send_message(
                                        chat_id=chat_id,
                                        text=text,
                                        parse_mode="Markdown",
                                        disable_web_page_preview=True,
                                    )

                                    for notification in covered_notifications:

                                        if DB.mark_notification_sent(
                                            notification["notification_id"]
                                        ):
                                            DB.increment_notifications()

                                    print(
                                        f"✅ Sent {len(group)} notification(s) "
                                        f"to user {chat_id}"
                                    )

                                except Exception as e:

                                    batch_succeeded = False

                                    print(
                                        f"❌ Error sending notification to "
                                        f"{chat_id}: {e}"
                                    )

                                    break

                            if not batch_succeeded:
                                continue

                # Email is an independent, best-effort fan-out. Running it after
                # Telegram preserves the existing delivery path when SMTP fails.
                for grant in new_grants:
                    await send_grant_email_best_effort(grant)

                # ==========================================
                # UPDATE USER COUNT
                # ==========================================

                DB.update_user_count()

            await asyncio.sleep(2)

        except asyncio.CancelledError:

            print("🛑 Scrape loop cancelled.")

            raise

        except Exception as e:

            print(f"❌ Scrape loop error: {e}")

            await asyncio.sleep(10)


# ==========================================
# MAIN BOT APPLICATION
# ==========================================

async def main():
    """Main bot function"""

    print("=" * 60)
    print("🤖 İtobot FIRST Robotics Hibe Takipçisi Başlatılıyor...")
    print("=" * 60)

    # ==========================================
    # DATABASE
    # ==========================================

    init_db()

    # ==========================================
    # CREATE TELEGRAM APPLICATION
    # ==========================================

    app = Application.builder().token(config.BOT_TOKEN).build()

    # ==========================================
    # HANDLERS
    # ==========================================

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    # ==========================================
    # HEALTH SERVER
    # ==========================================

    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True
    )

    health_thread.start()

    # ==========================================
    # INITIALIZE STATS
    # ==========================================

    DB.get_or_create_stats()
    DB.reset_started_at()

    print("✅ Bot initialized successfully!")

    print(
        f"⏰ Scrape interval: "
        f"{config.CHECK_INTERVAL} seconds "
        f"({config.CHECK_INTERVAL // 60} minutes)"
    )

    print("🟢 Bot is ready! Waiting for users...")
    print("=" * 60)

    # ==========================================
    # GRACEFUL SHUTDOWN EVENT
    # ==========================================

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    def handle_shutdown(signum, frame):
        """Handle SIGTERM/SIGINT."""

        signal_name = signal.Signals(signum).name

        print(
            f"\n🛑 Received {signal_name}. "
            f"Starting graceful shutdown..."
        )

        loop.call_soon_threadsafe(stop_event.set)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # ==========================================
    # START APPLICATION
    # ==========================================

    scrape_task = None

    async with app:

        try:

            await app.initialize()
            await app.start()

            scrape_task = asyncio.create_task(
                scrape_and_notify_loop(app)
            )

            await app.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                timeout=30,
                drop_pending_updates=True
            )

            print(
                "🤖 Bot polling started, "
                "listening for commands..."
            )

            await stop_event.wait()

        except asyncio.CancelledError:
            print("🛑 Main task cancelled.")
            raise

        except Exception as error:
            print(
                f"❌ Main application error: {type(error).__name__}"
            )
            raise

        finally:

            print("\n🛑 Stopping bot gracefully...")

            try:

                if app.updater.running:

                    print("⏹️ Stopping Telegram polling...")

                    await app.updater.stop()

            except Exception as e:

                print(f"❌ Error stopping polling: {e}")

            if scrape_task:

                print("⏹️ Stopping scraper task...")

                scrape_task.cancel()

                try:

                    await scrape_task

                except asyncio.CancelledError:

                    pass

            try:

                if app.running:

                    print("⏹️ Stopping Telegram application...")

                    await app.stop()

            except Exception as e:

                print(f"❌ Error stopping application: {e}")

            print("✅ Bot stopped gracefully.")


# ==========================================
# ENTRY POINT
# ==========================================

if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by keyboard interrupt.")

    except Exception as error:
        print(
            f"❌ Fatal error: {type(error).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(1)
