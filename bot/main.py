import os
import asyncio
import json
import hmac
import hashlib
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import parse_qsl

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    CallbackQuery,
    FSInputFile,
    Update,
)
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from .db import *

load_dotenv()
init()
seed_defaults()

TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP = os.getenv("WEBAPP_URL", "https://nukuspro.uz")
ADMIN = int(os.getenv("ADMIN_CHAT_ID", "8379731556"))
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))
PORT = int(os.getenv("PORT", "10000"))
SUB_REQUIRED = os.getenv("FORCE_SUB_REQUIRED", "1").lower() in ("1", "true", "yes")
SUB_CHANNEL = get_setting("subscription_channel", os.getenv("FORCE_SUB_CHANNEL", "@Rustambek_oqiw_orayi"))
SUB_URL = os.getenv("FORCE_SUB_URL", "https://t.me/Rustambek_oqiw_orayi")

dp = Dispatcher()
bot = Bot(TOKEN)
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://nukuspro.uz", "https://www.nukuspro.uz"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def times():
    return (
        get_setting("test_start", os.getenv("TEST_START", "08:30")),
        get_setting("test_end", os.getenv("TEST_END", "09:30")),
    )

def code_value():
    return get_setting("access_code", os.getenv("ACCESS_CODE", "0924"))

def test_mode():
    return get_setting("test_mode", "auto")

def open_now():
    s, e = times()
    mode = test_mode()
    now = datetime.now(TZ).time()
    if mode == "closed":
        return False
    if mode == "open":
        return True
    return time.fromisoformat(s) <= now < time.fromisoformat(e)

def user_open(u):
    if not u or not u["started_at"] or u["submitted"]:
        return False
    st = datetime.fromisoformat(u["started_at"])
    _, e = times()
    close = datetime.combine(st.date(), time.fromisoformat(e), tzinfo=TZ)
    return datetime.now(TZ) < min(st + timedelta(hours=1), close)

def expired(u):
    if not u or not u["started_at"] or u["submitted"]:
        return False
    st = datetime.fromisoformat(u["started_at"])
    _, e = times()
    close = datetime.combine(st.date(), time.fromisoformat(e), tzinfo=TZ)
    return datetime.now(TZ) >= min(st + timedelta(hours=1), close)

def web():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="TESTNI BOSHLASH", web_app=WebAppInfo(url=WEBAPP))]
        ]
    )

def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Telefon raqamingizni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def sub_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="KANALGA OBUNA BO‘LISH", url=SUB_URL)],
            [InlineKeyboardButton(text="OBUNANI TEKSHIRISH", callback_data="check_sub")],
        ]
    )

def admin_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Test sozlamalari"), KeyboardButton(text="Ishtirokchilar")],
            [KeyboardButton(text="Savollar"), KeyboardButton(text="Statistika")],
            [KeyboardButton(text="Real-time monitor"), KeyboardButton(text="Bildirishnoma")],
            [KeyboardButton(text="Majburiy obuna"), KeyboardButton(text="PDF natijalar")],
        ],
        resize_keyboard=True,
    )

def back_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Orqaga", callback_data="admin_home")]]
    )

def settings_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Boshlanish vaqti", callback_data="set_start"),
             InlineKeyboardButton(text="Tugash vaqti", callback_data="set_end")],
            [InlineKeyboardButton(text="Kirish kodi", callback_data="set_code")],
            [InlineKeyboardButton(text="Testni OCHISH", callback_data="mode_open"),
             InlineKeyboardButton(text="Testni YOPISH", callback_data="mode_closed")],
            [InlineKeyboardButton(text="Avto rejim", callback_data="mode_auto"),
             InlineKeyboardButton(text="Test holati", callback_data="test_status")],
            [InlineKeyboardButton(text="Orqaga", callback_data="admin_home")],
        ]
    )

def question_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Savolni tanlash", callback_data="q_pick_1"),
             InlineKeyboardButton(text="Yangi savol qo‘shish", callback_data="q_add")],
            [InlineKeyboardButton(text="Savol o‘chirish", callback_data="q_delete")],
            [InlineKeyboardButton(text="Savollar sonini belgilash", callback_data="q_count")],
            [InlineKeyboardButton(text="Barcha savollar ro‘yxati", callback_data="q_list")],
            [InlineKeyboardButton(text="Format", callback_data="q_format")],
            [InlineKeyboardButton(text="Orqaga", callback_data="admin_home")],
        ]
    )

