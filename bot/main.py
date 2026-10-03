import os, asyncio, logging, json, hmac, hashlib, re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import parse_qsl
from collections import defaultdict, deque
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery, FSInputFile, Update
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from .db import *

load_dotenv(); init(); seed_defaults()
TOKEN=os.getenv("BOT_TOKEN","")
WEBAPP=os.getenv("WEBAPP_URL","https://nukuspro.uz")
ADMIN=int(os.getenv("ADMIN_CHAT_ID","8379731556"))
TZ=ZoneInfo(os.getenv("TIMEZONE","Asia/Tashkent"))
PORT=int(os.getenv("PORT","10000"))
WEB_ORIGINS=[x.strip().rstrip("/") for x in os.getenv("WEBAPP_ORIGINS","https://nukuspro.uz,https://www.nukuspro.uz").split(",") if x.strip()]
RATE_BUCKET=defaultdict(deque); RATE_LIMIT=180; RATE_WINDOW=60
logging.basicConfig(level=logging.INFO); logger=logging.getLogger("nur-oqiw")
dp=Dispatcher(); bot=Bot(TOKEN); app=FastAPI()
app.add_middleware(CORSMiddleware,allow_origins=WEB_ORIGINS,allow_credentials=True,allow_methods=["GET","POST","OPTIONS"],allow_headers=["Content-Type","X-Admin-Key"])

# Register profile/tariff handlers before the project's catch-all message handler.
# The module only consumes its own exact buttons/callbacks and leaves all other states to main.py.
from .profile_features import register as register_profile_features, user_menu, admin_tariff_list
register_profile_features(dp, bot, WEBAPP)

def setting_bool(key,default=False): return str(get_setting(key,"1" if default else "0")).lower() in ("1","true","yes","on")
def times(): return get_setting("test_start",os.getenv("TEST_START","08:30")),get_setting("test_end",os.getenv("TEST_END","09:30"))
def code_value(): return get_setting("access_code",os.getenv("ACCESS_CODE","0924"))
def test_mode(): return get_setting("test_mode","auto")
def sub_required(): return setting_bool("subscription_enabled",False)
def sub_channels(): return [x.strip() for x in get_setting("subscription_channels","").split("\n") if x.strip()]
def open_now():
    s,e=times(); mode=test_mode(); now=datetime.now(TZ).time()
    if mode=="closed": return False
    if mode=="open": return True
    return time.fromisoformat(s)<=now<time.fromisoformat(e)
def user_open(u):
    if not u or not u["started_at"] or u["submitted"]: return False
    st=datetime.fromisoformat(u["started_at"]); _,e=times(); close=datetime.combine(st.date(),time.fromisoformat(e),tzinfo=TZ)
    return datetime.now(TZ)<min(st+timedelta(hours=1),close)
def expired(u):
    if not u or not u["started_at"] or u["submitted"]: return False
    st=datetime.fromisoformat(u["started_at"]); _,e=times(); close=datetime.combine(st.date(),time.fromisoformat(e),tzinfo=TZ)
    return datetime.now(TZ)>=min(st+timedelta(hours=1),close)
def web_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="TESTNI BOSHLASH",web_app=WebAppInfo(url=WEBAPP))]])
def phone_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Telefon raqamingizni yuborish",request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)
def sub_kb():
    rows=[[InlineKeyboardButton(text=f"KANALGA OBUNA BO‘LISH {i+1}",url=(c if c.startswith("http") else "https://t.me/"+c.lstrip("@")))] for i,c in enumerate(sub_channels())]
    rows.append([InlineKeyboardButton(text="OBUNANI TEKSHIRISH",callback_data="check_sub")]); return InlineKeyboardMarkup(inline_keyboard=rows)
