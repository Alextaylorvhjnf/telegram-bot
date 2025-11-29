import os
import logging
import sqlite3
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
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

# ==================== Utilities ====================
def create_start_link(film_code):
    return f"https://t.me/{BOT_USERNAME}?start={film_code}"

def get_join_channel_keyboard():
    channel_username = FORCE_SUB_CHANNEL.replace('@', '')
    keyboard = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{channel_username}")],
        [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]
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

def check_user_membership(update, context, user_id):
    try:
        member = context.bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except BadRequest:
        return False
    except Exception as e:
        logging.error(f"خطا در بررسی عضویت: {e}")
        return False

# بقیه هندلرها دقیقاً مثل کد تو هست و نیازی به تغییر ندارند.
# تنها نکته تغییر "Filters" به "filters" در PTB 20+ است.

# ==================== تابع اصلی ====================
def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)
    logger.info("🚀 در حال راه‌اندازی ربات...")
    
    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    # اضافه کردن هندلرها
    from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler
    dispatcher.add_handler(CommandHandler("start", start_handler))
    dispatcher.add_handler(CommandHandler("help", help_handler))
    dispatcher.add_handler(CommandHandler("stats", stats_handler))
    dispatcher.add_handler(CommandHandler("films", films_handler))
    dispatcher.add_handler(CommandHandler("users", users_handler))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    dispatcher.add_handler(MessageHandler(
        filters.Chat(PRIVATE_CHANNEL_ID) & (filters.VIDEO | filters.Document.ALL),
        handle_channel_post
    ))
    
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
