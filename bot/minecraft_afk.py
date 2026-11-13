"""Admin-only Minecraft AFK controls; isolated from test processing."""
import asyncio
import base64
import ipaddress
import json
import logging
import os
import re
import secrets
from pathlib import Path

from aiogram import F, Router
from aiogram.types import BufferedInputFile, KeyboardButton, ReplyKeyboardMarkup

from . import db

LOG = logging.getLogger('nur-oqiw.minecraft')
ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / '.cache' / 'nur-mc-runtime'
NODE = RUNTIME / 'node-v22.23.5-linux-x64' / 'bin' / 'node'
MODULES = RUNTIME / 'deps' / 'node_modules'
ACCOUNTS = 'minecraft_afk_accounts_v1'
STAGING = 'minecraft_afk_host_v1'
ICONS = {
    'server': '5341715473882955310', 'add': '6028205772117118673',
    'list': '5766994197705921104', 'tab': '6032594876506312598',
    'chat': '5884097155341226387', 'stop': '6032636795387121097',
    'back': '6039539366177541657',
}


def _button(text, icon):
    return KeyboardButton(text=text, icon_custom_emoji_id=ICONS[icon])


def menu():
    return ReplyKeyboardMarkup(keyboard=[
        [_button('Serverga kirish', 'server'), _button('Akkaunt qo‘shish', 'add')],
        [_button('Akkauntlar', 'list'), _button('TAB', 'tab')],
        [_button('Chat / buyruq', 'chat'), _button('Ulanishni boshlash', 'server')],
        [_button('Ulanishni to‘xtatish', 'stop')],
        [_button('Orqaga qaytish', 'back')],
    ], resize_keyboard=True, is_persistent=True)


def back_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[_button('Orqaga qaytish', 'back')]], resize_keyboard=True)


def accounts():
    try:
        value = json.loads(db.get_setting(ACCOUNTS, '[]') or '[]')
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


