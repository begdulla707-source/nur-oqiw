import os, re, json, asyncio
from datetime import datetime, timezone, time
from urllib.parse import quote
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, WebAppInfo
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from .db import *

ADMIN=int(os.getenv("ADMIN_CHAT_ID","8379731556"))
WEBAPP=os.getenv("WEBAPP_URL","https://nur-oqiw.onrender.com")

# The core module is already partially initialized when this file is imported.
# We use it only for the bot, FastAPI app and secure Telegram initData validator.
import sys
core=sys.modules.get("bot.main")


def user_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Profilim"),KeyboardButton(text="Tariflar")],
        [KeyboardButton(text="Testni boshlash"),KeyboardButton(text="Mening natijam")],
        [KeyboardButton(text="Userlar ro‘yxati"),KeyboardButton(text="Yordam")],
    ],resize_keyboard=True,is_persistent=True)

def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Tariflar haqida",callback_data="pf_tariffs")],[InlineKeyboardButton(text="Userlar ro‘yxati",callback_data="pf_users")]])

def tariff_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Default",callback_data="pf_default")],[InlineKeyboardButton(text="Premium 💠",callback_data="pf_premium")],[InlineKeyboardButton(text="Premium olish",callback_data="pf_buy")]])

def admin_tariff_list():
    rows=[]
    for i,u in enumerate(all_registered_users(),1):
        mark="💠 " if str(u["tier"] or "default")=="premium" else ""
        rows.append([InlineKeyboardButton(text=f"{i}. {mark}{(u['full_name'] or 'Ismsiz')[:22]} · {u['telegram_id']}",callback_data=f"tf_user:{u['telegram_id']}")])
    rows.append([InlineKeyboardButton(text="Yangilash",callback_data="tf_list")]);return InlineKeyboardMarkup(inline_keyboard=rows)

def profile_text(u):
    tier="Premium 💠" if str(u["tier"] or "default")=="premium" else "Default"
    t=get_test(u["test_id"]) if u["test_id"] else None
    a=get_attempt(t["test_id"],u["telegram_id"]) if t else None
    result_text=(f"{float(a['score'] or 0):.2f} · {a['grade'] or '—'}" if a and a["submitted"] else "Yakunlanmagan")
    return f"PROFILIM\n\nIsm-familiya: {u['full_name'] or '—'}\nTelefon: {u['phone'] or '—'}\nTelegram ID: {u['telegram_id']}\nTarif: {tier}\nTest: {t['name'] if t else 'Tanlanmagan'}\nKod: {t['code'] if t else '—'}\nNatija: {result_text}"

def tariff_text():
    return "TARIFLAR\n\nDEFAULT\n• Oddiy test qatnashchisi\n• Asosiy natija va profil\n\nPREMIUM 💠\n• Premium belgi\n• Kengaytirilgan statistika\n• Natijalarni ko‘rish\n\nPremium tarif uchun administratorga murojaat qiling."

def _mt_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Yangi test yaratish",callback_data="mt_new")],[InlineKeyboardButton(text="Testni tanlash",callback_data="mt_list")],[InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]])

def _test_list_kb():
    rows=[]
    for t in all_tests(): rows.append([InlineKeyboardButton(text=f"{t['name'][:25]} · {t['code']}",callback_data=f"mt_sel:{t['test_id']}")])
    rows.append([InlineKeyboardButton(text="Yangi test",callback_data="mt_new")]);rows.append([InlineKeyboardButton(text="Orqaga",callback_data="admin_home")]);return InlineKeyboardMarkup(inline_keyboard=rows)

