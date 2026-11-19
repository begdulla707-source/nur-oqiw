"""Group commands and private admin editing. Never expose admin controls in groups."""
import asyncio
import html
import json
import logging
import re
import time
from datetime import datetime, timezone

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery, CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)
from . import db

LOG=logging.getLogger("nur-oqiw.groups")
_META_CACHE={}
COMMANDS={
    "staff":"Guruh egasi va administratorlar",
    "status":"Guruh a'zolari va oxirgi 24 soat faolligi",
    "owner":"Guruh egasi",
    "me":"Mening guruhdagi statistikam",
    "top":"Eng faol o'nta ishtirokchi",
    "rules":"Guruh qoidalari",
    "info":"Guruh haqida ma'lumot",
    "admins":"Adminlar va huquqlari",
    "ping":"Bot javob tayyorlash vaqti",
    "help":"Guruh buyruqlari",
}
DEFAULTS={
    "staff":"<b>GURUH XODIMLARI</b>\n\nOwner: {owner}\n\n<b>Administratorlar:</b>\n{staff_list}\n\nJami: {admins_count}",
    "status":"<b>GURUH HOLATI</b>\n\nGuruh: {group_name}\nA'zolar: {members}\nAdministratorlar: {admins_count}\nOxirgi 24 soatda xabar yozganlar: {active_24h}\nBot holati: {bot_status}\n\n{online_note}",
    "owner":"<b>GURUH EGASI</b>\n\n{owner}\nGuruh: {group_name}",
    "me":"<b>MENING STATISTIKAM</b>\n\nFoydalanuvchi: {user}\nXabarlar: {my_messages}\nFaollik reytingi: {my_rank}\nOxirgi faollik: {my_last_seen}",
    "top":"<b>ENG FAOL 10 ISHTIROKCHI</b>\n\n{top_list}\n\nHisoblash bot guruhga qo'shilganidan yoki funksiya yoqilganidan boshlab yuritiladi.",
    "rules":"<b>GURUH QOIDALARI</b>\n\n1. Hurmat saqlang.\n2. Spam va reklama yubormang.\n3. Guruh mavzusidan chetga chiqmang.\n4. Moderatorlar talablariga rioya qiling.",
    "info":"<b>GURUH HAQIDA</b>\n\nNomi: {group_name}\nID: {group_id}\nA'zolar: {members}\nHavola: {group_link}\nTavsif: {description}",
    "admins":"<b>ADMINLAR HUQUQLARI</b>\n\n{admins_detail}",
    "ping":"<b>BOT HOLATI</b>\n\nHolat: {bot_status}\nJavobni tayyorlash: {ping_ms} ms",
    "help":"<b>GURUH BUYRUQLARI</b>\n\n{help_list}",
}
CFG_KEY="group_commands_v1"
UI_KEY="group_admin_ui_v1"
EMOJI_KEY="group_reply_icons_v1"
BACK="Orqaga qaytish"
ROOT_ROWS=[
    ["Guruhga qo‘shish","Ulangan guruhlar"],
    ["Buyruqlar","Xabarlarni tahrirlash"],
    ["Guruh statistikasi","Ruxsatlar"],
    ["Guruhga xabar yuborish","Guruhni tark etish"],
    ["Guruhni tanlash","Premium emojilar"],
    [BACK],
]
def _json_setting(key, default):
    try:
        obj=json.loads(db.get_setting(key,"{}") or "{}")
        return obj if isinstance(obj,dict) else default
    except (ValueError,TypeError):
        return default

def _save_setting(key, obj):
    db.set_setting(key,json.dumps(obj,ensure_ascii=False))

def _config():
    return _json_setting(CFG_KEY,{})

def _ui():
    return _json_setting(UI_KEY,{})

def _save_ui(**changes):
    value=_ui()
    value.update(changes)
    _save_setting(UI_KEY,value)
    return value

def _scope():
    target=str(_ui().get("scope","all"))
    if target=="all":
        return "all"
    try:
        if any(int(g["id"])==int(target) for g in _groups()):
            return target
    except (ValueError,TypeError):
        pass
    return "all"

