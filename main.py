import asyncio
import logging
import sqlite3
import base64
import json
import io
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import time
import re

import requests
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.error import TelegramError, BadRequest

# ============ الإعدادات ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8703000621:AAGh7Je5MSxd-tv8qFYEONbT2pW7A6nJ5dE")
ADMIN_ID = 8593727596
DEVELOPER = "سـمـعهہ‏‏_𝕍𝕀ℙ"
DEV_USERNAME = "asmael175"

BASE_URL = "https://mab.etisalat.com.eg:11003/Saytar/rest"

PRODUCTS = {
    "180": {"name": "Hekaya_XRP_MIX_Parent_6", "rate_plan_id": "951"},
    "270": {"name": "Hekaya_XRP_MIX_Parent_7", "rate_plan_id": ""},
}

SEARCH_ORDER = [
    "Hekaya_XRP_MIX_Parent_7",
    "Hekaya_XRP_MIX_Parent_6",
    "Hekaya_XRP_MIX_Child_1",
]

# ============ أنواع الاشتراك ============
SUBSCRIPTION_PLANS = {
    "daily":   {"name": "يومي",   "price": 100, "days": 1,  "emoji": "📅"},
    "weekly":  {"name": "أسبوعي", "price": 200, "days": 7,  "emoji": "📆"},
    "monthly": {"name": "شهري",   "price": 300, "days": 30, "emoji": "🗓"},
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

DB_PATH = "etisalat_bot_v5.db"

# loop_manager global (يتم تعريفه في post_init)
loop_manager = None


# ============ دوال مساعدة ============
def esc(s):
    if s is None: return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def b64_enc(s): return base64.b64encode((s or "").encode()).decode()

def b64_dec(s):
    try: return base64.b64decode(s or "").decode()
    except Exception: return ""

def db_exec(query, params=()):
    conn = sqlite3.connect(DB_PATH, timeout=15)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    rows = c.fetchall()
    conn.close()
    return rows

# ============ قاعدة البيانات ============
def db_init():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if c.fetchone():
        c.execute("PRAGMA table_info(users)")
        cols = [info[1] for info in c.fetchall()]
        required_cols = ['user_id', 'username', 'first_name', 'owner_email', 'owner_pass', 'child_email', 'child_pass', 'banned', 'created_at']
        if not all(col in cols for col in required_cols):
            c.execute("DROP TABLE users")

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        owner_email TEXT,
        owner_pass TEXT,
        child_email TEXT,
        child_pass TEXT,
        banned INTEGER DEFAULT 0,
        created_at TEXT
    )""")

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='loops'")
    if c.fetchone():
        c.execute("PRAGMA table_info(loops)")
        cols = [info[1] for info in c.fetchall()]
        required_cols = ['user_id', 'status', 'target', 'current_mix', 'cycles', 'started_at', 'ended_at', 'error']
        if not all(col in cols for col in required_cols):
            c.execute("DROP TABLE loops")

    c.execute("""CREATE TABLE IF NOT EXISTS loops (
        user_id INTEGER PRIMARY KEY,
        status TEXT DEFAULT 'idle',
        target INTEGER DEFAULT 0,
        current_mix INTEGER DEFAULT 0,
        cycles INTEGER DEFAULT 0,
        started_at TEXT,
        ended_at TEXT,
        error TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
        user_id INTEGER PRIMARY KEY,
        plan TEXT,
        started_at TEXT,
        expires_at TEXT,
        activated_by INTEGER,
        created_at TEXT
    )""")

    conn.commit()
    conn.close()

db_init()

# ============ دوال المستخدمين ============
def get_user(user_id):
    r = db_exec(
        "SELECT user_id, username, first_name, owner_email, owner_pass, "
        "child_email, child_pass, banned, created_at FROM users WHERE user_id=?",
        (user_id,)
    )
    if not r: return None
    keys = ["user_id", "username", "first_name", "owner_email", "owner_pass",
            "child_email", "child_pass", "banned", "created_at"]
    d = dict(zip(keys, r[0]))
    d['owner_pass'] = b64_dec(d['owner_pass'] or "")
    d['child_pass'] = b64_dec(d['child_pass'] or "")
    return d

def clear_user_creds(user_id):
    db_exec("UPDATE users SET owner_email=NULL, owner_pass=NULL, child_email=NULL, child_pass=NULL WHERE user_id=?", (user_id,))

def save_loop(user_id, **kwargs):
    if not kwargs:
        return
    r = db_exec("SELECT user_id FROM loops WHERE user_id=?", (user_id,))
    if r:
        fields = ", ".join(f"{k}=?" for k in kwargs)
        db_exec(f"UPDATE loops SET {fields} WHERE user_id=?", (*kwargs.values(), user_id))
    else:
        cols = ", ".join(kwargs.keys())
        ph = ", ".join("?" * len(kwargs))
        db_exec(f"INSERT INTO loops (user_id, {cols}) VALUES (?, {ph})", (user_id, *kwargs.values()))

def get_loop(user_id):
    r = db_exec("SELECT status, target, current_mix, cycles, started_at, ended_at, error "
                "FROM loops WHERE user_id=?", (user_id,))
    if not r: return None
    keys = ["status", "target", "current_mix", "cycles", "started_at", "ended_at", "error"]
    return dict(zip(keys, r[0]))

# ============ دوال الاشتراك ============
def get_subscription(user_id):
    r = db_exec("SELECT user_id, plan, started_at, expires_at, activated_by, created_at FROM subscriptions WHERE user_id=?", (user_id,))
    if not r: return None
    keys = ["user_id", "plan", "started_at", "expires_at", "activated_by", "created_at"]
    return dict(zip(keys, r[0]))

def is_sub_active(user_id):
    if user_id == ADMIN_ID:
        return True, None
    sub = get_subscription(user_id)
    if not sub: return False, None
    try:
        exp = datetime.fromisoformat(sub['expires_at'])
        if datetime.now() < exp:
            return True, sub
        return False, sub
    except Exception:
        return False, sub

def sub_remaining_text(sub):
    try:
        exp = datetime.fromisoformat(sub['expires_at'])
        delta = exp - datetime.now()
        if delta.total_seconds() <= 0:
            return "منتهي"
        days = delta.days
        hours = delta.seconds // 3600
        mins = (delta.seconds % 3600) // 60
        parts = []
        if days > 0: parts.append(f"{days} يوم")
        if hours > 0: parts.append(f"{hours} ساعة")
        if mins > 0 and days == 0: parts.append(f"{mins} دقيقة")
        return " و ".join(parts) if parts else "أقل من دقيقة"
    except Exception:
        return "غير معروف"

def activate_subscription(user_id, plan_key, activated_by):
    if plan_key not in SUBSCRIPTION_PLANS:
        return False, "نوع اشتراك غير صحيح"
    plan = SUBSCRIPTION_PLANS[plan_key]
    now = datetime.now()

    existing = get_subscription(user_id)
    start_from = now
    if existing:
        try:
            exp = datetime.fromisoformat(existing['expires_at'])
            if exp > now:
                start_from = exp
        except Exception:
            pass

    expires = start_from + timedelta(days=plan['days'])

    db_exec("""INSERT OR REPLACE INTO subscriptions
        (user_id, plan, started_at, expires_at, activated_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, plan_key, now.isoformat(), expires.isoformat(), activated_by, now.isoformat()))

    return True, expires

def cancel_subscription(user_id):
    db_exec("DELETE FROM subscriptions WHERE user_id=?", (user_id,))
    return True

def get_active_subs_count():
    now = datetime.now().isoformat()
    r = db_exec("SELECT COUNT(*) FROM subscriptions WHERE expires_at > ?", (now,))
    return r[0][0] if r else 0

# ============ شريط التقدم ============
def progress_bar(pct, length=12):
    filled = int(length * pct / 100)
    return "🟩" * filled + "⬜" * (length - filled)

MAIN_BUTTONS = ["🚀 ابدأ الشغل", "📈 وضعي الحالي", "📩 كلم المطور", "🛠 لوحة التحكم", "🏠 الرئيسية"]
ADMIN_ONLY_PREFIXES = ("admin_",)

