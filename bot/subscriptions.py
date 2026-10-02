import json
from aiogram import F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.dispatcher.event.bases import UNHANDLED


def install_subscription_admin(dp, bot, db, admin_id):
    get_setting = db.get_setting
    set_setting = db.set_setting

    def channels():
        raw = get_setting("subscription_channels", "")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return [str(x).strip() for x in data if str(x).strip()]
            except Exception:
                pass
        old = get_setting("subscription_channel", "")
        return [old] if old else []

    def normalize_channel(value):
        value = str(value).strip()
        if value.startswith("https://t.me/"):
            return "@" + value.rstrip("/").split("/")[-1]
        if not value.startswith("@"):
            value = "@" + value
        return value

    def save(items):
        clean=[]; seen=set()
        for x in items:
            x=normalize_channel(x)
            if x and x not in seen:
                clean.append(x); seen.add(x)
        set_setting("subscription_channels", json.dumps(clean, ensure_ascii=False))
        if clean:
            set_setting("subscription_channel", clean[0])
        return clean

    def required():
        return get_setting("subscription_required", "1").lower() in ("1","true","yes","on")

    def menu():
        items=channels()
        status="YOQILGAN" if required() else "O‘CHIRILGAN"
        rows=[
            [InlineKeyboardButton(text="ON", callback_data="sub_on"), InlineKeyboardButton(text="OFF", callback_data="sub_off")],
            [InlineKeyboardButton(text="Kanal qo‘shish", callback_data="sub_add"), InlineKeyboardButton(text="Kanal o‘chirish", callback_data="sub_remove")],
            [InlineKeyboardButton(text="Kanalni tahrirlash", callback_data="sub_edit")],
            [InlineKeyboardButton(text="Kanallar ro‘yxati", callback_data="sub_list")],
            [InlineKeyboardButton(text="Kanalni tekshirish", callback_data="sub_test")],
            [InlineKeyboardButton(text="Orqaga", callback_data="admin_home")],
        ]
        return f"MAJBURIY OBUNA\n\nHolat: {status}\nKanallar: {len(items)}", InlineKeyboardMarkup(inline_keyboard=rows)

    def sub_keyboard():
        items=channels()
        rows=[]
        for i,ch in enumerate(items,1):
            rows.append([InlineKeyboardButton(text=f"{i}. {ch} — OBUNA", url=f"https://t.me/{ch.lstrip('@')}")])
        rows.append([InlineKeyboardButton(text="OBUNANI TEKSHIRISH", callback_data="check_sub")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def check(tid):
        if not required(): return True
        items=channels()
        if not items: return True
        for channel in items:
            try:
                member=await bot.get_chat_member(channel, tid)
                if member.status not in ("member","administrator","creator"):
                    return False
            except Exception:
                return False
        return True

    async def show_menu(target):
        text,markup=menu()
        await target.answer(text, reply_markup=markup)

    @dp.callback_query(F.data == "sub_on")
    async def sub_on(q: CallbackQuery):
        if q.from_user.id != admin_id: return await q.answer("Ruxsat yo‘q", show_alert=True)
        set_setting("subscription_required","1"); await q.answer("Majburiy obuna yoqildi"); await show_menu(q.message)

    @dp.callback_query(F.data == "sub_off")
    async def sub_off(q: CallbackQuery):
        if q.from_user.id != admin_id: return await q.answer("Ruxsat yo‘q", show_alert=True)
        set_setting("subscription_required","0"); await q.answer("Majburiy obuna o‘chirildi"); await show_menu(q.message)

    @dp.callback_query(F.data == "sub_menu")
    async def sub_menu(q: CallbackQuery):
        if q.from_user.id != admin_id: return await q.answer("Ruxsat yo‘q", show_alert=True)
        text,markup=menu(); await q.message.edit_text(text,reply_markup=markup); await q.answer()

    @dp.callback_query(F.data == "sub_list")
    async def sub_list(q: CallbackQuery):
        if q.from_user.id != admin_id: return await q.answer("Ruxsat yo‘q", show_alert=True)
        items=channels()
        body="KANALLAR\n\n"+("\n".join(f"{i}. {x}" for i,x in enumerate(items,1)) if items else "Hozircha kanal qo‘shilmagan.")
        await q.message.edit_text(body,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Orqaga",callback_data="sub_menu")]])); await q.answer()

    @dp.callback_query(F.data == "sub_add")
    async def sub_add(q: CallbackQuery):
        if q.from_user.id != admin_id: return
        db.update_user(admin_id,state="admin_sub_add")
        await q.message.edit_text("Kanal username yoki t.me linkini yuboring.\nMasalan: @Rustambek_oqiw_orayi",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Orqaga",callback_data="sub_menu")]])); await q.answer()

    @dp.callback_query(F.data == "sub_remove")
    async def sub_remove(q: CallbackQuery):
        if q.from_user.id != admin_id: return
        db.update_user(admin_id,state="admin_sub_remove")
        await q.message.edit_text("O‘chiriladigan kanal username yoki linkini yuboring.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Orqaga",callback_data="sub_menu")]])); await q.answer()

    @dp.callback_query(F.data == "sub_edit")
    async def sub_edit(q: CallbackQuery):
        if q.from_user.id != admin_id: return
        db.update_user(admin_id,state="admin_sub_edit")
        await q.message.edit_text("Tahrirlash formati:\n@eski_kanal | @yangi_kanal",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Orqaga",callback_data="sub_menu")]])); await q.answer()

    @dp.callback_query(F.data == "sub_test")
    async def sub_test(q: CallbackQuery):
        if q.from_user.id != admin_id: return
        lines=[]
        for ch in channels():
            try:
                me=await bot.get_chat_member(ch,admin_id); lines.append(f"{ch}: {me.status}")
            except Exception:
                lines.append(f"{ch}: BOT HUQUQI YOKI KANAL TOPILMADI")
        await q.message.edit_text("KANAL TEKSHIRUVI\n\n"+("\n".join(lines) if lines else "Kanal yo‘q."),reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Orqaga",callback_data="sub_menu")]])); await q.answer()

    async def admin_text_handler(message: Message):
        if message.from_user.id != admin_id or not message.text:
            return UNHANDLED
        value=message.text.strip()
        u=db.get_user(admin_id); state=u["state"] if u else ""
        if value == "Majburiy obuna" and state in ("admin",""):
            db.update_user(admin_id,state="admin")
            await show_menu(message)
            return True
        if state == "admin_sub_add":
            save(channels()+[value]); db.update_user(admin_id,state="admin"); await show_menu(message); return True
        if state == "admin_sub_remove":
            target=normalize_channel(value); save([x for x in channels() if x != target]); db.update_user(admin_id,state="admin"); await show_menu(message); return True
        if state == "admin_sub_edit":
            parts=[x.strip() for x in value.split("|",1)]
            if len(parts)!=2:
                await message.answer("Format: @eski_kanal | @yangi_kanal"); return True
            old,new=normalize_channel(parts[0]),normalize_channel(parts[1])
            save([new if x==old else x for x in channels()]); db.update_user(admin_id,state="admin"); await show_menu(message); return True
        return UNHANDLED

    dp.message.register(admin_text_handler, F.from_user.id == admin_id)
    try:
        h=dp.message.handlers.pop(); dp.message.handlers.insert(0,h)
    except Exception:
        pass
    return check, sub_keyboard
