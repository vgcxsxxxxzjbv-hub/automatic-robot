import secrets
import base64
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InlineQueryResultArticle, InputTextMessageContent,
)
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import db
from .config import (
    STORAGE_CHANNEL, BASE_URL, ADMIN_IDS,
    OWNER_LINK, UPDATES_LINK, SUPPORT_LINK, VERSION,
    FORCE_SUB_CHANNELS, FORCE_SUB_USERNAMES,
    START_PHOTO,
)


def make_token(n=8):
    raw = secrets.token_bytes(6)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")[:n]


def unique_token():
    for _ in range(6):
        t = make_token(8)
        if not db.get_link(t):
            return t
    return make_token(20)


PENDING_GENLINK = {}
BATCH_STATE = {}


def is_admin(uid):
    return uid in ADMIN_IDS


async def check_subscribed(bot, user_id):
    if not FORCE_SUB_CHANNELS:
        return ("ok", [])
    missing = []
    for ch in FORCE_SUB_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status == ChatMemberStatus.BANNED:
                return ("banned", [ch])
            if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.RESTRICTED):
                missing.append(ch)
        except TelegramError:
            continue
    if missing:
        return ("join", missing)
    return ("ok", [])


def build_join_kb():
    rows = []
    if FORCE_SUB_USERNAMES:
        for u in FORCE_SUB_USERNAMES:
            rows.append([InlineKeyboardButton(f"📢 Join @{u} 📢", url=f"https://t.me/{u}")])
    else:
        for ch in FORCE_SUB_CHANNELS:
            if isinstance(ch, int):
                short = str(ch).replace("-100", "")
                url = f"https://t.me/c/{short}"
            else:
                url = f"https://t.me/{str(ch).lstrip('@')}"
            rows.append([InlineKeyboardButton("📢 Join Channel 📢", url=url)])
    rows.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)


async def enforce_subscription(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        return False
    if is_admin(u.id):
        return True
    status, _ = await check_subscribed(ctx.bot, u.id)
    if status == "banned":
        await update.effective_message.reply_text("🚫 You are banned from using this bot.")
        return False
    if status == "join":
        text = (
            f"<b>Hello {u.mention_html()}</b>\n\n"
            "You need to join our channel(s) to use me.\n\n"
            "Kindly join, then press <b>I've Joined</b>."
        )
        await update.effective_message.reply_text(
            text=text, reply_markup=build_join_kb(),
            parse_mode="HTML", quote=True,
        )
        return False
    return True


def main_menu(user=None):
    kb = [
        [InlineKeyboardButton("🔗 GENERATE LINK", callback_data="genlink_info")],
        [InlineKeyboardButton("📦 CUSTOM BATCH",  callback_data="batch_info")],
        [InlineKeyboardButton("HELP", callback_data="help"),
         InlineKeyboardButton("ABOUT", callback_data="about")],
        [InlineKeyboardButton("📁 MY FILES", callback_data="myfiles"),
         InlineKeyboardButton("🔗 MY LINKS", callback_data="mylinks")],
        [InlineKeyboardButton("📦 MY BATCHES", callback_data="mybatches")],
        [InlineKeyboardButton("🖼 CREATE MY OWN CLONE (SOON)", callback_data="clone")],
        [InlineKeyboardButton("📢 UPDATE CHANNEL", url=UPDATES_LINK or "https://t.me/")],
    ]
    return InlineKeyboardMarkup(kb)


def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("BACK", callback_data="menu")]])


def batch_kb(bid, paused=False):
    rows = []
    if paused:
        rows.append([InlineKeyboardButton("RESUME", callback_data=f"batch:resume:{bid}")])
    else:
        rows.append([InlineKeyboardButton("PAUSE",  callback_data=f"batch:pause:{bid}")])
    rows.append([InlineKeyboardButton("GENERATE LINK", callback_data=f"batch:gen:{bid}")])
    rows.append([InlineKeyboardButton("CANCEL",        callback_data=f"batch:cancel:{bid}")])
    return InlineKeyboardMarkup(rows)


