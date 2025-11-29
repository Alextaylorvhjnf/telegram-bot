import json
import time
import asyncio
from uuid import uuid4
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ----------------------- CONFIG -----------------------
TOKEN = "8519774430:AAGHPewxXjkmj3fMmjjtMMlb3GD2oXGFR-0"
BOT_USERNAME = "Senderpfilesbot"
FORCE_CHANNEL_ID = -1002920455639
CHANNEL_LINK = "https://t.me/betdesignernet"
ADMIN_ID = 7321524568

DB_FILE = "db.json"

# ----------------------- DATABASE -----------------------

def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"videos": {}, "users": []}


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


db = load_db()

# ----------------------- ADMIN PANEL -----------------------

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    total_users = len(db["users"])
    total_videos = len(db["videos"])

    text = (
        "📊 *پنل مدیریت*\n\n"
        f"👥 تعداد کاربران: {total_users}\n"
        f"🎞 تعداد ویدیوهای ذخیره‌شده: {total_videos}\n\n"
        "برای استفاده از پنل از دکمه‌ها استفاده کن:"
    )

    keyboard = [
        [InlineKeyboardButton("📁 لیست ویدیوها", callback_data="admin_videos")],
        [InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_users")]
    ]

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    if query.data == "admin_videos":
        txt = "🎞 *لیست ویدیوهای ذخیره شده:*\n\n"
        for key in db["videos"]:
            txt += f"• {key}\n"
        await query.message.reply_text(txt, parse_mode="Markdown")

    elif query.data == "admin_users":
        txt = "👥 *لیست کاربران:*\n\n"
        for u in db["users"]:
            txt += f"• {u}\n"
        await query.message.reply_text(txt, parse_mode="Markdown")

# ----------------------- VIDEO CAPTURE FROM CHANNEL -----------------------

async def save_channel_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat.id

    if chat_id != FORCE_CHANNEL_ID:
        return

    # detect video/document-video
    if not message.video and not (
        message.document and message.document.mime_type.startswith("video")
    ):
        return

    message_id = message.message_id
    key = "v_" + uuid4().hex[:10]

    db["videos"][key] = {"message_id": message_id}
    save_db(db)

    link = f"https://t.me/{BOT_USERNAME}?start={key}"

    await message.reply_text(f"لینک اختصاصی این ویدیو:\n{link}")

# ----------------------- USER START -----------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    # add user to database
    if user.id not in db["users"]:
        db["users"].append(user.id)
        save_db(db)

    args = context.args

    if not args:
        await update.message.reply_text("برای دریافت ویدیو از لینک اختصاصی استفاده کن.")
        return

    key = args[0]

    if key not in db["videos"]:
        await update.message.reply_text("لینک نامعتبر است یا حذف شده.")
        return

    await check_membership_and_send(update, context, key)

# ----------------------- CHECK MEMBERSHIP -----------------------

async def check_membership_and_send(update, context, key):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        member = await context.bot.get_chat_member(FORCE_CHANNEL_ID, user_id)
        if member.status not in ["member", "administrator", "creator"]:
            raise Exception("Not joined")

    except:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_LINK)],
            [InlineKeyboardButton("🔁 بررسی عضویت", callback_data=f"check_{key}")]
        ])

        await update.message.reply_text(
            "برای دریافت ویدیو ابتدا عضو کانال شو:",
            reply_markup=keyboard
        )
        return

    # send video and delete after 30 seconds
    msg = await context.bot.forward_message(
        chat_id=chat_id,
        from_chat_id=FORCE_CHANNEL_ID,
        message_id=db["videos"][key]["message_id"]
    )

    await asyncio.sleep(30)
    try:
        await context.bot.delete_message(chat_id, msg.message_id)
    except:
        pass

# ----------------------- CALLBACK QUERY -----------------------

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("check_"):
        key = data.replace("check_", "")
        await check_membership_and_send(query, context, key)

    # admin panel buttons
    await admin_buttons(update, context)

# ----------------------- MAIN -----------------------

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))

    app.add_handler(MessageHandler(filters.ALL, save_channel_video))
    app.add_handler(CallbackQueryHandler(callback_handler))

    print("BOT RUNNING…")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
