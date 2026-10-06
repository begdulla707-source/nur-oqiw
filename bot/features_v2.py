import os,json,secrets
from datetime import datetime,time,timedelta
from aiogram import Router,F
from aiogram.filters import CommandStart
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo,FSInputFile,ReplyKeyboardMarkup,KeyboardButton,ReplyKeyboardRemove
from fastapi.responses import JSONResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
from reportlab.lib.styles import getSampleStyleSheet
from . import db

CORE=None
ADMIN=0
APP=None
TZ=None
BOT=None
WEBAPP=''

def norm(v):return ' '.join(str(v or '').strip().casefold().split())
def grade(score):
    s=float(score);return 'A+' if s>=90 else 'A' if s>=80 else 'B' if s>=70 else 'C' if s>=60 else 'D' if s>=50 else 'F'
def user_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Profilim'),KeyboardButton(text='Tariflar')],[KeyboardButton(text='Testni boshlash'),KeyboardButton(text='Mening natijam')],[KeyboardButton(text='Userlar ro‘yxati'),KeyboardButton(text='Yordam')]],resize_keyboard=True,is_persistent=True)
def admin_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Test sozlamalari'),KeyboardButton(text='Ishtirokchilar')],[KeyboardButton(text='PDF natijalar'),KeyboardButton(text='Tariflar')]],resize_keyboard=True,is_persistent=True)
def test_kb(tid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Savollar',callback_data=f't2_q:{tid}'),InlineKeyboardButton(text='Yangi savol',callback_data=f't2_add:{tid}')],
        [InlineKeyboardButton(text='Oddiy variant',callback_data=f't2_choice:{tid}'),InlineKeyboardButton(text='Yozma variant',callback_data=f't2_written:{tid}')],
        [InlineKeyboardButton(text='To‘g‘ri javoblar',callback_data=f't2_keys:{tid}')],
        [InlineKeyboardButton(text='Natijalar',callback_data=f't2_results:{tid}'),InlineKeyboardButton(text='PDF',callback_data=f't2_pdf:{tid}')],
        [InlineKeyboardButton(text='Guruhga yuborish',callback_data=f't2_group:{tid}'),InlineKeyboardButton(text='Mini App link',callback_data=f't2_link:{tid}')],
        [InlineKeyboardButton(text='OCHISH',callback_data=f't2_open:{tid}'),InlineKeyboardButton(text='YOPISH',callback_data=f't2_close:{tid}')],
        [InlineKeyboardButton(text='Orqaga',callback_data='t2_list')]
    ])
def tests_kb():
    rows=[]
    for t in db.all_tests():
        rows.append([InlineKeyboardButton(text=f"{t['name'][:24]} · {t['code']}",callback_data=f't2_pick:{t["test_id"]}')])
    rows.append([InlineKeyboardButton(text='YANGI TEST',callback_data='t2_new')])
    return InlineKeyboardMarkup(inline_keyboard=rows)
def question_type_kb(tid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='ODDIY VARIANT',callback_data=f't2_choice:{tid}')],
        [InlineKeyboardButton(text='YOZMA VARIANT',callback_data=f't2_written:{tid}')],
        [InlineKeyboardButton(text='Orqaga',callback_data=f't2_pick:{tid}')]
    ])
def answer_kb(tid,num):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='A',callback_data=f't2_ans:{tid}:{num}:A'),InlineKeyboardButton(text='B',callback_data=f't2_ans:{tid}:{num}:B'),InlineKeyboardButton(text='C',callback_data=f't2_ans:{tid}:{num}:C'),InlineKeyboardButton(text='D',callback_data=f't2_ans:{tid}:{num}:D')]])
def admin_draft():
    try:return json.loads(db.get_setting('admin_question_draft','{}') or '{}')
    except:return {}
