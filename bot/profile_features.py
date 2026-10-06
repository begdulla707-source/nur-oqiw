import os,json,secrets
from datetime import datetime,time,timedelta
from aiogram import Router,F
from aiogram.filters import CommandStart
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo
from fastapi.responses import JSONResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
from reportlab.lib.styles import getSampleStyleSheet
from . import main as core
from .db import *

ADMIN=core.ADMIN;app=core.app;TZ=core.TZ

def user_menu():
    from aiogram.types import ReplyKeyboardMarkup,KeyboardButton
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Profilim'),KeyboardButton(text='Tariflar')],[KeyboardButton(text='Testni boshlash'),KeyboardButton(text='Mening natijam')],[KeyboardButton(text='Userlar ro‘yxati'),KeyboardButton(text='Yordam')]],resize_keyboard=True,is_persistent=True)
def tariff_text():return 'TARIFLAR\n\nDEFAULT\nOddiy test qatnashchisi.\n\nPREMIUM\nPremium belgi va kengaytirilgan statistika.\n\nPremium tarif uchun administratorga murojaat qiling.'
def admin_tariff_list():return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Userlar ro‘yxati',callback_data='tf_list')],[InlineKeyboardButton(text='Orqaga',callback_data='admin_home')]])
def _norm(v):return ' '.join(str(v or '').strip().casefold().split())
def _grade(score):
    s=float(score);return 'A+' if s>=90 else 'A' if s>=80 else 'B' if s>=70 else 'C' if s>=60 else 'D' if s>=50 else 'F'
def _test_open(t):
    if not t or not int(t['active']):return False
    mode=str(t['mode'] or 'auto')
    if mode=='open':return True
    if mode=='closed':return False
    now=datetime.now(TZ).time();return time.fromisoformat(t['start_time'])<=now<time.fromisoformat(t['end_time'])
def _test_expired(a,t):
    if not a or not a['started_at']:return False
    st=datetime.fromisoformat(a['started_at']);close=datetime.combine(st.date(),time.fromisoformat(t['end_time']),tzinfo=TZ)
    return datetime.now(TZ)>=min(st+timedelta(hours=1),close)
def _test_kb(tid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Savollar',callback_data=f'mt_q:{tid}'),InlineKeyboardButton(text='To‘g‘ri javoblar',callback_data=f'mt_key:{tid}')],
        [InlineKeyboardButton(text='Natijalar',callback_data=f'mt_results:{tid}'),InlineKeyboardButton(text='PDF',callback_data=f'mt_pdf:{tid}')],
        [InlineKeyboardButton(text='OCHISH',callback_data=f'mt_open:{tid}'),InlineKeyboardButton(text='YOPISH',callback_data=f'mt_close:{tid}')],
        [InlineKeyboardButton(text='Mini App havolasi',callback_data=f'mt_link:{tid}')],
        [InlineKeyboardButton(text='Orqaga',callback_data='mt_list')]
    ])
def _test_list_kb():
    rows=[[InlineKeyboardButton(text=f"{t['name'][:25]} · {t['code']}",callback_data=f'mt_pick:{t["test_id"]}')] for t in all_tests()];rows.append([InlineKeyboardButton(text='YANGI TEST',callback_data='mt_new')]);return InlineKeyboardMarkup(inline_keyboard=rows)
def _questions_kb(tid):
    qs=questions_for_test(tid);rows=[];row=[]
    for q in qs:
        row.append(InlineKeyboardButton(text=str(q['number']),callback_data=f'mt_qpick:{tid}:{q["number"]}'))
        if len(row)==5:rows.append(row);row=[]
    if row:rows.append(row)
    rows.append([InlineKeyboardButton(text='Yangi savol',callback_data=f'mt_addq:{tid}')]);rows.append([InlineKeyboardButton(text='Orqaga',callback_data=f'mt_pick:{tid}')]);return InlineKeyboardMarkup(inline_keyboard=rows)
def _finish_score(t,answers):
    qs=questions_for_test(t['test_id']);correct=sum(1 for q in qs if _norm(answers.get(str(q['number']),''))==_norm(q['answer']));return round(correct/len(qs)*100,2) if qs else 0