def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Test sozlamalari"),KeyboardButton(text="Ishtirokchilar")],[KeyboardButton(text="Savollar"),KeyboardButton(text="Statistika")],[KeyboardButton(text="Real-time monitor"),KeyboardButton(text="Bildirishnoma")],[KeyboardButton(text="Majburiy obuna"),KeyboardButton(text="PDF natijalar")],[KeyboardButton(text="Tariflar")]],resize_keyboard=True)
def settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Boshlanish vaqti",callback_data="set_start"),InlineKeyboardButton(text="Tugash vaqti",callback_data="set_end")],[InlineKeyboardButton(text="Kirish kodi",callback_data="set_code")],[InlineKeyboardButton(text="Testni OCHISH",callback_data="mode_open"),InlineKeyboardButton(text="Testni YOPISH",callback_data="mode_closed")],[InlineKeyboardButton(text="Avto rejim",callback_data="mode_auto"),InlineKeyboardButton(text="Test holati",callback_data="test_status")],[InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]])
def sub_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Majburiy obunani YOQISH",callback_data="sub_on"),InlineKeyboardButton(text="O‘CHIRISH",callback_data="sub_off")],[InlineKeyboardButton(text="Kanal qo‘shish",callback_data="sub_add"),InlineKeyboardButton(text="Kanalni o‘chirish",callback_data="sub_delete")],[InlineKeyboardButton(text="Kanalni tahrirlash",callback_data="sub_edit"),InlineKeyboardButton(text="Kanallar ro‘yxati",callback_data="sub_list")],[InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]])
def question_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Savolni tanlash",callback_data="q_pick"),InlineKeyboardButton(text="Yangi savol qo‘shish",callback_data="q_add")],[InlineKeyboardButton(text="Savol o‘chirish",callback_data="q_delete"),InlineKeyboardButton(text="Savollar sonini belgilash",callback_data="q_count")],[InlineKeyboardButton(text="Barcha savollar",callback_data="q_list"),InlineKeyboardButton(text="Format",callback_data="q_format")],[InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]])
def participants_kb(users):
    rows=[[InlineKeyboardButton(text=f"{(u['full_name'] or 'Ismsiz')[:25]} · {float(u['score'] or 0):.1f}",callback_data=f"adm_user_{u['telegram_id']}")] for u in users[:40]]
    rows.append([InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]); return InlineKeyboardMarkup(inline_keyboard=rows)
def question_picker(page=0):
    qs=active_questions(); part=qs[page*15:(page+1)*15]; rows=[]; row=[]
    for q in part:
        row.append(InlineKeyboardButton(text=str(q["id"]),callback_data=f"qsel_{q['id']}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    nav=[]
    if page: nav.append(InlineKeyboardButton(text="←",callback_data=f"qpage_{page-1}"))
    if (page+1)*15<len(qs): nav.append(InlineKeyboardButton(text="→",callback_data=f"qpage_{page+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="Orqaga",callback_data="admin_questions")]); return InlineKeyboardMarkup(inline_keyboard=rows)
async def subscribed(tid):
    if not sub_required() or not sub_channels(): return True
    for channel in sub_channels():
        try:
            m=await bot.get_chat_member(channel,tid)
            if m.status not in ("member","administrator","creator"): return False
        except Exception: return False
    return True
def normalize(v): return " ".join(str(v or "").strip().casefold().split())
def grade_for(score):
    s=float(score); return "A+" if s>=90 else "A" if s>=80 else "B" if s>=70 else "C" if s>=60 else "D" if s>=50 else "F"
def progress_text(u):
    try:return f"{len(json.loads(u['answers_json'] or '{}'))}/{len(active_questions())}"
    except:return "0/0"
def parse_question_payload(text,existing=None):
    p=[x.strip() for x in text.split("|")]
    if len(p)<3: raise ValueError("Format yetarli emas")
    qid=int(p[0]); question=p[1]; typ=p[2].lower()
    if typ in ("written","write","text","yozma"):
        return qid,question,[],p[3] if len(p)>3 else (existing["answer"] if existing else ""),"written",p[4] if len(p)>4 else (existing["group_id"] if existing else ""),p[5] if len(p)>5 else (existing["image_url"] if existing else "")
    if len(p)<7: raise ValueError("ID|savol|1|A|B|C|D")
    if typ in ("a","b","c","d"): typ=str("abcd".index(typ)+1)
    if typ not in ("1","2","3","4"): raise ValueError("To‘g‘ri variant 1–4")
    opts=p[3:7]
    if any(not x for x in opts): raise ValueError("4 ta variant kerak")
    return qid,question,opts,opts[int(typ)-1],"choice",p[7] if len(p)>7 else (existing["group_id"] if existing else ""),p[8] if len(p)>8 else (existing["image_url"] if existing else "")
async def discard_user(tid,reason="Test yopildi."):
    u=get_user(tid)
    if not u or u["submitted"]: return False
    update_user(tid,started_at=None,answers_json="{}",submitted=0,score=0,grade="",finished_at=None)
    try: await bot.send_message(tid,reason+" Yakunlanmagan urinish hisoblanmadi.")
    except Exception: pass
    return True
async def finalize_user(tid): return await discard_user(tid,"Test vaqti tugadi.")
def make_pdf(path):
    users=[u for u in all_registered_users() if u["started_at"] or u["submitted"]]
    styles=getSampleStyleSheet()
    rows=[["№","Ism Familiya","Kirilgan vaqt","Tugagan vaqt","Ball","Baho","Holat"]]
    def fmt_dt(value):
        if not value: return "—"
        try: return datetime.fromisoformat(str(value)).astimezone(TZ).strftime("%d.%m.%Y %H:%M")
        except Exception: return str(value)[:16]
    for i,u in enumerate(users,1):
        status="Yakunlangan" if u["submitted"] else ("Faol" if user_open(u) else "Yakunlanmagan")
        rows.append([str(i),u["full_name"] or "—",fmt_dt(u["started_at"]),fmt_dt(u["finished_at"]),f'{float(u["score"] or 0):.2f}',u["grade"] or "—",status])
    doc=SimpleDocTemplate(path,pagesize=landscape(A4),rightMargin=18,leftMargin=18,topMargin=24,bottomMargin=24)
    story=[Paragraph("NUR O‘QIW ORAYI — TEST NATIJALARI",styles["Title"]),Paragraph(f"Test vaqti: {times()[0]}–{times()[1]} · Testga kirganlar: {len(users)}",styles["Heading2"]),Spacer(1,10)]
    table=Table(rows,repeatRows=1,colWidths=[28,190,105,105,60,55,95])
    table.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),.5,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eeeeee")),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1),8.5),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE")
    ]))
    story.append(table)
    doc.build(story)

