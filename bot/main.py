import os,asyncio,logging,json,hmac,hashlib
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from urllib.parse import parse_qsl
from collections import defaultdict,deque
from dotenv import load_dotenv
from aiogram import Bot,Dispatcher,F,BaseMiddleware
from aiogram.filters import Command,CommandStart
from aiogram.types import Message,KeyboardButton,ReplyKeyboardMarkup,ReplyKeyboardRemove,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo,CallbackQuery,Update,ChatMemberUpdated
from fastapi import FastAPI,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from .db import *

load_dotenv()
import time as _time
logging.basicConfig(level=logging.INFO)
logger=logging.getLogger('nur-oqiw')
_boot_t0=_time.monotonic()
if os.getenv('NUR_SKIP_SCHEMA_INIT')!='1':init();ensure_schema();seed()
else:logger.info('Worker is using the service-managed database schema')
logger.info('Database schema ready in %.2fs',_time.monotonic()-_boot_t0)
TOKEN=os.getenv('BOT_TOKEN','');ADMIN=int(os.getenv('ADMIN_CHAT_ID','8379731556'));TZ=ZoneInfo(os.getenv('TIMEZONE','Asia/Tashkent'));PORT=int(os.getenv('PORT','10000'))
WEBAPP=os.getenv('WEBAPP_URL','https://nukuspro.uz');WEBHOOK_URL=os.getenv('WEBHOOK_URL',('https://nur-oqiw-bot.mcweb.uz/telegram/webhook' if os.getenv('MCWEB_READY')=='1' else 'https://nur-oqiw.onrender.com/telegram/webhook'));WEBHOOK_SECRET=os.getenv('WEBHOOK_SECRET','nur_oqiw_webhook')
TELEGRAM_UPDATES_MODE=os.getenv('TELEGRAM_UPDATES_MODE','webhook').strip().lower()
if TELEGRAM_UPDATES_MODE not in ('webhook','polling'):TELEGRAM_UPDATES_MODE='webhook'
ORIGINS=[x.strip().rstrip('/') for x in os.getenv('WEBAPP_ORIGINS','https://nukuspro.uz,https://www.nukuspro.uz,https://nur-oqiw.uz,https://www.nur-oqiw.uz,https://nur-oqiw-santizz.vercel.app,https://nur-oqiw-three.vercel.app').split(',') if x.strip()]
logging.basicConfig(level=logging.INFO);logger=logging.getLogger('nur-oqiw');RATE=defaultdict(deque);SUB_CACHE={}
dp=Dispatcher();bot=Bot(TOKEN);app=FastAPI();_cleanup_task=None;_polling_task=None
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
        data=json.loads(raw)
        if not isinstance(data,list):
            data=[x.strip() for x in raw.splitlines() if x.strip()]
    except Exception:
        data=[x.strip() for x in raw.splitlines() if x.strip()]
    channels=[]
    for item in data:
        channel=str(item.get('chat','') if isinstance(item,dict) else item).strip()
        if channel:channels.append(channel)
    return channels

async def subscribed(tid):
    if not sub_required():return True
    now=asyncio.get_running_loop().time();cached=SUB_CACHE.get(int(tid))
    if cached and now-cached[0]<60:return cached[1]
    channels=sub_channels()
    if not channels:return True
    semaphore=asyncio.Semaphore(5)
    async def check_channel(ch):
        async with semaphore:
            try:
                member=await asyncio.wait_for(bot.get_chat_member(ch,tid),timeout=4)
                return member.status in ('member','administrator','creator')
            except Exception as exc:
                logger.warning('Subscription check failed for %s: %s',ch,type(exc).__name__)
                return False
    checks=await asyncio.gather(*(check_channel(ch) for ch in channels),return_exceptions=True)
    result=all(x is True for x in checks);SUB_CACHE[int(tid)]=(now,result);return result

from . import menu_settings as menus

def user_menu():
    return menus.keyboard(__import__('bot.db',fromlist=['get_setting']),'user',WEBAPP)

def admin_user_menu():
    return menus.keyboard(__import__('bot.db',fromlist=['get_setting']),'user',WEBAPP,admin_entry=True)

