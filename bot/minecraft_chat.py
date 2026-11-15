"""Visible, opt-in Minecraft chat reports; isolated from tests and registrations.

Only a short-lived owner-created pairing code can enroll a client. Bot secrets
never leave the server. Individual devices have revocable, hashed credentials.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import Request
from fastapi.responses import JSONResponse

LOG = logging.getLogger("nur.minecraft_chat")
TZ = ZoneInfo("Asia/Tashkent")
PREFIX = "/api/minecraft-chat"
SECRET_COMMANDS = frozenset("login l register reg r changepassword changepass password passwd pass auth authenticate 2fa otp totp pin email recovery recover premium link linkaccount verify nurchat".split())
LABELED = re.compile(r"(?i)((?:password|passwd|parol|token|secret|api[_-]?key|authorization|пароль|bearer)\s*[:= ]\s*)\S+")
TOKEN = re.compile(r"(?:\d{6,12}:[A-Za-z0-9_-]{25,}|(?:ghp_|github_pat_|sk-)[A-Za-z0-9_-]{15,}|eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|[A-Za-z0-9_-]{40,})")
NICK = re.compile(r"^[A-Za-z0-9_]{1,16}$")
KINDS = {"join", "leave", "chat", "command", "heartbeat"}


def sanitized(text: str, command: bool = False) -> str | None:
    text = str(text).strip()
    if command or text.startswith("/"):
        name = text.lstrip("/").split(maxsplit=1)[0].lower().rsplit(":", 1)[-1] if text.lstrip("/") else ""
        if name in SECRET_COMMANDS:
            return None
        if not text.startswith("/"):
            text = "/" + text
    text = LABELED.sub(lambda m: m[1] + "[yashirildi]", text)
    return TOKEN.sub("[yashirildi]", text)[:1024]


def stamp(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TZ).strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, AttributeError):
        return "—"


def parse_time(value: object) -> str:
    value = str(value)[:48]
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    if dt.timestamp() > time.time() + 300:
        raise ValueError("future time")
    return dt.astimezone(timezone.utc).isoformat()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class ChatStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS pairing(code_hash TEXT PRIMARY KEY,owner INTEGER NOT NULL,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,owner INTEGER NOT NULL,token_hash TEXT UNIQUE NOT NULL,player TEXT NOT NULL,installed_at TEXT NOT NULL,consent_at TEXT NOT NULL,created_at TEXT NOT NULL,last_seen TEXT NOT NULL,last_server TEXT NOT NULL DEFAULT '',revoked INTEGER NOT NULL DEFAULT 0,notify INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,device TEXT NOT NULL,session TEXT NOT NULL,kind TEXT NOT NULL,player TEXT NOT NULL,server TEXT NOT NULL,at TEXT NOT NULL,text TEXT NOT NULL,received_at TEXT NOT NULL,notified INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS idx_mc_device_events ON events(device,seq DESC);
            CREATE INDEX IF NOT EXISTS idx_mc_pending ON events(notified,seq);
            CREATE INDEX IF NOT EXISTS idx_mc_owner ON devices(owner,last_seen DESC);
            """)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=10000")
        try:
            with c:
                yield c
        finally:
            c.close()

    def new_code(self, owner: int) -> str:
        code = secrets.token_hex(5).upper()
        with self.connect() as c:
            c.execute("DELETE FROM pairing WHERE expires<? OR used=1", (time.time(),))
            c.execute("INSERT INTO pairing(code_hash,owner,expires) VALUES(?,?,?)", (digest(code), owner, time.time()+600))
        return code

    def pair(self, code: str, player: str, installed_at: str):
        device, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
        timestamp = now()
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            pair = c.execute("SELECT * FROM pairing WHERE code_hash=? AND used=0 AND expires>?", (digest(code.upper()),time.time())).fetchone()
            if not pair:
                return None
            c.execute("UPDATE pairing SET used=1 WHERE code_hash=?", (digest(code.upper()),))
            c.execute("INSERT INTO devices(id,owner,token_hash,player,installed_at,consent_at,created_at,last_seen) VALUES(?,?,?,?,?,?,?,?)", (device,pair["owner"],digest(token),player,installed_at,timestamp,timestamp,timestamp))
        return {"ok":True,"device_id":device,"token":token,"recipient":"Nur bot administratori"}

    def authenticate(self, token: str):
        if len(token) < 32 or len(token) > 128:
            return None
        with self.connect() as c:
            row = c.execute("SELECT * FROM devices WHERE token_hash=? AND revoked=0", (digest(token),)).fetchone()
            return dict(row) if row else None

    def record(self, device: dict, events: list[dict]):
        # Validate the entire request before writing anything: retries are atomic.
        validated=[]
        for event in events:
            if not isinstance(event,dict):
                raise ValueError("event")
            kind=event.get("kind")
            if kind not in KINDS:
                raise ValueError("kind")
            event_id=str(uuid.UUID(str(event.get("id",""))))
            session=str(uuid.UUID(str(event.get("session",""))))
            player=str(event.get("player",""))
            server=str(event.get("server",""))
            if not NICK.fullmatch(player) or not server or len(server)>255 or any(ch.isspace() for ch in server) or any(ch in server for ch in "/\\@\x00"):
                raise ValueError("player or server")
            when=parse_time(event.get("at",""))
            text=sanitized(event.get("text",""),kind=="command") if kind in {"chat","command"} else ""
            if text is None or kind in {"chat","command"} and not text:
                continue
            validated.append((event_id,session,kind,player,server,when,text))
        accepted=0
        with self.connect() as c:
            if not c.execute("SELECT 1 FROM devices WHERE id=? AND revoked=0",(device["id"],)).fetchone():
                raise PermissionError("revoked")
            for event_id,session,kind,player,server,when,text in validated:
                c.execute("UPDATE devices SET player=?,last_seen=?,last_server=? WHERE id=?",(player,now(),server,device["id"]))
                if kind=="heartbeat":
                    continue
                cursor=c.execute("INSERT INTO events(id,device,session,kind,player,server,at,text,received_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",(event_id,device["id"],session,kind,player,server,when,text,now()))
                accepted+=cursor.rowcount
        return accepted

    def devices(self, owner: int, page=0):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM devices WHERE owner=? ORDER BY last_seen DESC LIMIT 9 OFFSET ?",(owner,max(0,page)*8))]

    def device(self, owner: int, device: str):
        with self.connect() as c:
            r=c.execute("SELECT * FROM devices WHERE id=? AND owner=?",(device,owner)).fetchone()
            return dict(r) if r else None

    def history(self, owner: int, device: str, page=0, limit=10):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT e.* FROM events e JOIN devices d ON d.id=e.device WHERE d.owner=? AND d.id=? ORDER BY e.seq DESC LIMIT ? OFFSET ?",(owner,device,limit,max(0,page)*limit))]

    def pending(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT e.*,d.owner,d.notify,d.revoked FROM events e JOIN devices d ON d.id=e.device WHERE e.notified=0 ORDER BY e.seq LIMIT 20")]

    def delivered(self, seq: int):
        with self.connect() as c:
            c.execute("UPDATE events SET notified=1 WHERE seq=?",(seq,))

    def toggle(self, owner: int, device: str):
        with self.connect() as c:
            c.execute("UPDATE devices SET notify=1-notify WHERE id=? AND owner=?",(device,owner))

    def revoke(self, owner: int, device: str):
        with self.connect() as c:
            c.execute("UPDATE devices SET revoked=1 WHERE id=? AND owner=?",(device,owner))


def report(event: dict) -> str:
    name,server=escape(event["player"]),escape(event["server"])
    moment=stamp(event["at"])
    if event["kind"]=="join":
        return f"<b>O‘yinchi ({name})</b>\nIP: <code>{server}</code>\nKirdi: {moment}"
    if event["kind"]=="leave":
        return f"<b>O‘yinchi ({name})</b>\nIP: <code>{server}</code>\nChiqdi: {moment}"
    label="Buyruq" if event["kind"]=="command" else "Chat"
    return f"<b>{label} · {name}</b>\nIP: <code>{server}</code>\n{moment}\n\n{escape(event['text'])}"


def markup(rows):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label,callback_data=data) for label,data in row] for row in rows])