def _groups():
    try:
        value=json.loads(db.get_setting("known_groups","[]") or "[]")
        return [g for g in value if isinstance(g,dict) and int(g.get("id",0))<0][:150]
    except (TypeError,ValueError):
        return []

def _record_for(key, scope=None):
    cfg=_config()
    scope=_scope() if scope is None else str(scope)
    general=cfg.get("global",{})
    local=cfg.get("groups",{}).get(scope,{}) if scope!="all" else {}
    base=general.get(key,{}) if isinstance(general,dict) else {}
    override=local.get(key,{}) if isinstance(local,dict) else {}
    return {**(base if isinstance(base,dict) else {}),**(override if isinstance(override,dict) else {})}

def _set_record(key, changes, scope=None, reset=False):
    scope=_scope() if scope is None else str(scope)
    cfg=_config()
    parent=cfg.setdefault("global",{}) if scope=="all" else cfg.setdefault("groups",{}).setdefault(scope,{})
    if reset:
        parent.pop(key,None)
    else:
        old=parent.get(key,{})
        old=old if isinstance(old,dict) else {}
        parent[key]={**old,**changes}
    _save_setting(CFG_KEY,cfg)

def _template(key,scope):
    record=_record_for(key,scope)
    return str(record.get("template",DEFAULTS[key]))[:3800]

def _enabled(key,scope):
    return _record_for(key,scope).get("enabled",True) is not False

def _init_activity():
    with db.conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS group_user_activity (
            chat_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '', username TEXT NOT NULL DEFAULT '',
            total_messages INTEGER NOT NULL DEFAULT 0,
            first_seen BIGINT NOT NULL, last_seen BIGINT NOT NULL,
            PRIMARY KEY(chat_id,user_id))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_group_activity_last ON group_user_activity(chat_id,last_seen)")

def _record_activity(chat_id,user):
    when=int(time.time())
    name=" ".join(x for x in (user.first_name,user.last_name) if x).strip()[:100] or str(user.id)
    username=(user.username or "")[:32]
    with db.conn() as c:
        c.execute("""INSERT INTO group_user_activity
            (chat_id,user_id,display_name,username,total_messages,first_seen,last_seen)
            VALUES (?,?,?,?,1,?,?)
            ON CONFLICT(chat_id,user_id) DO UPDATE SET
            display_name=excluded.display_name,username=excluded.username,
            total_messages=group_user_activity.total_messages+1,
            last_seen=excluded.last_seen""",
            (int(chat_id),int(user.id),name,username,when,when))

def _stats(chat_id,user_id=0):
    threshold=int(time.time())-86400
    with db.conn() as c:
        row=c.execute("""SELECT COUNT(*) AS participants,
            COALESCE(SUM(total_messages),0) AS total_messages,
            COALESCE(SUM(CASE WHEN last_seen >= ? THEN 1 ELSE 0 END),0) AS active_24h
            FROM group_user_activity WHERE chat_id=?""",(threshold,int(chat_id))).fetchone()
        top=c.execute("""SELECT user_id,display_name,username,total_messages,last_seen
            FROM group_user_activity WHERE chat_id=?
            ORDER BY total_messages DESC,last_seen DESC LIMIT 10""",(int(chat_id),)).fetchall()
        own=c.execute("""SELECT user_id,display_name,username,total_messages,last_seen
            FROM group_user_activity WHERE chat_id=? AND user_id=?""",(int(chat_id),int(user_id))).fetchone()
        rank=0
        if own:
            rank=c.execute("""SELECT COUNT(*)+1 AS n FROM group_user_activity
                WHERE chat_id=? AND total_messages>?""",(int(chat_id),own["total_messages"])).fetchone()["n"]
    return {"participants":row["participants"],"total_messages":row["total_messages"],
            "active_24h":row["active_24h"],"top":top,"own":own,"rank":rank}