CLONE_SOON_TEXT = (
    "🖼 <b>Clone Feature</b>\n\n"
    "⚡ <b>Coming soon in new update</b>\n\n"
    "This feature is temporarily disabled. It will be enabled "
    "in a future release.\n\n"
    "Stay tuned for updates!"
)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.upsert_user(u.id, u.username, u.first_name)
    if db.is_banned(u.id):
        await update.message.reply_text("🚫 You are banned.")
        return
    if ctx.args:
        if not await enforce_subscription(update, ctx):
            return
        token = ctx.args[0]
        b = db.get_batch_by_token(token)
        if b:
            db.inc_batch_views(token)
            await _deliver_batch(update, ctx, b)
            return
        row = db.get_link(token)
        if row:
            db.inc_link_views(token)
            await _deliver_stored(update, ctx, row)
            return
        await update.message.reply_text("❌ Link expired or invalid.")
        return
    if not await enforce_subscription(update, ctx):
        return
    text = (
        f"Hello <b>{u.first_name}</b> ✨\n\n"
        "I am a permanent file store bot and users can access "
        "stored messages by using a shareable link given by me.\n\n"
        "To know more click help button."
    )
    kb = main_menu(u)
    if START_PHOTO:
        try:
            is_url = START_PHOTO.startswith("http://") or START_PHOTO.startswith("https://")
            is_file_id = (not is_url) and (not START_PHOTO.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")))
            if is_url or is_file_id:
                await update.message.reply_photo(photo=START_PHOTO, caption=text,
                                                 reply_markup=kb, parse_mode="HTML")
            else:
                with open(START_PHOTO, "rb") as fh:
                    await update.message.reply_photo(photo=fh, caption=text,
                                                     reply_markup=kb, parse_mode="HTML")
            return
        except Exception as e:
            print("start photo err:", e)
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def _deliver_stored(update, ctx, row):
    try:
        await ctx.bot.copy_message(
            chat_id=update.effective_chat.id,
            from_chat_id=STORAGE_CHANNEL,
            message_id=row["message_id"],
        )
        url = f"https://t.me/{ctx.bot.username}?start={row['token']}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💾 SAVE THIS", url=url)],
            [InlineKeyboardButton("📢 MAKE YOUR OWN", url=f"https://t.me/{ctx.bot.username}")],
        ])
        await update.message.reply_text(
            f"<i>Shared via</i> <a href='https://t.me/{ctx.bot.username}'>"
            f"@{ctx.bot.username}</a>\n"
            f"<i>Views:</i> {row.get('views', 0) + 1}",
            reply_markup=kb, parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Delivery failed: {e}")


async def _deliver_batch(update, ctx, b):
    try:
        for m in b["messages"]:
            await ctx.bot.copy_message(
                chat_id=update.effective_chat.id,
                from_chat_id=STORAGE_CHANNEL,
                message_id=m["message_id"],
            )
            await asyncio.sleep(0.15)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 MAKE YOUR OWN", url=f"https://t.me/{ctx.bot.username}")],
        ])
        await update.message.reply_text(
            f"<i>Batch of {len(b['messages'])} · Views: {b.get('views', 0) + 1}</i>\n"
            f"<i>Shared via</i> <a href='https://t.me/{ctx.bot.username}'>"
            f"@{ctx.bot.username}</a>",
            reply_markup=kb, parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Delivery failed: {e}")


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.callback_query:
        if not await enforce_subscription(update, ctx):
            return
    user = update.effective_user
    is_admin_user = is_admin(user.id)
    text = (
        "I am a permanent file store bot. You can use my commands and "
        "you can access stored files by using shareable link given by me.\n\n"
        "📚 <b>Available Commands:</b>\n"
        "➔ /start - check i am alive.\n"
        "➔ /genlink - To store a single message or file.\n"
        "➔ /batch - To store multiple messages from a channel.\n"
        "➔ /custom_batch - To store multiple random messages.\n"
        "➔ /genlink_2 - To store message that can be accessed from any of your clones.\n"
        "➔ /settings - Customize Your settings as your need.\n"
    )
    if is_admin_user:
        text += (
            "\n🛡 <b>My Admin Commands:</b>\n"
            "➔ /genlink - To store a single message or file.\n"
            "➔ /batch - To store multiple messages from a channel.\n"
            "➔ /custom_batch - To store message that can be accessed from any of your clones.\n"
            "➔ /broadcast - Broadcast a messages to users.\n"
            "➔ /ban - ban a user.\n"
            "➔ /unban - unban a user.\n"
        )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("SETTINGS", callback_data="settings_page"),
         InlineKeyboardButton("STATS",    callback_data="stats_popup")],
        [InlineKeyboardButton("BACK",     callback_data="menu")],
    ])
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, reply_markup=kb, parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            await update.callback_query.message.reply_text(
                text, reply_markup=kb, parse_mode="HTML",
                disable_web_page_preview=True,
            )
    else:
        await update.message.reply_text(
            text, reply_markup=kb, parse_mode="HTML",
            disable_web_page_preview=True,
        )


