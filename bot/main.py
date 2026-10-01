import os, asyncio, json, hmac, hashlib
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import parse_qsl
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
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
TOKEN=os.getenv('BOT_TOKEN',''); WEBAPP=os.getenv('WEBAPP_URL','https://nukuspro.uz')
ADMIN=int(os.getenv('ADMIN_CHAT_ID','8379731556')); TZ=ZoneInfo(os.getenv('TIMEZONE','Asia/Tashkent'))
PORT=int(os.getenv('PORT','10000')); SUB_REQUIRED=os.getenv('FORCE_SUB_REQUIRED','1').lower() in ('1','true','yes')
SUB_CHANNEL=get_setting('subscription_channel',os.getenv('FORCE_SUB_CHANNEL','@Rustambek_oqiw_orayi'))
SUB_URL=os.getenv('FORCE_SUB_URL','https://t.me/Rustambek_oqiw_orayi')
dp=Dispatcher(); bot=Bot(TOKEN); app=FastAPI()
app.add_middleware(CORSMiddleware,allow_origins=['https://nukuspro.uz','https://www.nukuspro.uz'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

def times(): return get_setting('test_start',os.getenv('TEST_START','08:30')),get_setting('test_end',os.getenv('TEST_END','09:30'))
def code_value(): return get_setting('access_code',os.getenv('ACCESS_CODE','0924'))
def open_now():
    s,e=times(); n=datetime.now(TZ).time(); return time.fromisoformat(s)<=n<time.fromisoformat(e)
def user_open(u):
    if not u or not u['started_at'] or u['submitted']: return False
    st=datetime.fromisoformat(u['started_at']); now=datetime.now(TZ); _,e=times()
    close=datetime.combine(st.date(),time.fromisoformat(e),tzinfo=TZ)
    return now<min(st+timedelta(hours=1),close)
def web(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',web_app=WebAppInfo(url=WEBAPP))]])
def phone_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Telefon raqamingizni yuborish',request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)
def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Test sozlamalari'),KeyboardButton(text='Ishtirokchilar')],[KeyboardButton(text='Savollar'),KeyboardButton(text='Bildirishnoma')],[KeyboardButton(text='Majburiy obuna'),KeyboardButton(text='PDF natijalar')]],resize_keyboard=True)
def settings_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Boshlanish vaqti'),KeyboardButton(text='Tugash vaqti')],[KeyboardButton(text='Kirish kodi'),KeyboardButton(text='Orqaga')]],resize_keyboard=True)
def sub_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='KANALGA OBUNA BO‘LISH',url=SUB_URL)],[InlineKeyboardButton(text='OBUNANI TEKSHIRISH',callback_data='check_sub')]])
async def subscribed(tid):
    if not SUB_REQUIRED:return True
    try:
        m=await bot.get_chat_member(SUB_CHANNEL,tid); return m.status in ('member','administrator','creator')
    except Exception:return False

@dp.message(Command('start'))
async def start(m:Message):
    ensure_user(m.from_user.id)
    if m.from_user.id==ADMIN:
        await m.answer('NUR O‘QIW ORAYI\n\nAdmin boshqaruv paneli.',reply_markup=admin_kb()); return
    update_user(m.from_user.id,state='code',code_ok=0)
    await m.answer('NUR O‘QIW ORAYI — Milliy sertifikat boti.\n\nTestga kirish kodini kiriting:')

@dp.message(Command('stars'))
async def stars(m:Message):
    ensure_user(m.from_user.id); update_user(m.from_user.id,state='code',code_ok=0)
    await m.answer('NUR O‘QIW ORAYI — Milliy sertifikat boti.\n\nTestga kirish kodini kiriting:')

@dp.callback_query(F.data=='check_sub')
async def check_sub(q):
    if await subscribed(q.from_user.id):
        update_user(q.from_user.id,state='name',code_ok=1)
        await q.message.answer('📝 Ro‘yxatdan o‘tish\n\n👤 Ism, Familiya kiriting:')
    else: await q.message.answer('Kanalga obuna topilmadi. Avval obuna bo‘ling.')
    await q.answer()

@dp.message(F.contact)
async def contact(m:Message):
    u=ensure_user(m.from_user.id)
    if u['state']!='phone': await m.answer('Avval ism, familiyangizni kiriting.'); return
    upsert_user(m.from_user.id,u['full_name'],m.contact.phone_number); update_user(m.from_user.id,state='ready')
    await m.answer('✅ Xush kelibsiz!\n\n👤 '+u['full_name']+'\n📱 '+m.contact.phone_number+'\n\nTelegram akkauntingiz bog‘landi!\n\n🧮 Endi siz test yecha olasiz!',reply_markup=web())