@dp.message(Command("start"))
async def start(m:Message):
    ensure_user(m.from_user.id)
    if m.from_user.id==ADMIN:
        update_user(ADMIN,state="admin"); await m.answer("NUR O‘QIW ORAYI\n\nAdmin boshqaruv paneli.",reply_markup=admin_kb()); return
    if u["code_ok"] and u["full_name"] and u["phone"]:
        update_user(m.from_user.id,state="ready")
        await m.answer("NUR O‘QIW ORAYI\n\nXush kelibsiz! Profil va tarif bo‘limlaridan foydalanishingiz mumkin.",reply_markup=user_menu())
        return
    if not await subscribed(m.from_user.id):
        update_user(m.from_user.id,state="subscribe",code_ok=0); await m.answer("NUR O‘QIW ORAYI — Milliy sertifikat boti.\n\nTestga kirishdan oldin majburiy kanallarga obuna bo‘ling.",reply_markup=sub_kb()); return
    update_user(m.from_user.id,state="name",code_ok=0); await m.answer("📝 Ro‘yxatdan o‘tish\n\n👤 Ism, Familiya kiriting:",reply_markup=ReplyKeyboardRemove())
@dp.message(Command("stars"))
async def stars(m:Message): await start(m)
@dp.callback_query(F.data=="check_sub")
async def check_sub(q:CallbackQuery):
    if await subscribed(q.from_user.id): update_user(q.from_user.id,state="name",code_ok=0); await q.message.answer("📝 Ro‘yxatdan o‘tish\n\n👤 Ism, Familiya kiriting:",reply_markup=ReplyKeyboardRemove())
    else: await q.message.answer("Barcha majburiy kanallarga obuna bo‘ling.")
    await q.answer()
@dp.message(F.contact)
async def contact(m:Message):
    u=ensure_user(m.from_user.id)
    if u["state"]!="phone": await m.answer("Avval ism, familiyangizni kiriting."); return
    if m.contact.user_id and m.contact.user_id!=m.from_user.id: await m.answer("O‘zingizning Telegram raqamingizni yuboring."); return
    phone=m.contact.phone_number; upsert_user(m.from_user.id,u["full_name"],phone); update_user(m.from_user.id,state="code",code_ok=0)
    await m.answer(f"✅ Xush kelibsiz!\n\n👤 {u['full_name'] or '—'}\n📱 {phone}\n\nTelegram akkauntingiz bog‘landi!\n\n🔐 Testga kirish kodini kiriting:",reply_markup=ReplyKeyboardRemove())

