import os,json,secrets
from datetime import datetime,time,timedelta
from aiogram import Router,F
from aiogram.filters import CommandStart
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo,FSInputFile,ReplyKeyboardMarkup,KeyboardButton
from fastapi.responses import JSONResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
from reportlab.lib.styles import getSampleStyleSheet
from . import db

CORE=ADMIN=APP=TZ=BOT=WEBAPP=None

def norm(v): return ' '.join(str(v or '').strip().casefold().split())
def grade(s):
    s=float(s);return 'A+' if s>=90 else 'A' if s>=80 else 'B' if s>=70 else 'C' if s>=60 else 'D' if s>=50 else 'F'
def user_menu(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Profilim'),KeyboardButton(text='Tariflar')],[KeyboardButton(text='Testni boshlash'),KeyboardButton(text='Mening natijam')],[KeyboardButton(text='Userlar ro‘yxati'),KeyboardButton(text='Yordam')]],resize_keyboard=True,is_persistent=True)
def admin_menu(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Test sozlamalari'),KeyboardButton(text='Ishtirokchilar')],[KeyboardButton(text='PDF natijalar'),KeyboardButton(text='Tariflar')]],resize_keyboard=True,is_persistent=True)
def tests_kb():
    rows=[[InlineKeyboardButton(text=f"{t['name'][:24]} · {t['code']}",callback_data=f't_pick:{t["test_id"]}')] for t in db.all_tests()]
    rows.append([InlineKeyboardButton(text='YANGI TEST',callback_data='t_new')]);return InlineKeyboardMarkup(inline_keyboard=rows)
def test_kb(tid): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Savollar',callback_data=f't_q:{tid}'),InlineKeyboardButton(text='Yangi savol',callback_data=f't_add:{tid}')],[InlineKeyboardButton(text='Oddiy variant',callback_data=f't_choice:{tid}'),InlineKeyboardButton(text='Yozma variant',callback_data=f't_written:{tid}')],[InlineKeyboardButton(text='To‘g‘ri javoblar',callback_data=f't_keys:{tid}')],[InlineKeyboardButton(text='Natijalar',callback_data=f't_results:{tid}'),InlineKeyboardButton(text='PDF',callback_data=f't_pdf:{tid}')],[InlineKeyboardButton(text='Guruhga yuborish',callback_data=f't_group:{tid}'),InlineKeyboardButton(text='Mini App link',callback_data=f't_link:{tid}')],[InlineKeyboardButton(text='OCHISH',callback_data=f't_open:{tid}'),InlineKeyboardButton(text='YOPISH',callback_data=f't_close:{tid}')],[InlineKeyboardButton(text='Orqaga',callback_data='t_list')]])
def types_kb(tid): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ODDIY VARIANT',callback_data=f't_choice:{tid}')],[InlineKeyboardButton(text='YOZMA VARIANT',callback_data=f't_written:{tid}')],[InlineKeyboardButton(text='Orqaga',callback_data=f't_pick:{tid}')]])
def answer_kb(tid,n): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='A',callback_data=f't_ans:{tid}:{n}:A'),InlineKeyboardButton(text='B',callback_data=f't_ans:{tid}:{n}:B'),InlineKeyboardButton(text='C',callback_data=f't_ans:{tid}:{n}:C'),InlineKeyboardButton(text='D',callback_data=f't_ans:{tid}:{n}:D')]])
def draft():
    try:return json.loads(db.get_setting('admin_question_draft','{}') or '{}')
    except:return {}
def save_draft(x):db.set_setting('admin_question_draft',json.dumps(x,ensure_ascii=False))
def clear_draft():db.set_setting('admin_question_draft','{}')
def set_state(s):db.update_user(ADMIN,state=s)
def open_test(t):
    if not t or not int(t['active']):return False
    if str(t['mode'])=='open':return True
    if str(t['mode'])=='closed':return False
    now=datetime.now(TZ).time();return time.fromisoformat(t['start_time'])<=now<time.fromisoformat(t['end_time'])
def expired(a,t):
    if not a or not a['started_at']:return False
    st=datetime.fromisoformat(a['started_at']);end=datetime.combine(st.date(),time.fromisoformat(t['end_time']),tzinfo=TZ);return datetime.now(TZ)>=min(st+timedelta(hours=1),end)
