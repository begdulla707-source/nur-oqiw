import json
import re

from aiogram import F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, Message, CallbackQuery


def _load(m):
    raw = m.get_setting("subscription_channels", "")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    old = m.get_setting("subscription_channel", "")
    if old:
        return [{"chat": old, "url": _url(old), "title": old}]
    return []


def _save(m, channels):
    m.set_setting("subscription_channels", json.dumps(channels, ensure_ascii=False))


def _enabled(m):
    return m.get_setting("subscription_enabled", "0") == "1"


def _url(chat):
    s = str(chat).strip()
    if s.startswith("https://t.me/"):
        return s
    if s.startswith("@"):
        return "https://t.me/" + s[1:]
    return ""


def _normalize(raw):
    raw = raw.strip()
    if "|" in raw:
        left, right = [x.strip() for x in raw.split("|", 1)]
        chat = left
        url = right
    else:
        chat = raw
        url = _url(raw)
    if chat.startswith("https://t.me/"):
        chat = "@" + chat.rstrip("/").split("/")[-1]
    return chat, url


def menu(m):
    state = "YOQILGAN" if _enabled(m) else "OCHIRILGAN"
    channels = _load(m)
    rows = [
        [InlineKeyboardButton(text=f"Majburiy obuna: {state}", callback_data="sub_toggle")],
        [InlineKeyboardButton(text="Kanal qo‘shish", callback_data="sub_add"),
         InlineKeyboardButton(text="Kanallar", callback_data="sub_list")],
        [InlineKeyboardButton(text="Kanalni tahrirlash", callback_data="sub_edit_list"),
         InlineKeyboardButton(text="Kanalni o‘chirish", callback_data="sub_delete_list")],
        [InlineKeyboardButton(text="Tekshirish", callback_data="sub_check_config"),
         InlineKeyboardButton(text="Orqaga", callback_data="admin_home")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channel_list_kb(m, mode):
    channels = _load(m)
    rows = []
    for i, ch in enumerate(channels):
        title = ch.get("title") or ch.get("chat") or str(i + 1)
        rows.append([InlineKeyboardButton(text=f"{i+1}. {title}"[:60], callback_data=f"sub_{mode}_{i}")])
    rows.append([InlineKeyboardButton(text="Orqaga", callback_data="sub_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _replace_text_handler(m, new_handler):
    handlers = m.dp.message.handlers
    for h in list(handlers):
        if getattr(h.callback, "__name__", "") == "text_handler":
            handlers.remove(h)
    m.dp.message.register(new_handler)


def install(m):
    async def subscription_menu_message(msg: Message):
        if msg.from_user.id != m.ADMIN:
            return False
        if (msg.text or "").strip() != "Majburiy obuna":
            return False
        m.update_user(m.ADMIN, state="admin")
        await msg.answer("MAJBURIY OBUNA BOSHQARUVI\n\n" + ("Yoqilgan" if _enabled(m) else "O‘chirilgan") + f"\nKanallar: {len(_load(m))}", reply_markup=menu(m))
        return True

    original = m.text_handler

    async def wrapped(msg: Message):
        if await subscription_menu_message(msg):
            return
        if msg.from_user.id == m.ADMIN:
            state = (m.get_user(m.ADMIN)["state"] or "")
            if state == "admin_sub_add":
                chat, url = _normalize(msg.text or "")
                if not chat:
                    await msg.answer("Kanal username yoki chat ID kiriting.")
                    return
                channels = _load(m)
                if any(str(x.get("chat")) == chat for x in channels):
                    await msg.answer("Bu kanal allaqachon qo‘shilgan.", reply_markup=menu(m)); m.update_user(m.ADMIN, state="admin"); return
                channels.append({"chat": chat, "url": url, "title": chat})
                _save(m, channels)
                m.update_user(m.ADMIN, state="admin")
                await msg.answer(f"Kanal qo‘shildi: {chat}\n\nAgar kanal private bo‘lsa, format: -100... | https://t.me/+invite", reply_markup=menu(m))
                return
            if state.startswith("admin_sub_edit_"):
                try: idx = int(state.rsplit("_", 1)[1])
                except Exception: idx = -1
                channels = _load(m)
                if idx < 0 or idx >= len(channels):
                    m.update_user(m.ADMIN, state="admin"); await msg.answer("Kanal topilmadi.", reply_markup=menu(m)); return
                chat, url = _normalize(msg.text or "")
                if not chat:
                    await msg.answer("Kanal username yoki chat ID kiriting."); return
                channels[idx] = {"chat": chat, "url": url, "title": chat}
                _save(m, channels)
                m.update_user(m.ADMIN, state="admin")
                await msg.answer("Kanal tahrirlandi.", reply_markup=menu(m)); return
        await original(msg)

    _replace_text_handler(m, wrapped)

    @m.dp.message(Command("sub"))
    async def sub_command(msg: Message):
        if msg.from_user.id != m.ADMIN:
            return
        m.update_user(m.ADMIN, state="admin")
        await msg.answer("MAJBURIY OBUNA BOSHQARUVI", reply_markup=menu(m))

    @m.dp.callback_query(F.data == "sub_menu")
    async def sub_menu(q: CallbackQuery):
        if q.from_user.id != m.ADMIN: return
        await q.message.edit_text("MAJBURIY OBUNA BOSHQARUVI", reply_markup=menu(m)); await q.answer()

    @m.dp.callback_query(F.data == "sub_toggle")
    async def sub_toggle(q: CallbackQuery):
        if q.from_user.id != m.ADMIN: return
        new = not _enabled(m)
        m.set_setting("subscription_enabled", "1" if new else "0")
        await q.message.edit_text(f"Majburiy obuna {'YOQILDI' if new else 'O‘CHIRILDI'}.", reply_markup=menu(m)); await q.answer()

    @m.dp.callback_query(F.data == "sub_add")
    async def sub_add(q: CallbackQuery):
        if q.from_user.id != m.ADMIN: return
        m.update_user(m.ADMIN, state="admin_sub_add")
        await q.message.edit_text("Kanal username yoki chat ID yuboring.\n\nMisol: @kanal_nomi\nPrivate kanal: -1001234567890 | https://t.me/+invite", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Orqaga", callback_data="sub_menu")]])); await q.answer()

    @m.dp.callback_query(F.data == "sub_list")
    async def sub_list(q: CallbackQuery):
        if q.from_user.id != m.ADMIN: return
        channels = _load(m)
        text = "MAJBURIY KANALLAR\n\n" + ("\n".join(f"{i+1}. {x.get('chat')}" for i,x in enumerate(channels)) if channels else "Kanallar yo‘q.")
        await q.message.edit_text(text, reply_markup=menu(m)); await q.answer()

    @m.dp.callback_query(F.data == "sub_edit_list")
    async def sub_edit_list(q: CallbackQuery):
        if q.from_user.id != m.ADMIN: return
        await q.message.edit_text("Tahrirlash uchun kanalni tanlang:", reply_markup=channel_list_kb(m, "edit")); await q.answer()

    @m.dp.callback_query(F.data.startswith("sub_edit_"))
    async def sub_edit(q: CallbackQuery):
        if q.from_user.id != m.ADMIN: return
        idx = int(q.data.rsplit("_",1)[1]); channels = _load(m)
        if idx >= len(channels): await q.answer("Kanal topilmadi", show_alert=True); return
        m.update_user(m.ADMIN, state=f"admin_sub_edit_{idx}")
        await q.message.edit_text(f"Joriy kanal: {channels[idx].get('chat')}\n\nYangi kanal username/chat ID yuboring.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Orqaga", callback_data="sub_edit_list")]])); await q.answer()

    @m.dp.callback_query(F.data == "sub_delete_list")
    async def sub_delete_list(q: CallbackQuery):
        if q.from_user.id != m.ADMIN: return
        await q.message.edit_text("O‘chirish uchun kanalni tanlang:", reply_markup=channel_list_kb(m, "delete")); await q.answer()

    @m.dp.callback_query(F.data.startswith("sub_delete_"))
    async def sub_delete(q: CallbackQuery):
        if q.from_user.id != m.ADMIN: return
        idx = int(q.data.rsplit("_",1)[1]); channels = _load(m)
        if idx >= len(channels): await q.answer("Kanal topilmadi", show_alert=True); return
        removed = channels.pop(idx); _save(m, channels)
        await q.message.edit_text(f"O‘chirildi: {removed.get('chat')}", reply_markup=menu(m)); await q.answer()

    @m.dp.callback_query(F.data == "sub_check_config")
    async def sub_check_config(q: CallbackQuery):
        if q.from_user.id != m.ADMIN: return
        channels = _load(m); lines=[]
        for ch in channels:
            try:
                info = await m.bot.get_chat(ch.get("chat"))
                lines.append(f"OK — {ch.get('chat')} — {info.title or ''}")
            except Exception as exc:
                lines.append(f"XATO — {ch.get('chat')} — bot kanalni ko‘ra olmayapti")
        await q.message.edit_text("TEKSHIRUV\n\n" + ("\n".join(lines) if lines else "Kanallar yo‘q."), reply_markup=menu(m)); await q.answer()

    original_subscribed = m.subscribed

    async def subscribed(tid):
        if not _enabled(m):
            return True
        channels = _load(m)
        if not channels:
            return True
        for ch in channels:
            try:
                member = await m.bot.get_chat_member(ch.get("chat"), tid)
                if member.status not in ("member", "administrator", "creator"):
                    return False
            except Exception:
                return False
        return True

    m.subscribed = subscribed
    m.SUB_REQUIRED = False

    return True
