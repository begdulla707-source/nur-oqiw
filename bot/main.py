import os,asyncio,logging,json,hmac,hashlib
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from urllib.parse import parse_qsl
from collections import defaultdict,deque
from dotenv import load_dotenv
from aiogram import Bot,Dispatcher,F
from aiogram.filters import Command,CommandStart
from aiogram.types import Message,KeyboardButton,ReplyKeyboardMarkup,ReplyKeyboardRemove,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo,CallbackQuery,Update
from fastapi import FastAPI,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from .db import *

load_dotenv();init();ensure_schema();seed()
TOKEN=os.getenv('BOT_TOKEN','');ADMIN=int(os.getenv('ADMIN_CHAT_ID','8379731556'));TZ=ZoneInfo(os.getenv('TIMEZONE','Asia/Tashkent'));PORT=int(os.getenv('PORT','10000'))
WEBAPP=os.getenv('WEBAPP_URL','https://nukuspro.uz');WEBHOOK_URL=os.getenv('WEBHOOK_URL','https://nur-oqiw.onrender.com/telegram/webhook');WEBHOOK_SECRET=os.getenv('WEBHOOK_SECRET','nur_oqiw_webhook')
ORIGINS=[x.strip().rstrip('/') for x in os.getenv('WEBAPP_ORIGINS','https://nukuspro.uz,https://www.nukuspro.uz,https://nur-oqiw.uz,https://www.nur-oqiw.uz,https://nur-oqiw-santizz.vercel.app,https://nur-oqiw-three.vercel.app').split(',') if x.strip()]
logging.basicConfig(level=logging.INFO);logger=logging.getLogger('nur-oqiw');RATE=defaultdict(deque)
dp=Dispatcher();bot=Bot(TOKEN);app=FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_origin_regex=r'https://([a-z0-9-]+\.)*(telegram\.org|t\.me)$',
    allow_credentials=False,
    allow_methods=['GET','POST','OPTIONS'],
    allow_headers=['Content-Type','X-Admin-Key','Authorization']
)

def telegram_user(raw):
    try:
        d=dict(parse_qsl(raw or '',keep_blank_values=True));received=d.pop('hash',None);auth=int(d.get('auth_date','0'));u=json.loads(d.get('user','{}'));tid=int(u['id']);check='\n'.join(k+'='+d[k] for k in sorted(d));secret=hmac.new(b'WebAppData',TOKEN.encode(),hashlib.sha256).digest();calc=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest();return tid if received and hmac.compare_digest(calc,received) and 0 <= datetime.now(timezone.utc).timestamp()-auth <= 86400 else None
    except Exception:return None

def sub_required():return str(get_setting('subscription_required',get_setting('subscription_enabled','0'))).lower() in ('1','true','yes','on')
def sub_channels():
    raw=get_setting('subscription_channels','')
    try:
        v=json.loads(raw);return [str(x).strip() for x in v if str(x).strip()] if isinstance(v,list) else [x.strip() for x in raw.splitlines() if x.strip()]
    except:return [x.strip() for x in raw.splitlines() if x.strip()]
async def subscribed(tid):
    if not sub_required():return True
    for ch in sub_channels():
        try:
            m=await bot.get_chat_member(ch,tid)
            if m.status not in ('member','administrator','creator'):return False
        except:return False
    return True
def user_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Profilim'),KeyboardButton(text='Tariflar')],[KeyboardButton(text='Testni boshlash'),KeyboardButton(text='Test kodini kiritish')],[KeyboardButton(text='Mening natijam'),KeyboardButton(text='Yordam')]],resize_keyboard=True,is_persistent=True)
def phone_kb():return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Telefon raqamingizni yuborish',request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)
def sub_kb():
    rows=[[InlineKeyboardButton(text='KANALGA OBUNA BO‘LISH',url=(c if c.startswith('http') else 'https://t.me/'+c.lstrip('@')))] for c in sub_channels()];rows.append([InlineKeyboardButton(text='OBUNANI TEKSHIRISH',callback_data='check_sub')]);return InlineKeyboardMarkup(inline_keyboard=rows)
def admin_kb():return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Test sozlamalari'),KeyboardButton(text='Ishtirokchilar')],[KeyboardButton(text='Savollar'),KeyboardButton(text='Statistika')],[KeyboardButton(text='Real-time monitor'),KeyboardButton(text='Bildirishnoma')],[KeyboardButton(text='Majburiy obuna'),KeyboardButton(text='PDF natijalar')],[KeyboardButton(text='Tekshirish'),KeyboardButton(text='Tariflar')]],resize_keyboard=True)