async def about_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "✨ <b><u>ABOUT ME</u></b>\n\n"
        f"⭐ <b>MY NAME:</b> <a href='https://t.me/{ctx.bot.username}'>FILE STORE BOT</a>\n\n"
        f"⭐ <b>MY OWNER:</b> <a href='{OWNER_LINK}'>MD ADMIN</a>\n\n"
        f"⭐ <b>UPDATES:</b> <a href='{UPDATES_LINK}'>MD BOTZ</a>\n\n"
        f"⭐ <b>SUPPORT:</b> <a href='{SUPPORT_LINK}'>MD GROUP</a>\n\n"
        f"⭐ <b>VERSION:</b> <code>{VERSION}</code>"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=back_kb(),
            parse_mode="HTML", disable_web_page_preview=True,
        )
    else:
        await update.message.reply_text(text, parse_mode="HTML",
                                        disable_web_page_preview=True)


async def cancel_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    cancelled = False
    if PENDING_GENLINK.pop(u.id, None):
        cancelled = True
    st = BATCH_STATE.pop(u.id, None)
    if st:
        db.set_batch_state(st["bid"], "cancelled")
        cancelled = True
    await update.message.reply_text("Cancelled." if cancelled else "Nothing to cancel.")


async def files_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await enforce_subscription(update, ctx):
        return
    u = update.effective_user
    rows = db.user_files(u.id)
    if not rows:
        await update.message.reply_text("No files yet. Send me one.")
        return
    lines = ["<b>Your files</b>\n"]
    for r in rows:
        lines.append(f"• <a href='{BASE_URL}/file/{r['short_id']}'>{r['name'][:40]}</a> ({r.get('views', 0)} views)")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML",
                                    disable_web_page_preview=True)