# ============ تسجيل المستخدمين ============
def ensure_user_id(user_id, username="", first_name=""):
    db_exec("INSERT OR IGNORE INTO users (user_id, username, first_name, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username or "", first_name or "", datetime.now().isoformat()))

def register_user(user):
    ensure_user_id(user.id, user.username, user.first_name)
    db_exec("UPDATE users SET username=?, first_name=? WHERE user_id=?",
            (user.username or "", user.first_name or "", user.id))

def display_name(first_name, username, uid):
    name = (first_name or "").strip()
    un = f"@{username}" if username else ""
    if name and un: return f"{name} ({un})"
    return name or un or f"مستخدم {uid}"

def user_link(uid, first_name, username):
    label = (first_name or "").strip() or (f"@{username}" if username else str(uid))
    return f'<a href="tg://user?id={uid}">{esc(label)}</a>'

# ============ كلاس الجهاز الوهمي ============
class FakeDevice:
    @staticmethod
    def generate():
        return {
            "device_id": "a1b2c3d4e5f60718",
            "udid": "abcdef1234567890",
            "model": "SM-A546E",
            "model_name": "Galaxy A54",
            "os_version": "14",
            "os_build": "UP1A.123456.001",
            "manufacturer": "samsung",
        }

# ============ كلاس API اتصالات ============
class EtisalatAPI:
    def __init__(self):
        self._http = requests.Session()
        self.auth_token = None
        self.current_dial = None
        self.device = FakeDevice.generate()

    def _h(self):
        h = {
            "applicationVersion": "2", "applicationName": "MAB",
            "Accept": "text/xml", "APP-BuildNumber": "964",
            "APP-Version": "27.0.0", "OS-Type": "Android",
            "OS-Version": self.device["os_version"],
            "APP-STORE": "GOOGLE", "Is-Corporate": "false",
            "Content-Type": "text/xml; charset=UTF-8",
            "Host": "mab.etisalat.com.eg:11003", "Connection": "Keep-Alive",
            "User-Agent": f"okhttp/5.0.0-alpha.11 ({self.device['manufacturer']}; {self.device['model']})",
        }
        if self.auth_token:
            h["auth"] = f"Bearer {self.auth_token}"
        return h

    def call(self, method, path, body=None, req=None, retry=2):
        for attempt in range(retry + 1):
            url = f"{BASE_URL}{path}"
            headers = self._h()
            try:
                if method.upper() == "GET":
                    return self._http.get(url, headers=headers, params={"req": req}, timeout=25)
                return self._http.post(url, headers=headers, data=body, timeout=25)
            except Exception:
                if attempt < retry:
                    time.sleep(3)
                    continue
                return None

    def login(self, email, password):
        email, password = (email or "").strip(), (password or "").strip()
        if not email or not password: return False
        basic = base64.b64encode(f"{email}:{password}".encode()).decode()
        h = self._h()
        h["Authorization"] = f"Basic {basic}"
        body = (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            "<loginRequest>"
            f"<deviceId>{self.device['device_id']}</deviceId>"
            "<firstLoginAttempt>true</firstLoginAttempt>"
            f"<modelType>{self.device['model']}</modelType><osVersion>{self.device['os_version']}</osVersion>"
            f"<platform>Android</platform><udid>{self.device['udid']}</udid>"
            "</loginRequest>"
        )
        try:
            r = self._http.post(f"{BASE_URL}/authentication/loginWithPlan", headers=h, data=body, timeout=25)
        except Exception:
            return False
        if not r or r.status_code != 200 or "<status>true" not in r.text:
            return False
        self.auth_token = r.headers.get("auth", "")
        try:
            p = self.auth_token.split(".")
            pl = p[1] + "=" * (4 - len(p[1]) % 4)
            d = json.loads(base64.urlsafe_b64decode(pl))
            self.current_dial = d.get("dial")
            if not self.current_dial:
                self.current_dial = d.get("selectedDial")
        except Exception:
            pass
        return True

    def get_status_and_child(self):
        if not self.current_dial: return None, 0, None
        xml_body = (
            "<dialAndLanguageRequest><segmentId>XRP</segmentId>"
            f"<subscriberNumber>{self.current_dial}</subscriberNumber>"
            "<language>1</language><shortCode>ALFTL</shortCode>"
            "</dialAndLanguageRequest>"
        )
        r = self.call("GET", "/servicemanagement/getGenericConsumptionsV2", req=xml_body)
        if not r or r.status_code != 200: return None, 0, None
        try:
            root = ET.fromstring(r.text)
            p_id = root.findtext(".//ratePlanConsumption/productId") or "Unknown"

            r_mix = 0
            for cons in root.findall(".//newMeterConsumption/consumptionList/consumption"):
                ut = (cons.findtext("unitType") or "").upper()
                prod = (cons.findtext("productId") or "").upper()
                if "UNITS" in ut or "MIX" in ut or "XRP" in prod:
                    try: r_mix = int(cons.findtext("remainingValue", "0") or 0)
                    except ValueError: r_mix = 0
                    break
            if r_mix == 0:
                vals = []
                for cons in root.findall(".//newMeterConsumption/consumptionList/consumption"):
                    try: vals.append(int(cons.findtext("remainingValue", "0") or 0))
                    except Exception: pass
                if vals: r_mix = max(vals)

            child_number = None
            for item in root.findall(".//fafNumberList/fafNumber/value"):
                if item.text != self.current_dial: child_number = item.text
            return p_id, r_mix, child_number
        except Exception:
            return None, 0, None

    def get_balance(self, product, target_dial):
        req = (f"<transferInquiryRequest><productId>{product}</productId>"
               f"<subscriberNumber>{self.current_dial}</subscriberNumber>"
               f"<language>1</language></transferInquiryRequest>")
        r = self.call("GET", "/emerald/transferInquiry", req=req)
        if not r or r.status_code != 200:
            return 0
        try:
            root = ET.fromstring(r.text)
            if root.findtext("status") != "true":
                return 0
            for a in root.findall(".//assigned"):
                if a.findtext("dial") == str(target_dial):
                    return int(float(a.findtext("value", "0")))
        except Exception:
            pass
        return 0

    def detect_plan(self):
        req = (f"<hekayaPartialAllowedMovesRequest>"
               f"<subscriberNumber>{self.current_dial}</subscriberNumber>"
               f"<language>1</language>"
               f"<category>DigitalRPGroup_ALLOWED_HEKAYA_MOVES</category>"
               f"</hekayaPartialAllowedMovesRequest>")
        r = self.call("GET", "/HekayaPartial/inquireAllowedMovesByCategory", req=req)
        if not r or r.status_code != 200:
            return None
        try:
            root = ET.fromstring(r.text)
            if root.findtext("status") != "true":
                return None
            names = [p.text or "" for p in root.findall(".//productName")]
            for plan in ["270", "180", "120", "92", "69", "52"]:
                if not any(plan in n for n in names):
                    return plan
        except Exception:
            pass
        return None

    def change_plan(self, plan_name, plan_id="", operation="FULL_MIGRATE"):
        xml_body = (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            "<migrateRequest><addonName></addonName><oMSRatePlan>true</oMSRatePlan>"
            f"<operation>{operation}</operation>"
            f"<productName>{plan_name}</productName>"
            f"<ratePlanID>{plan_id}</ratePlanID>"
            f"<subscriberNumber>{self.current_dial}</subscriberNumber>"
            "</migrateRequest>"
        )
        r = self.call("POST", "/HekayaPartial/migrate", body=xml_body)
        if not r: return False
        return r.status_code == 200 and "<status>true" in r.text

    def transfer_mix(self, sender_number, receiver_number, quota_amount, product_name):
        try: quota = int(quota_amount)
        except Exception: return False
        xml_body = (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            "<newFamilyTransferRequest><distribute>false</distribute>"
            f"<msisdn>{sender_number}</msisdn>"
            f"<productName>{product_name}</productName>"
            f"<quota>{quota}</quota>"
            f"<receiverMsisdn>{receiver_number}</receiverMsisdn>"
            f"<senderMsisdn>{sender_number}</senderMsisdn>"
            "<type>UNITS</type></newFamilyTransferRequest>"
        )
        r = self.call("POST", "/services/newTransfer/v2", body=xml_body)
        if not r: return False
        return r.status_code == 200 and "<status>true" in r.text

    def migrate_harley_mini(self):
        xml_body = (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            "<submitOrderRequest>"
            f"<msisdn>{self.current_dial}</msisdn>"
            "<operation>MIGRATE</operation>"
            "<parameters>"
            "<parameter><name>MI_QUOTA</name><value>300</value></parameter>"
            "<parameter><name>UNIT_QUOTA</name><value>60</value></parameter>"
            "<parameter><name>VALIDITY</name><value>7</value></parameter>"
            "<parameter><name>PRICE</name><value>10.5</value></parameter>"
            "<parameter><name>OFFER_ID</name><value>17537</value></parameter>"
            "</parameters>"
            "<productName>HARLEY_MINI_BUNDLE</productName>"
            "</submitOrderRequest>"
        )
        r = self.call("POST", "/harleyPreset/migrate", body=xml_body)
        if not r: return False, "No response"
        ok = r.status_code == 200 and "<status>true</status>" in r.text
        return ok, (r.text or "")[:300]


# ============ مدير اللوب ============
class LoopManager:
    def __init__(self, bot):
        self.bot = bot
        self.tasks = {}
        self.states = {}
        self.pending_migrations = {}

    def is_running(self, user_id):
        t = self.tasks.get(user_id)
        return t is not None and not t.done()

    def request_stop(self, user_id, reason=None):
        if user_id in self.states:
            self.states[user_id]['stop_requested'] = True
            if reason:
                self.states[user_id]['stop_reason'] = reason
            return True
        return False

    async def _cleanup_admin_msg(self, state):
        admin_msg_id = state.get('admin_msg_id')
        if admin_msg_id:
            try:
                await self.bot.edit_message_reply_markup(chat_id=ADMIN_ID, message_id=admin_msg_id, reply_markup=None)
            except Exception: pass

    async def _cleanup_user_msg(self, state):
        msg_id = state.get('message_id')
        chat_id = state.get('chat_id')
        if msg_id and chat_id:
            try:
                await self.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=None)
            except Exception: pass

    async def start(self, user_id, chat_id, owner_creds, child_creds, target, child_num_input):
        if self.is_running(user_id):
            return False, "عندك عملية شغالة بالفعل"

        active, _ = is_sub_active(user_id)
        if not active:
            return False, "⛔ اشتراكك منتهي — جدد الاشتراك مع الأدمن"

        msg = await self.bot.send_message(chat_id, "⚙️ <b>بنجهز كل حاجة...</b>\n\nالرسالة دي هتتحدث لوحدها.", parse_mode="HTML")
        state = {
            'user_id': user_id, 'chat_id': chat_id, 'message_id': msg.message_id,
            'target': target, 'mix': 0, 'cycle': 0, 'plan': '', 'note': '',
            'stop_requested': False, 'stop_reason': None, 'last_update': 0, 'child_num': child_num_input
        }
        self.states[user_id] = state
        save_loop(user_id, status='running', target=target, current_mix=0, cycles=0, started_at=datetime.now().isoformat(), ended_at=None, error=None)
        self.tasks[user_id] = asyncio.create_task(self._run(owner_creds, child_creds, state))

        return True, "started"

    async def _notify(self, chat_id, text, kb=None):
        try: await self.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
        except Exception as e: logger.warning(f"notify: {e}")

    async def _update_progress(self, state, plan_id, mix, force=False):
        now = time.time()
        if not force and now - state['last_update'] < 1.5:
            return
        state['last_update'] = now
        state['mix'] = mix
        state['plan'] = plan_id

        name = PRODUCTS.get(plan_id, {}).get('name', plan_id if plan_id else "جاري التحديث...")
        target = state['target']

        header = "⚡ <b>الشغل شغال دلوقتي</b>"
        note_line = f"\n<i>{esc(state['note'])}</i>\n" if state.get('note') else ""

        pct = min(100, (mix / target * 100) if target else 0)
        text = (
            f"{header}\n\n"
            f"🔄 اللفة: <code>{state['cycle']}</code>\n"
            f"📦 النظام: <b>{esc(name)}</b>\n"
            f"💎 الميكس: <code>{mix:,}</code> / <code>{target:,}</code>\n"
            f"{progress_bar(pct)} <b>{pct:.1f}%</b>\n"
            f"{note_line}\n"
            f"👤 المستخدم: <code>{state['user_id']}</code>"
        )

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 وقّف الشغل", callback_data=f"stoploop_{state['user_id']}")]])
        try:
            await self.bot.edit_message_text(text, chat_id=state['chat_id'], message_id=state['message_id'], parse_mode="HTML", reply_markup=kb)
        except BadRequest: pass
        except Exception as e: logger.warning(f"edit_progress: {e}")

    async def _find_balance(self, sessions, target_dial):
        for p in SEARCH_ORDER:
            for session in sessions:
                if not session.auth_token: continue
                val = await asyncio.to_thread(session.get_balance, p, target_dial)
                if val > 0:
                    return p, val
        return None, 0

    async def _migrate_strong(self, owner, target, state, stop_flag):
        state['note'] = f"⚡ بنحول النظام لـ {target}"
        await self._update_progress(state, target, state.get('mix', 0), force=True)

        p = PRODUCTS[target]
        checks = 0
        start_time = time.time()

        while not stop_flag():
            await asyncio.to_thread(owner.change_plan, p['name'], p['rate_plan_id'])

            for _ in range(90):
                if stop_flag(): return False
                plan = await asyncio.to_thread(owner.detect_plan)
                if plan == target:
                    return True

                checks += 1
                el = int(time.time() - start_time)
                if el % 5 == 0:
                    state['note'] = f"⏳ مستنيين النظام الجديد...\n🕐 {el}ث (فحص {checks})"
                    await self._update_progress(state, target, state.get('mix', 0), force=True)

                await asyncio.sleep(2)

        return False

    async def _child_sweep_single(self, owner, child, child_num, state, stop_flag):
        state['note'] = "⚡ بنسحب من الفرد للأونر"
        await self._update_progress(state, state['plan'], state.get('mix', 0), force=True)

        while not stop_flag():
            product, amount = await self._find_balance([child, owner], child_num)
            if not product or amount == 0:
                return True

            sent = False
            if child.auth_token:
                if await asyncio.to_thread(child.transfer_mix, child_num, owner.current_dial, amount, product):
                    sent = True

            if not sent and owner.auth_token:
                if await asyncio.to_thread(owner.transfer_mix, child_num, owner.current_dial, amount, product):
                    sent = True

            await asyncio.sleep(4)
            _, remaining = await self._find_balance([child, owner], child_num)
            if remaining == 0:
                return True

            await asyncio.sleep(15)

        return True

    async def _wait_for_bonus(self, child, owner, child_num, expected, state, stop_flag):
        state['note'] = f"🎁 مستنيين البونص (~{expected})"
        await self._update_progress(state, state['plan'], state.get('mix', 0), force=True)

        start = time.time()
        last_shown = -30
        while not stop_flag():
            _, amt = await self._find_balance([child, owner], child_num)

            if amt >= expected * 0.8:
                return True

            el = int(time.time() - start)
            if el - last_shown >= 30:
                state['note'] = f"🎁 مستنيين البونص (~{expected})\n🕐 عدّى {el}ث..."
                await self._update_progress(state, state['plan'], state.get('mix', 0), force=True)
                last_shown = el

            await asyncio.sleep(2)
        return False

    async def _owner_sweep_split(self, owner, child_num, state, stop_flag, label="Owner → Child"):
        state['note'] = f"💸 {label} [تقسيم 30k]"
        await self._update_progress(state, state['plan'], state.get('mix', 0), force=True)

        total_sent = 0
        zero_confirmations = 0

        while not stop_flag():
            product, amount = await self._find_balance([owner], owner.current_dial)

            if not product or amount == 0:
                state['note'] = "🔍 بنتأكد إن الرصيد صفر..."
                await self._update_progress(state, state['plan'], total_sent, force=True)
                await asyncio.sleep(4)
                product2, amount2 = await self._find_balance([owner], owner.current_dial)
                if not product2 or amount2 == 0:
                    zero_confirmations += 1
                    if zero_confirmations >= 2:
                        return True
                    continue
                else:
                    amount = amount2
                    product = product2
                    zero_confirmations = 0

            chunk = min(amount, 30000)
            state['note'] = f"💸 بنبعت {chunk:,} للفرد..."
            await self._update_progress(state, state['plan'], amount, force=True)

            success = False
            for t in range(2):
                if stop_flag(): return False
                if await asyncio.to_thread(owner.transfer_mix, owner.current_dial, child_num, chunk, product):
                    success = True
                    break
                if t == 0:
                    await asyncio.sleep(2)

            if success:
                total_sent += chunk
                await asyncio.sleep(4)
            else:
                await asyncio.sleep(3)

        return False

    async def _verify_child_received(self, child, owner, child_num, expected_min, state, stop_flag):
        state['note'] = "🔒 بنتأكد إن الفرد استلم"
        await self._update_progress(state, state['plan'], state.get('mix', 0), force=True)

        while not stop_flag():
            await asyncio.sleep(8)
            _, child_amt = await self._find_balance([child, owner], child_num)

            if child_amt >= expected_min:
                return True

            _, owner_amt = await self._find_balance([owner], owner.current_dial)
            if owner_amt >= expected_min:
                product = SEARCH_ORDER[0]
                for p in SEARCH_ORDER:
                    if await asyncio.to_thread(owner.get_balance, p, owner.current_dial) > 0:
                        product = p
                        break
                chunk = min(owner_amt, 30000)
                state['note'] = f"🔒 بنتأكد إن الفرد استلم\nبنعيد تحويل {chunk:,} للفرد..."
                await self._update_progress(state, state['plan'], state.get('mix', 0), force=True)
                await asyncio.to_thread(owner.transfer_mix, owner.current_dial, child_num, chunk, product)

            await asyncio.sleep(20)
        return False

    async def _run(self, owner_creds, child_creds, state):
        user_id = state['user_id']
        child_num = state['child_num']
        stop_flag = lambda: state['stop_requested']

        try:
            owner = EtisalatAPI()
            if not await asyncio.to_thread(owner.login, *owner_creds):
                save_loop(user_id, status='error', error='فشل دخول الأونر', ended_at=datetime.now().isoformat())
                await self._cleanup_admin_msg(state)
                await self._cleanup_user_msg(state)
                await self._notify(state['chat_id'], "❌ <b>دخول الأونر فشل</b>")
                return

            child = EtisalatAPI()
            if not await asyncio.to_thread(child.login, *child_creds):
                save_loop(user_id, status='error', error='فشل دخول الفرد', ended_at=datetime.now().isoformat())
                await self._cleanup_admin_msg(state)
                await self._cleanup_user_msg(state)
                await self._notify(state['chat_id'], "❌ <b>دخول الفرد فشل</b>")
                return

            current_plan = await asyncio.to_thread(owner.detect_plan)
            if not current_plan:
                save_loop(user_id, status='error', error='فشل قراءة النظام', ended_at=datetime.now().isoformat())
                await self._cleanup_admin_msg(state)
                await self._cleanup_user_msg(state)
                await self._notify(state['chat_id'], "❌ <b>مقدرناش نقرأ نظام الأونر</b>")
                return

            if current_plan != "270":
                await self._owner_sweep_split(owner, child_num, state, stop_flag, label="حماية الرصيد: الأونر -> الفرد")
                if stop_flag(): return await self._finish_stopped(state)

                if not await self._migrate_strong(owner, "270", state, stop_flag):
                    save_loop(user_id, status='error', error='فشل ضبط النظام الأولي 270', ended_at=datetime.now().isoformat())
                    await self._cleanup_admin_msg(state)
                    await self._cleanup_user_msg(state)
                    return await self._notify(state['chat_id'], "❌ <b>الترقية لنظام 270 (التهيئة) فشلت</b>")

                state['note'] = "⏳ بنستنى 5 ثواني لاستقرار النظام..."
                await self._update_progress(state, "270", state.get('mix', 0), force=True)
                await asyncio.sleep(5)

            target = state['target']

            _, o_mix = await self._find_balance([owner], owner.current_dial)
            _, c_mix = await self._find_balance([owner, child], child_num)
            current_total = max(o_mix, c_mix)

            if current_total > 0:
                await self._notify(state['chat_id'],
                    f"✅ <b>لقينا ميكسات موجودة</b>\n\n"
                    f"💎 الميكس الحالي: <code>{current_total:,}</code>\n"
                    f"🎯 الهدف: <code>{target:,}</code>\n\n"
                    f"⏳ هنكمل اللوب من هنا من غير تصفير...")
                await asyncio.sleep(2)

            while not stop_flag():
                state['cycle'] += 1
                current_plan = await asyncio.to_thread(owner.detect_plan)

                if not current_plan:
                    await asyncio.sleep(5)
                    continue

                target_plan = "180" if current_plan == "270" else "270"

                await self._owner_sweep_split(owner, child_num, state, stop_flag, label="حماية الرصيد: الأونر -> الفرد")
                if stop_flag(): break

                if not await self._migrate_strong(owner, target_plan, state, stop_flag):
                    save_loop(user_id, status='error', error='فشل تحويل النظام', ended_at=datetime.now().isoformat())
                    await self._cleanup_admin_msg(state)
                    await self._cleanup_user_msg(state)
                    return await self._notify(state['chat_id'], "❌ <b>تحويل النظام فشل — وقفنا</b>")

                state['note'] = "⏳ بنستنى 5 ثواني لاستقرار النظام..."
                await self._update_progress(state, target_plan, current_total, force=True)
                await asyncio.sleep(5)

                if not await self._child_sweep_single(owner, child, child_num, state, stop_flag):
                    pass

                expected = 1300 if target_plan == "270" else 800
                await self._wait_for_bonus(child, owner, child_num, expected, state, stop_flag)
                if stop_flag(): break

                if not await self._owner_sweep_split(owner, child_num, state, stop_flag, label="الأونر -> الفرد"):
                    pass

                await self._verify_child_received(child, owner, child_num, 100, state, stop_flag)
                if stop_flag(): break

                _, o_mix = await self._find_balance([owner], owner.current_dial)
                _, c_mix = await self._find_balance([owner, child], child_num)
                current_total = max(o_mix, c_mix)
                state['mix'] = current_total

                await self._update_progress(state, target_plan, current_total, force=True)

                if current_total >= target:
                    await self._child_sweep_single(owner, child, child_num, state, stop_flag)

                    _, final_mix = await self._find_balance([owner], owner.current_dial)
                    _, child_rem = await self._find_balance([owner, child], child_num)

                    if stop_flag(): return await self._finish_stopped(state)
                    return await self._finish_success(state, max(final_mix, current_total), child_rem == 0)

            await self._finish_stopped(state)

        except Exception as e:
            logger.exception(f"Loop error user {user_id}")
            save_loop(user_id, status='error', error=str(e)[:200], ended_at=datetime.now().isoformat())
            await self._cleanup_admin_msg(state)
            await self._cleanup_user_msg(state)
            await self._notify(state['chat_id'], f"❌ <b>حصل خطأ مش متوقع:</b>\n<code>{esc(str(e)[:300])}</code>")
        finally:
            self.tasks.pop(user_id, None)

    async def _finish_success(self, state, mix, child_zero=True):
        save_loop(state['user_id'], status='completed', current_mix=mix, cycles=state['cycle'], ended_at=datetime.now().isoformat())
        await self._cleanup_admin_msg(state)
        await self._cleanup_user_msg(state)

        child_line = "✅ كل الميكسات عند الأونر (الفرد = 0)" if child_zero else "⚠️ الفرد لسه ظاهر عنده ميكسات — راجع حالته"
        text = (f"🎉 <b>مبرووك يا وحش!</b>\n\n"
                f"تم فك ليمت الفرد بنجاح!\n"
                f"عِيش، ليمت الفرد اتكسر في ثواني! 😎🔥\n\n"
                f"💎 الميكس اللي جمعناه: <code>{mix:,}</code>\n"
                f"🔁 عدد اللفات: <code>{state['cycle']}</code>\n{child_line}\n\n"
                f"👨‍💻 المطور: {DEVELOPER}\n"
                f"✈️ اليوزر: @{DEV_USERNAME}")
        try: await self.bot.edit_message_text(text, chat_id=state['chat_id'], message_id=state['message_id'], parse_mode="HTML")
        except Exception: await self._notify(state['chat_id'], text)

        uid = state['user_id']
        self.states.pop(uid, None)

        u = get_user(uid)
        if u and u.get('child_email'):
            self.pending_migrations[uid] = {
                'child_email': u['child_email'],
                'child_pass': u['child_pass'],
            }

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ أيوه، حوّل الفرد", callback_data=f"migyes_{uid}"),
            InlineKeyboardButton("❌ لأ", callback_data=f"migno_{uid}"),
        ]])
        await self._notify(state['chat_id'],
            "🔄 <b>خلصنا الشغل بنجاح!</b>\n\nتحب نحول حساب الفرد لنظام ميني حكاية 10.5 على طول؟", kb)

        clear_user_creds(uid)

    async def _finish_stopped(self, state):
        save_loop(state['user_id'], status='stopped', current_mix=state.get('mix', 0), cycles=state.get('cycle', 0), ended_at=datetime.now().isoformat())
        await self._cleanup_admin_msg(state)
        await self._cleanup_user_msg(state)

        reason = state.get('stop_reason')
        if reason == 'subscription_expired':
            text = (f"⛔ <b>اشتراكك انتهى — وقفنا العملية</b>\n\n"
                    f"💎 الميكس: <code>{state.get('mix', 0):,}</code>\n"
                    f"🔁 اللفات: <code>{state.get('cycle', 0)}</code>\n\n"
                    f"📩 جدد اشتراكك مع: @{DEV_USERNAME}")
        else:
            text = f"🛑 <b>وقفنا الشغل</b>\n\n💎 الميكس: <code>{state.get('mix', 0):,}</code>\n🔁 اللفات: <code>{state.get('cycle', 0)}</code>"

        try: await self.bot.edit_message_text(text, chat_id=state['chat_id'], message_id=state['message_id'], parse_mode="HTML")
        except Exception: await self._notify(state['chat_id'], text)
        self.states.pop(state['user_id'], None)
        clear_user_creds(state['user_id'])