def _user_link(user):
    user_id=int(getattr(user,"id",0) or (user["user_id"] if "user_id" in user else 0))
    username=getattr(user,"username",None) if not isinstance(user,dict) else user.get("username")
    if not isinstance(user,dict):
        name=" ".join(x for x in (user.first_name,user.last_name) if x).strip() or str(user_id)
    else:
        name=str(user.get("display_name") or user_id)
    url=("https://t.me/"+username) if username and re.fullmatch(r"[A-Za-z0-9_]{5,32}",username) else "tg://user?id="+str(user_id)
    return '<a href="'+html.escape(url,quote=True)+'">'+html.escape(name)+'</a>'

def _pretty_time(seconds):
    if not seconds:return "Hali faol emas"
    return datetime.fromtimestamp(int(seconds),timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

def _safe_values(values):
    rich={"owner","user","staff_list","top_list","admins_detail","help_list"}
    return {key:(str(value) if key in rich else html.escape(str(value))) for key,value in values.items()}

def _render(key,scope,values):
    rendered=_template(key,scope)
    values=_safe_values(values)
    return re.sub(r"\{([a-z0-9_]+)\}",lambda m:values.get(m.group(1),m.group(0)),rendered)

def _plain(text):
    return html.unescape(re.sub(r"<[^>]+>","",text))

def _copy_markup(text):
    plain=_plain(text)
    if 1<=len(plain)<=256:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Nusxalash",copy_text=CopyTextButton(text=plain))]])
    return None

async def _group_data(chat,bot,user=None,key="status"):
    started=time.perf_counter()
    # Group metadata is cached for 30 seconds, while .ping/.rules/.help remain instant.
    admins=[]
    count="—"
    details=None
    if key not in ("ping","rules","help","me","top"):
        cache=_META_CACHE.get(int(chat.id))
        if cache and time.monotonic()-cache[0]<30:
            admins,count,details=cache[1:]
        else:
            tasks=[
                asyncio.wait_for(bot.get_chat_administrators(chat.id),timeout=4),
                asyncio.wait_for(bot.get_chat_member_count(chat.id),timeout=4),
                asyncio.wait_for(bot.get_chat(chat.id),timeout=4),
            ]
            results=await asyncio.gather(*tasks,return_exceptions=True)
            if not isinstance(results[0],Exception):admins=results[0]
            if not isinstance(results[1],Exception):count=str(results[1])
            if not isinstance(results[2],Exception):details=results[2]
            _META_CACHE[int(chat.id)]=(time.monotonic(),admins,count,details)
    owner=next((x.user for x in admins if str(x.status) in ("creator","owner")),None)
    if key in ("status","me","top"):
        stats=await asyncio.to_thread(_stats,chat.id,user.id if user else 0)
    else:
        stats={"participants":0,"total_messages":0,"active_24h":0,
               "top":[],"own":None,"rank":0}
    staff=[x.user for x in admins if str(x.status) not in ("creator","owner")]
    staff_rows=[str(i)+". "+_user_link(x) for i,x in enumerate(staff[:40],1)]
    admin_rows=[]
    for person in admins[:40]:
        rights=[]
        for prop,description in (("can_delete_messages","xabarlarni o‘chirish"),
                 ("can_restrict_members","cheklash"),("can_invite_users","taklif"),
                 ("can_pin_messages","mahkamlash")):
            if getattr(person,prop,False):rights.append(description)
        status="Owner" if str(person.status) in ("creator","owner") else "Admin"
        admin_rows.append(_user_link(person.user)+" — "+status+(" ("+", ".join(rights)+")" if rights else ""))
    leader=[]
    for i,item in enumerate(stats["top"],1):
        leader.append(str(i)+". "+_user_link(dict(item))+" — "+str(item["total_messages"]))
    own=stats["own"]
    me_link=_user_link(user) if user else "—"
    me_link=_user_link(dict(own)) if own else me_link
    bot_status="Faol"
    link=getattr(details,"invite_link",None) or (("https://t.me/"+str(details.username)) if details and getattr(details,"username",None) else None)
    name=getattr(details,"title",None) or chat.title or str(chat.id)
    values={
        "group_name":name,"group_id":str(chat.id),"members":count,
        "admins_count":str(len(admins)),"active_24h":str(stats["active_24h"]),
        "bot_status":bot_status,"owner":_user_link(owner) if owner else "Aniqlanmadi",
        "staff_list":"\n".join(staff_rows) if staff_rows else "Boshqa adminlar yo‘q",
        "admins_detail":"\n".join(admin_rows) if admin_rows else "Ma’lumot olinmadi",
        "user":me_link,"my_messages":str(own["total_messages"] if own else 0),
        "my_rank":str(stats["rank"]) if stats["rank"] else "—",
        "my_last_seen":_pretty_time(own["last_seen"] if own else None),
        "top_list":"\n".join(leader) if leader else "Hali faol ishtirokchilar yo‘q",
        "group_link":link or "Ochiq havola mavjud emas",
        "description":getattr(details,"description",None) or "Tavsif yo‘q",
        "help_list":"\n".join("."+key+" — "+value for key,value in COMMANDS.items()),
        "online_note":"Telegram Bot API aniq online sonini ko‘rsatmaydi.",
        "ping_ms":str(round((time.perf_counter()-started)*1000)),
    }
    return values,stats

async def handle_group_message(m,bot):
    """Group messages never go through the private/admin/test routers."""
    if m.chat.type not in ("group","supergroup") or not m.from_user or m.from_user.is_bot:
        return
    text=(m.text or "").strip()
    match=re.match(r"^\.([a-z]+)(?:\s|$)",text,re.I)
    key=match.group(1).lower() if match else ""
    if key not in COMMANDS:
        # Track activity asynchronously without delaying unrelated group traffic.
        try:
            await asyncio.to_thread(_record_activity,m.chat.id,m.from_user)
        except Exception:
            LOG.exception("Group activity tracking failed")
        return
    try:
        await asyncio.to_thread(_record_activity,m.chat.id,m.from_user)
        if not _enabled(key,m.chat.id):return
        values,_=await _group_data(m.chat,bot,m.from_user,key=key)
        answer=_render(key,m.chat.id,values)
        if len(_plain(answer))>4000:
            answer="<b>Javob uzunligi chegaradan oshdi. Admin xabarni qisqartirsin.</b>"
        await m.answer(answer,parse_mode="HTML",reply_markup=_copy_markup(answer),
                       disable_web_page_preview=True)
    except Exception:
        LOG.exception("Group command %s failed in %s",key,m.chat.id)
        try:await m.answer("Buyruq bajarilmadi. Birozdan so‘ng qayta urinib ko‘ring.")
        except Exception:pass

def _scope_label():
    selected=_scope()
    if selected=="all":return "Barcha guruhlar"
    return next((str(g.get("title") or g["id"]) for g in _groups()
                 if str(g["id"])==selected),"Barcha guruhlar")

def _reply_keyboard(rows):
    icons=_json_setting(EMOJI_KEY,{})
    buttons=[]
    for row in rows:
        cells=[]
        for label in row:
            key=label
            config={"text":label}
            if isinstance(icons.get(key),str) and icons[key].isdigit():
                config["icon_custom_emoji_id"]=icons[key]
            cells.append(KeyboardButton(**config))
        buttons.append(cells)
    return ReplyKeyboardMarkup(keyboard=buttons,resize_keyboard=True,is_persistent=True)

def _root_keyboard():
    return _reply_keyboard(ROOT_ROWS)

def _cmd_keyboard():
    names=["."+name for name in COMMANDS]
    rows=[names[i:i+2] for i in range(0,len(names),2)]
    rows.append([BACK])
    return _reply_keyboard(rows)

def _inline(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _short_groups():
    return _groups()[:40]

async def _editor(m,key):
    scope=_scope()
    current=_record_for(key,scope)
    tpl=_template(key,scope)
    active=_enabled(key,scope)
    readable=_plain(tpl)
    if len(readable)>2800:readable=readable[:2800]+"..."
    rows=[
        [InlineKeyboardButton(text="Tahrirlash",callback_data="gs:edit:"+key,style="primary")],
        [InlineKeyboardButton(text="O‘chirish" if active else "Yoqish",callback_data="gs:toggle:"+key)],
        [InlineKeyboardButton(text="Standartga qaytarish",callback_data="gs:reset:"+key,style="danger")],
        [InlineKeyboardButton(text="Orqaga",callback_data="gs:commands")],
    ]
    if 1<=len(readable)<=256:
        rows.insert(1,[InlineKeyboardButton(text="Matnni nusxalash",
                    copy_text=CopyTextButton(text=readable))])
    # Preformatted preview is intentionally literal; editing supports Telegram formatted emoji.
    body=("<b>."+key+" — XABARNI SOZLASH</b>\n"
          "Guruh: "+html.escape(_scope_label())+"\n"
          "Holat: "+("Yoqilgan" if active else "O‘chirilgan")+"\n"
          "Shablon:\n<pre>"+html.escape(readable)+"</pre>\n"
          "Quyidagi {kalitlar} ma’lumot bilan to‘ldiriladi.")
    await m.answer(body[:3900],parse_mode="HTML",reply_markup=_inline(rows))

async def _show_groups(m,mode="list"):
    groups=_short_groups()
    if not groups:
        return await m.answer("Bot hali birorta guruhga qayd etilmagan. «Guruhga qo‘shish»ni bosing.")
    buttons=[]
    if mode=="scope":
        buttons.append([InlineKeyboardButton(text="Barcha guruhlar",callback_data="gs:scope:all")])
    for group in groups:
        gid=int(group["id"])
        action=("gs:scope:" if mode=="scope" else "group_leave:" if mode=="leave" else "gs:scope:")+str(gid)
        buttons.append([InlineKeyboardButton(text=str(group.get("title") or gid)[:55],
                    callback_data=action)])
    buttons.append([InlineKeyboardButton(text="Guruh sozlamalariga qaytish",callback_data="gs:home")])
    title={"scope":"Qaysi guruh uchun xabarlarni tahrirlaymiz?",
           "leave":"Bot chiqadigan guruhni tanlang (tasdiqlash chiqadi).",
           "list":"Bot qo‘shilgan guruhlar. Guruhni tanlang."}[mode]
    return await m.answer(title,reply_markup=_inline(buttons))

async def _show_icons(m):
    labels=[cell for row in ROOT_ROWS for cell in row]+["."+c for c in COMMANDS]
    rows=[[InlineKeyboardButton(text=label[:50],callback_data="gs:emoji:"+str(i))]
          for i,label in enumerate(labels)]
    rows.append([InlineKeyboardButton(text="Orqaga",callback_data="gs:home")])
    await m.answer("Premium emoji qo‘shish uchun tugmani tanlang, so‘ng bitta custom emoji yuboring.",
                   reply_markup=_inline(rows))

def _all_icon_labels():
    return [cell for row in ROOT_ROWS for cell in row]+["."+c for c in COMMANDS]

def _reset_ui():
    _save_ui(section="",mode="",key="",icon_label="")

async def _admin_home(m):
    _save_ui(section="group",mode="root",key="",icon_label="")
    return await m.answer("GURUH SOZLAMALARI\n\nTanlangan: "+_scope_label()+
                          "\n10 ta buyruq matni va har bir guruh uchun alohida sozlamalar.",
                          reply_markup=_root_keyboard())

async def _handle_admin_text(m,bot,core):
    if not m.from_user or m.from_user.id!=core.ADMIN or m.chat.type!="private":
        return False
    text=(m.text or "").strip()
    ui=_ui()
    if text=="Guruh sozlamalari":
        db.update_user(core.ADMIN,state="admin")
        await _admin_home(m)
        return True
    if ui.get("section")!="group":
        return False
    if text==BACK:
        if ui.get("mode") in ("commands","edit","emoji"):
            _save_ui(mode="root",key="",icon_label="")
            await _admin_home(m)
        else:
            _reset_ui()
            await m.answer("Admin menyusiga qaytildi.",reply_markup=core.admin_kb())
        return True
    if ui.get("mode")=="edit":
        key=ui.get("key")
        if key in COMMANDS:
            if not m.text or len(m.text)>3000:
                await m.answer("Xabar bo‘sh yoki juda uzun. 3000 belgigacha matn yuboring.")
                return True
            rich=m.html_text or html.escape(m.text)
            _set_record(key,{"template":rich})
            _save_ui(mode="commands",key="")
            await m.answer("."+key+" matni saqlandi. Premium emoji va format saqlanadi.",
                           reply_markup=_cmd_keyboard())
            await _editor(m,key)
            return True
    if ui.get("mode")=="emoji":
        label=ui.get("icon_label","")
        entities=(m.entities or [])
        emoji=next((e.custom_emoji_id for e in entities if e.type=="custom_emoji" and e.custom_emoji_id),None)
        if not emoji:
            await m.answer("Telegramdagi bitta Premium custom emojini yuboring yoki Orqaga qaytishni bosing.")
            return True
        icons=_json_setting(EMOJI_KEY,{})
        icons[label]=str(emoji)
        _save_setting(EMOJI_KEY,icons)
        _save_ui(mode="root",icon_label="")
        await m.answer("Premium emoji saqlandi: "+label,reply_markup=_root_keyboard())
        return True
    if text in ("Buyruqlar","Xabarlarni tahrirlash"):
        _save_ui(mode="commands",key="")
        await m.answer("10 ta buyruqdan birini tanlang. Har birining matni, premium emojisi va faolligini sozlaysiz.",
                       reply_markup=_cmd_keyboard())
        return True
    if text.startswith(".") and text[1:] in COMMANDS:
        _save_ui(mode="commands",key=text[1:])
        await _editor(m,text[1:])
        return True
    if text=="Guruhni tanlash":
        await _show_groups(m,"scope")
        return True
    if text=="Ulangan guruhlar":
        await _show_groups(m,"list")
        return True
    if text=="Guruhni tark etish":
        await _show_groups(m,"leave")
        return True
    if text=="Guruhga qo‘shish":
        try:
            me=await asyncio.wait_for(bot.get_me(),timeout=5)
            url="https://t.me/"+me.username+"?startgroup=true"
            await m.answer("Guruh tanlash uchun tugmani bosing. Guruh xabarlaridagi nuqtali buyruqlar ishlashi uchun botga admin huquqini bering yoki BotFather orqali Privacy Mode’ni o‘chiring.",
                reply_markup=_inline([[InlineKeyboardButton(text="Guruhga qo‘shish",url=url,style="success")]]))
        except Exception:
            await m.answer("Bot foydalanuvchi nomini olishning imkoni bo‘lmadi.")
        return True
    if text=="Guruhga xabar yuborish":
        await m.answer("Barcha ulangan guruhlarga xabar yuborish uchun:",
                       reply_markup=_inline([[InlineKeyboardButton(text="Xabar yozish",callback_data="group_compose",style="primary")]]))
        return True
    if text=="Premium emojilar":
        await _show_icons(m)
        return True
    if text in ("Guruh statistikasi","Ruxsatlar"):
        scope=_scope()
        if scope=="all":
            groups=_groups()
            text_value="Ulangan guruhlar: "+str(len(groups))+"\nAlohida guruhning ma’lumotlari uchun «Guruhni tanlash»ni bosing."
            await m.answer(text_value)
        else:
            try:
                chat=await bot.get_chat(int(scope))
                values,stats=await _group_data(chat,bot)
                if text=="Guruh statistikasi":
                    await m.answer("GURUH STATISTIKASI\n\nGuruh: "+str(chat.title)+
                      "\nBot ko‘rgan xabarlar: "+str(stats["total_messages"])+
                      "\nFaol ishtirokchilar (24 soat): "+str(stats["active_24h"])+
                      "\nKuzatilgan ishtirokchilar: "+str(stats["participants"])+
                      "\nGuruh a’zolari: "+str(values["members"]))
                else:
                    me=await bot.get_me()
                    member=await bot.get_chat_member(chat.id,me.id)
                    status=str(member.status)
                    await m.answer("BOT HUQUQLARI\n\nGuruh: "+str(chat.title)+
                       "\nHolati: "+status+"\nAdmin: "+("Ha" if status in ("administrator","creator") else "Yo‘q")+
                       "\nXabar o‘chirish: "+("Ha" if getattr(member,"can_delete_messages",False) else "Yo‘q")+
                       "\nA’zolarni cheklash: "+("Ha" if getattr(member,"can_restrict_members",False) else "Yo‘q"))
            except Exception as exc:
                LOG.warning("Cannot inspect selected group: %s",type(exc).__name__)
                await m.answer("Guruh ma’lumotlarini tekshirib bo‘lmadi.")
        return True
    # Other admin sections retain their existing handlers.
    return False

async def _handle_admin_callback(q,bot,core):
    if not q.data or not q.data.startswith("gs:"):
        return False
    if q.from_user.id!=core.ADMIN or not q.message or q.message.chat.type!="private":
        await q.answer("Faqat asosiy admin uchun.",show_alert=True)
        return True
    args=q.data.split(":")
    action=args[1]
    if action=="home":
        await _admin_home(q.message)
    elif action=="scope" and len(args)==3:
        target=args[2]
        if target!="all" and not any(str(g["id"])==target for g in _groups()):
            await q.answer("Bu guruh topilmadi.",show_alert=True)
            return True
        _save_ui(scope=target)
        await _admin_home(q.message)
    elif action=="commands":
        _save_ui(section="group",mode="commands")
        await q.message.answer("Buyruqni tanlang.",reply_markup=_cmd_keyboard())
    elif action=="edit" and len(args)==3 and args[2] in COMMANDS:
        key=args[2]
        _save_ui(section="group",mode="edit",key=key)
        await q.message.answer("."+key+" uchun yangi javob matnini yuboring.\n\n"
            "Premium emojilar va Telegram format saqlanadi. {group_name}, {members}, {owner}, {active_24h} "
            "kabi avtomatik kalitlardan foydalanish mumkin. Bekor qilish: «Orqaga qaytish».")
    elif action=="toggle" and len(args)==3 and args[2] in COMMANDS:
        key=args[2]
        _set_record(key,{"enabled":not _enabled(key,_scope())})
        await _editor(q.message,key)
    elif action=="reset" and len(args)==3 and args[2] in COMMANDS:
        key=args[2]
        _set_record(key,{},reset=True)
        await _editor(q.message,key)
    elif action=="emoji" and len(args)==3:
        try:label=_all_icon_labels()[int(args[2])]
        except (IndexError,ValueError):
            await q.answer("Tugma topilmadi.",show_alert=True)
            return True
        _save_ui(section="group",mode="emoji",icon_label=label)
        await q.message.answer(label+" tugmasi uchun bitta Telegram Premium custom emoji yuboring.")
    else:
        await q.answer("Amal aniqlanmadi.",show_alert=True)
        return True
    await q.answer()
    return True

class GroupAdminMiddleware(BaseMiddleware):
    def __init__(self,bot,core):
        self.bot,self.core=bot,core
    async def __call__(self,handler,event,data):
        if isinstance(event,Message):
            if await _handle_admin_text(event,self.bot,self.core):
                return None
        elif isinstance(event,CallbackQuery):
            if await _handle_admin_callback(event,self.bot,self.core):
                return None
        return await handler(event,data)

def install(core,dp,bot):
    _init_activity()
    guard=GroupAdminMiddleware(bot,core)
    dp.message.outer_middleware(guard)
    dp.callback_query.outer_middleware(guard)
