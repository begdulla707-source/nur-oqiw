"""Offline dispatch test: isolated SQLite and a fake Telegram transport."""
import asyncio
import base64
import os
from types import SimpleNamespace
from pathlib import Path

from aiogram.client.session.base import BaseSession
from aiogram.types import Message, Update

from bot import main, db


class FakeSession(BaseSession):
    def __init__(self): super().__init__(); self.calls = []; self.counter = 1000
    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method); self.counter += 1
        chat_id = getattr(method, 'chat_id', 123)
        return Message.model_validate({'message_id': self.counter, 'date': 1,
            'chat': {'id': chat_id, 'type': 'private'}, 'text': getattr(method, 'text', '') or ''}, context={'bot': bot})
    async def close(self): pass
    async def stream_content(self, *args, **kwargs):
        if False: yield b''


async def main_test():
    original_get = db.get_user
    db.get_user = lambda uid: dict(row) if (row := original_get(uid)) else None
    db.set_setting('minecraft_afk_accounts_v1', '[]')
    session = FakeSession(); main.bot.session = session
    commands = []
    async def fake_send(action, **data):
        commands.append((action, data))
        return ['Alex', 'Steve'] if action == 'tab' else True
    main.minecraft_afk.send = fake_send
    counter = 1

    async def feed(text, user=123, reply=None):
        nonlocal counter
        raw = {'message_id': counter, 'date': 1,
               'chat': {'id': user, 'type': 'private'},
               'from': {'id': user, 'is_bot': False, 'first_name': 'Test'}, 'text': text}
        if reply is not None:
            raw['reply_to_message'] = {'message_id': reply, 'date': 1, 'chat': {'id': user, 'type': 'private'}, 'text': 'captcha'}
        update = Update.model_validate({'update_id': counter, 'message': raw}, context={'bot': main.bot})
        counter += 1
        await main.dp.feed_update(main.bot, update)

    await feed('/start')
    await feed('Admin paneliga o‘tish')
    keyboard = session.calls[-1].reply_markup.keyboard
    assert keyboard[-1][0].text == 'APK sozlamalari'
    assert keyboard[-1][0].icon_custom_emoji_id
    await feed('MOCK testlar')
    assert db.get_setting('mock_menu_123') == 'admin'
    await feed('Orqaga qaytish')
    assert db.get_user(123)['state'] == 'admin'
    await feed('APK sozlamalari')
    assert db.get_user(123)['state'] == 'minecraft_menu'
    await feed('Serverga kirish'); await feed('mc.minestax.uz'); await feed('TestBot')
    items = main.minecraft_afk and __import__('bot.minecraft_afk', fromlist=['accounts']).accounts()
    assert len(items) == 1 and items[0]['username'] == 'TestBot'
    account_id = items[0]['id']
    assert commands[-1][0] == 'start'
    await feed('Chat / buyruq'); await feed('/boxpvp')
    assert commands[-1] == ('message', {'id': account_id, 'text': '/boxpvp'})
    await feed('TAB')
    assert commands[-1] == ('tab', {'id': account_id})
    main.minecraft_afk.pending_captchas[77] = {'id': account_id, 'challenge': 'challenge1'}
    await feed('Ab9', reply=77)
    assert commands[-1] == ('answer', {'id': account_id, 'challenge': 'challenge1', 'text': 'Ab9'})
    main.minecraft_afk.pending_captchas[78] = {'id': account_id, 'challenge': 'challenge2'}
    await feed('c2D')
    assert commands[-1] == ('answer', {'id': account_id, 'challenge': 'challenge2', 'text': 'c2D'})
    await feed('Orqaga qaytish')
    assert db.get_user(123)['state'] == 'admin'
    db.ensure_user(456)
    await feed('APK sozlamalari', user=456)
    assert not str(db.get_user(456)['state']).startswith('minecraft_')
    from bot import minecraft_afk
    minecraft_afk.NODE = Path('/home/container/.cache/nur-mc-runtime/node-v22.23.5-linux-x64/bin/node')
    minecraft_afk.MODULES = Path('/home/container/.cache/nur-mc-runtime/deps/node_modules')
    ipc = minecraft_afk.MinecraftBridge(main.bot, 123)
    assert await ipc.start_process()
    assert await ipc.send('tab', id='missing') is None
    child_env = Path(f'/proc/{ipc.proc.pid}/environ').read_bytes()
    assert b'BOT_TOKEN=' not in child_env and b'DATABASE_URL=' not in child_env
    await ipc.shutdown()
    print('PASS: admin menu, IP/nick, chat, TAB, captcha reply/plain and user isolation')
    await session.close()


if __name__ == '__main__': asyncio.run(main_test())