@dp.message()
async def text(m:Message):
    if not m.text:return
    u=ensure_user(m.from_user.id); st=u['state'] or 'code'; text=m.text.strip()
    if m.from_user.id==ADMIN:
        if st=='admin_start':
            try: time.fromisoformat(text)
            except ValueError: await m.answer('Masalan: 08:30'); return
            set_setting('test_start',text); update_user(ADMIN,state='admin'); await m.answer('Boshlanish vaqti saqlandi.',reply_markup=admin_kb()); return
        if st=='admin_end':
            try: time.fromisoformat(text)
            except ValueError: await m.answer('Masalan: 09:30'); return
            set_setting('test_end',text); update_user(ADMIN,state='admin'); await m.answer('Tugash vaqti saqlandi.',reply_markup=admin_kb()); return
        if st=='admin_code':
            set_setting('access_code',text); update_user(ADMIN,state='admin'); await m.answer('Kirish kodi saqlandi.',reply_markup=admin_kb()); return
        if st=='admin_broadcast':
            sent=0
            for x in all_users():
                try: await bot.send_message(x['telegram_id'],text); sent+=1
                except Exception: pass
            update_user(ADMIN,state='admin'); await m.answer(f'Bildirishnoma yuborildi: {sent} ta.',reply_markup=admin_kb()); return
        if st=='admin_sub':
            set_setting('subscription_channel',text if text.startswith('@') else '@'+text); update_user(ADMIN,state='admin'); await m.answer('Majburiy obuna kanali saqlandi.',reply_markup=admin_kb()); return
        if st=='admin':
            if text=='Test sozlamalari':
                s,e=times(); await m.answer(f'Boshlanish: {s}\nTugash: {e}\nKod: {code_value()}',reply_markup=settings_kb()); return
            if text=='Boshlanish vaqti': update_user(ADMIN,state='admin_start'); await m.answer('Boshlanish vaqtini yozing: 08:30'); return
            if text=='Tugash vaqti': update_user(ADMIN,state='admin_end'); await m.answer('Tugash vaqtini yozing: 09:30'); return
            if text=='Kirish kodi': update_user(ADMIN,state='admin_code'); await m.answer('Yangi kirish kodini yozing.'); return
            if text=='Orqaga': await m.answer('Admin panel',reply_markup=admin_kb()); return
            if text=='Ishtirokchilar':
                users=all_users(); lines=[f'{i}. {x["full_name"] or "—"} — {x["score"]:.2f} — {x["grade"] or "—"}' for i,x in enumerate(users[:100],1)]
                await m.answer('Ishtirokchilar\n\n'+('\n'.join(lines) if lines else 'Hozircha yo‘q.'),reply_markup=admin_kb()); return
            if text=='Savollar': await m.answer('45 ta savol tizimda. Savollarni admin paneldagi JSON orqali yangilash mumkin.',reply_markup=admin_kb()); return
            if text=='Bildirishnoma': update_user(ADMIN,state='admin_broadcast'); await m.answer('Hammaga yuboriladigan xabarni yozing.'); return
            if text=='Majburiy obuna': update_user(ADMIN,state='admin_sub'); await m.answer(f'Kanal: {get_setting("subscription_channel",SUB_CHANNEL)}\nYangi @username yozing:'); return
            if text=='PDF natijalar':
                path='/tmp/nur_results.pdf'; await make_pdf(path); await bot.send_document(ADMIN,document=path); await m.answer('PDF admin chatiga yuborildi.',reply_markup=admin_kb()); return
        # first admin message after restart
        if text not in ('/start','/stars'): update_user(ADMIN,state='admin')
    if st=='code':
        if text!=code_value(): await m.answer('Kirish kodi noto‘g‘ri. Qaytadan kiriting.'); return
        if not open_now():
            s,e=times(); await m.answer(f'Kodingiz to‘g‘ri, lekin test hozircha ochilmagan.\n\nTest vaqti: {s}–{e}.'); return
        if not await subscribed(m.from_user.id):
            update_user(m.from_user.id,state='subscribe',code_ok=1); await m.answer('Testga kirish uchun kanalga obuna bo‘ling.',reply_markup=sub_kb()); return
        update_user(m.from_user.id,state='name',code_ok=1); await m.answer('📝 Ro‘yxatdan o‘tish\n\n👤 Ism, Familiya kiriting:'); return
    if st=='subscribe': await m.answer('Avval kanalga obuna bo‘ling va tekshirish tugmasini bosing.',reply_markup=sub_kb()); return
    if st=='name':
        upsert_user(m.from_user.id,text); update_user(m.from_user.id,state='phone')
        await m.answer('QABUL QILINDI\n\n📱 Telefon raqamingizni kiriting:\n\nFormat: +998901234567\nMisol: +998901234567'); return
    if st=='phone':
        if text.startswith('+998') and len(text)==13 and text[1:].isdigit():
            upsert_user(m.from_user.id,u['full_name'],text); update_user(m.from_user.id,state='ready'); await m.answer('✅ Xush kelibsiz!\n\n👤 '+u['full_name']+'\n📱 '+text+'\n\nTelegram akkauntingiz bog‘landi!\n\n🧮 Endi siz test yecha olasiz!',reply_markup=web())
        else: await m.answer('Telefon raqami noto‘g‘ri. Format: +998901234567')
        return
    if st=='ready': await m.answer('Testni boshlash uchun tugmani bosing.',reply_markup=web())