def participants_kb(users):
    rows = []
    for u in users[:30]:
        name = (u["full_name"] or "Ismsiz")[:25]
        rows.append([InlineKeyboardButton(
            text=f"{name} · {u['score']:.1f}",
            callback_data=f"adm_user_{u['telegram_id']}"
        )])
    rows.append([InlineKeyboardButton(text="Orqaga", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def question_picker(page=0, mode="edit"):
    qs = active_questions()
    per_page = 15
    start = page * per_page
    part = qs[start:start + per_page]
    rows = []
    row = []
    for q in part:
        row.append(InlineKeyboardButton(text=str(q["id"]), callback_data=f"qsel_{mode}_{q['id']}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="←", callback_data=f"qpage_{mode}_{page-1}"))
    if start + per_page < len(qs):
        nav.append(InlineKeyboardButton(text="→", callback_data=f"qpage_{mode}_{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="Orqaga", callback_data="admin_questions")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def subscribed(tid):
    if not SUB_REQUIRED:
        return True
    try:
        m = await bot.get_chat_member(SUB_CHANNEL, tid)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return False

def parse_question_payload(text, existing=None):
    parts = [x.strip() for x in text.split("|")]
    if len(parts) < 3:
        raise ValueError("Format yetarli emas")
    qid = int(parts[0])
    question = parts[1]
    kind_or_answer = parts[2].lower()

    if kind_or_answer in ("written", "write", "text", "yozma"):
        options = []
        answer = existing["answer"] if existing else ""
        kind = "written"
        group_id = existing["group_id"] if existing else ""
        image_url = existing["image_url"] if existing else ""
        if len(parts) >= 4 and parts[3]:
            answer = parts[3]
        if len(parts) >= 5:
            group_id = parts[4]
        if len(parts) >= 6:
            image_url = parts[5]
        return qid, question, options, answer, kind, group_id, image_url

    if len(parts) < 7:
        raise ValueError("Choice format: ID|savol|1-4|A|B|C|D")
    correct = kind_or_answer
    if correct in ("a", "b", "c", "d"):
        correct = str({"a":1, "b":2, "c":3, "d":4}[correct])
    if correct not in ("1","2","3","4"):
        raise ValueError("To‘g‘ri variant 1, 2, 3, 4 yoki A, B, C, D bo‘lishi kerak")
    options = parts[3:7]
    if any(not x for x in options):
        raise ValueError("4 ta variantning hammasini yozing")
    answer = options[int(correct)-1]
    group_id = parts[7] if len(parts) >= 8 else (existing["group_id"] if existing else "")
    image_url = parts[8] if len(parts) >= 9 else (existing["image_url"] if existing else "")
    return qid, question, options, answer, "choice", group_id, image_url

def progress_text(u):
    try:
        total = len(active_questions())
        done = len(json.loads(u["answers_json"] or "{}"))
    except Exception:
        total, done = 0, 0
    return f"{done}/{total}"

@dp.message(Command("start"))
async def start(m: Message):
    ensure_user(m.from_user.id)
    if m.from_user.id == ADMIN:
        update_user(m.from_user.id, state="admin")
        await m.answer("NUR O‘QIW ORAYI\n\nAdmin boshqaruv paneli.", reply_markup=admin_kb())
        return
    update_user(m.from_user.id, state="code", code_ok=0)
    await m.answer("NUR O‘QIW ORAYI — Milliy sertifikat boti.\n\nKirish kodini kiriting:")

@dp.message(Command("stars"))
async def stars(m: Message):
    ensure_user(m.from_user.id)
    update_user(m.from_user.id, state="code", code_ok=0)
    await m.answer("NUR O‘QIW ORAYI — Milliy sertifikat boti.\n\nKirish kodini kiriting:")

@dp.callback_query(F.data == "check_sub")
async def check_sub(q: CallbackQuery):
    if await subscribed(q.from_user.id):
        update_user(q.from_user.id, state="name", code_ok=1)
        await q.message.answer("📝 Ro‘yxatdan o‘tish\n\n👤 Ism, Familiya kiriting:")
    else:
        await q.message.answer("Kanalga obuna bo‘lish topilmadi. Avval kanalga obuna bo‘ling.")
    await q.answer()

@dp.message(F.contact)
async def contact(m: Message):
    u = ensure_user(m.from_user.id)
    if u["state"] != "phone":
        await m.answer("Avval ism, familiyangizni kiriting.")
        return
    phone = m.contact.phone_number
    if m.contact.user_id and m.contact.user_id != m.from_user.id:
        await m.answer("Telefon raqami sizning Telegram akkauntingizga tegishli bo‘lishi kerak.")
        return
    upsert_user(m.from_user.id, u["full_name"], phone)
    update_user(m.from_user.id, state="ready")
    await m.answer(
        "✅ Xush kelibsiz!\n\n👤 " + (u["full_name"] or "—") +
        "\n📱 " + phone +
        "\n\nTelegram akkauntingiz bog‘landi!\n\n🧮 Endi siz test yecha olasiz!",
        reply_markup=web()
    )

@dp.callback_query(F.data == "admin_home")
async def admin_home(q: CallbackQuery):
    if q.from_user.id != ADMIN:
        await q.answer("Ruxsat yo‘q", show_alert=True)
        return
    update_user(ADMIN, state="admin")
    await q.message.edit_text("Admin boshqaruv paneli.")
    await q.message.answer("Pastki menyudan bo‘limni tanlang.", reply_markup=admin_kb())
    await q.answer()

@dp.callback_query(F.data == "admin_settings")
async def admin_settings_callback(q: CallbackQuery):
    if q.from_user.id != ADMIN:
        await q.answer("Ruxsat yo‘q", show_alert=True)
        return
    s, e = times()
    mode = test_mode()
    await q.message.edit_text(
        f"TEST SOZLAMALARI\n\nBoshlanish: {s}\nTugash: {e}\nKirish kodi: {code_value()}\nRejim: {mode}",
        reply_markup=settings_kb()
    )
    await q.answer()

@dp.callback_query(F.data == "set_start")
async def set_start(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    update_user(ADMIN, state="admin_start")
    await q.message.edit_text("Boshlanish vaqtini yozing. Masalan: 08:30")
    await q.answer()

@dp.callback_query(F.data == "set_end")
async def set_end(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    update_user(ADMIN, state="admin_end")
    await q.message.edit_text("Tugash vaqtini yozing. Masalan: 09:30")
    await q.answer()

@dp.callback_query(F.data == "set_code")
async def set_code_cb(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    update_user(ADMIN, state="admin_code")
    await q.message.edit_text("Yangi kirish kodini yozing:")
    await q.answer()

@dp.callback_query(F.data == "mode_open")
async def mode_open(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    set_setting("test_mode", "open")
    await q.message.edit_text("Test majburiy ravishda OCHILDI.", reply_markup=settings_kb())
    await q.answer()

@dp.callback_query(F.data == "mode_closed")
async def mode_closed(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    set_setting("test_mode", "closed")
    await q.message.edit_text("Test majburiy ravishda YOPILDI. Faol testlar avtomatik yakunlanadi.", reply_markup=settings_kb())
    for u in all_users():
        if u["started_at"] and not u["submitted"]:
            try:
                await finalize_user(u["telegram_id"], reason="Admin testni yopdi.")
            except Exception:
                pass
    await q.answer()

@dp.callback_query(F.data == "mode_auto")
async def mode_auto(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    set_setting("test_mode", "auto")
    await q.message.edit_text("Avto rejim yoqildi. Test jadval bo‘yicha ishlaydi.", reply_markup=settings_kb())
    await q.answer()

@dp.callback_query(F.data == "test_status")
async def test_status(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    s, e = times()
    active = sum(1 for u in all_users() if user_open(u))
    status = "OCHIQ" if open_now() else "YOPIQ"
    await q.message.edit_text(
        f"TEST HOLATI\n\nHolat: {status}\nRejim: {test_mode()}\nVaqt: {s}–{e}\nFaol qatnashchilar: {active}",
        reply_markup=settings_kb()
    )
    await q.answer()

@dp.callback_query(F.data == "admin_questions")
async def admin_questions(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    await q.message.edit_text(f"SAVOLLAR\n\nFaol savollar: {len(active_questions())}", reply_markup=question_menu_kb())
    await q.answer()

@dp.callback_query(F.data == "q_pick_1")
async def q_pick(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    await q.message.edit_text("Tahrirlash uchun savol raqamini tanlang:", reply_markup=question_picker(0, "edit"))
    await q.answer()

@dp.callback_query(F.data.startswith("qpage_"))
async def q_page(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    _, mode, page = q.data.split("_")
    await q.message.edit_reply_markup(reply_markup=question_picker(int(page), mode))
    await q.answer()

@dp.callback_query(F.data.startswith("qsel_edit_"))
async def q_select_edit(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    qid = int(q.data.split("_")[-1])
    row = get_question(qid)
    if not row:
        await q.answer("Savol topilmadi", show_alert=True)
        return
    opts = json.loads(row["options_json"] or "[]")
    if row["kind"] == "written":
        body = f"{qid}. {row['question']}\nTur: yozma\nJavob: {row['answer']}"
    else:
        body = f"{qid}. {row['question']}\n" + "\n".join(
            f"{chr(65+i)}. {x}" for i,x in enumerate(opts)
        ) + f"\nTo‘g‘ri: {row['answer']}"
    update_user(ADMIN, state=f"admin_qedit_{qid}")
    await q.message.edit_text(
        body + "\n\nYangi formatni yuboring:\nID|savol|1|A|B|C|D",
        reply_markup=back_kb()
    )
    await q.answer()

@dp.callback_query(F.data == "q_add")
async def q_add(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    update_user(ADMIN, state="admin_qadd")
    await q.message.edit_text(
        "Yangi savolni yuboring:\n\nChoice:\nID|savol|1|A|B|C|D\n\nYozma:\nID|savol|written|javob",
        reply_markup=back_kb()
    )
    await q.answer()

@dp.callback_query(F.data == "q_delete")
async def q_delete(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    update_user(ADMIN, state="admin_qdelete")
    await q.message.edit_text("O‘chirish uchun savol raqamini yozing. Masalan: 24", reply_markup=back_kb())
    await q.answer()

@dp.callback_query(F.data == "q_count")
async def q_count(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    update_user(ADMIN, state="admin_qcount")
    await q.message.edit_text(
        f"Hozir {len(active_questions())} ta faol savol bor. Yangi sonni 1–100 oralig‘ida yozing.",
        reply_markup=back_kb()
    )
    await q.answer()

@dp.callback_query(F.data == "q_list")
async def q_list(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    qs = active_questions()
    lines = []
    for row in qs:
        lines.append(f"{row['id']}. {row['question'][:90]}")
    text = "BARCHA FAOL SAVOLLAR\n\n" + "\n".join(lines)
    await q.message.edit_text(text[:3900], reply_markup=back_kb())
    await q.answer()

@dp.callback_query(F.data == "q_format")
async def q_format(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    await q.message.edit_text(
        "SAVOL FORMATLARI\n\n"
        "Variantli:\nID|savol|TO‘G‘RI(1-4)|A|B|C|D\n"
        "Misol:\n24|Tenglamani yeching|3|2x+1=5|x=2|x=3|x=4\n\n"
        "Yozma:\nID|savol|written|JAVOB\n"
        "33–35 bir xil rasm bo‘lsa group_id va image_url ni ham qo‘shish mumkin:\n"
        "33|savol|2|A|B|C|D|fig33|https://...\n"
        "Shu formatda savolni raqami bo‘yicha tanlab to‘liq boshqarish mumkin.",
        reply_markup=back_kb()
    )
    await q.answer()

@dp.callback_query(F.data.startswith("adm_user_"))
async def admin_user(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    tid = int(q.data.split("_")[-1])
    u = get_user(tid)
    if not u:
        await q.answer("Topilmadi", show_alert=True)
        return
    update_user(ADMIN, state=f"admin_result_{tid}")
    await q.message.edit_text(
        f"ISHTIROKCHI\n\n"
        f"Ism: {u['full_name'] or '—'}\n"
        f"Telefon: {u['phone'] or '—'}\n"
        f"Telegram ID: {tid}\n"
        f"Joriy ball: {u['score']:.2f}\n"
        f"Baho: {u['grade'] or '—'}\n"
        f"Javoblar: {progress_text(u)}\n"
        f"Status: {'Yakunlangan' if u['submitted'] else 'Faol' if user_open(u) else 'Kutmoqda'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ballni o‘zgartirish", callback_data=f"res_score_{tid}")],
            [InlineKeyboardButton(text="Bahoni o‘zgartirish", callback_data=f"res_grade_{tid}")],
            [InlineKeyboardButton(text="Qayta hisoblash", callback_data=f"res_recalc_{tid}")],
            [InlineKeyboardButton(text="Javoblarni ko‘rish", callback_data=f"res_answers_{tid}")],
            [InlineKeyboardButton(text="Orqaga", callback_data="admin_participants")],
        ])
    )
    await q.answer()

@dp.callback_query(F.data.startswith("res_score_"))
async def res_score(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    tid = int(q.data.split("_")[-1])
    update_user(ADMIN, state=f"admin_score_{tid}")
    await q.message.edit_text("Yangi ballni yozing. Masalan: 87.50", reply_markup=back_kb())
    await q.answer()

@dp.callback_query(F.data.startswith("res_grade_"))
async def res_grade(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    tid = int(q.data.split("_")[-1])
    update_user(ADMIN, state=f"admin_grade_{tid}")
    await q.message.edit_text("Yangi bahoni yozing. Masalan: A, B, C yoki A+", reply_markup=back_kb())
    await q.answer()

@dp.callback_query(F.data.startswith("res_recalc_"))
async def res_recalc(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    tid = int(q.data.split("_")[-1])
    u = get_user(tid)
    if u:
        answers = json.loads(u["answers_json"] or "{}")
        score = weighted_score(answers)
        grade = grade_for(score)
        finish_user(tid, score, grade, datetime.now(TZ).isoformat(), answers)
        await q.message.edit_text(f"Qayta hisoblandi. Ball: {score:.2f}\nBaho: {grade}", reply_markup=back_kb())
    await q.answer()

@dp.callback_query(F.data.startswith("res_answers_"))
async def res_answers(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    tid = int(q.data.split("_")[-1])
    u = get_user(tid)
    if not u:
        await q.answer("Topilmadi", show_alert=True); return
    answers = json.loads(u["answers_json"] or "{}")
    text = "JAVOBLAR\n\n" + "\n".join(f"{k}: {v}" for k,v in sorted(answers.items(), key=lambda x:int(x[0])))
    await q.message.edit_text(text[:3900], reply_markup=back_kb())
    await q.answer()

@dp.callback_query(F.data == "admin_participants")
async def admin_participants(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    users = all_users()
    await q.message.edit_text(
        f"ISHTIROKCHILAR\n\nJami: {len(users)}\nTanlash uchun ishtirokchini bosing.",
        reply_markup=participants_kb(users)
    )
    await q.answer()

async def monitor_message():
    users = all_users()
    active = [u for u in users if user_open(u)]
    s,e = times()
    lines = [
        "REAL-TIME MONITOR",
        "",
        f"Test: {'OCHIQ' if open_now() else 'YOPIQ'} · {s}–{e}",
        f"Faol: {len(active)} · Jami: {len(users)}",
        ""
    ]
    for i,u in enumerate(active[:25],1):
        lines.append(f"{i}. {u['full_name'] or '—'} · {progress_text(u)}")
    if not active:
        lines.append("Hozir faol qatnashchi yo‘q.")
    return "\n".join(lines)

@dp.callback_query(F.data == "monitor_refresh")
async def monitor_refresh(q: CallbackQuery):
    if q.from_user.id != ADMIN:
        await q.answer("Ruxsat yo‘q", show_alert=True)
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yangilash", callback_data="monitor_refresh")],
        [InlineKeyboardButton(text="Orqaga", callback_data="admin_home")],
    ])
    try:
        await q.message.edit_text(await monitor_message(), reply_markup=markup)
    except Exception as exc:
        # Telegram returns "message is not modified" when nothing changed.
        if "message is not modified" not in str(exc).lower():
            raise
    await q.answer()

async def live_monitor(q: CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yangilash", callback_data="monitor_refresh")],
        [InlineKeyboardButton(text="Orqaga", callback_data="admin_home")],
    ])
    last = None
    for _ in range(12):
        try:
            body = await monitor_message()
            if body != last:
                try:
                    await q.message.edit_text(body, reply_markup=markup)
                except Exception as exc:
                    if "message is not modified" not in str(exc).lower():
                        raise
                last = body
        except Exception:
            # A monitor refresh must never break the dispatcher.
            pass
        await asyncio.sleep(5)

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    users = all_users()
    started = sum(1 for u in users if u["started_at"])
    finished = sum(1 for u in users if u["submitted"])
    active = sum(1 for u in users if user_open(u))
    scores = [float(u["score"]) for u in users if u["submitted"]]
    avg = sum(scores)/len(scores) if scores else 0
    grades = {}
    for u in users:
        if u["submitted"]:
            grades[u["grade"] or "—"] = grades.get(u["grade"] or "—", 0) + 1
    grade_line = ", ".join(f"{k}: {v}" for k,v in sorted(grades.items()))
    qs = active_questions()
    with conn() as c:
        hardest = c.execute(
            "SELECT question_id,attempts,correct FROM item_stats WHERE attempts>0 "
            "ORDER BY CAST(correct AS REAL)/attempts ASC, attempts DESC LIMIT 5"
        ).fetchall()
    hard_line = []
    for st in hardest:
        pct = st["correct"]/st["attempts"]*100
        hard_line.append(f"#{st['question_id']} — {pct:.0f}% to‘g‘ri")
    await q.message.edit_text(
        "STATISTIKA\n\n"
        f"Foydalanuvchi: {len(users)}\n"
        f"Testni boshlagan: {started}\n"
        f"Yakunlagan: {finished}\n"
        f"Hozir faol: {active}\n"
        f"O‘rtacha ball: {avg:.2f}\n"
        f"Baho taqsimoti: {grade_line or '—'}\n"
        f"Faol savollar: {len(qs)}\n\n"
        f"Eng qiyin savollar:\n" + ("\n".join(hard_line) if hard_line else "Hali statistika yo‘q."),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Yangilash", callback_data="admin_stats")],
            [InlineKeyboardButton(text="Orqaga", callback_data="admin_home")],
        ])
    )
    await q.answer()

@dp.message()
async def text_handler(m: Message):
    if not m.text:
        return

    u = ensure_user(m.from_user.id)
    st = u["state"] or "code"
    text_value = m.text.strip()

    if m.from_user.id == ADMIN:
        if text_value == "Test sozlamalari":
            s,e = times()
            await m.answer(
                f"TEST SOZLAMALARI\n\nBoshlanish: {s}\nTugash: {e}\nKod: {code_value()}\nRejim: {test_mode()}",
                reply_markup=settings_kb()
            )
            return
        if text_value == "Ishtirokchilar":
            users = all_users()
            await m.answer(
                f"ISHTIROKCHILAR\n\nJami: {len(users)}",
                reply_markup=participants_kb(users)
            )
            return
        if text_value == "Savollar":
            await m.answer(f"SAVOLLAR\n\nFaol savollar: {len(active_questions())}", reply_markup=question_menu_kb())
            return
        if text_value == "Statistika":
            users = all_users()
            started = sum(1 for x in users if x["started_at"])
            finished = sum(1 for x in users if x["submitted"])
            active = sum(1 for x in users if user_open(x))
            scores = [float(x["score"]) for x in users if x["submitted"]]
            avg = sum(scores)/len(scores) if scores else 0
            await m.answer(
                f"STATISTIKA\n\nFoydalanuvchilar: {len(users)}\nBoshlagan: {started}\nYakunlagan: {finished}\nFaol: {active}\nO‘rtacha ball: {avg:.2f}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="To‘liq statistika", callback_data="admin_stats")],
                    [InlineKeyboardButton(text="Orqaga", callback_data="admin_home")]
                ])
            )
            return
        if text_value == "Real-time monitor":
            await m.answer(await monitor_message(), reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Jonli kuzatish (1 daqiqa)", callback_data="monitor_live")],
                    [InlineKeyboardButton(text="Yangilash", callback_data="monitor_refresh")],
                    [InlineKeyboardButton(text="Orqaga", callback_data="admin_home")],
                ]
            ))
            return
        if text_value == "Bildirishnoma":
            update_user(ADMIN, state="admin_broadcast")
            await m.answer("Hammaga yuboriladigan xabarni yozing.")
            return
        if text_value == "Majburiy obuna":
            update_user(ADMIN, state="admin_sub")
            await m.answer(
                f"Majburiy obuna: {'Yoqilgan' if SUB_REQUIRED else 'O‘chirilgan'}\n"
                f"Joriy kanal: {SUB_CHANNEL}\n\n"
                "Kanal nomini yozing. Masalan: @Rustambek_oqiw_orayi"
            )
            return
        if text_value == "PDF natijalar":
            path = "/tmp/nur_results.pdf"
            make_pdf(path)
            await bot.send_document(ADMIN, document=FSInputFile(path))
            await m.answer("PDF admin chatiga yuborildi.", reply_markup=admin_kb())
            return

        if st == "admin_start":
            try:
                time.fromisoformat(text_value)
            except ValueError:
                await m.answer("Noto‘g‘ri format. Masalan: 08:30")
                return
            set_setting("test_start", text_value)
            update_user(ADMIN, state="admin")
            await m.answer("Boshlanish vaqti saqlandi.", reply_markup=admin_kb())
            return

        if st == "admin_end":
            try:
                time.fromisoformat(text_value)
            except ValueError:
                await m.answer("Noto‘g‘ri format. Masalan: 09:30")
                return
            set_setting("test_end", text_value)
            update_user(ADMIN, state="admin")
            await m.answer("Tugash vaqti saqlandi.", reply_markup=admin_kb())
            return

        if st == "admin_code":
            if not text_value:
                await m.answer("Kod bo‘sh bo‘lmasin.")
                return
            set_setting("access_code", text_value)
            update_user(ADMIN, state="admin")
            await m.answer("Kirish kodi saqlandi.", reply_markup=admin_kb())
            return

        if st == "admin_broadcast":
            sent = 0
            failed = 0
            for usr in all_users():
                try:
                    await bot.send_message(usr["telegram_id"], text_value)
                    sent += 1
                    await asyncio.sleep(0.04)
                except Exception:
                    failed += 1
            update_user(ADMIN, state="admin")
            await m.answer(f"Bildirishnoma yakunlandi.\nYuborildi: {sent}\nXato: {failed}", reply_markup=admin_kb())
            return

        if st == "admin_sub":
            ch = text_value if text_value.startswith("@") else "@" + text_value
            set_setting("subscription_channel", ch)
            update_user(ADMIN, state="admin")
            await m.answer(f"Majburiy obuna kanali saqlandi: {ch}\n\nEslatma: bot kanalga kira olishi uchun kerakli huquqqa ega bo‘lsin.", reply_markup=admin_kb())
            return

        if st.startswith("admin_qedit_"):
            try:
                old_qid = int(st.split("_")[-1])
                existing = get_question(old_qid)
                parsed = parse_question_payload(text_value, existing=existing)
                qid, question, options, answer, kind, group_id, image_url = parsed
                upsert_question(qid, question, options, answer, kind, group_id, image_url)
                update_user(ADMIN, state="admin")
                await m.answer(f"Savol {qid} muvaffaqiyatli yangilandi.", reply_markup=admin_kb())
            except Exception as exc:
                await m.answer(f"Savol saqlanmadi: {exc}")
            return

        if st == "admin_qadd":
            try:
                qid, question, options, answer, kind, group_id, image_url = parse_question_payload(text_value)
                upsert_question(qid, question, options, answer, kind, group_id, image_url)
                update_user(ADMIN, state="admin")
                await m.answer(f"Savol {qid} qo‘shildi/yangilandi.", reply_markup=admin_kb())
            except Exception as exc:
                await m.answer(f"Savol saqlanmadi: {exc}")
            return

        if st == "admin_qdelete":
            try:
                qid = int(text_value)
                if delete_question(qid):
                    update_user(ADMIN, state="admin")
                    await m.answer(f"Savol {qid} o‘chirildi.", reply_markup=admin_kb())
                else:
                    await m.answer("Bunday savol topilmadi.")
            except ValueError:
                await m.answer("Faqat savol raqamini yozing. Masalan: 24")
            return

        if st == "admin_qcount":
            try:
                n = int(text_value)
                if not 1 <= n <= 100:
                    raise ValueError
                set_active_question_count(n)
                update_user(ADMIN, state="admin")
                await m.answer(f"Faol savollar soni {len(active_questions())} ta qilib belgilandi.", reply_markup=admin_kb())
            except ValueError:
                await m.answer("1 dan 100 gacha son yozing.")
            return

        if st.startswith("admin_score_"):
            try:
                tid = int(st.split("_")[-1])
                score = float(text_value.replace(",", "."))
                if score < 0 or score > 100: raise ValueError
                update_user(tid, score=score)
                update_user(ADMIN, state="admin")
                await m.answer("Ball yangilandi.", reply_markup=admin_kb())
            except ValueError:
                await m.answer("Ball 0–100 oralig‘ida bo‘lsin. Masalan: 87.50")
            return

        if st.startswith("admin_grade_"):
            tid = int(st.split("_")[-1])
            update_user(tid, grade=text_value)
            update_user(ADMIN, state="admin")
            await m.answer("Baho yangilandi.", reply_markup=admin_kb())
            return

        # Admin can always return home from text.
        if text_value.lower() in ("orqaga", "back"):
            update_user(ADMIN, state="admin")
            await m.answer("Admin boshqaruv paneli.", reply_markup=admin_kb())
            return

    if st == "code":
        if text_value != code_value():
            await m.answer("Kirish kodi noto‘g‘ri. Qaytadan kiriting.")
            return
        if not open_now():
            s,e = times()
            await m.answer(f"Kodingiz to‘g‘ri, lekin test hozir ochilmagan.\n\nTest vaqti: {s}–{e}.")
            return
        if not await subscribed(m.from_user.id):
            update_user(m.from_user.id, state="subscribe", code_ok=1)
            await m.answer("Testga kirish uchun kanalga obuna bo‘ling.", reply_markup=sub_kb())
            return
        update_user(m.from_user.id, state="name", code_ok=1)
        await m.answer("📝 Ro‘yxatdan o‘tish\n\n👤 Ism, Familiya kiriting:")
        return

    if st == "subscribe":
        await m.answer("Avval kanalga obuna bo‘ling va tekshirish tugmasini bosing.", reply_markup=sub_kb())
        return

    if st == "name":
        if len(text_value) < 3:
            await m.answer("Ism va familiyangizni to‘liqroq kiriting.")
            return
        upsert_user(m.from_user.id, text_value)
        update_user(m.from_user.id, state="phone")
        await m.answer(
            "QABUL QILINDI\n\n📱 Telefon raqamingizni kiriting:\n\n"
            "Format: +998901234567\nMisol: +998901234567",
            reply_markup=phone_kb()
        )
        return

    if st == "phone":
        if re.fullmatch(r"\+998\d{9}", text_value):
            upsert_user(m.from_user.id, u["full_name"], text_value)
            update_user(m.from_user.id, state="ready")
            await m.answer(
                "✅ Xush kelibsiz!\n\n👤 " + (u["full_name"] or "—") +
                "\n📱 " + text_value +
                "\n\nTelegram akkauntingiz bog‘landi!\n\n🧮 Endi siz test yecha olasiz!",
                reply_markup=web()
            )
        else:
            await m.answer("Telefon raqami noto‘g‘ri.\nFormat: +998901234567")
        return

    if st == "ready":
        if open_now():
            await m.answer("Testni boshlash uchun tugmani bosing.", reply_markup=web())
        else:
            s,e = times()
            await m.answer(f"Test hozir yopiq. Vaqt: {s}–{e}.")
        return

@app.get("/health")
def health():
    return {"ok": True, "test": times(), "mode": test_mode(), "questions": len(active_questions())}

def telegram_user(init_data):
    try:
        data = dict(parse_qsl(init_data or "", keep_blank_values=True))
        received = data.pop("hash", None)
        auth = int(data.get("auth_date", "0"))
        user = json.loads(data.get("user", "{}"))
        tid = int(user.get("id"))
        check = "\n".join(k + "=" + data[k] for k in sorted(data))
        secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        fresh = datetime.now(timezone.utc).timestamp() - auth <= 86400
        return tid if received and hmac.compare_digest(calc, received) and fresh else None
    except Exception:
        return None

async def finalize_user(tid, reason="Vaqt tugadi."):
    u = get_user(tid)
    if not u or u["submitted"]:
        return False
    answers = json.loads(u["answers_json"] or "{}")
    record_stats(answers)
    score = weighted_score(answers)
    grade = grade_for(score)
    finish_user(tid, score, grade, datetime.now(TZ).isoformat(), answers)
    try:
        await bot.send_message(tid, f"Test yakunlandi.\n\nBall: {score:.2f}\nBaho: {grade}\n\n{reason}")
    except Exception:
        pass
    return True

@app.get("/api/state")
async def api_state(request: Request):
    tid = telegram_user(request.query_params.get("initData", ""))
    u = get_user(tid) if tid else None
    if not u or not u["code_ok"]:
        return JSONResponse({"ok": False, "error": "not_authorized"}, status_code=401)
    if u["submitted"]:
        return {"ok": False, "error": "already_submitted", "score": u["score"], "grade": u["grade"]}
    if not open_now() and not u["started_at"]:
        return {"ok": False, "error": "test_closed"}
    if u["started_at"] and expired(u):
        await finalize_user(tid)
        return {"ok": False, "error": "test_closed"}
    if not u["started_at"]:
        update_user(tid, started_at=datetime.now(TZ).isoformat())
        u = get_user(tid)
    st = datetime.fromisoformat(u["started_at"])
    _,e = times()
    close = datetime.combine(st.date(), time.fromisoformat(e), tzinfo=TZ)
    ends = min(st + timedelta(hours=1), close)
    return {
        "ok": True,
        "answers": json.loads(u["answers_json"] or "{}"),
        "ends_at": ends.isoformat(),
        "started_at": u["started_at"],
        "total_questions": len(active_questions()),
    }

@app.get("/api/questions")
def questions():
    return [
        {
            "id": q["id"],
            "question": q["question"],
            "options": json.loads(q["options_json"] or "[]"),
            "kind": q["kind"],
            "group_id": q["group_id"],
            "image_url": q["image_url"],
        }
        for q in active_questions()
    ]

@app.post("/api/answer")
async def answer_api(p: dict):
    tid = telegram_user(p.get("initData", ""))
    u = get_user(tid) if tid else None
    if not u or not u["code_ok"] or u["submitted"]:
        return {"ok": False, "error": "not_authorized"}
    if expired(u):
        await finalize_user(tid)
        return {"ok": False, "error": "test_closed"}
    q = get_question(p.get("question_id"))
    if not q:
        return {"ok": False, "error": "question_not_found"}
    answers = json.loads(u["answers_json"] or "{}")
    key = str(q["id"])
    if key in answers:
        return {
            "ok": False,
            "error": "answer_locked",
            "correct": normalize(answers[key]) == normalize(q["answer"]),
            "saved_answer": answers[key],
        }
    value = str(p.get("answer", "")).strip()
    if not value:
        return {"ok": False, "error": "empty_answer"}
    answers[key] = value
    save_answers(tid, answers)
    correct = bool(q["answer"]) and normalize(value) == normalize(q["answer"])
    return {"ok": True, "locked": True, "correct": correct, "saved_answer": value}

@app.post("/api/finish")
async def finish_api(p: dict):
    tid = telegram_user(p.get("initData", ""))
    u = get_user(tid) if tid else None
    if not u or not u["code_ok"]:
        return {"ok": False, "error": "not_authorized"}
    if not u["started_at"]:
        return {"ok": False, "error": "not_started"}
    if u["submitted"]:
        return {"ok": True, "score": u["score"], "grade": u["grade"]}
    answers = json.loads(u["answers_json"] or "{}")
    record_stats(answers)
    score = weighted_score(answers)
    grade = grade_for(score)
    finish_user(tid, score, grade, datetime.now(TZ).isoformat(), answers)
    return {"ok": True, "score": score, "grade": grade}

def admin_ok(r: Request):
    return bool(os.getenv("ADMIN_KEY")) and r.headers.get("X-Admin-Key") == os.getenv("ADMIN_KEY")

@app.post("/admin/settings")
async def admin_settings_api(p: dict, r: Request):
    if not admin_ok(r):
        return {"ok": False, "error": "admin key noto‘g‘ri"}
    if p.get("start"): set_setting("test_start", p["start"])
    if p.get("end"): set_setting("test_end", p["end"])
    if p.get("code"): set_setting("access_code", p["code"])
    if p.get("mode") in ("auto","open","closed"): set_setting("test_mode", p["mode"])
    return {"ok": True, "test": times(), "mode": test_mode()}

@app.post("/admin/questions")
async def admin_questions_api(p: dict, r: Request):
    if not admin_ok(r):
        return {"ok": False, "error": "admin key noto‘g‘ri"}
    items = p if isinstance(p, list) else p.get("questions", [])
    if not items or len(items) > 100:
        return {"ok": False, "error": "1–100 ta savol bo‘lishi kerak"}
    rows = []
    for i,x in enumerate(items,1):
        qid = int(x.get("id",i))
        rows.append((
            qid,
            str(x.get("question","")),
            json.dumps(x.get("options",[]), ensure_ascii=False),
            str(x.get("answer","")),
            str(x.get("kind","choice")),
            str(x.get("group_id","")),
            str(x.get("image_url",""))
        ))
    replace_questions(rows)
    return {"ok": True, "count": len(active_questions())}

@app.get("/admin/users")
async def admin_users_api(r: Request):
    if not admin_ok(r):
        return {"ok": False, "error": "admin key noto‘g‘ri"}
    return {"ok": True, "users": [dict(x) for x in all_users()]}

@app.post("/admin/result")
async def admin_result_api(p: dict, r: Request):
    if not admin_ok(r):
        return {"ok": False, "error": "admin key noto‘g‘ri"}
    tid = int(p.get("telegram_id"))
    u = get_user(tid)
    if not u:
        return {"ok": False, "error": "user topilmadi"}
    fields = {}
    if p.get("score") is not None: fields["score"] = float(p["score"])
    if p.get("grade") is not None: fields["grade"] = str(p["grade"])
    update_user(tid, **fields)
    return {"ok": True}

@app.post("/admin/pdf")
async def admin_pdf(r: Request):
    if not admin_ok(r):
        return {"ok": False, "error": "admin key noto‘g‘ri"}
    path="/tmp/nur_results.pdf"
    make_pdf(path)
    await bot.send_document(ADMIN, document=FSInputFile(path))
    return {"ok": True}

@app.post("/admin/broadcast")
async def broadcast(p: dict, r: Request):
    if not admin_ok(r):
        return {"ok": False, "error": "admin key noto‘g‘ri"}
    txt = str(p.get("text","")).strip()
    sent = 0
    for u in all_users():
        try:
            await bot.send_message(u["telegram_id"], txt)
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            pass
    return {"ok": True, "sent": sent}

def make_pdf(path):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        path,
        pagesize=landscape(A4),
        rightMargin=24,leftMargin=24,topMargin=24,bottomMargin=24
    )
    rows = [["№","Ism Familiya","Ball","Baho"]]
    users = all_users()
    for i,u in enumerate(users,1):
        rows.append([str(i), u["full_name"] or "—", f"{u['score']:.2f}", u["grade"] or "—"])
    story = [
        Paragraph("NUR O‘QIW ORAYI — TEST NATIJALARI", styles["Title"]),
        Paragraph(f"Ishtirokchilar: {len(users)}", styles["Heading2"]),
        Spacer(1,10),
    ]
    table = Table(rows, repeatRows=1, colWidths=[35,430,80,70])
    table.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),.5,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eeeeee")),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
    ]))
    story.append(table)
    doc.build(story)

async def auto_finalize():
    sent_days = set()
    while True:
        try:
            now = datetime.now(TZ)
            _, end = times()
            for u in all_users():
                if expired(u):
                    await finalize_user(u["telegram_id"])
            day = now.strftime("%Y-%m-%d")
            key = f"pdf_sent_{day}"
            if now.time() >= time.fromisoformat(end) and not get_setting(key,"") and any(
                u["started_at"] or u["submitted"] for u in all_users()
            ):
                path = "/tmp/nur_results.pdf"
                make_pdf(path)
                await bot.send_document(ADMIN, document=FSInputFile(path))
                set_setting(key, "1")
                sent_days.add(day)
        except Exception:
            pass
        await asyncio.sleep(10)

@dp.callback_query(F.data == "monitor_live")
async def monitor_live(q: CallbackQuery):
    if q.from_user.id != ADMIN: return
    await q.answer("Jonli monitoring boshlandi")
    await live_monitor(q)

WEBHOOK_BASE = os.getenv("WEBHOOK_BASE_URL", "https://nur-oqiw.onrender.com").rstrip("/")
WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or hashlib.sha256(TOKEN.encode()).hexdigest()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    expected = WEBHOOK_SECRET
    if expected:
        received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(received, expected):
            return JSONResponse({"ok": False}, status_code=403)
    try:
        payload = await request.json()
        update = Update.model_validate(payload)
        await dp.feed_update(bot, update)
        return {"ok": True}
    except Exception:
        # Always acknowledge valid Telegram delivery so one bad update cannot
        # make the bot look frozen or cause repeated webhook retries.
        return {"ok": True}

async def run():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN missing")
    await bot.set_webhook(
        url=WEBHOOK_BASE + WEBHOOK_PATH,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=False,
        allowed_updates=dp.resolve_used_update_types(),
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    )
    await asyncio.gather(
        server.serve(),
        auto_finalize(),
    )

if __name__ == "__main__":
    asyncio.run(run())
