import os
import logging
import sqlite3
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest

# ==================== تنظیمات ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8519774430:AAGHPewxXjkmj3fMmjjtMMlb3GD2oXGFR-0")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Senderpfilesbot")
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL", "@betdesignernet")
PRIVATE_CHANNEL_ID = int(os.getenv("PRIVATE_CHANNEL_ID", "-1002920455639"))
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "7321524568").split(",")]

# ==================== دیتابیس ====================
class Database:
    def __init__(self, db_path="films_bot.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS films (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                film_code TEXT UNIQUE NOT NULL,
                file_id TEXT NOT NULL,
                title TEXT,
                caption TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id INTEGER PRIMARY KEY,
                pending_film_code TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logging.info("✅ دیتابیس آماده است")
    
    def add_film(self, film_code, file_id, title=None, caption=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO films (film_code, file_id, title, caption)
                VALUES (?, ?, ?, ?)
            ''', (film_code, file_id, title, caption))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"خطا در ذخیره فیلم: {e}")
            return False
        finally:
            conn.close()
    
    def get_film(self, film_code):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT film_code, file_id, title, caption FROM films WHERE film_code = ?', (film_code,))
        result = cursor.fetchone()
        conn.close()
        if result:
            return {
                'film_code': result[0],
                'file_id': result[1],
                'title': result[2],
                'caption': result[3]
            }
        return None
    
    def get_all_films(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT film_code, title FROM films ORDER BY added_at DESC')
        results = cursor.fetchall()
        conn.close()
        return [{'film_code': row[0], 'title': row[1] or row[0]} for row in results]
    
    def get_all_films_detailed(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT film_code, title, file_id, added_at FROM films ORDER BY added_at DESC')
        results = cursor.fetchall()
        conn.close()
        return [{'film_code': row[0], 'title': row[1], 'file_id': row[2], 'added_at': row[3]} for row in results]
    
    def add_user(self, user_id, username, first_name, last_name):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"خطا در ذخیره کاربر: {e}")
            return False
        finally:
            conn.close()
    
    def get_users_count(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def get_films_count(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM films')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def set_pending_film(self, user_id, film_code):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO user_sessions (user_id, pending_film_code)
                VALUES (?, ?)
            ''', (user_id, film_code))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"خطا در ذخیره session: {e}")
            return False
        finally:
            conn.close()
    
    def get_pending_film(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT pending_film_code FROM user_sessions WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def clear_pending_film(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"خطا در پاک کردن session: {e}")
            return False
        finally:
            conn.close()

# ==================== Utilities ====================
def create_start_link(film_code):
    return f"https://t.me/{BOT_USERNAME}?start={film_code}"

def get_join_channel_keyboard(film_code=None):
    channel_username = FORCE_SUB_CHANNEL.replace('@', '')
    keyboard = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{channel_username}")],
        [InlineKeyboardButton("✅ عضو شدم", callback_data=f"check_join_{film_code}" if film_code else "check_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📖 راهنما", callback_data="help")],
        [InlineKeyboardButton("🎬 لیست فیلم‌ها", callback_data="list_films")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 آمار ربات", callback_data="admin_stats")],
        [InlineKeyboardButton("🎬 مدیریت فیلم‌ها", callback_data="admin_films")],
        [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== هندلرهای اصلی ====================
db = Database()

async def check_user_membership(user_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = await context.bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except BadRequest:
        return False
    except Exception as e:
        logging.error(f"خطا در بررسی عضویت: {e}")
        return False

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.channel_post
        if message.chat.id != PRIVATE_CHANNEL_ID:
            return
        if not message.video and not message.document:
            return
        
        file_id = message.video.file_id if message.video else message.document.file_id
        caption = message.caption or ""
        
        film_code_match = re.search(r'film\d+', caption, re.IGNORECASE)
        if film_code_match:
            film_code = film_code_match.group().lower()
            title = caption.split('\n')[0] if '\n' in caption else caption[:100]
            
            success = db.add_film(film_code=film_code, file_id=file_id, title=title, caption=caption)
            if success:
                logging.info(f"✅ فیلم {film_code} ذخیره شد")
                # اطلاع به ادمین
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            admin_id, 
                            f"🎬 فیلم جدید ذخیره شد:\n\nکد: {film_code}\nعنوان: {title}"
                        )
                    except Exception as e:
                        logging.error(f"خطا در اطلاع به ادمین {admin_id}: {e}")
            else:
                logging.error(f"❌ خطا در ذخیره فیلم {film_code}")
        else:
            logging.warning(f"⚠️ کد فیلم در caption پیدا نشد: {caption}")
    except Exception as e:
        logging.error(f"❌ خطا در پردازش پست کانال: {e}")

async def send_film_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE, film_code: str, user_id: int):
    is_member = await check_user_membership(user_id, context)
    
    if not is_member:
        # ذخیره فیلم در حال انتظار برای کاربر
        db.set_pending_film(user_id, film_code)
        
        join_text = f"""
⚠️ برای دریافت فیلم باید در کانال ما عضو شوید.

📢 {FORCE_SUB_CHANNEL}

✅ پس از عضویت روی «عضو شدم» کلیک کنید.
        """
        if update.message:
            await update.message.reply_text(join_text, reply_markup=get_join_channel_keyboard(film_code))
        else:
            await update.callback_query.edit_message_text(join_text, reply_markup=get_join_channel_keyboard(film_code))
        return
    
    film = db.get_film(film_code)
    if not film:
        error_text = "❌ فیلم مورد نظر یافت نشد."
        if update.message:
            await update.message.reply_text(error_text)
        else:
            await update.callback_query.edit_message_text(error_text)
        return
    
    try:
        caption = film['caption'] or film['title'] or f"🎬 فیلم {film_code}"
        if film['file_id'].startswith('BA') or film['file_id'].startswith('Ag'):
            await context.bot.send_video(chat_id=user_id, video=film['file_id'], caption=caption, reply_markup=get_main_keyboard())
        else:
            await context.bot.send_document(chat_id=user_id, document=film['file_id'], caption=caption, reply_markup=get_main_keyboard())
        
        success_text = f"✅ فیلم {film_code} ارسال شد"
        if update.callback_query:
            await update.callback_query.edit_message_text(success_text)
            
        # پاک کردن فیلم در حال انتظار
        db.clear_pending_film(user_id)
        
        # لاگ دانلود
        user = update.effective_user
        logging.info(f"کاربر {user.id} ({user.first_name}) فیلم {film_code} را دانلود کرد")
        
    except Exception as e:
        logging.error(f"خطا در ارسال فیلم: {e}")
        error_text = "❌ خطا در ارسال فیلم. لطفاً بعداً تلاش کنید."
        if update.message:
            await update.message.reply_text(error_text)
        else:
            await update.callback_query.edit_message_text(error_text)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # ذخیره کاربر
    db.add_user(user_id, user.username, user.first_name, user.last_name)
    
    # اگر کاربر ادمین است
    if user_id in ADMIN_IDS:
        admin_text = f"""
👑 سلام ادمین {user.first_name}!

🤖 به پنل مدیریت ربات خوش آمدید.

📊 می‌توانید از دستورات زیر استفاده کنید:
/stats - نمایش آمار ربات
/films - لیست کامل فیلم‌ها  
/users - تعداد کاربران
/help - راهنمای کاربران
        """
        
        if context.args:
            film_code = context.args[0]
            return await send_film_to_user(update, context, film_code, user_id)
        else:
            await update.message.reply_text(admin_text, reply_markup=get_admin_keyboard())
        return
    
    # کاربر عادی
    if context.args:
        film_code = context.args[0]
        return await send_film_to_user(update, context, film_code, user_id)
    
    welcome_text = f"""
🤖 به ربات دریافت فیلم خوش آمدید {user.first_name}!

🎬 برای دریافت فیلم روی لینک مخصوص آن کلیک کنید.

📢 حتما در کانال ما عضو شوید:
{FORCE_SUB_CHANNEL}

🔍 برای راهنمایی بیشتر روی دکمه «راهنما» کلیک کنید.
    """
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = f"""
📖 راهنمای ربات:

🎬 روش دریافت فیلم:
1. روی لینک مخصوص فیلم کلیک کنید
2. اگر لینک کار نکرد، در کانال عضو شوید
3. پس از عضویت دکمه «عضو شدم» را بزنید
4. فیلم برای شما ارسال می‌شود

📋 مشاهده فیلم‌ها:
• روی دکمه «لیست فیلم‌ها» کلیک کنید
• یا از لینک مستقیم استفاده کنید

🔗 لینک نمونه:
https://t.me/{BOT_USERNAME}?start=film001

📢 کانال: {FORCE_SUB_CHANNEL}

⚡ در صورت مشکل به ادمین پیام دهید.
    """
    await update.message.reply_text(help_text)

# ==================== هندلرهای دکمه ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data.startswith("check_join"):
        # استخراج film_code از callback_data اگر موجود باشد
        film_code = None
        if query.data.startswith("check_join_"):
            film_code = query.data.replace("check_join_", "")
        
        is_member = await check_user_membership(user_id, context)
        if is_member:
            # اگر کاربر عضو شد، فیلم را ارسال کن
            if film_code:
                await send_film_to_user(update, context, film_code, user_id)
            else:
                # اگر film_code مشخص نبود، از session بگیر
                pending_film = db.get_pending_film(user_id)
                if pending_film:
                    await send_film_to_user(update, context, pending_film, user_id)
                else:
                    await query.edit_message_text("✅ عالی! حالا می‌توانید از لینک فیلم استفاده کنید.", reply_markup=get_main_keyboard())
        else:
            await query.edit_message_text("❌ هنوز در کانال عضو نشده‌اید. لطفاً ابتدا عضو شوید و سپس روی «عضو شدم» کلیک کنید.", reply_markup=get_join_channel_keyboard(film_code))
    
    elif query.data == "list_films":
        films = db.get_all_films()
        if not films:
            await query.edit_message_text("📭 در حال حاضر فیلمی موجود نیست.", reply_markup=get_main_keyboard())
            return
        
        films_text = "🎬 لیست فیلم‌های موجود:\n\n"
        keyboard = []
        for film in films[:15]:
            film_title = film['title']
            films_text += f"• {film_title}\n"
            keyboard.append([InlineKeyboardButton(film_title, url=create_start_link(film['film_code']))])
        
        keyboard.append([InlineKeyboardButton("بازگشت ◀️", callback_data="back_to_main")])
        await query.edit_message_text(films_text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data == "help":
        help_text = f"""
📖 راهنمای ربات:

🎬 روش دریافت فیلم:
1. روی لینک مخصوص فیلم کلیک کنید
2. اگر لینک کار نکرد، در کانال عضو شوید
3. پس از عضویت دکمه «عضو شدم» را بزنید

🔗 لینک نمونه:
https://t.me/{BOT_USERNAME}?start=film001

📢 کانال: {FORCE_SUB_CHANNEL}
        """
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت ◀️", callback_data="back_to_main")]]))
    
    elif query.data == "back_to_main":
        if user_id in ADMIN_IDS:
            admin_text = "👑 به پنل مدیریت بازگشتید."
            await query.edit_message_text(admin_text, reply_markup=get_admin_keyboard())
        else:
            welcome_text = "🤖 به ربات دریافت فیلم خوش آمدید!\n\n🎬 برای دریافت فیلم روی لینک مخصوص آن کلیک کنید."
            await query.edit_message_text(welcome_text, reply_markup=get_main_keyboard())
    
    elif query.data == "admin_stats":
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ دسترسی denied.")
            return
        
        films_count = db.get_films_count()
        users_count = db.get_users_count()
        
        stats_text = f"""
📊 آمار ربات:

🎬 تعداد فیلم‌ها: {films_count}
👥 تعداد کاربران: {users_count}
🆔 تعداد ادمین‌ها: {len(ADMIN_IDS)}
🤖 وضعیت: فعال ✅
        """
        await query.edit_message_text(stats_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت ◀️", callback_data="back_to_main")]]))
    
    elif query.data == "admin_films":
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ دسترسی denied.")
            return
        
        films = db.get_all_films_detailed()
        if not films:
            await query.edit_message_text("📭 هیچ فیلمی در دیتابیس وجود ندارد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت ◀️", callback_data="back_to_main")]]))
            return
        
        films_text = "🎬 لیست کامل فیلم‌ها:\n\n"
        for i, film in enumerate(films[:10], 1):
            films_text += f"{i}. {film['title']}\n   کد: {film['film_code']}\n   تاریخ: {film['added_at'][:16]}\n\n"
        
        if len(films) > 10:
            films_text += f"\n📁 و {len(films) - 10} فیلم دیگر..."
        
        await query.edit_message_text(films_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت ◀️", callback_data="back_to_main")]]))
    
    elif query.data == "admin_users":
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ دسترسی denied.")
            return
        
        users_count = db.get_users_count()
        users_text = f"""
👥 آمار کاربران:

📊 تعداد کل کاربران: {users_count}
🆔 ادمین فعلی: {user_id}
        """
        await query.edit_message_text(users_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت ◀️", callback_data="back_to_main")]]))

# ==================== هندلرهای ادمین ====================
async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ شما دسترسی به این دستور را ندارید.")
        return
    
    films_count = db.get_films_count()
    users_count = db.get_users_count()
    
    stats_text = f"""
📊 آمار کامل ربات:

🎬 تعداد فیلم‌ها: {films_count}
👥 تعداد کاربران: {users_count}
🆔 تعداد ادمین‌ها: {len(ADMIN_IDS)}
🔗 کانال اجباری: {FORCE_SUB_CHANNEL}
📺 کانال خصوصی: {PRIVATE_CHANNEL_ID}
🤖 وضعیت: فعال ✅
    """
    await update.message.reply_text(stats_text)

async def films_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ شما دسترسی به این دستور را ندارید.")
        return
    
    films = db.get_all_films_detailed()
    
    if not films:
        await update.message.reply_text("📭 هیچ فیلمی در دیتابیس وجود ندارد.")
        return
    
    films_text = "🎬 لیست کامل فیلم‌ها:\n\n"
    
    for i, film in enumerate(films, 1):
        films_text += f"{i}. {film['title']}\n   کد: {film['film_code']}\n   تاریخ: {film['added_at'][:16]}\n\n"
    
    if len(films_text) > 4000:
        films_text = films_text[:4000] + "\n\n... (لیست کامل در لاگ‌ها موجود است)"
    
    await update.message.reply_text(films_text)

async def users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ شما دسترسی به این دستور را ندارید.")
        return
    
    users_count = db.get_users_count()
    
    users_text = f"""
👥 آمار کاربران:

📊 تعداد کل کاربران: {users_count}
🆔 ادمین فعلی: {user_id}
📅 کاربران در دیتابیس ذخیره شده‌اند.
    """
    await update.message.reply_text(users_text)

# ==================== تابع اصلی ====================
def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 در حال راه‌اندازی ربات...")
    logger.info(f"🆔 ادمین‌ها: {ADMIN_IDS}")
    logger.info(f"📢 کانال اجباری: {FORCE_SUB_CHANNEL}")
    logger.info(f"📺 کانال خصوصی: {PRIVATE_CHANNEL_ID}")
    
    try:
        # ایجاد application با استفاده از builder
        application = Application.builder().token(BOT_TOKEN).build()
        
        # اضافه کردن هندلرها
        application.add_handler(CommandHandler("start", start_handler))
        application.add_handler(CommandHandler("help", help_handler))
        application.add_handler(CommandHandler("stats", stats_handler))
        application.add_handler(CommandHandler("films", films_handler))
        application.add_handler(CommandHandler("users", users_handler))
        application.add_handler(CallbackQueryHandler(button_handler))
        
        application.add_handler(MessageHandler(
            filters.Chat(PRIVATE_CHANNEL_ID) & (filters.VIDEO | filters.Document.ALL),
            handle_channel_post
        ))
        
        logger.info("✅ ربات شروع به کار کرد")
        
        # اجرای ربات
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"❌ خطا در راه‌اندازی ربات: {e}")
        raise

if __name__ == "__main__":
    main()
