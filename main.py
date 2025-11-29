import os
import logging
import sqlite3
import secrets
import string
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram.error import BadRequest

# ==================== تنظیمات ====================
TOKEN = "8519774430:AAGHPewxXjkmj3fMmjjtMMlb3GD2oXGFR-0"
BOT_USERNAME = "Senderpfilesbot"

# 🔥 مهم: از ID عددی کانال استفاده کنید
# برای پیدا کردن ID: پیامی از کانال را فوروارد کنید به @userinfobot
FORCE_CHANNEL = "-1002920455639"  # جایگزین کنید با ID واقعی کانال شما

ADMIN_ID = 7321524568

# ==================== دیتابیس ====================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot.db', check_same_thread=False)
        self.init_db()
    
    def init_db(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unique_key TEXT UNIQUE,
                file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                joined BOOLEAN DEFAULT FALSE,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
        logging.info("✅ دیتابیس آماده است")
    
    def add_video(self, unique_key, file_id):
        try:
            self.conn.execute('INSERT INTO videos (unique_key, file_id) VALUES (?, ?)', (unique_key, file_id))
            self.conn.commit()
            logging.info(f"✅ ویدیو با کد {unique_key} ذخیره شد")
            return True
        except Exception as e:
            logging.error(f"❌ خطا در ذخیره ویدیو: {e}")
            return False
    
    def get_video(self, unique_key):
        cursor = self.conn.execute('SELECT file_id FROM videos WHERE unique_key = ?', (unique_key,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def set_user_joined(self, user_id, username="", first_name=""):
        self.conn.execute(
            'INSERT OR REPLACE INTO users (user_id, joined, username, first_name) VALUES (?, ?, ?, ?)', 
            (user_id, True, username, first_name)
        )
        self.conn.commit()
        logging.info(f"✅ کاربر {user_id} به عنوان عضو ثبت شد")
    
    def has_user_joined(self, user_id):
        cursor = self.conn.execute('SELECT joined FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else False

db = Database()

# ==================== ابزارهای کمکی ====================
def generate_key():
    return 'vid_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))

def create_keyboard(video_key=None):
    buttons = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/betdesignernet")],
        [InlineKeyboardButton("✅ بررسی عضویت", callback_data=f"check_{video_key}" if video_key else "check")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")]
    ])

# ==================== بررسی عضویت - نسخه بهبود یافته ====================
async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    تابع پیشرفته برای بررسی عضویت کاربر
    """
    try:
        logging.info(f"🔍 بررسی عضویت کاربر {user_id} در کانال {FORCE_CHANNEL}")
        
        # بررسی با ID عددی کانال
        member = await context.bot.get_chat_member(chat_id=FORCE_CHANNEL, user_id=user_id)
        status = member.status
        
        logging.info(f"👤 وضعیت کاربر {user_id}: {status}")
        
        # وضعیت‌های مجاز
        if status in ['member', 'administrator', 'creator']:
            logging.info(f"✅ کاربر {user_id} عضو کانال است")
            return True
        else:
            logging.warning(f"❌ کاربر {user_id} عضو نیست. وضعیت: {status}")
            return False
            
    except BadRequest as e:
        error_msg = str(e)
        logging.error(f"❌ خطا در بررسی عضویت: {error_msg}")
        
        if "Chat not found" in error_msg:
            logging.error("❌ کانال پیدا نشد! مطمئن شوید:")
            logging.error("   1. از ID عددی کانال استفاده کنید")
            logging.error("   2. ربات در کانال ادمین است")
            logging.error("   3. ID کانال صحیح است")
        elif "bot is not a member" in error_msg:
            logging.error("❌ ربات عضو کانال نیست! ربات را به کانال اضافه کنید")
        elif "user not found" in error_msg:
            logging.error("❌ کاربر پیدا نشد")
        
        return False
        
    except Exception as e:
        logging.error(f"❌ خطای غیرمنتظره در بررسی عضویت: {e}")
        return False

# ==================== ارسال ویدیو ====================
async def send_video(context, user_id, video_key, message_to_edit=None):
    try:
        file_id = db.get_video(video_key)
        if not file_id:
            error_text = "❌ ویدیو پیدا نشد. لینک ممکن است منقضی شده باشد."
            if message_to_edit:
                await message_to_edit.edit_text(error_text)
            else:
                await context.bot.send_message(user_id, error_text)
            return
        
        # ارسال ویدیو
        await context.bot.send_video(
            user_id, 
            file_id, 
            caption=f"🎬 ویدیو شما\n🔑 کد: {video_key}",
            reply_markup=get_main_keyboard()
        )
        
        if message_to_edit:
            await message_to_edit.edit_text("✅ ویدیو با موفقیت ارسال شد!")
        
        # ثبت کاربر به عنوان عضو
        db.set_user_joined(user_id)
        logging.info(f"✅ ویدیو {video_key} برای کاربر {user_id} ارسال شد")
        
    except Exception as e:
        logging.error(f"❌ خطا در ارسال ویدیو: {e}")
        error_text = "❌ خطا در ارسال ویدیو. لطفاً بعداً تلاش کنید."
        if message_to_edit:
            await message_to_edit.edit_text(error_text)
        else:
            await context.bot.send_message(user_id, error_text)

# ==================== هندلر استارت ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    logging.info(f"🚀 کاربر {user_id} دستور /start را اجرا کرد")
    
    # اگر آرگومان دارد (یعنی از لینک آمده)
    if context.args:
        start_arg = context.args[0]
        
        if start_arg.startswith("video_"):
            video_key = start_arg.replace("video_", "")
            logging.info(f"🎬 درخواست ویدیو {video_key} توسط کاربر {user_id}")
            
            # بررسی وجود ویدیو
            if not db.get_video(video_key):
                await update.message.reply_text(
                    "❌ لینک معتبر نیست یا ویدیو حذف شده است.",
                    reply_markup=get_main_keyboard()
                )
                return
            
            # اگر کاربر قبلاً عضو شده
            if db.has_user_joined(user_id):
                logging.info(f"✅ کاربر {user_id} قبلاً عضو شده، ارسال ویدیو")
                await send_video(context, user_id, video_key)
                return
            
            # بررسی عضویت فعلی
            logging.info(f"🔍 بررسی عضویت کاربر {user_id}")
            is_member = await check_membership(user_id, context)
            
            if is_member:
                logging.info(f"✅ کاربر {user_id} عضو است، ارسال ویدیو")
                db.set_user_joined(user_id, user.username, user.first_name)
                await send_video(context, user_id, video_key)
            else:
                logging.info(f"⚠️ کاربر {user_id} عضو نیست، نمایش پیام عضویت")
                await update.message.reply_text(
                    "⚠️ برای دریافت ویدیو باید در کانال ما عضو شوید.\n\n"
                    "📢 @betdesignernet\n\n"
                    "✅ پس از عضویت روی دکمه زیر کلیک کنید:",
                    reply_markup=create_keyboard(video_key)
                )
    else:
        # پیام خوشامدگویی معمولی
        await update.message.reply_text(
            f"سلام {user.first_name}! 🤖\n\n"
            f"به ربات دریافت ویدیو خوش آمدید.\n\n"
            f"🎬 برای دریافت ویدیو روی لینک مخصوص کلیک کنید.\n"
            f"📢 کانال: @betdesignernet\n\n"
            f"🔍 برای اطلاعات بیشتر از منو استفاده کنید.",
            reply_markup=get_main_keyboard()
        )

# ==================== هندلر دکمه ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    logging.info(f"🔘 دکمه {data} توسط کاربر {user_id} فشرده شد")
    
    if data.startswith("check_"):
        video_key = data.replace("check_", "")
        
        logging.info(f"🔍 بررسی عضویت برای کاربر {user_id} (از طریق دکمه)")
        is_member = await check_membership(user_id, context)
        
        if is_member:
            db.set_user_joined(user_id)
            await send_video(context, user_id, video_key, query.message)
        else:
            await query.edit_message_text(
                "❌ هنوز در کانال عضو نشده‌اید!\n\n"
                "لطفاً:\n"
                "1. روی 'عضویت در کانال' کلیک کنید\n"
                "2. در کانال @betdesignernet عضو شوید\n" 
                "3. سپس دوباره روی 'بررسی عضویت' کلیک کنید\n\n"
                "🔍 اگر عضو شده‌اید اما این پیام را می‌بینید:\n"
                "• چند ثانیه صبر کنید\n"
                "• از کانال خارج و دوباره عضو شوید\n"
                "• با ادمین تماس بگیرید",
                reply_markup=create_keyboard(video_key)
            )
    
    elif data == "stats":
        # نمایش آمار ساده
        await query.edit_message_text(
            "📊 آمار ربات:\n\n"
            "🤖 وضعیت: فعال\n"
            "🔗 کانال: @betdesignernet\n"
            "👤 برای دریافت ویدیو از لینک استفاده کنید",
            reply_markup=get_main_keyboard()
        )
    
    elif data == "help":
        await query.edit_message_text(
            "📖 راهنمای ربات:\n\n"
            "🎬 روش دریافت ویدیو:\n"
            "1. روی لینک مخصوص ویدیو کلیک کنید\n"
            "2. در کانال عضو شوید\n"
            "3. روی 'بررسی عضویت' کلیک کنید\n"
            "4. ویدیو دریافت می‌شود\n\n"
            "✅ پس از اولین عضویت:\n"
            "• دیگر نیازی به بررسی نیست\n"
            "• تمام ویدیوها مستقیم ارسال می‌شوند\n\n"
            "📢 کانال: @betdesignernet",
            reply_markup=get_main_keyboard()
        )

# ==================== هندلر آپلود ویدیو ====================
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post or not update.channel_post.video:
        return
    
    video = update.channel_post.video
    unique_key = generate_key()
    
    if db.add_video(unique_key, video.file_id):
        link = f"https://t.me/{BOT_USERNAME}?start=video_{unique_key}"
        
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"🎬 ویدیو جدید ذخیره شد!\n\n"
                f"🔑 کد: {unique_key}\n"
                f"📊 حجم: {video.file_size // (1024*1024)} MB\n"
                f"🔗 لینک:\n{link}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📬 اشتراک‌گذاری لینک", url=link)
                ]])
            )
        except Exception as e:
            logging.error(f"❌ خطا در ارسال به ادمین: {e}")

# ==================== دستور تست ====================
async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ این دستور فقط برای ادمین است.")
        return
    
    is_member = await check_membership(user_id, context)
    
    await update.message.reply_text(
        f"🔍 تست عضویت:\n\n"
        f"👤 کاربر: {user_id}\n"
        f"📢 کانال: {FORCE_CHANNEL}\n"
        f"✅ عضو است: {is_member}\n\n"
        f"💡 اگر 'عضو است: False' ولی شما عضو هستید:\n"
        f"• مطمئن شوید از ID عددی کانال استفاده می‌کنید\n"
        f"• ربات باید ادمین کانال باشد\n"
        f"• ID کانال باید صحیح باشد"
    )

# ==================== دستور تنظیم مجدد ====================
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        return
    
    # حذف وضعیت عضویت کاربر
    db.conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    db.conn.commit()
    
    await update.message.reply_text("✅ وضعیت عضویت شما بازنشانی شد. حالا دوباره تست کنید.")

# ==================== اجرای ربات ====================
def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    logging.info("🚀 شروع ربات...")
    logging.info(f"📢 کانال اجباری: {FORCE_CHANNEL}")
    logging.info(f"👑 ادمین: {ADMIN_ID}")
    
    app = Application.builder().token(TOKEN).build()
    
    # هندلرها
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    
    logging.info("✅ ربات آماده است")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