def _test_kb(tid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Savollarni boshqarish",callback_data=f"mt_q:{tid}")],
        [InlineKeyboardButton(text="To‘g‘ri javoblar kaliti",callback_data=f"mt_key:{tid}")],
        [InlineKeyboardButton(text="Yangi savol qo‘shish",callback_data=f"mt_addq:{tid}")],
        [InlineKeyboardButton(text="Test havolasini olish",callback_data=f"mt_link:{tid}")],
        [InlineKeyboardButton(text="TESTNI OCHISH",callback_data=f"mt_open:{tid}"),InlineKeyboardButton(text="YOPISH",callback_data=f"mt_close:{tid}")],
        [InlineKeyboardButton(text="PDF natijalar",callback_data=f"mt_pdf:{tid}")],
        [InlineKeyboardButton(text="Orqaga",callback_data="mt_list")]
    ])

def _parse_q(text):
    p=[x.strip() for x in text.split("|")]
    if len(p)>=4 and p[2].lower() in ("written","write","yozma","text"):
        return int(p[0]),p[1],[],p[3],"written",p[4] if len(p)>4 else "",p[5] if len(p)>5 else ""
    if len(p)!=7: raise ValueError("Format: 1|Savol|3|A|B|C|D")
    n=int(p[0]);answer=p[2].lower();
    if answer in "abcd":answer=str("abcd".index(answer)+1)
    if answer not in ("1","2","3","4"):raise ValueError("To‘g‘ri variant 1–4 bo‘lishi kerak")
    opts=p[3:7]
    if any(not x for x in opts):raise ValueError("A B C D variantlarining hammasini kiriting")
    return n,p[1],opts,opts[int(answer)-1],"choice","",""

def _test_open(t):
    if not t or not t["active"]:return False
    if t["mode"]=="open":return True
    if t["mode"]=="closed":return False
    now=datetime.now(core.TZ).time() if core else datetime.now().time()
    return time.fromisoformat(t["start_time"])<=now<time.fromisoformat(t["end_time"])

def _test_expired(u,t):
    if not u or not u["started_at"] or u["submitted"]:return False
    tz=core.TZ if core else timezone.utc
    st=datetime.fromisoformat(u["started_at"]);close=datetime.combine(st.date(),time.fromisoformat(t["end_time"]),tzinfo=tz)
    return datetime.now(tz)>=close

def _test_pdf(tid,path):
    t=get_test(tid);rows=[["№","Ism Familiya","Telegram ID","Kirilgan vaqt","Tugagan vaqt","Ball","Baho","Holat"]]
    attempts=all_attempts_for_test(tid)
    for i,a in enumerate(attempts,1):
        rows.append([str(i),a["full_name"] or "—",str(a["telegram_id"]),str(a["started_at"] or "—")[:16],str(a["finished_at"] or "—")[:16],f'{float(a["score"] or 0):.2f}',a["grade"] or "—","Yakunlangan" if a["submitted"] else "Faol"])
    doc=SimpleDocTemplate(path,pagesize=landscape(A4),rightMargin=18,leftMargin=18,topMargin=24,bottomMargin=24)
    styles=getSampleStyleSheet()
    story=[Paragraph(f"NUR O‘QIW ORAYI — {t['name'] if t else 'TEST'}",styles["Title"]),Paragraph(f"Kod: {t['code'] if t else '—'} · Qatnashchilar: {len(attempts)}",styles["Heading2"]),Spacer(1,10)]
    table=Table(rows,repeatRows=1,colWidths=[24,155,85,100,100,55,50,75]);table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eeeeee")),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8.2)]));story.append(table);doc.build(story)