# ============ دوال الأزرار الرئيسية ============
def get_main_keyboard(is_admin):
    keyboard = [
        [KeyboardButton("🚀 ابدأ الشغل")],
        [KeyboardButton("📈 وضعي الحالي"), KeyboardButton("📩 كلم المطور")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton("🛠 لوحة التحكم")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def kb_cancel(): return InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]])

def kb_target():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("80,000 💎", callback_data="target_80000"), InlineKeyboardButton("120,000 💎", callback_data="target_120000")],
        [InlineKeyboardButton("150,000 💎", callback_data="target_150000"), InlineKeyboardButton("200,000 💎", callback_data="target_200000")],
        [InlineKeyboardButton("✍️ رقم مخصص", callback_data="target_custom")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")],
    ])

def kb_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 الأعضاء", callback_data="admin_users_0"), InlineKeyboardButton("🔄 الشغل الشغال", callback_data="admin_loops")],
        [InlineKeyboardButton("💳 الاشتراكات", callback_data="admin_subs"), InlineKeyboardButton("📊 تقارير", callback_data="admin_stats")],
        [InlineKeyboardButton("🔍 دور على عضو", callback_data="admin_search"), InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🚫 المحظورين", callback_data="admin_banned"), InlineKeyboardButton("💾 نسخة احتياطية", callback_data="admin_backup")],
        [InlineKeyboardButton("♻️ رجّع نسخة", callback_data="admin_restore")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu")],
    ])

