import os,asyncio,json
from datetime import datetime,time
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from aiogram import Bot,Dispatcher,F
from aiogram.filters import Command
from aiogram.types import Message,KeyboardButton,ReplyKeyboardMarkup,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo
from fastapi import FastAPI
import uvicorn
from .db import *
load_dotenv();init();seed()
TOKEN=os.getenv('BOT_TOKEN','');WEBAPP=os.getenv('WEBAPP_URL','https://nukuspro.uz');ADMIN=int(os.getenv('ADMIN_CHAT_ID','8379731556'));CODE=os.getenv('ACCESS_CODE','0924');TZ=ZoneInfo(os.getenv('TIMEZONE','Asia/Tashkent'));PORT=int(os.getenv('PORT','8080'));dp=Dispatcher();bot=Bot(TOKEN);app=FastAPI()
def times():return get_setting('test_start',os.getenv('TEST_START','08:30')),get_setting('test_end',os.getenv('TEST_END','09:30'))
def open_now():
 s,e=times();n=datetime.now(TZ).time();return time.fromisoformat(s)<=n<=time.fromisoformat(e)
def web():return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',web_app=WebAppInfo(url=WEBAPP))]])
def contact_kb():return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Telefon raqamini yuborish',request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)
@dp.message(Command('start'))
async def start(m:Message):
 if m.from_user.id==ADMIN:await m.answer('Admin panel',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Admin panel',web_app=WebAppInfo(url=WEBAPP+'/admin'))]]));return
 await m.answer('Ro‘yxatdan o‘tish\n\nIsm, Familiya kiriting:')
@dp.message(Command('stars'))
async def stars(m:Message):await m.answer('NUR O‘QIW ORAYI — Milliy sertifikat boti.\n\nIsm, Familiyangizni yozing!')
@dp.message(F.contact)
async def contact(m:Message):
 u=get_user(m.from_user.id)
 if not u:await m.answer('Avval /start orqali ism-familiyangizni kiriting.');return
 upsert_user(m.from_user.id,u['full_name'],m.contact.phone_number);await m.answer('Xush kelibsiz!\n\nKirish kodini yuboring:')
@dp.message()
async def text(m:Message):
 u=get_user(m.from_user.id)
 if not u:upsert_user(m.from_user.id,m.text);await m.answer('QABUL QILINDI\n\nTelefon raqamingizni kiriting:',reply_markup=contact_kb());return
 if not u['code_ok']:
  if m.text.strip()!=CODE:await m.answer('Kirish kodi noto‘g‘ri. Qaytadan kiriting.');return
  s,e=times()
  if not open_now():await m.answer(f'Kodingiz qabul qilindi. Test hozircha ochilmagan.\n\nTest vaqti: {s}–{e}.');return
  set_code(m.from_user.id);set_started(m.from_user.id,datetime.now(TZ).isoformat());await m.answer('Test ochildi.',reply_markup=web());return
@app.get('/health')
def health():return {'ok':True,'time':datetime.now(TZ).isoformat(),'test':times()}
@app.get('/api/questions')
def questions():return [{'id':q['id'],'question':q['question'],'options':json.loads(q['options_json'] or '[]'),'kind':q['kind'],'group_id':q['group_id'],'image_url':q['image_url']} for q in active_questions()]
@app.post('/api/save')
async def save(p:dict):
 u=get_user(int(p.get('telegram_id',0)))
 if not u or not u['code_ok']:return {'ok':False}
 save_answers(u['telegram_id'],p.get('answers',{}));return {'ok':True}
@app.post('/api/finish')
async def finish_api(p:dict):
 tid=int(p.get('telegram_id',0));a=p.get('answers',{});u=get_user(tid)
 if not u or not u['code_ok']:return {'ok':False,'error':'not_authorized'}
 qs=active_questions();score=round(sum(1 for q in qs if str(a.get(str(q['id']),a.get(q['id'],''))).strip().lower()==str(q['answer']).strip().lower() and q['answer'])/max(1,len(qs))*100,2);grade='A+' if score>=90 else 'A' if score>=80 else 'B+' if score>=70 else 'B' if score>=60 else 'C' if score>=50 else '—';record_stats(a);finish(tid,score,grade,datetime.now(TZ).isoformat(),a);return {'ok':True,'score':score,'grade':grade}
async def run():
 if not TOKEN:raise RuntimeError('BOT_TOKEN missing')
 server=uvicorn.Server(uvicorn.Config(app,host='0.0.0.0',port=PORT));await asyncio.gather(dp.start_polling(bot),server.serve())
if __name__=='__main__':asyncio.run(run())