@dp.message()
async def text_handler(m:Message):
    if not m.text:return
    u=ensure_user(m.from_user.id); st=u["state"] or "code"; text=m.text.strip()
    if m.from_user.id==ADMIN:
        if text=="Tariflar":
            await m.answer("TARIFLAR BOSHQARUVI\n\nBarcha /start bosgan userlar:",reply_markup=admin_tariff_list()); return
        if text=="Test sozlamalari":
            s,e=times(); await m.answer(f"TEST SOZLAMALARI\n\nBoshlanish: {s}\nTugash: {e}\nKod: {code_value()}\nRejim: {test_mode()}",reply_markup=settings_kb()); return
        if text=="Ishtirokchilar":
            users=all_registered_users(); await m.answer(f"ISHTIROKCHILAR\n\nJami ro‘yxatdan o‘tgan: {len(users)}",reply_markup=participants_kb(users)); return
        if text=="Savollar": await m.answer(f"SAVOLLAR\n\nFaol: {len(active_questions())}",reply_markup=question_menu_kb()); return
        if text=="Statistika": await m.answer(await stats_text(),reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Yangilash",callback_data="admin_stats")],[InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]])); return
        if text=="Real-time monitor": await m.answer(await monitor_message(),reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Yangilash",callback_data="monitor_refresh")],[InlineKeyboardButton(text="Jonli 1 daqiqa",callback_data="monitor_live")],[InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]])); return
        if text=="Bildirishnoma": update_user(ADMIN,state="admin_broadcast"); await m.answer("Hammaga yuboriladigan xabarni yozing."); return
        if text=="Majburiy obuna": await m.answer(f"MAJBURIY OBUNA\n\nHolat: {'YOQILGAN' if sub_required() else 'O‘CHIRILGAN'}\nKanallar: {len(sub_channels())}",reply_markup=sub_admin_kb()); return
        if text=="PDF natijalar": path="/tmp/nur_results.pdf"; make_pdf(path); await bot.send_document(ADMIN,document=FSInputFile(path)); await m.answer("PDF yuborildi.",reply_markup=admin_kb()); return
        if st=="admin_start":
            try:time.fromisoformat(text)
            except:await m.answer("Vaqt HH:MM formatida bo‘lsin.");return
            set_setting("test_start",text);update_user(ADMIN,state="admin");await m.answer("Boshlanish vaqti saqlandi.",reply_markup=admin_kb());return
        if st=="admin_end":
            try:time.fromisoformat(text)
            except:await m.answer("Vaqt HH:MM formatida bo‘lsin.");return
            set_setting("test_end",text);update_user(ADMIN,state="admin");await m.answer("Tugash vaqti saqlandi.",reply_markup=admin_kb());return
        if st=="admin_code": set_setting("access_code",text);update_user(ADMIN,state="admin");await m.answer("Kod saqlandi.",reply_markup=admin_kb());return
        if st=="admin_broadcast":
            ok,total=await broadcast_notification(text)
            update_user(ADMIN,state="admin");await m.answer(f"Yuborildi: {ok}/{total}",reply_markup=admin_kb());return
        if st=="admin_qadd":
            try:q=parse_question_payload(text);upsert_question(q[0],q[1],q[2],q[3],q[4],q[5],q[6]);update_user(ADMIN,state="admin");await m.answer("Savol qo‘shildi.",reply_markup=admin_kb())
            except Exception as e:await m.answer(f"Xato: {e}")
            return
        if st.startswith("admin_qedit_"):
            try:q=parse_question_payload(text,get_question_any(int(st.rsplit("_",1)[1])));upsert_question(q[0],q[1],q[2],q[3],q[4],q[5],q[6]);update_user(ADMIN,state="admin");await m.answer("Savol yangilandi.",reply_markup=admin_kb())
            except Exception as e:await m.answer(f"Xato: {e}")
            return
        if st=="admin_qdelete":
            try:delete_question(int(text));update_user(ADMIN,state="admin");await m.answer("Savol o‘chirildi.",reply_markup=admin_kb())
            except:await m.answer("Savol raqamini kiriting.")
            return
        if st=="admin_qcount":
            try:set_active_question_count(int(text));update_user(ADMIN,state="admin");await m.answer(f"Faol savollar: {len(active_questions())}",reply_markup=admin_kb())
            except:await m.answer("Son kiriting.")
            return
        if st=="admin_sub_add":
            chans=sub_channels();
            if text not in chans:chans.append(text);set_setting("subscription_channels","\n".join(chans))
            update_user(ADMIN,state="admin");await m.answer("Kanal qo‘shildi.",reply_markup=admin_kb());return
        if st=="admin_sub_delete":
            try:i=int(text)-1;chans=sub_channels();del chans[i];set_setting("subscription_channels","\n".join(chans));update_user(ADMIN,state="admin");await m.answer("Kanal o‘chirildi.",reply_markup=admin_kb())
            except:await m.answer("Raqamni to‘g‘ri kiriting.")
            return
        if st=="admin_sub_edit":
            try:i,new=text.split("|",1);chans=sub_channels();chans[int(i)-1]=new.strip();set_setting("subscription_channels","\n".join(chans));update_user(ADMIN,state="admin");await m.answer("Kanal tahrirlandi.",reply_markup=admin_kb())
            except:await m.answer("Format: 1|@kanal_nomi")
            return
        if st.startswith("admin_"): return
    if st=="name":
        if len(text)<3:await m.answer("Ism va familiyangizni to‘liq kiriting.");return
        upsert_user(m.from_user.id,text);update_user(m.from_user.id,state="phone");await m.answer("📱 Telefon raqamingizni yuboring:",reply_markup=phone_kb());return
    if st=="code":
        if text!=code_value():await m.answer("❌ Kod noto‘g‘ri. Qayta kiriting:");return
        update_user(m.from_user.id,code_ok=1,state="ready");await m.answer("🎉 Ro‘yxatdan o‘tish tugadi!\n\nTestga kirishingiz mumkin.",reply_markup=web_kb());return
    if st=="ready": await m.answer("Testga kirish:",reply_markup=web_kb());return
    await m.answer("Testga kirish:",reply_markup=web_kb())

@dp.callback_query(F.data=="admin_home")
async def admin_home(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return await q.answer("Ruxsat yo‘q",show_alert=True)
    update_user(ADMIN,state="admin");await q.message.answer("Admin boshqaruv paneli.",reply_markup=admin_kb());await q.answer()
@dp.callback_query(F.data=="admin_stats")
async def admin_stats(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    await q.message.edit_text(await stats_text(),reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Yangilash",callback_data="admin_stats")],[InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]]));await q.answer()
@dp.callback_query(F.data=="monitor_refresh")
async def monitor_refresh(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    try:await q.message.edit_text(await monitor_message(),reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Yangilash",callback_data="monitor_refresh")],[InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]]))
    except Exception as e:
        if "not modified" not in str(e).lower():raise
    await q.answer()
async def monitor_live_loop(q):
    last=""
    for _ in range(12):
        body=await monitor_message()
        if body!=last:
            try:await q.message.edit_text(body,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Yangilash",callback_data="monitor_refresh")],[InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]]))
            except Exception:pass
            last=body
        await asyncio.sleep(5)
@dp.callback_query(F.data=="monitor_live")
async def monitor_live(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    await q.answer("Jonli monitoring boshlandi");await monitor_live_loop(q)
@dp.callback_query(F.data=="set_start")
async def cb_set_start(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    update_user(ADMIN,state="admin_start");await q.message.edit_text("Boshlanish vaqtini yozing. Masalan: 08:30");await q.answer()
@dp.callback_query(F.data=="set_end")
async def cb_set_end(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    update_user(ADMIN,state="admin_end");await q.message.edit_text("Tugash vaqtini yozing. Masalan: 09:30");await q.answer()
@dp.callback_query(F.data=="set_code")
async def cb_set_code(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    update_user(ADMIN,state="admin_code");await q.message.edit_text("Yangi kirish kodini yozing:");await q.answer()
@dp.callback_query(F.data=="mode_open")
async def cb_open(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    set_setting("test_mode","open");await q.message.edit_text("Test ochiq.",reply_markup=settings_kb());await q.answer()
@dp.callback_query(F.data=="mode_auto")
async def cb_auto(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    set_setting("test_mode","auto");await q.message.edit_text("Avto rejim yoqildi.",reply_markup=settings_kb());await q.answer()
@dp.callback_query(F.data=="mode_closed")
async def cb_closed(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    set_setting("test_mode","closed")
    for u in all_registered_users():
        if u["started_at"] and not u["submitted"]:await discard_user(u["telegram_id"],"Admin testni yopdi.")
    await q.message.edit_text("Test yopildi. Tugallanmagan urinishlar hisoblanmadi.",reply_markup=settings_kb());await q.answer()
@dp.callback_query(F.data=="test_status")
async def cb_status(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    s,e=times();await q.message.edit_text(f"TEST HOLATI\n\n{'OCHIQ' if open_now() else 'YOPIQ'}\nRejim: {test_mode()}\nVaqt: {s}–{e}\nFaol: {sum(user_open(u) for u in all_registered_users())}",reply_markup=settings_kb());await q.answer()
@dp.callback_query(F.data=="admin_questions")
async def admin_questions(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    await q.message.edit_text(f"SAVOLLAR\n\nFaol: {len(active_questions())}",reply_markup=question_menu_kb());await q.answer()
@dp.callback_query(F.data=="q_pick")
async def q_pick(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    await q.message.edit_text("Savolni tanlang:",reply_markup=question_picker());await q.answer()
@dp.callback_query(F.data.startswith("qpage_"))
async def q_page(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    await q.message.edit_reply_markup(reply_markup=question_picker(int(q.data.split("_")[1])));await q.answer()
@dp.callback_query(F.data.startswith("qsel_"))
async def qsel(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    qid=int(q.data.split("_")[1]);row=get_question(qid)
    if not row:return await q.answer("Topilmadi",show_alert=True)
    opts=json.loads(row["options_json"] or "[]");body=f"{qid}. {row['question']}\n"+("\n".join(f"{chr(65+i)}. {x}" for i,x in enumerate(opts)) if opts else "Yozma savol")+f"\nTo‘g‘ri: {row['answer']}";update_user(ADMIN,state=f"admin_qedit_{qid}")
    await q.message.edit_text(body+"\n\nYuboring:\nID|savol|1|A|B|C|D",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Orqaga",callback_data="admin_questions")]]));await q.answer()
@dp.callback_query(F.data=="q_add")
async def qadd(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    update_user(ADMIN,state="admin_qadd");await q.message.edit_text("Choice: ID|savol|1|A|B|C|D\nYozma: ID|savol|written|javob");await q.answer()
@dp.callback_query(F.data=="q_delete")
async def qdelete(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    update_user(ADMIN,state="admin_qdelete");await q.message.edit_text("Savol raqamini yozing.");await q.answer()
@dp.callback_query(F.data=="q_count")
async def qcount(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    update_user(ADMIN,state="admin_qcount");await q.message.edit_text(f"Hozir {len(active_questions())} ta. Yangi sonni yozing.");await q.answer()
@dp.callback_query(F.data=="q_list")
async def qlist(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    text="BARCHA SAVOLLAR\n\n"+"\n".join(f"{x['id']}. {x['question'][:100]}" for x in active_questions());await q.message.edit_text(text[:3900]);await q.answer()
@dp.callback_query(F.data=="q_format")
async def qformat(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    await q.message.edit_text("Variantli: ID|savol|1|A|B|C|D\nYozma: ID|savol|written|javob\nRasm: ID|savol|1|A|B|C|D|group|image_url");await q.answer()
@dp.callback_query(F.data=="sub_on")
async def sub_on(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    if not sub_channels():return await q.answer("Avval kanal qo‘shing.",show_alert=True)
    set_setting("subscription_enabled","1");await q.message.edit_text("Majburiy obuna YOQILDI.",reply_markup=sub_admin_kb());await q.answer()
@dp.callback_query(F.data=="sub_off")
async def sub_off(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    set_setting("subscription_enabled","0");await q.message.edit_text("Majburiy obuna O‘CHIRILDI.",reply_markup=sub_admin_kb());await q.answer()
@dp.callback_query(F.data=="sub_add")
async def sub_add(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    update_user(ADMIN,state="admin_sub_add");await q.message.edit_text("Kanal username yoki linkini yuboring.\nMasalan: @kanal_nomi");await q.answer()
@dp.callback_query(F.data=="sub_delete")
async def sub_delete(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    update_user(ADMIN,state="admin_sub_delete");chans=sub_channels();await q.message.edit_text("O‘chirish uchun raqam:\n\n"+"\n".join(f"{i}. {c}" for i,c in enumerate(chans,1)) if chans else "Kanal qo‘shilmagan.");await q.answer()
@dp.callback_query(F.data=="sub_edit")
async def sub_edit(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    update_user(ADMIN,state="admin_sub_edit");await q.message.edit_text("Format: 1|@yangi_kanal");await q.answer()
@dp.callback_query(F.data=="sub_list")
async def sub_list(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    chans=sub_channels();body=f"Holat: {'YOQILGAN' if sub_required() else 'O‘CHIRILGAN'}\n\n"+"\n".join(f"{i}. {c}" for i,c in enumerate(chans,1)) if chans else "Kanal qo‘shilmagan.";await q.message.edit_text(body,reply_markup=sub_admin_kb());await q.answer()
@dp.callback_query(F.data.startswith("adm_user_"))
async def adm_user(q:CallbackQuery):
    if q.from_user.id!=ADMIN:return
    tid=int(q.data.split("_")[-1]);u=get_user(tid)
    if not u:return
    await q.message.edit_text(f"ISHTIROKCHI\n\nIsm: {u['full_name'] or '—'}\nTelefon: {u['phone'] or '—'}\nID: {tid}\nBall: {float(u['score'] or 0):.2f}\nBaho: {u['grade'] or '—'}\nJavoblar: {progress_text(u)}\nHolat: {'Yakunlangan' if u['submitted'] else 'Faol' if user_open(u) else 'Kutmoqda'}",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]]));await q.answer()

async def monitor_message():
    users=all_registered_users();active=[u for u in users if user_open(u)];s,e=times();lines=["REAL-TIME MONITOR","",f"Test: {'OCHIQ' if open_now() else 'YOPIQ'} · {s}–{e}",f"Ro‘yxatdan o‘tgan: {len(users)} · Faol: {len(active)}",""]
    lines += [f"{i}. {u['full_name'] or '—'} · {progress_text(u)}" for i,u in enumerate(active[:40],1)]
    if not active:lines.append("Hozir faol qatnashchi yo‘q.")
    return "\n".join(lines)
async def stats_text():
    users=all_registered_users();fin=[u for u in users if u["submitted"]];act=[u for u in users if user_open(u)];avg=sum(float(u["score"] or 0) for u in fin)/len(fin) if fin else 0
    return f"STATISTIKA\n\nRo‘yxatdan o‘tgan: {len(users)}\nTestni yakunlagan: {len(fin)}\nFaol: {len(act)}\nO‘rtacha ball: {avg:.2f}"
def telegram_user(init_data):
    try:
        data=dict(parse_qsl(init_data or "",keep_blank_values=True));received=data.pop("hash",None);auth=int(data.get("auth_date","0"));user=json.loads(data.get("user","{}"));tid=int(user.get("id"));check="\n".join(k+"="+data[k] for k in sorted(data));secret=hmac.new(b"WebAppData",TOKEN.encode(),hashlib.sha256).digest();calc=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest();return tid if received and hmac.compare_digest(calc,received) and datetime.now(timezone.utc).timestamp()-auth<=86400 else None
    except Exception:return None
@app.middleware("http")
async def abuse_guard(request:Request,call_next):
    if request.url.path.startswith("/api/"):
        ip=request.client.host if request.client else "unknown";now=datetime.now(timezone.utc).timestamp();q=RATE_BUCKET[ip]
        while q and now-q[0]>RATE_WINDOW:q.popleft()
        if len(q)>=RATE_LIMIT:return JSONResponse({"ok":False,"error":"rate_limited"},status_code=429,headers={"Retry-After":"60"})
        q.append(now)
    return await call_next(request)
@app.get("/health")
def health():return {"ok":True,"test":times(),"mode":test_mode(),"questions":len(active_questions()),"subscription_enabled":sub_required()}
@app.get("/api/state")
async def api_state(request:Request):
    tid=telegram_user(request.query_params.get("initData",""));u=get_user(tid) if tid else None;s,e=times()
    if not u or not u["code_ok"]:return JSONResponse({"ok":False,"error":"not_authorized"},status_code=401)
    if u["submitted"]:return {"ok":False,"error":"already_submitted","score":u["score"],"grade":u["grade"],"full_name":u["full_name"] or ""}
    if not open_now() and not u["started_at"]:return {"ok":False,"error":"test_closed","test_open":False,"start":s,"end":e,"mode":test_mode()}
    if u["started_at"] and expired(u):await discard_user(tid);return {"ok":False,"error":"test_closed","test_open":False,"start":s,"end":e}
    if not u["started_at"]:update_user(tid,started_at=datetime.now(TZ).isoformat());u=get_user(tid)
    st=datetime.fromisoformat(u["started_at"]);close=datetime.combine(st.date(),time.fromisoformat(e),tzinfo=TZ);ends=min(st+timedelta(hours=1),close)
    return {"ok":True,"full_name":u["full_name"] or "","answers":json.loads(u["answers_json"] or "{}"),"ends_at":ends.isoformat(),"started_at":u["started_at"],"total_questions":len(active_questions()),"test_open":True,"start":s,"end":e,"mode":test_mode()}
@app.get("/api/questions")
def questions():return [{"id":q["id"],"question":q["question"],"options":json.loads(q["options_json"] or "[]"),"kind":q["kind"],"group_id":q["group_id"],"image_url":q["image_url"]} for q in active_questions()]
@app.post("/api/answer")
async def answer_api(p:dict):
    tid=telegram_user(p.get("initData",""));u=get_user(tid) if tid else None
    if not u or not u["code_ok"] or u["submitted"]:return {"ok":False,"error":"not_authorized"}
    if not open_now() or expired(u):await discard_user(tid);return {"ok":False,"error":"test_closed"}
    q=get_question(p.get("question_id"));
    if not q:return {"ok":False,"error":"question_not_found"}
    answers=json.loads(u["answers_json"] or "{}");key=str(q["id"])
    if key in answers:return {"ok":False,"error":"answer_locked","correct":normalize(answers[key])==normalize(q["answer"])}
    answers[key]=p.get("answer","");save_answers(tid,answers);return {"ok":True,"correct":normalize(answers[key])==normalize(q["answer"])}
@app.post("/api/submit")
async def submit_api(p:dict):
    tid=telegram_user(p.get("initData",""));u=get_user(tid) if tid else None
    if not u or not u["code_ok"]:return {"ok":False,"error":"not_authorized"}
    if u["submitted"]:return {"ok":False,"error":"already_submitted"}
    if not open_now() or expired(u):await discard_user(tid);return {"ok":False,"error":"test_closed"}
    answers=json.loads(u["answers_json"] or "{}");qs=active_questions();correct=sum(1 for q in qs if normalize(answers.get(str(q["id"]),""))==normalize(q["answer"]));score=round(correct/len(qs)*100,2) if qs else 0;grade=grade_for(score);update_user(tid,score=score,grade=grade,submitted=1,finished_at=datetime.now(TZ).isoformat());return {"ok":True,"score":score,"grade":grade,"full_name":u["full_name"] or ""}
@app.post("/api/admin/questions")
async def api_admin_questions(p:dict):
    if p.get("key")!=os.getenv("ADMIN_API_KEY",""):return JSONResponse({"ok":False},status_code=403)
    return {"ok":True,"questions":[dict(q) for q in all_questions()]}

@app.get("/",include_in_schema=False)
async def root():return {"ok":True,"service":"nur-oqiw","health":"/health"}
@app.get("/api/ping")
def ping():return {"ok":True}
async def cleanup_loop():
    while True:
        try:
            await asyncio.sleep(10)
            for u in all_registered_users():
                if u["started_at"] and not u["submitted"]:
                    if expired(u):
                        await finalize_user(u["telegram_id"])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("cleanup_loop: %s", e)

WEBHOOK_URL=os.getenv("WEBHOOK_URL","https://nur-oqiw.onrender.com/telegram/webhook")
WEBHOOK_SECRET=os.getenv("WEBHOOK_SECRET","nur_oqiw_webhook")

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    secret=request.headers.get("X-Telegram-Bot-Api-Secret-Token","")
    if WEBHOOK_SECRET and secret!=WEBHOOK_SECRET:
        return JSONResponse({"ok":False},status_code=403)
    try:
        data=await request.json()
        update=Update.model_validate(data)
        await dp.feed_update(bot,update)
        return {"ok":True}
    except Exception as e:
        logger.exception("Telegram webhook error: %s",e)
        return JSONResponse({"ok":False},status_code=500)

async def send_notification(tid,text):
    for attempt in range(3):
        try:
            await bot.send_message(tid,text)
            return True
        except Exception as e:
            logger.warning("Notification to %s failed (attempt %s): %s",tid,attempt+1,e)
            if attempt<2:
                await asyncio.sleep(1.5*(attempt+1))
    return False

async def broadcast_notification(text):
    users=all_registered_users()
    ok=0
    for u in users:
        if await send_notification(u["telegram_id"],text):
            ok+=1
        await asyncio.sleep(0.05)
    return ok,len(users)

async def main():
    logger.info("Bot starting — webhook mode")
    cleanup_task = asyncio.create_task(cleanup_loop())
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info"))
    server_task = asyncio.create_task(server.serve())
    try:
        await bot.set_webhook(
            WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=False,
            allowed_updates=dp.resolve_used_update_types(),
        )
        logger.info("Telegram webhook set: %s",WEBHOOK_URL)
        await server_task
    finally:
        if not server_task.done():
            server_task.cancel()
        if not cleanup_task.done():
            cleanup_task.cancel()
        await asyncio.gather(server_task,cleanup_task,return_exceptions=True)
        try:
            await bot.session.close()
        except Exception:
            pass

if __name__=="__main__":
    asyncio.run(main())