def _register_api():
    if not core:return
    app=core.app;bot=core.bot
    async def auth(request):
        init_data=request.query_params.get("initData","")
        tid=core.telegram_user(init_data);u=get_user(tid) if tid else None
        return tid,u
    @app.get("/api/test/state")
    async def mt_state(request):
        tid,u=await auth(request);code=request.query_params.get("code","").strip()
        t=get_test_by_code(code) if code else (get_test(u["test_id"]) if u and u["test_id"] else None)
        if not tid or not u:return {"ok":False,"error":"not_authorized"}
        if not t:return {"ok":False,"error":"test_not_found"}
        if code and (u["test_id"]!=t["test_id"]):
            update_user(tid,test_id=t["test_id"],code_ok=1,state="ready")
            u=get_user(tid)
        if not u["full_name"] or not u["phone"]:
            return {"ok":False,"error":"registration_required","test_name":t["name"],"test_code":t["code"]}
        a=ensure_attempt(t["test_id"],tid)
        if a["submitted"]:
            return {"ok":False,"error":"already_submitted","score":a["score"],"grade":a["grade"],"full_name":u["full_name"] or "","test_name":t["name"]}
        if not _test_open(t) and not a["started_at"]:
            return {"ok":False,"error":"test_closed","start":t["start_time"],"end":t["end_time"],"test_name":t["name"]}
        if a["started_at"] and _test_expired(a,t):
            update_attempt(a["attempt_id"],status="expired")
            return {"ok":False,"error":"test_closed","test_name":t["name"]}
        if not a["started_at"]:
            update_attempt(a["attempt_id"],started_at=datetime.now(core.TZ).isoformat(),status="active");a=ensure_attempt(t["test_id"],tid)
        answers=json.loads(a["answers_json"] or "{}")
        close=datetime.combine(datetime.fromisoformat(a["started_at"]).date(),time.fromisoformat(t["end_time"]),tzinfo=core.TZ)
        return {"ok":True,"full_name":u["full_name"] or "","answers":answers,"ends_at":close.isoformat(),"test_name":t["name"],"test_code":t["code"],"total_questions":len(questions_for_test(t["test_id"]))}

    @app.get("/api/test/questions")
    async def mt_questions(request):
        tid,u=await auth(request);code=request.query_params.get("code","").strip();t=get_test_by_code(code) if code else (get_test(u["test_id"]) if u and u["test_id"] else None)
        if not tid or not u or not t:return JSONResponse({"ok":False,"error":"not_authorized"},status_code=401)
        return {"ok":True,"questions":[{"id":q["number"],"question":q["question"],"options":json.loads(q["options_json"] or "[]"),"kind":q["kind"],"image_url":q["image_url"]} for q in questions_for_test(t["test_id"])]}

    @app.post("/api/test/answer")
    async def mt_answer(p:dict):
        tid=core.telegram_user(p.get("initData",""));u=get_user(tid) if tid else None
        t=get_test_by_code(p.get("code","")) if p.get("code") else (get_test(u["test_id"]) if u and u["test_id"] else None)
        if not tid or not u or not t:return {"ok":False,"error":"not_authorized"}
        a=ensure_attempt(t["test_id"],tid)
        if a["submitted"]:return {"ok":False,"error":"already_submitted"}
        if not _test_open(t) or _test_expired(a,t):return {"ok":False,"error":"test_closed"}
        q=get_question_for_test(t["test_id"],p.get("question_id"))
        if not q:return {"ok":False,"error":"question_not_found"}
        answers=json.loads(a["answers_json"] or "{}");key=str(q["number"])
        if key in answers:return {"ok":False,"error":"answer_locked","correct":normalize(answers[key])==normalize(q["answer"])}
        ans=str(p.get("answer","")).strip();answers[key]=ans;save_attempt_answers(a["attempt_id"],answers)
        return {"ok":True,"correct":normalize(ans)==normalize(q["answer"]),"number":q["number"]}

    @app.post("/api/test/finish")
    async def mt_finish(p:dict):
        tid=core.telegram_user(p.get("initData",""));u=get_user(tid) if tid else None
        t=get_test_by_code(p.get("code","")) if p.get("code") else (get_test(u["test_id"]) if u and u["test_id"] else None)
        if not tid or not u or not t:return {"ok":False,"error":"not_authorized"}
        a=ensure_attempt(t["test_id"],tid)
        if a["submitted"]:return {"ok":False,"error":"already_submitted","score":a["score"]}
        if not _test_open(t) or _test_expired(a,t):return {"ok":False,"error":"test_closed"}
        answers=json.loads(a["answers_json"] or "{}");qs=questions_for_test(t["test_id"])
        correct=sum(1 for q in qs if normalize(answers.get(str(q["number"]),""))==normalize(q["answer"]))
        score=round(correct/len(qs)*100,2) if qs else 0
        grade="A+" if score>=90 else "A" if score>=80 else "B" if score>=70 else "C" if score>=60 else "D" if score>=50 else "F"
        update_attempt(a["attempt_id"],score=score,grade=grade,submitted=1,status="submitted",finished_at=datetime.now(core.TZ).isoformat())
        return {"ok":True,"score":score,"grade":grade,"full_name":u["full_name"] or "","test_name":t["name"]}

