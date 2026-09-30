from http.server import BaseHTTPRequestHandler
import json, asyncio, requests

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, InlineQueryHandler, filters,
)

from bot import handlers
from bot.config import BOT_TOKEN, WEBHOOK_SECRET, WEBHOOK_URL

_application = None


def get_app():
    global _application
    if _application is None:
        _application = Application.builder().token(BOT_TOKEN).build()

        _application.add_handler(CommandHandler("start",         handlers.start))
        _application.add_handler(CommandHandler("help",          handlers.help_cmd))
        _application.add_handler(CommandHandler("about",         handlers.about_cmd))
        _application.add_handler(CommandHandler("cancel",        handlers.cancel_cmd))
        _application.add_handler(CommandHandler("files",         handlers.files_cmd))
        _application.add_handler(CommandHandler("settings",      handlers.settings_cmd))
        _application.add_handler(CommandHandler("clone",         handlers.clone_cmd))
        _application.add_handler(CommandHandler("genlink",       handlers.genlink_cmd))
        _application.add_handler(CommandHandler("custom_batch",  handlers.custom_batch_cmd))
        _application.add_handler(CommandHandler("mylinks",       handlers.mylinks_cmd))
        _application.add_handler(CommandHandler("mybatches",     handlers.mybatches_cmd))

        _application.add_handler(CommandHandler("broadcast",     handlers.broadcast_cmd))
        _application.add_handler(CommandHandler("ban",           handlers.ban_cmd))
        _application.add_handler(CommandHandler("unban",         handlers.unban_cmd))
        _application.add_handler(CommandHandler("admin_stats",   handlers.admin_stats))

        _application.add_handler(CallbackQueryHandler(handlers.on_callback))
        _application.add_handler(InlineQueryHandler(handlers.inline_query))
        _application.add_handler(MessageHandler(
            filters.ALL & ~filters.COMMAND, handlers.handle_any,
        ))
    return _application


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
            self.send_response(403); self.end_headers(); return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except Exception:
            self.send_response(400); self.end_headers(); return

        async def process():
            app = get_app()
            async with app:
                update = Update.de_json(data, app.bot)
                await app.process_update(update)

        try:
            asyncio.run(process())
        except Exception as e:
            print("update err:", e)

        self.send_response(200); self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        url = f"{WEBHOOK_URL}/api/webhook"
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            data={"url": url, "secret_token": WEBHOOK_SECRET},
            timeout=10,
        )
        self.send_response(200); self.end_headers()
        self.wfile.write(r.text.encode())