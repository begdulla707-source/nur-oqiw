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
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Test sozlamalari"),KeyboardButton(text="Ishtirokchilar")],[KeyboardButton(text="Savollar"),KeyboardButton(text="Statistika")],[KeyboardButton(text="Real-time monitor"),KeyboardButton(text="Bildirishnoma")],[KeyboardButton(text="Majburiy obuna"),KeyboardButton(text="PDF natijalar")]],resize_keyboard=True)
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
    styles=getSampleStyleSheet(); users=[u for u in all_registered_users() if u["submitted"]]
    rows=[["№","Ism Familiya","Ball","Baho"]]+[[str(i),u["full_name"] or "—",f"{float(u['score'] or 0):.2f}",u["grade"] or "—"] for i,u in enumerate(users,1)]
    doc=SimpleDocTemplate(path,pagesize=landscape(A4),rightMargin=24,leftMargin=24,topMargin=24,bottomMargin=24); story=[Paragraph("NUR O‘QIW ORAYI — TEST NATIJALARI",styles["Title"]),Paragraph(f"Ishtirokchilar: {len(users)}",styles["Heading2"]),Spacer(1,10)]
    table=Table(rows,repeatRows=1,colWidths=[35,430,80,70]); table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eeeeee")),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold")])); story.append(table); doc.build(story)

@dp.message(Command("start"))
async def start(m:Message):
    ensure_user(m.from_user.id)
    if m.from_user.id==ADMIN:
        update_user(ADMIN,state="admin"); await m.answer("NUR O‘QIW ORAYI\n\nAdmin boshqaruv paneli.",reply_markup=admin_kb()); return
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
            except ValueError:await m.answer("Masalan: 08:30");return
            set_setting("test_start",text);update_user(ADMIN,state="admin");await m.answer("Boshlanish saqlandi.",reply_markup=admin_kb());return
        if st=="admin_end":
            try:time.fromisoformat(text)
            except ValueError:await m.answer("Masalan: 09:30");return
            set_setting("test_end",text);update_user(ADMIN,state="admin");await m.answer("Tugash saqlandi.",reply_markup=admin_kb());return
        if st=="admin_code": set_setting("access_code",text);update_user(ADMIN,state="admin");await m.answer("Kod saqlandi.",reply_markup=admin_kb());return
        if st=="admin_broadcast":
            sent=failed=0
            for usr in all_registered_users():
                try:await bot.send_message(usr["telegram_id"],text);sent+=1;await asyncio.sleep(.035)
                except Exception:failed+=1
            update_user(ADMIN,state="admin");await m.answer(f"Bildirishnoma tugadi.\nYuborildi: {sent}\nXato: {failed}",reply_markup=admin_kb());return
        if st=="admin_sub_add":
            ch=text; chans=sub_channels()
            if ch not in chans:chans.append(ch)
            set_setting("subscription_channels","\n".join(chans));update_user(ADMIN,state="admin");await m.answer(f"Kanal qo‘shildi: {ch}",reply_markup=admin_kb());return
        if st=="admin_sub_delete":
            chans=sub_channels()
            try:idx=int(text)-1;removed=chans.pop(idx)
            except Exception:await m.answer("Kanal raqamini yozing.");return
            set_setting("subscription_channels","\n".join(chans));update_user(ADMIN,state="admin");await m.answer(f"O‘chirildi: {removed}",reply_markup=admin_kb());return
        if st=="admin_sub_edit":
            try:n,new=text.split("|",1);idx=int(n)-1;chans=sub_channels();chans[idx]=new.strip();set_setting("subscription_channels","\n".join(chans))
            except Exception:await m.answer("Format: 1|@yangi_kanal");return
            update_user(ADMIN,state="admin");await m.answer("Kanal tahrirlandi.",reply_markup=admin_kb());return
        if st.startswith("admin_qedit_"):
            try:old=int(st.rsplit("_",1)[1]);vals=parse_question_payload(text,get_question(old));upsert_question(*vals);update_user(ADMIN,state="admin");await m.answer(f"Savol {vals[0]} yangilandi.",reply_markup=admin_kb())
            except Exception as e:await m.answer(f"Xato: {e}")
            return
        if st=="admin_qadd":
            try:vals=parse_question_payload(text);upsert_question(*vals);update_user(ADMIN,state="admin");await m.answer(f"Savol {vals[0]} saqlandi.",reply_markup=admin_kb())
            except Exception as e:await m.answer(f"Xato: {e}")
            return
        if st=="admin_qdelete":
            try:qid=int(text);ok=delete_question(qid)
            except:ok=False
            if ok:update_user(ADMIN,state="admin")
            await m.answer("O‘chirildi." if ok else "Savol topilmadi.",reply_markup=admin_kb());return
        if st=="admin_qcount":
            try:n=int(text);assert 1<=n<=100;set_active_question_count(n);update_user(ADMIN,state="admin");await m.answer(f"{n} ta faol savol.",reply_markup=admin_kb())
            except:await m.answer("1–100 oralig‘ida son.")
            return
        if text.lower() in ("orqaga","back"):update_user(ADMIN,state="admin");await m.answer("Admin boshqaruv paneli.",reply_markup=admin_kb());return
    if st=="code":
        if text!=code_value():await m.answer("Kirish kodi noto‘g‘ri.");return
        if not open_now():s,e=times();await m.answer(f"Kod qabul qilindi, lekin test hozir yopiq.\n\nTest vaqti: {s}–{e}.");return
        if not await subscribed(m.from_user.id):update_user(m.from_user.id,state="subscribe",code_ok=1);await m.answer("Avval majburiy kanallarga obuna bo‘ling.",reply_markup=sub_kb());return
        u=get_user(m.from_user.id)
        if not u or not u["full_name"] or not u["phone"]:update_user(m.from_user.id,state="name",code_ok=0);await m.answer("Avval ism, familiya va telefon raqamingizni kiriting.");return
        update_user(m.from_user.id,state="ready",code_ok=1);await m.answer("Kod qabul qilindi. Test ochiq — kirishingiz mumkin.",reply_markup=web_kb())
        return
    if st=="subscribe":await m.answer("Barcha majburiy kanallarga obuna bo‘ling va tekshirish tugmasini bosing.",reply_markup=sub_kb());return
    if st=="name":
        if len(text)<3:await m.answer("Ism va familiyangizni to‘liqroq kiriting.");return
        upsert_user(m.from_user.id,text);update_user(m.from_user.id,state="phone");await m.answer("QABUL QILINDI\n\n📱 Telefon raqamingizni kiriting:\n\nFormat: +998901234567\nMisol: +998901234567",reply_markup=phone_kb());return
    if st=="phone":
        if not re.fullmatch(r"\+998\d{9}",text):await m.answer("Format: +998901234567",reply_markup=phone_kb());return
        upsert_user(m.from_user.id,u["full_name"],text);update_user(m.from_user.id,state="code",code_ok=0);await m.answer(f"✅ Xush kelibsiz!\n\n👤 {u['full_name'] or '—'}\n📱 {text}\n\nTelegram akkauntingiz bog‘landi!\n\n🔐 Testga kirish kodini kiriting:",reply_markup=ReplyKeyboardRemove());return
    if st=="ready":
        if open_now():await m.answer("Test ochiq — kirishingiz mumkin.",reply_markup=web_kb())
        else:s,e=times();await m.answer(f"Test hozir yopiq.\n\nTest vaqti: {s}–{e}.")

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
