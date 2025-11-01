# -*- coding: utf-8 -*-
import telebot
from telebot import types
import sqlite3, json, re, datetime, time

# ====== НАСТРОЙКИ ======
TOKEN = 7557908459:AAHJt4DqnN-TijbjMm9BbGExwCxJ49vm18I
ADMIN_ID = 7867809053                # ваш Telegram ID
MANAGER_IDS = [7867809053]          # список Telegram ID менеджеров
CHANNEL_ID = None                  # например: -1001234567890, если хотите постить ссылки в канал. Иначе None
CURRENCY = "₽"
REFERRAL_CAP = 40                  # потолок реферальной скидки, %

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
BOT_USERNAME = None  # узнаем при старте

# ====== БАЗА ДАННЫХ ======
conn = sqlite3.connect("shop.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  sizes TEXT,              -- строка размеров "S,M,L"
  price INTEGER,           -- цена (число)
  photos TEXT,             -- JSON [file_id, ...]
  category TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS cart(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  product_id INTEGER,
  size TEXT                -- выбранный размер (или "—")
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS favorites(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  product_id INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  username TEXT,
  products TEXT,           -- CSV: "Название [Размер]"
  total INTEGER,           -- сумма
  status TEXT,             -- новый/подтвержден/в пути/доставлен/отменен
  created_at TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  rating INTEGER,
  text TEXT,
  created_at TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS subscriptions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  category TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS promocodes(
  code TEXT PRIMARY KEY,
  discount INTEGER,        -- скидка в %
  active INTEGER           -- 1/0
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS support(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  question TEXT,
  status TEXT,             -- открыт/отвечен/закрыт
  created_at TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS user_settings(
  user_id INTEGER PRIMARY KEY,
  theme TEXT               -- light/dark
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS users(
  user_id INTEGER PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  last_active TEXT
)""")

# Реферальная система
cur.execute("""CREATE TABLE IF NOT EXISTS referrals(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,         -- кто пришёл
  referrer_id INTEGER,     -- кто пригласил
  created_at TEXT
)""")

conn.commit()

# --- МИГРАЦИИ (если БД старая) ---
def try_alter(sql):
    try:
        cur.execute(sql); conn.commit()
    except Exception:
        pass
try_alter("ALTER TABLE products ADD COLUMN sizes TEXT")
try_alter("ALTER TABLE cart ADD COLUMN size TEXT")

# ====== СОСТОЯНИЯ ======
pending_search = {}               # user_id -> True
pending_promo_input = set()
pending_support = set()
pending_manager_answer = {}
pending_broadcast = {}
awaiting_broadcast_content = set()
awaiting_broadcast_confirm = set()
gallery_state = {}                # (chat_id, product_id) -> index

# ====== УТИЛИТЫ ======
def now_str() -> str:
    return datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

def fmt_price(value: int) -> str:
    return f"{value}{CURRENCY} (стоимость доставки из Китая включена в стоимость)"

def theme_of(user_id: int) -> str:
    cur.execute("SELECT theme FROM user_settings WHERE user_id=?", (user_id,))
    r = cur.fetchone()
    return r[0] if r and r[0] in ("light","dark") else "light"

def set_theme(user_id: int, theme: str):
    cur.execute("INSERT OR REPLACE INTO user_settings(user_id, theme) VALUES(?,?)", (user_id, theme))
    conn.commit()