def save_accounts(value):
    db.set_setting(ACCOUNTS, json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def parse_server(text):
    text = (text or '').strip()
    if not text or text.count(':') > 1 or '/' in text or len(text) > 259:
        raise ValueError('invalid address')
    if ':' in text:
        host, port_text = text.rsplit(':', 1)
        if not port_text.isdecimal(): raise ValueError('invalid port')
        port = int(port_text)
    else:
        host, port = text, 25565
    host = host.lower().rstrip('.')
    if not 1 <= port <= 65535 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', host):
        raise ValueError('invalid address')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('private address')
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global: raise ValueError('private address')
    except ValueError as exc:
        if str(exc) == 'private address': raise
        if re.fullmatch(r'[0-9.]+', host): raise ValueError('invalid address')
    return host, port


class MinecraftBridge:
    def __init__(self, bot, admin):
        self.bot, self.admin = bot, admin
        self.proc = None
        self.read_task = None
        self.write_lock = asyncio.Lock()
        self.start_lock = asyncio.Lock()
        self.pending_requests = {}
        self.pending_captchas = {}
        self.statuses = {}
        self.selected = None
        self.closing = False
        self.restore_task = None

    async def start_process(self):
        async with self.start_lock:
            if self.proc and self.proc.returncode is None: return True
            if not NODE.is_file() or not (MODULES / 'mineflayer').is_dir() or not (MODULES / 'flayercaptcha').is_dir():
                LOG.warning('Minecraft runtime is not installed')
                return False
            try:
                # Deliberately do not pass BOT_TOKEN or database credentials to Node.
                child_env = {'PATH': '/usr/bin:/bin', 'NODE_PATH': str(MODULES), 'LANG': 'C.UTF-8'}
                # Minecraft protocol libraries need the real home directory even in offline mode.
                if os.environ.get('HOME'): child_env['HOME'] = os.environ['HOME']
                self.proc = await asyncio.create_subprocess_exec(
                    str(NODE), '--max-old-space-size=384', str(ROOT / 'bot' / 'mc_client.cjs'),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, limit=3 * 1024 * 1024,
                    env=child_env,
                )
                self.read_task = asyncio.create_task(self.read_events(self.proc), name='minecraft-events')
                return True
            except Exception:
                LOG.exception('Could not start isolated Minecraft process')
                return False

    async def send(self, action, **data):
        if not await self.start_process(): return False
        request = secrets.token_hex(8)
        future = asyncio.get_running_loop().create_future()
        self.pending_requests[request] = future
        payload = json.dumps({'action': action, 'request': request, **data}, separators=(',', ':'))
        try:
            async with self.write_lock:
                self.proc.stdin.write((payload + '\n').encode())
                await self.proc.stdin.drain()
            return await asyncio.wait_for(future, timeout=8)
        except (OSError, RuntimeError, asyncio.TimeoutError):
            return False
        finally:
            self.pending_requests.pop(request, None)

    async def read_events(self, proc):
        try:
            while True:
                line = await proc.stdout.readline()
                if not line: break
                try: event = json.loads(line)
                except (ValueError, TypeError): continue
                if not isinstance(event, dict): continue
                if event.get('event') == 'result':
                    future = self.pending_requests.get(event.get('request'))
                    if future and not future.done(): future.set_result(event.get('result'))
                elif event.get('event') == 'captcha':
                    asyncio.create_task(self.deliver_captcha(event))
                elif event.get('event') == 'status':
                    account_id, status = event.get('id'), event.get('status')
                    self.statuses[account_id] = status
                    if status in ('connecting', 'reconnecting', 'stopped'):
                        self.clear_captchas(account_id)
                    if status == 'login_needed':
                        asyncio.create_task(self.notify_login(account_id))
        except (OSError, ValueError, asyncio.CancelledError):
            pass
        finally:
            if self.proc is proc: self.proc = None
            for future in list(self.pending_requests.values()):
                if not future.done(): future.set_result(False)
            self.pending_captchas.clear()
            if not self.closing:
                self.restore_task = asyncio.create_task(self.restore_after_delay())

    def clear_captchas(self, account_id):
        self.pending_captchas = {mid: item for mid, item in self.pending_captchas.items() if item['id'] != account_id}

    async def notify_login(self, account_id):
        account = next((x for x in accounts() if x.get('id') == account_id), None)
        if account:
            try: await self.bot.send_message(self.admin, account['username'] + ': server login so‘rayapti. Chat / buyruq bo‘limidan kiriting.')
            except Exception: LOG.warning('Could not notify owner about login prompt')

    async def deliver_captcha(self, event):
        account_id, challenge = event.get('id'), event.get('challenge')
        account = next((x for x in accounts() if x.get('id') == account_id), None)
        if not account or not isinstance(challenge, str): return
        try:
            image = base64.b64decode(event.get('image', ''), validate=True)
            if not image.startswith(b'\x89PNG\r\n\x1a\n') or len(image) > 1500000: return
            self.clear_captchas(account_id)
            message = await self.bot.send_photo(
                self.admin, BufferedInputFile(image, filename='captcha.png'),
                caption=f"{account['username']} — captcha. Javobni shu rasmga Reply qiling yoki AFK menyusida oddiy yozing.",
            )
            # An event from a closed connection must not become a fresh challenge.
            if self.statuses.get(account_id) not in ('connecting', 'connected', 'login_needed'): return
            self.pending_captchas[message.message_id] = {'id': account_id, 'challenge': challenge}
        except Exception:
            LOG.warning('Could not send captcha image')

    async def restore_after_delay(self):
        await asyncio.sleep(10)
        if self.closing: return
        for account in accounts():
            if account.get('enabled'):
                await self.send('start', account=account)

    async def start_saved(self):
        await asyncio.sleep(3)
        for account in accounts():
            if account.get('enabled'):
                await self.send('start', account=account)

    async def shutdown(self):
        self.closing = True
        if self.restore_task: self.restore_task.cancel()
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.stdin.write(b'{"action":"shutdown"}\n')
                await self.proc.stdin.drain()
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=3)
            except (OSError, ProcessLookupError, asyncio.TimeoutError):
                try: self.proc.kill()
                except (OSError, ProcessLookupError): pass


