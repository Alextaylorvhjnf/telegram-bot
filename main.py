import os
import logging
import sqlite3
import secrets
import string
import asyncio
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest, Conflict

# ==================== تنظیمات ====================
TOKEN = os.getenv("BOT_TOKEN", "8519774430:AAGHPewxXjkmj3fMmjjtMMlb3GD2oXGFR-0")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Senderpfilesbot").lstrip("@")
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "@betdesignernet")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7321524568"))
PORT = int(os.getenv("PORT", 8080))
RAILWAY_STATIC_URL = os.getenv("RAILWAY_STATIC_URL", "")

# ==================== دیتابیس ====================
class Database:
    def __init__(self, db_path="/data/database.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def init_db(self):
        with self.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unique_key TEXT UNIQUE NOT NULL,
                    file_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    joined INTEGER DEFAULT 0,
                    first_name TEXT,
                    username TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id INTEGER PRIMARY KEY,
                    pending_video_key TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        logging.info("دیتابیس آماده است")

    def add_video(self, unique_key, file_id):
        with self.get_connection() as conn:
            try:
                conn.execute('''
                    INSERT INTO videos (unique_key, file_id)
                    VALUES (?, ?)
                ''', (unique_key, file_id))
                return True
            except sqlite3.IntegrityError:
                logging.warning(f"کلید تکراری: {unique_key}")
                return False
            except Exception as e:
                logging.error(f"خطا در ذخیره ویدیو: {e}")
                return False

    def get_video(self, unique_key):
        with self.get_connection() as conn:
            cur = conn.execute('SELECT unique_key, file_id FROM videos WHERE unique_key = ?', (unique_key,))
            row = cur.fetchone()
            if row:
                return {'unique_key': row[0], 'file_id': row[1]}
            return None

    def get_all_videos(self):
        with self.get_connection() as conn:
            cur = conn.execute('SELECT unique_key, file_id, created_at FROM videos ORDER BY created_at DESC')
            return [{'unique_key': r[0], 'file_id': r[1], 'created_at': r[2]} for r in cur.fetchall()]

    def add_user(self, user_id, first_name, username):
        with self.get_connection() as conn:
            conn.execute('''
                INSERT OR IGNORE INTO users (user_id, first_name, username)
                VALUES (?, ?, ?)
            ''', (user_id, first_name, username))

    def set_user_joined(self, user_id):
        with self.get_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO users (user_id, joined, joined_at)
                VALUES (?, 1, CURRENT_TIMESTAMP)
            ''', (user_id,))

    def has_user_joined(self, user_id):
        with self.get_connection() as conn:
            cur = conn.execute('SELECT joined FROM users WHERE user_id = ?', (user_id,))
            row = cur.fetchone()
            return row and row[0] == 1

    def set_pending_video(self, user_id, video_key):
        with self.get_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO user_sessions (user_id, pending_video_key)
                VALUES (?, ?)
            ''', (user_id, video_key))

    def get_pending_video(self, user_id):
        with self.get_connection() as conn:
            cur = conn.execute('SELECT pending_video_key FROM user_sessions WHERE user_id = ?', (user_id,))
            row = cur.fetchone()
            return row[0] if row else None

    def clear_pending_video(self, user_id):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))

    def get_stats(self):
        with self.get_connection() as conn:
            videos_count = conn.execute('SELECT COUNT(*) FROM videos').fetchone()[0]
            users_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            joined_users = conn.execute('SELECT COUNT(*) FROM users WHERE joined = 1').fetchone()[0]
            return videos_count, users_count, joined_users

db = Database()

# ==================== ابزارهای کمکی ====================
def generate_unique_key(length=10):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def create_video_link(unique_key):
    return f"https://t.me/{BOT_USERNAME}?start=video_{unique_key}"

