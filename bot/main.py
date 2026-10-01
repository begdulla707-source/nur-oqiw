import os,asyncio,json
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from aiogram import Bot,Dispatcher,F
from aiogram.filters import Command
from aiogram.types import Message,KeyboardButton,ReplyKeyboardMarkup,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo
from fastapi import FastAPI
import uvicorn
from .db import *
load_dotenv();init();seed()
TOKEN=os.getenv('BOT_TOKEN','');WEBAPP=os.getenv('WEBAPP_URL','https://nukuspro.uz');ADMIN=int(os.getenv('ADMIN_CHAT_ID','8379731556'));TZ=ZoneInfo(os.getenv('TIMEZONE','Asia/Tashkent'));PORT=int(os.getenv('PORT','8080'))
dp=Dispatcher();bot=Bot(TOKEN);app=FastAPI()
def times():return get_setting('test_start',os.getenv('TEST_START','08:30')),get_setting('test_end',os.getenv('TEST_END','09:30'))
def open_now():
 s,e=times();n=datetime.now(TZ).time();return time.fromisoformat(s)<=n<time.fromisoformat(e)
def web():return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',web_app=WebAppInfo(url=WEBAPP))]])
def phone_kb():return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Telefon raqamingizni yuborish',request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)
def admin_kb():return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ADMIN PANEL',web_app=WebAppInfo(url=WEBAPP+'/admin'))]])
def code_value():return get_setting('access_code',os.getenv('ACCESS_CODE','0924'))
@dp.message(Command('start'))
async def start(m:Message):
 u=ensure_user(m.from_user.id)
 if m.from_user.id==ADMIN:
  await m.answer('NUR O‘QIW ORAYI\n\nAdmin boshqaruv paneli.',reply_markup=admin_kb());return
 update_user(m.from_user.id,state='code',code_ok=0)
 await m.answer('NUR O‘QIW ORAYI — Milliy sertifikat boti.\n\nKirish kodini kiriting:')
@dp.message(Command('stars'))
async def stars(m:Message):
 ensure_user(m.from_user.id);update_user(m.from_user.id,state='code',code_ok=0)
 await m.answer('NUR O‘QIW ORAYI — Milliy sertifikat boti.\n\nKirish kodini kiriting:')
@dp.message(F.contact)
async def contact(m:Message):
 u=ensure_user(m.from_user.id)
 if u['state']!='phone':await m.answer('Avval kirish kodi va ism, familiyangizni kiriting.');return
 upsert_user(m.from_user.id,u['full_name'],m.contact.phone_number);update_user(m.from_user.id,state='ready')
 await m.answer('✅ Xush kelibsiz!\n\n👤 '+u['full_name']+'\n📱 '+m.contact.phone_number+'\n\nTelegram akkauntingiz bog‘landi!\n\n🧮 Endi siz test yecha olasiz!',reply_markup=web())
@dp.message()
async def text(m:Message):
 if not m.text:return
 u=ensure_user(m.from_user.id);state=u['state'] or 'code'
 if state=='code':
  if m.text.strip()!=code_value():await m.answer('Kirish kodi noto‘g‘ri. Qaytadan kiriting.');return
  if not open_now():
   s,_=times();await m.answer('Kodingiz qabul qilindi, lekin test hali ochilmagan.');return
  update_user(m.from_user.id,code_ok=1,state='name')
  await m.answer('📝 Ro‘yxatdan o‘tish\n\n👤 Ism, Familiya kiriting:');return
 if state=='name':
  upsert_user(m.from_user.id,m.text.strip());update_user(m.from_user.id,state='phone')
  await m.answer('QABUL QILINDI\n📱 Telefon raqamingizni kiriting:\n\nFormat: +998901234567\nMisol: +998901234567',reply_markup=phone_kb());return
 if state=='phone':await m.answer('Telefon raqamingizni tugma orqali yuboring.',reply_markup=phone_kb());return
 if state=='ready':await m.answer('Testni boshlash uchun tugmani bosing.',reply_markup=web());return
@app.get('/health')
def health():return {'ok':True,'test':times()}
@app.get('/api/questions')
def questions():return [{'id':q['id'],'question':q['question'],'options':json.loads(q['options_json'] or '[]'),'kind':q['kind'],'group_id':q['group_id'],'image_url':q['image_url']} for q in active_questions()]
@app.post('/api/save')
async def save(p:dict):
 tid=int(p.get('telegram_id',0));u=get_user(tid)
 if not u or not u['code_ok']:return {'ok':False}
 save_answers(tid,p.get('answers',{}));return {'ok':True}
@app.post('/api/finish')
async def finish_api(p:dict):
 tid=int(p.get('telegram_id',0));a=p.get('answers',{});u=get_user(tid)
 if not u or not u['code_ok']:return {'ok':False,'error':'not_authorized'}
 qs=active_questions();score=round(sum(1 for q in qs if q['answer'] and str(a.get(str(q['id']),a.get(q['id'],''))).strip().lower()==str(q['answer']).strip().lower())/max(1,len(qs))*100,2);grade='A+' if score>=90 else 'A' if score>=80 else 'B+' if score>=70 else 'B' if score>=60 else 'C' if score>=50 else '—';record_stats(a);finish(tid,score,grade,datetime.now(TZ).isoformat(),a);return {'ok':True,'score':score,'grade':grade}
async def run():
 if not TOKEN:raise RuntimeError('BOT_TOKEN missing')
 server=uvicorn.Server(uvicorn.Config(app,host='0.0.0.0',port=PORT));await asyncio.gather(dp.start_polling(bot),server.serve())
if __name__=='__main__':asyncio.run(run())