_register_api()

def register(dp,bot,webapp_url):
    r=Router(name="profile_features")
    @r.message(F.text=="Profilim")
    async def profile(m:Message):
        u=get_user(m.from_user.id) or ensure_user(m.from_user.id)
        if not u["code_ok"]:await m.answer("Avval test kodini kiriting.");return
        await m.answer(profile_text(u),reply_markup=profile_kb())
    @r.message(F.text=="Tariflar")
    async def tariffs(m:Message):
        if m.from_user.id==ADMIN:await m.answer("TARIFLAR BOSHQARUVI",reply_markup=admin_tariff_list());return
        u=get_user(m.from_user.id) or ensure_user(m.from_user.id)
        await m.answer(tariff_text(),reply_markup=tariff_kb())
    @r.message(F.text=="Testni boshlash")
    async def test_start(m:Message):
        u=get_user(m.from_user.id) or ensure_user(m.from_user.id);t=get_test(u["test_id"]) if u["test_id"] else None
        if not u["code_ok"] or not t:await m.answer("Avval test kodini kiriting.");return
        await m.answer(f"{t['name']}\nKod: {t['code']}",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="TESTNI BOSHLASH",web_app=WebAppInfo(url=f"{webapp_url.rstrip('/')}/test?code={quote(t['code'])}"))]]))
    @r.message(F.text=="Mening natijam")
    async def result(m:Message):
        u=get_user(m.from_user.id) or ensure_user(m.from_user.id);t=get_test(u["test_id"]) if u["test_id"] else None;a=get_attempt(t["test_id"],m.from_user.id) if t else None
        await m.answer(f"NATIJAM\n\nTest: {t['name'] if t else '—'}\nBall: {float(a['score'] or 0):.2f}\nBaho: {a['grade'] or 'Hali yakunlanmagan'}" if a else "NATIJAM\n\nHali test tanlanmagan.")
    @r.message(F.text=="Userlar ro‘yxati")
    async def users(m:Message):
        people=all_registered_users();lines=["USERLAR RO‘YXATI","",f"Jami: {len(people)}",""]
        lines += [f"{i}. {'💠 ' if str(x['tier'] or 'default')=='premium' else ''}{x['full_name'] or 'Ismsiz'}" for i,x in enumerate(people,1)]
        await m.answer("\n".join(lines)[:4000])
    @r.message(F.text=="Yordam")
    async def help_(m:Message):
        await m.answer("YORDAM\n\nSavol yoki muammo bo‘lsa administratorga yozing.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ADMINISTRATORGA YOZISH",url=f"tg://user?id={ADMIN}")]]))
    @r.message(CommandStart(deep_link=True))
    async def deep_start(m:Message,command):
        code=(command.args or "").strip();t=get_test_by_code(code)
        if not t:raise SkipHandler()
        u=ensure_user(m.from_user.id);update_user(m.from_user.id,test_id=t["test_id"],state="ready")
        if not u["full_name"] or not u["phone"]:
            update_user(m.from_user.id,state="name",code_ok=0)
            await m.answer(f"{t['name']}\n\nIsm va Familiyangizni kiriting:")
            return
        await m.answer(f"{t['name']}\n\nTest kodi: {t['code']}\n\nTestga kirishingiz mumkin.",reply_markup=user_menu())
    @r.message(F.text)
    async def dynamic_text(m:Message):
        text=(m.text or "").strip();u=ensure_user(m.from_user.id)
        if m.from_user.id==ADMIN and text=="Test sozlamalari":
            await m.answer("TESTLAR BOSHQARUVI\n\nHar bir test alohida kod, vaqt, savollar va natijalarga ega.",reply_markup=_mt_kb());return
        if m.from_user.id==ADMIN and text=="Savollar":
            await m.answer("Qaysi test savollarini boshqaramiz?",reply_markup=_test_list_kb());return
        t=get_test_by_code(text)
        if t:
            if not u["full_name"] or not u["phone"]:
                update_user(m.from_user.id,test_id=t["test_id"],state="name",code_ok=0)
                await m.answer(f"{t['name']}\n\nAvval ism va familiyangizni kiriting:")
                return
            update_user(m.from_user.id,test_id=t["test_id"],code_ok=1,state="ready")
            ensure_attempt(t["test_id"],m.from_user.id)
            await m.answer(f"TEST TANLANDI\n\n{t['name']}\nKod: {t['code']}\n\nMini App orqali testni boshlang.",reply_markup=user_menu());return
        raise SkipHandler()
    @r.callback_query(F.data=="mt_new")
    async def mt_new(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return await q.answer("Ruxsat yo‘q",show_alert=True)
        update_user(ADMIN,state="mt_new");await q.message.edit_text("Yangi test yaratish\n\nFormat:\nNomi|KOD|08:30|09:30\n\nMasalan:\nMatematika 1|MATH01|09:00|10:00");await q.answer()
    @r.callback_query(F.data=="mt_list")
    async def mt_list(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return await q.answer("Ruxsat yo‘q",show_alert=True)
        await q.message.edit_text("TESTLAR RO‘YXATI",reply_markup=_test_list_kb());await q.answer()
    @r.callback_query(F.data.startswith("mt_sel:"))
    async def mt_sel(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(":",1)[1];t=get_test(tid)
        if not t:return await q.answer("Test topilmadi",show_alert=True)
        set_setting("admin_test_id",tid);body=f"{t['name']}\n\nKod: {t['code']}\nSavollar: {len(questions_for_test(tid))}\nVaqt: {t['start_time']}–{t['end_time']}\nRejim: {t['mode']}\nHolat: {'OCHIQ' if _test_open(t) else 'YOPIQ'}"
        await q.message.edit_text(body,reply_markup=_test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith("mt_addq:"))
    async def mt_addq(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(":",1)[1];set_setting("admin_test_id",tid);update_user(ADMIN,state=f"mt_addq:{tid}");await q.message.edit_text("Yangi savol\n\nChoice:\n1|Savol matni|3|A|B|C|D\n\nYozma:\n1|Savol matni|written|to‘g‘ri javob\n\n3 — to‘g‘ri variant (A=1 B=2 C=3 D=4).",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Orqaga",callback_data=f"mt_sel:{tid}")]]));await q.answer()
    @r.callback_query(F.data.startswith("mt_key:"))
    async def mt_key(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return await q.answer("Ruxsat yo‘q",show_alert=True)
        tid=q.data.split(":",1)[1]
        cq=q
        set_setting("admin_test_id",tid);update_user(ADMIN,state=f"mt_key:{tid}")
        await cq.message.edit_text("TO‘G‘RI JAVOBLAR KALITI\n\nFaqat javob kalitini kiriting.\nFormat: 1-A, 2-C, 3-B, 4-D\n\nBir nechta javobni vergul yoki yangi qatorda yozish mumkin.")
        await cq.answer()

    @r.callback_query(F.data.startswith("mt_q:"))
    async def mt_q(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(":",1)[1];set_setting("admin_test_id",tid);qs=questions_for_test(tid);body="SAVOLLAR\n\n"+"\n".join(f"{x['number']}. {x['question'][:80]} · To‘g‘ri: {x['answer']}" for x in qs) if qs else "Hali savol yo‘q."
        await q.message.edit_text(body[:3900],reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Yangi savol",callback_data=f"mt_addq:{tid}")],[InlineKeyboardButton(text="Orqaga",callback_data=f"mt_sel:{tid}")]]));await q.answer()
    @r.callback_query(F.data.startswith("mt_open:"))
    async def mt_open(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(":",1)[1];set_setting("admin_test_id",tid);set_test_active(tid,1)
        with conn() as c:c.execute("UPDATE tests SET mode='open' WHERE test_id=?",(tid,))
        await q.message.edit_text("Test OCHILDI.",reply_markup=_test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith("mt_close:"))
    async def mt_close(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(":",1)[1]
        with conn() as c:c.execute("UPDATE tests SET mode='closed' WHERE test_id=?",(tid,))
        await q.message.edit_text("Test YOPILDI. Yangi kirishlar bloklandi.",reply_markup=_test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith("mt_link:"))
    async def mt_link(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(":",1)[1];t=get_test(tid);me=await bot.get_me();link=f"https://t.me/{me.username}?start={quote(t['code'])}"
        await q.message.edit_text(f"{t['name']}\n\nTEST KODI: {t['code']}\n\nGuruhga tashlash uchun:\n{link}",reply_markup=_test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith("mt_pdf:"))
    async def mt_pdf(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(":",1)[1];path=f"/tmp/{tid}_results.pdf";_test_pdf(tid,path)
        from aiogram.types import FSInputFile
        await bot.send_document(ADMIN,FSInputFile(path),caption=f"{get_test(tid)['name']} — natijalar");await q.answer("PDF yuborildi")
    @r.callback_query(F.data=="admin_home")
    async def admin_home2(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        update_user(ADMIN,state="admin");await q.message.answer("Admin boshqaruv paneli.");await q.answer()
    @r.message(F.text)
    async def admin_state_text(m:Message):
        if m.from_user.id!=ADMIN:raise SkipHandler()
        u=ensure_user(ADMIN);st=u["state"] or ""
        if st=="mt_new":
            try:
                name,code,start,end=[x.strip() for x in m.text.split("|",3)]
                if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}",code):raise ValueError("Kod faqat A-Z, 0-9, _ yoki - bo‘lsin")
                time.fromisoformat(start);time.fromisoformat(end)
                if get_test_by_code(code):raise ValueError("Bu kod allaqachon mavjud")
                t=create_test(name,code,start,end,"auto");update_user(ADMIN,state="admin");set_setting("admin_test_id",t["test_id"])
                await m.answer(f"TEST YARATILDI\n\n{t['name']}\nKod: {t['code']}\nSavollar: 0",reply_markup=_test_kb(t["test_id"]))
            except Exception as e:await m.answer(f"Xato: {e}")
            return
        if st.startswith("mt_key:"):
            tid=st.split(":",1)[1]
            try:
                pairs=[x.strip() for x in re.split(r"[,;\n]+",m.text) if x.strip()]
                changed=0
                for pair in pairs:
                    mm=re.fullmatch(r"(\d+)\s*[-:]\s*([ABCDabcd])",pair)
                    if not mm:raise ValueError(f"Noto‘g‘ri format: {pair}")
                    num=int(mm.group(1));letter=mm.group(2).upper();q=get_question_for_test(tid,num)
                    if not q:raise ValueError(f"{num}-savol topilmadi")
                    opts=json.loads(q["options_json"] or "[]")
                    if len(opts)!=4:raise ValueError(f"{num}-savol 4 variantli emas")
                    answer=opts[ord(letter)-65]
                    upsert_test_question(tid,num,q["question"],opts,answer,q["kind"],q["group_id"],q["image_url"])
                    changed+=1
                update_user(ADMIN,state="admin")
                await m.answer(f"{changed} ta to‘g‘ri javob saqlandi.",reply_markup=_test_kb(tid))
            except Exception as e:await m.answer(f"Xato: {e}")
            return
        if st.startswith("mt_addq:"):
            tid=st.split(":",1)[1]
            try:
                n,question,opts,answer,kind,group_id,image_url=_parse_q(m.text);upsert_test_question(tid,n,question,opts,answer,kind,group_id,image_url);update_user(ADMIN,state="admin");await m.answer(f"{n}-savol saqlandi.\nTo‘g‘ri javob: {answer}",reply_markup=_test_kb(tid))
            except Exception as e:await m.answer(f"Xato: {e}")
            return
        raise SkipHandler()
    @r.callback_query(F.data=="pf_tariffs")
    async def pf_tariffs(q:CallbackQuery):await q.message.answer(tariff_text(),reply_markup=tariff_kb());await q.answer()
    @r.callback_query(F.data=="pf_users")
    async def pf_users(q:CallbackQuery):await q.message.answer("USERLAR RO‘YXATI\n\n"+"\n".join(f"{i}. {u['full_name'] or 'Ismsiz'}" for i,u in enumerate(all_registered_users(),1))[:4000]);await q.answer()
    @r.callback_query(F.data=="pf_default")
    async def pf_default(q:CallbackQuery):await q.answer("Default — oddiy user tarifi.",show_alert=True)
    @r.callback_query(F.data=="pf_premium")
    async def pf_premium(q:CallbackQuery):await q.answer("Premium 💠 — kengaytirilgan imkoniyatlar.",show_alert=True)
    @r.callback_query(F.data=="pf_buy")
    async def pf_buy(q:CallbackQuery):await q.message.answer("Premium 💠 tarifini olish uchun administratorga yozing.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ADMINISTRATORGA YOZISH",url=f"tg://user?id={ADMIN}")]]));await q.answer()
    @r.callback_query(F.data=="tf_list")
    async def tf_list(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return await q.answer("Ruxsat yo‘q",show_alert=True)
        await q.message.edit_text("TARIFLAR BOSHQARUVI",reply_markup=admin_tariff_list());await q.answer()
    @r.callback_query(F.data.startswith("tf_user:"))
    async def tf_user(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return await q.answer("Ruxsat yo‘q",show_alert=True)
        uid=int(q.data.split(":",1)[1]);u=get_user(uid)
        if not u:return await q.answer("User topilmadi",show_alert=True)
        label="Premium 💠" if str(u["tier"] or "default")=="premium" else "Default";kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Premium 💠 berish",callback_data=f"tf_set:premium:{uid}")],[InlineKeyboardButton(text="Default qilish",callback_data=f"tf_set:default:{uid}")],[InlineKeyboardButton(text="Orqaga",callback_data="tf_list")]])
        await q.message.edit_text(f"USER TARIFI\n\nIsm: {u['full_name'] or '—'}\nID: {uid}\nHozirgi tarif: {label}",reply_markup=kb);await q.answer()
    @r.callback_query(F.data.startswith("tf_set:"))
    async def tf_set(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        _,tier,uid_s=q.data.split(":");uid=int(uid_s);label="Premium 💠" if tier=="premium" else "Default";set_tier(uid,tier,ADMIN)
        try:await bot.send_message(uid,f"Tarifingiz yangilandi: {label}.")
        except Exception:pass
        await q.message.edit_text(f"SAQLANDI\n\nID: {uid}\nTarif: {label}",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Tariflar ro‘yxati",callback_data="tf_list")]]));await q.answer()
    dp.include_router(r)