def score(t,answers):
    qs=db.questions_for_test(t['test_id']);return round(sum(norm(answers.get(str(q['number'])))==norm(q['answer']) for q in qs)/len(qs)*100,2) if qs else 0

def register(core,dp,bot,webapp_url):
    global CORE,ADMIN,APP,TZ,BOT,WEBAPP
    CORE,ADMIN,APP,TZ,BOT,WEBAPP=core,core.ADMIN,core.app,core.TZ,bot,webapp_url
    r=Router(name='features_v2')
    async def auth(request):
        raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or request.query_params.get('initData','');tid=CORE.telegram_user(raw);return tid,db.get_user(tid) if tid else None
    @APP.get('/api/test/state')
    async def state(request):
        tid,u=await auth(request);code=request.query_params.get('code','').strip();t=db.get_test_by_code(code) if code else (db.get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u:return {'ok':False,'error':'not_authorized'}
        if not t:return {'ok':False,'error':'test_not_found'}
        if code and u['test_id']!=t['test_id']:db.update_user(tid,test_id=t['test_id'],code_ok=1,state='ready');u=db.get_user(tid)
        if not u['full_name'] or not u['phone']:return {'ok':False,'error':'registration_required','test_name':t['name']}
        a=db.ensure_attempt(t['test_id'],tid)
        if a['submitted']:return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade'],'test_name':t['name'],'full_name':u['full_name']}
        if not a['started_at']:
            if not open_test(t):return {'ok':False,'error':'test_closed','test_name':t['name']}
            db.update_attempt(a['attempt_id'],started_at=datetime.now(TZ).isoformat(),status='active');a=db.get_attempt(t['test_id'],tid)
        if expired(a,t):return {'ok':False,'error':'test_closed','test_name':t['name']}
        st=datetime.fromisoformat(a['started_at']);end=datetime.combine(st.date(),time.fromisoformat(t['end_time']),tzinfo=TZ)
        return {'ok':True,'full_name':u['full_name'],'answers':json.loads(a['answers_json'] or '{}'),'ends_at':end.isoformat(),'test_name':t['name'],'test_code':t['code'],'total_questions':len(db.questions_for_test(t['test_id']))}
    @APP.get('/api/test/questions')
    async def questions(request):
        tid,u=await auth(request);code=request.query_params.get('code','').strip();t=db.get_test_by_code(code) if code else (db.get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u or not t:return JSONResponse({'ok':False,'error':'not_authorized'},status_code=401)
        return {'ok':True,'questions':[{'id':q['number'],'question':q['question'],'options':json.loads(q['options_json'] or '[]'),'kind':q['kind'],'image_url':q['image_url']} for q in db.questions_for_test(t['test_id'])]}
    @APP.post('/api/test/answer')
    async def answer(p:dict):
        tid=CORE.telegram_user(p.get('initData',''));u=db.get_user(tid) if tid else None;code=str(p.get('code','')).strip();t=db.get_test_by_code(code) if code else (db.get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
        a=db.ensure_attempt(t['test_id'],tid)
        if a['submitted']:return {'ok':False,'error':'already_submitted'}
        if not open_test(t) or expired(a,t):return {'ok':False,'error':'test_closed'}
        q=db.get_question_for_test(t['test_id'],p.get('question_id'))
        if not q:return {'ok':False,'error':'question_not_found'}
        answ=json.loads(a['answers_json'] or '{}');k=str(q['number'])
        if k in answ:return {'ok':False,'error':'answer_locked','correct':norm(answ[k])==norm(q['answer'])}
        ans=str(p.get('answer','')).strip();answ[k]=ans;db.save_attempt_answers(a['attempt_id'],answ);return {'ok':True,'correct':norm(ans)==norm(q['answer']),'number':q['number']}
    @APP.post('/api/test/finish')
    async def finish(p:dict):
        tid=CORE.telegram_user(p.get('initData',''));u=db.get_user(tid) if tid else None;code=str(p.get('code','')).strip();t=db.get_test_by_code(code) if code else (db.get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
        a=db.ensure_attempt(t['test_id'],tid)
        if a['submitted']:return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade']}
        if not open_test(t) and not expired(a,t):return {'ok':False,'error':'test_closed'}
        sc=score(t,json.loads(a['answers_json'] or '{}'));gr=grade(sc);db.update_attempt(a['attempt_id'],score=sc,grade=gr,submitted=1,status='submitted',finished_at=datetime.now(TZ).isoformat());return {'ok':True,'score':sc,'grade':gr,'full_name':u['full_name'],'test_name':t['name']}
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
        u=db.get_user(m.from_user.id) or db.ensure_user(m.from_user.id);t=db.get_test(u['test_id']) if u['test_id'] else None;a=db.get_attempt(t['test_id'],m.from_user.id) if t else None;res=f"{float(a['score'] or 0):.2f} · {a['grade'] or '—'}" if a and a['submitted'] else 'Yakunlanmagan';await m.answer(f"PROFILIM\n\nIsm-familiya: {u['full_name'] or '—'}\nTelefon: {u['phone'] or '—'}\nTest: {t['name'] if t else 'Tanlanmagan'}\nKod: {t['code'] if t else '—'}\nNatija: {res}")
    @r.message(F.text=='Tariflar')
    async def tariffs(m:Message):await m.answer('TARIFLAR\n\nDEFAULT\nOddiy test qatnashchisi.\n\nPREMIUM\nKengaytirilgan statistika.')
    @r.message(F.text=='Testni boshlash')
    async def begin(m:Message):
        u=db.get_user(m.from_user.id);t=db.get_test(u['test_id']) if u and u['test_id'] else None
        if not t:return await m.answer('Avval test kodini kiriting.')
        await m.answer(f"{t['name']}\n\nTestni boshlash uchun:",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',web_app=WebAppInfo(url=f'{WEBAPP.rstrip("/")}/test?code={t["code"]}'))]]))
    @r.message(F.text=='Mening natijam')
    async def result(m:Message):
        u=db.get_user(m.from_user.id);t=db.get_test(u['test_id']) if u and u['test_id'] else None;a=db.get_attempt(t['test_id'],m.from_user.id) if t else None;await m.answer(f"NATIJAM\n\nTest: {t['name']}\nBall: {float(a['score'] or 0):.2f}\nBaho: {a['grade'] or 'Hali yakunlanmagan'}" if a and t else 'Hali test tanlanmagan.')
    @r.message(F.text=='Yordam')
    async def help_(m:Message):await m.answer('Guruhdagi test xabaridagi TESTNI BOSHLASH tugmasini bosing.')
    @r.message(F.text=='Userlar ro‘yxati')
    async def users(m:Message):
        us=db.all_registered_users();await m.answer('\n'.join(f"{i}. {u['full_name'] or 'Ismsiz'} · {u['telegram_id']}" for i,u in enumerate(us[:100],1)) or 'User yo‘q.')
    @r.message(F.from_user.id==ADMIN)
    async def admin_text(m:Message):
        u=db.get_user(ADMIN) or db.ensure_user(ADMIN);st=u['state'] or 'admin';text=(m.text or '').strip()
        if text in ('Test sozlamalari','Ishtirokchilar','PDF natijalar'):return await m.answer('TESTLAR',reply_markup=tests_kb())
        if st=='new_code':
            if ' ' in text or len(text)>32:return await m.answer('Kodni bitta so‘z qilib kiriting. Masalan: MAT2026')
            if db.get_test_by_code(text):return await m.answer('Bu kod band. Boshqa kod tanlang.')
            save_draft({'code':text});set_state('new_name');return await m.answer('Test nomini kiriting:')
        if st=='new_name':
            d=draft();d['name']=text;save_draft(d);set_state('new_time');return await m.answer('Vaqt: 08:30-09:30 yoki OPEN')
        if st=='new_time':
            d=draft()
            try:
                a,b=('00:00','23:59') if text.upper()=='OPEN' else [x.strip() for x in text.split('-',1)];time.fromisoformat(a);time.fromisoformat(b);t=db.create_test(d['name'],d['code'],a,b,'open' if text.upper()=='OPEN' else 'closed');clear_draft();set_state('admin');return await m.answer(f"Yangi test yaratildi.\nKod: {t['code']}",reply_markup=test_kb(t['test_id']))
            except:return await m.answer('Format xato: 08:30-09:30')
        if st.startswith('choice:'):
            d=draft();tid=st.split(':',1)[1]
            try:
                if st.startswith('choice:num:'):d['number']=int(text);d['test_id']=tid;save_draft(d);set_state('choice:q:'+tid);return await m.answer('Savol matnini kiriting:')
            except:return await m.answer('Savol raqami son bo‘lsin.')
        if st.startswith('choice:q:'):
            d=draft();d['question']=text;save_draft(d);set_state('choice:a:'+d['test_id']);return await m.answer('A variantini kiriting:')
        if st.startswith('choice:a:'):
            d=draft();d['A']=text;save_draft(d);set_state('choice:b:'+d['test_id']);return await m.answer('B variantini kiriting:')
        if st.startswith('choice:b:'):
            d=draft();d['B']=text;save_draft(d);set_state('choice:c:'+d['test_id']);return await m.answer('C variantini kiriting:')
        if st.startswith('choice:c:'):
            d=draft();d['C']=text;save_draft(d);set_state('choice:d:'+d['test_id']);return await m.answer('D variantini kiriting:')
        if st.startswith('choice:d:'):
            d=draft();d['D']=text;save_draft(d);set_state('choice:answer:'+d['test_id']);return await m.answer('To‘g‘ri variantni tanlang:',reply_markup=answer_kb(d['test_id'],d['number']))
        if st.startswith('written:num:'):
            d=draft();d.update({'test_id':st.split(':',1)[1],'number':int(text)});save_draft(d);set_state('written:q:'+d['test_id']);return await m.answer('Savol matnini kiriting:')
        if st.startswith('written:q:'):
            d=draft();d['question']=text;save_draft(d);set_state('written:a:'+d['test_id']);return await m.answer('To‘g‘ri yozma javobni kiriting:')
        if st.startswith('written:a:'):
            d=draft();db.upsert_test_question(d['test_id'],d['number'],d['question'],[],text,'written');clear_draft();set_state('admin');return await m.answer('Yozma savol saqlandi.',reply_markup=test_kb(d['test_id']))
        if st.startswith('group:'):
            tid=st.split(':',1)[1]
            try:
                t=db.get_test(tid);me=await BOT.get_me();chunks=[];cur=f"{t['name']}\nKirish kodi: {t['code']}\n\n"
                for q in db.questions_for_test(tid):
                    opts=json.loads(q['options_json'] or '[]');block=f"{q['number']}. {q['question']}\n"+('\n'.join(f"{chr(65+i)}) {v}" for i,v in enumerate(opts)) if opts else 'Yozma javob')+'\n\n')
                    if len(cur)+len(block)>3300:chunks.append(cur);cur=''
                    cur+=block
                if cur:chunks.append(cur)
                for ch in chunks:await BOT.send_message(text,ch)
                await BOT.send_message(text,'Testni bot Mini App orqali yechish:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',url=f'https://t.me/{me.username}?start={t["code"]}')]]));set_state('admin');return await m.answer('Guruhga yuborildi.',reply_markup=test_kb(tid))
            except Exception as e:return await m.answer(f'Guruhga yuborishda xato: {e}')
    @r.callback_query(F.data=='t_list')
    async def list_(q:CallbackQuery):
        if q.from_user.id==ADMIN:await q.message.edit_text('TESTLAR',reply_markup=tests_kb());await q.answer()
    @r.callback_query(F.data=='t_new')
    async def new_(q:CallbackQuery):
        if q.from_user.id==ADMIN:clear_draft();set_state('new_code');await q.message.edit_text('Yangi test uchun KIRISH KODINI qo‘lda tanlang:');await q.answer()
    @r.callback_query(F.data.startswith('t_pick:'))
    async def pick(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];t=db.get_test(tid);await q.message.edit_text(f"{t['name']}\nKod: {t['code']}\nSavollar: {len(db.questions_for_test(tid))}",reply_markup=test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith('t_add:'))
    async def add(q:CallbackQuery):
        if q.from_user.id==ADMIN:await q.message.edit_text('Savol turini tanlang:',reply_markup=types_kb(q.data.split(':',1)[1]));await q.answer()
    @r.callback_query(F.data.startswith('t_choice:'))
    async def choice(q:CallbackQuery):
        if q.from_user.id==ADMIN:save_draft({'test_id':q.data.split(':',1)[1]});set_state('choice:num:'+q.data.split(':',1)[1]);await q.message.answer('Savol raqami:');await q.answer()
    @r.callback_query(F.data.startswith('t_written:'))
    async def written(q:CallbackQuery):
        if q.from_user.id==ADMIN:save_draft({'test_id':q.data.split(':',1)[1]});set_state('written:num:'+q.data.split(':',1)[1]);await q.message.answer('Savol raqami:');await q.answer()
    @r.callback_query(F.data.startswith('t_ans:'))
    async def ans(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        _,tid,n,letter=q.data.split(':');d=draft();opts=[d.get('A',''),d.get('B',''),d.get('C',''),d.get('D','')];db.upsert_test_question(tid,int(n),d['question'],opts,opts['ABCD'.index(letter)],'choice');clear_draft();set_state('admin');await q.message.answer(f'{n}-savol saqlandi. To‘g‘ri javob: {letter}',reply_markup=test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith('t_open:'))
    async def op(q:CallbackQuery):
        if q.from_user.id==ADMIN:
            tid=q.data.split(':',1)[1]
            with db.conn() as c:c.execute("UPDATE tests SET mode='open',active=1 WHERE test_id=?",(tid,))
            await q.answer('Test ochildi')
    @r.callback_query(F.data.startswith('t_close:'))
    async def cl(q:CallbackQuery):
        if q.from_user.id==ADMIN:
            tid=q.data.split(':',1)[1]
            with db.conn() as c:c.execute("UPDATE tests SET mode='closed' WHERE test_id=?",(tid,))
            await q.answer('Test yopildi')
    @r.callback_query(F.data.startswith('t_link:'))
    async def link(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        t=db.get_test(q.data.split(':',1)[1]);me=await BOT.get_me();await q.message.answer(f"KOD: {t['code']}\nBOT: https://t.me/{me.username}?start={t['code']}\nMINI APP: {WEBAPP.rstrip('/')}/test?code={t['code']}");await q.answer()
    @r.callback_query(F.data.startswith('t_group:'))
    async def group(q:CallbackQuery):
        if q.from_user.id==ADMIN:set_state('group:'+q.data.split(':',1)[1]);await q.message.answer('Guruh @username yoki chat ID sini yuboring. Bot guruhda admin bo‘lishi kerak.');await q.answer()
    @r.callback_query(F.data.startswith('t_keys:'))
    async def keys(q:CallbackQuery):
        if q.from_user.id==ADMIN:set_state('keys:'+q.data.split(':',1)[1]);await q.message.answer('Kalitni yozing: 1-A, 2-C, 3-D');await q.answer()
    @r.callback_query(F.data.startswith('t_results:'))
    async def results(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        rows=db.all_attempts_for_test(q.data.split(':',1)[1]);await q.message.edit_text('\n'.join([f"{i}. {a['full_name'] or 'Ismsiz'} · {float(a['score'] or 0):.2f} · {a['grade'] or '—'}" for i,a in enumerate(rows,1)])[:3900] or 'Hali qatnashchi yo‘q.',reply_markup=test_kb(q.data.split(':',1)[1]));await q.answer()
    @r.callback_query(F.data.startswith('t_pdf:'))
    async def pdf(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];t=db.get_test(tid);rows=[['№','Ism Familiya','Telegram ID','Kirish','Tugash','Ball','Baho','Holat']]
        for i,a in enumerate(db.all_attempts_for_test(tid),1):rows.append([i,a['full_name'] or '—',a['telegram_id'],str(a['started_at'] or '—')[:16],str(a['finished_at'] or '—')[:16],f"{float(a['score'] or 0):.2f}",a['grade'] or '—','Yakunlangan' if a['submitted'] else 'Faol'])
        path=f'/tmp/{secrets.token_hex(6)}.pdf';styles=getSampleStyleSheet();doc=SimpleDocTemplate(path,pagesize=landscape(A4));tb=Table(rows,repeatRows=1);tb.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.lightgrey)]));doc.build([Paragraph(f"NUR O‘QIW ORAYI — {t['name']} · {t['code']}",styles['Title']),Spacer(1,8),tb]);await BOT.send_document(ADMIN,FSInputFile(path),caption=f"PDF NATIJA — {t['name']} · {t['code']}");await q.answer('PDF yuborildi')
    dp.include_router(r)
