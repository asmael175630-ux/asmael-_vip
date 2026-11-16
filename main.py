import os
import json
import requests
import telebot
from telebot import types
from datetime import datetime

# ============ الإعدادات ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "9190057613:AAHzGl4leCLtu2m-QAqpmeWJtRq3R7K63Bg")
OWNER_ID = int(os.getenv("OWNER_ID", "8593727596"))
VODAFONE_NUMBER = os.getenv("VODAFONE_NUMBER", "01041974269")
DEVELOPER = os.getenv("DEVELOPER", "asmael_VIP")
BOT_NAME = "™NET_VIP"
API_URL = "https://ghostsnet.xyz/sc/vip.php"
DATA_FILE = "data.json"

# ============ إعدادات القناة الإجبارية ============
CHANNEL_USERNAME = "@A_S_MAEL_VIP"
CHANNEL_URL = "https://t.me/A_S_MAEL_VIP"
CHANNEL_ID = "@A_S_MAEL_VIP"

bot = telebot.TeleBot(BOT_TOKEN)

# ============ الباقات ============
PACKAGES = {
    "1": {"name": "Flex 40",  "action": "activate"},
    "2": {"name": "Flex 60",  "action": "activate"},
    "3": {"name": "Flex 90",  "action": "activate"},
    "4": {"name": "Flex 130", "action": "activate"},
    "5": {"name": "Flex 260", "action": "activate"},
}
ROLLOVER_ID = "6"
ROLLOVER_NAME = "تزويد يومين"
ROLLOVER_ACTION = "activate_rollover"

# ============ الإعدادات الافتراضية ============
DEFAULT_SETTINGS = {
    "mode": "paid",
    "convert_star_price": 25,
    "rollover_star_price": 5,
    "convert_cost_stars": 1,
    "rollover_cost_stars": 1,
    "notify_owner_activity": True,
    "force_subscribe": True,
}

# ============ قاعدة البيانات ============
def load_db():
    if not os.path.exists(DATA_FILE):
        return {
            "users": {},
            "banned": [],
            "stats": {"activations": 0, "rollovers": 0},
            "pending": {},
            "next_req_id": 1,
            "settings": DEFAULT_SETTINGS.copy()
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "settings" not in data:
        data["settings"] = DEFAULT_SETTINGS.copy()
    for k, v in DEFAULT_SETTINGS.items():
        data["settings"].setdefault(k, v)
    return data

def save_db(db):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

db = load_db()

def S(key):
    return db["settings"].get(key, DEFAULT_SETTINGS.get(key))

# ============ الثوابت ============
STAR = "⭐"; BRIGHT = "🔆"; FIRE = "🔥"; DIAMOND = "💎"
CROWN = "👑"; CHECK = "✅"; CROSS = "❌"; GHOST = "👻"
MONEY = "💰"; SCREEN = "🖼"; WAIT = "⏳"; CLOCK = "⏰"
GEAR = "⚙️"; EYE = "👁"; LOCK = "🔒"; UNLOCK = "🔓"
BELL = "🔔"; CHART = "📊"; TAG = "🏷"; GIFT = "🎁"
ROCKET = "🚀"; SHIELD = "🛡"; SPARKLE = "✨"

# ============ API ============
def get_package_ids():
    try:
        r = requests.get(API_URL, timeout=10)
        text = r.text.strip()
        if not text:
            return None
        ids = [x.strip() for x in text.split(",") if x.strip()]
        result = []
        for pid in ids:
            if pid in PACKAGES:
                result.append({
                    "id": pid,
                    "name": PACKAGES[pid]["name"],
                    "action": PACKAGES[pid]["action"],
                })
        return result if result else None
    except:
        return None

def post_api(payload):
    try:
        r = requests.post(API_URL, json=payload, timeout=30)
        text = r.text.strip()
        try:
            return r.json()
        except:
            return {"status": "success", "message": text if text else "تم"}
    except requests.exceptions.Timeout:
        return {"status": "error", "message": "⏰ انتهت مهلة الاتصال"}
    except Exception as e:
        return {"status": "error", "message": f"❌ خطأ: {str(e)[:50]}"}

# ============ أدوات ============
def is_owner(uid): return uid == OWNER_ID
def is_banned(uid): return str(uid) in db["banned"]
def is_free_mode(): return S("mode") == "free"

def ensure_user(uid, name):
    if str(uid) not in db["users"]:
        db["users"][str(uid)] = {
            "name": name,
            "convert_stars": 0,
            "rollover_stars": 0,
            "joined": datetime.now().isoformat(),
            "activations": 0,
            "rollovers": 0,
            "last_seen": datetime.now().isoformat()
        }
        save_db(db)
    else:
        db["users"][str(uid)]["last_seen"] = datetime.now().isoformat()
        save_db(db)

def get_convert_stars(uid):
    return db["users"].get(str(uid), {}).get("convert_stars", 0)

def get_rollover_stars(uid):
    return db["users"].get(str(uid), {}).get("rollover_stars", 0)

def log_activity(uid, name, action):
    if not S("notify_owner_activity"):
        return
    try:
        u = db["users"].get(str(uid), {})
        text = (
            f"{BELL} <b>نشاط مستخدم</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{EYE} الاسم: {name}\n"
            f"🆔 <code>{uid}</code>\n"
            f"{FIRE} الإجراء: {action}\n"
            f"{STAR} رصيد التحويل: {u.get('convert_stars',0)}\n"
            f"{CLOCK} رصيد التزويد: {u.get('rollover_stars',0)}\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💬 مراسلة المستخدم", callback_data=f"msguser_{uid}"))
        bot.send_message(OWNER_ID, text, parse_mode="HTML", reply_markup=kb)
    except:
        pass

# ============ التحقق من الاشتراك الإجباري ============
def check_subscription(uid):
    if not S("force_subscribe"):
        return True
    try:
        member = bot.get_chat_member(CHANNEL_ID, uid)
        status = member.status
        if status in ["member", "administrator", "creator"]:
            return True
        if status == "restricted" and getattr(member, "is_member", False):
            return True
        return False
    except Exception as e:
        print(f"⚠️ Check subscription error: {e}")
        return True  # لو حصل خطأ نعتبره مشترك عشان البوت ميتقفلش

def send_join_message(uid, name="صديقي"):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(f"{ROCKET} اشترك في القناة", url=CHANNEL_URL))
    kb.add(types.InlineKeyboardButton(f"{CHECK} تحققت من الاشتراك", callback_data="check_sub"))
    text = (
        f"{SHIELD} <b>اشتراك إجباري</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"مرحباً <b>{name}</b> 👋\n\n"
        f"للاستفادة من البوت، لازم تشترك في قناتنا الرسمية أولاً:\n\n"
        f"{FIRE} <b>القناة:</b> {CHANNEL_USERNAME}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"1️⃣ اضغط زر <b>اشترك في القناة</b>\n"
        f"2️⃣ اضغط <b>Join</b> في تيليجرام\n"
        f"3️⃣ ارجع هنا واضغط <b>تحققت من الاشتراك</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{STAR} شكراً لاشتراكك!"
    )
    bot.send_message(uid, text, reply_markup=kb, parse_mode="HTML")

def require_sub(call):
    uid = call.from_user.id
    if is_owner(uid):
        return True
    if check_subscription(uid):
        return True
    bot.answer_callback_query(call.id, "❌ لازم تشترك في القناة الأول!", show_alert=True)
    send_join_message(uid, call.from_user.first_name)
    return False

@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def cb_check_sub(call):
    uid = call.from_user.id
    if check_subscription(uid):
        bot.answer_callback_query(call.id, "✅ تم التحقق! أهلاً بك", show_alert=True)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        fake_msg = call.message
        fake_msg.from_user = call.from_user
        start(fake_msg)
    else:
        bot.answer_callback_query(
            call.id,
            "❌ لسه مش مشترك!\nاشترك في القناة الأول ثم اضغط تحققت",
            show_alert=True
        )

