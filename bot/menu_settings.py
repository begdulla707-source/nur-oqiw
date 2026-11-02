"""Editable Telegram keyboard labels, premium emoji and native button colors."""
import json
from html import escape as escape_html
from aiogram import BaseMiddleware, F
from aiogram.types import (
    KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton,
    InlineKeyboardMarkup, WebAppInfo
)
from aiogram.filters import Command

# Canonical keys are handler action names; only their display labels change.
DEFAULTS = {
    'user': [
        ('Profilim', 'primary'), ('Pulli testlar', 'success'),
        ('Aktiv testlar', 'success'), ('Testni boshlash', 'primary'),
        ('Test kodini kiritish', 'primary'), ('Mening natijam', 'success'),
        ('Yordam', 'primary'),
    ],
    'admin': [
        ('Test sozlamalari', 'primary'), ('Pulli testlar', 'success'),
        ('Ishtirokchilar', 'primary'), ('Statistika', 'primary'),
        ('Guruhlar holati', 'primary'), ('Guruhga xabar yuborish', 'primary'),
        ('Bildirishnoma', 'success'), ('Majburiy obuna', 'success'),
        ('Mini App admini', 'primary'), ('Menyu sozlamalari', 'primary'),
    ],
}
COLORS = ('primary', 'success', 'danger', 'default')
COLORS_UZ = {'primary':'Ko‘k', 'success':'Yashil', 'danger':'Qizil', 'default':'Oddiy'}
KEY = 'menu_custom_v1'
PROFILE_KEY = 'profile_template_html_v1'
PROFILE_DEFAULT = 'PROFILIM\n\nIsm-familiya: {name}\nTest: {test}\nKod: {code}\nNatija: {result}'

def render_profile(db, values):
    template=db.get_setting(PROFILE_KEY,PROFILE_DEFAULT) or PROFILE_DEFAULT
    # Only these fixed slots are supported; never evaluate user-supplied HTML.
    for key in ('name','test','code','result'):
        template=template.replace('{'+key+'}',escape_html(str(values.get(key,'—'))))
    return template


def load(db):
    try:
        value = json.loads(db.get_setting(KEY, '{}') or '{}')
        return value if isinstance(value, dict) else {}
    except (ValueError,TypeError):
        return {}

def save(db, data):
    db.set_setting(KEY, json.dumps(data, ensure_ascii=False))

def items(db, role):
    stored = load(db).get(role, {})
    result = []
    for name, default_style in DEFAULTS[role]:
        cfg = stored.get(name, {}) if isinstance(stored,dict) else {}
        cfg = cfg if isinstance(cfg,dict) else {}
        style = cfg.get('style',default_style)
        if style not in COLORS: style = default_style
        label = str(cfg.get('label',name)).strip()[:55] or name
        icon_id = str(cfg.get('emoji_id','')).strip()
        visible = bool(cfg.get('visible',True)) or name in ('Menyu sozlamalari','Aktiv testlar')
        order = int(cfg.get('order',len(result))) if str(cfg.get('order',len(result))).lstrip('-').isdigit() else len(result)
        result.append({'key':name,'label':label,'style':style,'emoji_id':icon_id,'visible':visible,'order':order})
    return sorted(result,key=lambda item:item['order'])

def button(info, *, webapp_url=None):
    kwargs={'text':info['label']}
    if info['emoji_id']:kwargs['icon_custom_emoji_id']=info['emoji_id']
    if webapp_url and info['key']=='Mini App admini':
        kwargs['web_app']=WebAppInfo(url=webapp_url.rstrip('/')+'/admin')
    return KeyboardButton(**kwargs)

def keyboard(db, role, webapp_url, *, admin_entry=False):
    entries=[x for x in items(db,role) if x['visible']]
    rows=[]
    for n in range(0,len(entries),2):
        rows.append([button(x,webapp_url=webapp_url) for x in entries[n:n+2]])
    if admin_entry:
        rows.append([KeyboardButton(text='Admin paneliga o‘tish')])
    return ReplyKeyboardMarkup(keyboard=rows,resize_keyboard=True,is_persistent=True)