def save_draft(d):db.set_setting('admin_question_draft',json.dumps(d,ensure_ascii=False))
def clear_draft():db.set_setting('admin_question_draft','{}')
def set_admin_state(state):db.update_user(ADMIN,state=state)
def current_admin():return db.get_user(ADMIN) or db.ensure_user(ADMIN)
def open_test(t):
    if not t or not int(t['active']):return False
    mode=str(t['mode'] or 'closed')
    if mode=='open':return True
    if mode=='closed':return False
    now=datetime.now(TZ).time();return time.fromisoformat(t['start_time'])<=now<time.fromisoformat(t['end_time'])
def expired(a,t):
    if not a or not a['started_at']:return False
    st=datetime.fromisoformat(a['started_at']);close=datetime.combine(st.date(),time.fromisoformat(t['end_time']),tzinfo=TZ)
    return datetime.now(TZ)>=min(st+timedelta(hours=1),close)
def score_for(t,answers):
    qs=db.questions_for_test(t['test_id']);correct=sum(1 for q in qs if norm(answers.get(str(q['number']),''))==norm(q['answer']));return round(correct/len(qs)*100,2) if qs else 0

def register(core,dp,bot,webapp_url):
    global CORE,ADMIN,APP,TZ,BOT,WEBAPP
    CORE=core;ADMIN=core.ADMIN;APP=core.app;TZ=core.TZ;BOT=bot;WEBAPP=webapp_url
    r=Router(name='features_v2')

    @APP.get('/api/test/state')
    async def api_state(request):
        raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or request.query_params.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;code=request.query_params.get('code','').strip();t=db.get_test_by_code(code) if code else (db.get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u:return {'ok':False,'error':'not_authorized'}
        if not t:return {'ok':False,'error':'test_not_found'}
        if code and u['test_id']!=t['test_id']:db.update_user(tid,test_id=t['test_id'],code_ok=1,state='ready');u=db.get_user(tid)
        if not u['full_name'] or not u['phone']:return {'ok':False,'error':'registration_required','test_name':t['name'],'test_code':t['code']}
        a=db.ensure_attempt(t['test_id'],tid)
        if a['submitted']:return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade'],'full_name':u['full_name'] or '','test_name':t['name']}
        if not a['started_at']:
            if not open_test(t):return {'ok':False,'error':'test_closed','start':t['start_time'],'end':t['end_time'],'test_name':t['name']}
            db.update_attempt(a['attempt_id'],started_at=datetime.now(TZ).isoformat(),status='active');a=db.get_attempt(t['test_id'],tid)
        if expired(a,t):return {'ok':False,'error':'test_closed','test_name':t['name']}
        answers=json.loads(a['answers_json'] or '{}');st=datetime.fromisoformat(a['started_at']);close=datetime.combine(st.date(),time.fromisoformat(t['end_time']),tzinfo=TZ)
        return {'ok':True,'full_name':u['full_name'] or '','answers':answers,'ends_at':close.isoformat(),'test_name':t['name'],'test_code':t['code'],'total_questions':len(db.questions_for_test(t['test_id']))}

    @APP.get('/api/test/questions')
    async def api_questions(request):
        raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or request.query_params.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;code=request.query_params.get('code','').strip();t=db.get_test_by_code(code) if code else (db.get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u or not t:return JSONResponse({'ok':False,'error':'not_authorized'},status_code=401)
        return {'ok':True,'questions':[{'id':q['number'],'question':q['question'],'options':json.loads(q['options_json'] or '[]'),'kind':q['kind'],'image_url':q['image_url']} for q in db.questions_for_test(t['test_id'])]}

    @APP.post('/api/test/answer')
    async def api_answer(p:dict):
        tid=CORE.telegram_user(p.get('initData',''));u=db.get_user(tid) if tid else None;code=str(p.get('code','')).strip();t=db.get_test_by_code(code) if code else (db.get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
        a=db.ensure_attempt(t['test_id'],tid)
        if a['submitted']:return {'ok':False,'error':'already_submitted'}
        if not open_test(t) or expired(a,t):return {'ok':False,'error':'test_closed'}
        q=db.get_question_for_test(t['test_id'],p.get('question_id'))
        if not q:return {'ok':False,'error':'question_not_found'}
        answers=json.loads(a['answers_json'] or '{}');key=str(q['number'])
        if key in answers:return {'ok':False,'error':'answer_locked','correct':norm(answers[key])==norm(q['answer'])}
        ans=str(p.get('answer','')).strip();answers[key]=ans;db.save_attempt_answers(a['attempt_id'],answers);return {'ok':True,'correct':norm(ans)==norm(q['answer']),'number':q['number']}

    @APP.post('/api/test/finish')
    async def api_finish(p:dict):
        tid=CORE.telegram_user(p.get('initData',''));u=db.get_user(tid) if tid else None;code=str(p.get('code','')).strip();t=db.get_test_by_code(code) if code else (db.get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
        a=db.ensure_attempt(t['test_id'],tid)
        if a['submitted']:return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade']}
        if not open_test(t) and not expired(a,t):return {'ok':False,'error':'test_closed'}
        answers=json.loads(a['answers_json'] or '{}');sc=score_for(t,answers);gr=grade(sc);db.update_attempt(a['attempt_id'],score=sc,grade=gr,submitted=1,status='submitted',finished_at=datetime.now(TZ).isoformat());return {'ok':True,'score':sc,'grade':gr,'full_name':u['full_name'] or '','test_name':t['name']}

    @APP.get('/api/admin/tests')
    async def api_admin_tests(request):
        key=os.getenv('ADMIN_API_KEY','');
        if not key or request.headers.get('X-Admin-Key','')!=key:return JSONResponse({'ok':False,'error':'forbidden'},status_code=403)
        return {'ok':True,'tests':[{'test_id':t['test_id'],'code':t['code'],'name':t['name'],'mode':t['mode'],'active':t['active'],'questions':len(db.questions_for_test(t['test_id'])),'participants':len(db.all_attempts_for_test(t['test_id']))} for t in db.all_tests()]}

    @r.message(CommandStart(deep_link=True))
    async def deep(m:Message,command):
        t=db.get_test_by_code((command.args or '').strip())
        if not t:return
        u=db.ensure_user(m.from_user.id);db.update_user(m.from_user.id,test_id=t['test_id'],code_ok=1,state='ready' if u['full_name'] and u['phone'] else ('name' if not u['full_name'] else 'phone'));db.ensure_attempt(t['test_id'],m.from_user.id)
        u=db.get_user(m.from_user.id)
        if not u['full_name']:return await m.answer(f"{t['name']}\n\nIsm, Familiyangizni kiriting:")
        if not u['phone']:return await m.answer('Telefon raqamingizni yuboring:')
        await m.answer(f"{t['name']}\n\nKirish kodi: {t['code']}\n\nTest tayyor.",reply_markup=user_menu())

    @r.message(F.text=='Profilim')
    async def profile(m:Message):
        u=db.get_user(m.from_user.id) or db.ensure_user(m.from_user.id);t=db.get_test(u['test_id']) if u['test_id'] else None;a=db.get_attempt(t['test_id'],m.from_user.id) if t else None;result=(f"{float(a['score'] or 0):.2f} ball · {a['grade'] or '—'}" if a and a['submitted'] else 'Yakunlanmagan')
        await m.answer(f"PROFILIM\n\nIsm-familiya: {u['full_name'] or '—'}\nTelefon: {u['phone'] or '—'}\nTest: {t['name'] if t else 'Tanlanmagan'}\nKod: {t['code'] if t else '—'}\nNatija: {result}")
    @r.message(F.text=='Tariflar')
    async def tariffs(m:Message):await m.answer('TARIFLAR\n\nDEFAULT\nOddiy test qatnashchisi.\n\nPREMIUM\nKengaytirilgan statistika.')
    @r.message(F.text=='Testni boshlash')
    async def begin(m:Message):
        u=db.get_user(m.from_user.id);t=db.get_test(u['test_id']) if u and u['test_id'] else None
        if not t:return await m.answer('Avval test kodini kiriting.')
        url=f'{WEBAPP.rstrip("/")}/test?code={t["code"]}';await m.answer(f"{t['name']}\n\nTestni boshlash:",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',web_app=WebAppInfo(url=url))]]))
    @r.message(F.text=='Mening natijam')
    async def result(m:Message):
        u=db.get_user(m.from_user.id);t=db.get_test(u['test_id']) if u and u['test_id'] else None;a=db.get_attempt(t['test_id'],m.from_user.id) if t else None
        if not a:return await m.answer('Hali test tanlanmagan.')
        await m.answer(f"NATIJAM\n\nTest: {t['name']}\nBall: {float(a['score'] or 0):.2f}\nBaho: {a['grade'] or 'Hali yakunlanmagan'}")
    @r.message(F.text=='Yordam')
    async def help_(m:Message):await m.answer('Guruhdagi test xabaridagi TESTNI BOSHLASH tugmasini bosing yoki botga test kodini yuboring.')
    @r.message(F.text=='Userlar ro‘yxati')
    async def users(m:Message):
        us=db.all_registered_users();await m.answer('\n'.join(f"{i}. {u['full_name'] or 'Ismsiz'} · {u['telegram_id']}" for i,u in enumerate(us[:100],1)) or 'User yo‘q.')

    @r.message(F.from_user.id==ADMIN)
    async def admin_text(m:Message):
        u=current_admin();st=u['state'] or 'admin';text=(m.text or '').strip()
        if text=='Test sozlamalari' or text=='PDF natijalar' or text=='Ishtirokchilar':return await m.answer('TESTLAR',reply_markup=tests_kb())
        if text=='Tariflar':return await m.answer('TARIFLAR BOSHQARUVI',reply_markup=admin_menu())
        if st=='new_code':
            if not text or len(text)>32 or ' ' in text:return await m.answer('Kodni bitta so‘z sifatida kiriting. Masalan: MAT2026')
            if db.get_test_by_code(text):return await m.answer('Bu kod allaqachon mavjud. Boshqa kod tanlang.')
            save_draft({'code':text});set_admin_state('new_name');return await m.answer('Test nomini kiriting:')
        if st=='new_name':
            d=admin_draft();d['name']=text;save_draft(d);set_admin_state('new_time');return await m.answer('Vaqtni kiriting: 08:30-09:30\nYoki test doim OCHIQ bo‘lsa: OPEN')
        if st=='new_time':
            d=admin_draft()
            try:
                if text.upper()=='OPEN':start,end='00:00','23:59'
                else:start,end=[x.strip() for x in text.split('-',1)];time.fromisoformat(start);time.fromisoformat(end)
                t=db.create_test(d['name'],d['code'],start,end,'closed');clear_draft();set_admin_state('admin');return await m.answer(f"YANGI TEST YARATILDI\n\n{t['name']}\nKirish kodi: {t['code']}",reply_markup=test_kb(t['test_id']))
            except Exception:return await m.answer('Format xato. Masalan: 08:30-09:30')
        if st.startswith('choice_num:') or st.startswith('choice_question:') or st.startswith('choice_a:') or st.startswith('choice_b:') or st.startswith('choice_c:') or st.startswith('choice_d:') or st.startswith('written_num:') or st.startswith('written_question:') or st.startswith('written_answer:'):
            d=admin_draft()
            try:
                if st.startswith('choice_num:'):
                    d.update({'test_id':st.split(':',1)[1],'kind':'choice','number':int(text)});save_draft(d);set_admin_state('choice_question:'+d['test_id']);return await m.answer('Savol matnini kiriting:')
                if st.startswith('choice_question:'):
                    d['question']=text;save_draft(d);set_admin_state('choice_a:'+d['test_id']);return await m.answer('A variant matnini kiriting:')
                if st.startswith('choice_a:'):
                    d['A']=text;save_draft(d);set_admin_state('choice_b:'+d['test_id']);return await m.answer('B variant matnini kiriting:')
                if st.startswith('choice_b:'):
                    d['B']=text;save_draft(d);set_admin_state('choice_c:'+d['test_id']);return await m.answer('C variant matnini kiriting:')
                if st.startswith('choice_c:'):
                    d['C']=text;save_draft(d);set_admin_state('choice_d:'+d['test_id']);return await m.answer('D variant matnini kiriting:')
                if st.startswith('choice_d:'):
                    d['D']=text;save_draft(d);set_admin_state('choice_answer:'+d['test_id']);return await m.answer('To‘g‘ri javobni tugma orqali tanlang:',reply_markup=answer_kb(d['test_id'],d['number']))
                if st.startswith('written_num:'):
                    d.update({'test_id':st.split(':',1)[1],'kind':'written','number':int(text)});save_draft(d);set_admin_state('written_question:'+d['test_id']);return await m.answer('Savol matnini kiriting:')
                if st.startswith('written_question:'):
                    d['question']=text;save_draft(d);set_admin_state('written_answer:'+d['test_id']);return await m.answer('To‘g‘ri yozma javobni kiriting:')
                if st.startswith('written_answer:'):
                    d['answer']=text;db.upsert_test_question(d['test_id'],d['number'],d['question'],[],d['answer'],'written');clear_draft();set_admin_state('admin');return await m.answer(f"{d['number']}-savol saqlandi.",reply_markup=test_kb(d['test_id']))
            except Exception as e:return await m.answer(f'Xato: {e}')
        if st.startswith('group_target:'):
            tid=st.split(':',1)[1];target=text
            try:
                t=db.get_test(tid);me=await BOT.get_me();link=f'https://t.me/{me.username}?start={t["code"]}';qs=db.questions_for_test(tid)
                chunks=[];cur=f"{t['name']}\nKirish kodi: {t['code']}\n\n"
                for q in qs:
                    opts=json.loads(q['options_json'] or '[]');block=f"{q['number']}. {q['question']}\n"+('\n'.join(f"{chr(65+i)}) {v}" for i,v in enumerate(opts)) if opts else '')+'\n\n')
                    if len(cur)+len(block)>3300:chunks.append(cur);cur='';
                    cur+=block
                if cur:chunks.append(cur)
                for i,ch in enumerate(chunks):await BOT.send_message(target,ch)
                await BOT.send_message(target,'Testni Mini App orqali yechish uchun:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',url=link)]]))
                set_admin_state('admin');return await m.answer('Test guruhga yuborildi.',reply_markup=test_kb(tid))
            except Exception as e:return await m.answer(f'Guruhga yuborishda xato: {e}')

    @r.callback_query(F.data=='t2_list')
    async def list_tests(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        await q.message.edit_text('TESTLAR',reply_markup=tests_kb());await q.answer()
    @r.callback_query(F.data=='t2_new')
    async def new_test(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        clear_draft();set_admin_state('new_code');await q.message.edit_text('Avval yangi testning KIRISH KODINI qo‘lda tanlang.\n\nMasalan: MAT2026');await q.answer()
    @r.callback_query(F.data.startswith('t2_pick:'))
    async def pick(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];db.set_setting('admin_test_id',tid);t=db.get_test(tid);await q.message.edit_text(f"{t['name']}\n\nKirish kodi: {t['code']}\nHolat: {t['mode']}\nSavollar: {len(db.questions_for_test(tid))}",reply_markup=test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith('t2_add:'))
    async def add(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];await q.message.edit_text('Savol turini tanlang:',reply_markup=question_type_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith('t2_choice:'))
    async def choice(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];save_draft({'test_id':tid,'kind':'choice'});set_admin_state('choice_num:'+tid);await q.message.answer('Savol raqamini kiriting:');await q.answer()
    @r.callback_query(F.data.startswith('t2_written:'))
    async def written(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];save_draft({'test_id':tid,'kind':'written'});set_admin_state('written_num:'+tid);await q.message.answer('Savol raqamini kiriting:');await q.answer()
    @r.callback_query(F.data.startswith('t2_ans:'))
    async def choose_answer(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        _,tid,num,letter=q.data.split(':');d=admin_draft();opts=[d.get('A',''),d.get('B',''),d.get('C',''),d.get('D','')];ans=opts['ABCD'.index(letter)];db.upsert_test_question(tid,int(num),d['question'],opts,ans,'choice');clear_draft();set_admin_state('admin');await q.message.answer(f"{num}-savol saqlandi. To‘g‘ri javob: {letter}",reply_markup=test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith('t2_keys:'))
    async def keys(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];set_admin_state('keys:'+tid);await q.message.answer('Masalan: 1-A, 2-C, 3-D, 4-B');await q.answer()
    @r.callback_query(F.data.startswith('t2_open:'))
    async def open_(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1]
        with db.conn() as c:c.execute("UPDATE tests SET mode='open',active=1 WHERE test_id=?",(tid,))
        await q.answer('Test ochildi')
    @r.callback_query(F.data.startswith('t2_close:'))
    async def close_(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1]
        with db.conn() as c:c.execute("UPDATE tests SET mode='closed' WHERE test_id=?",(tid,))
        await q.answer('Test yopildi')
    @r.callback_query(F.data.startswith('t2_link:'))
    async def link(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        t=db.get_test(q.data.split(':',1)[1]);me=await BOT.get_me();url=f'https://t.me/{me.username}?start={t["code"]}';await q.message.answer(f"Kirish kodi: {t['code']}\nBot havolasi: {url}\nMini App: {WEBAPP.rstrip('/')}/test?code={t['code']}");await q.answer()
    @r.callback_query(F.data.startswith('t2_group:'))
    async def group(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];set_admin_state('group_target:'+tid);await q.message.answer('Guruh @username yoki chat ID sini yuboring. Bot o‘sha guruhda bo‘lishi va xabar yuborish huquqiga ega bo‘lishi kerak.');await q.answer()
    @r.callback_query(F.data.startswith('t2_results:'))
    async def results(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];rows=db.all_attempts_for_test(tid);lines=['NATIJALAR','']+[f"{i}. {a['full_name'] or 'Ismsiz'} · {float(a['score'] or 0):.2f} · {a['grade'] or '—'} · {'Yakunlangan' if a['submitted'] else 'Faol'}" for i,a in enumerate(rows,1)];await q.message.edit_text(('\n'.join(lines) if rows else 'Hali qatnashchi yo‘q.')[:3900],reply_markup=test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith('t2_pdf:'))
    async def pdf(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];t=db.get_test(tid);rows=[['№','Ism Familiya','Telegram ID','Kirish','Tugash','Ball','Baho','Holat']]
        for i,a in enumerate(db.all_attempts_for_test(tid),1):rows.append([str(i),a['full_name'] or '—',str(a['telegram_id']),str(a['started_at'] or '—')[:16],str(a['finished_at'] or '—')[:16],f"{float(a['score'] or 0):.2f}",a['grade'] or '—','Yakunlangan' if a['submitted'] else 'Faol'])
        path=f'/tmp/{secrets.token_hex(8)}.pdf';styles=getSampleStyleSheet();doc=SimpleDocTemplate(path,pagesize=landscape(A4),rightMargin=18,leftMargin=18,topMargin=24,bottomMargin=24);table=Table(rows,repeatRows=1,colWidths=[24,155,80,100,100,55,50,75]);table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eeeeee')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8)]));doc.build([Paragraph(f"NUR O‘QIW ORAYI — {t['name']}",styles['Title']),Paragraph(f"Kirish kodi: {t['code']} · Qatnashchilar: {len(rows)-1}",styles['Heading2']),Spacer(1,10),table]);await BOT.send_document(ADMIN,FSInputFile(path),caption=f"PDF NATIJA — {t['name']} — {t['code']}");await q.answer('Alohida PDF yuborildi')
    @r.callback_query(F.data.startswith('t2_q:'))
    async def questions(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];qs=db.questions_for_test(tid);text='\n'.join(f"{x['number']}. {x['question']}" for x in qs) or 'Savol yo‘q';await q.message.edit_text(text[:3900],reply_markup=test_kb(tid));await q.answer()
    dp.include_router(r)
