"""Private, bot-mediated student to administrator support correspondence."""
import json
import time
from aiogram import F
from aiogram.types import (
    KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup,
)

STATES = frozenset(('support_name', 'support_message', 'support_review'))


def keyboard(*rows):
    # No style here: these are always neutral reply-keyboard controls.
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
    )


def draft_key(uid):
    return 'support_draft_v1_' + str(int(uid))


def draft(db, uid):
    try:
        data = json.loads(db.get_setting(draft_key(uid), '{}') or '{}')
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def active(db, uid):
    u = db.get_user(uid)
    return bool(u and str(u['state'] or '') in STATES)


def install(dp, bot, db, admin_id, user_keyboard, admin_keyboard, mock_user_keyboard):
    def restore(uid):
        current = draft(db, uid)
        previous = str(current.get('previous_state') or 'code')
        if previous in STATES or previous == 'support_reply':
            previous = 'ready' if (db.get_user(uid) or {})['test_id'] else 'code'
        db.update_user(uid, state=previous)
        # Remove the message and personal name from persistent draft storage.
        db.set_setting(draft_key(uid), '{}')
        return mock_user_keyboard() if db.get_setting('mock_menu_' + str(uid), '') == 'user' else user_keyboard()

    @dp.message(F.text == 'Yordam', F.from_user.id != admin_id)
    async def support_begin(m):
        if m.chat.type != 'private':
            return
        uid = m.from_user.id
        u = db.ensure_user(uid)
        previous = str(u['state'] or 'code')
        if previous in STATES:
            previous = str(draft(db, uid).get('previous_state') or 'code')
        db.set_setting(draft_key(uid), json.dumps({
            'previous_state': previous,
            'name': '',
            'message': '',
        }, ensure_ascii=False))
        db.update_user(uid, state='support_name')
        await m.answer(
            'Adminga murojaat yuborish uchun avval ism-familiyangizni yozing.',
            reply_markup=keyboard(['Bekor qilish']),
        )

    @dp.message(lambda m: bool(m.from_user) and m.from_user.id != admin_id and active(db, m.from_user.id))
    async def support_step(m):
        if m.chat.type != 'private':
            return
        uid = m.from_user.id
        state = str(db.get_user(uid)['state'] or '')
        raw = (m.text or '').strip()

        if raw in ('Bekor qilish', 'Orqaga qaytish', '/cancel'):
            previous_keyboard = restore(uid)
            return await m.answer('Murojaat bekor qilindi.', reply_markup=previous_keyboard)

        item = draft(db, uid)
        if state == 'support_name':
            if not 3 <= len(raw) <= 100 or raw.startswith('/') or raw in ('Yuborish', 'Qayta yozish'):
                return await m.answer('Ism va familiyangizni 3–100 belgi bilan kiriting.')
            item['name'] = raw
            item['message'] = ''
            db.set_setting(draft_key(uid), json.dumps(item, ensure_ascii=False))
            db.update_user(uid, state='support_message')
            return await m.answer(
                'Endi adminga murojaatingizni yozing. Savol yoki muammoni batafsil tushuntiring.',
                reply_markup=keyboard(['Bekor qilish']),
            )

        if state == 'support_message':
            if not 5 <= len(raw) <= 2700 or raw.startswith('/'):
                return await m.answer('Murojaat matnini 5–2700 belgi oralig‘ida yozing.')
            item['message'] = raw
            db.set_setting(draft_key(uid), json.dumps(item, ensure_ascii=False))
            db.update_user(uid, state='support_review')
            return await m.answer(
                'Murojaatingiz tayyor.\n\n'
                'Ism-familiya: ' + item['name'] + '\n'
                'Xabar: ' + raw[:1000] + ('…' if len(raw) > 1000 else '') + '\n\n'
                'Yuborishni tasdiqlang.',
                reply_markup=keyboard(['Yuborish', 'Qayta yozish'], ['Bekor qilish']),
            )

        if state == 'support_review':
            if raw == 'Qayta yozish':
                item['message'] = ''
                db.set_setting(draft_key(uid), json.dumps(item, ensure_ascii=False))
                db.update_user(uid, state='support_message')
                return await m.answer('Murojaatni qayta yozing.', reply_markup=keyboard(['Bekor qilish']))
            if raw != 'Yuborish':
                return await m.answer('Yuborish, Qayta yozish yoki Bekor qilish tugmasini tanlang.')
            if not item.get('name') or not item.get('message'):
                db.update_user(uid, state='support_name')
                return await m.answer('Ism-familiyangizni qayta kiriting.', reply_markup=keyboard(['Bekor qilish']))
            last_key = 'support_last_sent_v1_' + str(uid)
            try:
                last = float(db.get_setting(last_key, '0') or 0)
            except (TypeError, ValueError):
                last = 0
            if time.time() - last < 45:
                return await m.answer('Yangi murojaat yuborishdan avval biroz kuting.')
            user = m.from_user
            username = '@' + user.username if user.username else 'ko‘rsatilmagan'
            message = (
                'NUR OQIW ORAYI — YANGI MUROJAAT\n\n'
                'Ism-familiya: ' + item['name'] + '\n'
                'Telegram: ' + username + '\n'
                'User ID: ' + str(uid) + '\n\n'
                'Xabar:\n' + item['message']
            )
            actions = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text='JAVOB YOZISH', callback_data='support_reply:' + str(uid)),
            ]])
            try:
                await bot.send_message(admin_id, message, reply_markup=actions)
            except Exception:
                return await m.answer('Hozir xabarni yuborib bo‘lmadi. Keyinroq qayta urinib ko‘ring.')
            db.set_setting(last_key, str(time.time()))
            previous_keyboard = restore(uid)
            return await m.answer(
                'Murojaatingiz adminga yuborildi. Javob shu bot orqali keladi.',
                reply_markup=previous_keyboard,
            )

    @dp.callback_query(F.data.startswith('support_reply:'))
    async def reply_start(q):
        if not q.from_user or q.from_user.id != admin_id:
            return await q.answer('Ruxsat yo‘q.', show_alert=True)
        try:
            uid = int((q.data or '').split(':', 1)[1])
            if uid <= 0:
                raise ValueError
        except (TypeError, ValueError, IndexError):
            return await q.answer('Qabul qiluvchi topilmadi.', show_alert=True)
        db.set_setting('support_reply_target_v1', str(uid))
        db.update_user(admin_id, state='support_reply')
        await q.answer()
        await q.message.answer(
            'Foydalanuvchiga javob matnini yozing.',
            reply_markup=keyboard(['Bekor qilish']),
        )

    @dp.message(lambda m: bool(m.from_user) and m.from_user.id == admin_id and
                str((db.get_user(admin_id) or {})['state'] or '') == 'support_reply')
    async def reply_send(m):
        if m.chat.type != 'private':
            return
        raw = (m.text or '').strip()
        if raw in ('Bekor qilish', '/cancel'):
            db.update_user(admin_id, state='admin')
            db.set_setting('support_reply_target_v1', '')
            return await m.answer('Javob bekor qilindi.', reply_markup=admin_keyboard())
        if not 1 <= len(raw) <= 3000:
            return await m.answer('Javob matnini yozing (3000 belgigacha).')
        try:
            uid = int(db.get_setting('support_reply_target_v1', '') or 0)
            if uid <= 0:
                raise ValueError
            await bot.send_message(uid, 'ADMIN JAVOBI\n\n' + raw)
        except Exception:
            return await m.answer('Javobni yuborib bo‘lmadi. Tekshirib qayta yuboring yoki bekor qiling.')
        db.update_user(admin_id, state='admin')
        db.set_setting('support_reply_target_v1', '')
        await m.answer('Javob foydalanuvchiga yuborildi.', reply_markup=admin_keyboard())