@app.get('/api/ping')
async def ping():return {'ok':True}
@app.get('/health')
async def health():return {'ok':True,'service':'nur-oqiw','storage':'postgres' if USE_POSTGRES else 'sqlite','tests':len(all_tests()),'questions':sum(len(questions_for_test(t['test_id'])) for t in all_tests())}

@dp.message(CommandStart(deep_link=False))
async def start(m:Message):
    u=ensure_user(m.from_user.id)
    if m.from_user.id==ADMIN:update_user(ADMIN,state='admin');await m.answer('NUR O‘QIW ORAYI\n\nAdmin boshqaruv paneli.',reply_markup=admin_kb());return
    if not await subscribed(m.from_user.id):update_user(m.from_user.id,state='subscribe',code_ok=0);await m.answer('Testga kirishdan oldin majburiy kanallarga obuna bo‘ling.',reply_markup=sub_kb());return
    if u['full_name']:
        update_user(m.from_user.id,state='ready' if u['code_ok'] else 'code')
        if u['code_ok']:
            await m.answer('Xush kelibsiz! Ro‘yxatdan o‘tishingiz saqlangan.',reply_markup=user_menu())
        else:
            await m.answer('Ism-familiyangiz saqlangan. Test kodini kiriting yoki menyudan testni tanlang.',reply_markup=user_menu())
        return
    update_user(m.from_user.id,state='name',code_ok=0)
    await m.answer('Ro‘yxatdan o‘tish\n\nIsm, Familiyangizni yozing yoki Telegram ismingiz bilan davom eting:',reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Telegram ismim bilan davom etish')]],resize_keyboard=True,one_time_keyboard=True))

@dp.callback_query(F.data=='check_sub')
async def check_sub(q:CallbackQuery):
    if await subscribed(q.from_user.id):
        u=ensure_user(q.from_user.id)
        if u['full_name']:
            update_user(q.from_user.id,state='code')
            await q.message.answer('Ism-familiyangiz saqlangan. Test kodini kiriting:',reply_markup=user_menu())
        else:
            update_user(q.from_user.id,state='name',code_ok=0)
            await q.message.answer('Ism, Familiyangizni yozing yoki Telegram ismingiz bilan davom eting:',reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Telegram ismim bilan davom etish')]],resize_keyboard=True,one_time_keyboard=True))
    else:await q.message.answer('Barcha majburiy kanallarga obuna bo‘ling.')
    await q.answer()

@dp.message(F.contact)
async def contact(m:Message):
    u=ensure_user(m.from_user.id)
    if u['state']!='phone':await m.answer('Avval ism, familiyangizni kiriting.');return
    if m.contact.user_id and m.contact.user_id!=m.from_user.id:await m.answer('O‘zingizning Telegram raqamingizni yuboring.');return
    upsert_user(m.from_user.id,u['full_name'],m.contact.phone_number);u=get_user(m.from_user.id);update_user(m.from_user.id,state='test_code' if u['test_id'] else 'code',code_ok=0);await m.answer('Telefon raqamingiz saqlandi.\n\nTest kodini kiriting:',reply_markup=ReplyKeyboardRemove())

MENU_TEXTS={'Profilim','Tariflar','Testni boshlash','Test kodini kiritish','Mening natijam','Yordam','Telegram ismim bilan davom etish'}

@dp.message(F.text=='Telegram ismim bilan davom etish')
async def use_telegram_name(m:Message):
    u=ensure_user(m.from_user.id)
    if u['full_name']:
        update_user(m.from_user.id,state='ready' if u['test_id'] else 'code')
        return await m.answer('Ismingiz avval saqlangan. ' + ('Testni boshlashingiz mumkin.' if u['test_id'] else 'Test kodini kiriting.'),reply_markup=user_menu())
    name=' '.join(x for x in [m.from_user.first_name,m.from_user.last_name] if x).strip()
    if not name:
        return await m.answer('Telegram profilingizda ism topilmadi. Ism va familiyangizni yozing.')
    upsert_user(m.from_user.id,name)
    u=get_user(m.from_user.id)
    update_user(m.from_user.id,state='ready' if u and u['test_id'] else 'code',code_ok=1 if u and u['test_id'] else 0)
    await m.answer(f'Ism-familiya saqlandi: {name}\n' + ('Test tanlangan. Testni boshlashingiz mumkin.' if u and u['test_id'] else 'Endi test kodini kiriting.'),reply_markup=user_menu())

@dp.message(F.text=='Test kodini kiritish')
async def change_test_code(m:Message):
    u=ensure_user(m.from_user.id)
    if not await subscribed(m.from_user.id):
        return await m.answer('Avval majburiy kanallarga obuna bo‘ling.',reply_markup=sub_kb())
    update_user(m.from_user.id,state='test_code',code_ok=0)
    await m.answer('Yangi testning kirish kodini kiriting:')

@dp.message(F.text & (F.from_user.id!=ADMIN) & ~F.text.in_(MENU_TEXTS))
async def registration_text(m:Message):
    u=ensure_user(m.from_user.id);st=u['state'] or 'code';text=m.text.strip()
    if st=='name':
        if len(text)<3:return await m.answer('Ism va Familiyangizni to‘liq kiriting.')
        upsert_user(m.from_user.id,text)
        saved=get_user(m.from_user.id);has_test=bool(saved and saved['test_id'] and get_test(saved['test_id']))
        update_user(m.from_user.id,state='ready' if has_test else 'code',code_ok=1 if has_test else 0)
        return await m.answer('Ism-familiyangiz saqlandi. ' + ('Test tanlangan, Testni boshlash tugmasini bosing.' if has_test else 'Endi test kodini kiriting.'),reply_markup=user_menu())
    if st in ('code','test_code'):
        t=get_test_by_code(text)
        if not t:return await m.answer('Test kodi noto‘g‘ri. Qayta kiriting:')
        update_user(m.from_user.id,test_id=t['test_id'],code_ok=1,state='ready');ensure_attempt(t['test_id'],m.from_user.id);return await m.answer(f"{t['name']} tanlandi. Testni boshlashingiz mumkin.",reply_markup=user_menu())
    if st=='ready':return await m.answer('Testni boshlash tugmasini bosing.',reply_markup=user_menu())
    return await m.answer('Test kodini kiriting:')

@dp.message(F.text=='Testni boshlash')
async def start_test(m:Message):
    u=get_user(m.from_user.id) or ensure_user(m.from_user.id)
    u=dict(u)
    if not u.get('full_name'):
        return await m.answer('Avval ism-familiyangizni kiriting.')
    if not u.get('test_id') or not int(u.get('code_ok') or 0):
        update_user(m.from_user.id,state='test_code',code_ok=0)
        return await m.answer('Avval “Test kodini kiritish” tugmasini bosib, test kodini kiriting.')
    t=get_test(u['test_id'])
    if not t:
        update_user(m.from_user.id,test_id=None,code_ok=0,state='test_code')
        return await m.answer('Test topilmadi. Test kodini qaytadan kiriting.')
    t=dict(t)
    if not int(t.get('active') or 0):
        return await m.answer('Bu test hozir administrator tomonidan yopilgan.')
    ensure_attempt(t['test_id'],m.from_user.id)
    url=f"{WEBAPP.rstrip('/')}/test?code={t['code']}"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',web_app=WebAppInfo(url=url))]])
    return await m.answer(f"{t['name']}\n\nTest tayyor. Quyidagi tugmani bosing — Mini App ochiladi.",reply_markup=kb)

async def cleanup_loop():
    # Attempts remain active until a user submits or an admin closes the test.
    while True:
        await asyncio.sleep(3600)

@app.get('/',include_in_schema=False)
async def root():return {'ok':True,'service':'nur-oqiw','health':'/health'}
@app.middleware('http')
async def rate_limit(request:Request,call_next):
    if request.url.path.startswith('/api/'):
        ip=request.client.host if request.client else 'x';now=asyncio.get_running_loop().time();q=RATE[ip]
        while q and now-q[0]>60:q.popleft()
        if len(q)>=180:return JSONResponse({'ok':False,'error':'rate_limited'},status_code=429)
        q.append(now)
    return await call_next(request)

async def _process_telegram_update(update:Update):
    try:
        await dp.feed_update(bot,update)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception('Telegram update processing failed')

@app.post('/telegram/webhook')
async def telegram_webhook(request:Request):
    if WEBHOOK_SECRET and request.headers.get('X-Telegram-Bot-Api-Secret-Token','')!=WEBHOOK_SECRET:return JSONResponse({'ok':False},status_code=403)
    try:
        update=Update.model_validate(await request.json());await _process_telegram_update(update);return {'ok':True}
    except Exception as e:logger.exception('webhook: %s',e);return JSONResponse({'ok':False},status_code=400)

from .features_v2 import register as register_features
register_features(__import__(__name__,fromlist=['*']),dp,bot,WEBAPP)

async def main():
    cleanup=asyncio.create_task(cleanup_loop());server=uvicorn.Server(uvicorn.Config(app,host='0.0.0.0',port=PORT,log_level='info'));task=asyncio.create_task(server.serve())
    try:await bot.set_webhook(WEBHOOK_URL,secret_token=WEBHOOK_SECRET,drop_pending_updates=False,allowed_updates=dp.resolve_used_update_types());await task
    finally:cleanup.cancel();task.cancel();await asyncio.gather(cleanup,task,return_exceptions=True);await bot.session.close()
if __name__=='__main__':asyncio.run(main())