def install(core):
    path=Path(os.getenv("NUR_CHAT_DB",str(Path(__file__).resolve().parent.parent/"data"/"minecraft-chat.sqlite3")))
    store=ChatStore(path)
    task=None
    limits=defaultdict(deque)

    def allowed(key, count, window):
        t=time.monotonic(); q=limits[key]
        while q and q[0]<t-window:q.popleft()
        if len(q)>=count:return False
        q.append(t)
        if len(limits)>10000:
            for old in list(limits)[:2000]:
                if not limits[old] or limits[old][-1]<t-600:limits.pop(old,None)
        return True

    async def body(request):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>65536:raise ValueError("request too large")
        data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError("object required")
        return data

    @core.app.get(PREFIX+"/health")
    async def chat_health():
        return {"ok":True,"minecraft":"1.21.1","consent_required":True,"version":"1.0.0"}

    @core.app.post(PREFIX+"/pair")
    async def pair_client(request: Request):
        ip=request.client.host if request.client else "unknown"
        if not allowed(("pair",ip),8,600):return JSONResponse({"ok":False},status_code=429)
        try:
            data=await body(request)
            if data.get("consent") is not True:raise ValueError("consent required")
            code=str(data.get("code","")); player=str(data.get("player",""))
            if not re.fullmatch(r"[A-Fa-f0-9]{10}",code) or not NICK.fullmatch(player):raise ValueError("invalid")
            installed=parse_time(data.get("installed_at",""))
            result=await asyncio.to_thread(store.pair,code,player,installed)
            return result if result else JSONResponse({"ok":False,"error":"invalid_or_expired_code"},status_code=403)
        except (ValueError,TypeError,KeyError):
            return JSONResponse({"ok":False,"error":"invalid_request"},status_code=400)

    @core.app.post(PREFIX+"/events")
    async def receive_events(request: Request):
        auth=request.headers.get("authorization","")
        token=auth[7:] if auth.startswith("Bearer ") else ""
        if not allowed(("auth",request.client.host if request.client else "unknown"),600,60):return JSONResponse({"ok":False},status_code=429)
        device=await asyncio.to_thread(store.authenticate,token)
        if not device:return JSONResponse({"ok":False},status_code=403)
        if not allowed(("device",device["id"]),90,60):return JSONResponse({"ok":False},status_code=429)
        try:
            data=await body(request); events=data.get("events")
            if not isinstance(events,list) or not 1<=len(events)<=32:raise ValueError("events")
            accepted=await asyncio.to_thread(store.record,device,events)
            return {"ok":True,"accepted":accepted}
        except PermissionError:return JSONResponse({"ok":False},status_code=403)
        except (ValueError,TypeError,KeyError):return JSONResponse({"ok":False,"error":"invalid_events"},status_code=400)

    async def deliver():
        while True:
            try:
                events=await asyncio.to_thread(store.pending)
                for event in events:
                    if event["notify"] and not event["revoked"]:
                        await core.bot.send_message(event["owner"],report(event),parse_mode="HTML",disable_web_page_preview=True)
                        await asyncio.sleep(0.65)
                    await asyncio.to_thread(store.delivered,event["seq"])
            except asyncio.CancelledError:raise
            except Exception as exc:
                # Never include request bodies or credentials in logs.
                LOG.warning("Minecraft delivery delayed: %s",type(exc).__name__)
                await asyncio.sleep(8)
            await asyncio.sleep(1)

    @core.app.on_event("startup")
    async def start_reports():
        nonlocal task
        task=asyncio.create_task(deliver(),name="nur-chat-reports")

    @core.app.on_event("shutdown")
    async def stop_reports():
        if task:
            task.cancel(); await asyncio.gather(task,return_exceptions=True)

    def private_admin(message):
        return bool(message and message.from_user and message.from_user.id==core.ADMIN and message.chat.type=="private")

    async def show_root(message):
        await message.answer("CHAT SOZLAMALARI\n\nMinecraft 1.21.1 / Fabric\nO‘yinchi rozilik berganidan keyin uning yuborgan chatlari, buyruqlari va server tarixi shu yerda ko‘rinadi.\n\n/login, /register, parol va tokenlar olinmaydi. Vaqt: Toshkent.",reply_markup=markup([[('O‘yinchilar','mcchat:players:0')],[('Modni ulash kodi','mcchat:code')],[('O‘rnatish yo‘riqnomasi','mcchat:help')],[('Admin menyusi','mcchat:back')]]))

    @core.dp.message(F.text=="Chat sozlamalari")
    @core.dp.message(Command("chat_settings"))
    async def open_chat_settings(message):
        if not private_admin(message):return
        core.update_user(core.ADMIN,state="admin")
        core.set_setting("mock_menu_"+str(core.ADMIN),"")
        await show_root(message)

    async def show_device(message, owner, identifier):
        d=await asyncio.to_thread(store.device,owner,identifier)
        if not d:return await message.answer("Qurilma topilmadi.")
        state="Uzilgan" if d["revoked"] else "Ulangan"
        notify="Yoqilgan" if d["notify"] else "O‘chirilgan"
        text=f"<b>O‘yinchi ({escape(d['player'])})</b>\nIP: <code>{escape(d['last_server']) or '—'}</code>\nHolat: {state}\nMod ilk ishga tushgan: {stamp(d['installed_at'])}\nRozilik / ulanish: {stamp(d['consent_at'])}\nOxirgi aloqa: {stamp(d['last_seen'])}\nYangi xabarlar: {notify}"
        rows=[[('Chat va buyruqlar',f'mcchat:history:{identifier}:0')],[('Tarixni TXT olish',f'mcchat:export:{identifier}')],[('Bildirishnoma ON/OFF',f'mcchat:notify:{identifier}')]]
        if not d['revoked']:rows.append([('Qurilmani uzish',f'mcchat:revoke:{identifier}')])
        rows.append([('O‘yinchilar','mcchat:players:0')])
        await message.answer(text,parse_mode="HTML",reply_markup=markup(rows))

    @core.dp.callback_query(F.data.startswith("mcchat:"))
    async def chat_callback(q):
        if q.from_user.id!=core.ADMIN or not q.message or q.message.chat.type!="private":
            return await q.answer("Faqat administrator uchun.",show_alert=True)
        await q.answer()
        parts=q.data.split(":"); action=parts[1]; owner=core.ADMIN
        if action=="root":return await show_root(q.message)
        if action=="back":return await q.message.answer("Admin boshqaruv menyusi.",reply_markup=core.admin_kb())
        if action=="help":
            return await q.message.answer("1. NurChat-1.21.1.jar faylini Minecraft mods papkasiga qo‘ying. Fabric 1.21.1 va Java 21 kerak; Fabric API jar ichiga qo‘shilgan.\n2. Botdagi «Modni ulash kodi» tugmasini bosing.\n3. Minecraft ichida F8 bosing, kodni kiriting va ma’lumot yuborishga rozilik bering.\n4. Serverga kirganda xabar keladi; keyin chat va maxfiy bo‘lmagan buyruqlar alohida yuboriladi.\n\nMod ishlayotganida ekranda Nur Chat belgisi turadi. F8 orqali to‘xtatiladi. Mod o‘rnatilishidan / rozilikdan oldingi chatlar olinmaydi. Maxfiy kalitlarni modga yozmang.")
        if action=="code":
            code=await asyncio.to_thread(store.new_code,owner)
            return await q.message.answer(f"<b>Modni ulash kodi</b>\n\n<code>{code}</code>\n\n10 daqiqa amal qiladi, faqat bir marta ishlaydi. O‘yinchi F8 oynasida kodni kiritib, rozilik beradi. Bot tokeni kerak emas.",parse_mode="HTML")
        if action=="players":
            try:page=max(0,int(parts[2]))
            except (ValueError,IndexError):return
            devices=await asyncio.to_thread(store.devices,owner,page)
            rows=[]
            for d in devices[:8]:
                label=d['player']+(' · uzilgan' if d['revoked'] else '')
                rows.append([(label,f"mcchat:device:{d['id']}")])
            nav=[]
            if page:nav.append(('Oldingi',f'mcchat:players:{page-1}'))
            if len(devices)>8:nav.append(('Keyingi',f'mcchat:players:{page+1}'))
            if nav:rows.append(nav)
            rows.append([('Chat sozlamalari','mcchat:root')])
            return await q.message.answer("O‘YINCHILAR\n\n"+("O‘yinchini tanlang:" if devices else "Hali mod ulanmagan. Ulash kodi yarating va o‘yinchi F8 oynasida rozilik bersin."),reply_markup=markup(rows))
        if len(parts)<3:return
        identifier=parts[2]
        if not await asyncio.to_thread(store.device,owner,identifier):return await q.message.answer("Qurilma topilmadi.")
        if action=="device":return await show_device(q.message,owner,identifier)
        if action=="notify":
            await asyncio.to_thread(store.toggle,owner,identifier)
            return await show_device(q.message,owner,identifier)
        if action=="revoke":
            return await q.message.answer("Ulanish bekor qilinsinmi? Mod yangi ma’lumot yubora olmaydi. Tarix saqlanadi.",reply_markup=markup([[('Ha, uzish',f'mcchat:confirm:{identifier}')],[('Orqaga',f'mcchat:device:{identifier}')]]))
        if action=="confirm":
            await asyncio.to_thread(store.revoke,owner,identifier)
            return await show_device(q.message,owner,identifier)
        if action=="history":
            try:page=max(0,int(parts[3]))
            except (IndexError,ValueError):return
            events=await asyncio.to_thread(store.history,owner,identifier,page,10)
            if not events:return await q.message.answer("Hali tarix yo‘q.",reply_markup=markup([[('Orqaga',f'mcchat:device:{identifier}')]]))
            # Separate messages preserve readability even for long chat lines.
            for event in reversed(events):await q.message.answer(report(event),parse_mode="HTML",disable_web_page_preview=True)
            nav=[]
            if page:nav.append(('Yangiroq',f'mcchat:history:{identifier}:{page-1}'))
            if len(events)==10:nav.append(('Oldinroq',f'mcchat:history:{identifier}:{page+1}'))
            rows=[nav] if nav else []
            rows.append([('O‘yinchi',f'mcchat:device:{identifier}')])
            return await q.message.answer(f"Tarix: {page+1}-sahifa",reply_markup=markup(rows))
        if action=="export":
            def export():
                with store.connect() as c:
                    rows=c.execute("SELECT e.* FROM events e JOIN devices d ON d.id=e.device WHERE d.owner=? AND d.id=? ORDER BY seq",(owner,identifier))
                    out=io.StringIO(); out.write("NUR CHAT TARIXI — vaqt: Asia/Tashkent\n\n")
                    for row in rows:
                        out.write(f"{stamp(row['at'])} | {row['player']} | {row['server']} | {row['kind']}\n{row['text']}\n\n")
                    return out.getvalue().encode("utf-8")
            data=await asyncio.to_thread(export)
            return await q.message.answer_document(BufferedInputFile(data,filename="NurChat-tarix.txt"),caption="O‘yinchining saqlangan chat va server tarixi.")
    return store
