from fastapi import Request
import json,secrets,os,reportlab
from datetime import datetime,time,timedelta
from aiogram import Router,F
from aiogram.filters import CommandStart
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo,FSInputFile,ReplyKeyboardMarkup,KeyboardButton
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from xml.sax.saxutils import escape
from . import db
try:
 pdfmetrics.registerFont(TTFont('NurVera',os.path.join(os.path.dirname(reportlab.__file__),'fonts','Vera.ttf')))
 PDF_FONT='NurVera'
except Exception:PDF_FONT='Helvetica'
CORE=ADMIN=BOT=TZ=None;WEBAPP=''
def norm(v):return ' '.join(str(v or '').strip().casefold().split())
def grade(s):
 s=float(s);return 'A+' if s>=90 else 'A' if s>=80 else 'B' if s>=70 else 'C' if s>=60 else 'D' if s>=50 else 'F'
def user_menu():return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Profilim'),KeyboardButton(text='Tariflar')],[KeyboardButton(text='Testni boshlash'),KeyboardButton(text='Test kodini kiritish')],[KeyboardButton(text='Mening natijam'),KeyboardButton(text='Userlar ro‘yxati')],[KeyboardButton(text='Yordam')]],resize_keyboard=True,is_persistent=True)
def tests_kb():
 r=[[InlineKeyboardButton(text=f"{t['name'][:24]} · {t['code']}",callback_data=f't_pick:{t["test_id"]}')] for t in db.all_tests()];r.append([InlineKeyboardButton(text='YANGI TEST',callback_data='t_new')]);return InlineKeyboardMarkup(inline_keyboard=r)
def test_kb(t):return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Savol qo‘shish',callback_data=f't_add:{t}')],[InlineKeyboardButton(text='Oddiy variant',callback_data=f't_choice:{t}'),InlineKeyboardButton(text='Yozma variant',callback_data=f't_written:{t}')],[InlineKeyboardButton(text='Savollar',callback_data=f't_q:{t}'),InlineKeyboardButton(text='Natijalar',callback_data=f't_results:{t}')],[InlineKeyboardButton(text='PDF',callback_data=f't_pdf:{t}'),InlineKeyboardButton(text='Mini App link',callback_data=f't_link:{t}')],[InlineKeyboardButton(text='Guruhga yuborish',callback_data=f't_group:{t}')],[InlineKeyboardButton(text='DOIMO OCHIQ',callback_data=f't_open:{t}')],[InlineKeyboardButton(text='Orqaga',callback_data='t_list')]])
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
 # Published tests remain available at all times; mode is intentionally ignored.
 return bool(t and int(t['active']))
def expired(a,t):
 # No automatic timeout; submit manually or use the admin close action.
 return False
def score(t,a):
 q=db.questions_for_test(t['test_id']);return round(sum(norm(a.get(str(x['number']),' '))==norm(x['answer']) for x in q)/len(q)*100,2) if q else 0
def finalize_expired(a,t):
 q=db.questions_for_test(t['test_id']);answers=json.loads(a['answers_json'] or '{}');sc=round(sum(norm(answers.get(str(x['number']),' '))==norm(x['answer']) for x in q)/len(q)*100,2) if q else 0;gr=grade(sc);db.update_attempt(a['attempt_id'],score=sc,grade=gr,submitted=1,status='submitted',finished_at=datetime.now(TZ).isoformat());return sc,gr

def result_label(a):
 return f"{float(a['score'] or 0):.2f} ball · {a['grade'] or '—'}" if a['submitted'] else 'Natija kutilmoqda'