def telegram_user(init_data):
    try:
        data=dict(parse_qsl(init_data or '',keep_blank_values=True)); received=data.pop('hash',None); user=json.loads(data.get('user','{}')); tid=int(user.get('id')); auth=int(data.get('auth_date','0'))
        check='\n'.join(k+'='+data[k] for k in sorted(data)); secret=hmac.new(b'WebAppData',TOKEN.encode(),hashlib.sha256).digest(); calc=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if not received or not hmac.compare_digest(calc,received) or datetime.now(timezone.utc).timestamp()-auth>86400:return None
        return tid
    except Exception:return None

async def finalize_user(tid):
    u=get_user(tid)
    if not u or not u['started_at'] or u['submitted']:return False
    answers=json.loads(u['answers_json'] or '{}'); record_stats(answers); score=weighted_score(answers); grade=grade_for(score); finish_user(tid,score,grade,datetime.now(TZ).isoformat(),answers)
    try: await bot.send_message(tid,f'Test yakunlandi.\n\nBall: {score:.2f}\nBaho: {grade}')
    except Exception: pass
    return True

def expired(u):
    if not u or not u['started_at'] or u['submitted']:return False
    st=datetime.fromisoformat(u['started_at']); _,e=times(); close=datetime.combine(st.date(),time.fromisoformat(e),tzinfo=TZ)
    return datetime.now(TZ)>=min(st+timedelta(hours=1),close)

@app.get('/health')
def health(): return {'ok':True,'test':times(),'channel':get_setting('subscription_channel',SUB_CHANNEL)}
@app.get('/api/state')
async def api_state(request:Request):
    tid=telegram_user(request.query_params.get('initData','')); u=get_user(tid) if tid else None
    if not u or not u['code_ok'] or not u['started_at']:return JSONResponse({'ok':False,'error':'not_authorized'},status_code=401)
    if u['submitted']:return {'ok':False,'error':'already_submitted','score':u['score'],'grade':u['grade']}
    if not user_open(u): await finalize_user(tid); return {'ok':False,'error':'test_closed'}
    st=datetime.fromisoformat(u['started_at']); _,e=times(); close=datetime.combine(st.date(),time.fromisoformat(e),tzinfo=TZ); ends=min(st+timedelta(hours=1),close)
    return {'ok':True,'answers':json.loads(u['answers_json'] or '{}'),'started_at':st.isoformat(),'ends_at':ends.isoformat()}
@app.get('/api/questions')
def questions(): return [{'id':q['id'],'question':q['question'],'options':json.loads(q['options_json'] or '[]'),'kind':q['kind']} for q in active_questions()]
@app.post('/api/answer')
async def answer_api(p:dict):
    tid=telegram_user(p.get('initData','')); u=get_user(tid) if tid else None
    if not u or not u['code_ok'] or u['submitted']:return JSONResponse({'ok':False,'error':'not_authorized'},status_code=401)
    if not user_open(u): await finalize_user(tid); return {'ok':False,'error':'test_closed'}
    q=get_question(p.get('question_id')); 
    if not q:return {'ok':False,'error':'question_not_found'}
    answers=json.loads(u['answers_json'] or '{}'); key=str(q['id'])
    if key in answers:return {'ok':False,'error':'answer_locked','correct':normalize(answers[key])==normalize(q['answer'])}
    value=str(p.get('answer','')).strip(); answers[key]=value; save_answers(tid,answers)
    return {'ok':True,'locked':True,'correct':bool(q['answer']) and normalize(value)==normalize(q['answer'])}