def kb_cancel_admin():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel")]])

def kb_back_admin():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")]])

def kb_sub_plans():
    btns = []
    for key, plan in SUBSCRIPTION_PLANS.items():
        btns.append([InlineKeyboardButton(
            f"{plan['emoji']} {plan['name']} — {plan['price']}ج ({plan['days']} يوم)",
            callback_data=f"subplan_{key}"
        )])
    btns.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_subs")])
    return InlineKeyboardMarkup(btns)

def kb_subscription_gate():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📩 تواصل مع الأدمن", url=f"https://t.me/{DEV_USERNAME}")
    ]])

async def safe_answer(q, *a, **k):
    try: await q.answer(*a, **k)
    except Exception: pass

# ============ بوابة فحص الاشتراك ============
async def gate_message(update, context):
    user = update.effective_user
    register_user(user)
    if user.id == ADMIN_ID: return True
    u = get_user(user.id)
    if u and u['banned']:
        await update.message.reply_text("🚫 أنت محظور من استخدام البوت.", reply_markup=ReplyKeyboardRemove())
        return False
    active, _ = is_sub_active(user.id)
    if not active:
        await show_sub_gate(update.message, context)
        return False
    return True

async def gate_callback(update, context):
    q = update.callback_query
    user = update.effective_user
    register_user(user)
    if user.id == ADMIN_ID: return True
    u = get_user(user.id)
    if u and u['banned']:
        await safe_answer(q, "🚫 أنت محظور", show_alert=True)
        return False
    active, _ = is_sub_active(user.id)
    if not active:
        await safe_answer(q, "⛔ اشتراكك منتهي", show_alert=True)
        try:
            await q.edit_message_text(
                "⛔ <b>لازم تشترك الأول عشان تستخدم البوت</b>\n\n"
                "📅 اليومي بي <b>100ج</b>\n"
                "📆 الأسبوع بي <b>200ج</b>\n"
                "🗓 الشهري بي <b>300ج</b>\n\n"
                f"للتواصل مع الأدمن للاشتراك\n@{DEV_USERNAME}",
                parse_mode="HTML", reply_markup=kb_subscription_gate()
            )
        except Exception: pass
        return False
    return True

async def show_sub_gate(message_obj, context):
    text = (
        "⛔ <b>لازم تشترك الأول عشان تستخدم البوت</b>\n\n"
        "📅 اليومي بي <b>100ج</b>\n"
        "📆 الأسبوع بي <b>200ج</b>\n"
        "🗓 الشهري بي <b>300ج</b>\n\n"
        f"للتواصل مع الأدمن للاشتراك\n@{DEV_USERNAME}"
    )
    try:
        await message_obj.reply_text(text, parse_mode="HTML", reply_markup=kb_subscription_gate())
    except Exception:
        try:
            await context.bot.send_message(message_obj.chat_id, text, parse_mode="HTML", reply_markup=kb_subscription_gate())
        except Exception: pass

# ============ البحث في المستخدمين ============
def search_users(q):
    q = (q or "").strip().lstrip("@")
    if not q: return []
    cols = "user_id, username, first_name, banned"
    if q.isdigit(): return db_exec(f"SELECT {cols} FROM users WHERE user_id=?", (int(q),))
    like = f"%{q.lower()}%"
    return db_exec(f"SELECT {cols} FROM users WHERE LOWER(COALESCE(first_name,'')) LIKE ? OR LOWER(COALESCE(username,'')) LIKE ? LIMIT 10", (like, like))

