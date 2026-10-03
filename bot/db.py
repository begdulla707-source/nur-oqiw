import os, sqlite3, json
from pathlib import Path
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row
else:
    DB = Path(__file__).resolve().parent.parent / "data" / "app.db"
    DB.parent.mkdir(exist_ok=True)

class DBConn:
    def __init__(self, raw, pg=False):
        self.raw = raw
        self.pg = pg
    def __enter__(self):
        self.raw.__enter__()
        return self
    def __exit__(self, *args):
        return self.raw.__exit__(*args)
    def execute(self, query, params=()):
        if self.pg:
            query = query.replace("?", "%s")
        return self.raw.execute(query, params)
    def executemany(self, query, seq):
        if self.pg:
            query = query.replace("?", "%s")
        return self.raw.executemany(query, seq)
    def __getattr__(self, name):
        return getattr(self.raw, name)

def conn():
    if USE_POSTGRES:
        return DBConn(psycopg.connect(DATABASE_URL, row_factory=dict_row), True)
    c = sqlite3.connect(DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.row_factory = sqlite3.Row
    return DBConn(c, False)

def init():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            telegram_id BIGINT PRIMARY KEY,
            full_name TEXT,
            phone TEXT,
            registered_at TEXT,
            code_ok INTEGER DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            score DOUBLE PRECISION DEFAULT 0,
            grade TEXT DEFAULT '',
            answers_json TEXT DEFAULT '{}',
            submitted INTEGER DEFAULT 0,
            state TEXT DEFAULT 'code',
            tier TEXT DEFAULT 'default',
            premium_since TEXT,
            premium_granted_by BIGINT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS questions(
            id INTEGER PRIMARY KEY,
            question TEXT,
            options_json TEXT DEFAULT '[]',
            answer TEXT DEFAULT '',
            kind TEXT DEFAULT 'choice',
            group_id TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            image_url TEXT DEFAULT ''
        )""")
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)")
        c.execute("""CREATE TABLE IF NOT EXISTS item_stats(
            question_id INTEGER PRIMARY KEY,
            attempts INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_code ON users(code_ok)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_submitted ON users(submitted)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier)")

def ensure_schema():
    with conn() as c:
        if USE_POSTGRES:
            cols={r["column_name"] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'").fetchall()}
            qcols={r["column_name"] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='questions'").fetchall()}
        else:
            cols={r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
            qcols={r["name"] for r in c.execute("PRAGMA table_info(questions)").fetchall()}
        if "state" not in cols: c.execute("ALTER TABLE users ADD COLUMN state TEXT DEFAULT 'code'")
        if "tier" not in cols: c.execute("ALTER TABLE users ADD COLUMN tier TEXT DEFAULT 'default'")
        if "premium_since" not in cols: c.execute("ALTER TABLE users ADD COLUMN premium_since TEXT")
        if "premium_granted_by" not in cols: c.execute("ALTER TABLE users ADD COLUMN premium_granted_by BIGINT")
        if "image_url" not in qcols: c.execute("ALTER TABLE questions ADD COLUMN image_url TEXT DEFAULT ''")
        if "group_id" not in qcols: c.execute("ALTER TABLE questions ADD COLUMN group_id TEXT DEFAULT ''")
        if "active" not in qcols: c.execute("ALTER TABLE questions ADD COLUMN active INTEGER DEFAULT 1")

def get_setting(k,d=None):
    with conn() as c:
        r=c.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone()
        return r["value"] if r else d

def set_setting(k,v):
    with conn() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(v)))

def get_user(t):
    with conn() as c: return c.execute("SELECT * FROM users WHERE telegram_id=?",(int(t),)).fetchone()

def ensure_user(t):
    t=int(t); u=get_user(t)
    if u:return u
    now=datetime.now(timezone.utc).isoformat()
    with conn() as c:c.execute("INSERT INTO users(telegram_id,full_name,phone,registered_at,code_ok,state,tier) VALUES(?,?,?,?,0,'code','default')",(t,"",None,now))
    return get_user(t)

def upsert_user(t,name,phone=None):
    with conn() as c:
        c.execute("""INSERT INTO users(telegram_id,full_name,phone,registered_at,tier) VALUES(?,?,?,?, 'default')
        ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name,phone=COALESCE(excluded.phone,users.phone)""",(int(t),name,phone,datetime.now(timezone.utc).isoformat()))

def update_user(t,**fields):
    allowed={"full_name","phone","registered_at","code_ok","started_at","finished_at","score","grade","answers_json","submitted","state","tier","premium_since","premium_granted_by"}
    fields={k:v for k,v in fields.items() if k in allowed}
    if not fields:return
    with conn() as c:c.execute("UPDATE users SET "+", ".join(f"{k}=?" for k in fields)+" WHERE telegram_id=?",list(fields.values())+[int(t)])

def set_code(t,v=1):update_user(t,code_ok=v)
def set_started(t,ts):update_user(t,started_at=ts)
def save_answers(t,a):
    with conn() as c:c.execute("UPDATE users SET answers_json=? WHERE telegram_id=?",(json.dumps(a,ensure_ascii=False),int(t)))
def finish_user(t,score,grade,ts,a):
    with conn() as c:c.execute("UPDATE users SET finished_at=?,score=?,grade=?,answers_json=?,submitted=1 WHERE telegram_id=?",(ts,float(score),str(grade),json.dumps(a,ensure_ascii=False),int(t)))
def finish(t,score,grade,ts,a):finish_user(t,score,grade,ts,a)

def all_users():
    with conn() as c:return c.execute("SELECT * FROM users WHERE code_ok=1 ORDER BY score DESC,full_name").fetchall()
def all_registered_users():
    with conn() as c:return c.execute("SELECT * FROM users ORDER BY registered_at ASC").fetchall()
def public_users():
    with conn() as c:return c.execute("SELECT telegram_id,full_name,tier FROM users WHERE code_ok=1 ORDER BY registered_at ASC").fetchall()
def set_tier(t,tier,admin_id=None):
    tier="premium" if str(tier).lower()=="premium" else "default"
    now=datetime.now(timezone.utc).isoformat() if tier=="premium" else None
    update_user(t,tier=tier,premium_since=now,premium_granted_by=(int(admin_id) if admin_id and tier=="premium" else None))
def is_premium(t):
    u=get_user(t); return bool(u and str(u["tier"] or "default").lower()=="premium")
def active_questions():
    with conn() as c:return c.execute("SELECT * FROM questions WHERE active=1 ORDER BY id").fetchall()
def all_questions():
    with conn() as c:return c.execute("SELECT * FROM questions ORDER BY id").fetchall()
def get_question(qid):
    try:qid=int(qid)
    except:return None
    with conn() as c:return c.execute("SELECT * FROM questions WHERE id=? AND active=1",(qid,)).fetchone()
def get_question_any(qid):
    try:qid=int(qid)
    except:return None
    with conn() as c:return c.execute("SELECT * FROM questions WHERE id=?",(qid,)).fetchone()
def upsert_question(qid,question,options,answer,kind="choice",group_id="",image_url=""):
    with conn() as c:c.execute("""INSERT INTO questions(id,question,options_json,answer,kind,group_id,active,image_url) VALUES(?,?,?,?,?,?,1,?)
    ON CONFLICT(id) DO UPDATE SET question=excluded.question,options_json=excluded.options_json,answer=excluded.answer,kind=excluded.kind,group_id=excluded.group_id,image_url=excluded.image_url,active=1""",(int(qid),str(question),json.dumps(options,ensure_ascii=False),str(answer),str(kind),str(group_id),str(image_url)))
def delete_question(qid):
    with conn() as c:
        if not c.execute("SELECT id FROM questions WHERE id=?",(int(qid),)).fetchone():return False
        c.execute("DELETE FROM questions WHERE id=?",(int(qid),));return True
def set_active_question_count(n):
    n=max(0,int(n))
    with conn() as c:
        c.execute("UPDATE questions SET active=0")
        ids=[r["id"] for r in c.execute("SELECT id FROM questions ORDER BY id LIMIT ?",(n,)).fetchall()]
        for qid in ids:c.execute("UPDATE questions SET active=1 WHERE id=?",(qid,))
def replace_questions(items):
    with conn() as c:
        c.execute("DELETE FROM questions")
        c.executemany("INSERT INTO questions(id,question,options_json,answer,kind,group_id,image_url) VALUES(?,?,?,?,?,?,?)",items)
        c.execute("UPDATE questions SET active=1")
def normalize(v):return " ".join(str(v or "").strip().casefold().split())
def record_stats(a):
    if not a:return
    with conn() as c:
        for qid,ans in a.items():
            try:qid=int(qid)
            except:continue
            q=c.execute("SELECT answer FROM questions WHERE id=?",(qid,)).fetchone()
            if not q:continue
            good=int(normalize(ans)==normalize(q["answer"]))
            c.execute("INSERT INTO item_stats(question_id,attempts,correct) VALUES(?,?,?) ON CONFLICT(question_id) DO UPDATE SET attempts=attempts+1,correct=correct+excluded.correct",(qid,1,good))
def weighted_score(a):
    qs={int(q["id"]):q for q in active_questions()}
    if not qs:return 0.0
    total=earned=0.0
    with conn() as c:
        for qid,q in qs.items():
            st=c.execute("SELECT attempts,correct FROM item_stats WHERE question_id=?",(qid,)).fetchone()
            attempts=int(st["attempts"]) if st else 0; corrects=int(st["correct"]) if st else 0
            p=corrects/attempts if attempts else 0.5; weight=0.5+(1-p)*1.5; total+=weight
            if str(qid) in a and normalize(a[str(qid)])==normalize(q["answer"]):earned+=weight
    return round(earned/total*100,2) if total else 0.0
def grade_for(score):
    s=float(score);return "A+" if s>=90 else "A" if s>=80 else "B" if s>=70 else "C" if s>=60 else "D" if s>=50 else "F"
def seed():
    if active_questions():return
    data=[]
    for i in range(1,33):data.append((i,f"Sertifikat uslubidagi matematika savoli {i}. To‘g‘ri javobni toping.",json.dumps(["A","B","C","D"],ensure_ascii=False),"A","choice","",""))
    data += [(33,"Shu rasmdagi to‘g‘ri to‘rtburchakning enini toping.",json.dumps(["6","8","10","12"],ensure_ascii=False),"8","choice","fig33",""),(34,"Shu rasmdagi perimetrni toping.",json.dumps(["32","36","40","44"],ensure_ascii=False),"40","choice","fig33",""),(35,"Shu rasmdagi yuzani toping.",json.dumps(["72","84","96","108"],ensure_ascii=False),"96","choice","fig33","")]
    for i in range(36,46):data.append((i,f"{i}. Yozma javobli sertifikat savoli.","[]","","written","",""))
    with conn() as c:c.executemany("INSERT INTO questions(id,question,options_json,answer,kind,group_id,image_url) VALUES(?,?,?,?,?,?,?)",data)

def seed_defaults():init();ensure_schema();seed()

# --- Persistent profile + Default/Premium Telegram UI ---
# This router is installed before the project's catch-all message handler. It therefore
# adds the new profile/tariff system without replacing the existing test/admin handlers.
from aiogram import Router, F as _F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command as _Command
from aiogram.types import ReplyKeyboardMarkup as _ReplyKeyboardMarkup, KeyboardButton as _KeyboardButton, InlineKeyboardMarkup as _InlineKeyboardMarkup, InlineKeyboardButton as _InlineKeyboardButton, WebAppInfo as _WebAppInfo
_premium_router = Router(name="profile_tariff_router")

ADMIN_ID = int(os.getenv("ADMIN_CHAT_ID", "8379731556"))
_WEBAPP_URL = os.getenv("WEBAPP_URL", "https://nukuspro.uz")

def _user_menu():
    return _ReplyKeyboardMarkup(keyboard=[
        [_KeyboardButton(text="Testni boshlash"), _KeyboardButton(text="Profilim")],
        [_KeyboardButton(text="Tarif sotib olish"), _KeyboardButton(text="Userlar ro‘yxati")],
        [_KeyboardButton(text="Mening natijam"), _KeyboardButton(text="Yordam")]
    ], resize_keyboard=True, is_persistent=True)

def _admin_menu():
    return _ReplyKeyboardMarkup(keyboard=[
        [_KeyboardButton(text="Test sozlamalari"), _KeyboardButton(text="Ishtirokchilar")],
        [_KeyboardButton(text="Savollar"), _KeyboardButton(text="Statistika")],
        [_KeyboardButton(text="Real-time monitor"), _KeyboardButton(text="Bildirishnoma")],
        [_KeyboardButton(text="Majburiy obuna"), _KeyboardButton(text="PDF natijalar")],
        [_KeyboardButton(text="Tariflar")]
    ], resize_keyboard=True, is_persistent=True)

def _profile_kb():
    return _InlineKeyboardMarkup(inline_keyboard=[
        [_InlineKeyboardButton(text="Tariflar", callback_data="profile_tariffs")],
        [_InlineKeyboardButton(text="Userlar ro‘yxati", callback_data="profile_users")],
        [_InlineKeyboardButton(text="Orqaga", callback_data="profile_back")]
    ])

def _tariff_kb():
    return _InlineKeyboardMarkup(inline_keyboard=[
        [_InlineKeyboardButton(text="1 — Default", callback_data="tariff_default_info")],
        [_InlineKeyboardButton(text="2 — Premium 💠", callback_data="tariff_premium_info")],
        [_InlineKeyboardButton(text="Orqaga", callback_data="profile_back")]
    ])

def _user_list_kb(tid):
    rows=[]
    for u in public_users()[:100]:
        name=(u["full_name"] or "Ismsiz")[:28]
        mark="💠 " if str(u["tier"] or "default")=="premium" else ""
        if is_premium(tid):
            rows.append([_InlineKeyboardButton(text=f"{mark}{name}", url=f"tg://user?id={int(u['telegram_id'])}")])
        else:
            rows.append([_InlineKeyboardButton(text=f"{mark}{name}", callback_data="profile_no_access")])
    rows.append([_InlineKeyboardButton(text="Orqaga", callback_data="profile_back")])
    return _InlineKeyboardMarkup(inline_keyboard=rows)

def _profile_text(u):
    tier="Premium 💠" if str(u["tier"] or "default")=="premium" else "Default"
    return ("PROFILIM\n\n"
            f"👤 Ism-familiya: {u['full_name'] or '—'}\n"
            f"📱 Telefon: {u['phone'] or '—'}\n"
            f"🆔 Telegram ID: {u['telegram_id']}\n"
            f"💠 Tarif: {tier}")

async def _profile_router_handler(message, bot, data):
    tid=message.from_user.id; text=(message.text or "").strip(); u=ensure_user(tid)
    if tid==ADMIN_ID and text=="/start":
        update_user(tid,state="admin")
        await message.answer("NUR O‘QIW ORAYI\n\nAdmin boshqaruv paneli.",reply_markup=_admin_menu())
        return
    if text=="/start" and u["code_ok"] and u["full_name"] and u["phone"]:
        update_user(tid,state="ready")
        await message.answer(f"✅ Xush kelibsiz, {u['full_name']}!\n\nTelegram akkauntingiz saqlangan. Qayta ro‘yxatdan o‘tishingiz shart emas.", reply_markup=_user_menu())
        return
    if tid==ADMIN_ID and text=="Tariflar":
        users=all_registered_users()
        rows=[]
        for i,x in enumerate(users,1):
            mark="💠" if str(x["tier"] or "default")=="premium" else ""
            rows.append([_InlineKeyboardButton(text=f"{i}. {mark} {(x['full_name'] or 'Ismsiz')[:22]} — {x['telegram_id']}",callback_data=f"tariff_user_{x['telegram_id']}")])
        rows.append([_InlineKeyboardButton(text="Orqaga",callback_data="admin_tariff_back")])
        await message.answer(f"TARIFLAR\n\nJami userlar: {len(users)}\n\nUserni tanlang:",reply_markup=_InlineKeyboardMarkup(inline_keyboard=rows))
        return
    if text=="Profilim" and u["code_ok"]:
        await message.answer(_profile_text(u),reply_markup=_profile_kb())
        return
    if text=="Tarif sotib olish" and u["code_ok"]:
        await message.answer("TARIFLAR\n\n1 — Default\n• Oddiy user tarifi\n• Reklamalar mavjud\n• 💠 Premium nishon yo‘q\n• Boshqa userlarga Telegram orqali yozish yopiq\n\n2 — Premium 💠\n• Reklamalarsiz\n• 💠 Premium nishon\n• Userlar ro‘yxatidan Telegram profiliga yozish\n• Kengaytirilgan shaxsiy statistika\n\nPremium tarifni olish uchun admin bilan bog‘laning.",reply_markup=_InlineKeyboardMarkup(inline_keyboard=[[_InlineKeyboardButton(text="Premium 💠 olish",callback_data="buy_premium")],[_InlineKeyboardButton(text="Tariflar haqida",callback_data="profile_tariffs")]]))
        return
    if text=="Tarif sotib olish" and u["code_ok"]:
        await message.answer("TARIFLAR\n\n1 — Default\n• Oddiy user tarifi\n• Reklamalar mavjud\n• 💠 Premium nishon yo‘q\n• Boshqa userlarga Telegram orqali yozish yopiq\n\n2 — Premium 💠\n• Reklamalarsiz\n• 💠 Premium nishon\n• Userlar ro‘yxatidan Telegram profiliga yozish\n• Kengaytirilgan shaxsiy statistika\n\nPremium tarifni olish uchun admin bilan bog‘laning.",reply_markup=_InlineKeyboardMarkup(inline_keyboard=[[_InlineKeyboardButton(text="Premium 💠 olish",callback_data="buy_premium")],[_InlineKeyboardButton(text="Tariflar haqida",callback_data="profile_tariffs")]]))
        return
    if text=="Userlar ro‘yxati" and u["code_ok"]:
        await message.answer("USERLAR RO‘YXATI\n\n💠 — Premium tarif.\n\n" + ("Premium tarifda user nomini bosib Telegram profiliga yozish mumkin." if is_premium(tid) else "Default tarifda ro‘yxat ko‘rinadi, lekin boshqa userga o‘tish/yazish yopiq."), reply_markup=_user_list_kb(tid))
        return
    if text=="Testni boshlash" and u["code_ok"]:
        await message.answer("Testni Mini App orqali boshlang.",reply_markup=_InlineKeyboardMarkup(inline_keyboard=[[_InlineKeyboardButton(text="TESTNI BOSHLASH",web_app=_WebAppInfo(url=_WEBAPP_URL))]]))
        return
    if text=="Yordam" and u["code_ok"]:
        await message.answer("Yordam\n\nTest, profil va tarif bo‘yicha savollar uchun admin bilan bog‘laning.")
        return
    if text=="Mening natijam" and u["code_ok"]:
        await message.answer(f"Mening natijam\n\nBall: {float(u['score'] or 0):.2f}\nBaho: {u['grade'] or 'Hali yakunlanmagan'}")
        return
    if text==code_value() and u["state"]=="code":
        update_user(tid,code_ok=1,state="ready")
        status="Test hozir ochiq." if _test_open_for_profile() else "Test hozir yopiq."
        await message.answer(f"✅ Kod qabul qilindi!\n\n{status}\n\nProfilingiz saqlandi.",reply_markup=_user_menu())
        await message.answer("Testga kirish:",reply_markup=_InlineKeyboardMarkup(inline_keyboard=[[_InlineKeyboardButton(text="TESTNI BOSHLASH",web_app=_WebAppInfo(url=_WEBAPP_URL))]]))
        return
    raise SkipHandler


def _test_open_for_profile():
    try:
        s=get_setting("test_start",os.getenv("TEST_START","08:30")); e=get_setting("test_end",os.getenv("TEST_END","09:30")); mode=get_setting("test_mode","auto");
        if mode=="open": return True
        if mode=="closed": return False
        from datetime import time as _time
        now=datetime.now().astimezone().time()
        return _time.fromisoformat(s)<=now<_time.fromisoformat(e)
    except Exception:return False

@_premium_router.message()
async def _premium_message(message, **data):
    return await _profile_router_handler(message, data["bot"], data)

@_premium_router.callback_query()
async def _premium_callback(query, **data):
    tid=query.from_user.id; d=query.data or ""; bot=data["bot"]
    u=ensure_user(tid)
    if d=="profile_back":
        await query.message.edit_text(f"Profil menyusi: {u['full_name'] or 'Ismsiz'}",reply_markup=_profile_kb()); await query.answer(); return
    if d=="buy_premium":
        await query.message.answer(f"Premium 💠 tarifini olish uchun admin bilan bog‘laning.",reply_markup=_InlineKeyboardMarkup(inline_keyboard=[[_InlineKeyboardButton(text="Admin bilan bog‘lanish",url=f"tg://user?id={ADMIN_ID}")],[ _InlineKeyboardButton(text="Tariflar haqida",callback_data="profile_tariffs")]]))
        await query.answer("Premium olish so‘rovi tayyor")
        return
    if d=="buy_premium":
        await query.message.answer(f"Premium 💠 tarifini olish uchun admin bilan bog‘laning.",reply_markup=_InlineKeyboardMarkup(inline_keyboard=[[_InlineKeyboardButton(text="Admin bilan bog‘lanish",url=f"tg://user?id={ADMIN_ID}")],[ _InlineKeyboardButton(text="Tariflar haqida",callback_data="profile_tariffs")]]))
        await query.answer("Premium olish so‘rovi tayyor")
        return
    if d=="profile_tariffs":
        await query.message.edit_text("TARIFLAR\n\n1 — Default\n• Oddiy user funksiyalari\n• Reklamalar mavjud\n• Premium nishon yo‘q\n• Userlar ro‘yxati ko‘rinadi, lekin boshqa userga yozish yopiq\n\n2 — Premium 💠\n• Reklamalarsiz\n• 💠 Premium nishon\n• Userlar ro‘yxatidan Telegram profiliga yozish\n• Premium userlarga mo‘ljallangan qo‘shimcha imkoniyatlar\n\nPremium tarifni olish uchun admin bilan bog‘laning.",reply_markup=_tariff_kb()); await query.answer(); return
    if d=="tariff_default_info":
        await query.answer("Default — oddiy tarif",show_alert=True); return
    if d=="tariff_premium_info":
        await query.answer("Premium 💠 admin orqali beriladi",show_alert=True); return
    if d=="profile_users":
        await query.message.edit_text("USERLAR RO‘YXATI\n\n💠 — Premium",reply_markup=_user_list_kb(tid)); await query.answer(); return
    if d=="profile_no_access":
        await query.answer("Bu imkoniyat Premium tarif uchun.",show_alert=True); return
    if d=="admin_tariff_back":
        await query.message.answer("Admin panel",reply_markup=_admin_menu()); await query.answer(); return
    if tid==ADMIN_ID and d.startswith("tariff_user_"):
        uid=int(d.rsplit("_",1)[1]); target=get_user(uid)
        if not target: await query.answer("User topilmadi",show_alert=True); return
        current="Premium 💠" if str(target["tier"] or "default")=="premium" else "Default"
        kb=_InlineKeyboardMarkup(inline_keyboard=[
            [_InlineKeyboardButton(text="Premium 💠 berish",callback_data=f"tariff_grant_{uid}"),_InlineKeyboardButton(text="Default qilish",callback_data=f"tariff_default_{uid}")],
            [_InlineKeyboardButton(text="Orqaga",callback_data="admin_tariff_list")]
        ])
        await query.message.edit_text(f"TARIFNI BOSHQARISH\n\n👤 {target['full_name'] or 'Ismsiz'}\n📱 {target['phone'] or '—'}\n🆔 {uid}\n\nHozirgi tarif: {current}\n\nTarifni tanlang:",reply_markup=kb); await query.answer(); return
    if tid==ADMIN_ID and (d.startswith("tariff_grant_") or d.startswith("tariff_default_")):
        uid=int(d.rsplit("_",1)[1]); target=get_user(uid)
        if not target: await query.answer("User topilmadi",show_alert=True); return
        tier="premium" if d.startswith("tariff_grant_") else "default"
        set_tier(uid,tier,ADMIN_ID)
        label="Premium 💠" if tier=="premium" else "Default"
        await query.message.edit_text(f"TASDIQLASH\n\n👤 {target['full_name'] or 'Ismsiz'}\n🆔 {uid}\n\nYangi tarif: {label}\n\nTasdiqlandi.",reply_markup=_InlineKeyboardMarkup(inline_keyboard=[[_InlineKeyboardButton(text="Tariflar ro‘yxati",callback_data="admin_tariff_list")],[ _InlineKeyboardButton(text="Admin panel",callback_data="admin_tariff_back")]])); await query.answer("Tarif saqlandi");
        try: await bot.send_message(uid,f"Tarifingiz yangilandi: {label}.")
        except Exception: pass
        return
    if tid==ADMIN_ID and d=="admin_tariff_list":
        users=all_registered_users(); rows=[]
        for i,x in enumerate(users,1):
            mark="💠" if str(x["tier"] or "default")=="premium" else ""
            rows.append([_InlineKeyboardButton(text=f"{i}. {mark} {(x['full_name'] or 'Ismsiz')[:22]} — {x['telegram_id']}",callback_data=f"tariff_user_{x['telegram_id']}")])
        rows.append([_InlineKeyboardButton(text="Admin panel",callback_data="admin_tariff_back")])
        await query.message.edit_text("TARIFLAR — USERLAR\n\nUserni tanlang:",reply_markup=_InlineKeyboardMarkup(inline_keyboard=rows)); await query.answer(); return
    raise SkipHandler

# Install this router before the existing project handlers. The original handlers remain intact.
try:
    from aiogram import Dispatcher as _Dispatcher
    _original_dispatcher_init=_Dispatcher.__init__
    def _patched_dispatcher_init(self,*args,**kwargs):
        _original_dispatcher_init(self,*args,**kwargs)
        self.include_router(_premium_router)
    _Dispatcher.__init__=_patched_dispatcher_init
except Exception:
    pass