def get_join_keyboard(video_key=None):
    channel_username = FORCE_CHANNEL.lstrip('@')
    keyboard = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{channel_username}")],
        [InlineKeyboardButton("✅ بررسی عضویت", callback_data=f"check_join_{video_key}" if video_key else "check_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 آمار ربات", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== بررسی عضویت - نسخه اصلاح شده ====================
async def check_channel_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    تابع بهبود یافته برای بررسی عضویت کاربر در کانال
    """
    try:
        # لاگ برای دیباگ
        logging.info(f"🔍 بررسی عضویت کاربر {user_id} در کانال {FORCE_CHANNEL}")
        
        # بررسی با استفاده از get_chat_member
        member = await context.bot.get_chat_member(FORCE_CHANNEL, user_id)
        
        # لاگ وضعیت کاربر
        logging.info(f"👤 وضعیت کاربر {user_id} در کانال: {member.status}")
        
        # بررسی وضعیت‌های مجاز
        allowed_statuses = ["member", "administrator", "creator"]
        is_member = member.status in allowed_statuses
        
        logging.info(f"✅ نتیجه بررسی عضویت کاربر {user_id}: {is_member}")
        return is_member
        
    except BadRequest as e:
        logging.error(f"❌ خطا در بررسی عضویت کاربر {user_id}: {e}")
        # اگر کانال پیدا نشد یا ربات دسترسی ندارد
        if "Chat not found" in str(e):
            logging.error("❌ کانال پیدا نشد. مطمئن شوید ربات در کانال ادمین است")
        elif "bot is not a member" in str(e):
            logging.error("❌ ربات عضو کانال نیست")
        elif "user not found" in str(e):
            logging.error("❌ کاربر پیدا نشد")
        return False
    except Exception as e:
        logging.error(f"❌ خطای غیرمنتظره در بررسی عضویت کاربر {user_id}: {e}")
        return False

# ==================== هندلر پست کانال ====================
async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.channel_post
        
        # فقط ویدیوها را پردازش کن
        if not message.video:
            return

        # تولید کلید منحصر به فرد
        unique_key = generate_unique_key()
        
        # ذخیره در دیتابیس
        if db.add_video(unique_key, message.video.file_id):
            # ایجاد لینک
            video_link = create_video_link(unique_key)
            
            # ارسال لینک به ادمین
            try:
                file_size = message.video.file_size
                size_text = f"{file_size // (1024*1024)} مگابایت" if file_size else "نامشخص"
                
                await context.bot.send_message(
                    ADMIN_ID,
                    f"🎬 ویدیو جدید ذخیره شد!\n\n"
                    f"🔑 کد: {unique_key}\n"
                    f"📁 حجم: {size_text}\n"
                    f"🔗 لینک مستقیم:\n{video_link}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📬 اشتراک‌گذاری لینک", url=video_link)]
                    ])
                )
                logging.info(f"✅ ویدیو جدید با کد {unique_key} ذخیره شد")
            except Exception as e:
                logging.error(f"❌ خطا در ارسال پیام به ادمین: {e}")
        else:
            logging.error("❌ خطا در ذخیره ویدیو در دیتابیس")
            
    except Exception as e:
        logging.error(f"❌ خطا در پردازش پست کانال: {e}")

# ==================== ارسال ویدیو به کاربر ====================
async def send_video_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE, video_key: str, user_id: int):
    try:
        # پیدا کردن ویدیو در دیتابیس
        video = db.get_video(video_key)
        if not video:
            error_text = "❌ ویدیو مورد نظر یافت نشد."
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return

        # ارسال ویدیو
        await context.bot.send_video(
            chat_id=user_id,
            video=video['file_id'],
            caption=f"🎬 ویدیو اختصاصی\n🔑 کد: {video_key}",
            reply_markup=get_main_keyboard()
        )

        # پاک کردن session در انتظار
        db.clear_pending_video(user_id)

        success_text = f"✅ ویدیو با موفقیت ارسال شد!\nکد: {video_key}"
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(success_text)
        
        logging.info(f"✅ کاربر {user_id} ویدیو {video_key} را دریافت کرد")

    except Exception as e:
        logging.error(f"❌ خطا در ارسال ویدیو: {e}")
        error_text = "❌ خطا در ارسال ویدیو. لطفاً بعداً تلاش کنید."
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)

# ==================== هندلر استارت - نسخه اصلاح شده ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # ذخیره اطلاعات کاربر
    db.add_user(user_id, user.first_name, user.username)

    # اگر کاربر ادمین است
    if user_id == ADMIN_ID:
        admin_text = f"""
👑 سلام ادمین عزیز!

🤖 به پنل مدیریت ربات خوش آمدید.

📊 دستورات مدیریتی:
/stats - نمایش آمار ربات
/videos - لیست ویدیوها
/help - راهنمای کاربران

🎬 برای آپلود ویدیو، آن را در کانال خصوصی آپلود کنید.
        """
        await update.message.reply_text(admin_text, reply_markup=get_main_keyboard())
        return

    # بررسی آرگومان استارت
    if context.args:
        start_arg = context.args[0]
        
        if start_arg.startswith("video_"):
            video_key = start_arg.replace("video_", "")
            
            # بررسی وجود ویدیو
            video = db.get_video(video_key)
            if not video:
                await update.message.reply_text(
                    "❌ ویدیو مورد نظر یافت نشد.",
                    reply_markup=get_main_keyboard()
                )
                return

            # بررسی اینکه آیا کاربر قبلاً عضو شده است
            if db.has_user_joined(user_id):
                # کاربر قبلاً عضو شده، مستقیماً ویدیو را ارسال کن
                logging.info(f"✅ کاربر {user_id} قبلاً عضو شده، ارسال ویدیو")
                await send_video_to_user(update, context, video_key, user_id)
                return
            else:
                # بررسی عضویت فعلی کاربر
                logging.info(f"🔍 بررسی عضویت فعلی کاربر {user_id}")
                is_member = await check_channel_membership(user_id, context)
                if is_member:
                    # کاربر عضو است، وضعیت را ذخیره کن و ویدیو را ارسال کن
                    logging.info(f"✅ کاربر {user_id} عضو است، ذخیره وضعیت و ارسال ویدیو")
                    db.set_user_joined(user_id)
                    await send_video_to_user(update, context, video_key, user_id)
                    return
                else:
                    # کاربر عضو نیست، درخواست عضویت بده
                    logging.info(f"❌ کاربر {user_id} عضو نیست، درخواست عضویت")
                    db.set_pending_video(user_id, video_key)
                    join_text = f"""
⚠️ برای دریافت ویدیو باید در کانال ما عضو شوید.

📢 کانال: {FORCE_CHANNEL}

✅ پس از عضویت، روی دکمه «بررسی عضویت» کلیک کنید.

💡 نکته: اگر قبلاً عضو شده‌اید، ممکن است نیاز باشد دوباره بررسی کنید.
                    """
                    await update.message.reply_text(
                        join_text,
                        reply_markup=get_join_keyboard(video_key)
                    )
                    return

    # پیام خوشامدگویی معمولی
    welcome_text = f"""
🤖 به ربات دریافت ویدیو خوش آمدید {user.first_name}!

🎬 برای دریافت ویدیو، روی لینک مخصوص آن کلیک کنید.

📢 برای دسترسی به تمام ویدیوها، در کانال ما عضو شوید:
{FORCE_CHANNEL}

🔍 برای اطلاعات بیشتر روی «راهنما» کلیک کنید.
    """
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

# ==================== هندلر دکمه‌ها - نسخه اصلاح شده ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    logging.info(f"🔘 دکمه فشرده شده: {data} توسط کاربر {user_id}")

    if data.startswith("check_join"):
        # استخراج video_key از callback_data
        video_key = None
        if data.startswith("check_join_"):
            video_key = data.replace("check_join_", "")
        
        # اگر video_key در callback_data نبود، از session بگیر
        if not video_key:
            video_key = db.get_pending_video(user_id)

        logging.info(f"🔍 بررسی عضویت برای کاربر {user_id}، ویدیو: {video_key}")

        # بررسی عضویت کاربر
        is_member = await check_channel_membership(user_id, context)
        
        if is_member:
            # کاربر عضو شده است
            logging.info(f"✅ کاربر {user_id} عضو است، ذخیره وضعیت")
            db.set_user_joined(user_id)
            
            if video_key:
                # ویدیو را ارسال کن
                logging.info(f"🎬 ارسال ویدیو {video_key} به کاربر {user_id}")
                await send_video_to_user(update, context, video_key, user_id)
            else:
                await query.edit_message_text(
                    "✅ عالی! شما عضو کانال هستید. حالا می‌توانید از لینک‌های ویدیو استفاده کنید.",
                    reply_markup=get_main_keyboard()
                )
        else:
            # کاربر هنوز عضو نشده
            logging.warning(f"❌ کاربر {user_id} هنوز عضو نیست")
            await query.edit_message_text(
                "❌ هنوز در کانال عضو نشده‌اید!\n\n"
                "لطفاً:\n"
                "1. روی دکمه «عضویت در کانال» کلیک کنید\n"
                "2. در کانال عضو شوید\n"
                "3. سپس روی «بررسی عضویت» کلیک کنید\n\n"
                "💡 نکته: اگر عضو شده‌اید، ممکن است نیاز باشد چند ثانیه صبر کنید سپس دوباره بررسی کنید.",
                reply_markup=get_join_keyboard(video_key)
            )

    elif data == "stats":
        videos_count, users_count, joined_users = db.get_stats()
        stats_text = f"""
📊 آمار ربات:

🎬 تعداد ویدیوها: {videos_count}
👥 کاربران کل: {users_count}
✅ کاربران عضو: {joined_users}
📅 آخرین بروزرسانی: {datetime.now().strftime('%Y-%m-%d %H:%M')}
        """
        await query.edit_message_text(stats_text, reply_markup=get_main_keyboard())

    elif data == "help":
        help_text = f"""
📖 راهنمای ربات:

🎬 روش دریافت ویدیو:
1. روی لینک مخصوص ویدیو کلیک کنید
2. اگر عضو کانال نیستید، ابتدا عضو شوید
3. روی «بررسی عضویت» کلیک کنید
4. ویدیو برای شما ارسال می‌شود

✅ پس از اولین عضویت:
• برای همیشه به تمام ویدیوها دسترسی دارید
• نیازی به بررسی مجدد عضویت نیست

📢 کانال اجباری: {FORCE_CHANNEL}

⚡ در صورت مشکل با ادمین تماس بگیرید.
        """
        await query.edit_message_text(help_text, reply_markup=get_main_keyboard())

# ==================== دستورات ادمین ====================
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ دسترسی denied.")
        return

    videos_count, users_count, joined_users = db.get_stats()
    stats_text = f"""
📊 آمار کامل ربات:

🎬 تعداد ویدیوها: {videos_count}
👥 کل کاربران: {users_count}
✅ کاربران عضو: {joined_users}
🔗 کانال اجباری: {FORCE_CHANNEL}
🤖 وضعیت: فعال ✅
    """
    await update.message.reply_text(stats_text)

async def videos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ دسترسی denied.")
        return

    videos = db.get_all_videos()
    if not videos:
        await update.message.reply_text("📭 هیچ ویدیویی در دیتابیس وجود ندارد.")
        return

    videos_text = "🎬 لیست ویدیوها:\n\n"
    for i, video in enumerate(videos[:10], 1):
        videos_text += f"{i}. کد: {video['unique_key']}\n   تاریخ: {video['created_at'][:16]}\n\n"

    if len(videos) > 10:
        videos_text += f"📁 و {len(videos) - 10} ویدیو دیگر..."

    await update.message.reply_text(videos_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = f"""
🤖 راهنمای ربات دریافت ویدیو

🎬 روش کار:
1. ویدیو را در کانال خصوصی آپلود کنید
2. ربات自动 یک لینک خصوصی تولید می‌کند
3. لینک را برای کاربران ارسال کنید
4. کاربران پس از عضویت در کانال، ویدیو را دریافت می‌کنند

📊 دستورات ادمین:
/stats - نمایش آمار
/videos - لیست ویدیوها

🔗 نمونه لینک:
https://t.me/{BOT_USERNAME}?start=video_ABC123XYZ
    """
    await update.message.reply_text(help_text)

# ==================== هندلر خطا ====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"❌ خطا در پردازش بروزرسانی: {context.error}")
    
    if isinstance(context.error, Conflict):
        logging.warning("⚠️ درگیری تشخیص داده شد - احتمالاً نمونه‌های متعدد ربات در حال اجرا هستند")
        await asyncio.sleep(5)

# ==================== تنظیمات لاگ و اجرا ====================
def main():
    # تنظیمات لاگ
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)

    logger.info("🚀 در حال راه‌اندازی ربات...")
    logger.info(f"🆔 ادمین: {ADMIN_ID}")
    logger.info(f"📢 کانال اجباری: {FORCE_CHANNEL}")
    logger.info(f"🤖 نام ربات: {BOT_USERNAME}")
    logger.info(f"🌐 پورت: {PORT}")

    try:
        # ایجاد اپلیکیشن
        app = Application.builder().token(TOKEN).build()

        # اضافه کردن هندلرها
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("videos", videos_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CallbackQueryHandler(button_handler))

        # هندلر پست‌های کانال (فقط ویدیو)
        app.add_handler(MessageHandler(filters.VIDEO, channel_post_handler))

        # هندلر خطا
        app.add_error_handler(error_handler)

        logger.info("✅ ربات شروع به کار کرد")

        # استفاده از webhook اگر URL استاتیک موجود باشد
        if RAILWAY_STATIC_URL:
            logger.info(f"🌐 استفاده از webhook با آدرس: {RAILWAY_STATIC_URL}")
            app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=TOKEN,
                webhook_url=f"{RAILWAY_STATIC_URL}/{TOKEN}"
            )
        else:
            logger.info("🔄 استفاده از polling")
            # استفاده از polling با drop_pending_updates برای جلوگیری از درگیری
            app.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
                close_loop=False
            )

    except Conflict as e:
        logger.error(f"❌ خطای درگیری: {e}")
        logger.info("ربات دیگری در حال اجرا است. این نمونه متوقف می‌شود.")
    except Exception as e:
        logger.error(f"❌ خطا در راه‌اندازی ربات: {e}")
        raise

if __name__ == "__main__":
    main()