def build_user_card(uid):
    u = get_user(uid)
    if not u: return None, None
    if uid == ADMIN_ID: st = "👑 أدمن (صلاحيات كاملة)"
    elif u['banned']: st = "🚫 محظور"
    else: st = "👤 عضو"

    running = bool(loop_manager and loop_manager.is_running(uid))
    sub_active, sub = is_sub_active(uid) if uid != ADMIN_ID else (True, None)

    if uid == ADMIN_ID:
        sub_line = "👑 معفي من الاشتراك"
    elif sub_active and sub:
        plan_name = SUBSCRIPTION_PLANS.get(sub['plan'], {}).get('name', sub['plan'])
        sub_line = f"✅ {plan_name} — متبقي {sub_remaining_text(sub)}"
    elif sub:
        sub_line = "❌ منتهي"
    else:
        sub_line = "❌ مفيش اشتراك"

    text = (f"👤 <b>{user_link(uid, u['first_name'], u['username'])}</b>\n"
            f"🔗 اليوزر: {('@' + esc(u['username'])) if u['username'] else 'لا يوجد'}\n"
            f"🆔 الايدي: <code>{uid}</code>\n"
            f"📌 الحالة: {st}\n"
            f"💳 الاشتراك: {sub_line}\n"
            f"📅 انضم: <code>{(u['created_at'] or '')[:16].replace('T', ' ')}</code>\n")
    if running: text += "🟢 <b>عنده عملية شغالة دلوقتي</b>\n"

    btns = [
        [InlineKeyboardButton("✉️ ابعتله رسالة", callback_data=f"admin_dm_{uid}")],
        [InlineKeyboardButton("🗂 إحصائيات عملياته", callback_data=f"admin_user_loops_{uid}")],
    ]
    if running:
        btns.append([InlineKeyboardButton("🛑 وقّف عمليته", callback_data=f"stoploop_{uid}")])
    if uid != ADMIN_ID:
        if sub_active:
            btns.append([InlineKeyboardButton("💳 تمديد/تغيير الاشتراك", callback_data=f"admin_sub_manage_{uid}")])
            btns.append([InlineKeyboardButton("❌ إلغاء الاشتراك", callback_data=f"admin_sub_cancel_{uid}")])
        else:
            btns.append([InlineKeyboardButton("💳 تفعيل اشتراك", callback_data=f"admin_sub_manage_{uid}")])
        btns.append([InlineKeyboardButton("✅ فك الحظر" if u['banned'] else "🚫 حظر", callback_data=f"admin_toggleban_{uid}")])
        btns.append([InlineKeyboardButton("🗑 امسح العضو", callback_data=f"admin_delconfirm_{uid}")])
    btns.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_users_0")])
    return text, InlineKeyboardMarkup(btns)

# ============ Callbacks الاشتراكات (أدمن) ============
async def cb_admin_subs(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    await safe_answer(q)

    active_count = get_active_subs_count()
    total_subs = db_exec("SELECT COUNT(*) FROM subscriptions")[0][0]

    text = (
        f"💳 <b>إدارة الاشتراكات</b>\n\n"
        f"✅ نشطين دلوقتي: <code>{active_count}</code>\n"
        f"📊 إجمالي الاشتراكات: <code>{total_subs}</code>\n\n"
        f"<b>الأسعار:</b>\n"
        f"📅 يومي — 100ج\n"
        f"📆 أسبوعي — 200ج\n"
        f"🗓 شهري — 300ج\n\n"
        f"اختار العملية:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ تفعيل اشتراك", callback_data="admin_sub_activate")],
        [InlineKeyboardButton("👥 المشتركين النشطين", callback_data="admin_sub_list")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")],
    ])
    try: await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception: pass

async def cb_admin_sub_activate(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    await q.answer()
    context.user_data['state'] = 'admin_sub_activate_id'
    await q.edit_message_text(
        "💳 <b>تفعيل اشتراك</b>\n\n"
        "ابعت <b>ID</b> المستخدم اللي عايز تفعله:",
        parse_mode="HTML",
        reply_markup=kb_cancel_admin()
    )

async def cb_admin_sub_manage(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    await safe_answer(q)
    try: uid = int(q.data.split("_")[-1])
    except Exception: return

    u = get_user(uid)
    name = display_name(u['first_name'], u['username'], uid) if u else str(uid)
    sub_active, sub = is_sub_active(uid)

    if sub_active and sub:
        plan_name = SUBSCRIPTION_PLANS.get(sub['plan'], {}).get('name', sub['plan'])
        status_line = f"✅ نشط — {plan_name} — متبقي {sub_remaining_text(sub)}"
    elif sub:
        status_line = "❌ منتهي"
    else:
        status_line = "❌ مفيش اشتراك"

    text = (
        f"💳 <b>اشتراك {esc(name)}</b>\n\n"
        f"📌 الحالة: {status_line}\n\n"
        f"اختار النوع اللي عايز تفعله/تمدده:"
    )
    context.user_data['sub_target_uid'] = uid
    try: await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb_sub_plans())
    except Exception: pass

async def cb_admin_sub_plan_chosen(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    await safe_answer(q)

    plan_key = q.data.split("_", 1)[1]
    uid = context.user_data.get('sub_target_uid')
    if not uid:
        return await q.edit_message_text("❌ حصل خطأ، ابدأ تاني.", reply_markup=kb_back_admin())

    ok, result = activate_subscription(uid, plan_key, ADMIN_ID)
    if not ok:
        return await q.edit_message_text(f"❌ {result}", reply_markup=kb_back_admin())

    plan = SUBSCRIPTION_PLANS[plan_key]
    expires_str = result.strftime('%Y-%m-%d %H:%M')

    u = get_user(uid)
    name = display_name(u['first_name'], u['username'], uid) if u else str(uid)

    try:
        await context.bot.send_message(
            uid,
            f"🎉 <b>تم تفعيل اشتراكك بنجاح!</b>\n\n"
            f"💳 النوع: <b>{plan['name']}</b>\n"
            f"💰 السعر: <b>{plan['price']}ج</b>\n"
            f"📅 ينتهي: <code>{expires_str}</code>\n\n"
            f"🚀 استمتع بالبوت!\n\n"
            f"👨‍💻 المطور: {DEVELOPER}\n"
            f"✈️ اليوزر: @{DEV_USERNAME}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"sub notify: {e}")

    await q.edit_message_text(
        f"✅ <b>تم تفعيل الاشتراك</b>\n\n"
        f"👤 العضو: {esc(name)}\n"
        f"💳 النوع: {plan['name']}\n"
        f"💰 السعر: {plan['price']}ج\n"
        f"📅 ينتهي: <code>{expires_str}</code>\n\n"
        f"📩 اتبعتله إشعار.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 عرض العضو", callback_data=f"admin_user_{uid}")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_subs")],
        ])
    )