def _register_api():
    async def auth(request):
        raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw
        raw=raw or request.query_params.get('initData','');tid=core.telegram_user(raw);return tid,get_user(tid) if tid else None
    @app.get('/api/test/state')
    async def test_state(request):
        tid,u=await auth(request);code=request.query_params.get('code','').strip();t=get_test_by_code(code) if code else (get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u:return {'ok':False,'error':'not_authorized'}
        if not t:return {'ok':False,'error':'test_not_found'}
        if code and u['test_id']!=t['test_id']:update_user(tid,test_id=t['test_id'],code_ok=1,state='ready');u=get_user(tid)
        if not u['full_name'] or not u['phone']:return {'ok':False,'error':'registration_required','test_name':t['name'],'test_code':t['code']}
        a=ensure_attempt(t['test_id'],tid)
        if a['submitted']:return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade'],'full_name':u['full_name'] or '','test_name':t['name']}
        if not a['started_at']:
            if not _test_open(t):return {'ok':False,'error':'test_closed','start':t['start_time'],'end':t['end_time'],'test_name':t['name']}
            update_attempt(a['attempt_id'],started_at=datetime.now(TZ).isoformat(),status='active');a=ensure_attempt(t['test_id'],tid)
        if _test_expired(a,t):return {'ok':False,'error':'test_closed','test_name':t['name']}
        answers=json.loads(a['answers_json'] or '{}');st=datetime.fromisoformat(a['started_at']);close=datetime.combine(st.date(),time.fromisoformat(t['end_time']),tzinfo=TZ)
        return {'ok':True,'full_name':u['full_name'] or '','answers':answers,'ends_at':close.isoformat(),'test_name':t['name'],'test_code':t['code'],'total_questions':len(questions_for_test(t['test_id']))}
    @app.get('/api/test/questions')
    async def test_questions(request):
        tid,u=await auth(request);code=request.query_params.get('code','').strip();t=get_test_by_code(code) if code else (get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u or not t:return JSONResponse({'ok':False,'error':'not_authorized'},status_code=401)
        return {'ok':True,'questions':[{'id':q['number'],'question':q['question'],'options':json.loads(q['options_json'] or '[]'),'kind':q['kind'],'image_url':q['image_url']} for q in questions_for_test(t['test_id'])]}
    @app.post('/api/test/answer')
    async def test_answer(p:dict):
        tid=core.telegram_user(p.get('initData',''));u=get_user(tid) if tid else None;code=str(p.get('code','')).strip();t=get_test_by_code(code) if code else (get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
        a=ensure_attempt(t['test_id'],tid)
        if a['submitted']:return {'ok':False,'error':'already_submitted'}
        if not _test_open(t) or _test_expired(a,t):return {'ok':False,'error':'test_closed'}
        q=get_question_for_test(t['test_id'],p.get('question_id'))
        if not q:return {'ok':False,'error':'question_not_found'}
        answers=json.loads(a['answers_json'] or '{}');key=str(q['number'])
        if key in answers:return {'ok':False,'error':'answer_locked','correct':_norm(answers[key])==_norm(q['answer'])}
        ans=str(p.get('answer','')).strip();answers[key]=ans;save_attempt_answers(a['attempt_id'],answers);return {'ok':True,'correct':_norm(ans)==_norm(q['answer']),'number':q['number']}
    @app.post('/api/test/finish')
    async def test_finish(p:dict):
        tid=core.telegram_user(p.get('initData',''));u=get_user(tid) if tid else None;code=str(p.get('code','')).strip();t=get_test_by_code(code) if code else (get_test(u['test_id']) if u and u['test_id'] else None)
        if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
        a=ensure_attempt(t['test_id'],tid)
        if a['submitted']:return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade']}
        expired=_test_expired(a,t)
        if not _test_open(t) and not expired:return {'ok':False,'error':'test_closed'}
        score=_finish_score(t,json.loads(a['answers_json'] or '{}'));grade=_grade(score);update_attempt(a['attempt_id'],score=score,grade=grade,submitted=1,status='submitted',finished_at=datetime.now(TZ).isoformat());return {'ok':True,'score':score,'grade':grade,'full_name':u['full_name'] or '','test_name':t['name']}
    @app.get('/api/admin/tests')
    async def admin_tests(request):
        key=os.getenv('ADMIN_API_KEY','')
        if not key or request.headers.get('X-Admin-Key','')!=key:return JSONResponse({'ok':False,'error':'forbidden'},status_code=403)
        return {'ok':True,'tests':[{'test_id':t['test_id'],'code':t['code'],'name':t['name'],'mode':t['mode'],'active':t['active'],'questions':len(questions_for_test(t['test_id'])),'participants':len(all_attempts_for_test(t['test_id']))} for t in all_tests()]}
_register_api()

def _pdf(tid,path):
    t=get_test(tid);rows=[['№','Ism Familiya','Telegram ID','Kirish','Tugash','Ball','Baho','Holat']]
    for i,a in enumerate(all_attempts_for_test(tid),1):rows.append([str(i),a['full_name'] or '—',str(a['telegram_id']),str(a['started_at'] or '—')[:16],str(a['finished_at'] or '—')[:16],f"{float(a['score'] or 0):.2f}",a['grade'] or '—','Yakunlangan' if a['submitted'] else 'Faol'])
    styles=getSampleStyleSheet();doc=SimpleDocTemplate(path,pagesize=landscape(A4),rightMargin=18,leftMargin=18,topMargin=24,bottomMargin=24);table=Table(rows,repeatRows=1,colWidths=[24,155,80,100,100,55,50,75]);table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eeeeee')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8)]));doc.build([Paragraph(f"NUR O‘QIW ORAYI — {t['name'] if t else 'TEST'}",styles['Title']),Paragraph(f"Kod: {t['code'] if t else '—'} · Qatnashchilar: {len(rows)-1}",styles['Heading2']),Spacer(1,10),table])

def profile_text(u):
    t=get_test(u['test_id']) if u['test_id'] else None;a=get_attempt(t['test_id'],u['telegram_id']) if t else None;res=f"{float(a['score'] or 0):.2f} · {a['grade'] or '—'}" if a and a['submitted'] else 'Yakunlanmagan';return f"PROFILIM\n\nIsm-familiya: {u['full_name'] or '—'}\nTelefon: {u['phone'] or '—'}\nTest: {t['name'] if t else 'Tanlanmagan'}\nKod: {t['code'] if t else '—'}\nNatija: {res}"

def register(dp,bot,webapp_url):
    r=Router(name='profile_features')
    @r.message(CommandStart(deep_link=True))
    async def deep_start(m:Message,command):
        code=(command.args or '').strip();t=get_test_by_code(code)
        if not t:return
        u=ensure_user(m.from_user.id);update_user(m.from_user.id,test_id=t['test_id'],state='name' if not u['full_name'] else ('phone' if not u['phone'] else 'test_code'),code_ok=0)
        await m.answer(f"{t['name']}\n\n"+('Ism, Familiyangizni kiriting:' if not u['full_name'] else ('Telefon raqamingizni yuboring:' if not u['phone'] else f"Test kodi: {t['code']}\n\nTestni boshlashingiz mumkin.")),reply_markup=user_menu() if u['full_name'] and u['phone'] else None)
    @r.message(F.text=='Profilim')
    async def profile(m:Message):await m.answer(profile_text(get_user(m.from_user.id) or ensure_user(m.from_user.id)))
    @r.message(F.text=='Tariflar')
    async def tariffs(m:Message):await m.answer(tariff_text())
    @r.message(F.text=='Testni boshlash')
    async def begin(m:Message):
        u=get_user(m.from_user.id);t=get_test(u['test_id']) if u and u['test_id'] else None
        if not t:return await m.answer('Avval test kodini kiriting.')
        url=f'{webapp_url.rstrip("/")}/test?code={t["code"]}';await m.answer(f"{t['name']}\n\nTestni boshlash uchun:",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',web_app=WebAppInfo(url=url))]]))
    @r.message(F.text=='Mening natijam')
    async def result(m:Message):
        u=get_user(m.from_user.id);t=get_test(u['test_id']) if u and u['test_id'] else None;a=get_attempt(t['test_id'],m.from_user.id) if t else None;await m.answer(f"NATIJAM\n\nTest: {t['name'] if t else '—'}\nBall: {float(a['score'] or 0):.2f}\nBaho: {a['grade'] or 'Hali yakunlanmagan'}" if a else 'Hali test tanlanmagan.')
    @r.message(F.text=='Yordam')
    async def help_(m:Message):await m.answer('Test kodi orqali kerakli testni tanlang. Test Telegram ichidagi Mini App orqali ochiladi.')
    @r.message(F.text=='Userlar ro‘yxati')
    async def users_(m:Message):
        us=all_registered_users();await m.answer('\n'.join(f"{i}. {u['full_name'] or 'Ismsiz'} · {u['telegram_id']}" for i,u in enumerate(us[:100],1)) or 'User yo‘q.')
    @r.message(F.from_user.id==ADMIN)
    async def admin_text(m:Message):
        u=get_user(ADMIN) or ensure_user(ADMIN);st=u['state'] or 'admin';text=m.text.strip()
        if text in ('Test sozlamalari','Ishtirokchilar','PDF natijalar'):return await m.answer('TESTLAR',reply_markup=_test_list_kb())
        if text=='Tariflar':return await m.answer('TARIFLAR BOSHQARUVI',reply_markup=admin_tariff_list())
        if st=='mt_new:pending':
            p=[x.strip() for x in text.split('|')]
            if len(p)!=4:return await m.answer('Format: Nomi | KOD | 08:30 | 09:30')
            try:t=create_test(p[0],p[1],p[2],p[3],'closed');update_user(ADMIN,state='admin');return await m.answer(f"Yangi test yaratildi: {t['name']} · {t['code']}",reply_markup=_test_kb(t['test_id']))
            except Exception as e:return await m.answer(f'Xato: {e}')
        if st.startswith('mt_addq:'):
            tid=st.split(':',1)[1]
            try:
                p=[x.strip() for x in text.split('|')];num=int(p[0]);kind=p[2].lower();question=p[1]
                if kind in ('written','write','text','yozma'):opts=[];answer=p[3] if len(p)>3 else '';kind='written'
                else:
                    if len(p)<7:raise ValueError('Format: № | savol | A | B | C | D | A/B/C/D')
                    opts=p[2:6];letter=p[6].upper();answer=opts['ABCD'.index(letter)];kind='choice'
                upsert_test_question(tid,num,question,opts,answer,kind);update_user(ADMIN,state='admin');return await m.answer(f'{num}-savol saqlandi.',reply_markup=_test_kb(tid))
            except Exception as e:return await m.answer(f'Xato: {e}')
        if st.startswith('mt_key:'):
            tid=st.split(':',1)[1];changed=0
            try:
                for item in [x.strip() for x in text.replace(';',',').split(',') if x.strip()]:
                    num,letter=[x.strip() for x in item.replace(':','-').split('-',1)];q=get_question_for_test(tid,int(num));opts=json.loads(q['options_json'] or '[]') if q else []
                    if not q or len(opts)!=4:raise ValueError(f'{num}-savol topilmadi yoki 4 variant emas')
                    ans=opts['ABCD'.index(letter.upper())];upsert_test_question(tid,int(num),q['question'],opts,ans,q['kind'],q['group_id'],q['image_url']);changed+=1
                update_user(ADMIN,state='admin');return await m.answer(f'{changed} ta javob kaliti saqlandi.',reply_markup=_test_kb(tid))
            except Exception as e:return await m.answer(f'Xato: {e}')
    @r.callback_query(F.data=='mt_list')
    async def mt_list(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        await q.message.edit_text('TESTLAR',reply_markup=_test_list_kb());await q.answer()
    @r.callback_query(F.data=='mt_new')
    async def mt_new(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        update_user(ADMIN,state='mt_new:pending');await q.message.edit_text('Yangi test formati:\nNomi | KOD | 08:30 | 09:30');await q.answer()
    @r.callback_query(F.data.startswith('mt_pick:'))
    async def mt_pick(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];set_setting('admin_test_id',tid);t=get_test(tid);await q.message.edit_text(f"{t['name']}\nKod: {t['code']}\nHolat: {t['mode']}\nSavollar: {len(questions_for_test(tid))}",reply_markup=_test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith('mt_open:'))
    async def mt_open(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1]
        with conn() as c:c.execute("UPDATE tests SET mode='open',active=1 WHERE test_id=?",(tid,))
        await q.answer('Test ochildi')
    @r.callback_query(F.data.startswith('mt_close:'))
    async def mt_close(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1]
        with conn() as c:c.execute("UPDATE tests SET mode='closed' WHERE test_id=?",(tid,))
        await q.answer('Test yopildi')
    @r.callback_query(F.data.startswith('mt_link:'))
    async def mt_link(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        t=get_test(q.data.split(':',1)[1]);me=await bot.get_me();await q.message.answer(f"Kod: {t['code']}\nBot: https://t.me/{me.username}?start={t['code']}\nMini App: {webapp_url.rstrip('/')}/test?code={t['code']}");await q.answer()
    @r.callback_query(F.data.startswith('mt_q:'))
    async def mt_q(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        await q.message.edit_text('SAVOLLAR',reply_markup=_questions_kb(q.data.split(':',1)[1]));await q.answer()
    @r.callback_query(F.data.startswith('mt_addq:'))
    async def mt_addq(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        update_user(ADMIN,state=f'mt_addq:{q.data.split(":",1)[1]}');await q.message.answer('Format: № | savol | A | B | C | D | A/B/C/D\nYozma: № | savol | written | javob');await q.answer()
    @r.callback_query(F.data.startswith('mt_key:'))
    async def mt_key(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        update_user(ADMIN,state=f'mt_key:{q.data.split(":",1)[1]}');await q.message.answer('Kalit: 1-A, 2-C, 3-D, 4-B');await q.answer()
    @r.callback_query(F.data.startswith('mt_results:'))
    async def mt_results(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        tid=q.data.split(':',1)[1];a=all_attempts_for_test(tid);lines=['NATIJALAR','']
        for i,x in enumerate(a,1):lines.append(f"{i}. {x['full_name'] or 'Ismsiz'} · {float(x['score'] or 0):.2f} · {x['grade'] or '—'} · {'Yakunlangan' if x['submitted'] else 'Faol'}")
        await q.message.edit_text(('\n'.join(lines) if a else 'Hali qatnashchi yo‘q.')[:3900],reply_markup=_test_kb(tid));await q.answer()
    @r.callback_query(F.data.startswith('mt_pdf:'))
    async def mt_pdf(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        from aiogram.types import FSInputFile
        path=f'/tmp/{secrets.token_hex(6)}.pdf';tid=q.data.split(':',1)[1];_pdf(tid,path);await bot.send_document(ADMIN,FSInputFile(path),caption='Test natijalari PDF');await q.answer('PDF yuborildi')
    @r.callback_query(F.data.startswith('mt_qpick:'))
    async def mt_qpick(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        _,tid,num=q.data.split(':');x=get_question_for_test(tid,int(num));await q.message.answer(f"{num}-savol\n\n{x['question'] if x else 'Topilmadi'}\n\nVariantlar: {json.loads(x['options_json']) if x else []}\nTo‘g‘ri: {x['answer'] if x else '—'}");await q.answer()
    @r.callback_query(F.data=='tf_list')
    async def tf_list(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        us=all_registered_users();await q.message.edit_text('\n'.join(f"{i}. {u['full_name'] or 'Ismsiz'} · {u['telegram_id']}" for i,u in enumerate(us[:100],1)) or 'User yo‘q.',reply_markup=admin_tariff_list());await q.answer()
    @r.callback_query(F.data=='admin_home')
    async def admin_home(q:CallbackQuery):
        if q.from_user.id!=ADMIN:return
        update_user(ADMIN,state='admin');await q.message.answer('Admin boshqaruv paneli.');await q.answer()
    dp.include_router(r)
