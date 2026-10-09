from fastapi import Request
import json,secrets
from datetime import datetime,time,timedelta
from aiogram import Router,F
from aiogram.filters import CommandStart
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo,FSInputFile,ReplyKeyboardMarkup,KeyboardButton
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
from reportlab.lib.styles import getSampleStyleSheet
from . import db
CORE=ADMIN=BOT=TZ=None;WEBAPP=''
def norm(v):return ' '.join(str(v or '').strip().casefold().split())
def grade(s):
 s=float(s);return 'A+' if s>=90 else 'A' if s>=80 else 'B' if s>=70 else 'C' if s>=60 else 'D' if s>=50 else 'F'
def user_menu():return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Profilim'),KeyboardButton(text='Tariflar')],[KeyboardButton(text='Testni boshlash'),KeyboardButton(text='Test kodini kiritish')],[KeyboardButton(text='Mening natijam'),KeyboardButton(text='Yordam')]],resize_keyboard=True,is_persistent=True)
def tests_kb():
 r=[[InlineKeyboardButton(text=f"{t['name'][:24]} · {t['code']}",callback_data=f't_pick:{t["test_id"]}')] for t in db.all_tests()];r.append([InlineKeyboardButton(text='YANGI TEST',callback_data='t_new')]);return InlineKeyboardMarkup(inline_keyboard=r)
def test_kb(t):return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Savol qo‘shish',callback_data=f't_add:{t}')],[InlineKeyboardButton(text='Oddiy variant',callback_data=f't_choice:{t}'),InlineKeyboardButton(text='Yozma variant',callback_data=f't_written:{t}')],[InlineKeyboardButton(text='Savollar',callback_data=f't_q:{t}'),InlineKeyboardButton(text='Natijalar',callback_data=f't_results:{t}')],[InlineKeyboardButton(text='PDF',callback_data=f't_pdf:{t}'),InlineKeyboardButton(text='Mini App link',callback_data=f't_link:{t}')],[InlineKeyboardButton(text='Guruhga yuborish',callback_data=f't_group:{t}')],[InlineKeyboardButton(text='OCHISH',callback_data=f't_open:{t}'),InlineKeyboardButton(text='YOPISH',callback_data=f't_close:{t}')],[InlineKeyboardButton(text='Orqaga',callback_data='t_list')]])
def type_kb(t):return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ODDIY VARIANT',callback_data=f't_choice:{t}')],[InlineKeyboardButton(text='YOZMA VARIANT',callback_data=f't_written:{t}')]])
def abcd(t,n):return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=x,callback_data=f't_ans:{t}:{n}:{x}') for x in 'ABCD']])
def new_answer_kb():return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=x,callback_data=f't_new_ans:{x}') for x in 'ABCD']])
def draft():
 try:return json.loads(db.get_setting('admin_question_draft','{}') or '{}')
 except:return {}
def save_draft(x):db.set_setting('admin_question_draft',json.dumps(x,ensure_ascii=False))
def clear_draft():db.set_setting('admin_question_draft','{}')
def ast(s):db.update_user(ADMIN,state=s)
def opened(t):
 # Tests stay available at all times unless explicitly closed by the admin.
 return bool(t and int(t['active']) and str(t['mode'])!='closed')
def expired(a,t):
 # No automatic timeout; submit manually or use the admin close action.
 return False
def score(t,a):
 q=db.questions_for_test(t['test_id']);return round(sum(norm(a.get(str(x['number']),' '))==norm(x['answer']) for x in q)/len(q)*100,2) if q else 0
def finalize_expired(a,t):
 q=db.questions_for_test(t['test_id']);answers=json.loads(a['answers_json'] or '{}');sc=round(sum(norm(answers.get(str(x['number']),' '))==norm(x['answer']) for x in q)/len(q)*100,2) if q else 0;gr=grade(sc);db.update_attempt(a['attempt_id'],score=sc,grade=gr,submitted=1,status='submitted',finished_at=datetime.now(TZ).isoformat());return sc,gr