@app.post('/api/finish')
async def finish_api(p:dict):
    tid=telegram_user(p.get('initData','')); u=get_user(tid) if tid else None
    if not u or not u['code_ok']:return {'ok':False,'error':'not_authorized'}
    if u['submitted']:return {'ok':True,'score':u['score'],'grade':u['grade']}
    answers=json.loads(u['answers_json'] or '{}'); record_stats(answers); score=weighted_score(answers); grade=grade_for(score); finish_user(tid,score,grade,datetime.now(TZ).isoformat(),answers)
    return {'ok':True,'score':score,'grade':grade}

def admin_ok(r): return bool(os.getenv('ADMIN_KEY')) and r.headers.get('X-Admin-Key')==os.getenv('ADMIN_KEY')
@app.post('/admin/settings')
async def admin_settings(p:dict,r:Request):
    if not admin_ok(r):return {'ok':False,'error':'admin key noto‘g‘ri'}
    if p.get('start'):set_setting('test_start',p['start'])
    if p.get('end'):set_setting('test_end',p['end'])
    if p.get('code'):set_setting('access_code',p['code'])
    return {'ok':True,'test':times()}
@app.post('/admin/questions')
async def admin_questions(p:dict,r:Request):
    if not admin_ok(r):return {'ok':False,'error':'admin key noto‘g‘ri'}
    items=p if isinstance(p,list) else p.get('questions',[])
    if len(items)!=45:return {'ok':False,'error':'Aynan 45 ta savol kerak'}
    rows=[(int(x.get('id',i+1)),str(x['question']),json.dumps(x.get('options',[]),ensure_ascii=False),str(x.get('answer','')),str(x.get('kind','choice')),str(x.get('group_id','')),str(x.get('image_url',''))) for i,x in enumerate(items)]
    replace_questions(rows); return {'ok':True,'count':45}
@app.get('/admin/users')
async def admin_users(r:Request):
    if not admin_ok(r):return {'ok':False,'error':'admin key noto‘g‘ri'}
    return {'ok':True,'users':[dict(x) for x in all_users()]}

def make_pdf(path):
    styles=getSampleStyleSheet(); doc=SimpleDocTemplate(path,pagesize=landscape(A4),rightMargin=24,leftMargin=24,topMargin=24,bottomMargin=24)
    rows=[['№','Ism Familiya','Ball','Baho']]
    for i,u in enumerate(all_users(),1):rows.append([str(i),u['full_name'] or '—',f"{u['score']:.2f}",u['grade'] or '—'])
    t=Table(rows,repeatRows=1,colWidths=[35,430,80,70]); t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eeeeee')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold')]))
    story=[Paragraph('134-MOCK TEST NATIJALARI',styles['Title']),Paragraph('Milliy sertifikat formatida · barcha ishtirokchilar',styles['Heading2']),Spacer(1,10),t]; doc.build(story)
@app.post('/admin/pdf')
async def admin_pdf(r:Request):
    if not admin_ok(r):return {'ok':False,'error':'admin key noto‘g‘ri'}
    path='/tmp/nur_results.pdf'; make_pdf(path); await bot.send_document(ADMIN,document=path); return {'ok':True}
@app.post('/admin/broadcast')
async def broadcast(p:dict,r:Request):
    if not admin_ok(r):return {'ok':False,'error':'admin key noto‘g‘ri'}
    sent=0
    for u in all_users():
        try: await bot.send_message(u['telegram_id'],str(p.get('text',''))); sent+=1
        except Exception: pass
    return {'ok':True,'sent':sent}

async def auto_finalize_loop():
    last_pdf=''
    while True:
        try:
            for u in all_users():
                if expired(u): await finalize_user(u['telegram_id'])
            now=datetime.now(TZ); _,end=times()
            if now.time()>=time.fromisoformat(end) and last_pdf!=now.strftime('%Y-%m-%d'):
                for u in all_users():
                    if u['started_at'] and not u['submitted']: await finalize_user(u['telegram_id'])
                path='/tmp/nur_results.pdf'; make_pdf(path); await bot.send_document(ADMIN,document=path); last_pdf=now.strftime('%Y-%m-%d')
        except Exception: pass
        await asyncio.sleep(15)

async def run():
    if not TOKEN:raise RuntimeError('BOT_TOKEN missing')
    server=uvicorn.Server(uvicorn.Config(app,host='0.0.0.0',port=PORT))
    await asyncio.gather(dp.start_polling(bot),server.serve(),auto_finalize_loop())
if __name__=='__main__':asyncio.run(run())