async def settings_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await enforce_subscription(update, ctx):
        return
    u = update.effective_user
    clones = db.get_clones(u.id)
    text = "<b>⚙️ Settings</b>\n\n"
    if clones:
        text += "<b>Your clones:</b>\n"
        for c in clones:
            text += f"• @{c['bot_username']}\n"
    else:
        text += "You have no clones.\n"
    text += (
        "\n<b>Available options:</b>\n"
        "• /custom_batch — toggle batch mode\n"
        "• /genlink — toggle genlink mode\n"
        "• /cancel — cancel any pending action"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def clone_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await enforce_subscription(update, ctx):
        return
    await update.message.reply_text(CLONE_SOON_TEXT, parse_mode="HTML")


async def genlink_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.upsert_user(u.id, u.username, u.first_name)
    if db.is_banned(u.id):
        await update.message.reply_text("🚫 Banned.")
        return
    if not await enforce_subscription(update, ctx):
        return
    PENDING_GENLINK[u.id] = True
    await update.message.reply_text("Send A Message For To Get Your Shareable Link")


async def custom_batch_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.upsert_user(u.id, u.username, u.first_name)
    if db.is_banned(u.id):
        await update.message.reply_text("🚫 Banned.")
        return
    if not await enforce_subscription(update, ctx):
        return
    ex = db.get_active_batch(u.id)
    if ex:
        BATCH_STATE[u.id] = {"bid": str(ex["_id"]), "paused": False}
        await update.message.reply_text(
            f"Active batch found with {len(ex['messages'])} messages. "
            f"Send more or use buttons below.",
            reply_markup=batch_kb(str(ex["_id"])),
        )
        return
    bid = db.create_batch(u.id)
    BATCH_STATE[u.id] = {"bid": str(bid), "paused": False}
    await update.message.reply_text("Send me the message you want to store")


async def _store_batch_message(update, ctx, msg):
    u = msg.from_user
    st = BATCH_STATE.get(u.id)
    if not st or st.get("paused"):
        return False
    bid = st["bid"]
    b = db.get_batch_by_id(bid)
    if not b or b["state"] not in ("collecting",):
        return False
    kind = None; preview = None
    if msg.text:
        kind, preview = "text", msg.text[:60]
    elif msg.photo:
        kind, preview = "photo", "🖼 Photo"
    elif msg.video:
        kind, preview = "video", "🎥 Video"
    elif msg.document:
        kind = "document"
        preview = f"📄 {getattr(msg.document, 'file_name', 'Document')}"
    elif msg.audio:
        kind, preview = "audio", "🎵 Audio"
    elif msg.voice:
        kind, preview = "voice", "🎤 Voice"
    elif msg.sticker:
        kind, preview = "sticker", "🎨 Sticker"
    elif msg.animation:
        kind, preview = "animation", "🎞 Animation"
    else:
        await msg.reply_text("Unsupported content in batch.")
        return True
    try:
        fwd = await ctx.bot.forward_message(
            chat_id=STORAGE_CHANNEL,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id,
        )
    except Exception as e:
        await msg.reply_text(f"⚠️ Storage failed: {e}")
        return True
    db.add_batch_message(bid, fwd.message_id, kind, preview)
    b = db.get_batch_by_id(bid)
    count = len(b["messages"])
    await msg.reply_text(
        f"<b>Stored Messages:</b> {count}\n\n"
        f"<i>Want to add another message? Just send it!</i>",
        reply_markup=batch_kb(bid),
        parse_mode="HTML",
    )
    return True


async def on_batch_callback(update, ctx, d):
    q = update.callback_query
    u = q.from_user
    _, action, bid = d.split(":", 2)
    b = db.get_batch_by_id(bid)
    if not b or b["owner_id"] != u.id:
        await q.edit_message_text("Batch not found.")
        return
    if action == "pause":
        db.set_batch_state(bid, "paused")
        st = BATCH_STATE.get(u.id)
        if st: st["paused"] = True
        await q.edit_message_text(
            f"<b>Stored Messages:</b> {len(b['messages'])}\n\n"
            f"<i>Want to add another message? Resume First!</i>",
            reply_markup=batch_kb(bid, paused=True),
            parse_mode="HTML",
        )
        return
    if action == "resume":
        db.set_batch_state(bid, "collecting")
        st = BATCH_STATE.get(u.id)
        if st: st["paused"] = False
        await q.edit_message_text(
            f"<b>Stored Messages:</b> {len(b['messages'])}\n\n"
            f"<i>Send another message.</i>",
            reply_markup=batch_kb(bid, paused=False),
            parse_mode="HTML",
        )
        return
    if action == "cancel":
        db.set_batch_state(bid, "cancelled")
        BATCH_STATE.pop(u.id, None)
        await q.edit_message_text("❌ Batch cancelled.")
        return
    if action == "gen":
        if not b["messages"]:
            await q.edit_message_text("No messages stored yet.")
            return
        token = unique_token()
        db.set_batch_token(bid, token)
        BATCH_STATE.pop(u.id, None)
        share_url = f"https://t.me/{ctx.bot.username}?start={token}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 OPEN LINK", url=share_url)],
            [InlineKeyboardButton("📤 SHARE URL",
                                  url=f"https://t.me/share/url?url={share_url}")],
        ])
        await q.edit_message_text(
            f"<b>Here is your link:</b>\n\n<code>{share_url}</code>\n\n"
            f"<i>{len(b['messages'])} messages stored</i>",
            reply_markup=kb, parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return


async def mylinks_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await enforce_subscription(update, ctx):
        return
    u = update.effective_user
    rows = db.user_links(u.id)
    if not rows:
        await update.message.reply_text("No links yet. Use /genlink.")
        return
    lines = ["<b>Your shareable links</b>\n"]
    for r in rows:
        url = f"https://t.me/{ctx.bot.username}?start={r['token']}"
        label = (r.get("preview_text") or r.get("name") or r.get("kind") or "link")[:40]
        lines.append(f"• <a href='{url}'>{label}</a> — {r.get('views', 0)} views")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML",
                                    disable_web_page_preview=True)