def register(core, dispatcher, bot):
    bridge = MinecraftBridge(bot, core.ADMIN)
    router = Router(name='minecraft_afk')

    async def current_state():
        user = db.get_user(core.ADMIN)
        return str(user['state'] or '') if user else ''

    def is_afk(message):
        if not message.from_user or message.from_user.id != core.ADMIN or message.chat.type != 'private': return False
        user = db.get_user(core.ADMIN)
        return bool(user and str(user['state'] or '').startswith('minecraft_'))

    def is_captcha_reply(message):
        reply = getattr(message, 'reply_to_message', None)
        return bool(message.from_user and message.from_user.id == core.ADMIN and message.chat.type == 'private' and reply and reply.message_id in bridge.pending_captchas)

    async def answer_captcha(message, message_id):
        pending = bridge.pending_captchas.get(message_id)
        code = (message.text or '').strip()
        if not pending: return await message.answer('Bu captcha eskirgan. Yangi rasmni kuting.')
        if not re.fullmatch(r'[A-Za-z0-9]{1,32}', code): return await message.answer('Captcha javobi faqat harf va raqamlardan iborat bo‘lsin.')
        result = await bridge.send('answer', id=pending['id'], challenge=pending['challenge'], text=code)
        bridge.pending_captchas.pop(message_id, None)
        return await message.answer('Captcha javobi Minecraft chatiga yuborildi.' if result else 'Bu captcha eskirgan yoki aloqa uzilgan. Yangi rasmni kuting.')

    @router.message(F.from_user.id == core.ADMIN, F.chat.type == 'private', F.text == 'APK sozlamalari')
    async def open_afk(message):
        db.update_user(core.ADMIN, state='minecraft_menu')
        db.set_setting('mock_menu_' + str(core.ADMIN), '')
        await message.answer('MINECRAFT AFK BOSHQARUVI\n\nServerga kirish yoki akkaunt qo‘shishni tanlang.', reply_markup=menu())

    @router.message(is_captcha_reply)
    async def captcha_reply(message):
        await answer_captcha(message, message.reply_to_message.message_id)

    @router.message(is_afk)
    async def admin_afk(message):
        text = (message.text or '').strip()
        state = await current_state()
        if text == 'Orqaga qaytish':
            db.update_user(core.ADMIN, state='admin')
            return await message.answer('Admin boshqaruv menyusi.', reply_markup=core.admin_kb())
        if text in ('Serverga kirish', 'Akkaunt qo‘shish'):
            if len(accounts()) >= 5: return await message.answer('Bir vaqtda ko‘pi bilan 5 ta akkaunt qo‘shish mumkin.')
            db.update_user(core.ADMIN, state='minecraft_ip')
            return await message.answer('Server IP yoki manzilini yozing. Masalan: mc.minestax.uz yoki manzil:25565', reply_markup=back_keyboard())
        if state == 'minecraft_ip':
            try: host, port = parse_server(text)
            except ValueError: return await message.answer('IP yoki manzil noto‘g‘ri. Masalan: mc.minestax.uz:25565')
            db.set_setting(STAGING, json.dumps({'host': host, 'port': port}))
            db.update_user(core.ADMIN, state='minecraft_nick')
            return await message.answer('Minecraft nikingizni yozing:')
        if state == 'minecraft_nick':
            if not re.fullmatch(r'[A-Za-z0-9_]{3,16}', text): return await message.answer('Nik 3–16 ta lotin harfi, raqam yoki _ bo‘lsin.')
            existing = accounts()
            try: server = json.loads(db.get_setting(STAGING, '{}'))
            except (TypeError, ValueError): server = {}
            try: host, port = parse_server(str(server['host']) + ':' + str(server['port']))
            except (KeyError, ValueError):
                db.update_user(core.ADMIN, state='minecraft_ip')
                return await message.answer('Server manzilini qayta kiriting.')
            if any(x.get('host') == host and x.get('port') == port and str(x.get('username', '')).casefold() == text.casefold() for x in existing):
                return await message.answer('Bu nik ushbu server uchun allaqachon qo‘shilgan.')
            account = {'id': secrets.token_hex(8), 'host': host, 'port': port, 'username': text, 'enabled': True}
            existing.append(account); save_accounts(existing); bridge.selected = account['id']
            db.update_user(core.ADMIN, state='minecraft_menu')
            ok = await bridge.send('start', account=account)
            return await message.answer('Akkaunt saqlandi. Serverga ulanmoqda.' if ok else 'Akkaunt saqlandi, lekin Minecraft qismi ishga tushmadi.', reply_markup=menu())
        if text == 'Akkauntlar':
            existing = accounts()
            if not existing: return await message.answer('Hali akkaunt qo‘shilmagan.', reply_markup=menu())
            rows = [[_button('Tanlash: ' + a['username'] + ' · ' + a['id'][:4], 'list')] for a in existing]
            rows.append([_button('Orqaga qaytish', 'back')])
            return await message.answer('Boshqariladigan akkauntni tanlang:', reply_markup=ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True))
        if text.startswith('Tanlash: '):
            found = next((a for a in accounts() if text == 'Tanlash: ' + a['username'] + ' · ' + a['id'][:4]), None)
            if not found: return await message.answer('Akkaunt topilmadi.', reply_markup=menu())
            bridge.selected = found['id']; db.update_user(core.ADMIN, state='minecraft_menu')
            return await message.answer('Tanlandi: ' + found['username'], reply_markup=menu())
        selected = next((a for a in accounts() if a.get('id') == bridge.selected), None)
        if not selected and len(accounts()) == 1:
            selected = accounts()[0]; bridge.selected = selected['id']
        if text == 'TAB':
            if not selected: return await message.answer('Avval Akkauntlar tugmasidan akkauntni tanlang.')
            players = await bridge.send('tab', id=selected['id'])
            if players is False or players is None: return await message.answer('Serverga ulanmagan.')
            return await message.answer('TAB · ' + selected['username'] + '\n\n' + ('\n'.join(players) if players else 'Ro‘yxat bo‘sh.'))
        if text == 'Ulanishni boshlash':
            if not selected: return await message.answer('Avval akkauntni tanlang.')
            result = await bridge.send('start', account=selected)
            if not result: return await message.answer('Minecraft qismi ishga tushmadi. Server sozlamasini tekshiring.')
            data = accounts()
            for item in data:
                if item['id'] == selected['id']: item['enabled'] = True
            save_accounts(data); db.update_user(core.ADMIN, state='minecraft_menu')
            return await message.answer('Serverga ulanmoqda.', reply_markup=menu())
        if text == 'Ulanishni to‘xtatish':
            if not selected: return await message.answer('Avval akkauntni tanlang.')
            data = accounts()
            for item in data:
                if item['id'] == selected['id']: item['enabled'] = False
            save_accounts(data); await bridge.send('stop', id=selected['id'])
            db.update_user(core.ADMIN, state='minecraft_menu')
            return await message.answer('Ulanish to‘xtatildi.', reply_markup=menu())
        if text == 'Chat / buyruq':
            if not selected: return await message.answer('Avval akkauntni tanlang.')
            db.update_user(core.ADMIN, state='minecraft_chat')
            return await message.answer(selected['username'] + ': server chatiga yuboriladigan xabar yoki /buyruqni yozing.', reply_markup=menu())
        matching = [(mid, item) for mid, item in bridge.pending_captchas.items() if selected and item['id'] == selected['id']]
        if not matching and len(bridge.pending_captchas) == 1: matching = list(bridge.pending_captchas.items())
        if matching and re.fullmatch(r'[A-Za-z0-9]{1,32}', text):
            return await answer_captcha(message, matching[-1][0])
        if state == 'minecraft_chat':
            if not selected: return await message.answer('Avval akkauntni tanlang.')
            result = await bridge.send('message', id=selected['id'], text=text)
            return await message.answer('Minecraft chatiga yuborildi.' if result else 'Xabar yuborilmadi: ulanish yoki matnni tekshiring.')
        await message.answer('Pastki menyudan amalni tanlang.', reply_markup=menu())

    dispatcher.include_router(router)
    return bridge
