"""Send native Telegram button styles, preserving configured colors and actions."""
import time
import re

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup


def default_style(text):
    text=(text or '').casefold()
    if any(x in text for x in ('orqaga','ortga','yopish','admin menyusi')):return None
    if any(x in text for x in ('to‘xtat','to\'xtat','o‘chir','o\'chir','uzish','bekor','chiqish','off')):return 'danger'
    if any(x in text for x in ('boshlash','tasdiq','saqla','ha,','yoqish','davom','on /')):return 'success'
    return 'primary'


def styled_markup(markup,configured=None):
    if not isinstance(markup,(ReplyKeyboardMarkup,InlineKeyboardMarkup)):return markup
    field='keyboard' if isinstance(markup,ReplyKeyboardMarkup) else 'inline_keyboard'
    configured=configured or {}
    rows=[]
    for row in getattr(markup,field):
        new=[]
        for button in row:
            style=button.style
            if style is None:
                style=configured.get(button.text,default_style(button.text))
                if style=='default':style=None
            new.append(button.model_copy(update={'style':style}))
        rows.append(new)
    return markup.model_copy(update={field:rows})


def without_custom_emoji(method):
    updates={};changed=False
    for field in ('text','caption'):
        text=getattr(method,field,None)
        if isinstance(text,str) and '<tg-emoji' in text:
            updates[field]=re.sub(r'</?tg-emoji\b[^>]*>','',text);changed=True
    for field in ('entities','caption_entities'):
        entities=getattr(method,field,None)
        if entities and any(e.type=='custom_emoji' for e in entities):
            updates[field]=[e for e in entities if e.type!='custom_emoji'];changed=True
    markup=getattr(method,'reply_markup',None)
    if isinstance(markup,(ReplyKeyboardMarkup,InlineKeyboardMarkup)):
        field='keyboard' if isinstance(markup,ReplyKeyboardMarkup) else 'inline_keyboard'
        rows=[]
        for row in getattr(markup,field):
            result=[]
            for button in row:
                if button.icon_custom_emoji_id:changed=True
                result.append(button.model_copy(update={'icon_custom_emoji_id':None}))
            rows.append(result)
        updates['reply_markup']=markup.model_copy(update={field:rows})
    return method.model_copy(update=updates) if changed else None


class ButtonStyleMiddleware(BaseRequestMiddleware):
    def __init__(self,db):
        self.db=db;self.updated=0;self.configured={}

    def preferences(self):
        if time.monotonic()-self.updated>2:
            from . import menu_settings as menus
            # One database read, independent of the number of buttons in a message.
            saved=menus.load(self.db);mapping={}
            for role,entries in menus.DEFAULTS.items():
                for name,default in entries:
                    settings=saved.get(role,{}).get(name,{})
                    style=settings.get('style',default)
                    if style in menus.COLORS:mapping[str(settings.get('label',name))]=style
            self.configured=mapping;self.updated=time.monotonic()
        return self.configured

    async def __call__(self,make_request,bot,method):
        markup=getattr(method,'reply_markup',None)
        if isinstance(markup,(ReplyKeyboardMarkup,InlineKeyboardMarkup)):
            method=method.model_copy(update={'reply_markup':styled_markup(markup,self.preferences())})
        try:return await make_request(bot,method)
        except TelegramBadRequest as exc:
            if not any(word in str(exc).lower() for word in ('emoji','premium','fragment')):raise
            plain=without_custom_emoji(method)
            if plain is None:raise
            # Keep reports and menus available if Telegram denies custom emoji.
            return await make_request(bot,plain)


def install(bot,db):
    middleware=ButtonStyleMiddleware(db)
    bot.session.middleware(middleware)
    return middleware