def phone_kb():return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Telefon raqamingizni yuborish',request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)
def sub_kb():
    try: links=json.loads(get_setting('subscription_invite_links','{}') or '{}')
    except (TypeError,ValueError):links={}
    rows=[]
    for index,channel in enumerate(sub_channels(),1):
        if channel.startswith('@'):link='https://t.me/'+channel.lstrip('@')
        elif channel.startswith('-100'):link=links.get(channel,'')
        elif channel.startswith('https://t.me/'):link=channel
        else:link=''
        if link and link.startswith('https://t.me/'):
            rows.append([InlineKeyboardButton(text=f'{index}-KANALGA OBUNA BO‘LISH',url=link,style='primary')])
    rows.append([InlineKeyboardButton(text='OBUNANI TEKSHIRISH',callback_data='check_sub',style='success')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def mock_channel_status(test,user_id):
    channel=str(test['required_channel'] or '').strip()
    if not channel:return True,None
    link=str(test['required_channel_link'] or '').strip()
    if not link and channel.startswith('@'):link='https://t.me/'+channel.lstrip('@')
    try:
        member=await asyncio.wait_for(bot.get_chat_member(channel,int(user_id)),timeout=5)
        joined=member.status in ('member','administrator','creator') or (member.status=='restricted' and bool(getattr(member,'is_member',False)))
        return joined,None if joined else (link or None)
    except Exception as exc:
        logger.warning('MOCK subscription check failed for %s: %s',channel,type(exc).__name__)
        return False,link or None

def mock_subscription_kb(test,link):
    rows=[]
    if link:rows.append([InlineKeyboardButton(text='KANALGA OBUNA BO‘LISH',url=link,style='primary')])
    rows.append([InlineKeyboardButton(text='OBUNANI TEKSHIRISH',callback_data='mock_sub_check:'+str(test['test_id']),style='success')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def mock_open_kb(test):
    url=f"{WEBAPP.rstrip('/')}/test?code={test['code']}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='MOCK TESTNI OCHISH',web_app=WebAppInfo(url=url),style='primary')]])

async def prompt_mock_subscription(message,test,link=None):
    return await message.answer('Bu MOCK test uchun avval alohida kanalga obuna bo‘ling, keyin tekshirish tugmasini bosing.',reply_markup=mock_subscription_kb(test,link))

def admin_kb():
    return menus.keyboard(__import__('bot.db',fromlist=['get_setting']),'admin',WEBAPP)

@app.get('/api/ping')
async def ping():return {'ok':True}
@app.get('/health')
async def health():return {'ok':True,'service':'nur-oqiw','storage':'postgres' if USE_POSTGRES else 'sqlite','tests':len(all_tests()),'questions':sum(len(questions_for_test(t['test_id'])) for t in all_tests())}

@dp.message(CommandStart(deep_link=False))
async def start(m:Message):
    u=ensure_user(m.from_user.id)
    if m.from_user.username:set_setting('telegram_username_'+str(m.from_user.id),m.from_user.username.lstrip('@').lower())
    if m.from_user.id==ADMIN:
        name=' '.join(x for x in [m.from_user.first_name,m.from_user.last_name] if x).strip()
        if name and not u['full_name']:upsert_user(ADMIN,name)
        update_user(ADMIN,state='code')
        return await m.answer('NUR O‘QIW ORAYI\n\nFoydalanuvchi bo‘limiga xush kelibsiz. Admin paneli alohida tugmada bo‘ladi.',reply_markup=admin_user_menu())
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

@dp.message(CommandStart(deep_link=True))
async def start_deep_link(m:Message):
    u=ensure_user(m.from_user.id)
    if m.from_user.username:set_setting('telegram_username_'+str(m.from_user.id),m.from_user.username.lstrip('@').lower())
    if m.from_user.id==ADMIN:
        update_user(ADMIN,state='admin');return await m.answer('NUR O‘QIW ORAYI\n\nAdmin boshqaruv paneli.',reply_markup=admin_kb())
    parts=(m.text or '').split(maxsplit=1)
    payload=parts[1].strip() if len(parts)>1 else ''
    t=get_test_by_code_or_name(payload) if payload else None
    if not t or not can_access_test(t['test_id'],m.from_user.id,ADMIN):
        update_user(m.from_user.id,state='code',code_ok=0)
        return await m.answer('Test kodi topilmadi. Test kodini qayta kiriting:',reply_markup=user_menu())
    is_mock=bool(int(t['is_mock'] or 0))
    if is_mock and not int(t['published'] or 0):
        existing=get_attempt(t['test_id'],m.from_user.id)
        if not existing or not existing['started_at'] or existing['submitted']:
            return await m.answer('Bu MOCK test hali aktiv testlarga chiqarilmagan.')
    if not is_mock and not await subscribed(m.from_user.id):
        update_user(m.from_user.id,state='subscribe',code_ok=0);return await m.answer('Testga kirishdan oldin majburiy kanallarga obuna bo‘ling.',reply_markup=sub_kb())
    if is_mock:
        if not int(t['active'] or 0):
            return await m.answer('Bu MOCK test yopilgan.')
        joined,link=await mock_channel_status(t,m.from_user.id)
        if not joined:
            return await prompt_mock_subscription(m,t,link)
        update_user(m.from_user.id,test_id=t['test_id'],code_ok=1,state='ready')
        ensure_attempt(t['test_id'],m.from_user.id)
        return await m.answer(f"{t['name']} · MOCK test\n\nTest uchun ism-familiyangizni Mini App ichida kiriting.",reply_markup=mock_open_kb(t))
    if not u['full_name']:
        update_user(m.from_user.id,state='name_code:'+str(t['code']),code_ok=0)
        return await m.answer(f"{t['name']} testi tanlandi. Ism-familiyangizni yozing yoki Telegram ismingiz bilan davom eting:",reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Telegram ismim bilan davom etish')]],resize_keyboard=True,one_time_keyboard=True))
    update_user(m.from_user.id,test_id=t['test_id'],code_ok=1,state='ready')
    ensure_attempt(t['test_id'],m.from_user.id)
    return await m.answer(f"{t['name']} tanlandi. Testni boshlash tugmasini bosing.",reply_markup=user_menu())

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

@dp.callback_query(F.data.startswith('mock_sub_check:'))
async def check_mock_subscription(q:CallbackQuery):
    try:test_id=q.data.split(':',1)[1];test=get_test(test_id)
    except Exception:test=None
    if not test or not int(test['is_mock'] or 0) or not int(test['published'] or 0) or not int(test['active'] or 0):
        return await q.answer('MOCK test hozir aktiv emas.',show_alert=True)
    joined,link=await mock_channel_status(test,q.from_user.id)
    if not joined:
        await q.answer('Avval test kanaliga obuna bo‘ling.',show_alert=True)
        if q.message:await prompt_mock_subscription(q.message,test,link)
        return
    update_user(q.from_user.id,test_id=test['test_id'],code_ok=1,state='ready')
    ensure_attempt(test['test_id'],q.from_user.id)
    if q.message:await q.message.answer(f"{test['name']} · MOCK test\n\nIsm-familiyangizni Mini App ichida kiriting.",reply_markup=mock_open_kb(test))
    await q.answer('Obuna tasdiqlandi.')

# Only Telegram group/supergroup chat IDs are recorded; no personal DMs or channels.
def known_groups():
    try:
        parsed=json.loads(get_setting('known_groups','[]') or '[]')
    except (TypeError,ValueError):
        parsed=[]
    if not isinstance(parsed,list):return []
    result=[]
    seen=set()
    for raw in parsed:
        if not isinstance(raw,dict):continue
        try:chat_id=int(raw.get('id',0))
        except (ValueError,TypeError):continue
        if chat_id>=0 or chat_id in seen:continue
        kind=str(raw.get('type') or 'supergroup')
        if kind not in ('group','supergroup'):continue
        seen.add(chat_id)
        result.append({'id':chat_id,'title':str(raw.get('title') or chat_id)[:140],'type':kind})
    return result[:150]

def track_group(chat,joined=True):
    chat_id=int(chat.id)
    if chat_id>=0 or chat.type not in ('group','supergroup'):return
    current=known_groups()
    old=next((g for g in current if g['id']==chat_id),None)
    changed=False
    if old:
        if not joined:
            current=[x for x in current if x['id']!=chat_id];changed=True
        elif old['title']!=(chat.title or str(chat_id)) or old['type']!=chat.type:
            old['title']=str(chat.title or chat_id)[:140];old['type']=chat.type;changed=True
    elif joined:
        current.append({'id':chat_id,'title':str(chat.title or chat_id)[:140],'type':chat.type})
        changed=True
    if changed:set_setting('known_groups',json.dumps(current,ensure_ascii=False))

@dp.my_chat_member()
async def update_bot_group_membership(event:ChatMemberUpdated):
    if event.chat.type not in ('group','supergroup'):return
    status=str(event.new_chat_member.status)
    track_group(event.chat,joined=status not in ('left','kicked'))
    logger.info('Bot group membership updated: chat=%s, status=%s',event.chat.id,status)

class PrivateChatAccessGuard(BaseMiddleware):
    """Fail closed for every message/callback in a group, regardless of text.

    Old reply keyboards and inline admin buttons cannot authorize group users.
    The only group command permitted is /group_status from the configured owner.
    """
    async def __call__(self,handler,event,data):
        if isinstance(event,Message) and event.chat.type in ('group','supergroup','channel'):
            if event.chat.type in ('group','supergroup'):
                try:track_group(event.chat)
                except Exception:logger.exception('Could not track group')
                text=str(event.text or '')
                if (event.from_user and event.from_user.id==ADMIN and
                    text.split(maxsplit=1)[0].split('@')[0]=='/group_status'):
                    return await handler(event,data)
            return None
        if isinstance(event,CallbackQuery):
            chat=getattr(getattr(event,'message',None),'chat',None)
            if chat and chat.type!='private':
                try:await event.answer('Admin panel faqat bot bilan shaxsiy chatda ochiladi.',show_alert=True)
                except Exception:pass
                return None
        return await handler(event,data)

# Run before all handlers; never depend on a button label for authorization.
dp.message.outer_middleware(PrivateChatAccessGuard())
dp.callback_query.outer_middleware(PrivateChatAccessGuard())

@dp.message(Command("group_status"))
async def group_status_command(m:Message):
    if m.chat.type not in ('group','supergroup'):
        return await m.answer("Bu buyruqni bot qo‘shilgan guruh ichida yuboring.")
    try:
        me=await bot.get_me()
        member=await bot.get_chat_member(m.chat.id,me.id)
        chat=await bot.get_chat(m.chat.id)
        permissions=getattr(chat,'permissions',None)
        can_send=member.status not in ('left','kicked') and not (member.status=='administrator' and getattr(member,'can_send_messages',True) is False) and getattr(permissions,'can_send_messages',True) is not False
        track_group(m.chat)
        await m.answer(f"Guruh: {chat.title or m.chat.id}\nBot holati: {member.status}\nXabar yuborish: {'ha' if can_send else 'yo‘q'}\nAdmin huquqi: {'ha' if member.status in ('administrator','creator') else 'yo‘q'}")
    except Exception as exc:
        logger.warning("group permission check failed: %s",type(exc).__name__)
        await m.answer("Guruh ruxsatlarini tekshirib bo‘lmadi. Botni guruhga qo‘shing va xabar yuborish huquqini tekshiring.")

@dp.message(F.contact)
async def contact(m:Message):
    u=ensure_user(m.from_user.id)
    if u['state']!='phone':await m.answer('Avval ism, familiyangizni kiriting.');return
    if m.contact.user_id and m.contact.user_id!=m.from_user.id:await m.answer('O‘zingizning Telegram raqamingizni yuboring.');return
    upsert_user(m.from_user.id,u['full_name'],m.contact.phone_number);u=get_user(m.from_user.id);update_user(m.from_user.id,state='test_code' if u['test_id'] else 'code',code_ok=0);await m.answer('Telefon raqamingiz saqlandi.\n\nTest kodini kiriting:',reply_markup=ReplyKeyboardRemove())

MENU_TEXTS={'Profilim','Pulli testlar','Testni boshlash','Test kodini kiritish','Mening natijam','Yordam','Aktiv testlar','Telegram ismim bilan davom etish'}

@dp.message(F.text=='Telegram ismim bilan davom etish')
async def use_telegram_name(m:Message):
    u=ensure_user(m.from_user.id)
    state=str(u['state'] or '')
    pending_code=state.split(':',1)[1] if state.startswith('name_code:') else ''
    if u['full_name'] and not pending_code:
        update_user(m.from_user.id,state='ready' if u['test_id'] else 'code')
        return await m.answer('Ismingiz avval saqlangan. ' + ('Testni boshlashingiz mumkin.' if u['test_id'] else 'Test kodini kiriting.'),reply_markup=user_menu())
    name=' '.join(x for x in [m.from_user.first_name,m.from_user.last_name] if x).strip()
    if not name:
        return await m.answer('Telegram profilingizda ism topilmadi. Ism va familiyangizni yozing.')
    upsert_user(m.from_user.id,name)
    if pending_code:
        t=get_test_by_code_or_name(pending_code)
        if t:
            update_user(m.from_user.id,test_id=t['test_id'],code_ok=1,state='ready');ensure_attempt(t['test_id'],m.from_user.id)
            return await m.answer(f"Ism-familiya saqlandi: {name}\n{t['name']} tanlandi. Testni boshlash tugmasini bosing.",reply_markup=user_menu())
    u=get_user(m.from_user.id)
    update_user(m.from_user.id,state='ready' if u and u['test_id'] else 'code',code_ok=1 if u and u['test_id'] else 0)
    await m.answer(f'Ism-familiya saqlandi: {name}\n' + ('Test tanlangan. Testni boshlashingiz mumkin.' if u and u['test_id'] else 'Endi test kodini kiriting.'),reply_markup=user_menu())

@dp.message(F.text=='Test kodini kiritish')
async def change_test_code(m:Message):
    ensure_user(m.from_user.id)
    update_user(m.from_user.id,state='test_code',code_ok=0)
    await m.answer('Yangi testning kirish kodini kiriting:')

@dp.message(F.text & (F.from_user.id!=ADMIN) & ~F.text.in_(MENU_TEXTS))
async def registration_text(m:Message):
    u=ensure_user(m.from_user.id);st=u['state'] or 'code';text=m.text.strip()
    if st=='name' or st.startswith('name_code:'):
        if len(text)<3:return await m.answer('Ism va Familiyangizni to‘liq kiriting.')
        pending_code=st.split(':',1)[1] if st.startswith('name_code:') else ''
        upsert_user(m.from_user.id,text)
        if pending_code:
            t=get_test_by_code_or_name(pending_code)
            if t and can_access_test(t['test_id'],m.from_user.id,ADMIN):
                update_user(m.from_user.id,test_id=t['test_id'],code_ok=1,state='ready');ensure_attempt(t['test_id'],m.from_user.id)
                return await m.answer(f"Ism-familiyangiz saqlandi. {t['name']} tanlandi, Testni boshlash tugmasini bosing.",reply_markup=user_menu())
        saved=get_user(m.from_user.id);has_test=bool(saved and saved['test_id'] and get_test(saved['test_id']))
        update_user(m.from_user.id,state='ready' if has_test else 'code',code_ok=1 if has_test else 0)
        return await m.answer('Ism-familiyangiz saqlandi. ' + ('Test tanlangan, Testni boshlash tugmasini bosing.' if has_test else 'Endi test kodini kiriting.'),reply_markup=user_menu())
    if st in ('code','test_code'):
        t=get_test_by_code_or_name(text)
        if not t or not can_access_test(t['test_id'],m.from_user.id,ADMIN):return await m.answer('Test kodi noto‘g‘ri yoki pulli testga ruxsat yo‘q. Qayta kiriting:')
        is_mock=bool(int(t['is_mock'] or 0))
        if is_mock:
            if not int(t['published'] or 0) or not int(t['active'] or 0):return await m.answer('Bu MOCK test hali aktiv emas. Test kodi va holatini admin bilan tekshiring.')
            joined,link=await mock_channel_status(t,m.from_user.id)
            if not joined:return await prompt_mock_subscription(m,t,link)
            update_user(m.from_user.id,test_id=t['test_id'],code_ok=1,state='ready');ensure_attempt(t['test_id'],m.from_user.id)
            return await m.answer(f"{t['name']} · MOCK test\n\nIsm-familiyangizni Mini App ichida kiriting.",reply_markup=mock_open_kb(t))
        if not await subscribed(m.from_user.id):
            update_user(m.from_user.id,state='subscribe',code_ok=0)
            return await m.answer('Testga kirishdan oldin majburiy kanallarga obuna bo‘ling.',reply_markup=sub_kb())
        update_user(m.from_user.id,test_id=t['test_id'],code_ok=1,state='ready');ensure_attempt(t['test_id'],m.from_user.id);return await m.answer(f"{t['name']} tanlandi. Testni boshlashingiz mumkin.",reply_markup=user_menu())
    if st=='ready':return await m.answer('Testni boshlash tugmasini bosing.',reply_markup=user_menu())
    return await m.answer('Test kodini kiriting:')

@dp.message(F.text=='Aktiv testlar')
async def active_tests(m:Message):
    tests=[t for t in all_tests() if int(t['active']) and not is_paid_test(t['test_id']) and (not int(t['is_mock'] or 0) or int(t['published'] or 0))]
    if not tests:return await m.answer('Hozircha aktiv testlar mavjud emas.',reply_markup=user_menu())
    rows=[[InlineKeyboardButton(text=str(t['name'])[:48],callback_data='active_test:'+str(t['test_id']),style='success')] for t in tests[:40]]
    return await m.answer('AKTIV TESTLAR\n\nTestni tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data.startswith('active_test:'))
async def select_active_test(q:CallbackQuery):
    try:
        tid=q.data.split(':',1)[1];t=get_test(tid)
        if not t or not int(t['active']) or not can_access_test(t['test_id'],q.from_user.id,ADMIN):return await q.answer('Test hozir yopiq yoki ruxsat yo‘q.',show_alert=True)
        u=ensure_user(q.from_user.id)
        is_mock=bool(int(t['is_mock'] or 0))
        if is_mock and not int(t['published'] or 0):
            existing=get_attempt(t['test_id'],q.from_user.id)
            if not existing or not existing['started_at'] or existing['submitted']:
                return await q.answer('Bu MOCK test hozir aktiv ro‘yxatda yo‘q.',show_alert=True)
        if is_mock:
            joined,link=await mock_channel_status(t,q.from_user.id)
            if not joined:
                if q.message:await prompt_mock_subscription(q.message,t,link)
                return await q.answer('Avval test kanaliga obuna bo‘ling.',show_alert=True)
        if not u['full_name'] and not is_mock:
            await q.answer('Avval ro‘yxatdan o‘ting.',show_alert=True)
            return
        update_user(q.from_user.id,test_id=t['test_id'],code_ok=1,state='ready')
        attempt=ensure_attempt(t['test_id'],q.from_user.id)
        restarted=False
        if attempt and int(attempt['submitted'] or 0):
            if is_mock:return await q.answer('Bu MOCK testdagi urinish yakunlangan.',show_alert=True)
            outcome=restart_completed_attempt(t['test_id'],q.from_user.id)
            if outcome not in ('restarted','already_active'):
                return await q.answer('Yangi urinishni boshlash imkoni bo‘lmadi.',show_alert=True)
            restarted=outcome=='restarted'
        url=f"{WEBAPP.rstrip('/')}/test?code={t['code']}"
        await q.message.answer(str(t['name'])+'\n\n'+('Eski natijangiz arxivga saqlandi. Yangi urinish tayyor.\n' if restarted else '')+'Mini Appni oching:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='MINI APPNI OCHISH',web_app=WebAppInfo(url=url),style='primary')]]))
        await q.answer()
    except Exception:
        logger.exception('active_test callback failed')
        await q.answer('Xatolik. Qayta urinib ko‘ring.',show_alert=True)

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
    if not can_access_test(t['test_id'],m.from_user.id,ADMIN):
        return await m.answer('Bu pulli testga ruxsat yo‘q. «Pulli testlar» bo‘limidan adminga murojaat qiling.')
    if not int(t.get('active') or 0):
        return await m.answer('Bu test hozir administrator tomonidan yopilgan.')
    attempt=ensure_attempt(t['test_id'],m.from_user.id)
    restarted=False
    if attempt and int(attempt['submitted'] or 0):
        outcome=restart_completed_attempt(t['test_id'],m.from_user.id)
        if outcome not in ('restarted','already_active'):
            return await m.answer('Yangi urinishni boshlashda xatolik. Qayta urinib ko‘ring.')
        restarted=outcome=='restarted'
    url=f"{WEBAPP.rstrip('/')}/test?code={t['code']}"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',web_app=WebAppInfo(url=url),style='primary')]])
    return await m.answer(f"{t['name']}\n\n"+('Oldingi natijangiz saqlandi. Yangi urinish ochildi.\n' if restarted else '')+"Test tayyor. Quyidagi tugmani bosing — Mini App ochiladi.",reply_markup=kb)

async def cleanup_loop():
    from .features_v2 import mock_timer_tick
    while True:
        try:await mock_timer_tick()
        except asyncio.CancelledError:raise
        except Exception:logger.exception('MOCK timer cleanup failed')
        await asyncio.sleep(1)

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
        update=Update.model_validate(await request.json())
        asyncio.create_task(_process_telegram_update(update))
        return {'ok':True}
    except Exception as e:logger.exception('webhook: %s',e);return JSONResponse({'ok':False},status_code=400)

async def register_mcweb_webhook_with_retry():
    for attempt in range(12):
        try:
            await bot.set_webhook(
                WEBHOOK_URL,
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=False,
                allowed_updates=dp.resolve_used_update_types(),
                request_timeout=12
            )
            logger.info('Telegram webhook registered on MCWeb: %s', WEBHOOK_URL)
            return
        except Exception as exc:
            logger.warning('Webhook registration attempt %d failed: %s',attempt+1,str(exc)[:180])
            await asyncio.sleep(min(15+attempt*5,60))
    logger.error('Webhook registration did not succeed; server remains available for retry')

@app.on_event('startup')
async def register_mcweb_webhook():
    global _cleanup_task,_polling_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task=asyncio.create_task(cleanup_loop(),name='nur-mock-timer')
    asyncio.create_task(asyncio.to_thread(startup_maintenance))
    if os.getenv('MCWEB_READY')=='1' and TELEGRAM_UPDATES_MODE=='webhook':
        asyncio.create_task(register_mcweb_webhook_with_retry())
    elif TELEGRAM_UPDATES_MODE=='polling':
        if os.getenv('NUR_API_POLLING_ENABLED')=='1':
            if not TOKEN:
                logger.error('API polling was requested, but BOT_TOKEN is not configured')
            else:
                _polling_task=asyncio.create_task(
                    dp.start_polling(
                        bot,
                        allowed_updates=dp.resolve_used_update_types(),
                        polling_timeout=25,
                        close_bot_session=False,
                    ),
                    name='nur-telegram-polling',
                )
                logger.info('Telegram polling started inside the MCWeb API service')
        else:
            logger.info('Telegram polling is disabled in the API until NUR_API_POLLING_ENABLED=1')

@app.on_event('shutdown')
async def close_telegram_client():
    global _cleanup_task,_polling_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        await asyncio.gather(_cleanup_task,return_exceptions=True)
    _cleanup_task=None
    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
        await asyncio.gather(_polling_task,return_exceptions=True)
    _polling_task=None
    await bot.session.close()

from .features_v2 import register as register_features
register_features(__import__(__name__,fromlist=['*']),dp,bot,WEBAPP)
menus.install(dp,__import__('bot.db',fromlist=['get_setting']),ADMIN,WEBAPP)

@dp.message(F.text=='Admin paneliga o‘tish')
async def enter_admin_panel(m:Message):
    if m.chat.type!='private':
        return
    if m.from_user.id != ADMIN:
        await m.answer('Bu bo‘lim faqat administrator uchun.')
        return
    update_user(ADMIN,state='admin')
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Admin panelini ochish',web_app=WebAppInfo(url=WEBAPP.rstrip('/')+'/admin'))]])
    await m.answer('Admin paneli tayyor. Ochish uchun quyidagi tugmani bosing.',reply_markup=kb)
    await m.answer('Admin boshqaruv menyusi.',reply_markup=admin_kb())

async def main():
    server=uvicorn.Server(uvicorn.Config(app,host='0.0.0.0',port=PORT,log_level='info'));task=asyncio.create_task(server.serve())
    try:
        if os.getenv('MCWEB_READY')=='1':
            logger.info('Starting MCWeb API service; Telegram update mode is %s',TELEGRAM_UPDATES_MODE)
        else:
            logger.info('Legacy runtime: webhook registration disabled to preserve MCWeb ownership')
        await task
    finally:task.cancel();await asyncio.gather(task,return_exceptions=True)
if __name__=='__main__':asyncio.run(main())
