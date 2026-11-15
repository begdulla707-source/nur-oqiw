import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bot import menu_settings as menus
from bot.button_styles import styled_markup,ButtonStyleMiddleware,without_custom_emoji
from aiogram.methods import SendMessage
from aiogram.types import KeyboardButton,ReplyKeyboardMarkup,InlineKeyboardButton,InlineKeyboardMarkup,WebAppInfo


class StyleTests(unittest.TestCase):
    def test_configured_reply_color_is_serialized(self):
        b=menus.button({'label':'Test','style':'success','key':'x','emoji_id':''})
        self.assertEqual(b.model_dump(exclude_none=True)['style'],'success')

    def test_default_omits_invalid_default_value(self):
        b=menus.button({'label':'Test','style':'default','key':'x','emoji_id':''})
        self.assertNotIn('style',b.model_dump(exclude_none=True))

    def test_styling_preserves_webapp_and_callback_actions(self):
        app=WebAppInfo(url='https://example.org/admin')
        m=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Admin',web_app=app)]],resize_keyboard=True)
        s=styled_markup(m);self.assertEqual(s.keyboard[0][0].web_app,app);self.assertEqual(s.keyboard[0][0].style,'primary')
        inline=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Boshlash',callback_data='run',style='danger')]])
        result=styled_markup(inline)
        self.assertEqual(result.inline_keyboard[0][0].style,'danger')
        self.assertEqual(result.inline_keyboard[0][0].callback_data,'run')

    def test_explicit_default_configuration_is_respected(self):
        m=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Oddiy')]])
        self.assertIsNone(styled_markup(m,{'Oddiy':'default'}).keyboard[0][0].style)

    def test_outgoing_method_receives_styles_without_mutating_input(self):
        db=SimpleNamespace(get_setting=lambda k,d='':json.dumps({'admin':{'Statistika':{'style':'success'}}}))
        middleware=ButtonStyleMiddleware(db)
        method=SendMessage(chat_id=12345,text='test',reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Statistika')]]))
        make=AsyncMock(return_value='OK')
        self.assertEqual(asyncio.run(middleware(make,None,method)),'OK')
        sent=make.call_args.args[1]
        self.assertEqual(sent.reply_markup.keyboard[0][0].style,'success')
        self.assertIsNone(method.reply_markup.keyboard[0][0].style)

    def test_premium_fallback_preserves_color_and_actions(self):
        method=SendMessage(chat_id=12345,text='<tg-emoji emoji-id="123">⭐</tg-emoji> Test',parse_mode='HTML',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Test',callback_data='same',style='success',icon_custom_emoji_id='123')]]))
        plain=without_custom_emoji(method)
        self.assertEqual(plain.text,'⭐ Test')
        self.assertEqual(plain.reply_markup.inline_keyboard[0][0].style,'success')
        self.assertEqual(plain.reply_markup.inline_keyboard[0][0].callback_data,'same')
        self.assertIsNone(plain.reply_markup.inline_keyboard[0][0].icon_custom_emoji_id)


if __name__=='__main__':unittest.main(verbosity=2)
