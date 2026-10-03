import os
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher.event.bases import SkipHandler
from .db import ensure_user, get_user, all_registered_users, is_premium, set_tier, update_user

ADMIN = int(os.getenv("ADMIN_CHAT_ID", "8379731556"))

def user_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Profilim"), KeyboardButton(text="Tariflar")],
        [KeyboardButton(text="Testni boshlash"), KeyboardButton(text="Mening natijam")],
        [KeyboardButton(text="Userlar ro‘yxati"), KeyboardButton(text="Yordam")],
    ], resize_keyboard=True, is_persistent=True)

def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Tariflar haqida", callback_data="pf_tariffs")],
        [InlineKeyboardButton(text="Userlar ro‘yxati", callback_data="pf_users")],
    ])

def tariff_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Default", callback_data="pf_default")],
        [InlineKeyboardButton(text="Premium 💠", callback_data="pf_premium")],
        [InlineKeyboardButton(text="Premium olish", callback_data="pf_buy")],
    ])

def admin_tariff_list():
    users = all_registered_users(); rows=[]
    for i,u in enumerate(users,1):
        mark="💠 " if str(u["tier"] or "default")=="premium" else ""
        name=(u["full_name"] or "Ro‘yxatdan o‘tgan user")[:22]
        rows.append([InlineKeyboardButton(text=f"{i}. {mark}{name} · {u['telegram_id']}",callback_data=f"tf_user:{u['telegram_id']}")])
    rows.append([InlineKeyboardButton(text="Yangilash",callback_data="tf_list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def profile_text(u):
    tier="Premium 💠" if str(u["tier"] or "default")=="premium" else "Default"
    return f"PROFILIM\n\nIsm-familiya: {u['full_name'] or '—'}\nTelefon: {u['phone'] or '—'}\nTelegram ID: {u['telegram_id']}\nTarif: {tier}"

def tariff_text():
    return ("TARIFLAR\n\n1. DEFAULT\n• Oddiy test qatnashchisi\n• Reklamalar mavjud\n• Oddiy userlar ro‘yxati\n• Boshqa userga Telegram orqali yozish yopiq\n\n2. PREMIUM 💠\n• Reklamalarsiz foydalanish\n• Profil yonida 💠 premium nishon\n• Kengaytirilgan shaxsiy statistika\n• Xato ishlangan savollarni qayta ko‘rish\n• Userlar ro‘yxatidan Telegram profiliga yozish\n\nPremium tarifni olish uchun administratorga murojaat qiling.")

def register(dp, bot, webapp_url):
    r=Router(name="profile_features")

    @r.message(F.text == "Profilim")
    async def profile(m:Message):
        u=get_user(m.from_user.id) or ensure_user(m.from_user.id)
        if not u["code_ok"]: await m.answer("Avval ro‘yxatdan o‘tib, kirish kodini tasdiqlang."); return
        await m.answer(profile_text(u),reply_markup=profile_kb())

    @r.message(F.text == "Tariflar")
    async def tariffs(m:Message):
        if m.from_user.id==ADMIN:
            await m.answer("TARIFLAR BOSHQARUVI\n\nBarcha /start bosgan userlar:",reply_markup=admin_tariff_list()); return
        u=get_user(m.from_user.id) or ensure_user(m.from_user.id)
        if not u["code_ok"]: await m.answer("Avval ro‘yxatdan o‘tib, kirish kodini tasdiqlang."); return
        await m.answer(tariff_text(),reply_markup=tariff_kb())

    @r.message(F.text == "Testni boshlash")
    async def test_start(m:Message):
        u=get_user(m.from_user.id) or ensure_user(m.from_user.id)
        if not u["code_ok"]: await m.answer("Avval ro‘yxatdan o‘ting."); return
        await m.answer("Testni Mini App orqali boshlang:",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="TESTNI BOSHLASH",web_app=__import__('aiogram').types.WebAppInfo(url=webapp_url))]]))

    @r.message(F.text == "Mening natijam")
    async def result(m:Message):
        u=get_user(m.from_user.id) or ensure_user(m.from_user.id)
        if not u["code_ok"]: await m.answer("Avval ro‘yxatdan o‘ting."); return
        await m.answer(f"NATIJAM\n\nBall: {float(u['score'] or 0):.2f}\nBaho: {u['grade'] or 'Hali yakunlanmagan'}")

    @r.message(F.text == "Userlar ro‘yxati")
    async def users(m:Message):
        u=get_user(m.from_user.id) or ensure_user(m.from_user.id)
        if not u["code_ok"]: await m.answer("Avval ro‘yxatdan o‘ting."); return
        people=all_registered_users(); lines=["USERLAR RO‘YXATI","",f"Jami: {len(people)}",""]
        for i,x in enumerate(people,1): lines.append(f"{i}. {'💠 ' if str(x['tier'] or 'default')=='premium' else ''}{x['full_name'] or 'Ismsiz'}")
        lines.append("\nPremium userlar uchun Telegram profiliga yozish imkoniyati ochiladi." if is_premium(m.from_user.id) else "\nTelegram orqali boshqa userga yozish Premium tarifda ochiladi.")
        await m.answer("\n".join(lines)[:4000])

    @r.message(F.text == "Yordam")
    async def help_(m:Message): await m.answer("Yordam uchun administratorga murojaat qiling.")

    @r.callback_query(F.data == "pf_tariffs")
    async def pf_tariffs(q:CallbackQuery): await q.message.answer(tariff_text(),reply_markup=tariff_kb()); await q.answer()

    @r.callback_query(F.data == "pf_users")
    async def pf_users(q:CallbackQuery):
        people=all_registered_users(); text="USERLAR RO‘YXATI\n\n"+"\n".join(f"{i}. {'💠 ' if str(u['tier'] or 'default')=='premium' else ''}{u['full_name'] or 'Ismsiz'}" for i,u in enumerate(people,1))
        await q.message.answer(text[:4000]); await q.answer()

    @r.callback_query(F.data == "pf_default")
    async def pf_default(q:CallbackQuery): await q.answer("Default — oddiy user tarifi.",show_alert=True)

    @r.callback_query(F.data == "pf_premium")
    async def pf_premium(q:CallbackQuery): await q.answer("Premium 💠 — reklamasiz + kengaytirilgan statistika + xato savollar.",show_alert=True)

    @r.callback_query(F.data == "pf_buy")
    async def pf_buy(q:CallbackQuery):
        await q.message.answer("Premium 💠 tarifini olish uchun administratorga yozing.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ADMINISTRATORGA YOZISH",url=f"tg://user?id={ADMIN}")]])); await q.answer()

    @r.callback_query(F.data == "tf_list")
    async def tf_list(q:CallbackQuery):
        if q.from_user.id!=ADMIN: await q.answer("Ruxsat yo‘q",show_alert=True); return
        await q.message.edit_text("TARIFLAR BOSHQARUVI\n\nBarcha /start bosgan userlar:",reply_markup=admin_tariff_list()); await q.answer()

    @r.callback_query(F.data.startswith("tf_user:"))
    async def tf_user(q:CallbackQuery):
        if q.from_user.id!=ADMIN: await q.answer("Ruxsat yo‘q",show_alert=True); return
        uid=int(q.data.split(":",1)[1]); u=get_user(uid)
        if not u: await q.answer("User topilmadi",show_alert=True); return
        label="Premium 💠" if str(u["tier"] or "default")=="premium" else "Default"
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Premium 💠 berish",callback_data=f"tf_set:premium:{uid}")],[InlineKeyboardButton(text="Default qilish",callback_data=f"tf_set:default:{uid}")],[InlineKeyboardButton(text="Orqaga",callback_data="tf_list")]])
        await q.message.edit_text(f"USER TARIFI\n\nIsm: {u['full_name'] or '—'}\nTelefon: {u['phone'] or '—'}\nID: {uid}\nHozirgi tarif: {label}\n\nTanlang:",reply_markup=kb); await q.answer()

    @r.callback_query(F.data.startswith("tf_set:"))
    async def tf_set(q:CallbackQuery):
        if q.from_user.id!=ADMIN: await q.answer("Ruxsat yo‘q",show_alert=True); return
        _,tier,uid_s=q.data.split(":"); uid=int(uid_s); u=get_user(uid)
        if not u: await q.answer("User topilmadi",show_alert=True); return
        label="Premium 💠" if tier=="premium" else "Default"
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="TASDIQLASH",callback_data=f"tf_confirm:{tier}:{uid}")],[InlineKeyboardButton(text="Bekor qilish",callback_data=f"tf_user:{uid}")]])
        await q.message.edit_text(f"TASDIQLASH\n\n{u['full_name'] or 'Ismsiz'}\nID: {uid}\n\n{label} tarifini berish/tayinlashni tasdiqlaysizmi?",reply_markup=kb); await q.answer()

    @r.callback_query(F.data.startswith("tf_confirm:"))
    async def tf_confirm(q:CallbackQuery):
        if q.from_user.id!=ADMIN: await q.answer("Ruxsat yo‘q",show_alert=True); return
        _,tier,uid_s=q.data.split(":"); uid=int(uid_s); u=get_user(uid)
        if not u: await q.answer("User topilmadi",show_alert=True); return
        set_tier(uid,tier,ADMIN); label="Premium 💠" if tier=="premium" else "Default"
        sent=False
        for attempt in range(3):
            try:
                await bot.send_message(uid,f"Tarifingiz yangilandi: {label}.")
                sent=True
                break
            except Exception as e:
                import asyncio
                if attempt<2:
                    await asyncio.sleep(1.5*(attempt+1))
                else:
                    import logging
                    logging.getLogger("nur-oqiw").warning("Tariff notification to %s failed: %s",uid,e)
        await q.message.edit_text(f"SAQLANDI\n\n{u['full_name'] or 'Ismsiz'}\nID: {uid}\nTarif: {label}",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Tariflar ro‘yxati",callback_data="tf_list")]])); await q.answer("Tarif saqlandi")

    # This handler catches the registration code before main.py's generic text handler.
    # For every other text it yields control to the original registration/admin flow.
    @r.message(F.text)
    async def profile_fallback(m:Message):
        u=get_user(m.from_user.id) or ensure_user(m.from_user.id)
        if m.from_user.id!=ADMIN and (u["state"] or "") == "code":
            from .db import get_setting
            expected=get_setting("access_code",os.getenv("ACCESS_CODE","0924"))
            if m.text.strip()==str(expected):
                update_user(m.from_user.id,code_ok=1,state="ready")
                await m.answer("🎉 Ro‘yxatdan o‘tish tugadi!\n\nProfilingiz saqlandi. Endi botdan istalgan vaqtda foydalanishingiz mumkin.",reply_markup=user_menu())
                return
        raise SkipHandler

    dp.include_router(r)