def canonical(db, text, role):
    for item in items(db,role):
        if item['visible'] and item['label']==text:return item['key']
    return text

class MenuAliasMiddleware(BaseMiddleware):
    def __init__(self,db,admin_id):
        self.db,self.admin_id=db,admin_id
    async def __call__(self,handler,event,data):
        if getattr(event,'text',None):
            role='admin' if event.from_user and event.from_user.id==self.admin_id and (self.db.get_user(self.admin_id) or {}).get('state')=='admin' else 'user'
            actual=canonical(self.db,event.text,role)
            if actual!=event.text:event=event.model_copy(update={'text':actual})
        return await handler(event,data)

def install(dp,db,admin_id,webapp_url):
    from aiogram.types import Message, CallbackQuery
    dp.message.outer_middleware(MenuAliasMiddleware(db,admin_id))

    def selector(role):
        buttons=[]
        for idx,entry in enumerate(items(db,role)):
            label=entry['label'][:32]
            buttons.append([InlineKeyboardButton(text=f"{idx+1}. {label}",callback_data=f'menub:edit:{role}:{idx}',style='primary')])
        buttons.append([InlineKeyboardButton(text='Orqaga',callback_data='menub:root')])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def root():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Foydalanuvchi menyusi',callback_data='menub:list:user',style='primary')],
            [InlineKeyboardButton(text='Admin menyusi',callback_data='menub:list:admin',style='primary')],
            [InlineKeyboardButton(text='Profilim xabari va premium emoji',callback_data='menub:profile',style='primary')],
        ])

    def editor(role,index):
        cfg=items(db,role)[index]
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Nomini o‘zgartirish',callback_data=f'menub:set:label:{role}:{index}',style='primary')],
            [InlineKeyboardButton(text='Premium emoji',callback_data=f'menub:set:emoji:{role}:{index}')],
            [InlineKeyboardButton(text='Ko‘k',callback_data=f'menub:color:primary:{role}:{index}',style='primary'),
             InlineKeyboardButton(text='Yashil',callback_data=f'menub:color:success:{role}:{index}',style='success'),
             InlineKeyboardButton(text='Qizil',callback_data=f'menub:color:danger:{role}:{index}',style='danger')],
            [InlineKeyboardButton(text='Rangsiz',callback_data=f'menub:color:default:{role}:{index}')],
            [InlineKeyboardButton(text='Yuqoriga',callback_data=f'menub:move:up:{role}:{index}'),
             InlineKeyboardButton(text='Pastga',callback_data=f'menub:move:down:{role}:{index}')],
            [InlineKeyboardButton(text='Ko‘rsatish / yashirish',callback_data=f'menub:toggle:{role}:{index}')],
            [InlineKeyboardButton(text='Tiklash',callback_data=f'menub:reset:{role}:{index}',style='danger')],
            [InlineKeyboardButton(text='Orqaga',callback_data=f'menub:list:{role}')],
        ])

    def details(role,index):
        x=items(db,role)[index]
        return f"MENYU TUGMASI\n\nBo‘lim: {'Admin' if role=='admin' else 'Foydalanuvchi'}\nAsl vazifa: {x['key']}\nKo‘rinadigan nom: {x['label']}\nRang: {COLORS_UZ[x['style']]}\nPremium emoji: {'Ulangan' if x['emoji_id'] else 'Yo‘q'}\nHolat: {'Ko‘rinadi' if x['visible'] else 'Yashirilgan'}\n\nNomini o‘zgartirish tugmaning asl vazifasini o‘zgartirmaydi."

    def mutate(role,index,fields=None,*,reset=False):
        name=items(db,role)[index]['key']
        value=load(db)
        records=value.setdefault(role,{})
        if reset:records.pop(name,None)
        else:records.setdefault(name,{}).update(fields or {})
        save(db,value)

    @dp.message(F.text=='Menyu sozlamalari')
    @dp.message(Command('menu_settings'))
    async def menu_settings(m:Message):
        if m.from_user.id!=admin_id:return
        db.update_user(admin_id,state='admin')
        await m.answer('MENYU SOZLAMALARI\n\nTugmalar nomi, ranglari, premium emojisi va tartibini sozlang.',reply_markup=root())

    @dp.callback_query(F.data.startswith('menub:'))
    async def actions(q:CallbackQuery):
        if q.from_user.id!=admin_id:return await q.answer('Ruxsat yo‘q',show_alert=True)
        args=q.data.split(':')
        action=args[1]
        if action=='profile':
            if len(args)==2:
                await q.message.edit_text('PROFILIM XABARI\n\nQuyidagi kalitlar avtomatik to‘ldiriladi: {name}, {test}, {code}, {result}. Telegram Premium emojilarni ham kiritishingiz mumkin.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Xabarni tahrirlash',callback_data='menub:profile:edit',style='primary')],[InlineKeyboardButton(text='Asl holatga qaytarish',callback_data='menub:profile:reset',style='danger')],[InlineKeyboardButton(text='Orqaga',callback_data='menub:root')]]))
            elif args[2]=='edit':
                db.update_user(admin_id,state='profile_template_edit')
                await q.message.answer('Yangi PROFILIM matnini yuboring.\n\n{name} · {test} · {code} · {result} avtomatik to‘ldiriladi. Telegram Premium emojilar ham saqlanadi. Bekor qilish: /cancel')
            elif args[2]=='reset':
                db.set_setting(PROFILE_KEY,PROFILE_DEFAULT)
                await q.message.answer('PROFILIM shabloni tiklandi.')
        elif action=='root':
            await q.message.edit_text('MENYU SOZLAMALARI',reply_markup=root())
        elif action=='list':
            role=args[2]
            if role not in DEFAULTS:return await q.answer('Noto‘g‘ri bo‘lim',show_alert=True)
            await q.message.edit_text('Tahrirlash uchun tugmani tanlang:',reply_markup=selector(role))
        else:
            role=args[-2];index=int(args[-1])
            if role not in DEFAULTS or not 0<=index<len(items(db,role)):
                return await q.answer('Tugma topilmadi',show_alert=True)
            if action=='edit':
                await q.message.edit_text(details(role,index),reply_markup=editor(role,index))
            elif action=='set':
                what=args[2]
                if what not in ('label','emoji'):return await q.answer('Noto‘g‘ri maydon',show_alert=True)
                db.set_setting('menu_edit_pending',json.dumps({'role':role,'key':items(db,role)[index]['key'],'what':what}))
                db.update_user(admin_id,state='menu_edit')
                await q.message.edit_text('Yangi nomni yuboring (55 belgigacha).' if what=='label' else 'Premium emojini yuboring. O‘chirish uchun OFF yozing. Emoji oddiy Unicode emas, Telegram premium custom emoji bo‘lishi kerak.')
            elif action=='color':
                style=args[2]
                if style not in COLORS:return await q.answer('Rang noto‘g‘ri',show_alert=True)
                mutate(role,index,{'style':style})
                await q.message.edit_text(details(role,index),reply_markup=editor(role,index))
            elif action=='toggle':
                x=items(db,role)[index]
                if x['key'] in ('Menyu sozlamalari','Aktiv testlar'):
                    return await q.answer('Bu tugma doim mavjud bo‘lishi kerak.',show_alert=True)
                mutate(role,index,{'visible':not x['visible']})
                await q.message.edit_text(details(role,index),reply_markup=editor(role,index))
            elif action=='reset':
                mutate(role,index,reset=True)
                await q.message.edit_text(details(role,index),reply_markup=editor(role,index))
            elif action=='move':
                direction=args[2]
                current=items(db,role)
                target=index+(-1 if direction=='up' else 1)
                if 0<=target<len(current):
                    value=load(db); records=value.setdefault(role,{})
                    for pos,item in enumerate(current):
                        records.setdefault(item['key'],{})['order']=pos
                    first,second=current[index],current[target]
                    records[first['key']]['order']=target
                    records[second['key']]['order']=index
                    save(db,value)
                    index=target
                await q.message.edit_text(details(role,index),reply_markup=editor(role,index))
        await q.answer()

    @dp.message(lambda m: m.from_user.id==admin_id and bool(db.get_user(admin_id)) and db.get_user(admin_id)['state']=='profile_template_edit')
    async def edit_profile_template(m:Message):
        raw=(m.text or '').strip()
        if raw=='/cancel':
            db.update_user(admin_id,state='admin')
            return await m.answer('O‘zgartirish bekor qilindi.')
        if not raw or len(raw)>2500:
            return await m.answer('Xabar matni 1 dan 2500 belgigacha bo‘lsin.')
        # aiogram preserves Telegram custom_emoji entities as safe <tg-emoji> HTML.
        custom=m.html_text or raw
        for token in ('{name}','{test}','{code}','{result}'):
            if token not in custom:
                return await m.answer('To‘rtta shablon kaliti ham bo‘lsin: {name}, {test}, {code}, {result}')
        db.set_setting(PROFILE_KEY,custom)
        db.update_user(admin_id,state='admin')
        await m.answer('PROFILIM matni saqlandi. Maxsus emoji va format saqlanadi. /start orqali menyuni yangilash mumkin.',reply_markup=keyboard(db,'admin',webapp_url))

    @dp.message(lambda m: m.from_user.id==admin_id and bool(db.get_user(admin_id)) and db.get_user(admin_id)['state']=='menu_edit')
    async def edited_value(m:Message):
        user=db.get_user(admin_id)
        if not user or user['state']!='menu_edit':return
        try:
            pending=json.loads(db.get_setting('menu_edit_pending','{}'))
            role,key,what=pending['role'],pending['key'],pending['what']
            index=next(i for i,x in enumerate(items(db,role)) if x['key']==key)
        except (KeyError,ValueError,StopIteration,TypeError):
            db.update_user(admin_id,state='admin')
            return await m.answer('Sozlamalar sessiyasi eskirgan.',reply_markup=keyboard(db,'admin',webapp_url))
        raw=(m.text or '').strip()
        if what=='label':
            if not raw or len(raw)>55 or '\n' in raw or raw.startswith('/'):
                return await m.answer('Nom 1–55 belgi bo‘lsin. Buyruq yoki yangi qator kiritmang.')
            if raw in ('Admin paneliga o‘tish','Telegram ismim bilan davom etish'):
                return await m.answer('Bu nom tizim uchun band. Boshqa nom tanlang.')
            for r in DEFAULTS:
                if any(entry['label']==raw and (r!=role or entry['key']!=key) for entry in items(db,r)):
                    return await m.answer('Bu nom boshqa tugmada ishlatilgan. Boshqa nom tanlang.')
            mutate(role,index,{'label':raw})
        else:
            emoji_id=''
            if raw.upper()!='OFF':
                entities=list(m.entities or [])
                found=next((e for e in entities if e.type=='custom_emoji' and e.custom_emoji_id),None)
                if not found:return await m.answer('Telegram Premium emojini o‘zini yuboring (oddiy emoji emas) yoki OFF yozing.')
                emoji_id=found.custom_emoji_id
            mutate(role,index,{'emoji_id':emoji_id})
        db.update_user(admin_id,state='admin')
        new_index=next(i for i,x in enumerate(items(db,role)) if x['key']==key)
        await m.answer('Saqlandi. Yangilangan tugmalar /start yoki menyu qayta ochilganda ko‘rinadi.\n\n'+details(role,new_index),reply_markup=editor(role,new_index))