# ============ لوحات المفاتيح ============
def main_menu(uid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    kb.add(
        types.InlineKeyboardButton(f"{STAR} تحويل نظام {STAR}", callback_data="convert"),
        types.InlineKeyboardButton(f"{CLOCK} تزويد يومين", callback_data="rollover"),
    )
    kb.add(
        types.InlineKeyboardButton(f"📋 اشتراكاتي", callback_data="subs"),
        types.InlineKeyboardButton(f"{DIAMOND} رصيدي", callback_data="balance"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{MONEY} شراء نجوم {STAR}", callback_data="buy_stars"),
        types.InlineKeyboardButton(f"{TAG} الأسعار", callback_data="prices"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{GHOST} حول البوت", callback_data="about"),
        types.InlineKeyboardButton(f"👨‍💻 المطور", url=f"https://t.me/{DEVELOPER}"),
    )
    kb.add(types.InlineKeyboardButton(f"{FIRE} قناتنا الرسمية", url=CHANNEL_URL))
    if is_owner(uid):
        kb.add(types.InlineKeyboardButton(
            f"{CROWN} لوحة التحكم ({mode_txt}) {CROWN}", callback_data="admin_panel"))
    return kb

def reply_menu(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton(f"{STAR} تحويل نظام"),
        types.KeyboardButton(f"{CLOCK} تزويد يومين"),
    )
    kb.add(
        types.KeyboardButton(f"📋 اشتراكاتي"),
        types.KeyboardButton(f"{DIAMOND} رصيدي"),
    )
    kb.add(
        types.KeyboardButton(f"{MONEY} شراء نجوم"),
        types.KeyboardButton(f"{TAG} الأسعار"),
    )
    kb.add(
        types.KeyboardButton(f"{GHOST} حول البوت"),
        types.KeyboardButton(f"👨‍💻 تواصل مع المطور"),
    )
    if is_owner(uid):
        kb.add(types.KeyboardButton(f"{CROWN} لوحة التحكم"))
    return kb

def packages_menu(packages):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for p in packages:
        kb.add(types.InlineKeyboardButton(
            f"{BRIGHT} {p['name']}",
            callback_data=f"pkg_{p['id']}_{p['name']}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    return kb

def buy_stars_menu():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(
        f"{STAR} نجوم تحويل ({S('convert_star_price')}ج/نجمة)",
        callback_data="buy_convert"
    ))
    kb.add(types.InlineKeyboardButton(
        f"{CLOCK} نجوم تزويد ({S('rollover_star_price')}ج/نجمة)",
        callback_data="buy_rollover"
    ))
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    return kb

def buy_convert_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    price = S("convert_star_price")
    for n in [1, 2, 5, 10]:
        kb.add(types.InlineKeyboardButton(
            f"{n} {STAR} = {n*price}ج",
            callback_data=f"buyconv_{n}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="buy_stars"))
    return kb

def buy_rollover_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    price = S("rollover_star_price")
    for n in [1, 2, 5, 10]:
        kb.add(types.InlineKeyboardButton(
            f"{n} {STAR} = {n*price}ج",
            callback_data=f"buyroll_{n}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="buy_stars"))
    return kb

def rollover_confirm_menu():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"{CHECK} نعم، تأكيد التزويد", callback_data="confirm_rollover"),
        types.InlineKeyboardButton("🔙 إلغاء", callback_data="back_main"),
    )
    return kb

# ============ /start ============
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    ensure_user(uid, msg.from_user.first_name)
    if is_banned(uid):
        bot.send_message(uid, f"{CROSS} أنت محظور من استخدام البوت.")
        return

    # 🔒 التحقق من الاشتراك الإجباري (عدا المالك)
    if not is_owner(uid):
        if not check_subscription(uid):
            send_join_message(uid, msg.from_user.first_name)
            return

    mode_badge = f"{LOCK} <b>الوضع المدفوع</b>" if not is_free_mode() else f"{UNLOCK} <b>الوضع المجاني (مفتوح)</b>"
    text = (
        f"{SPARKLE} <b>مرحباً {msg.from_user.first_name}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{GHOST} <b>{BOT_NAME}</b>\n"
        f"{BRIGHT} بوت تحويل الأنظمة القديمة\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{mode_badge}\n"
        f"{STAR} نجمة التحويل: <b>{S('convert_star_price')} جنيه</b>\n"
        f"{CLOCK} نجمة التزويد: <b>{S('rollover_star_price')} جنيه</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{DIAMOND} رصيد نجوم التحويل: <b>{get_convert_stars(uid)}</b>\n"
        f"{DIAMOND} رصيد نجوم التزويد: <b>{get_rollover_stars(uid)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر من القائمة 👇"
    )
    bot.send_message(uid, text, reply_markup=reply_menu(uid), parse_mode="HTML")
    bot.send_message(uid, f"{BRIGHT} القائمة الرئيسية:", reply_markup=main_menu(uid))
    log_activity(uid, msg.from_user.first_name, "دخل البوت /start")

# ============ /developer ============
@bot.message_handler(commands=['developer', 'dev'])
def cmd_dev(msg):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👨‍💻 تواصل مع المطور", url=f"https://t.me/{DEVELOPER}"))
    bot.send_message(
        msg.chat.id,
        f"👨‍💻 <b>{BOT_NAME} - المطور</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 يوزر: @{DEVELOPER}\n"
        f"📩 للاستفسارات والدعم الفني\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"اضغط الزر للتواصل مباشرة 👇",
        reply_markup=kb, parse_mode="HTML")

# ============ طلب رقم + باسورد ============
def ask_credentials(uid, next_step_func):
    msg = bot.send_message(
        uid,
        f"📱 <b>أدخل رقم الموبايل:</b>\n"
        f"مثال: <code>01234567890</code>",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🔙 إلغاء", callback_data="back_main")))
    bot.register_next_step_handler(msg, receive_phone_general, next_step_func)

def receive_phone_general(msg, next_step_func):
    uid = msg.from_user.id
    phone = msg.text.strip() if msg.text else ""
    if not phone.isdigit() or len(phone) < 10:
        m = bot.send_message(uid, f"{CROSS} رقم غير صالح! أدخل رقم صحيح:\nمثال: <code>01234567890</code>",
                             parse_mode="HTML")
        bot.register_next_step_handler(m, receive_phone_general, next_step_func)
        return
    db["users"][str(uid)]["temp_phone"] = phone
    save_db(db)
    m = bot.send_message(
        uid,
        f"{CHECK} تم حفظ الرقم: <code>{phone}</code>\n\n"
        f"🔐 <b>أدخل باسورد فودافون:</b>",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🔙 إلغاء", callback_data="back_main")))
    bot.register_next_step_handler(m, receive_password_general, next_step_func)

def receive_password_general(msg, next_step_func):
    uid = msg.from_user.id
    phone = db["users"].get(str(uid), {}).get("temp_phone")
    if not phone:
        bot.send_message(uid, f"{CROSS} حدث خطأ. ابدأ من جديد /start")
        return
    password = msg.text.strip() if msg.text else ""
    if not password:
        m = bot.send_message(uid, f"{CROSS} الباسورد لا يمكن أن يكون فارغاً! أرسل الباسورد:")
        bot.register_next_step_handler(m, receive_password_general, next_step_func)
        return
    db["users"][str(uid)]["temp_password"] = password
    save_db(db)
    next_step_func(msg, phone, password)

# ============ تحويل نظام ============
@bot.callback_query_handler(func=lambda c: c.data == "convert")
def cb_convert(call):
    if not require_sub(call): return
    if is_banned(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 محظور", show_alert=True); return
    uid = call.from_user.id
    stars = get_convert_stars(uid)
    cost = S("convert_cost_stars")
    if not is_free_mode():
        if stars < cost:
            bot.answer_callback_query(
                call.id,
                f"❌ تحتاج {cost} {STAR} للتحويل!\n"
                f"رصيدك: {stars}\n"
                f"السعر: {S('convert_star_price')} جنيه/نجمة",
                show_alert=True)
            return
    packages = get_package_ids()
    if not packages:
        bot.answer_callback_query(call.id, "❌ فشل تحميل الباقات", show_alert=True); return
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    cost_txt = f"{cost} {STAR} = {cost*S('convert_star_price')} جنيه" if not is_free_mode() else "مجاني 🎁"
    text = (
        f"{BRIGHT} <b>اختر الباقة</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{mode_txt}\n"
        f"💡 التكلفة: <b>{cost_txt}</b>\n"
        f"{DIAMOND} رصيدك: <b>{stars} {STAR}</b>"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=packages_menu(packages), parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("pkg_"))
def cb_pkg(call):
    if not require_sub(call): return
    uid = call.from_user.id
    _, pkg_id, pkg_name = call.data.split("_", 2)
    db["users"][str(uid)]["temp_pkg"] = {"id": pkg_id, "name": pkg_name, "action": "activate"}
    save_db(db)
    ask_credentials(uid, do_activation)

def do_activation(msg, phone, password):
    uid = msg.from_user.id
    pkg = db["users"].get(str(uid), {}).get("temp_pkg")
    if not pkg:
        bot.send_message(uid, f"{CROSS} لم يتم اختيار باقة."); return
    cost = S("convert_cost_stars")
    if not is_free_mode():
        if get_convert_stars(uid) < cost:
            bot.send_message(uid, f"{CROSS} رصيدك غير كافٍ!"); return
    wait = bot.send_message(uid, f"{BRIGHT} جاري التحويل... انتظر")
    result = post_api({"action": pkg["action"], "number": phone,
                       "password": password, "package": pkg["id"]})
    if result.get('status') == 'success':
        if not is_free_mode():
            db["users"][str(uid)]["convert_stars"] -= cost
        db["users"][str(uid)]["activations"] += 1
        db["stats"]["activations"] += 1
        db["users"][str(uid)].pop("temp_pkg", None)
        db["users"][str(uid)].pop("temp_phone", None)
        db["users"][str(uid)].pop("temp_password", None)
        save_db(db)
        mode_line = f"{STAR} خصم: {cost} {STAR}" if not is_free_mode() else "🎁 مجاني"
        bot.edit_message_text(
            f"{CHECK} <b>تم التحويل بنجاح!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 الباقة: {pkg['name']}\n"
            f"📱 الرقم: <code>{phone}</code>\n"
            f"{mode_line}\n"
            f"{DIAMOND} الرصيد المتبقي: {get_convert_stars(uid)} {STAR}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 {result.get('message','')}",
            uid, wait.message_id, parse_mode="HTML")
        log_activity(uid, msg.from_user.first_name, f"تحويل نظام - {pkg['name']}")
    else:
        bot.edit_message_text(
            f"{CROSS} <b>فشل التحويل</b>\n\n💬 {result.get('message','خطأ')}",
            uid, wait.message_id, parse_mode="HTML")

# ============ تزويد يومين ============
@bot.callback_query_handler(func=lambda c: c.data == "rollover")
def cb_rollover(call):
    if not require_sub(call): return
    if is_banned(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 محظور", show_alert=True); return
    uid = call.from_user.id
    stars = get_rollover_stars(uid)
    cost = S("rollover_cost_stars")
    price = S("rollover_star_price")
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    text = (
        f"{CLOCK} <b>تزويد يومين</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{mode_txt}\n"
        f"{MONEY} السعر: <b>{price} جنيه = {cost} {STAR}</b>\n"
        f"{DIAMOND} رصيدك: <b>{stars} {STAR}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    if not is_free_mode() and stars < cost:
        text += f"\n{CROSS} رصيدك غير كافٍ!\n💡 تحتاج {cost} {STAR} = {cost*price} جنيه"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton(f"{MONEY} شراء نجوم تزويد", callback_data="buy_rollover"),
                                  types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")),
                              parse_mode="HTML")
        return
    text += f"\n{CHECK} {'رصيدك كافٍ' if not is_free_mode() else 'مجاني'}! اضغط تأكيد"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=rollover_confirm_menu(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "confirm_rollover")
def cb_confirm_rollover(call):
    if not require_sub(call): return
    uid = call.from_user.id
    if is_banned(uid):
        bot.answer_callback_query(call.id, "🚫 محظور", show_alert=True); return
    cost = S("rollover_cost_stars")
    if not is_free_mode() and get_rollover_stars(uid) < cost:
        bot.answer_callback_query(call.id, f"❌ رصيدك غير كافٍ!", show_alert=True); return
    db["users"][str(uid)]["temp_pkg"] = {"id": ROLLOVER_ID, "name": ROLLOVER_NAME, "action": ROLLOVER_ACTION}
    save_db(db)
    bot.edit_message_text(
        f"{CLOCK} <b>تزويد يومين</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 أدخل رقم الموبايل:",
        call.message.chat.id, call.message.message_id, parse_mode="HTML")
    ask_credentials(uid, do_rollover)

def do_rollover(msg, phone, password):
    uid = msg.from_user.id
    pkg = db["users"].get(str(uid), {}).get("temp_pkg")
    if not pkg or pkg.get("action") != ROLLOVER_ACTION:
        bot.send_message(uid, f"{CROSS} خطأ في البيانات. ابدأ من جديد."); return
    cost = S("rollover_cost_stars")
    if not is_free_mode() and get_rollover_stars(uid) < cost:
        bot.send_message(uid, f"{CROSS} رصيدك غير كافٍ!"); return
    wait = bot.send_message(uid, f"{BRIGHT} جاري تزويد اليومين... انتظر")
    result = post_api({"action": ROLLOVER_ACTION, "number": phone,
                       "password": password, "package": ROLLOVER_ID})
    if not is_free_mode():
        db["users"][str(uid)]["rollover_stars"] -= cost
    db["users"][str(uid)]["rollovers"] = db["users"][str(uid)].get("rollovers", 0) + 1
    db["stats"]["rollovers"] = db["stats"].get("rollovers", 0) + 1
    db["users"][str(uid)].pop("temp_pkg", None)
    db["users"][str(uid)].pop("temp_phone", None)
    db["users"][str(uid)].pop("temp_password", None)
    save_db(db)
    api_msg = result.get('message', 'تم') if isinstance(result, dict) else str(result)
    mode_line = f"{STAR} خصم: {cost} {STAR}" if not is_free_mode() else "🎁 مجاني"
    bot.edit_message_text(
        f"{CHECK} <b>تم تزويد اليومين بنجاح!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{CLOCK} الخدمة: {ROLLOVER_NAME}\n"
        f"📱 الرقم: <code>{phone}</code>\n"
        f"{mode_line}\n"
        f"{DIAMOND} الرصيد المتبقي: {get_rollover_stars(uid)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 {api_msg}",
        uid, wait.message_id, parse_mode="HTML")
    log_activity(uid, msg.from_user.first_name, "تزويد يومين")

# ============ الأسعار ============
@bot.callback_query_handler(func=lambda c: c.data == "prices")
def cb_prices(call):
    if not require_sub(call): return
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    text = (
        f"{TAG} <b>الأسعار الحالية</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{GEAR} الوضع: <b>{mode_txt}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{STAR} <b>نجمة التحويل:</b> {S('convert_star_price')} جنيه\n"
        f"💡 التحويل يحتاج: {S('convert_cost_stars')} {STAR} = {S('convert_cost_stars')*S('convert_star_price')} جنيه\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{CLOCK} <b>نجمة التزويد:</b> {S('rollover_star_price')} جنيه\n"
        f"💡 التزويد يحتاج: {S('rollover_cost_stars')} {STAR} = {S('rollover_cost_stars')*S('rollover_star_price')} جنيه\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    if is_free_mode():
        text += f"{UNLOCK} <b>الوضع مجاني حالياً — الخدمات مفتوحة بدون نجوم!</b>"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=kb, parse_mode="HTML")

# ============ اشتراكاتي ============
@bot.callback_query_handler(func=lambda c: c.data == "subs")
def cb_subs(call):
    if not require_sub(call): return
    uid = call.from_user.id
    if is_banned(uid):
        bot.answer_callback_query(call.id, "🚫 محظور", show_alert=True); return
    bot.edit_message_text(
        f"📋 <b>اشتراكاتي</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 أدخل رقم الموبايل:",
        call.message.chat.id, call.message.message_id, parse_mode="HTML")
    ask_credentials(uid, do_subs_list)

def do_subs_list(msg, phone, password):
    uid = msg.from_user.id
    wait = bot.send_message(uid, f"{BRIGHT} جاري تحميل الاشتراكات...")
    result = post_api({"action": "list_subs", "number": phone, "password": password})
    if result.get('status') != 'success':
        bot.edit_message_text(
            f"{CROSS} <b>فشل التحميل</b>\n\n💬 {result.get('message','خطأ')}",
            uid, wait.message_id, parse_mode="HTML")
        return
    subs = result.get('subscriptions', [])
    if not subs:
        bot.edit_message_text(
            f"📋 <b>اشتراكاتي</b>\n\n{CROSS} لا توجد اشتراكات",
            uid, wait.message_id, parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")))
        return
    lines = [f"📋 <b>اشتراكاتك ({len(subs)})</b>\n━━━━━━━━━━━━━━━━━━━━"]
    for sub in subs:
        lines.append(
            f"\n<b>{sub['index']}.</b> {sub['description']}\n"
            f"🆔 <code>{sub['id']}</code>\n"
            f"💰 {sub['price']} | 🏷 {sub['type']}"
        )
    text = "\n".join(lines)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for sub in subs:
        kb.add(types.InlineKeyboardButton(
            f"❌ إلغاء {sub['description']}",
            callback_data=f"cancelsub_{sub['index']}_{sub['id']}_{sub['encProductId']}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    bot.edit_message_text(text, uid, wait.message_id, parse_mode="HTML", reply_markup=kb)
    log_activity(uid, msg.from_user.first_name, "عرض اشتراكاته")

@bot.callback_query_handler(func=lambda c: c.data.startswith("cancelsub_"))
def cb_cancelsub(call):
    if not require_sub(call): return
    uid = call.from_user.id
    parts = call.data.split("_")
    index = parts[1]; sub_id = parts[2]; enc = parts[3] if len(parts) > 3 else ""
    phone = db["users"].get(str(uid), {}).get("temp_phone")
    password = db["users"].get(str(uid), {}).get("temp_password")
    if not phone or not password:
        bot.answer_callback_query(call.id, "❌ أعد إدخال بياناتك", show_alert=True); return
    bot.answer_callback_query(call.id, "⏳ جاري الإلغاء...")
    result = post_api({"action": "cancel_sub", "number": phone, "password": password,
                       "sub_id": sub_id, "enc_product_id": enc, "description": ""})
    if result.get('status') == 'success':
        bot.send_message(uid,
            f"{CHECK} <b>تم إلغاء الاشتراك!</b>\n💬 {result.get('message','')}",
            parse_mode="HTML")
        log_activity(uid, call.from_user.first_name, "إلغاء اشتراك")
    else:
        bot.send_message(uid,
            f"{CROSS} <b>فشل الإلغاء</b>\n💬 {result.get('message','خطأ')}",
            parse_mode="HTML")

# ============ شراء النجوم ============
@bot.callback_query_handler(func=lambda c: c.data == "buy_stars")
def cb_buy(call):
    if not require_sub(call): return
    uid = call.from_user.id
    if is_free_mode():
        bot.answer_callback_query(call.id, "🎁 الوضع مجاني حالياً — لا حاجة لشراء نجوم!", show_alert=True)
        return
    text = (
        f"{MONEY} <b>شراء نجوم</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{STAR} نجمة تحويل: <b>{S('convert_star_price')} جنيه</b>\n"
        f"{CLOCK} نجمة تزويد: <b>{S('rollover_star_price')} جنيه</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{DIAMOND} رصيد التحويل: <b>{get_convert_stars(uid)}</b>\n"
        f"{DIAMOND} رصيد التزويد: <b>{get_rollover_stars(uid)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر نوع النجوم:"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=buy_stars_menu(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "buy_convert")
def cb_buy_convert(call):
    if not require_sub(call): return
    bot.edit_message_text(
        f"{STAR} <b>شراء نجوم التحويل</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"سعر النجمة: {S('convert_star_price')} جنيه\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر عدد النجوم:",
        call.message.chat.id, call.message.message_id,
        reply_markup=buy_convert_menu(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "buy_rollover")
def cb_buy_rollover(call):
    if not require_sub(call): return
    bot.edit_message_text(
        f"{CLOCK} <b>شراء نجوم التزويد</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"سعر النجمة: {S('rollover_star_price')} جنيه\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر عدد النجوم:",
        call.message.chat.id, call.message.message_id,
        reply_markup=buy_rollover_menu(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("buyconv_"))
def cb_buyconv(call):
    if not require_sub(call): return
    n = int(call.data.split("_")[1])
    total = n * S("convert_star_price")
    uid = call.from_user.id
    req_type = "buy_convert"
    db["users"][str(uid)]["temp_buy"] = {"n": n, "type": req_type}
    save_db(db)
    text = (
        f"{STAR} <b>طلب شراء {n} نجمة تحويل</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{STAR} النجوم: <b>{n}</b>\n"
        f"{MONEY} المبلغ: <b>{total} جنيه</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>حوّل على فودافون كاش:</b>\n"
        f"<code>{VODAFONE_NUMBER}</code>\n\n"
        f"📸 بعد التحويل، ابعت <b>صورة سكرين شوت</b>."
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML")
    msg = bot.send_message(uid, f"{SCREEN} ابعت صورة السكرين شوت الآن:")
    bot.register_next_step_handler(msg, receive_screenshot, n, req_type, total)

@bot.callback_query_handler(func=lambda c: c.data.startswith("buyroll_"))
def cb_buyroll(call):
    if not require_sub(call): return
    n = int(call.data.split("_")[1])
    total = n * S("rollover_star_price")
    uid = call.from_user.id
    req_type = "buy_rollover"
    db["users"][str(uid)]["temp_buy"] = {"n": n, "type": req_type}
    save_db(db)
    text = (
        f"{CLOCK} <b>طلب شراء {n} نجمة تزويد</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{STAR} النجوم: <b>{n}</b>\n"
        f"{MONEY} المبلغ: <b>{total} جنيه</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>حوّل على فودافون كاش:</b>\n"
        f"<code>{VODAFONE_NUMBER}</code>\n\n"
        f"📸 بعد التحويل، ابعت <b>صورة سكرين شوت</b>."
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML")
    msg = bot.send_message(uid, f"{SCREEN} ابعت صورة السكرين شوت الآن:")
    bot.register_next_step_handler(msg, receive_screenshot, n, req_type, total)

def receive_screenshot(msg, n, req_type, total):
    uid = msg.from_user.id
    if not msg.photo:
        bot.send_message(uid, f"{CROSS} لازم تبعت صورة سكرين شوت!")
        return
    req_id = db["next_req_id"]; db["next_req_id"] += 1
    db["pending"][str(req_id)] = {
        "user_id": uid, "name": msg.from_user.first_name,
        "username": msg.from_user.username or "—",
        "stars": n, "amount": total,
        "screenshot": msg.photo[-1].file_id,
        "date": datetime.now().isoformat(),
        "type": req_type
    }
    save_db(db)
    type_name = "نجوم تحويل" if req_type == "buy_convert" else "نجوم تزويد"
    bot.send_message(uid,
        f"{CHECK} <b>تم إرسال طلبك للإدارة</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 الطلب: <code>#{req_id}</code>\n"
        f"{STAR} النوع: {type_name}\n"
        f"{STAR} النجوم: {n}\n"
        f"{MONEY} المبلغ: {total} جنيه\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{WAIT} سيتم المراجعة.",
        parse_mode="HTML")
    owner_text = (
        f"{FIRE} <b>طلب شراء {type_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 الطلب: <code>#{req_id}</code>\n"
        f"👤 {msg.from_user.first_name} | @{msg.from_user.username or '—'}\n"
        f"🆔 <code>{uid}</code>\n"
        f"{STAR} النجوم: <b>{n}</b>\n"
        f"{MONEY} المبلغ: <b>{total} جنيه</b>\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{CHECK} موافقة (+{n} {STAR})", callback_data=f"approve_{req_id}"),
        types.InlineKeyboardButton(f"{CROSS} رفض + حظر", callback_data=f"reject_{req_id}")
    )
    try:
        bot.send_photo(OWNER_ID, msg.photo[-1].file_id,
                       caption=owner_text, reply_markup=kb, parse_mode="HTML")
    except: pass
    log_activity(uid, msg.from_user.first_name, f"طلب شراء {n} {type_name}")

# ============ موافقة/رفض المالك ============
@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_"))
def cb_approve(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 للمالك فقط", show_alert=True); return
    req_id = call.data.split("_")[1]
    req = db["pending"].get(req_id)
    if not req:
        bot.answer_callback_query(call.id, "❌ الطلب غير موجود", show_alert=True); return
    uid = req["user_id"]; n = req["stars"]; req_type = req.get("type", "buy_convert")
    if str(uid) not in db["users"]:
        db["users"][str(uid)] = {"name": req["name"], "convert_stars": 0, "rollover_stars": 0,
                                  "joined": datetime.now().isoformat(),
                                  "activations": 0, "rollovers": 0}
    if req_type == "buy_rollover":
        db["users"][str(uid)]["rollover_stars"] = db["users"][str(uid)].get("rollover_stars", 0) + n
        added_msg = f"{CLOCK} أضيف: <b>{n} نجمة تزويد</b>"
    else:
        db["users"][str(uid)]["convert_stars"] = db["users"][str(uid)].get("convert_stars", 0) + n
        added_msg = f"{STAR} أضيف: <b>{n} نجمة تحويل</b>"
    del db["pending"][req_id]
    save_db(db)
    bot.edit_message_caption(
        f"{CHECK} <b>تمت الموافقة</b>\nطلب #{req_id} — أضيف {n} {STAR}",
        call.message.chat.id, call.message.message_id, parse_mode="HTML")
    try:
        bot.send_message(uid,
            f"{CHECK} <b>تمت الموافقة!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 #{req_id}\n"
            f"{added_msg}\n"
            f"{STAR} رصيد التحويل: <b>{get_convert_stars(uid)}</b>\n"
            f"{CLOCK} رصيد التزويد: <b>{get_rollover_stars(uid)}</b>",
            parse_mode="HTML", reply_markup=reply_menu(uid))
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("reject_"))
def cb_reject(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 للمالك فقط", show_alert=True); return
    req_id = call.data.split("_")[1]
    req = db["pending"].get(req_id)
    if not req:
        bot.answer_callback_query(call.id, "❌ غير موجود", show_alert=True); return
    uid = req["user_id"]
    if str(uid) not in db["banned"]: db["banned"].append(str(uid))
    del db["pending"][req_id]
    save_db(db)
    bot.edit_message_caption(
        f"{CROSS} <b>رفض + حظر</b> — #{req_id}",
        call.message.chat.id, call.message.message_id, parse_mode="HTML")
    try:
        bot.send_message(uid,
            f"{CROSS} <b>تم رفض طلبك وحظرك</b>\n🆔 #{req_id}\n"
            f"للاستفسار: @{DEVELOPER}")
    except: pass

# ============ الرصيد ============
@bot.callback_query_handler(func=lambda c: c.data == "balance")
def cb_balance(call):
    if not require_sub(call): return
    uid = call.from_user.id
    u = db["users"].get(str(uid), {})
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    text = (
        f"{DIAMOND} <b>رصيدك</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{GEAR} الوضع: <b>{mode_txt}</b>\n"
        f"{STAR} نجوم التحويل: <b>{u.get('convert_stars',0)}</b>\n"
        f"{CLOCK} نجوم التزويد: <b>{u.get('rollover_stars',0)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{FIRE} التحويلات: <b>{u.get('activations',0)}</b>\n"
        f"{CLOCK} التزويدات: <b>{u.get('rollovers',0)}</b>\n"
        f"📅 انضم: {u.get('joined','')[:10]}"
    )
    if is_free_mode():
        text += f"\n\n{UNLOCK} <b>الوضع مجاني — النجوم محفوظة ولا تُخصم حالياً</b>"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=types.InlineKeyboardMarkup().add(
                              types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")),
                          parse_mode="HTML")

# ============ حول ============
@bot.callback_query_handler(func=lambda c: c.data == "about")
def cb_about(call):
    if not require_sub(call): return
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    text = (
        f"{GHOST} <b>{BOT_NAME}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔆 تحويل الأنظمة القديمة\n"
        f"{GEAR} الوضع: <b>{mode_txt}</b>\n"
        f"{STAR} نجمة التحويل: {S('convert_star_price')} جنيه\n"
        f"{CLOCK} نجمة التزويد: {S('rollover_star_price')} جنيه\n"
        f"{MONEY} دفع: {VODAFONE_NUMBER}\n"
        f"{FIRE} القناة: {CHANNEL_USERNAME}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👨‍💻 المطور: @{DEVELOPER}"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("👨‍💻 تواصل مع المطور", url=f"https://t.me/{DEVELOPER}"))
    kb.add(types.InlineKeyboardButton(f"{FIRE} القناة الرسمية", url=CHANNEL_URL))
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "back_main")
def cb_back(call):
    if not require_sub(call): return
    uid = call.from_user.id
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    text = (f"{GHOST} <b>القائمة الرئيسية</b>\n"
            f"{GEAR} الوضع: <b>{mode_txt}</b>\n"
            f"{STAR} نجوم التحويل: <b>{get_convert_stars(uid)}</b>\n"
            f"{CLOCK} نجوم التزويد: <b>{get_rollover_stars(uid)}</b>")
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=main_menu(uid), parse_mode="HTML")

# ============ لوحة المالك ============
@bot.callback_query_handler(func=lambda c: c.data == "admin_panel")
def cb_admin(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 للمالك فقط", show_alert=True); return
    pending_count = len(db["pending"])
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    toggle_txt = f"🔓 تحويل لمجاني" if not is_free_mode() else f"🔒 تحويل لمدفوع"
    sub_txt = f"{CHECK} مفعل" if S("force_subscribe") else f"{CROSS} معطل"
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton(toggle_txt, callback_data="adm_toggle_mode"))
    kb.add(
        types.InlineKeyboardButton(f"⏳ الطلبات ({pending_count})", callback_data="adm_pending"),
        types.InlineKeyboardButton(f"{CHART} إحصائيات", callback_data="adm_stats"),
    )
    kb.add(
        types.InlineKeyboardButton(f"👥 المستخدمين", callback_data="adm_users"),
        types.InlineKeyboardButton(f"{TAG} تغيير الأسعار", callback_data="adm_prices"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{BELL} إشعارات النشاط", callback_data="adm_notif"),
        types.InlineKeyboardButton(f"{EYE} مراسلة مستخدم", callback_data="adm_msguser"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{SHIELD} الاشتراك الإجباري ({sub_txt})", callback_data="adm_toggle_sub"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{STAR} نجوم تحويل", callback_data="adm_addconv"),
        types.InlineKeyboardButton(f"{CLOCK} نجوم تزويد", callback_data="adm_addroll"),
    )
    kb.add(
        types.InlineKeyboardButton(f"🚫 حظر", callback_data="adm_ban"),
        types.InlineKeyboardButton(f"✅ رفع الحظر", callback_data="adm_unban"),
    )
    kb.add(types.InlineKeyboardButton(f"📢 إذاعة", callback_data="adm_broadcast"))
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
    bot.edit_message_text(
        f"{CROWN} <b>لوحة تحكم المالك</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{GEAR} الوضع: <b>{mode_txt}</b>\n"
        f"{SHIELD} الاشتراك الإجباري: <b>{sub_txt}</b>\n"
        f"⏳ طلبات معلقة: <b>{pending_count}</b>",
        call.message.chat.id, call.message.message_id,
        reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "adm_toggle_mode")
def cb_toggle_mode(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 للمالك فقط", show_alert=True); return
    current = S("mode")
    new_mode = "free" if current == "paid" else "paid"
    db["settings"]["mode"] = new_mode
    save_db(db)
    if new_mode == "free":
        alert = f"{UNLOCK} تحول البوت للوضع المجاني\nالخدمات مفتوحة بدون نجوم\nنجوم المستخدمين محفوظة"
    else:
        alert = f"{LOCK} تحول البوت للوضع المدفوع\nالخدمات تحتاج نجوم مرة أخرى"
    bot.answer_callback_query(call.id, alert, show_alert=True)
    cb_admin(call)

@bot.callback_query_handler(func=lambda c: c.data == "adm_toggle_sub")
def cb_toggle_sub(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 للمالك فقط", show_alert=True); return
    current = S("force_subscribe")
    db["settings"]["force_subscribe"] = not current
    save_db(db)
    if current:
        bot.answer_callback_query(call.id, f"{CROSS} تم تعطيل الاشتراك الإجباري\nالمستخدمون يدخلون بدون اشتراك", show_alert=True)
    else:
        bot.answer_callback_query(call.id, f"{CHECK} تم تفعيل الاشتراك الإجباري\nالمستخدمون لازم يشتركوا في القناة", show_alert=True)
    cb_admin(call)

# ============ تغيير الأسعار ============
@bot.callback_query_handler(func=lambda c: c.data == "adm_prices")
def cb_adm_prices(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 للمالك فقط", show_alert=True); return
    text = (
        f"{TAG} <b>إعدادات الأسعار</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{STAR} نجمة التحويل: <b>{S('convert_star_price')} جنيه</b>\n"
        f"💡 التحويل يحتاج: <b>{S('convert_cost_stars')} {STAR}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{CLOCK} نجمة التزويد: <b>{S('rollover_star_price')} جنيه</b>\n"
        f"💡 التزويد يحتاج: <b>{S('rollover_cost_stars')} {STAR}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر ما تريد تعديله:"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(f"{STAR} سعر نجمة التحويل", callback_data="adm_set_price_convert"))
    kb.add(types.InlineKeyboardButton(f"{CLOCK} سعر نجمة التزويد", callback_data="adm_set_price_rollover"))
    kb.add(types.InlineKeyboardButton(f"💡 نجوم مطلوبة للتحويل", callback_data="adm_set_cost_convert"))
    kb.add(types.InlineKeyboardButton(f"💡 نجوم مطلوبة للتزويد", callback_data="adm_set_cost_rollover"))
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_set_"))
def cb_adm_set(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 للمالك فقط", show_alert=True); return
    key = call.data.replace("adm_set_", "")
    prompts = {
        "price_convert": ("convert_star_price", "سعر نجمة التحويل (جنيه)"),
        "price_rollover": ("rollover_star_price", "سعر نجمة التزويد (جنيه)"),
        "cost_convert": ("convert_cost_stars", "عدد النجوم المطلوبة للتحويل"),
        "cost_rollover": ("rollover_cost_stars", "عدد النجوم المطلوبة للتزويد"),
    }
    if key not in prompts:
        return
    setting_key, label = prompts[key]
    msg = bot.send_message(call.message.chat.id,
        f"{GEAR} <b>{label}</b>\n\n"
        f"القيمة الحالية: <code>{S(setting_key)}</code>\n\n"
        f"أرسل القيمة الجديدة (رقم):",
        parse_mode="HTML")
    bot.register_next_step_handler(msg, _do_set_price, setting_key)

def _do_set_price(msg, setting_key):
    if msg.from_user.id != OWNER_ID: return
    try:
        val = int(msg.text.strip())
        if val <= 0:
            raise ValueError
        db["settings"][setting_key] = val
        save_db(db)
        bot.send_message(msg.chat.id,
            f"{CHECK} تم التحديث!\n"
            f"{GEAR} <code>{setting_key}</code> = <b>{val}</b>\n\n"
            f"سيتم تطبيقه على كل الخدمات الجديدة فوراً.",
            parse_mode="HTML")
    except:
        bot.send_message(msg.chat.id, f"{CROSS} قيمة غير صحيحة! أرسل رقم أكبر من صفر.")

# ============ إشعارات النشاط ============
@bot.callback_query_handler(func=lambda c: c.data == "adm_notif")
def cb_adm_notif(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 للمالك فقط", show_alert=True); return
    current = S("notify_owner_activity")
    status_txt = f"{CHECK} مفعل" if current else f"{CROSS} معطل"
    text = (
        f"{BELL} <b>إشعارات نشاط المستخدمين</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"الحالة: <b>{status_txt}</b>\n\n"
        f"عند التفعيل، ستستقبل إشعاراً فور قيام أي مستخدم بأي إجراء\n"
        f"(تحويل، تزويد، طلب شراء، إلخ)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"هل تريد التبديل؟"
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{CHECK} تفعيل", callback_data="adm_notif_on"),
        types.InlineKeyboardButton(f"{CROSS} تعطيل", callback_data="adm_notif_off"),
    )
    kb.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "adm_notif_on")
def cb_notif_on(call):
    if not is_owner(call.from_user.id): return
    db["settings"]["notify_owner_activity"] = True
    save_db(db)
    bot.answer_callback_query(call.id, f"{CHECK} تم تفعيل إشعارات النشاط", show_alert=True)
    cb_adm_notif(call)

@bot.callback_query_handler(func=lambda c: c.data == "adm_notif_off")
def cb_notif_off(call):
    if not is_owner(call.from_user.id): return
    db["settings"]["notify_owner_activity"] = False
    save_db(db)
    bot.answer_callback_query(call.id, f"{CROSS} تم تعطيل إشعارات النشاط", show_alert=True)
    cb_adm_notif(call)

# ============ مراسلة مستخدم ============
@bot.callback_query_handler(func=lambda c: c.data == "adm_msguser")
def cb_adm_msguser(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "🚫 للمالك فقط", show_alert=True); return
    msg = bot.send_message(call.message.chat.id,
        f"{EYE} <b>مراسلة مستخدم</b>\n\n"
        f"أرسل بالصيغة التالية:\n"
        f"<code>آيدي_المستخدم | نص الرسالة</code>\n\n"
        f"مثال:\n"
        f"<code>123456789 | مرحباً، تم تفعيل طلبك</code>",
        parse_mode="HTML")
    bot.register_next_step_handler(msg, _do_msguser)

def _do_msguser(msg):
    if msg.from_user.id != OWNER_ID: return
    try:
        parts = msg.text.split("|", 1)
        if len(parts) != 2:
            raise ValueError
        target_uid = int(parts[0].strip())
        text_to_send = parts[1].strip()
        bot.send_message(target_uid,
            f"{BELL} <b>رسالة من الإدارة</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{text_to_send}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👨‍💻 @{DEVELOPER}",
            parse_mode="HTML")
        bot.send_message(msg.chat.id,
            f"{CHECK} تم إرسال الرسالة للمستخدم {target_uid}")
    except:
        bot.send_message(msg.chat.id, f"{CROSS} صيغة خاطئة! استخدم: آيدي | رسالة")

@bot.callback_query_handler(func=lambda c: c.data.startswith("msguser_"))
def cb_msguser_from_notif(call):
    if not is_owner(call.from_user.id): return
    target_uid = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id,
        f"{EYE} <b>مراسلة المستخدم</b> <code>{target_uid}</code>\n\n"
        f"أرسل نص الرسالة الآن:",
        parse_mode="HTML")
    bot.register_next_step_handler(msg, _do_replyuser, target_uid)

def _do_replyuser(msg, target_uid):
    if msg.from_user.id != OWNER_ID: return
    try:
        bot.send_message(int(target_uid),
            f"{BELL} <b>رسالة من الإدارة</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{msg.text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👨‍💻 @{DEVELOPER}",
            parse_mode="HTML")
        bot.send_message(msg.chat.id, f"{CHECK} تم إرسال الرسالة للمستخدم {target_uid}")
    except Exception as e:
        bot.send_message(msg.chat.id, f"{CROSS} فشل الإرسال: {e}")

# ============ الطلبات ============
@bot.callback_query_handler(func=lambda c: c.data == "adm_pending")
def adm_pending(call):
    if not is_owner(call.from_user.id): return
    if not db["pending"]:
        bot.answer_callback_query(call.id, "لا توجد طلبات معلقة ✅", show_alert=True); return
    bot.edit_message_text(
        f"⏳ <b>الطلبات المعلقة: {len(db['pending'])}</b>\nسيتم إرسالها أدناه 👇",
        call.message.chat.id, call.message.message_id,
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")),
        parse_mode="HTML")
    for rid, req in db["pending"].items():
        t = req.get("type", "buy_convert")
        type_txt = f"{STAR} نجوم تحويل" if t == "buy_convert" else f"{CLOCK} نجوم تزويد"
        text = (
            f"{FIRE} <b>طلب #{rid}</b> — {type_txt}\n"
            f"👤 {req['name']} | @{req['username']}\n"
            f"🆔 <code>{req['user_id']}</code>\n"
            f"{STAR} {req['stars']} نجمة | {MONEY} {req['amount']}ج\n"
            f"🕐 {req['date'][:16]}"
        )
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton(f"{CHECK} موافقة", callback_data=f"approve_{rid}"),
            types.InlineKeyboardButton(f"{CROSS} رفض + حظر", callback_data=f"reject_{rid}")
        )
        try:
            bot.send_photo(OWNER_ID, req["screenshot"], caption=text,
                           reply_markup=kb, parse_mode="HTML")
        except: pass

# ============ الإحصائيات ============
@bot.callback_query_handler(func=lambda c: c.data == "adm_stats")
def adm_stats(call):
    if not is_owner(call.from_user.id): return
    total_conv = sum(u.get('convert_stars',0) for u in db['users'].values())
    total_roll = sum(u.get('rollover_stars',0) for u in db['users'].values())
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    sub_txt = f"{CHECK} مفعل" if S("force_subscribe") else f"{CROSS} معطل"
    text = (
        f"{CHART} <b>الإحصائيات</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{GEAR} الوضع: <b>{mode_txt}</b>\n"
        f"{SHIELD} اشتراك إجباري: <b>{sub_txt}</b>\n"
        f"👥 المستخدمين: {len(db['users'])}\n"
        f"{FIRE} التحويلات: {db['stats']['activations']}\n"
        f"{CLOCK} التزويدات: {db['stats'].get('rollovers',0)}\n"
        f"⏳ طلبات معلقة: {len(db['pending'])}\n"
        f"🚫 محظورين: {len(db['banned'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{STAR} نجوم تحويل: {total_conv}\n"
        f"{CLOCK} نجوم تزويد: {total_roll}"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=types.InlineKeyboardMarkup().add(
                              types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")),
                          parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "adm_users")
def adm_users(call):
    if not is_owner(call.from_user.id): return
    lines = [f"👥 <b>المستخدمين ({len(db['users'])})</b>\n"]
    for i, (uid, u) in enumerate(list(db['users'].items())[:30], 1):
        lines.append(
            f"{i}. {u['name']} | <code>{uid}</code>\n"
            f"   {STAR}{u.get('convert_stars',0)} | {CLOCK}{u.get('rollover_stars',0)}"
        )
    bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.message_id,
                          reply_markup=types.InlineKeyboardMarkup().add(
                              types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")),
                          parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "adm_addconv")
def adm_addconv(call):
    if not is_owner(call.from_user.id): return
    msg = bot.send_message(call.message.chat.id,
        f"{STAR} <b>إضافة نجوم تحويل</b>\n\nأرسل: <code>الآيدي عدد_النجوم</code>",
        parse_mode="HTML")
    bot.register_next_step_handler(msg, _do_addconv)

def _do_addconv(msg):
    if msg.from_user.id != OWNER_ID: return
    try:
        uid, n = msg.text.split(); n = int(n)
        if str(uid) not in db["users"]:
            db["users"][str(uid)] = {"name": "?", "convert_stars": 0, "rollover_stars": 0,
                                      "joined": "", "activations": 0, "rollovers": 0}
        db["users"][str(uid)]["convert_stars"] = db["users"][str(uid)].get("convert_stars", 0) + n
        save_db(db)
        bot.send_message(msg.chat.id, f"{CHECK} أضيف {n} {STAR} تحويل للمستخدم {uid}")
        try: bot.send_message(int(uid), f"{STAR} تم إضافة {n} نجمة تحويل! رصيدك: {get_convert_stars(uid)}")
        except: pass
    except:
        bot.send_message(msg.chat.id, f"{CROSS} صيغة خاطئة")

@bot.callback_query_handler(func=lambda c: c.data == "adm_addroll")
def adm_addroll(call):
    if not is_owner(call.from_user.id): return
    msg = bot.send_message(call.message.chat.id,
        f"{CLOCK} <b>إضافة نجوم تزويد</b>\n\nأرسل: <code>الآيدي عدد_النجوم</code>",
        parse_mode="HTML")
    bot.register_next_step_handler(msg, _do_addroll)

def _do_addroll(msg):
    if msg.from_user.id != OWNER_ID: return
    try:
        uid, n = msg.text.split(); n = int(n)
        if str(uid) not in db["users"]:
            db["users"][str(uid)] = {"name": "?", "convert_stars": 0, "rollover_stars": 0,
                                      "joined": "", "activations": 0, "rollovers": 0}
        db["users"][str(uid)]["rollover_stars"] = db["users"][str(uid)].get("rollover_stars", 0) + n
        save_db(db)
        bot.send_message(msg.chat.id, f"{CHECK} أضيف {n} {CLOCK} تزويد للمستخدم {uid}")
        try: bot.send_message(int(uid), f"{CLOCK} تم إضافة {n} نجمة تزويد! رصيدك: {get_rollover_stars(uid)}")
        except: pass
    except:
        bot.send_message(msg.chat.id, f"{CROSS} صيغة خاطئة")

@bot.callback_query_handler(func=lambda c: c.data == "adm_ban")
def adm_ban(call):
    if not is_owner(call.from_user.id): return
    msg = bot.send_message(call.message.chat.id, "أرسل آيدي المستخدم للحظر:")
    bot.register_next_step_handler(msg, lambda m: _do_ban(m, True))

@bot.callback_query_handler(func=lambda c: c.data == "adm_unban")
def adm_unban(call):
    if not is_owner(call.from_user.id): return
    msg = bot.send_message(call.message.chat.id, "أرسل آيدي المستخدم لرفع الحظر:")
    bot.register_next_step_handler(msg, lambda m: _do_ban(m, False))

def _do_ban(msg, ban):
    if msg.from_user.id != OWNER_ID: return
    uid = msg.text.strip()
    if ban:
        if uid not in db["banned"]: db["banned"].append(uid)
        txt = f"{CROSS} تم حظر {uid}"
    else:
        if uid in db["banned"]: db["banned"].remove(uid)
        txt = f"{CHECK} تم رفع الحظر عن {uid}"
    save_db(db)
    bot.send_message(msg.chat.id, txt)

@bot.callback_query_handler(func=lambda c: c.data == "adm_broadcast")
def adm_broadcast(call):
    if not is_owner(call.from_user.id): return
    msg = bot.send_message(call.message.chat.id, "أرسل رسالة الإذاعة:")
    bot.register_next_step_handler(msg, _do_broadcast)

def _do_broadcast(msg):
    if msg.from_user.id != OWNER_ID: return
    ok = fail = 0
    for uid in db["users"].keys():
        try:
            bot.send_message(int(uid), f"📢 <b>إعلان</b>\n\n{msg.text}", parse_mode="HTML")
            ok += 1
        except: fail += 1
    bot.send_message(msg.chat.id, f"{CHECK} نجح: {ok} | {CROSS} فشل: {fail}")

# ============ معالجات الأزرار الثابتة ============
@bot.message_handler(func=lambda m: m.text == f"{STAR} تحويل نظام")
def btn_convert(msg):
    uid = msg.from_user.id
    if is_banned(uid):
        bot.send_message(uid, f"{CROSS} أنت محظور."); return
    if not is_owner(uid) and not check_subscription(uid):
        send_join_message(uid, msg.from_user.first_name); return
    cost = S("convert_cost_stars")
    if not is_free_mode() and get_convert_stars(uid) < cost:
        bot.send_message(uid,
            f"❌ تحتاج {cost} {STAR} تحويل!\nسعر النجمة: {S('convert_star_price')} جنيه\n"
            f"اشترِ نجوم 👇", reply_markup=reply_menu(uid))
        return
    packages = get_package_ids()
    if not packages:
        bot.send_message(uid, "❌ فشل تحميل الباقات"); return
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    cost_txt = f"{cost} {STAR}" if not is_free_mode() else "مجاني 🎁"
    bot.send_message(uid,
        f"{BRIGHT} <b>اختر الباقة</b>\n"
        f"{mode_txt} | التكلفة: {cost_txt}\nرصيدك: {get_convert_stars(uid)} {STAR}",
        reply_markup=packages_menu(packages), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == f"{CLOCK} تزويد يومين")
def btn_rollover(msg):
    uid = msg.from_user.id
    if is_banned(uid):
        bot.send_message(uid, f"{CROSS} أنت محظور."); return
    if not is_owner(uid) and not check_subscription(uid):
        send_join_message(uid, msg.from_user.first_name); return
    stars = get_rollover_stars(uid)
    cost = S("rollover_cost_stars")
    price = S("rollover_star_price")
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    text = (
        f"{CLOCK} <b>تزويد يومين</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{mode_txt}\n"
        f"{MONEY} السعر: <b>{price} جنيه = {cost} {STAR}</b>\n"
        f"{DIAMOND} رصيدك: <b>{stars} {STAR}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    if not is_free_mode() and stars < cost:
        text += f"\n{CROSS} رصيدك غير كافٍ!\n💡 اشترِ نجوم تزويد أولاً"
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton(f"{MONEY} شراء نجوم تزويد", callback_data="buy_rollover"))
        bot.send_message(uid, text, reply_markup=kb, parse_mode="HTML")
        return
    text += f"\n{CHECK} {'رصيدك كافٍ' if not is_free_mode() else 'مجاني'}! اضغط تأكيد"
    bot.send_message(uid, text, reply_markup=rollover_confirm_menu(), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "📋 اشتراكاتي")
def btn_subs(msg):
    uid = msg.from_user.id
    if not is_owner(uid) and not check_subscription(uid):
        send_join_message(uid, msg.from_user.first_name); return
    bot.send_message(uid,
        f"📋 <b>اشتراكاتي</b>\n\n📱 أدخل رقم الموبايل:",
        parse_mode="HTML")
    ask_credentials(uid, do_subs_list)

@bot.message_handler(func=lambda m: m.text == f"{DIAMOND} رصيدي")
def btn_balance(msg):
    uid = msg.from_user.id
    if not is_owner(uid) and not check_subscription(uid):
        send_join_message(uid, msg.from_user.first_name); return
    u = db["users"].get(str(uid), {})
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    bot.send_message(uid,
        f"{DIAMOND} <b>رصيدك</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{GEAR} الوضع: <b>{mode_txt}</b>\n"
        f"{STAR} نجوم التحويل: <b>{u.get('convert_stars',0)}</b>\n"
        f"{CLOCK} نجوم التزويد: <b>{u.get('rollover_stars',0)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{FIRE} التحويلات: <b>{u.get('activations',0)}</b>\n"
        f"{CLOCK} التزويدات: <b>{u.get('rollovers',0)}</b>",
        parse_mode="HTML", reply_markup=reply_menu(uid))

@bot.message_handler(func=lambda m: m.text == f"{MONEY} شراء نجوم")
def btn_buy(msg):
    uid = msg.from_user.id
    if not is_owner(uid) and not check_subscription(uid):
        send_join_message(uid, msg.from_user.first_name); return
    if is_free_mode():
        bot.send_message(uid, f"🎁 الوضع مجاني حالياً — لا حاجة لشراء نجوم!")
        return
    text = (
        f"{MONEY} <b>شراء نجوم</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{STAR} نجمة تحويل: <b>{S('convert_star_price')} جنيه</b>\n"
        f"{CLOCK} نجمة تزويد: <b>{S('rollover_star_price')} جنيه</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{DIAMOND} رصيد التحويل: <b>{get_convert_stars(uid)}</b>\n"
        f"{DIAMOND} رصيد التزويد: <b>{get_rollover_stars(uid)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر نوع النجوم:"
    )
    bot.send_message(uid, text, reply_markup=buy_stars_menu(), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == f"{TAG} الأسعار")
def btn_prices(msg):
    uid = msg.from_user.id
    if not is_owner(uid) and not check_subscription(uid):
        send_join_message(uid, msg.from_user.first_name); return
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    text = (
        f"{TAG} <b>الأسعار الحالية</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{GEAR} الوضع: <b>{mode_txt}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{STAR} <b>نجمة التحويل:</b> {S('convert_star_price')} جنيه\n"
        f"💡 التحويل يحتاج: {S('convert_cost_stars')} {STAR}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{CLOCK} <b>نجمة التزويد:</b> {S('rollover_star_price')} جنيه\n"
        f"💡 التزويد يحتاج: {S('rollover_cost_stars')} {STAR}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )
    if is_free_mode():
        text += f"{UNLOCK} <b>الوضع مجاني حالياً — الخدمات مفتوحة!</b>"
    bot.send_message(uid, text, reply_markup=reply_menu(uid), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == f"{GHOST} حول البوت")
def btn_about(msg):
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    text = (
        f"{GHOST} <b>{BOT_NAME}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔆 تحويل الأنظمة القديمة\n"
        f"{GEAR} الوضع: <b>{mode_txt}</b>\n"
        f"{STAR} نجمة التحويل: {S('convert_star_price')} جنيه\n"
        f"{CLOCK} نجمة التزويد: {S('rollover_star_price')} جنيه\n"
        f"{MONEY} دفع: {VODAFONE_NUMBER}\n"
        f"{FIRE} القناة: {CHANNEL_USERNAME}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👨‍💻 المطور: @{DEVELOPER}"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👨‍💻 تواصل مع المطور", url=f"https://t.me/{DEVELOPER}"))
    kb.add(types.InlineKeyboardButton(f"{FIRE} القناة الرسمية", url=CHANNEL_URL))
    bot.send_message(msg.chat.id, text, reply_markup=kb, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "👨‍💻 تواصل مع المطور")
def btn_dev(msg):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👨‍💻 اضغط للتواصل", url=f"https://t.me/{DEVELOPER}"))
    bot.send_message(msg.chat.id,
        f"👨‍💻 <b>{BOT_NAME} - المطور</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 @{DEVELOPER}\n"
        f"📩 للدعم الفني\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"اضغط الزر 👇",
        reply_markup=kb, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == f"{CROWN} لوحة التحكم")
def btn_admin(msg):
    if not is_owner(msg.from_user.id):
        bot.send_message(msg.chat.id, f"{CROSS} للمالك فقط"); return
    pending_count = len(db["pending"])
    mode_txt = f"{LOCK} مدفوع" if not is_free_mode() else f"{UNLOCK} مجاني"
    toggle_txt = f"🔓 تحويل لمجاني" if not is_free_mode() else f"🔒 تحويل لمدفوع"
    sub_txt = f"{CHECK} مفعل" if S("force_subscribe") else f"{CROSS} معطل"
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton(toggle_txt, callback_data="adm_toggle_mode"))
    kb.add(
        types.InlineKeyboardButton(f"⏳ الطلبات ({pending_count})", callback_data="adm_pending"),
        types.InlineKeyboardButton(f"{CHART} إحصائيات", callback_data="adm_stats"),
    )
    kb.add(
        types.InlineKeyboardButton(f"👥 المستخدمين", callback_data="adm_users"),
        types.InlineKeyboardButton(f"{TAG} تغيير الأسعار", callback_data="adm_prices"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{BELL} إشعارات النشاط", callback_data="adm_notif"),
        types.InlineKeyboardButton(f"{EYE} مراسلة مستخدم", callback_data="adm_msguser"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{SHIELD} الاشتراك الإجباري ({sub_txt})", callback_data="adm_toggle_sub"),
    )
    kb.add(
        types.InlineKeyboardButton(f"{STAR} نجوم تحويل", callback_data="adm_addconv"),
        types.InlineKeyboardButton(f"{CLOCK} نجوم تزويد", callback_data="adm_addroll"),
    )
    kb.add(
        types.InlineKeyboardButton(f"🚫 حظر", callback_data="adm_ban"),
        types.InlineKeyboardButton(f"✅ رفع الحظر", callback_data="adm_unban"),
    )
    kb.add(types.InlineKeyboardButton(f"📢 إذاعة", callback_data="adm_broadcast"))
    bot.send_message(msg.chat.id,
        f"{CROWN} <b>لوحة تحكم المالك</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{GEAR} الوضع: <b>{mode_txt}</b>\n"
        f"{SHIELD} الاشتراك الإجباري: <b>{sub_txt}</b>\n"
        f"⏳ طلبات معلقة: <b>{pending_count}</b>",
        reply_markup=kb, parse_mode="HTML")

# ============ تشغيل ============
if __name__ == "__main__":
    print(f"{GHOST} {BOT_NAME} Bot running...")
    print(f"{GEAR} Mode: {S('mode')}")
    print(f"{SHIELD} Force Subscribe: {S('force_subscribe')} → {CHANNEL_USERNAME}")
    print(f"{STAR} Convert star: {S('convert_star_price')}ج | Rollover star: {S('rollover_star_price')}ج")
    bot.infinity_polling(timeout=60)