async def mybatches_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await enforce_subscription(update, ctx):
        return
    u = update.effective_user
    rows = db.user_batches(u.id)
    if not rows:
        await update.message.reply_text("No batches yet. Use /custom_batch.")
        return
    lines = ["<b>Your batches</b>\n"]
    for r in rows:
        url = f"https://t.me/{ctx.bot.username}?start={r['token']}"
        lines.append(f"• <a href='{url}'>{len(r['messages'])} messages</a> — {r.get('views', 0)} views")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML",
                                    disable_web_page_preview=True)


async def handle_any(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    u = msg.from_user
    if db.is_banned(u.id):
        await msg.reply_text("🚫 You are banned from using this bot.")
        return
    if msg.chat.type == "private":
        if not await enforce_subscription(update, ctx):
            return
    st = BATCH_STATE.get(u.id)
    if st and not st.get("paused"):
        if await _store_batch_message(update, ctx, msg):
            return
    if PENDING_GENLINK.pop(u.id, None):
        await _create_share_link(update, ctx, msg)
        return
    await handle_file(update, ctx)


async def _create_share_link(update, ctx, msg):
    kind = None; file_obj = None; preview_text = None
    if msg.text:
        kind, preview_text = "text", msg.text
    elif msg.photo:
        kind, file_obj = "photo", msg.photo[-1]
    elif msg.video:
        kind, file_obj = "video", msg.video
    elif msg.document:
        kind, file_obj = "document", msg.document
    elif msg.audio:
        kind, file_obj = "audio", msg.audio
    elif msg.voice:
        kind, file_obj = "voice", msg.voice
    elif msg.video_note:
        kind, file_obj = "video_note", msg.video_note
    elif msg.sticker:
        kind, file_obj = "sticker", msg.sticker
    elif msg.animation:
        kind, file_obj = "animation", msg.animation
    else:
        await msg.reply_text("Unsupported message type.")
        return
    try:
        fwd = await ctx.bot.forward_message(
            chat_id=STORAGE_CHANNEL,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id,
        )
    except Exception as e:
        await msg.reply_text(f"⚠️ Storage failed: {e}")
        return
    token = unique_token()
    file_id = getattr(file_obj, "file_id", None) if file_obj else None
    name = getattr(file_obj, "file_name", None) if file_obj else None
    db.save_link(
        token=token, owner_id=msg.from_user.id,
        file_id=file_id, message_id=fwd.message_id,
        kind=kind, preview_text=preview_text, name=name,
    )
    share_url = f"https://t.me/{ctx.bot.username}?start={token}"
    label_map = {
        "text": f"📝 {(preview_text or '')[:60]}",
        "photo": "🖼 Photo",
        "video": "🎥 Video",
        "document": f"📄 {name or 'Document'}",
        "audio": "🎵 Audio",
        "voice": "🎤 Voice",
        "sticker": "🎨 Sticker",
        "animation": "🎞 Animation",
        "video_note": "📹 Video note",
    }
    label = label_map.get(kind, "📦 File")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 OPEN LINK", url=share_url)],
        [InlineKeyboardButton("📤 SHARE URL",
                              url=f"https://t.me/share/url?url={share_url}")],
    ])
    await msg.reply_text(
        f"<b>Here is your link:</b>\n\n<code>{share_url}</code>\n\n<i>{label}</i>",
        reply_markup=kb, parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    u = msg.from_user
    f = (msg.document or msg.video or msg.audio or msg.voice
         or msg.video_note or (msg.photo[-1] if msg.photo else None))
    if not f:
        await msg.reply_text("Send a file, video, photo, audio, or voice.")
        return
    try:
        fwd = await ctx.bot.forward_message(
            chat_id=STORAGE_CHANNEL,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id,
        )
    except Exception as e:
        await msg.reply_text(f"⚠️ Storage failed: {e}")
        return
    sid = unique_token()
    name = getattr(f, "file_name", None) or f"file_{sid}"
    size = getattr(f, "file_size", 0)
    mime = getattr(f, "mime_type", "application/octet-stream")
    db.save_file(sid, u.id, f.file_id, fwd.message_id, name, size, mime)
    link = f"{BASE_URL}/file/{sid}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 OPEN LINK", url=link)],
        [InlineKeyboardButton("📋 COPY", callback_data=f"copy:{sid}")],
    ])
    await msg.reply_text(
        f"✅ Stored.\n\n<b>Link:</b>\n<code>{link}</code>\n\n"
        f"<b>Name:</b> {name}\n<b>Size:</b> {size/1024:.1f} KB",
        reply_markup=kb, parse_mode="HTML",
    )