async def cb_admin_sub_cancel(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    try: uid = int(q.data.split("_")[-1])
    except Exception: return

    if loop_manager.is_running(uid):
        loop_manager.request_stop(uid, reason='subscription_expired')

    cancel_subscription(uid)

    try:
        await context.bot.send_message(
            uid,
            "⛔ <b>تم إلغاء اشتراكك</b>\n\n"
            f"للاشتراك تاني كلم الأدمن: @{DEV_USERNAME}",
            parse_mode="HTML"
        )
    except Exception: pass

    await safe_answer(q, "✅ اتلغى الاشتراك", show_alert=True)
    q.data = f"admin_user_{uid}"
    await cb_admin_user(update, context)

async def cb_admin_sub_list(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    await safe_answer(q)

    now = datetime.now().isoformat()
    rows = db_exec(
        "SELECT s.user_id, s.plan, s.expires_at, u.username, u.first_name "
        "FROM subscriptions s LEFT JOIN users u ON s.user_id = u.user_id "
        "WHERE s.expires_at > ? ORDER BY s.expires_at ASC LIMIT 30",
        (now,)
    )

    text = f"👥 <b>المشتركين النشطين ({len(rows)})</b>\n\n"
    btns = []
    for uid, plan, exp, uname, fname in rows:
        plan_name = SUBSCRIPTION_PLANS.get(plan, {}).get('name', plan)
        try:
            exp_dt = datetime.fromisoformat(exp)
            exp_str = exp_dt.strftime('%m-%d %H:%M')
        except Exception:
            exp_str = exp[:16]
        name = display_name(fname, uname, uid)
        text += f"• <b>{esc(name)}</b> — {plan_name} — ⏰ {exp_str}\n"
        btns.append([InlineKeyboardButton(f"👤 {name[:40]}", callback_data=f"admin_user_{uid}")])

    if not rows:
        text += "مفيش مشتركين نشطين دلوقتي."

    btns.append([InlineKeyboardButton("🔄 تحديث", callback_data="admin_sub_list")])
    btns.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_subs")])

    try: await q.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    except Exception: pass

# ============ باقي Callbacks الأدمن ============
async def cb_admin_user_loops(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    try: uid = int(q.data.split("_")[-1])
    except Exception: return await safe_answer(q)
    await safe_answer(q)

    u = get_user(uid)
    name = display_name(u['first_name'], u['username'], uid) if u else str(uid)

    stats = db_exec("SELECT status, COUNT(*), SUM(target) FROM loops WHERE user_id=? GROUP BY status", (uid,))
    total_runs = sum(s[1] for s in stats) if stats else 0
    success = sum(s[1] for s in stats if s[0] == 'completed') if stats else 0
    failed = sum(s[1] for s in stats if s[0] == 'error') if stats else 0
    stopped = sum(s[1] for s in stats if s[0] == 'stopped') if stats else 0

    text = f"🗂 <b>إحصائيات عمليات {esc(name)}</b>\n\n"
    text += f"إجمالي العمليات: <b>{total_runs}</b>\n"
    text += f"✅ ناجحة: <b>{success}</b>\n"
    text += f"❌ فاشلة: <b>{failed}</b>\n"
    text += f"🛑 متوقفة: <b>{stopped}</b>\n\n"
    text += "<b>آخر العمليات:</b>\n"

    loops = db_exec("SELECT status, target, current_mix, cycles, started_at, error FROM loops WHERE user_id=? ORDER BY started_at DESC LIMIT 10", (uid,))

    if not loops:
        text += "مفيش عمليات مسجلة."
    else:
        for i, (status, target, current_mix, cycles, started_at, error) in enumerate(loops, 1):
            status_map = {'completed': '✅ ناجحة', 'stopped': '🛑 متوقفة', 'error': '❌ فاشلة', 'running': '🔄 شغالة'}
            status_ar = status_map.get(status, status)
            start_txt = (started_at or '')[:16].replace('T', ' ')
            text += f"<b>{i}.</b> {status_ar} | 🕐 <code>{start_txt}</code>\n"
            text += f"   🎯 الهدف: {target:,} | 💎 وصل: {current_mix:,} | 🔄 {cycles} لفة\n"
            if error:
                text += f"   ⚠️ {esc(error[:60])}\n"
            text += "─────────────────\n"

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للعضو", callback_data=f"admin_user_{uid}")]])
    try: await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception: pass

async def cb_admin_user(update, context):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await query.answer("❌", show_alert=True)
    try: uid = int(query.data.split("_")[-1])
    except Exception: return await safe_answer(query)
    text, kb = build_user_card(uid)
    if not text: return await safe_answer(query, "مش موجود", show_alert=True)
    await safe_answer(query)
    try: await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception: pass

async def cb_admin_users(update, context):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await query.answer("❌", show_alert=True)
    await safe_answer(query)
    try: page = int(query.data.split("_")[-1])
    except Exception: page = 0
    per_page = 8
    total = db_exec("SELECT COUNT(*) FROM users")[0][0]
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    rows = db_exec("SELECT user_id, username, first_name, banned FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (per_page, page * per_page))
    text = (f"👥 <b>الأعضاء</b>\n\n📊 الإجمالي: <code>{total}</code>\n📄 الصفحة: <code>{page+1}/{total_pages}</code>\n\n👑 أدمن • 🚫 محظور • 👤 عضو")
    btns = []
    for uid, uname, fname, banned in rows:
        icon = "👑" if uid == ADMIN_ID else ("🚫" if banned else "👤")
        btns.append([InlineKeyboardButton(f"{icon} {display_name(fname, uname, uid)}"[:60], callback_data=f"admin_user_{uid}")])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin_users_{page-1}"))
    if page < total_pages - 1: nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin_users_{page+1}"))
    if nav: btns.append(nav)
    btns.append([InlineKeyboardButton("🔍 بحث", callback_data="admin_search")])
    btns.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")])
    try: await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    except Exception: pass

async def cb_admin_toggleban(update, context):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await query.answer("❌", show_alert=True)
    try: uid = int(query.data.split("_")[-1])
    except Exception: return
    if uid == ADMIN_ID: return await query.answer("مش ممكن تحظر نفسك", show_alert=True)
    u = get_user(uid)
    if not u: return await query.answer("العضو مش موجود", show_alert=True)
    new_val = 0 if u['banned'] else 1
    db_exec("UPDATE users SET banned=? WHERE user_id=?", (new_val, uid))
    if new_val == 1:
        await query.answer("✅ العضو اتحظر", show_alert=True)
        try: await context.bot.send_message(uid, "🚫 <b>أنت محظور من استخدام البوت.</b>", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        except Exception: pass
    else:
        await query.answer("✅ فكينا الحظر", show_alert=True)
        try: await context.bot.send_message(uid, "✅ <b>تم فك الحظر عنك.</b>", parse_mode="HTML")
        except Exception: pass
    query.data = f"admin_user_{uid}"
    await cb_admin_user(update, context)

async def cb_admin_delconfirm(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    try: uid = int(q.data.split("_")[-1])
    except Exception: return await safe_answer(q)
    u = get_user(uid)
    if not u: return await safe_answer(q, "مش موجود", show_alert=True)
    if uid == ADMIN_ID: return await safe_answer(q, "مش ممكن تمسح الأدمن", show_alert=True)
    await safe_answer(q)
    name = display_name(u['first_name'], u['username'], uid)
    text = f"⚠️ <b>متأكد إنك عايز تمسح</b>\n{esc(name)} (<code>{uid}</code>)؟\n\nهيتمسح كل بياناته وسجل نشاطه واشتراكه."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑 أيوه امسح", callback_data=f"admin_deluser_{uid}")], [InlineKeyboardButton("↩️ لأ", callback_data=f"admin_user_{uid}")]])
    try: await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception: pass

async def cb_admin_deluser(update, context):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await query.answer("❌", show_alert=True)
    try: uid = int(query.data.split("_")[-1])
    except Exception: return
    if uid == ADMIN_ID: return await query.answer("مش ممكن تمسح الأدمن", show_alert=True)
    loop_manager.request_stop(uid)
    db_exec("DELETE FROM users WHERE user_id=?", (uid,))
    db_exec("DELETE FROM loops WHERE user_id=?", (uid,))
    db_exec("DELETE FROM subscriptions WHERE user_id=?", (uid,))
    await safe_answer(query, "🗑 اتمسح")
    query.data = "admin_users_0"
    await cb_admin_users(update, context)

async def cb_admin_banned(update, context):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await query.answer("❌", show_alert=True)
    await safe_answer(query)
    rows = db_exec("SELECT user_id, username, first_name FROM users WHERE banned=1")
    text = f"🚫 <b>إدارة المحظورين ({len(rows)})</b>\n\n"
    btns = []
    for uid, uname, fname in rows[:30]:
        btns.append([InlineKeyboardButton(f"✅ فك حظر {display_name(fname, uname, uid)}"[:60], callback_data=f"admin_toggleban_{uid}")])
    btns.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")])
    if not rows:
        text += "مفيش محظورين دلوقتي."
    try: await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    except Exception: pass

async def cb_admin_loops_live(update, context):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await query.answer("❌", show_alert=True)
    await safe_answer(query)
    active = [(uid, st) for uid, st in loop_manager.states.items() if isinstance(st, dict) and 'user_id' in st and uid != ADMIN_ID]
    text = f"🔄 <b>الشغل الشغال ({len(active)})</b>\n\n"
    btns = []
    for uid, st in active:
        u = get_user(uid)
        name = display_name(u['first_name'], u['username'], uid) if u else str(uid)
        target, mix = st.get('target', 0), st.get('mix', 0)
        pct = min(100, (mix / target * 100) if target else 0)
        text += f"• <b>{esc(name)}</b> — {mix:,}/{target:,} ({pct:.0f}%) • لفة {st.get('cycle', 0)}\n"
        btns.append([InlineKeyboardButton(f"🛑 وقّف {name}"[:60], callback_data=f"stoploop_{uid}")])
    if not active:
        text += "مفيش عمليات شغالة دلوقتي."
    btns.append([InlineKeyboardButton("🔄 حدّث القائمة", callback_data="admin_loops")])
    btns.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")])
    try: await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    except Exception: pass

async def cb_admin_stats(update, context):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await query.answer("❌", show_alert=True)
    await safe_answer(query)
    total_users = db_exec("SELECT COUNT(*) FROM users")[0][0]
    banned = db_exec("SELECT COUNT(*) FROM users WHERE banned=1")[0][0]
    running = len([t for t in loop_manager.tasks.values() if not t.done()])
    completed = db_exec("SELECT COUNT(*) FROM loops WHERE status='completed'")[0][0]
    stopped = db_exec("SELECT COUNT(*) FROM loops WHERE status='stopped'")[0][0]
    errors = db_exec("SELECT COUNT(*) FROM loops WHERE status='error'")[0][0]
    total_mix = db_exec("SELECT COALESCE(SUM(current_mix),0) FROM loops")[0][0]
    active_subs = get_active_subs_count()

    text = (
        "📊 <b>تقارير</b>\n\n"
        f"👥 إجمالي الأعضاء: <code>{total_users}</code>\n"
        f"🚫 محظورين: <code>{banned}</code>\n"
        f"💳 مشتركين نشطين: <code>{active_subs}</code>\n\n"
        f"🔄 شغل شغال دلوقتي: <code>{running}</code>\n"
        f"✅ مكتملة: <code>{completed}</code> • 🛑 متوقفة: <code>{stopped}</code> • ❌ فشلت: <code>{errors}</code>\n"
        f"💎 إجمالي الميكسات المتراكمة: <code>{total_mix:,}</code>\n"
    )
    try: await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb_back_admin())
    except Exception as e: logger.warning(f"cb_admin_stats error: {e}")

async def cb_admin_broadcast(update, context):
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await query.answer("❌", show_alert=True)
    await query.answer()
    context.user_data['state'] = 'broadcast'
    await query.edit_message_text("📢 ابعت الرسالة (نص أو صورة) دلوقتي للجميع.", reply_markup=kb_cancel_admin())

async def cb_admin_search(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    await q.answer()
    context.user_data['state'] = 'admin_search'
    await q.edit_message_text("🔍 ابعت الاسم أو اليوزر أو الايدي:", reply_markup=kb_cancel_admin())

async def cb_admin_backup(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    await safe_answer(q)
    await q.edit_message_text("⏳ <b>بنعمل النسخة الاحتياطية...</b>", parse_mode="HTML")
    try:
        with open(DB_PATH, "rb") as f:
            db_content = f.read()
        filename = f"etisalat_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        document = io.BytesIO(db_content)
        document.name = filename
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=document,
            caption="💾 <b>نسخة احتياطية كاملة لقاعدة البيانات</b>\n\n"
                    f"🕐 التاريخ: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                    f"📊 الحجم: <code>{len(db_content) / 1024:.1f} KB</code>",
            parse_mode="HTML"
        )
        try: await q.edit_message_text("✅ <b>النسخة الاحتياطية اتبعتت بنجاح!</b>", parse_mode="HTML")
        except Exception: pass
    except Exception as e:
        logger.exception("backup error")
        try: await q.edit_message_text(f"❌ <b>النسخة الاحتياطية فشلت</b>\n\n<code>{esc(str(e)[:300])}</code>", parse_mode="HTML")
        except Exception: pass

async def cb_admin_restore(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID: return await q.answer("❌", show_alert=True)
    await safe_answer(q)
    context.user_data['state'] = 'admin_restore_backup'
    await q.edit_message_text(
        "♻️ <b>رجّع نسخة احتياطية</b>\n\n"
        "📎 ابعت ملف قاعدة البيانات (<code>.db</code>) عشان نرجّعها.\n\n"
        "⚠️ <b>تحذير:</b> الرجوع هيستبدل كل البيانات الحالية!",
        parse_mode="HTML", reply_markup=kb_cancel_admin()
    )

# ============ شاشة الاشتراك العامة ============
async def show_subscription_screen(update, context):
    text = (
        "⛔ <b>لازم تشترك الأول عشان تستخدم البوت</b>\n\n"
        "📅 اليومي بي <b>100ج</b>\n"
        "📆 الأسبوع بي <b>200ج</b>\n"
        "🗓 الشهري بي <b>300ج</b>\n\n"
        f"للتواصل مع الأدمن للاشتراك\n@{DEV_USERNAME}"
    )
    if update.callback_query:
        try: await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb_subscription_gate())
        except Exception: pass
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb_subscription_gate())

# ============ معالجات الأوامر ============
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    u = get_user(user.id)
    if u and u['banned'] and user.id != ADMIN_ID:
        await update.message.reply_text("🚫 أنت محظور.", reply_markup=ReplyKeyboardRemove()); return
    if user.id != ADMIN_ID:
        active, _ = is_sub_active(user.id)
        if not active:
            await show_subscription_screen(update, context)
            return
    await show_main_menu(update, context)

async def show_main_menu(update, context):
    user = update.effective_user
    is_admin = user.id == ADMIN_ID
    context.user_data['kb_removed'] = False

    sub_line = ""
    if not is_admin:
        active, sub = is_sub_active(user.id)
        if active and sub:
            sub_line = f"\n💳 اشتراكك: <b>{SUBSCRIPTION_PLANS.get(sub['plan'], {}).get('name', sub['plan'])}</b> — متبقي {sub_remaining_text(sub)}\n"

    text = (f"🏠 <b>الرئيسية</b>\n\nيا هلا <b>{esc(user.first_name or 'صديقي')}</b> 👋{sub_line}\n\nاختار من الأزرار تحت:")
    reply_kb = get_main_keyboard(is_admin)
    if update.callback_query:
        try: await update.callback_query.edit_message_text(text, parse_mode="HTML")
        except BadRequest: pass
        await context.bot.send_message(user.id, "👇 القائمة الرئيسية تحت", reply_markup=reply_kb)
    else:
        await context.bot.send_message(user.id, text, parse_mode="HTML", reply_markup=reply_kb)

async def show_admin_panel(update, context):
    user = update.effective_user
    if user.id != ADMIN_ID:
        if update.callback_query: await update.callback_query.answer("❌", show_alert=True)
        else: await update.message.reply_text("❌"); return
    context.user_data['state'] = None
    today = datetime.now().strftime('%Y-%m-%d')
    total = db_exec("SELECT COUNT(*) FROM users")[0][0]
    new_today = db_exec("SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (today + '%',))[0][0]
    active = len([t for t in loop_manager.tasks.values() if not t.done()])
    active_subs = get_active_subs_count()
    text = ("🛠 <b>لوحة التحكم</b>\n\n"
            f"👥 الأعضاء: <code>{total}</code> (جداد: <code>{new_today}</code>)\n"
            f"💳 مشتركين نشطين: <code>{active_subs}</code>\n"
            f"🔄 شغل شغال: <code>{active}</code>")
    kb = kb_admin()
    if update.callback_query:
        try: await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        except BadRequest: pass
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 <code>{update.effective_user.id}</code>", parse_mode="HTML")

async def cmd_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        return await update.message.reply_text("👑 أنت الأدمن — معفي من الاشتراك.")
    active, sub = is_sub_active(user.id)
    if active and sub:
        plan_name = SUBSCRIPTION_PLANS.get(sub['plan'], {}).get('name', sub['plan'])
        try: exp_str = datetime.fromisoformat(sub['expires_at']).strftime('%Y-%m-%d %H:%M')
        except Exception: exp_str = sub['expires_at']
        await update.message.reply_text(
            f"💳 <b>اشتراكك الحالي</b>\n\n"
            f"📌 النوع: <b>{plan_name}</b>\n"
            f"📅 ينتهي: <code>{exp_str}</code>\n"
            f"⏰ متبقي: <b>{sub_remaining_text(sub)}</b>",
            parse_mode="HTML"
        )
    else:
        await show_subscription_screen(update, context)

# ============ معالج الرسائل النصية ============
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_ID

    st0 = context.user_data.get('state') or ''
    media_ok = st0 in ('broadcast', 'admin_restore_backup') or st0.startswith('admin_dm_')
    if not text and not media_ok: return

    register_user(update.effective_user)
    if not is_admin:
        u = get_user(user_id)
        if u and u['banned']:
            await update.message.reply_text("🚫 أنت محظور من استخدام البوت.", reply_markup=ReplyKeyboardRemove())
            return

    if text == "🚀 ابدأ الشغل":
        if not is_admin:
            active, _ = is_sub_active(user_id)
            if not active:
                return await show_subscription_screen(update, context)
        context.user_data['action'] = 'loop'
        context.user_data['state'] = 'setup_owner_email'
        await update.message.reply_text("📧 اكتب إيميل الأونر:")
        return
    elif text == "📈 وضعي الحالي":
        if not is_admin:
            active, _ = is_sub_active(user_id)
            if not active:
                return await show_subscription_screen(update, context)
        lp = get_loop(user_id)
        if not lp: await update.message.reply_text("مفيش عمليات سابقة.")
        else: await update.message.reply_text(f"📈 الحالة: {lp['status']}\n💎 الميكس: {lp['current_mix']:,} / {lp['target']:,}")
        return
    elif text == "📩 كلم المطور":
        await update.message.reply_text(f"📩 المطور: {DEVELOPER}\n✈️ تواصل: @{DEV_USERNAME}")
        return
    elif text == "🛠 لوحة التحكم" and is_admin:
        await show_admin_panel(update, context)
        return
    elif text == "🏠 الرئيسية":
        await show_main_menu(update, context)
        return

    if not is_admin:
        active, _ = is_sub_active(user_id)
        if not active:
            return await show_subscription_screen(update, context)

    state = context.user_data.get('state')
    if not state: return

    if state == 'setup_owner_email':
        if "@" not in text: return await update.message.reply_text("❌ إيميل غير صحيح.")
        context.user_data['owner_email'] = text
        context.user_data['state'] = 'setup_owner_pass'
        await update.message.reply_text("🔑 اكتب باسورد الأونر:")

    elif state == 'setup_owner_pass':
        context.user_data['owner_pass'] = text
        context.user_data['state'] = 'setup_child_num'
        await update.message.reply_text("📱 اكتب رقم الفرد (11 رقم):")

    elif state == 'setup_child_num':
        child_n = "".join(re.findall(r"\d", text))
        if len(child_n) < 10: return await update.message.reply_text("❌ رقم غير صحيح.")
        if len(child_n) == 11 and child_n.startswith("0"): child_n = child_n[1:]
        context.user_data['child_num'] = child_n
        context.user_data['state'] = 'setup_child_email'
        await update.message.reply_text("📧 اكتب إيميل الفرد:")

    elif state == 'setup_child_email':
        if "@" not in text: return await update.message.reply_text("❌ إيميل غير صحيح.")
        context.user_data['child_email'] = text
        context.user_data['state'] = 'setup_child_pass'
        await update.message.reply_text("🔑 اكتب باسورد الفرد:")

    elif state == 'setup_child_pass':
        context.user_data['child_pass'] = text
        db_exec("UPDATE users SET owner_email=?, owner_pass=?, child_email=?, child_pass=? WHERE user_id=?",
                (context.user_data['owner_email'], b64_enc(context.user_data['owner_pass']), context.user_data['child_email'], b64_enc(context.user_data['child_pass']), user_id))
        context.user_data['state'] = 'setup_target'
        await update.message.reply_text("✅ البيانات اتحفظت.\n🎯 اختار الهدف:", reply_markup=kb_target())

    elif state == 'setup_target':
        try: target = int(text.replace(",", ""))
        except Exception: return await update.message.reply_text("❌ رقم غير صحيح.")
        context.user_data['state'] = None
        u = get_user(user_id)
        ok, msg = await loop_manager.start(user_id, user_id, (u['owner_email'], u['owner_pass']), (u['child_email'], u['child_pass']), target, context.user_data.get('child_num'))
        if not ok: await update.message.reply_text(f"❌ {msg}")

    elif state == 'mig_child_email':
        if "@" not in text: return await update.message.reply_text("❌ إيميل غير صحيح.")
        context.user_data['mig_child_email'] = text
        context.user_data['state'] = 'mig_child_pass'
        return await update.message.reply_text("🔑 اكتب باسورد الفرد:")

    elif state == 'mig_child_pass':
        context.user_data['mig_child_pass'] = text
        uid = context.user_data.get('mig_uid')
        context.user_data['state'] = None
        await update.message.reply_text("⏳ <b>بنسجل الدخول وبنحوّل...</b>", parse_mode="HTML")
        child = EtisalatAPI()
        if not await asyncio.to_thread(child.login, context.user_data['mig_child_email'], context.user_data['mig_child_pass']):
            return await update.message.reply_text("❌ <b>دخول الفرد فشل</b>\n\nاتأكد من البيانات.")
        ok, info = await asyncio.to_thread(child.migrate_harley_mini)
        if ok:
            await update.message.reply_text(
                f"🎉 <b>مبرووك يا وحش!</b>\n\n"
                f"تم فك ليمت الفرد بنجاح!\n"
                f"عِيش، ليمت الفرد اتكسر في ثواني! 😎🔥\n\n"
                f"📱 الرقم: <code>{esc(child.current_dial)}</code>\n\n"
                f"👨‍💻 المطور: {DEVELOPER}\n"
                f"✈️ اليوزر: @{DEV_USERNAME}",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(f"❌ <b>التحويل فشل</b>\n\n<code>{esc(info)}</code>", parse_mode="HTML")
        if uid:
            clear_user_creds(uid)

    elif state == 'admin_sub_activate_id':
        if not is_admin: return
        try: target_uid = int(text)
        except Exception: return await update.message.reply_text("❌ ايدي غير صحيح، ابعت أرقام بس:", reply_markup=kb_cancel_admin())
        ensure_user_id(target_uid)
        context.user_data['sub_target_uid'] = target_uid
        context.user_data['state'] = None
        u = get_user(target_uid)
        name = display_name(u['first_name'], u['username'], target_uid) if u else str(target_uid)
        await update.message.reply_text(
            f"👤 العضو: <b>{esc(name)}</b>\n🆔 <code>{target_uid}</code>\n\n💳 اختار نوع الاشتراك:",
            parse_mode="HTML",
            reply_markup=kb_sub_plans()
        )

    elif state == 'admin_search':
        if not is_admin: return
        context.user_data['state'] = None
        rows = search_users(text)
        if not rows: return await update.message.reply_text("❌ مفيش نتائج.", reply_markup=kb_back_admin())
        if len(rows) == 1:
            card, kb = build_user_card(rows[0][0])
            return await update.message.reply_text(card, parse_mode="HTML", reply_markup=kb)
        btns = [[InlineKeyboardButton(display_name(r[2], r[1], r[0]), callback_data=f"admin_user_{r[0]}")] for r in rows]
        btns.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")])
        await update.message.reply_text(f"🔍 <b>نتائج البحث ({len(rows)})</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif state.startswith('admin_dm_'):
        if not is_admin: return
        try: uid = int(state.split('_')[-1])
        except Exception: return
        context.user_data['state'] = None
        try:
            await context.bot.copy_message(chat_id=uid, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
            await update.message.reply_text("✅ اتبعتت للعضو.")
        except Exception as e: await update.message.reply_text(f"❌ {esc(str(e)[:100])}", parse_mode="HTML")

    elif state == 'broadcast':
        if not is_admin: return
        context.user_data['state'] = None
        users = db_exec("SELECT user_id FROM users WHERE banned=0")
        sent, failed = 0, 0
        status_msg = await update.message.reply_text("⏳ <b>بنبعت...</b>", parse_mode="HTML")
        for (uid,) in users:
            try:
                await context.bot.copy_message(chat_id=uid, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
                sent += 1
                await asyncio.sleep(0.05)
            except Exception: failed += 1
        await status_msg.edit_text(f"✅ <b>الرسالة الجماعية تمت</b>\n\n• نجح: <code>{sent}</code>\n• فشل: <code>{failed}</code>", parse_mode="HTML")

    elif state == 'admin_restore_backup':
        if not is_admin: return
        if not update.message.document:
            return await update.message.reply_text("❌ ابعت ملف قاعدة البيانات (`.db`).")
        doc = update.message.document
        if not doc.file_name.endswith(".db"):
            return await update.message.reply_text("❌ الملف لازم يكون `.db`.")
        context.user_data['state'] = None
        try:
            tg_file = await doc.get_file()
            file_bytes = await tg_file.download_as_bytearray()
            if not file_bytes.startswith(b"SQLite format 3\x00"):
                return await update.message.reply_text("❌ الملف مش قاعدة بيانات SQLite صالحة.")
            with open(DB_PATH, "wb") as f:
                f.write(file_bytes)
            db_init()
            await update.message.reply_text("✅ <b>النسخة الاحتياطية اترجعت بنجاح!</b>\n\nكل البيانات رجعت.", parse_mode="HTML")
            await show_admin_panel(update, context)
        except Exception as e:
            logger.exception("restore error")
            await update.message.reply_text(f"❌ <b>الرجوع فشل</b>\n\n<code>{esc(str(e)[:300])}</code>", parse_mode="HTML")

# ============ معالج الأزرار (Callbacks) ============
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_ID

    if data.startswith(ADMIN_ONLY_PREFIXES) and not is_admin:
        return await q.answer("❌ غير مصرح", show_alert=True)

    register_user(update.effective_user)
    if not is_admin:
        u = get_user(user_id)
        if u and u['banned']:
            return await q.answer("🚫 أنت محظور", show_alert=True)

    if data == "main_menu":
        await q.answer()
        if not is_admin:
            active, _ = is_sub_active(user_id)
            if not active:
                return await show_subscription_screen(update, context)
        return await show_main_menu(update, context)

    if data == "cancel":
        await q.answer("تم الإلغاء"); context.user_data['state'] = None
        if not is_admin:
            active, _ = is_sub_active(user_id)
            if not active:
                return await show_subscription_screen(update, context)
        return await show_main_menu(update, context)

    if not is_admin and not (data.startswith("migno_") or data.startswith("migyes_")):
        active, _ = is_sub_active(user_id)
        if not active:
            return await q.answer("⛔ اشتراكك منتهي", show_alert=True)

    if data == "admin_subs": await cb_admin_subs(update, context)
    elif data == "admin_sub_activate": await cb_admin_sub_activate(update, context)
    elif data == "admin_sub_list": await cb_admin_sub_list(update, context)
    elif data.startswith("admin_sub_manage_"): await cb_admin_sub_manage(update, context)
    elif data.startswith("admin_sub_cancel_"): await cb_admin_sub_cancel(update, context)
    elif data.startswith("subplan_"): await cb_admin_sub_plan_chosen(update, context)
    elif data.startswith("admin_users_"): await cb_admin_users(update, context)
    elif data.startswith("admin_user_loops_"): await cb_admin_user_loops(update, context)
    elif data.startswith("admin_user_"): await cb_admin_user(update, context)
    elif data.startswith("admin_toggleban_"): await cb_admin_toggleban(update, context)
    elif data.startswith("admin_delconfirm_"): await cb_admin_delconfirm(update, context)
    elif data.startswith("admin_deluser_"): await cb_admin_deluser(update, context)
    elif data.startswith("admin_dm_"):
        await q.answer()
        try: uid = int(data.split("_")[-1])
        except ValueError: return
        context.user_data['state'] = f"admin_dm_{uid}"
        await context.bot.send_message(user_id, "✉️ ابعت الرسالة (نص أو صورة) للعضو:", reply_markup=kb_cancel_admin())
    elif data == "admin_search": await cb_admin_search(update, context)
    elif data == "admin_loops": await q.answer(); await cb_admin_loops_live(update, context)
    elif data == "admin_broadcast": await cb_admin_broadcast(update, context)
    elif data == "admin_stats": await cb_admin_stats(update, context)
    elif data == "admin_banned": await cb_admin_banned(update, context)
    elif data == "admin_panel": await show_admin_panel(update, context)
    elif data == "admin_backup": await cb_admin_backup(update, context)
    elif data == "admin_restore": await cb_admin_restore(update, context)
    elif data.startswith("stoploop_"):
        uid = int(data.split("_")[-1])
        if user_id != uid and not is_admin: return await q.answer("❌", show_alert=True)
        if loop_manager.request_stop(uid): await q.answer("🛑 بنوقف...")
        else: await q.answer("مفيش عملية نشطة")
    elif data.startswith("migno_"):
        uid = int(data.split("_")[-1])
        if user_id != uid and not is_admin: return await q.answer("❌ غير مصرح", show_alert=True)
        await q.answer("تمام")
        clear_user_creds(uid)
        if uid in loop_manager.pending_migrations:
            loop_manager.pending_migrations.pop(uid, None)
        try: await q.edit_message_text("👌 تمام، الفرد فضل على نظامه الحالي.")
        except Exception: pass
    elif data.startswith("migyes_"):
        uid = int(data.split("_")[-1])
        if user_id != uid and not is_admin: return await q.answer("❌ غير مصرح", show_alert=True)
        pending = loop_manager.pending_migrations.get(uid)
        if not pending:
            context.user_data['state'] = 'mig_child_email'
            context.user_data['mig_uid'] = uid
            await q.answer()
            return await q.edit_message_text(
                "📧 <b>محتاجين إيميل الفرد عشان نحوّله</b>\n\nاكتب إيميل الفرد:",
                parse_mode="HTML"
            )
        await q.answer("⏳ بنحوّل...")
        try: await q.edit_message_text("⏳ <b>بنسجل دخول الفرد وبنحوّله لميني حكاية 10.5...</b>", parse_mode="HTML")
        except Exception: pass
        child = EtisalatAPI()
        if not await asyncio.to_thread(child.login, pending['child_email'], pending['child_pass']):
            retry_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 جرّب تاني", callback_data=f"migyes_{uid}")]])
            return await q.edit_message_text(
                "❌ <b>دخول الفرد فشل</b>\n\nاتأكد من البيانات أو جرّب تاني.",
                parse_mode="HTML", reply_markup=retry_kb
            )
        ok, info = await asyncio.to_thread(child.migrate_harley_mini)
        if ok:
            await q.edit_message_text(
                f"🎉 <b>مبرووك يا وحش!</b>\n\n"
                f"تم فك ليمت الفرد بنجاح!\n"
                f"عِيش، ليمت الفرد اتكسر في ثواني! 😎🔥\n\n"
                f"📱 الرقم: <code>{esc(child.current_dial)}</code>\n\n"
                f"👨‍💻 المطور: {DEVELOPER}\n"
                f"✈️ اليوزر: @{DEV_USERNAME}",
                parse_mode="HTML"
            )
            clear_user_creds(uid)
            if uid in loop_manager.pending_migrations:
                loop_manager.pending_migrations.pop(uid, None)
        else:
            retry_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 جرّب تاني", callback_data=f"migyes_{uid}")]])
            await q.edit_message_text(f"❌ <b>التحويل فشل</b>\n\n<code>{esc(info)}</code>", parse_mode="HTML", reply_markup=retry_kb)
    elif data.startswith("target_"):
        await q.answer()
        val = data.split("_", 1)[1]
        if val == "custom":
            context.user_data['state'] = 'setup_target'
            try: await q.edit_message_text("✍️ اكتب المبلغ المخصص:", reply_markup=kb_cancel())
            except Exception: pass
        else:
            context.user_data['state'] = None
            try: await q.edit_message_text(f"⏳ بنجهز للهدف {int(val):,}...", parse_mode="HTML")
            except Exception: pass
            u = get_user(user_id)
            ok, msg = await loop_manager.start(user_id, user_id, (u['owner_email'], u['owner_pass']), (u['child_email'], u['child_pass']), int(val), context.user_data.get('child_num'))
            if not ok: await q.edit_message_text(f"❌ {msg}")

# ============ فحص دوري للاشتراكات ============
async def periodic_sub_check(context: ContextTypes.DEFAULT_TYPE):
    try:
        for uid in list(loop_manager.states.keys()):
            if uid == ADMIN_ID: continue
            active, _ = is_sub_active(uid)
            if not active and loop_manager.is_running(uid):
                logger.info(f"Stopping loop for {uid} — subscription expired")
                loop_manager.request_stop(uid, reason='subscription_expired')
                try:
                    await context.bot.send_message(
                        uid,
                        "⛔ <b>اشتراكك انتهى!</b>\n\n"
                        f"تم إيقاف عمليتك تلقائيًا.\n\n"
                        f"📩 جدد اشتراكك مع: @{DEV_USERNAME}",
                        parse_mode="HTML"
                    )
                except Exception: pass
    except Exception as e:
        logger.exception(f"periodic_sub_check error: {e}")

# ============ post_init ============
async def post_init(app: Application):
    global loop_manager
    loop_manager = LoopManager(app.bot)
    await app.bot.set_my_commands([
        BotCommand("start", "بدء البوت"),
        BotCommand("myid", "عرض الآيدي"),
        BotCommand("sub", "حالة الاشتراك"),
    ])
    app.job_queue.run_repeating(periodic_sub_check, interval=300, first=60)
    logger.info("✅ Subscription checker started (every 5 min)")

# ============ main ============
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("sub", cmd_sub))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_text))
    logger.info("🚀 Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