def register(core,dp,bot,webapp_url):
 global CORE,ADMIN,BOT,TZ,WEBAPP
 CORE,ADMIN,BOT,TZ,WEBAPP=core,core.ADMIN,bot,core.TZ,webapp_url;r=Router(name='test_v3')
 async def auth(req):
  raw=req.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or req.query_params.get('initData','');tid=CORE.telegram_user(raw);return tid,db.get_user(tid) if tid else None
 @core.app.get('/api/test/state')
 async def state(req: Request):
  tid,u=await auth(req);c=req.query_params.get('code','').strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  if not t:return {'ok':False,'error':'test_not_found'}
  if u['test_id']!=t['test_id']:db.update_user(tid,test_id=t['test_id'],code_ok=1,state='ready');u=db.get_user(tid)
  if not u['full_name']:return {'ok':False,'error':'registration_required','test_name':t['name']}
  a=db.ensure_attempt(t['test_id'],tid)
  if a['submitted']:return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade'],'test_name':t['name'],'full_name':u['full_name']}
  if not a['started_at']:
   if not opened(t):return {'ok':False,'error':'test_closed','test_name':t['name']}
   db.update_attempt(a['attempt_id'],started_at=datetime.now(TZ).isoformat(),status='active');a=db.get_attempt(t['test_id'],tid)
  if expired(a,t):
   sc,gr=finalize_expired(a,t);return {'ok':False,'error':'already_submitted','score':sc,'grade':gr,'test_name':t['name'],'full_name':u['full_name']}
  return {'ok':True,'full_name':u['full_name'],'answers':json.loads(a['answers_json'] or '{}'),'ends_at':None,'test_name':t['name'],'test_code':t['code'],'total_questions':len(db.questions_for_test(t['test_id']))}
 @core.app.get('/api/test/questions')
 async def questions(req: Request):
  tid,u=await auth(req);c=req.query_params.get('code','').strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
  return {'ok':True,'questions':[{'id':q['number'],'question':q['question'] or '', 'options':(json.loads(q['options_json'] or '[]') if q['options_json'] else []) or ['A','B','C','D'], 'kind':q['kind'],'image_url':q['image_url'] or ''} for q in db.questions_for_test(t['test_id'])]}
 @core.app.post('/api/test/answer')
 async def answer(p:dict, request: Request):
  raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or p.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;c=str(p.get('code','')).strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
  a=db.ensure_attempt(t['test_id'],tid)
  if a['submitted']:return {'ok':False,'error':'already_submitted'}
  if expired(a,t):
   sc,gr=finalize_expired(a,t);return {'ok':False,'error':'already_submitted','score':sc,'grade':gr}
  if not opened(t):return {'ok':False,'error':'test_closed'}
  q=db.get_question_for_test(t['test_id'],p.get('question_id'))
  if not q:return {'ok':False,'error':'question_not_found'}
  ans=json.loads(a['answers_json'] or '{}');k=str(q['number'])
  if k in ans:return {'ok':False,'error':'answer_locked','correct':norm(ans[k])==norm(q['answer'])}
  v=str(p.get('answer','')).strip()
  if q['kind']=='written':
   if not v:return {'ok':False,'error':'invalid_answer'}
  else:
   v=v.upper()
   if v not in 'ABCD':return {'ok':False,'error':'invalid_answer'}
  ans[k]=v;db.save_attempt_answers(a['attempt_id'],ans);return {'ok':True,'correct':norm(v)==norm(q['answer']),'number':q['number']}
 @core.app.post('/api/test/finish')
 async def finish(p:dict, request: Request):
  raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or p.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;c=str(p.get('code','')).strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
  a=db.ensure_attempt(t['test_id'],tid)
  if a['submitted']:return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade']}
  if expired(a,t):
   sc,gr=finalize_expired(a,t);return {'ok':True,'score':sc,'grade':gr,'full_name':u['full_name'],'test_name':t['name']}
  if not opened(t):return {'ok':False,'error':'test_closed'}
  sc=score(t,json.loads(a['answers_json'] or '{}'));gr=grade(sc);db.update_attempt(a['attempt_id'],score=sc,grade=gr,submitted=1,status='submitted',finished_at=datetime.now(TZ).isoformat());return {'ok':True,'score':sc,'grade':gr,'full_name':u['full_name'],'test_name':t['name']}
 @r.message(CommandStart(deep_link=True))
 async def deep(m:Message,command):
  t=db.get_test_by_code((command.args or '').strip())
  if not t:return await m.answer('Bu test kodi topilmadi.')
  u=db.ensure_user(m.from_user.id);db.update_user(m.from_user.id,test_id=t['test_id'],code_ok=1,state='ready' if u['full_name'] else 'name');db.ensure_attempt(t['test_id'],m.from_user.id);u=db.get_user(m.from_user.id)
  if not u['full_name']:
   return await m.answer(f"{t['name']}\n\nIsm-familiyangizni yozing yoki Telegram ismingiz bilan davom eting:",reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Telegram ismim bilan davom etish')]],resize_keyboard=True,one_time_keyboard=True))
  return await m.answer(f"{t['name']}\n\nTest tanlandi. Testni boshlash tugmasini bosing.",reply_markup=user_menu())
 @r.message(F.text=='Profilim')
 async def profile(m:Message):
  u=db.ensure_user(m.from_user.id);t=db.get_test(u['test_id']) if u['test_id'] else None;a=db.get_attempt(t['test_id'],m.from_user.id) if t else None;res=f"{float(a['score'] or 0):.2f} ball · {a['grade'] or '—'}" if a and a['submitted'] else 'Yakunlanmagan';await m.answer(f"PROFILIM\n\nIsm-familiya: {u['full_name'] or '—'}\nTelefon: {u['phone'] or '—'}\nTest: {t['name'] if t else 'Tanlanmagan'}\nKod: {t['code'] if t else '—'}\nNatija: {res}")
 @r.message(F.text=='Testni boshlash')
 async def start(m:Message):
  u=db.get_user(m.from_user.id);t=db.get_test(u['test_id']) if u and u['test_id'] else None
  if not t or not u['code_ok']:return await m.answer('Avval test kodini kiritib, testni tanlang.',reply_markup=user_menu())
  url=f"{WEBAPP.rstrip('/')}/test?code={t['code']}";mk=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',web_app=WebAppInfo(url=url))],[InlineKeyboardButton(text='Linkni ochish',url=url)]])
  await m.answer(f"{t['name']}\n\nTest kodi: {t['code']}\n\nTESTNI BOSHLASH tugmasini bosing.",reply_markup=mk)
 @r.message(F.text=='Test kodini kiritish')
 async def enter(m:Message):db.update_user(m.from_user.id,state='test_code',code_ok=0);await m.answer('Testning kirish kodini kiriting:')
 @r.message(F.text=='Mening natijam')
 async def result(m:Message):
  u=db.get_user(m.from_user.id);t=db.get_test(u['test_id']) if u and u['test_id'] else None;a=db.get_attempt(t['test_id'],m.from_user.id) if t else None
  if not t or not a:return await m.answer('Hali test tanlanmagan.')
  await m.answer(f"NATIJAM\n\nTest: {t['name']}\nBall: {float(a['score'] or 0):.2f}\nBaho: {a['grade'] or 'Hali yakunlanmagan'}")
 @r.message(F.text=='Yordam')
 async def help_(m:Message):await m.answer('Test kodini kiriting, keyin Testni boshlash tugmasini bosing.')
 @r.message(F.text=='Tariflar')
 async def tariffs(m:Message):await m.answer('TARIFLAR\n\nDEFAULT\nOddiy test qatnashchisi.\n\nPREMIUM\nKengaytirilgan statistika.')
 @r.message(F.from_user.id==ADMIN)
 async def admin_text(m:Message):
  u=db.ensure_user(ADMIN);s=u['state'] or 'admin';txt=(m.text or '').strip()
  if txt in {'Test sozlamalari','Ishtirokchilar','PDF natijalar'}:return await m.answer('TESTLAR',reply_markup=tests_kb())
  if s=='new_code':
   if not txt or ' ' in txt:return await m.answer('Kodni bitta so‘z qilib kiriting. Masalan: MAT2026')
   if db.get_test_by_code(txt):return await m.answer('Bu kod band. Boshqa kod tanlang.')
   save_draft({'code':txt});ast('new_name');return await m.answer('Test nomini kiriting:')
  if s=='new_name':
   if not txt:return await m.answer('Test nomini kiriting:')
   d=draft();d['name']=txt;save_draft(d);ast('new_count');return await m.answer('Testda jami nechta savol bo‘ladi? (1–200)')
  if s=='new_count':
   try:n=int(txt);assert 1<=n<=200
   except:return await m.answer('Savollar sonini 1 dan 200 gacha butun son bilan kiriting.')
   d=draft();d['count']=n;d['answers']=[];save_draft(d);ast('new_answer')
   return await m.answer(f'1/{n}-savolning to‘g‘ri javobini tanlang:',reply_markup=new_answer_kb())
  if s.startswith('choice_num:'):
   try:n=int(txt);assert n>0
   except:return await m.answer('Faqat savol raqamini kiriting. Masalan: 1')
   tid=s.split(':',1)[1];save_draft({'test_id':tid,'number':n,'kind':'choice'});ast('admin');return await m.answer(f'{n}-savol uchun TO‘G‘RI JAVOBNI tanlang:',reply_markup=abcd(tid,n))
  if s.startswith('written_num:'):
   try:n=int(txt);assert n>0
   except:return await m.answer('Faqat savol raqamini kiriting. Masalan: 1')
   tid=s.split(':',1)[1];save_draft({'test_id':tid,'number':n,'kind':'written'});ast('written_answer');return await m.answer(f'{n}-savol uchun to‘g‘ri yozma javobni kiriting:')
  if s=='written_answer':
   d=draft();db.upsert_test_question(d['test_id'],int(d['number']),'',[],txt,'written');clear_draft();ast('admin');return await m.answer(f"{d['number']}-savol saqlandi.",reply_markup=test_kb(d['test_id']))
 @r.callback_query(F.data=='t_list')
 async def tl(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  await q.message.edit_text('TESTLAR',reply_markup=tests_kb());await q.answer()
 @r.callback_query(F.data.startswith('t_new_ans:'))
 async def new_answer(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  d=draft();u=db.get_user(ADMIN);letter=q.data.rsplit(':',1)[-1]
  if letter not in 'ABCD' or not d.get('code') or not d.get('name') or not d.get('count') or (u and u['state']!='new_answer'):
   return await q.answer('Test yaratish sessiyasi topilmadi. Qaytadan boshlang.',show_alert=True)
  d.setdefault('answers',[]).append(letter);save_draft(d)
  done=len(d['answers']);total=int(d['count'])
  if done<total:
   await q.message.answer(f'{done+1}/{total}-savolning to‘g‘ri javobini tanlang:',reply_markup=new_answer_kb())
   return await q.answer(f'{done}/{total} saqlandi')
  try:
   if db.get_test_by_code(d['code']):return await q.answer('Bu kod band. Test yaratilmaydi.',show_alert=True)
   t=db.create_test(d['name'],d['code'],'00:00','23:59','open')
   for n,ans in enumerate(d['answers'],1):
    db.upsert_test_question(t['test_id'],n,'',['A','B','C','D'],ans,'choice')
   clear_draft();ast('admin')
   await q.message.answer(f"TEST SAQLANDI\n\n{t['name']}\nKod: {t['code']}\nSavollar: {total}\nHolat: DOIMO OCHIQ",reply_markup=test_kb(t['test_id']))
   await q.answer('Test saqlandi')
  except Exception:
   import logging;logging.getLogger('nur-oqiw').exception('create test from answer key')
   return await q.answer('Test saqlanmadi. Qaytadan urinib ko‘ring.',show_alert=True)
 @r.callback_query(F.data=='t_new')
 async def tn(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  clear_draft();ast('new_code');await q.message.answer('Yangi testning KIRISH KODINI qo‘lda tanlang.\nMasalan: MAT2026');await q.answer()
 @r.callback_query(F.data.startswith('t_pick:'))
 async def tp(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];t=db.get_test(tid)
  if not t:return await q.answer('Test topilmadi',show_alert=True)
  db.set_setting('admin_test_id',tid);await q.message.edit_text(f"{t['name']}\n\nKod: {t['code']}\nSavollar: {len(db.questions_for_test(tid))}",reply_markup=test_kb(tid));await q.answer()
 @r.callback_query(F.data.startswith('t_add:'))
 async def ta(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  await q.message.answer('Savol turini tanlang:',reply_markup=type_kb(q.data.split(':',1)[1]));await q.answer()
 @r.callback_query(F.data.startswith('t_choice:'))
 async def tc(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];clear_draft();ast('choice_num:'+tid);await q.message.answer('Faqat savol raqamini kiriting. Masalan: 1');await q.answer()
 @r.callback_query(F.data.startswith('t_written:'))
 async def tw(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];clear_draft();ast('written_num:'+tid);await q.message.answer('Faqat savol raqamini kiriting. Masalan: 1');await q.answer()
 @r.callback_query(F.data.startswith('t_ans:'))
 async def tans(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  _,tid,n,letter=q.data.split(':');d=draft()
  if d.get('test_id')!=tid or int(d.get('number',-1))!=int(n):return await q.answer('Savol sessiyasi eskirgan.',show_alert=True)
  db.upsert_test_question(tid,int(n),'',['A','B','C','D'],letter,'choice');clear_draft();ast('admin');await q.message.answer(f'{n}-savol saqlandi. To‘g‘ri javob: {letter}',reply_markup=test_kb(tid));await q.answer('Saqlandi')
 @r.callback_query(F.data.startswith('t_open:'))
 async def to(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1]
  with db.conn() as c:c.execute("UPDATE tests SET mode='open',active=1 WHERE test_id=?",(tid,))
  await q.answer('Test ochildi')
 @r.callback_query(F.data.startswith('t_close:'))
 async def tx(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1]
  with db.conn() as c:
   c.execute("UPDATE tests SET mode='closed' WHERE test_id=?",(tid,))
  for a in db.all_attempts_for_test(tid):
   if not a['submitted']:
    answers=json.loads(a['answers_json'] or '{}');qs=db.questions_for_test(tid);sc=round(sum(norm(answers.get(str(x['number']),' '))==norm(x['answer']) for x in qs)/len(qs)*100,2) if qs else 0;db.update_attempt(a['attempt_id'],score=sc,grade=grade(sc),submitted=1,status='submitted',finished_at=datetime.now(TZ).isoformat())
  await q.answer('Test yopildi')
 @r.callback_query(F.data.startswith('t_q:'))
 async def tq(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];qs=db.questions_for_test(tid);text='SAVOLLAR\n\n'+('\n'.join(f"{x['number']}. To‘g‘ri javob: {x['answer']}" for x in qs) if qs else 'Savol yo‘q');await q.message.edit_text(text[:3900],reply_markup=test_kb(tid));await q.answer()
 @r.callback_query(F.data.startswith('t_results:'))
 async def tr(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];rows=db.all_attempts_for_test(tid);text='NATIJALAR\n\n'+('\n'.join(f"{i}. {x['full_name'] or 'Ismsiz'} · {float(x['score'] or 0):.2f} · {x['grade'] or '—'} · {"Yakunlangan" if x['submitted'] else "Faol"}" for i,x in enumerate(rows,1)) if rows else 'Hali qatnashchi yo‘q.');await q.message.edit_text(text[:3900],reply_markup=test_kb(tid));await q.answer()
 @r.callback_query(F.data.startswith('t_link:'))
 async def link(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  t=db.get_test(q.data.split(':',1)[1]);me=await BOT.get_me();await q.message.answer(f"KOD: {t['code']}\nBOT: https://t.me/{me.username}?start={t['code']}\nMINI APP: {WEBAPP.rstrip('/')}/test?code={t['code']}");await q.answer()
 @r.callback_query(F.data.startswith('t_group:'))
 async def group(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  t=db.get_test(q.data.split(':',1)[1]);me=await BOT.get_me();await q.message.answer(f"{t['name']}\n\nTest kodi: {t['code']}\nBot linki: https://t.me/{me.username}?start={t['code']}\n\nSavollar PDF/materialda beriladi. Mini App faqat A/B/C/D javoblarini qabul qiladi.");await q.answer()
 @r.callback_query(F.data.startswith('t_pdf:'))
 async def pdf(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  await q.answer('PDF tayyorlanmoqda...')
  tid=q.data.split(':',1)[1];t=db.get_test(tid);rows=[['№','Ism Familiya','Telegram ID','Kirish','Tugash','Ball','Baho','Holat']]
  for i,a in enumerate(db.all_attempts_for_test(tid),1):rows.append([str(i),a['full_name'] or '—',str(a['telegram_id']),str(a['started_at'] or '—')[:16],str(a['finished_at'] or '—')[:16],f"{float(a['score'] or 0):.2f}",a['grade'] or '—','Yakunlangan' if a['submitted'] else 'Faol'])
  path=f'/tmp/{secrets.token_hex(8)}.pdf';st=getSampleStyleSheet();doc=SimpleDocTemplate(path,pagesize=landscape(A4));tab=Table(rows,repeatRows=1);tab.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eeeeee')),('FONTSIZE',(0,0),(-1,-1),8)]));doc.build([Paragraph(f"NUR O‘QIW ORAYI — {t['name']}",st['Title']),Spacer(1,8),tab]);await BOT.send_document(ADMIN,FSInputFile(path),caption=f"PDF NATIJA — {t['name']} — {t['code']}");await q.answer('PDF yuborildi')
 dp.include_router(r)