async def inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.inline_query
    u = q.from_user
    status, _ = await check_subscribed(ctx.bot, u.id)
    if status != "ok":
        await q.answer([], cache_time=0,
                       switch_pm_text="Join our channel to use",
                       switch_pm_parameter="start")
        return
    text = (q.query or "").strip()
    if not text: return
    db.upsert_user(u.id, u.username, u.first_name)
    try:
        sent = await ctx.bot.send_message(chat_id=STORAGE_CHANNEL, text=text)
    except Exception:
        return
    token = unique_token()
    db.save_link(
        token=token, owner_id=u.id,
        file_id=None, message_id=sent.message_id,
        kind="text", preview_text=text, name=None,
    )
    share_url = f"https://t.me/{ctx.bot.username}?start={token}"
    result = InlineQueryResultArticle(
        id=token, title="🔗 Create link", description=text[:90],
        input_message_content=InputTextMessageContent(
            message_text=(
                f"🔗 <b>Tap to open</b>\n\n"
                f"<a href='{share_url}'>{text[:60]}</a>"
            ),
            parse_mode="HTML", disable_web_page_preview=False,
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("OPEN LINK", url=share_url)]
        ]),
    )
    await q.answer([result], cache_time=0, is_personal=True)


async def broadcast_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not is_admin(u.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    src = None
    if update.message.reply_to_message:
        src = update.message.reply_to_message
    elif ctx.args:
        src = " ".join(ctx.args)
    else:
        await update.message.reply_text(
            "Usage:\n• /broadcast <text>\n• /broadcast as reply to any message"
        )
        return
    status = await update.message.reply_text("📢 Broadcast started…")
    sent = failed = blocked = deleted = 0
    total = 0
    for uid in db.all_user_ids():
        total += 1
        try:
            if isinstance(src, str):
                await ctx.bot.send_message(uid, src)
            else:
                await ctx.bot.copy_message(chat_id=uid,
                                           from_chat_id=src.chat_id,
                                           message_id=src.message_id)
            sent += 1
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err:
                blocked += 1
            elif "deactivated" in err or "user is deactivated" in err:
                deleted += 1
            elif "chat not found" in err:
                deleted += 1
            else:
                failed += 1
        await asyncio.sleep(0.05)
        if total % 25 == 0:
            try:
                await status.edit_text(
                    f"📢 Broadcasting…\n\n"
                    f"Processed: <b>{total}</b>\n"
                    f"✅ Sent: <b>{sent}</b>\n"
                    f"🚫 Blocked: <b>{blocked}</b>\n"
                    f"👻 Deleted: <b>{deleted}</b>\n"
                    f"❌ Failed: <b>{failed}</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    final_text = (
        f"<blockquote>"
        f"🦋 <a href='https://t.me/{ctx.bot.username}'>Broadcast completed</a> !!\n"
        f"✅ Processed: <b>{total}</b>\n"
        f"❞"
        f"</blockquote>\n\n"
        f"◇ Total Users: <b>{total}</b>\n"
        f"◇ Successful: <b>{sent}</b>\n"
        f"◇ Blocked Users: <b>{blocked}</b>\n"
        f"◇ Deleted Accounts: <b>{deleted}</b>\n"
        f"◇ Unsuccessful: <b>{failed}</b>"
    )
    await status.edit_text(final_text, parse_mode="HTML")


async def ban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not is_admin(u.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    target_id = None; reason = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        reason = " ".join(ctx.args) if ctx.args else None
    elif ctx.args:
        try:
            target_id = int(ctx.args[0])
            reason = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else None
        except ValueError:
            await update.message.reply_text("Invalid user id.")
            return
    else:
        await update.message.reply_text("Usage: /ban <user_id> [reason]")
        return
    if target_id in ADMIN_IDS:
        await update.message.reply_text("⛔ Cannot ban an admin.")
        return
    if db.is_banned(target_id):
        await update.message.reply_text(f"User {target_id} already banned.")
        return
    db.ban_user(target_id, reason)
    try:
        await ctx.bot.send_message(target_id,
            "🚫 You have been banned from using this bot."
            + (f"\nReason: {reason}" if reason else ""))
    except Exception:
        pass
    await update.message.reply_text(
        f"✅ Banned <code>{target_id}</code>"
        + (f"\nReason: {reason}" if reason else ""),
        parse_mode="HTML",
    )


async def unban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not is_admin(u.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    target_id = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    elif ctx.args:
        try:
            target_id = int(ctx.args[0])
        except ValueError:
            await update.message.reply_text("Invalid user id.")
            return
    else:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    if db.unban_user(target_id):
        try:
            await ctx.bot.send_message(target_id, "✅ You have been unbanned.")
        except Exception:
            pass
        await update.message.reply_text(
            f"✅ Unbanned <code>{target_id}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text(f"User {target_id} was not banned.")


async def admin_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not is_admin(u.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    text = (
        "📊 <b>Admin Stats</b>\n\n"
        f"👥 Users: <b>{db.count_users()}</b>\n"
        f"🔗 Links: <b>{db.count_links()}</b>\n"
        f"📁 Files: <b>{db.count_files()}</b>\n"
        f"🚫 Bans: <b>{db.count_bans()}</b>\n"
        f"📢 Force-sub channels: <b>{len(FORCE_SUB_CHANNELS)}</b>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    u = q.from_user
    if d.startswith("batch:"):
        return await on_batch_callback(update, ctx, d)
    if d == "stats_popup":
        await q.answer(
            f"{ctx.bot.first_name}\n\n"
            f"◇ Total Users: {db.count_users()}\n"
            f"◇ Banned Users: {db.count_bans()}",
            show_alert=True,
        )
        return
    if d == "settings_page":
        clones = db.get_clones(u.id)
        text = "<b>⚙️ Settings</b>\n\n"
        if clones:
            text += "<b>Your clones:</b>\n"
            for c in clones:
                text += f"• @{c['bot_username']}\n"
        else:
            text += "You have no clones.\n"
        text += (
            "\n<b>Available options:</b>\n"
            "• /custom_batch — toggle batch mode\n"
            "• /genlink — toggle genlink mode\n"
            "• /cancel — cancel any pending action"
        )
        await q.edit_message_text(text, reply_markup=back_kb(), parse_mode="HTML")
        return
    if d == "check_sub":
        status, _ = await check_subscribed(ctx.bot, u.id)
        if status == "ok":
            await q.edit_message_text("✅ Verified. You can now use the bot.\n\nSend /start to begin.")
        elif status == "banned":
            await q.edit_message_text("🚫 You are banned.")
        else:
            await q.answer("❌ You haven't joined all channels yet.", show_alert=True)
        return
    if d == "menu":
        text = (
            f"Hello <b>{u.first_name}</b> ✨\n\n"
            "I am a permanent file store bot and users can access "
            "stored messages by using a shareable link given by me.\n\n"
            "To know more click help button."
        )
        await q.edit_message_text(text, reply_markup=main_menu(u), parse_mode="HTML")
        return
    if d == "help":
        return await help_cmd(update, ctx)
    if d == "about":
        return await about_cmd(update, ctx)
    if d == "genlink_info":
        PENDING_GENLINK[u.id] = True
        await q.edit_message_text(
            "Send A Message For To Get Your Shareable Link",
            reply_markup=back_kb(),
        )
        return
    if d == "batch_info":
        ex = db.get_active_batch(u.id)
        if ex:
            BATCH_STATE[u.id] = {"bid": str(ex["_id"]), "paused": False}
            await q.edit_message_text(
                f"Active batch with {len(ex['messages'])} messages.",
                reply_markup=batch_kb(str(ex["_id"])),
            )
            return
        bid = db.create_batch(u.id)
        BATCH_STATE[u.id] = {"bid": str(bid), "paused": False}
        await q.edit_message_text("Send me the message you want to store")
        return
    if d == "myfiles":
        rows = db.user_files(u.id)
        if not rows:
            await q.edit_message_text("No files yet.", reply_markup=back_kb())
            return
        lines = ["<b>Your files</b>\n"]
        for r in rows[:15]:
            lines.append(
                f"• <a href='{BASE_URL}/file/{r['short_id']}'>{r['name'][:40]}</a> ({r.get('views', 0)})"
            )
        await q.edit_message_text("\n".join(lines), parse_mode="HTML",
                                  disable_web_page_preview=True, reply_markup=back_kb())
        return
    if d == "mylinks":
        rows = db.user_links(u.id)
        if not rows:
            await q.edit_message_text("No links yet.", reply_markup=back_kb())
            return
        lines = ["<b>Your shareable links</b>\n"]
        for r in rows[:15]:
            url = f"https://t.me/{ctx.bot.username}?start={r['token']}"
            label = (r.get("preview_text") or r.get("name") or r.get("kind") or "link")[:40]
            lines.append(f"• <a href='{url}'>{label}</a> — {r.get('views', 0)} views")
        await q.edit_message_text("\n".join(lines), parse_mode="HTML",
                                  disable_web_page_preview=True, reply_markup=back_kb())
        return
    if d == "mybatches":
        rows = db.user_batches(u.id)
        if not rows:
            await q.edit_message_text("No batches yet.", reply_markup=back_kb())
            return
        lines = ["<b>Your batches</b>\n"]
        for r in rows[:15]:
            url = f"https://t.me/{ctx.bot.username}?start={r['token']}"
            lines.append(f"• <a href='{url}'>{len(r['messages'])} messages</a> — {r.get('views', 0)} views")
        await q.edit_message_text("\n".join(lines), parse_mode="HTML",
                                  disable_web_page_preview=True, reply_markup=back_kb())
        return
    if d == "clone":
        await q.edit_message_text(CLONE_SOON_TEXT, parse_mode="HTML", reply_markup=back_kb())
        return
    if d.startswith("copy:"):
        sid = d.split(":", 1)[1]
        await q.edit_message_text(f"<code>{BASE_URL}/file/{sid}</code>", parse_mode="HTML")
        return