def build_test_pdf(tid,path):
 t=db.get_test(tid)
 if not t:raise ValueError('Test topilmadi')
 styles=getSampleStyleSheet();styles['Title'].fontName=PDF_FONT
 body=ParagraphStyle('NurTableBody',parent=styles['BodyText'],fontName=PDF_FONT,fontSize=7,leading=9,wordWrap='CJK')
 head=ParagraphStyle('NurTableHead',parent=body,fontSize=7,leading=8)
 headings=['№','Ism-familiya','Telegram ID','Boshlangan','Yakunlangan','Ball','Baho','Holat']
 rows=[[Paragraph('<b>'+escape(x)+'</b>',head) for x in headings]]
 for i,a in enumerate(db.all_attempts_for_test(tid),1):
  name=escape(str(a['full_name'] or '—'))
  started=escape(str(a['started_at'] or '—')[:19].replace('T',' '))
  finished=escape(str(a['finished_at'] or '—')[:19].replace('T',' '))
  score_text=f"{float(a['score'] or 0):.2f}" if a['submitted'] else '—'
  rows.append([str(i),Paragraph(name,body),str(a['telegram_id']),Paragraph(started,body),Paragraph(finished,body),score_text,escape(str(a['grade'] or '—')) if a['submitted'] else '—','Yakunlangan' if a['submitted'] else 'Faol'])
 doc=SimpleDocTemplate(path,pagesize=landscape(A4),rightMargin=18,leftMargin=18,topMargin=24,bottomMargin=24)
 tab=Table(rows,repeatRows=1,colWidths=[28,175,70,100,100,48,48,72],hAlign='LEFT')
 tab.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),PDF_FONT),('GRID',(0,0),(-1,-1),.45,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9edf3')),('FONTSIZE',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
 title=Paragraph(escape(f"NUR O‘QIW ORAYI — {t['name']}"),styles['Title'])
 subtitle=Paragraph(escape(f"Kod: {t['code']} · Savollar: {len(db.questions_for_test(tid))} · Qatnashchilar: {len(rows)-1}"),styles['Normal'])
 doc.build([title,subtitle,Spacer(1,10),tab])

def _locked_attempt(c, test_id, telegram_id):
 suffix = " FOR UPDATE" if db.USE_POSTGRES else ""
 return c.execute("SELECT * FROM test_attempts WHERE test_id=? AND telegram_id=?" + suffix, (str(test_id), int(telegram_id))).fetchone()

def save_answer_atomically(test_id, telegram_id, number, value):
 """Serialize answer writes so simultaneous requests cannot overwrite each other."""
 with db.conn() as c:
  if not db.USE_POSTGRES:
   c.execute("BEGIN IMMEDIATE")
  a = _locked_attempt(c, test_id, telegram_id)
  if not a or not a["started_at"]:
   return "not_started"
  if a["submitted"]:
   return "submitted"
  answers = json.loads(a["answers_json"] or "{}")
  key = str(number)
  if key in answers:
   return "locked"
  answers[key] = value
  c.execute("UPDATE test_attempts SET answers_json=? WHERE attempt_id=?", (json.dumps(answers, ensure_ascii=False), a["attempt_id"]))
 return "ok"

def finish_attempt_atomically(test_id, telegram_id, questions, finished_at):
 """Lock the attempt while scoring and submitting it; never overwrite an existing result."""
 with db.conn() as c:
  if not db.USE_POSTGRES:
   c.execute("BEGIN IMMEDIATE")
  a = _locked_attempt(c, test_id, telegram_id)
  if not a or not a["started_at"]:
   return ("not_started", None, None)
  if a["submitted"]:
   return ("already_submitted", float(a["score"] or 0), a["grade"] or "")
  answers = json.loads(a["answers_json"] or "{}")
  correct = sum(1 for q in questions if norm(answers.get(str(q["number"]), "")) == norm(q["answer"]))
  score_value = round(correct / len(questions) * 100, 2) if questions else 0
  grade_value = grade(score_value)
  c.execute("UPDATE test_attempts SET score=?,grade=?,submitted=1,status='submitted',finished_at=? WHERE attempt_id=? AND submitted=0",
            (score_value, grade_value, finished_at, a["attempt_id"]))
 return ("ok", score_value, grade_value)

def register(core,dp,bot,webapp_url):
 global CORE,ADMIN,BOT,TZ,WEBAPP
 CORE,ADMIN,BOT,TZ,WEBAPP=core,core.ADMIN,bot,core.TZ,webapp_url;r=Router(name='test_v3')
 async def auth(req):
  raw=req.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or req.query_params.get('initData','');tid=CORE.telegram_user(raw)
  if tid and raw:
   try:
    from urllib.parse import parse_qsl
    profile=json.loads(dict(parse_qsl(raw,keep_blank_values=True)).get('user','{}'))
    if profile.get('photo_url'):db.update_user(tid,telegram_photo=str(profile['photo_url']))
   except Exception:pass
  return tid,db.get_user(tid) if tid else None
 @core.app.get('/api/test/profile')
 async def profile_api(req:Request):
  tid,u=await auth(req)
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  with db.conn() as c:
   rows=c.execute("SELECT a.test_id,t.name,t.code,a.started_at,a.finished_at,a.score,a.grade,a.submitted FROM test_attempts a LEFT JOIN tests t ON t.test_id=a.test_id WHERE a.telegram_id=? ORDER BY COALESCE(a.finished_at,a.started_at) DESC",(tid,)).fetchall()
  history=[{'test_id':x['test_id'],'test_name':x['name'] or 'Test','code':x['code'] or '', 'started_at':x['started_at'],'finished_at':x['finished_at'],'score':float(x['score'] or 0),'grade':x['grade'] or '', 'submitted':bool(x['submitted'])} for x in rows]
  return {'ok':True,'full_name':u['full_name'] or '','photo_url':u['telegram_photo'] or '','tests':history}
 @core.app.get('/api/test/ranking')
 async def ranking_api(req:Request):
  tid,u=await auth(req);code=req.query_params.get('code','').strip()
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  t=db.get_test_by_code(code)
  if not t:return {'ok':False,'error':'test_not_found'}
  rows=[x for x in db.all_attempts_for_test(t['test_id']) if x['submitted']]
  rows.sort(key=lambda x:(-float(x['score'] or 0),str(x['finished_at'] or '9999')))
  top=[{'rank':i+1,'full_name':x['full_name'] or 'Ismsiz','photo_url':x['telegram_photo'] or '', 'score':float(x['score'] or 0),'grade':x['grade'] or '', 'finished_at':x['finished_at']} for i,x in enumerate(rows[:15])]
  return {'ok':True,'test_name':t['name'],'code':t['code'],'total':len(rows),'ranking':top}
 @core.app.get('/api/test/state')
 async def state(req: Request):
  tid,u=await auth(req);c=req.query_params.get('code','').strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  if not t:return {'ok':False,'error':'test_not_found'}
  if not db.questions_for_test(t['test_id']):return {'ok':False,'error':'test_not_ready','test_name':t['name']}
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
  if not u['full_name'] or u['test_id']!=t['test_id'] or not opened(t):return {'ok':False,'error':'test_not_started'}
  a=db.get_attempt(t['test_id'],tid)
  if not a or not a['started_at'] or a['submitted']:return {'ok':False,'error':'test_not_started'}
  return {'ok':True,'questions':[{'id':q['number'],'question':q['question'] or '', 'options':(json.loads(q['options_json'] or '[]') if q['options_json'] else []) or ['A','B','C','D'], 'kind':q['kind'],'image_url':q['image_url'] or ''} for q in db.questions_for_test(t['test_id'])]}
 @core.app.post('/api/test/answer')
 async def answer(p:dict, request: Request):
  raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or p.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;c=str(p.get('code','')).strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t or not u['full_name']:return {'ok':False,'error':'not_authorized'}
  if u['test_id']!=t['test_id']:return {'ok':False,'error':'test_not_started'}
  a=db.get_attempt(t['test_id'],tid)
  if not a or not a['started_at']:return {'ok':False,'error':'test_not_started'}
  if a['submitted']:return {'ok':False,'error':'already_submitted'}
  if expired(a,t):
   sc,gr=finalize_expired(a,t);return {'ok':False,'error':'already_submitted','score':sc,'grade':gr}
  if not opened(t):return {'ok':False,'error':'test_closed'}
  q=db.get_question_for_test(t['test_id'],p.get('question_id'))
  if not q:return {'ok':False,'error':'question_not_found'}
  v=str(p.get('answer','')).strip()
  if q['kind']=='written':
   if not v:return {'ok':False,'error':'invalid_answer'}
  else:
   v=v.upper()
   if v not in ('A','B','C','D'):return {'ok':False,'error':'invalid_answer'}
  saved=save_answer_atomically(t['test_id'],tid,q['number'],v)
  if saved=='locked':return {'ok':False,'error':'answer_locked'}
  if saved=='submitted':return {'ok':False,'error':'already_submitted'}
  if saved!='ok':return {'ok':False,'error':'test_not_started'}
  return {'ok':True,'number':q['number']}
 @core.app.post('/api/test/finish')
 async def finish(p:dict, request: Request):
  raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or p.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;c=str(p.get('code','')).strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t or not u['full_name']:return {'ok':False,'error':'not_authorized'}
  if u['test_id']!=t['test_id']:return {'ok':False,'error':'test_not_started'}
  a=db.get_attempt(t['test_id'],tid)
  if not a or not a['started_at']:return {'ok':False,'error':'test_not_started'}
  if a['submitted']:return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade']}
  if expired(a,t):
   sc,gr=finalize_expired(a,t);return {'ok':True,'score':sc,'grade':gr,'full_name':u['full_name'],'test_name':t['name']}
  if not opened(t):return {'ok':False,'error':'test_closed'}
  status,sc,gr=finish_attempt_atomically(t['test_id'],tid,db.questions_for_test(t['test_id']),datetime.now(TZ).isoformat())
  if status=='not_started':return {'ok':False,'error':'test_not_started'}
  if status=='already_submitted':return {'ok':False,'error':'already_submitted','score':sc,'grade':gr}
  return {'ok':True,'score':sc,'grade':gr,'full_name':u['full_name'],'test_name':t['name']}
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
  u=db.ensure_user(m.from_user.id);t=db.get_test(u['test_id']) if u['test_id'] else None;a=db.get_attempt(t['test_id'],m.from_user.id) if t else None;res=f"{float(a['score'] or 0):.2f} ball · {a['grade'] or '—'}" if a and a['submitted'] else 'Yakunlanmagan'
  url=f"{WEBAPP.rstrip('/')}/profile";mk=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='MINI APP PROFILIM',web_app=WebAppInfo(url=url))]])
  await m.answer(f"PROFILIM\n\nIsm-familiya: {u['full_name'] or '—'}\nTest: {t['name'] if t else 'Tanlanmagan'}\nKod: {t['code'] if t else '—'}\nNatija: {res}",reply_markup=mk)
 @r.message(F.text=='Userlar ro‘yxati')
 async def user_ranking(m:Message):
  u=db.get_user(m.from_user.id);t=db.get_test(u['test_id']) if u and u['test_id'] else None
  if not t:return await m.answer('Avval test kodini kiriting, keyin reytingni oching.')
  url=f"{WEBAPP.rstrip('/')}/ranking?code={t['code']}";mk=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TOP 15 REYTING',web_app=WebAppInfo(url=url))]])
  await m.answer(f"{t['name']} · TOP 15 reyting",reply_markup=mk)
 @r.message(F.text=='Testni boshlash')
 async def start(m:Message):
  u=db.get_user(m.from_user.id);t=db.get_test(u['test_id']) if u and u['test_id'] else None
  if not t or not int(t['active']) or not u['code_ok']:
   if t and not int(t['active']):db.update_user(m.from_user.id,test_id='',code_ok=0,state='code')
   return await m.answer('Avval ochiq test kodini kiriting va testni tanlang.',reply_markup=user_menu())
  url=f"{WEBAPP.rstrip('/')}/test?code={t['code']}";mk=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='TESTNI BOSHLASH',web_app=WebAppInfo(url=url))],[InlineKeyboardButton(text='Linkni ochish',url=url)]])
  await m.answer(f"{t['name']}\n\nTest kodi: {t['code']}\n\nTESTNI BOSHLASH tugmasini bosing.",reply_markup=mk)
 @r.message(F.text=='Test kodini kiritish')
 async def enter(m:Message):db.update_user(m.from_user.id,state='test_code',code_ok=0);await m.answer('Testning kirish kodini kiriting:')
 @r.message(F.text=='Mening natijam')
 async def result(m:Message):
  u=db.get_user(m.from_user.id);t=db.get_test(u['test_id']) if u and u['test_id'] else None;a=db.get_attempt(t['test_id'],m.from_user.id) if t else None
  if not t or not a:return await m.answer('Hali test tanlanmagan.')
  await m.answer(f"NATIJAM\n\nTest: {t['name']}\n" + (f"Ball: {float(a['score'] or 0):.2f}\nBaho: {a['grade'] or '—'}" if a['submitted'] else 'Holat: Hali yakunlanmagan. Testni tugatgandan keyin ball chiqadi.'))
 @r.message(F.text=='Yordam')
 async def help_(m:Message):await m.answer('Test kodini kiriting, keyin Testni boshlash tugmasini bosing.')
 @r.message(F.text=='Tariflar')
 async def tariffs(m:Message):await m.answer('TARIFLAR\n\nDEFAULT\nOddiy test qatnashchisi.\n\nPREMIUM\nKengaytirilgan statistika.')
 @r.message(F.from_user.id==ADMIN, F.text.startswith('PDF '))
 async def pdf_by_code(m:Message):
  parts=m.text.split(maxsplit=1);code=parts[1].strip() if len(parts)>1 else ''
  t=db.get_test_by_code(code)
  if not t:return await m.answer('Bu kod bilan faol test topilmadi.')
  path=f'/tmp/{secrets.token_hex(8)}.pdf';build_test_pdf(t['test_id'],path)
  await BOT.send_document(m.chat.id,FSInputFile(path),caption=f"PDF NATIJA · {t['name']} · kod {t['code']}")
 @r.message(F.from_user.id==ADMIN)
 async def admin_text(m:Message):
  u=db.ensure_user(ADMIN);s=u['state'] or 'admin';txt=(m.text or '').strip()
  if txt in {'Test sozlamalari','Ishtirokchilar','PDF natijalar'}:return await m.answer('TESTLAR',reply_markup=tests_kb())
  if s=='new_code':
   if not txt or ' ' in txt:return await m.answer('Kodni bitta so‘z qilib kiriting. Masalan: MAT2026')
   if db.test_code_exists(txt):return await m.answer('Bu kod avval ishlatilgan. Boshqa kod tanlang.')
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
   if db.test_code_exists(d['code']):return await q.answer('Bu kod avval ishlatilgan. Boshqa kod tanlang.',show_alert=True)
   if len(d['answers'])!=total:return await q.answer('Barcha to‘g‘ri javoblar kiritilmagan. Test saqlanmadi.',show_alert=True)
   t=db.create_test_with_answers(d['name'],d['code'],d['answers'])
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
  with db.conn() as c:c.execute("UPDATE tests SET mode='open',active=1 WHERE test_id=?",(tid,))
  await q.answer('Testlar doimo ochiq qoladi')
 @r.callback_query(F.data.startswith('t_q:'))
 async def tq(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];qs=db.questions_for_test(tid);text='SAVOLLAR\n\n'+('\n'.join(f"{x['number']}. To‘g‘ri javob: {x['answer']}" for x in qs) if qs else 'Savol yo‘q');await q.message.edit_text(text[:3900],reply_markup=test_kb(tid));await q.answer()
 @r.callback_query(F.data.startswith('t_results:'))
 async def tr(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];rows=db.all_attempts_for_test(tid);lines=['NATIJALAR',''];
  for i,x in enumerate(rows,1):lines.append(f"{i}. {x['full_name'] or 'Ismsiz'} · {result_label(x)} · {'Yakunlangan' if x['submitted'] else 'Faol'}")
  text='\n'.join(lines) if rows else 'Hali qatnashchi yo‘q.';await q.message.edit_text(text[:3900],reply_markup=test_kb(tid));await q.answer()
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
  tid=q.data.split(':',1)[1];t=db.get_test(tid);path=f'/tmp/{secrets.token_hex(8)}.pdf';build_test_pdf(tid,path);await BOT.send_document(ADMIN,FSInputFile(path),caption=f"PDF NATIJA — {t['name']} — {t['code']}")
 dp.include_router(r)
