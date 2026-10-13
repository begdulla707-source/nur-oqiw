from fastapi import Request
import asyncio
import json,secrets,os,reportlab,urllib.request,urllib.error,urllib.parse,logging
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
def user_menu():return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Profilim'),KeyboardButton(text='Tariflar')],[KeyboardButton(text='Testni boshlash'),KeyboardButton(text='Test kodini kiritish')],[KeyboardButton(text='Mening natijam'),KeyboardButton(text='Yordam')]],resize_keyboard=True,is_persistent=True)
def tests_kb():
 r=[]
 for t in db.all_tests():
  state='OCHIQ' if int(t['active']) else 'YOPIQ'
  r.append([InlineKeyboardButton(text=f"{state} | {t['name'][:20]} | {t['code']}",callback_data=f't_pick:{t["test_id"]}')])
 r.append([InlineKeyboardButton(text='YANGI TEST',callback_data='t_new')])
 r.append([InlineKeyboardButton(text='UMUMIY REYTING ARXIVI',callback_data='t_archive_results')])
 r.append([InlineKeyboardButton(text='TEKSHIRISH',callback_data='t_check_list')])
 return InlineKeyboardMarkup(inline_keyboard=r)
def test_kb(t):
 test=db.get_test(t);active=bool(test and int(test['active']))
 toggle=InlineKeyboardButton(text='TESTNI TO‘XTATISH' if active else 'QAYTA OCHISH',callback_data=f't_close:{t}' if active else f't_open:{t}')
 return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Savol qo‘shish',callback_data=f't_add:{t}')],[InlineKeyboardButton(text='Oddiy variant',callback_data=f't_choice:{t}'),InlineKeyboardButton(text='Yozma variant',callback_data=f't_written:{t}')],[InlineKeyboardButton(text='Savollar',callback_data=f't_q:{t}'),InlineKeyboardButton(text='Natijalar',callback_data=f't_results:{t}')],[InlineKeyboardButton(text='PDF',callback_data=f't_pdf:{t}'),InlineKeyboardButton(text='Mini App link',callback_data=f't_link:{t}')],[InlineKeyboardButton(text='Guruhga yuborish',callback_data=f't_group:{t}')],[toggle],[InlineKeyboardButton(text='TEKSHIRISH',callback_data=f't_check:{t}')],[InlineKeyboardButton(text='O‘CHIRISH',callback_data=f't_delete:{t}')],[InlineKeyboardButton(text='Orqaga',callback_data='t_list')]])
def type_kb(t):return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ODDIY VARIANT',callback_data=f't_choice:{t}')],[InlineKeyboardButton(text='YOZMA VARIANT',callback_data=f't_written:{t}')]])
def abcd(t,n):return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=x,callback_data=f't_ans:{t}:{n}:{x}') for x in 'ABCD']])
def new_answer_kb():return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=x,callback_data=f't_new_ans:{x}') for x in 'ABCD']])
def new_question_type_kb():return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ODDIY VARIANT (A/B/C/D)',callback_data='t_new_kind:choice')],[InlineKeyboardButton(text='YOZMA JAVOB',callback_data='t_new_kind:written')]])
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
  # Answers stay editable until the test is submitted; the newest choice replaces the previous one.
  answers[key] = value
  c.execute("UPDATE test_attempts SET answers_json=? WHERE attempt_id=?", (json.dumps(answers, ensure_ascii=False), a["attempt_id"]))
 return "ok"

def result_counts(answers, questions):
 correct=sum(1 for q in questions if norm(answers.get(str(q["number"]), ""))==norm(q["answer"]))
 total=len(questions)
 answered=sum(1 for q in questions if str(q["number"]) in answers and str(answers.get(str(q["number"]), "")).strip())
 return correct,total,max(0,total-answered)


def question_order_for_attempt(attempt, questions):
 """Create one stable randomized question order per user/test attempt."""
 answers=json.loads(attempt["answers_json"] or "{}")
 valid=[int(q["number"]) for q in questions]
 order=answers.get("_question_order")
 if not isinstance(order,list) or sorted(str(x) for x in order)!=sorted(str(x) for x in valid):
  order=valid[:]
  secrets.SystemRandom().shuffle(order)
  answers["_question_order"]=order
  db.update_attempt(attempt["attempt_id"],answers_json=json.dumps(answers,ensure_ascii=False))
 return [int(x) for x in order]


def finish_attempt_atomically(test_id, telegram_id, questions, finished_at):
 """Lock the attempt while scoring and submitting it; never overwrite an existing result."""
 with db.conn() as c:
  if not db.USE_POSTGRES:c.execute("BEGIN IMMEDIATE")
  a=_locked_attempt(c,test_id,telegram_id)
  if not a or not a["started_at"]:return ("not_started",None,None,None,len(questions))
  if a["submitted"]:
   answers=json.loads(a["answers_json"] or "{}");correct,total,_=result_counts(answers,questions)
   return ("already_submitted",float(a["score"] or 0),a["grade"] or "",correct,total)
  answers=json.loads(a["answers_json"] or "{}")
  correct,total,_=result_counts(answers,questions)
  score_value=round(correct/total*100,2) if total else 0
  grade_value=grade(score_value)
  c.execute("UPDATE test_attempts SET score=?,grade=?,submitted=1,status='submitted',finished_at=? WHERE attempt_id=? AND submitted=0",(score_value,grade_value,finished_at,a["attempt_id"]))
 db.archive_attempt_result(a["attempt_id"])
 return ("ok",score_value,grade_value,correct,total)

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
  t=db.get_test_by_code(code) if code else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not t:return {'ok':False,'error':'test_not_found'}
  rows=[x for x in db.all_attempts_for_test(t['test_id']) if x['submitted']]
  rows.sort(key=lambda x:(-float(x['score'] or 0),str(x['finished_at'] or '9999')))
  top=[{'rank':i+1,'full_name':x['full_name'] or 'Ismsiz','photo_url':x['telegram_photo'] or '', 'score':float(x['score'] or 0),'grade':x['grade'] or '', 'finished_at':x['finished_at']} for i,x in enumerate(rows[:15])]
  return {'ok':True,'test_name':t['name'],'code':t['code'],'total':len(rows),'ranking':top}

 async def render_usage_data():
  api_key=os.getenv('RENDER_API_KEY','').strip()
  if not api_key:
   return {'ok':False,'error':'render_api_key_missing','limit_hours':750,'dashboard_url':'https://dashboard.render.com/billing'}
  now=datetime.now().astimezone()
  month_start=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
  window_start=month_start
  partial=False
  if (now-window_start).total_seconds()>30*86400:
   window_start=now-timedelta(days=30);partial=True
  params=urllib.parse.urlencode({'startTime':window_start.isoformat().replace('+00:00','Z'),'endTime':now.isoformat().replace('+00:00','Z'),'resolutionSeconds':3600,'resource':os.getenv('RENDER_SERVICE_ID','srv-dav8s4m7bikc73f779v0')})
  req_obj=urllib.request.Request('https://api.render.com/v1/metrics/instance-count?'+params,headers={'Authorization':'Bearer '+api_key,'Accept':'application/json'})
  try:
   def fetch_metrics():
    with urllib.request.urlopen(req_obj,timeout=12) as response:return json.loads(response.read().decode('utf-8'))
   series=await asyncio.to_thread(fetch_metrics)
   points=[]
   for item in series if isinstance(series,list) else []:
    for value in item.get('values',[]) if isinstance(item,dict) else []:
     try:points.append((datetime.fromisoformat(str(value.get('timestamp','')).replace('Z','+00:00')),max(0,float(value.get('value',0)))))
     except Exception:pass
   points.sort(key=lambda x:x[0])
   hours=0.0
   for i,(stamp,count) in enumerate(points):
    if i+1<len(points):delta=max(0,min(3600,(points[i+1][0]-stamp).total_seconds()))
    else:delta=3600
    hours+=count*delta/3600
   limit=750.0
   return {'ok':True,'limit_hours':limit,'used_hours':round(hours,1),'remaining_hours':round(max(0,limit-hours),1),'percent':round(min(100,hours/limit*100),1),'partial':partial,'samples':len(points),'window_start':window_start.isoformat(),'window_end':now.isoformat(),'dashboard_url':'https://dashboard.render.com/billing','note':'Instance-count metrikasidan taxminiy hisob; Billing sahifasidagi hisob aniqroq.'}
  except urllib.error.HTTPError as exc:
   logging.getLogger('nur-oqiw.render_usage').warning('Render metrics HTTP %s',exc.code)
   return {'ok':False,'error':'render_metrics_unavailable','limit_hours':750,'dashboard_url':'https://dashboard.render.com/billing'}
  except Exception:
   logging.getLogger('nur-oqiw.render_usage').exception('Could not read Render usage metrics')
   return {'ok':False,'error':'render_metrics_unavailable','limit_hours':750,'dashboard_url':'https://dashboard.render.com/billing'}
 @core.app.get('/api/admin/render-usage')
 async def admin_render_usage(req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  return await render_usage_data()

 @core.app.get('/api/admin/schedule')
 async def admin_schedule_get(req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  raw=db.get_setting('awake_schedule','{}')
  try:cfg=json.loads(raw)
  except Exception:cfg={}
  return {'ok':True,'schedule':cfg or {'date':'','start':'08:00','end':'22:00','timezone':'Asia/Tashkent'}}
 @core.app.post('/api/admin/schedule')
 async def admin_schedule_save(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  import re
  day=str(p.get('date','')).strip();start=str(p.get('start','')).strip();end=str(p.get('end','')).strip()
  if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',start) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',end):
   return {'ok':False,'error':'invalid_schedule'}
  cfg={'date':day,'start':start,'end':end,'timezone':'Asia/Tashkent'}
  db.set_setting('awake_schedule',json.dumps(cfg,ensure_ascii=False))
  db.set_setting('awake_window',start+'-'+end)
  return {'ok':True,'schedule':cfg,'message':'Jadval saqlandi. Bu sozlama Render uyquga ketgan instansiyasini o‘zi uyg‘otmaydi.'}
 @core.app.post('/api/admin/jarvis')
 async def admin_jarvis(p:dict, req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  api_key=os.getenv('OPENAI_API_KEY','').strip()
  if not api_key:return {'ok':False,'error':'api_key_missing'}
  incoming=p.get('messages',[])
  if not isinstance(incoming,list):return {'ok':False,'error':'invalid_messages'}
  messages=[]
  for item in incoming[-16:]:
   if not isinstance(item,dict):continue
   role=item.get('role')
   content=str(item.get('content','')).strip()[:3000]
   if role in ('user','assistant') and content:messages.append({'role':role,'content':content})
  if not messages or messages[-1]['role']!='user':return {'ok':False,'error':'invalid_messages'}
  # Only a small allowlist of admin actions can be proposed; every mutation needs a separate confirmation.
  import re
  command=messages[-1]['content'].strip()
  low=command.casefold()
  toggle_match=re.fullmatch(r"(?:testni|test)\s+(yop|yopiq qil|to['’‘]?xtat|och|qayta och)\s+([A-Za-z0-9_-]{2,40})",command,re.I)
  if toggle_match:
   verb=toggle_match.group(1).casefold();code=toggle_match.group(2).strip();test=db.get_test_by_code(code)
   if not test:return {'ok':True,'reply':f"'{code}' kodi bilan test topilmadi. Kodni tekshirib qayta yuboring."}
   desired_active=verb in ('och','qayta och')
   if bool(int(test['active']))==desired_active:return {'ok':True,'reply':f"{test['name']} hozirning o‘zida {'ochiq' if desired_active else 'yopiq'}."}
   return {'ok':True,'reply':f"Amal tayyor: {test['name']} testini {'ochish' if desired_active else 'to‘xtatish'}. Tasdiqlasangiz bajaraman.",'action':{'type':'test_toggle','test_id':str(test['test_id']),'code':str(test['code']),'name':str(test['name']),'active':desired_active}}
  if re.search(r'majburiy\s+obuna.*(?:o[\'’‘]?chir|off)',low):
   return {'ok':True,'reply':'Majburiy obunani o‘chirishni tasdiqlang. Bu barcha foydalanuvchilar uchun obuna tekshiruvini o‘chiradi.','action':{'type':'subscription_required','enabled':False}}
  if re.search(r'majburiy\s+obuna.*(?:yoq|on)',low):
   channels=db.get_setting('subscription_channels','')
   if not channels or channels in ('[]','{}'):return {'ok':True,'reply':'Avval admin menyusidagi “Majburiy obuna” orqali kanal(lar)ni kiriting. Hozir kanal ro‘yxati bo‘sh.'}
   return {'ok':True,'reply':'Majburiy obunani yoqishni tasdiqlang. Bot kanallarga admin sifatida qo‘shilgan bo‘lishi kerak.','action':{'type':'subscription_required','enabled':True}}
  window_match=re.search(r'(?:jadval|ish vaqti).*?((?:[01]\d|2[0-3]):[0-5]\d)\s*[-–]\s*((?:[01]\d|2[0-3]):[0-5]\d)',low)
  if window_match:
   start_time,end_time=window_match.groups()
   return {'ok':True,'reply':f"Ish vaqti jadvalini {start_time}-{end_time} qilib saqlashni tasdiqlang. Bu jadval Render Free serverini uyqudan majburan uyg‘otmaydi.",'action':{'type':'awake_window','start':start_time,'end':end_time}}
  context=p.get('context',{})
  if not isinstance(context,dict):context={}
  safe_stats=context.get('stats',{}) if isinstance(context.get('stats',{}),dict) else {}
  safe_tests=context.get('tests',[]) if isinstance(context.get('tests',[]),list) else []
  safe_tests=[{'name':str(t.get('name',''))[:120],'code':str(t.get('code',''))[:40],'active':bool(t.get('active')),'questions':int(t.get('questions',0) or 0),'participants':int(t.get('participants',0) or 0),'completed':int(t.get('completed',0) or 0)} for t in safe_tests[:30] if isinstance(t,dict)]
  system='You are Jarvis, the AI admin assistant for Nur oqıw orayı Milliy sertifikat test system. Reply in clear Uzbek Latin or Qaraqalpaq Latin. Be concise and practical. Use the LIVE SNAPSHOT below for current users, tests and results. Supported direct actions are limited to: "testni yop KOD", "testni och KOD", "majburiy obunani yoq", "majburiy obunani o‘chir", and "jadval 08:00-22:00". The backend proposes these actions and requires the administrator to press a confirmation button before execution. For other changes, explain how to do them through existing admin controls. Never claim an action succeeded unless an API confirms it. Never reveal secrets or ask the user to paste API keys into chat. LIVE SNAPSHOT: '+json.dumps({'stats':safe_stats,'tests':safe_tests},ensure_ascii=False)
  payload={'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'input':[{'role':'system','content':system}]+messages,'max_output_tokens':1200}
  def call_api():
   req_obj=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/json'},method='POST')
   with urllib.request.urlopen(req_obj,timeout=45) as response:return json.loads(response.read().decode('utf-8'))
  try:
   result=await asyncio.to_thread(call_api)
   answer=str(result.get('output_text','')).strip()
   if not answer:
    chunks=[]
    for item in result.get('output',[]):
     for part in item.get('content',[]):
      if part.get('type')=='output_text':chunks.append(str(part.get('text','')))
    answer='\n'.join(chunks).strip()
   if not answer:return {'ok':False,'error':'empty_response'}
   return {'ok':True,'reply':answer}
  except urllib.error.HTTPError as exc:
   if exc.code==401:return {'ok':False,'error':'api_key_invalid'}
   logging.getLogger('nur-oqiw.jarvis').warning('Jarvis API returned HTTP %s',exc.code)
   return {'ok':False,'error':'jarvis_api_error'}
  except Exception:
   logging.getLogger('nur-oqiw.jarvis').exception('Jarvis API request failed')
   return {'ok':False,'error':'jarvis_api_error'}

 @core.app.get('/api/admin/overview')
 async def admin_overview(req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  tests=[];all_rows=[]
  for t in db.all_tests():
   attempts=db.all_attempts_for_test(t['test_id'])
   done=[a for a in attempts if a['submitted']]
   ranked=sorted(done,key=lambda a:(-float(a['score'] or 0),str(a['finished_at'] or '9999')))
   participants=[{'full_name':a['full_name'] or 'Ismsiz','telegram_id':int(a['telegram_id']),'score':float(a['score'] or 0),'grade':a['grade'] or '', 'submitted':bool(a['submitted']),'started_at':a['started_at'],'finished_at':a['finished_at']} for a in sorted(attempts,key=lambda a:str(a['started_at'] or ''),reverse=True)]
   tests.append({'test_id':str(t['test_id']),'name':t['name'],'code':t['code'],'active':bool(int(t['active'])),'questions':len(db.questions_for_test(t['test_id'])),'participants':len(attempts),'completed':len(done),'ranking':participants and [{'rank':i+1,'full_name':a['full_name'] or 'Ismsiz','score':float(a['score'] or 0),'grade':a['grade'] or ''} for i,a in enumerate(ranked[:10])] or [],'recent':participants[:50]})
   all_rows.extend(participants)
  with db.conn() as con:
   user_count=int(con.execute("SELECT COUNT(*) AS n FROM users").fetchone()['n'])
  return {'ok':True,'stats':{'users':user_count,'tests':len(tests),'participants':len(all_rows),'completed':sum(1 for a in all_rows if a['submitted'])},'tests':tests}
 @core.app.post('/api/admin/test/toggle')
 async def admin_toggle_test(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id','')).strip();t=db.get_test(test_id)
  if not t:return {'ok':False,'error':'test_not_found'}
  if int(t['active']):
   qs=db.questions_for_test(test_id);closed=0
   for a in db.all_attempts_for_test(test_id):
    if a['submitted'] or not a['started_at']:continue
    state,_,_,_,_=finish_attempt_atomically(test_id,int(a['telegram_id']),qs,datetime.now(TZ).isoformat())
    if state=='ok':closed+=1
   db.set_test_active(test_id,0)
   return {'ok':True,'active':False,'finalized':closed,'message':'Test to‘xtatildi; javoblar bo‘yicha ball hisoblandi.'}
  db.set_test_active(test_id,1)
  return {'ok':True,'active':True,'finalized':0,'message':'Test qayta ochildi.'}
 @core.app.post('/api/admin/jarvis/action')
 async def admin_jarvis_action(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  action=p.get('action')
  if not isinstance(action,dict):return {'ok':False,'error':'invalid_action'}
  kind=action.get('type')
  if kind=='test_toggle':
   test_id=str(action.get('test_id','')).strip();desired=action.get('active')
   if not test_id or not isinstance(desired,bool):return {'ok':False,'error':'invalid_action'}
   test=db.get_test(test_id)
   if not test:return {'ok':False,'error':'test_not_found'}
   if bool(int(test['active']))==desired:return {'ok':True,'message':f"Test allaqachon {'ochiq' if desired else 'yopiq'}."}
   result=await admin_toggle_test({'test_id':test_id},req)
   if not result.get('ok') or bool(result.get('active'))!=desired:return {'ok':False,'error':'action_failed'}
   return {'ok':True,'message':result.get('message','Amal bajarildi.')}
  if kind=='subscription_required':
   enabled=action.get('enabled')
   if not isinstance(enabled,bool):return {'ok':False,'error':'invalid_action'}
   channels=db.get_setting('subscription_channels','')
   if enabled and (not channels or channels in ('[]','{}')):return {'ok':False,'error':'channels_missing'}
   db.set_setting('subscription_required','1' if enabled else '0')
   return {'ok':True,'message':'Majburiy obuna '+('yoqildi.' if enabled else 'o‘chirildi.')}
  if kind=='awake_window':
   import re
   start=str(action.get('start',''));end=str(action.get('end',''))
   if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',start) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',end):return {'ok':False,'error':'invalid_action'}
   db.set_setting('awake_window',start+'-'+end)
   db.set_setting('awake_schedule',json.dumps({'date':'','start':start,'end':end,'timezone':'Asia/Tashkent'},ensure_ascii=False))
   return {'ok':True,'message':f'Jadval saqlandi: {start}-{end}. Bu Render serverining uyqu rejimini bekor qilmaydi.'}
  return {'ok':False,'error':'action_not_allowed'}
 @core.app.get('/api/test/state')
 async def state(req: Request):
  tid,u=await auth(req);c=req.query_params.get('code','').strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  if not t:return {'ok':False,'error':'test_not_found'}
  if not db.questions_for_test(t['test_id']):return {'ok':False,'error':'test_not_ready','test_name':t['name']}
  if u['test_id']!=t['test_id']:db.update_user(tid,test_id=t['test_id'],code_ok=1,state='ready');u=db.get_user(tid)
  if not u['full_name']:return {'ok':False,'error':'registration_required','test_name':t['name']}
  a=db.ensure_attempt(t['test_id'],tid)
  if a['submitted']:
   answers=json.loads(a['answers_json'] or '{}');correct,total,unanswered=result_counts(answers,db.questions_for_test(t['test_id']))
   return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade'],'correct_count':correct,'total_questions':total,'unanswered_count':unanswered,'test_name':t['name'],'full_name':u['full_name']}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
  if not a['started_at']:
   if not opened(t):return {'ok':False,'error':'test_closed','test_name':t['name']}
   db.update_attempt(a['attempt_id'],started_at=datetime.now(TZ).isoformat(),status='active');a=db.get_attempt(t['test_id'],tid)
  if expired(a,t):
   sc,gr=finalize_expired(a,t);return {'ok':False,'error':'already_submitted','score':sc,'grade':gr,'test_name':t['name'],'full_name':u['full_name']}
  qs=db.questions_for_test(t['test_id']);order=question_order_for_attempt(a,qs);by_number={int(q['number']):q for q in qs}
  answers=json.loads(a['answers_json'] or '{}');answers.pop('_question_order',None)
  results={str(q['number']):('correct' if db.normalize(answers.get(str(q['number']),''))==db.normalize(q['answer']) else 'wrong') for q in qs if str(q['number']) in answers and q['kind']!='written'}
  return {'ok':True,'full_name':u['full_name'],'answers':answers,'results':results,'ends_at':None,'test_name':t['name'],'test_code':t['code'],'total_questions':len(qs),'questions':[{'id':by_number[n]['number'],'display_number':i+1,'question':by_number[n]['question'] or '', 'options':(json.loads(by_number[n]['options_json'] or '[]') if by_number[n]['options_json'] else []) or ['A','B','C','D'], 'kind':by_number[n]['kind'],'image_url':by_number[n]['image_url'] or ''} for i,n in enumerate(order)]}
 @core.app.get('/api/test/questions')
 async def questions(req: Request):
  tid,u=await auth(req);c=req.query_params.get('code','').strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
  if not u['full_name'] or u['test_id']!=t['test_id'] or not opened(t):return {'ok':False,'error':'test_not_started'}
  a=db.get_attempt(t['test_id'],tid)
  if not a or not a['started_at'] or a['submitted']:return {'ok':False,'error':'test_not_started'}
  qs=db.questions_for_test(t['test_id']);order=question_order_for_attempt(a,qs);by_number={int(q['number']):q for q in qs}
  return {'ok':True,'questions':[{'id':by_number[n]['number'],'display_number':i+1,'question':by_number[n]['question'] or '', 'options':(json.loads(by_number[n]['options_json'] or '[]') if by_number[n]['options_json'] else []) or ['A','B','C','D'], 'kind':by_number[n]['kind'],'image_url':by_number[n]['image_url'] or ''} for i,n in enumerate(order)]}
 @core.app.post('/api/test/answer')
 async def answer(p:dict, request: Request):
  raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or p.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;c=str(p.get('code','')).strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t or not u['full_name']:return {'ok':False,'error':'not_authorized'}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
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
   pass
  else:
   v=v.upper()
   try:
    option_list=json.loads(q['options_json'] or '[]')
   except Exception:
    option_list=[]
   allowed={chr(65+i) for i in range(min(26,len(option_list) if option_list else 4))}
   if v not in allowed:return {'ok':False,'error':'invalid_answer'}
  saved=save_answer_atomically(t['test_id'],tid,q['number'],v)
  if saved=='locked':return {'ok':False,'error':'answer_locked'}
  if saved=='submitted':return {'ok':False,'error':'already_submitted'}
  if saved!='ok':return {'ok':False,'error':'test_not_started'}
  return {'ok':True,'number':q['number'],'correct': (db.normalize(v)==db.normalize(q['answer'])) if q['kind']!='written' else None}
 @core.app.post('/api/test/finish')
 async def finish(p:dict, request: Request):
  raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or p.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;c=str(p.get('code','')).strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t or not u['full_name']:return {'ok':False,'error':'not_authorized'}
  if u['test_id']!=t['test_id']:return {'ok':False,'error':'test_not_started'}
  a=db.get_attempt(t['test_id'],tid)
  if not a or not a['started_at']:return {'ok':False,'error':'test_not_started'}
  if a['submitted']:
   answers=json.loads(a['answers_json'] or '{}');correct,total,_=result_counts(answers,db.questions_for_test(t['test_id']))
   return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade'],'correct_count':correct,'total_questions':total}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
  if expired(a,t):
   sc,gr=finalize_expired(a,t);return {'ok':True,'score':sc,'grade':gr,'full_name':u['full_name'],'test_name':t['name']}
  if not opened(t):return {'ok':False,'error':'test_closed'}
  status,sc,gr,correct,total=finish_attempt_atomically(t['test_id'],tid,db.questions_for_test(t['test_id']),datetime.now(TZ).isoformat())
  if status=='not_started':return {'ok':False,'error':'test_not_started'}
  if status=='already_submitted':return {'ok':False,'error':'already_submitted','score':sc,'grade':gr,'correct_count':correct,'total_questions':total}
  return {'ok':True,'score':sc,'grade':gr,'correct_count':correct,'total_questions':total,'wrong_count':max(0,total-correct),'full_name':u['full_name'],'test_name':t['name']}
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
 @r.message(F.text=='Mening natijam')
 async def user_results(m:Message):
  u=db.get_user(m.from_user.id)
  if not u:return await m.answer("Siz hali ro‘yxatdan o‘tmagansiz. /start ni bosing.",reply_markup=user_menu())
  with db.conn() as c:
   rows=c.execute("SELECT a.test_id,t.name,t.code,a.started_at,a.finished_at,a.score,a.grade,a.submitted FROM test_attempts a LEFT JOIN tests t ON t.test_id=a.test_id WHERE a.telegram_id=? ORDER BY COALESCE(a.finished_at,a.started_at) DESC",(m.from_user.id,)).fetchall()
  if not rows:return await m.answer("Hozircha test natijangiz yo‘q.",reply_markup=user_menu())
  lines=["MENING NATIJALARIM",""]
  for i,row in enumerate(rows[:15],1):
   state=(f"{float(row['score'] or 0):.2f} ball | {row['grade'] or '—'}" if row['submitted'] else "Yakunlanmagan")
   lines.append(f"{i}. {row['name'] or 'Test'} ({row['code'] or 'kod yo‘q'}) — {state}")
  await m.answer('\\n'.join(lines),reply_markup=user_menu())
 @r.message(F.text=='Tariflar')
 async def tariffs(m:Message):
  await m.answer('Tariflar bo‘yicha ma’lumot olish uchun administratorga murojaat qiling: @up17v',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ADMIN BILAN BOG‘LANISH',url='https://t.me/up17v')]]))
 @r.message(F.text=='Yordam')
 async def help_user(m:Message):
  await m.answer('Savol yoki muammo bo‘lsa, administratorga yozing: @up17v',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ADMIN BILAN BOG‘LANISH',url='https://t.me/up17v')]]))
 async def check_prompt(tid,fake_id,index):
  t=db.get_test(tid);qs=db.questions_for_test(tid);u=db.get_user(fake_id);a=db.get_attempt(tid,fake_id)
  if not t or not u or not a:return await BOT.send_message(ADMIN,'Tekshirish sessiyasi topilmadi.')
  if index>=len(qs):
   answers=json.loads(a['answers_json'] or '{}')
   score_value=round(sum(1 for x in qs if norm(answers.get(str(x['number']),' '))==norm(x['answer']))/len(qs)*100,2) if qs else 0
   grade_value=grade(score_value);finished=datetime.now(TZ).isoformat()
   db.update_attempt(a['attempt_id'],score=score_value,grade=grade_value,submitted=1,status='submitted',finished_at=finished)
   db.update_user(fake_id,score=score_value,grade=grade_value,submitted=1,finished_at=finished)
   return await BOT.send_message(ADMIN,f"TEKSHIRISH TUGADI\\nAkkaunt: {u['full_name']}\\nTest: {t['name']}\\nNatija: {score_value:.2f} ball · {grade_value}",reply_markup=test_kb(tid))
  x=qs[index];head=f"TEKSHIRISH — {u['full_name']}\\n{t['name']}\\nSavol {index+1}/{len(qs)}\\n{x['question'] or (str(x['number'])+'-savol')}\\n"
  if x['kind']=='written':
   ast(f"check_written:{tid}:{fake_id}:{index}")
   return await BOT.send_message(ADMIN,head+"\\nTo‘g‘ri yozma javobni kiriting (simulyatsiya):")
  kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=z,callback_data=f"t_check_ans:{tid}:{fake_id}:{index}:{z}") for z in 'ABCD']])
  return await BOT.send_message(ADMIN,head+"\\nVariantni tanlang:",reply_markup=kb)
 @r.message(F.from_user.id==ADMIN)
 async def admin_text(m:Message):
  u=db.ensure_user(ADMIN);s=u['state'] or 'admin';txt=(m.text or '').strip()
  if txt in {'Test sozlamalari','Ishtirokchilar','Statistika','Guruhlar holati','Guruhga xabar yuborish','Bildirishnoma','Ish vaqti jadvali','Majburiy obuna','PDF natijalar','Tekshirish','Tariflar','Botni uyg‘otish','Render limitini ko‘rish'}:
   ast('admin');u=db.ensure_user(ADMIN);s='admin'
  if s.startswith('check_written:'):
   try:
    _,tid,fake_id,index=s.split(':');fake_id=int(fake_id);index=int(index)
    a=db.get_attempt(tid,fake_id);qs=db.questions_for_test(tid)
    if not a or index>=len(qs):raise ValueError()
    answers=json.loads(a['answers_json'] or '{}');answers[str(qs[index]['number'])]=txt
    db.update_attempt(a['attempt_id'],answers_json=json.dumps(answers,ensure_ascii=False));ast('admin')
    return await check_prompt(tid,fake_id,index+1)
   except Exception:return await m.answer('Tekshirish javobi saqlanmadi. Tekshirishni qaytadan boshlang.')
  if txt=='Render limitini ko‘rish':
   usage=await render_usage_data()
   if not usage.get('ok'):
    reason='RENDER_API_KEY ulanmagan.' if usage.get('error')=='render_api_key_missing' else 'Render metrikasini olishning imkoni bo‘lmadi.'
    return await m.answer(f"RENDER FREE LIMITI\\n\\nOylik limit: 750 instance-soat\\n\\n{reason}\\nAniq limitni Render Billing sahifasidan ko‘ring: https://dashboard.render.com/billing\\n\\nAniq ko‘rsatkichni admin menyusida olish uchun Render API key yaratib, Render Environment Variables ichiga RENDER_API_KEY nomi bilan saqlang.")
   partial='\\nEslatma: oxirgi 30 kun bilan cheklangan taxminiy hisob.' if usage.get('partial') else ''
   return await m.answer(f"RENDER FREE LIMITI\\n\\nTaxminiy ishlatilgan: {usage['used_hours']} / {usage['limit_hours']} soat\\nQolgan limit: {usage['remaining_hours']} soat\\nIshlatilgan: {usage['percent']}%\\n\\n{usage['note']}{partial}\\nAniq hisob: https://dashboard.render.com/billing")
  if txt=='Botni uyg‘otish':
   try:
    me=await BOT.get_me()
    return await m.answer(f'Bot faol: @{me.username}\nServer ishlayapti. Agar birinchi so‘rov sekin bo‘lsa, Mini App admin panelidagi «Botni uyg‘otish» tugmasini ham bosing.')
   except Exception:
    return await m.answer('Bot hozir javob bermadi. Biroz kutib qayta urinib ko‘ring.')
  if txt in {'/statistika','Statistika'}:
   users=db.all_registered_users();tests=db.all_tests();attempts=[a for t in tests for a in db.all_attempts_for_test(t['test_id'])];groups=json.loads(db.get_setting('known_groups','[]') or '[]')
   return await m.answer(f"BOT STATISTIKASI\\n\\nFoydalanuvchilar: {len(users)}\\nTestlar: {len(tests)}\\nUrinishlar: {len(attempts)}\\nYakunlangan testlar: {sum(1 for a in attempts if a['submitted'])}\\nGuruhlar: {len(groups)}\\nVaqt zonasi: Asia/Tashkent",reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Test sozlamalari'),KeyboardButton(text='Ishtirokchilar')],[KeyboardButton(text='Statistika'),KeyboardButton(text='Guruhlar holati')],[KeyboardButton(text='Guruhga xabar yuborish'),KeyboardButton(text='Bildirishnoma')],[KeyboardButton(text='Ish vaqti jadvali'),KeyboardButton(text='Majburiy obuna')],[KeyboardButton(text='PDF natijalar'),KeyboardButton(text='Tekshirish')],[KeyboardButton(text='Tariflar'),KeyboardButton(text='Botni uyg‘otish')]],resize_keyboard=True))
  if txt=='Guruhlar holati':
   groups=json.loads(db.get_setting('known_groups','[]') or '[]')
   if not groups:return await m.answer("Guruhlar ro‘yxati bo‘sh. Botni guruhga qo‘shing va /group_status buyrug‘ini yuboring.")
   lines=['GURUHLAR VA RUXSATLAR','']
   for g in groups[:30]:
    try:
     member=await BOT.get_chat_member(int(g['id']),BOT.id)
     can_send=member.status not in ('left','kicked') and not (member.status=='administrator' and getattr(member,'can_send_messages',True) is False)
     lines.append(f"{g.get('title',g['id'])} ({g['id']}) — {member.status}; xabar yuborish: {'ha' if can_send else 'yo‘q'}")
    except Exception:lines.append(f"{g.get('title',g['id'])} ({g['id']}) — tekshirib bo‘lmadi; bot huquqini tekshiring")
   return await m.answer('\\n'.join(lines)[:3900])
  if txt=='Majburiy obuna':
   ast('subscription_channels')
   current=json.loads(db.get_setting('subscription_channels','[]') or '[]') if db.get_setting('subscription_channels','') else []
   return await m.answer("Majburiy obuna kanallarini @username yoki -100... ID ko‘rinishida, har birini yangi qatordan yuboring. O‘chirish uchun OFF yozing.\\n\\nHozirgi kanallar: "+(', '.join(str(x) for x in current) if current else 'o‘chirilgan'))
  if s=='subscription_channels':
   if txt.strip().upper()=='OFF':
    db.set_setting('subscription_required','0');db.set_setting('subscription_channels','[]');ast('admin')
    return await m.answer("Majburiy obuna o‘chirildi.")
   channels=[x.strip() for x in txt.replace(',','\\n').splitlines() if x.strip()]
   if not channels:return await m.answer("Kanal username yoki ID kiriting, yoki OFF yozing.")
   db.set_setting('subscription_channels',json.dumps(channels,ensure_ascii=False));db.set_setting('subscription_required','1');ast('admin')
   return await m.answer(f"Majburiy obuna saqlandi. Kanallar: {len(channels)}. Bot kanalga admin sifatida qo‘shilganini tekshiring.")
  if txt=='Tariflar':
   ast('premium_user_id')
   return await m.answer("Tarifini o‘zgartirmoqchi bo‘lgan foydalanuvchining Telegram ID raqamini kiriting.")
  if s=='premium_user_id':
   try:target=int(txt)
   except:return await m.answer("Telegram ID faqat raqam bo‘lishi kerak.")
   user=db.get_user(target)
   if not user:return await m.answer("Foydalanuvchi topilmadi. Avval botga /start bosgan bo‘lishi kerak.")
   db.set_setting('premium_target_user',str(target));ast('premium_tier')
   return await m.answer(f"Foydalanuvchi: {user['full_name'] or 'Ismsiz'} (ID {target}). Tarifni tanlang:",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='PREMIUM BERISH',callback_data='premium_set:premium')],[InlineKeyboardButton(text='ODDIY TARIF',callback_data='premium_set:default')]]))
  if txt=='Bildirishnoma':
   ast('notification_message')
   return await m.answer("Barcha bot foydalanuvchilariga yuboriladigan xabarni kiriting. Yuborishdan oldin tasdiqlash chiqadi.")
  if s=='notification_message':
   if not txt:return await m.answer("Xabar matni bo‘sh bo‘lmasin.")
   db.set_setting('pending_notification',json.dumps({'text':txt},ensure_ascii=False));ast('notification_confirm')
   return await m.answer(f"XABAR NAMUNASI\\n\\n{txt[:2500]}\\n\\nBarcha ro‘yxatdan o‘tgan foydalanuvchilarga yuborilsinmi?",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='YUBORISH',callback_data='notification_send'),InlineKeyboardButton(text='BEKOR QILISH',callback_data='notification_cancel')]]))
  if txt=='Ishtirokchilar':
   users=db.all_registered_users()
   if not users:return await m.answer("Hozircha foydalanuvchilar yo‘q.")
   lines=["FOYDALANUVCHILAR RO‘YXATI",""]
   for i,user in enumerate(users[:35],1):
    lines.append(f"{i}. {user['full_name'] or 'Ismsiz'} | ID: {user['telegram_id']} | Tarif: {user['tier'] or 'default'}")
   return await m.answer('\\n'.join(lines)[:3900])
  if txt=='Guruhga xabar yuborish':
   ast('broadcast_message')
   return await m.answer("Guruhlarga yuboriladigan xabar matnini yuboring. Keyin yuborishdan oldin tasdiqlash so‘raladi.")
  if s=='broadcast_message':
   if not txt:return await m.answer("Xabar bo‘sh bo‘lmasin. Matnni qayta yuboring.")
   db.set_setting('pending_broadcast',json.dumps({'text':txt},ensure_ascii=False));ast('broadcast_confirm')
   return await m.answer(f"XABAR NAMUNASI\\n\\n{txt[:2500]}\\n\\nBarcha ro‘yxatdagi guruhlarga yuborilsinmi?",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='YUBORISH',callback_data='broadcast_send'),InlineKeyboardButton(text='BEKOR QILISH',callback_data='broadcast_cancel')]]))
  if txt=='Ish vaqti jadvali':
   current=db.get_setting('awake_window','08:00-22:00');ast('awake_window')
   return await m.answer(f"Toshkent vaqti bilan HH:MM-HH:MM ko‘rinishida kiriting. Hozirgi sozlama: {current}.\\nEslatma: Render bepul xizmat uyquga ketgan bo‘lsa, bot ichidagi jadvalning o‘zi uni uyg‘ota olmaydi; tashqi uptime monitor kerak bo‘ladi.")
  if s=='awake_window':
   import re
   if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d',txt):return await m.answer("Format noto‘g‘ri. Masalan: 07:30-23:00")
   db.set_setting('awake_window',txt);ast('admin')
   return await m.answer(f"Jadval saqlandi: {txt} (Asia/Tashkent). Uyqudagi Render instansiyasini tashqaridan uyg‘otmaydi.")
  if txt in {'Test sozlamalari','Ishtirokchilar','PDF natijalar','Tekshirish'}:return await m.answer('TESTLAR — saqlangan testlar',reply_markup=tests_kb())
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
   d=draft();d['count']=n;d['items']=[];save_draft(d);ast('new_kind')
   return await m.answer(f'1/{n}-savol turini tanlang:',reply_markup=new_question_type_kb())
  if s=='new_written_answer':
   if not txt:return await m.answer('Yozma javob bo‘sh bo‘lmasin. To‘g‘ri javobni kiriting:')
   d=draft();d.setdefault('items',[]).append({'kind':'written','answer':txt});save_draft(d);done=len(d['items']);total=int(d['count'])
   if done<total:
    ast('new_kind');return await m.answer(f'{done+1}/{total}-savol turini tanlang:',reply_markup=new_question_type_kb())
   try:
    if len(d['items'])!=total:return await m.answer('Savollar to‘liq emas. Test hali saqlanmadi.')
    t=db.create_test_with_questions(d['name'],d['code'],d['items']);clear_draft();ast('admin')
    return await m.answer(f"TEST SAQLANDI\n\n{t['name']}\nKod: {t['code']}\nSavollar: {total}\nHolat: DOIMO OCHIQ",reply_markup=test_kb(t['test_id']))
   except Exception as e:return await m.answer(f'Test saqlanmadi: {e}')
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
 @r.callback_query(F.data=='t_check_list')
 async def tcl(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  await q.message.edit_text('Tekshirish uchun testni tanlang:',reply_markup=tests_kb());await q.answer()
 @r.callback_query(F.data.startswith('t_check:'))
 async def tcheck(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];t=db.get_test(tid)
  if not t:return await q.answer('Test topilmadi',show_alert=True)
  if not int(t['active']):return await q.answer('Avval testni qayta oching.',show_alert=True)
  fake_name='user'+str(secrets.randbelow(900)+100);fake_id=-(int(secrets.randbelow(900000000)+100000000))
  while db.get_user(fake_id):fake_id-=1
  db.upsert_user(fake_id,fake_name);db.update_user(fake_id,code_ok=1,state='ready',test_id=tid)
  db.ensure_attempt(tid,fake_id)
  a=db.get_attempt(tid,fake_id);db.update_attempt(a['attempt_id'],started_at=datetime.now(TZ).isoformat(),status='active')
  await q.message.answer(f"TEKSHIRISH AKKAUNTI YARATILDI\\nLogin: {fake_name}\\nTest: {t['name']}\\nKod: {t['code']}\\n\\nEndi har bir savolga javob berib test oqimini tekshirishingiz mumkin.")
  await check_prompt(tid,fake_id,0)
  await q.answer('Tekshiruv akkaunti yaratildi')
 @r.callback_query(F.data.startswith('t_check_ans:'))
 async def tcheck_answer(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  try:
   _,tid,fake_id,index,letter=q.data.split(':');fake_id=int(fake_id);index=int(index)
   qs=db.questions_for_test(tid);a=db.get_attempt(tid,fake_id)
   if not a or index>=len(qs) or letter not in 'ABCD':return await q.answer('Tekshirish sessiyasi eskirgan.',show_alert=True)
   answers=json.loads(a['answers_json'] or '{}');answers[str(qs[index]['number'])]=letter
   db.update_attempt(a['attempt_id'],answers_json=json.dumps(answers,ensure_ascii=False))
   await q.answer('Javob qabul qilindi')
   await check_prompt(tid,fake_id,index+1)
  except Exception:
   import logging;logging.getLogger('nur-oqiw').exception('test check answer')
   await q.answer('Javobni saqlashda xatolik',show_alert=True)
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
  d.setdefault('items',[]).append({'kind':'choice','answer':letter});save_draft(d)
  done=len(d['items']);total=int(d['count'])
  if done<total:
   ast('new_kind');await q.message.answer(f'{done+1}/{total}-savol turini tanlang:',reply_markup=new_question_type_kb())
   return await q.answer(f'{done}/{total} saqlandi')
  try:
   if db.test_code_exists(d['code']):return await q.answer('Bu kod avval ishlatilgan. Boshqa kod tanlang.',show_alert=True)
   if len(d['items'])!=total:return await q.answer('Barcha savollar tugallanmagan. Test saqlanmadi.',show_alert=True)
   t=db.create_test_with_questions(d['name'],d['code'],d['items'])
   clear_draft();ast('admin')
   await q.message.answer(f"TEST SAQLANDI\n\n{t['name']}\nKod: {t['code']}\nSavollar: {total}\nHolat: DOIMO OCHIQ",reply_markup=test_kb(t['test_id']))
   await q.answer('Test saqlandi')
  except Exception:
   import logging;logging.getLogger('nur-oqiw').exception('create test from answer key')
   return await q.answer('Test saqlanmadi. Qaytadan urinib ko‘ring.',show_alert=True)
 @r.callback_query(F.data.startswith('t_new_kind:'))
 async def new_kind(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  d=draft();u=db.get_user(ADMIN);kind=q.data.rsplit(':',1)[-1]
  if not d.get('code') or not d.get('name') or not d.get('count') or not u or u['state']!='new_kind':
   return await q.answer('Test yaratish bosqichi eskirgan. Yangi testni qaytadan boshlang.',show_alert=True)
  if len(d.get('items',[]))>=int(d['count']):return await q.answer('Barcha savollar kiritilgan.',show_alert=True)
  d['current_kind']=kind;save_draft(d);number=len(d.get('items',[]))+1;total=int(d['count'])
  if kind=='choice':
   ast('new_answer');await q.message.answer(f'{number}/{total}-savol uchun to‘g‘ri variantni tanlang:',reply_markup=new_answer_kb())
  elif kind=='written':
   ast('new_written_answer');await q.message.answer(f'{number}/{total}-savol uchun to‘g‘ri yozma javobni kiriting:')
  else:return await q.answer('Savol turi noto‘g‘ri.',show_alert=True)
  await q.answer()

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
  tid=q.data.split(':',1)[1];db.set_test_active(tid,1);t=db.get_test(tid)
  await q.message.edit_text(f"TEST QAYTA OCHILDI\n\n{t['name']}\nKod: {t['code']}",reply_markup=test_kb(tid));await q.answer('Test qayta ochildi')
 @r.callback_query(F.data.startswith('t_close:'))
 async def tx(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];t=db.get_test(tid);qs=db.questions_for_test(tid);closed_count=0
  for a in db.all_attempts_for_test(tid):
   if a['submitted'] or not a['started_at']:continue
   status,_,_,_,_=finish_attempt_atomically(tid,int(a['telegram_id']),qs,datetime.now(TZ).isoformat())
   if status=='ok':closed_count+=1
  db.set_test_active(tid,0)
  await q.message.edit_text(f"TEST TO‘XTATILDI\n\n{t['name']}\nKod: {t['code']}\nYakunlanmagan urinishlarga javoblari bo‘yicha ball hisoblandi: {closed_count} ta.",reply_markup=test_kb(tid));await q.answer('Test to‘xtatildi; ballar hisoblandi')
 @r.callback_query(F.data.startswith('t_delete:'))
 async def td(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];t=db.get_test(tid)
  if not t:return await q.answer('Test topilmadi',show_alert=True)
  kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='HA, BUTUNLAY O‘CHIRISH',callback_data=f't_delete_yes:{tid}')],[InlineKeyboardButton(text='BEKOR QILISH',callback_data=f't_pick:{tid}')]])
  await q.message.edit_text(f"Diqqat! «{t['name']}» testi, savollari va natijalari butunlay o‘chiriladi. Davom etasizmi?",reply_markup=kb);await q.answer()
 @r.callback_query(F.data.startswith('t_delete_yes:'))
 async def td_yes(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];db.delete_test(tid);await q.message.edit_text('Test va unga tegishli savollar/natijalar butunlay o‘chirildi.',reply_markup=tests_kb());await q.answer('O‘chirildi')
 @r.callback_query(F.data.startswith('t_q:'))
 async def tq(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];qs=db.questions_for_test(tid);text='SAVOLLAR\n\n'+('\n'.join(f"{x['number']}. To‘g‘ri javob: {x['answer']}" for x in qs) if qs else 'Savol yo‘q');await q.message.edit_text(text[:3900],reply_markup=test_kb(tid));await q.answer()
 @r.callback_query(F.data=='t_archive_results')
 async def archive_results(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  rows=db.all_permanent_results(200)
  lines=['UMUMIY REYTING ARXIVI','Barcha testlar bo‘yicha saqlangan natijalar:','']
  for i,x in enumerate(rows,1):
   status=(f"{float(x['score'] or 0):.2f} ball · {x['grade'] or '—'}" if x['submitted'] else 'Yakunlanmagan')
   when=str(x['finished_at'] or x['started_at'] or x['archived_at'] or '')[:16].replace('T',' ')
   lines.append(f"{i}. {x['full_name'] or 'Ismsiz'} (TG:{x['telegram_id']}) · {x['test_name'] or 'Test'} [{x['test_code'] or 'kod yo‘q'}] · {status} · {when}")
  body='\n'.join(lines) if rows else 'Hozircha saqlangan natijalar yo‘q.'
  await q.message.edit_text(body[:3900],reply_markup=tests_kb());await q.answer()

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
 @r.callback_query(F.data=='broadcast_send')
 async def broadcast_send(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  pending=json.loads(db.get_setting('pending_broadcast','{}') or '{}');message=str(pending.get('text','')).strip()
  groups=json.loads(db.get_setting('known_groups','[]') or '[]')
  if not message:return await q.answer('Yuboriladigan xabar topilmadi.',show_alert=True)
  sent=0;failed=0
  for group in groups:
   try:
    await BOT.send_message(int(group['id']),message);sent+=1
   except Exception:
    failed+=1
  db.set_setting('pending_broadcast','{}');db.update_user(ADMIN,state='admin')
  await q.message.answer(f"GURUH XABARI YAKUNLANDI\\nYuborildi: {sent}\\nYuborilmadi: {failed}")
  await q.answer('Yakunlandi')
 @r.callback_query(F.data=='broadcast_cancel')
 async def broadcast_cancel(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  db.set_setting('pending_broadcast','{}');db.update_user(ADMIN,state='admin')
  await q.message.answer('Guruh xabari bekor qilindi.')
  await q.answer('Bekor qilindi')
 @r.callback_query(F.data=='notification_send')
 async def notification_send(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  pending=json.loads(db.get_setting('pending_notification','{}') or '{}');message=str(pending.get('text','')).strip()
  if not message:return await q.answer('Yuboriladigan xabar topilmadi.',show_alert=True)
  users=db.all_registered_users();sent=0;failed=0
  for user in users:
   uid=int(user['telegram_id'])
   if uid<=0 or uid==ADMIN:continue
   try:
    await BOT.send_message(uid,message);sent+=1
   except Exception:failed+=1
   if sent%25==0:await asyncio.sleep(.1)
  db.set_setting('pending_notification','{}');db.update_user(ADMIN,state='admin')
  await q.message.answer(f"BILDIRISHNOMA YAKUNLANDI\\nYuborildi: {sent}\\nYuborilmadi: {failed}")
  await q.answer('Yakunlandi')
 @r.callback_query(F.data=='notification_cancel')
 async def notification_cancel(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  db.set_setting('pending_notification','{}');db.update_user(ADMIN,state='admin')
  await q.message.answer('Bildirishnoma bekor qilindi.')
  await q.answer('Bekor qilindi')
 @r.callback_query(F.data.startswith('premium_set:'))
 async def premium_set(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tier=q.data.split(':',1)[1]
  if tier not in ('premium','default'):return await q.answer('Tarif noto‘g‘ri.',show_alert=True)
  try:target=int(db.get_setting('premium_target_user','0'))
  except Exception:target=0
  user=db.get_user(target)
  if not user:return await q.answer('Foydalanuvchi topilmadi.',show_alert=True)
  db.set_tier(target,tier,ADMIN);db.update_user(ADMIN,state='admin')
  await q.message.answer(f"Tarif yangilandi: {user['full_name'] or target} — {'PREMIUM' if tier=='premium' else 'ODDIY'}.")
  await q.answer('Saqlandi')
 dp.include_router(r)
,command,re.I)
  if toggle_match:
   verb=toggle_match.group(1).casefold();code=toggle_match.group(2).strip();test=db.get_test_by_code(code)
   if not test:return {'ok':True,'reply':f"'{code}' kodi bilan test topilmadi. Kodni tekshirib qayta yuboring."}
   desired_active=verb in ('och','qayta och')
   if bool(int(test['active']))==desired_active:return {'ok':True,'reply':f"{test['name']} hozirning o‘zida {'ochiq' if desired_active else 'yopiq'}."}
   return {'ok':True,'reply':f"Amal tayyor: {test['name']} testini {'ochish' if desired_active else 'to‘xtatish'}. Tasdiqlasangiz bajaraman.",'action':{'type':'test_toggle','test_id':str(test['test_id']),'code':str(test['code']),'name':str(test['name']),'active':desired_active}}
  if re.search(r'majburiy\s+obuna.*(?:o[\'’‘]?chir|off)',low):
   return {'ok':True,'reply':'Majburiy obunani o‘chirishni tasdiqlang. Bu barcha foydalanuvchilar uchun obuna tekshiruvini o‘chiradi.','action':{'type':'subscription_required','enabled':False}}
  if re.search(r'majburiy\s+obuna.*(?:yoq|on)',low):
   channels=db.get_setting('subscription_channels','')
   if not channels or channels in ('[]','{}'):return {'ok':True,'reply':'Avval admin menyusidagi “Majburiy obuna” orqali kanal(lar)ni kiriting. Hozir kanal ro‘yxati bo‘sh.'}
   return {'ok':True,'reply':'Majburiy obunani yoqishni tasdiqlang. Bot kanallarga admin sifatida qo‘shilgan bo‘lishi kerak.','action':{'type':'subscription_required','enabled':True}}
  window_match=re.search(r'(?:jadval|ish vaqti).*?((?:[01]\d|2[0-3]):[0-5]\d)\s*[-–]\s*((?:[01]\d|2[0-3]):[0-5]\d)',low)
  if window_match:
   start,end=window_match.groups()
   return {'ok':True,'reply':f"Ish vaqti jadvalini {start}-{end} qilib saqlashni tasdiqlang. Eslatma: bu sozlama Render Free serverini uyqudan majburan uyg‘otmaydi.",'action':{'type':'awake_window','start':start,'end':end}}
  context=p.get('context',{})
  if not isinstance(context,dict):context={}
  safe_stats=context.get('stats',{}) if isinstance(context.get('stats',{}),dict) else {}
  safe_tests=context.get('tests',[]) if isinstance(context.get('tests',[]),list) else []
  safe_tests=[{'name':str(t.get('name',''))[:120],'code':str(t.get('code',''))[:40],'active':bool(t.get('active')),'questions':int(t.get('questions',0) or 0),'participants':int(t.get('participants',0) or 0),'completed':int(t.get('completed',0) or 0)} for t in safe_tests[:30] if isinstance(t,dict)]
  system='You are Jarvis, the AI admin assistant for Nur oqıw orayı Milliy sertifikat test system. Reply in clear Uzbek Latin or Qaraqalpaq Latin. Be concise and practical. You can use the LIVE SNAPSHOT below to answer questions about bot users, tests, and results, but this snapshot is read-only and may be absent. You cannot directly change hosting, environment variables, secrets, or data in this chat. Never claim an action succeeded unless an API confirms it. For changes, explain what should be changed and request confirmation through supported admin controls. Never reveal secrets or ask the user to paste API keys into chat. LIVE SNAPSHOT: '+json.dumps({'stats':safe_stats,'tests':safe_tests},ensure_ascii=False)
  payload={'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'input':[{'role':'system','content':system}]+messages,'max_output_tokens':1200}
  def call_api():
   req_obj=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/json'},method='POST')
   with urllib.request.urlopen(req_obj,timeout=45) as response:return json.loads(response.read().decode('utf-8'))
  try:
   result=await asyncio.to_thread(call_api)
   answer=str(result.get('output_text','')).strip()
   if not answer:
    chunks=[]
    for item in result.get('output',[]):
     for part in item.get('content',[]):
      if part.get('type')=='output_text':chunks.append(str(part.get('text','')))
    answer='\n'.join(chunks).strip()
   if not answer:return {'ok':False,'error':'empty_response'}
   return {'ok':True,'reply':answer}
  except urllib.error.HTTPError as exc:
   if exc.code==401:return {'ok':False,'error':'api_key_invalid'}
   logging.getLogger('nur-oqiw.jarvis').warning('Jarvis API returned HTTP %s',exc.code)
   return {'ok':False,'error':'jarvis_api_error'}
  except Exception:
   logging.getLogger('nur-oqiw.jarvis').exception('Jarvis API request failed')
   return {'ok':False,'error':'jarvis_api_error'}

 @core.app.get('/api/admin/overview')
 async def admin_overview(req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  tests=[];all_rows=[]
  for t in db.all_tests():
   attempts=db.all_attempts_for_test(t['test_id'])
   done=[a for a in attempts if a['submitted']]
   ranked=sorted(done,key=lambda a:(-float(a['score'] or 0),str(a['finished_at'] or '9999')))
   participants=[{'full_name':a['full_name'] or 'Ismsiz','telegram_id':int(a['telegram_id']),'score':float(a['score'] or 0),'grade':a['grade'] or '', 'submitted':bool(a['submitted']),'started_at':a['started_at'],'finished_at':a['finished_at']} for a in sorted(attempts,key=lambda a:str(a['started_at'] or ''),reverse=True)]
   tests.append({'test_id':str(t['test_id']),'name':t['name'],'code':t['code'],'active':bool(int(t['active'])),'questions':len(db.questions_for_test(t['test_id'])),'participants':len(attempts),'completed':len(done),'ranking':participants and [{'rank':i+1,'full_name':a['full_name'] or 'Ismsiz','score':float(a['score'] or 0),'grade':a['grade'] or ''} for i,a in enumerate(ranked[:10])] or [],'recent':participants[:50]})
   all_rows.extend(participants)
  with db.conn() as con:
   user_count=int(con.execute("SELECT COUNT(*) AS n FROM users").fetchone()['n'])
  return {'ok':True,'stats':{'users':user_count,'tests':len(tests),'participants':len(all_rows),'completed':sum(1 for a in all_rows if a['submitted'])},'tests':tests}
 @core.app.post('/api/admin/test/toggle')
 async def admin_toggle_test(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id','')).strip();t=db.get_test(test_id)
  if not t:return {'ok':False,'error':'test_not_found'}
  if int(t['active']):
   qs=db.questions_for_test(test_id);closed=0
   for a in db.all_attempts_for_test(test_id):
    if a['submitted'] or not a['started_at']:continue
    state,_,_,_,_=finish_attempt_atomically(test_id,int(a['telegram_id']),qs,datetime.now(TZ).isoformat())
    if state=='ok':closed+=1
   db.set_test_active(test_id,0)
   return {'ok':True,'active':False,'finalized':closed,'message':'Test to‘xtatildi; javoblar bo‘yicha ball hisoblandi.'}
  db.set_test_active(test_id,1)
  return {'ok':True,'active':True,'finalized':0,'message':'Test qayta ochildi.'}
 @core.app.get('/api/test/state')
 async def state(req: Request):
  tid,u=await auth(req);c=req.query_params.get('code','').strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  if not t:return {'ok':False,'error':'test_not_found'}
  if not db.questions_for_test(t['test_id']):return {'ok':False,'error':'test_not_ready','test_name':t['name']}
  if u['test_id']!=t['test_id']:db.update_user(tid,test_id=t['test_id'],code_ok=1,state='ready');u=db.get_user(tid)
  if not u['full_name']:return {'ok':False,'error':'registration_required','test_name':t['name']}
  a=db.ensure_attempt(t['test_id'],tid)
  if a['submitted']:
   answers=json.loads(a['answers_json'] or '{}');correct,total,unanswered=result_counts(answers,db.questions_for_test(t['test_id']))
   return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade'],'correct_count':correct,'total_questions':total,'unanswered_count':unanswered,'test_name':t['name'],'full_name':u['full_name']}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
  if not a['started_at']:
   if not opened(t):return {'ok':False,'error':'test_closed','test_name':t['name']}
   db.update_attempt(a['attempt_id'],started_at=datetime.now(TZ).isoformat(),status='active');a=db.get_attempt(t['test_id'],tid)
  if expired(a,t):
   sc,gr=finalize_expired(a,t);return {'ok':False,'error':'already_submitted','score':sc,'grade':gr,'test_name':t['name'],'full_name':u['full_name']}
  qs=db.questions_for_test(t['test_id']);order=question_order_for_attempt(a,qs);by_number={int(q['number']):q for q in qs}
  answers=json.loads(a['answers_json'] or '{}');answers.pop('_question_order',None)
  results={str(q['number']):('correct' if db.normalize(answers.get(str(q['number']),''))==db.normalize(q['answer']) else 'wrong') for q in qs if str(q['number']) in answers and q['kind']!='written'}
  return {'ok':True,'full_name':u['full_name'],'answers':answers,'results':results,'ends_at':None,'test_name':t['name'],'test_code':t['code'],'total_questions':len(qs),'questions':[{'id':by_number[n]['number'],'display_number':i+1,'question':by_number[n]['question'] or '', 'options':(json.loads(by_number[n]['options_json'] or '[]') if by_number[n]['options_json'] else []) or ['A','B','C','D'], 'kind':by_number[n]['kind'],'image_url':by_number[n]['image_url'] or ''} for i,n in enumerate(order)]}
 @core.app.get('/api/test/questions')
 async def questions(req: Request):
  tid,u=await auth(req);c=req.query_params.get('code','').strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
  if not u['full_name'] or u['test_id']!=t['test_id'] or not opened(t):return {'ok':False,'error':'test_not_started'}
  a=db.get_attempt(t['test_id'],tid)
  if not a or not a['started_at'] or a['submitted']:return {'ok':False,'error':'test_not_started'}
  qs=db.questions_for_test(t['test_id']);order=question_order_for_attempt(a,qs);by_number={int(q['number']):q for q in qs}
  return {'ok':True,'questions':[{'id':by_number[n]['number'],'display_number':i+1,'question':by_number[n]['question'] or '', 'options':(json.loads(by_number[n]['options_json'] or '[]') if by_number[n]['options_json'] else []) or ['A','B','C','D'], 'kind':by_number[n]['kind'],'image_url':by_number[n]['image_url'] or ''} for i,n in enumerate(order)]}
 @core.app.post('/api/test/answer')
 async def answer(p:dict, request: Request):
  raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or p.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;c=str(p.get('code','')).strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t or not u['full_name']:return {'ok':False,'error':'not_authorized'}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
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
   pass
  else:
   v=v.upper()
   try:
    option_list=json.loads(q['options_json'] or '[]')
   except Exception:
    option_list=[]
   allowed={chr(65+i) for i in range(min(26,len(option_list) if option_list else 4))}
   if v not in allowed:return {'ok':False,'error':'invalid_answer'}
  saved=save_answer_atomically(t['test_id'],tid,q['number'],v)
  if saved=='locked':return {'ok':False,'error':'answer_locked'}
  if saved=='submitted':return {'ok':False,'error':'already_submitted'}
  if saved!='ok':return {'ok':False,'error':'test_not_started'}
  return {'ok':True,'number':q['number'],'correct': (db.normalize(v)==db.normalize(q['answer'])) if q['kind']!='written' else None}
 @core.app.post('/api/test/finish')
 async def finish(p:dict, request: Request):
  raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or p.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;c=str(p.get('code','')).strip();t=db.get_test_by_code(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t or not u['full_name']:return {'ok':False,'error':'not_authorized'}
  if u['test_id']!=t['test_id']:return {'ok':False,'error':'test_not_started'}
  a=db.get_attempt(t['test_id'],tid)
  if not a or not a['started_at']:return {'ok':False,'error':'test_not_started'}
  if a['submitted']:
   answers=json.loads(a['answers_json'] or '{}');correct,total,_=result_counts(answers,db.questions_for_test(t['test_id']))
   return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade'],'correct_count':correct,'total_questions':total}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
  if expired(a,t):
   sc,gr=finalize_expired(a,t);return {'ok':True,'score':sc,'grade':gr,'full_name':u['full_name'],'test_name':t['name']}
  if not opened(t):return {'ok':False,'error':'test_closed'}
  status,sc,gr,correct,total=finish_attempt_atomically(t['test_id'],tid,db.questions_for_test(t['test_id']),datetime.now(TZ).isoformat())
  if status=='not_started':return {'ok':False,'error':'test_not_started'}
  if status=='already_submitted':return {'ok':False,'error':'already_submitted','score':sc,'grade':gr,'correct_count':correct,'total_questions':total}
  return {'ok':True,'score':sc,'grade':gr,'correct_count':correct,'total_questions':total,'wrong_count':max(0,total-correct),'full_name':u['full_name'],'test_name':t['name']}
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
 @r.message(F.text=='Mening natijam')
 async def user_results(m:Message):
  u=db.get_user(m.from_user.id)
  if not u:return await m.answer("Siz hali ro‘yxatdan o‘tmagansiz. /start ni bosing.",reply_markup=user_menu())
  with db.conn() as c:
   rows=c.execute("SELECT a.test_id,t.name,t.code,a.started_at,a.finished_at,a.score,a.grade,a.submitted FROM test_attempts a LEFT JOIN tests t ON t.test_id=a.test_id WHERE a.telegram_id=? ORDER BY COALESCE(a.finished_at,a.started_at) DESC",(m.from_user.id,)).fetchall()
  if not rows:return await m.answer("Hozircha test natijangiz yo‘q.",reply_markup=user_menu())
  lines=["MENING NATIJALARIM",""]
  for i,row in enumerate(rows[:15],1):
   state=(f"{float(row['score'] or 0):.2f} ball | {row['grade'] or '—'}" if row['submitted'] else "Yakunlanmagan")
   lines.append(f"{i}. {row['name'] or 'Test'} ({row['code'] or 'kod yo‘q'}) — {state}")
  await m.answer('\\n'.join(lines),reply_markup=user_menu())
 @r.message(F.text=='Tariflar')
 async def tariffs(m:Message):
  await m.answer('Tariflar bo‘yicha ma’lumot olish uchun administratorga murojaat qiling: @up17v',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ADMIN BILAN BOG‘LANISH',url='https://t.me/up17v')]]))
 @r.message(F.text=='Yordam')
 async def help_user(m:Message):
  await m.answer('Savol yoki muammo bo‘lsa, administratorga yozing: @up17v',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ADMIN BILAN BOG‘LANISH',url='https://t.me/up17v')]]))
 async def check_prompt(tid,fake_id,index):
  t=db.get_test(tid);qs=db.questions_for_test(tid);u=db.get_user(fake_id);a=db.get_attempt(tid,fake_id)
  if not t or not u or not a:return await BOT.send_message(ADMIN,'Tekshirish sessiyasi topilmadi.')
  if index>=len(qs):
   answers=json.loads(a['answers_json'] or '{}')
   score_value=round(sum(1 for x in qs if norm(answers.get(str(x['number']),' '))==norm(x['answer']))/len(qs)*100,2) if qs else 0
   grade_value=grade(score_value);finished=datetime.now(TZ).isoformat()
   db.update_attempt(a['attempt_id'],score=score_value,grade=grade_value,submitted=1,status='submitted',finished_at=finished)
   db.update_user(fake_id,score=score_value,grade=grade_value,submitted=1,finished_at=finished)
   return await BOT.send_message(ADMIN,f"TEKSHIRISH TUGADI\\nAkkaunt: {u['full_name']}\\nTest: {t['name']}\\nNatija: {score_value:.2f} ball · {grade_value}",reply_markup=test_kb(tid))
  x=qs[index];head=f"TEKSHIRISH — {u['full_name']}\\n{t['name']}\\nSavol {index+1}/{len(qs)}\\n{x['question'] or (str(x['number'])+'-savol')}\\n"
  if x['kind']=='written':
   ast(f"check_written:{tid}:{fake_id}:{index}")
   return await BOT.send_message(ADMIN,head+"\\nTo‘g‘ri yozma javobni kiriting (simulyatsiya):")
  kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=z,callback_data=f"t_check_ans:{tid}:{fake_id}:{index}:{z}") for z in 'ABCD']])
  return await BOT.send_message(ADMIN,head+"\\nVariantni tanlang:",reply_markup=kb)
 @r.message(F.from_user.id==ADMIN)
 async def admin_text(m:Message):
  u=db.ensure_user(ADMIN);s=u['state'] or 'admin';txt=(m.text or '').strip()
  if txt in {'Test sozlamalari','Ishtirokchilar','Statistika','Guruhlar holati','Guruhga xabar yuborish','Bildirishnoma','Ish vaqti jadvali','Majburiy obuna','PDF natijalar','Tekshirish','Tariflar','Botni uyg‘otish','Render limitini ko‘rish'}:
   ast('admin');u=db.ensure_user(ADMIN);s='admin'
  if s.startswith('check_written:'):
   try:
    _,tid,fake_id,index=s.split(':');fake_id=int(fake_id);index=int(index)
    a=db.get_attempt(tid,fake_id);qs=db.questions_for_test(tid)
    if not a or index>=len(qs):raise ValueError()
    answers=json.loads(a['answers_json'] or '{}');answers[str(qs[index]['number'])]=txt
    db.update_attempt(a['attempt_id'],answers_json=json.dumps(answers,ensure_ascii=False));ast('admin')
    return await check_prompt(tid,fake_id,index+1)
   except Exception:return await m.answer('Tekshirish javobi saqlanmadi. Tekshirishni qaytadan boshlang.')
  if txt=='Render limitini ko‘rish':
   usage=await render_usage_data()
   if not usage.get('ok'):
    reason='RENDER_API_KEY ulanmagan.' if usage.get('error')=='render_api_key_missing' else 'Render metrikasini olishning imkoni bo‘lmadi.'
    return await m.answer(f"RENDER FREE LIMITI\\n\\nOylik limit: 750 instance-soat\\n\\n{reason}\\nAniq limitni Render Billing sahifasidan ko‘ring: https://dashboard.render.com/billing\\n\\nAniq ko‘rsatkichni admin menyusida olish uchun Render API key yaratib, Render Environment Variables ichiga RENDER_API_KEY nomi bilan saqlang.")
   partial='\\nEslatma: oxirgi 30 kun bilan cheklangan taxminiy hisob.' if usage.get('partial') else ''
   return await m.answer(f"RENDER FREE LIMITI\\n\\nTaxminiy ishlatilgan: {usage['used_hours']} / {usage['limit_hours']} soat\\nQolgan limit: {usage['remaining_hours']} soat\\nIshlatilgan: {usage['percent']}%\\n\\n{usage['note']}{partial}\\nAniq hisob: https://dashboard.render.com/billing")
  if txt=='Botni uyg‘otish':
   try:
    me=await BOT.get_me()
    return await m.answer(f'Bot faol: @{me.username}\nServer ishlayapti. Agar birinchi so‘rov sekin bo‘lsa, Mini App admin panelidagi «Botni uyg‘otish» tugmasini ham bosing.')
   except Exception:
    return await m.answer('Bot hozir javob bermadi. Biroz kutib qayta urinib ko‘ring.')
  if txt in {'/statistika','Statistika'}:
   users=db.all_registered_users();tests=db.all_tests();attempts=[a for t in tests for a in db.all_attempts_for_test(t['test_id'])];groups=json.loads(db.get_setting('known_groups','[]') or '[]')
   return await m.answer(f"BOT STATISTIKASI\\n\\nFoydalanuvchilar: {len(users)}\\nTestlar: {len(tests)}\\nUrinishlar: {len(attempts)}\\nYakunlangan testlar: {sum(1 for a in attempts if a['submitted'])}\\nGuruhlar: {len(groups)}\\nVaqt zonasi: Asia/Tashkent",reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Test sozlamalari'),KeyboardButton(text='Ishtirokchilar')],[KeyboardButton(text='Statistika'),KeyboardButton(text='Guruhlar holati')],[KeyboardButton(text='Guruhga xabar yuborish'),KeyboardButton(text='Bildirishnoma')],[KeyboardButton(text='Ish vaqti jadvali'),KeyboardButton(text='Majburiy obuna')],[KeyboardButton(text='PDF natijalar'),KeyboardButton(text='Tekshirish')],[KeyboardButton(text='Tariflar'),KeyboardButton(text='Botni uyg‘otish')]],resize_keyboard=True))
  if txt=='Guruhlar holati':
   groups=json.loads(db.get_setting('known_groups','[]') or '[]')
   if not groups:return await m.answer("Guruhlar ro‘yxati bo‘sh. Botni guruhga qo‘shing va /group_status buyrug‘ini yuboring.")
   lines=['GURUHLAR VA RUXSATLAR','']
   for g in groups[:30]:
    try:
     member=await BOT.get_chat_member(int(g['id']),BOT.id)
     can_send=member.status not in ('left','kicked') and not (member.status=='administrator' and getattr(member,'can_send_messages',True) is False)
     lines.append(f"{g.get('title',g['id'])} ({g['id']}) — {member.status}; xabar yuborish: {'ha' if can_send else 'yo‘q'}")
    except Exception:lines.append(f"{g.get('title',g['id'])} ({g['id']}) — tekshirib bo‘lmadi; bot huquqini tekshiring")
   return await m.answer('\\n'.join(lines)[:3900])
  if txt=='Majburiy obuna':
   ast('subscription_channels')
   current=json.loads(db.get_setting('subscription_channels','[]') or '[]') if db.get_setting('subscription_channels','') else []
   return await m.answer("Majburiy obuna kanallarini @username yoki -100... ID ko‘rinishida, har birini yangi qatordan yuboring. O‘chirish uchun OFF yozing.\\n\\nHozirgi kanallar: "+(', '.join(str(x) for x in current) if current else 'o‘chirilgan'))
  if s=='subscription_channels':
   if txt.strip().upper()=='OFF':
    db.set_setting('subscription_required','0');db.set_setting('subscription_channels','[]');ast('admin')
    return await m.answer("Majburiy obuna o‘chirildi.")
   channels=[x.strip() for x in txt.replace(',','\\n').splitlines() if x.strip()]
   if not channels:return await m.answer("Kanal username yoki ID kiriting, yoki OFF yozing.")
   db.set_setting('subscription_channels',json.dumps(channels,ensure_ascii=False));db.set_setting('subscription_required','1');ast('admin')
   return await m.answer(f"Majburiy obuna saqlandi. Kanallar: {len(channels)}. Bot kanalga admin sifatida qo‘shilganini tekshiring.")
  if txt=='Tariflar':
   ast('premium_user_id')
   return await m.answer("Tarifini o‘zgartirmoqchi bo‘lgan foydalanuvchining Telegram ID raqamini kiriting.")
  if s=='premium_user_id':
   try:target=int(txt)
   except:return await m.answer("Telegram ID faqat raqam bo‘lishi kerak.")
   user=db.get_user(target)
   if not user:return await m.answer("Foydalanuvchi topilmadi. Avval botga /start bosgan bo‘lishi kerak.")
   db.set_setting('premium_target_user',str(target));ast('premium_tier')
   return await m.answer(f"Foydalanuvchi: {user['full_name'] or 'Ismsiz'} (ID {target}). Tarifni tanlang:",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='PREMIUM BERISH',callback_data='premium_set:premium')],[InlineKeyboardButton(text='ODDIY TARIF',callback_data='premium_set:default')]]))
  if txt=='Bildirishnoma':
   ast('notification_message')
   return await m.answer("Barcha bot foydalanuvchilariga yuboriladigan xabarni kiriting. Yuborishdan oldin tasdiqlash chiqadi.")
  if s=='notification_message':
   if not txt:return await m.answer("Xabar matni bo‘sh bo‘lmasin.")
   db.set_setting('pending_notification',json.dumps({'text':txt},ensure_ascii=False));ast('notification_confirm')
   return await m.answer(f"XABAR NAMUNASI\\n\\n{txt[:2500]}\\n\\nBarcha ro‘yxatdan o‘tgan foydalanuvchilarga yuborilsinmi?",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='YUBORISH',callback_data='notification_send'),InlineKeyboardButton(text='BEKOR QILISH',callback_data='notification_cancel')]]))
  if txt=='Ishtirokchilar':
   users=db.all_registered_users()
   if not users:return await m.answer("Hozircha foydalanuvchilar yo‘q.")
   lines=["FOYDALANUVCHILAR RO‘YXATI",""]
   for i,user in enumerate(users[:35],1):
    lines.append(f"{i}. {user['full_name'] or 'Ismsiz'} | ID: {user['telegram_id']} | Tarif: {user['tier'] or 'default'}")
   return await m.answer('\\n'.join(lines)[:3900])
  if txt=='Guruhga xabar yuborish':
   ast('broadcast_message')
   return await m.answer("Guruhlarga yuboriladigan xabar matnini yuboring. Keyin yuborishdan oldin tasdiqlash so‘raladi.")
  if s=='broadcast_message':
   if not txt:return await m.answer("Xabar bo‘sh bo‘lmasin. Matnni qayta yuboring.")
   db.set_setting('pending_broadcast',json.dumps({'text':txt},ensure_ascii=False));ast('broadcast_confirm')
   return await m.answer(f"XABAR NAMUNASI\\n\\n{txt[:2500]}\\n\\nBarcha ro‘yxatdagi guruhlarga yuborilsinmi?",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='YUBORISH',callback_data='broadcast_send'),InlineKeyboardButton(text='BEKOR QILISH',callback_data='broadcast_cancel')]]))
  if txt=='Ish vaqti jadvali':
   current=db.get_setting('awake_window','08:00-22:00');ast('awake_window')
   return await m.answer(f"Toshkent vaqti bilan HH:MM-HH:MM ko‘rinishida kiriting. Hozirgi sozlama: {current}.\\nEslatma: Render bepul xizmat uyquga ketgan bo‘lsa, bot ichidagi jadvalning o‘zi uni uyg‘ota olmaydi; tashqi uptime monitor kerak bo‘ladi.")
  if s=='awake_window':
   import re
   if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d',txt):return await m.answer("Format noto‘g‘ri. Masalan: 07:30-23:00")
   db.set_setting('awake_window',txt);ast('admin')
   return await m.answer(f"Jadval saqlandi: {txt} (Asia/Tashkent). Uyqudagi Render instansiyasini tashqaridan uyg‘otmaydi.")
  if txt in {'Test sozlamalari','Ishtirokchilar','PDF natijalar','Tekshirish'}:return await m.answer('TESTLAR — saqlangan testlar',reply_markup=tests_kb())
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
   d=draft();d['count']=n;d['items']=[];save_draft(d);ast('new_kind')
   return await m.answer(f'1/{n}-savol turini tanlang:',reply_markup=new_question_type_kb())
  if s=='new_written_answer':
   if not txt:return await m.answer('Yozma javob bo‘sh bo‘lmasin. To‘g‘ri javobni kiriting:')
   d=draft();d.setdefault('items',[]).append({'kind':'written','answer':txt});save_draft(d);done=len(d['items']);total=int(d['count'])
   if done<total:
    ast('new_kind');return await m.answer(f'{done+1}/{total}-savol turini tanlang:',reply_markup=new_question_type_kb())
   try:
    if len(d['items'])!=total:return await m.answer('Savollar to‘liq emas. Test hali saqlanmadi.')
    t=db.create_test_with_questions(d['name'],d['code'],d['items']);clear_draft();ast('admin')
    return await m.answer(f"TEST SAQLANDI\n\n{t['name']}\nKod: {t['code']}\nSavollar: {total}\nHolat: DOIMO OCHIQ",reply_markup=test_kb(t['test_id']))
   except Exception as e:return await m.answer(f'Test saqlanmadi: {e}')
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
 @r.callback_query(F.data=='t_check_list')
 async def tcl(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  await q.message.edit_text('Tekshirish uchun testni tanlang:',reply_markup=tests_kb());await q.answer()
 @r.callback_query(F.data.startswith('t_check:'))
 async def tcheck(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];t=db.get_test(tid)
  if not t:return await q.answer('Test topilmadi',show_alert=True)
  if not int(t['active']):return await q.answer('Avval testni qayta oching.',show_alert=True)
  fake_name='user'+str(secrets.randbelow(900)+100);fake_id=-(int(secrets.randbelow(900000000)+100000000))
  while db.get_user(fake_id):fake_id-=1
  db.upsert_user(fake_id,fake_name);db.update_user(fake_id,code_ok=1,state='ready',test_id=tid)
  db.ensure_attempt(tid,fake_id)
  a=db.get_attempt(tid,fake_id);db.update_attempt(a['attempt_id'],started_at=datetime.now(TZ).isoformat(),status='active')
  await q.message.answer(f"TEKSHIRISH AKKAUNTI YARATILDI\\nLogin: {fake_name}\\nTest: {t['name']}\\nKod: {t['code']}\\n\\nEndi har bir savolga javob berib test oqimini tekshirishingiz mumkin.")
  await check_prompt(tid,fake_id,0)
  await q.answer('Tekshiruv akkaunti yaratildi')
 @r.callback_query(F.data.startswith('t_check_ans:'))
 async def tcheck_answer(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  try:
   _,tid,fake_id,index,letter=q.data.split(':');fake_id=int(fake_id);index=int(index)
   qs=db.questions_for_test(tid);a=db.get_attempt(tid,fake_id)
   if not a or index>=len(qs) or letter not in 'ABCD':return await q.answer('Tekshirish sessiyasi eskirgan.',show_alert=True)
   answers=json.loads(a['answers_json'] or '{}');answers[str(qs[index]['number'])]=letter
   db.update_attempt(a['attempt_id'],answers_json=json.dumps(answers,ensure_ascii=False))
   await q.answer('Javob qabul qilindi')
   await check_prompt(tid,fake_id,index+1)
  except Exception:
   import logging;logging.getLogger('nur-oqiw').exception('test check answer')
   await q.answer('Javobni saqlashda xatolik',show_alert=True)
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
  d.setdefault('items',[]).append({'kind':'choice','answer':letter});save_draft(d)
  done=len(d['items']);total=int(d['count'])
  if done<total:
   ast('new_kind');await q.message.answer(f'{done+1}/{total}-savol turini tanlang:',reply_markup=new_question_type_kb())
   return await q.answer(f'{done}/{total} saqlandi')
  try:
   if db.test_code_exists(d['code']):return await q.answer('Bu kod avval ishlatilgan. Boshqa kod tanlang.',show_alert=True)
   if len(d['items'])!=total:return await q.answer('Barcha savollar tugallanmagan. Test saqlanmadi.',show_alert=True)
   t=db.create_test_with_questions(d['name'],d['code'],d['items'])
   clear_draft();ast('admin')
   await q.message.answer(f"TEST SAQLANDI\n\n{t['name']}\nKod: {t['code']}\nSavollar: {total}\nHolat: DOIMO OCHIQ",reply_markup=test_kb(t['test_id']))
   await q.answer('Test saqlandi')
  except Exception:
   import logging;logging.getLogger('nur-oqiw').exception('create test from answer key')
   return await q.answer('Test saqlanmadi. Qaytadan urinib ko‘ring.',show_alert=True)
 @r.callback_query(F.data.startswith('t_new_kind:'))
 async def new_kind(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  d=draft();u=db.get_user(ADMIN);kind=q.data.rsplit(':',1)[-1]
  if not d.get('code') or not d.get('name') or not d.get('count') or not u or u['state']!='new_kind':
   return await q.answer('Test yaratish bosqichi eskirgan. Yangi testni qaytadan boshlang.',show_alert=True)
  if len(d.get('items',[]))>=int(d['count']):return await q.answer('Barcha savollar kiritilgan.',show_alert=True)
  d['current_kind']=kind;save_draft(d);number=len(d.get('items',[]))+1;total=int(d['count'])
  if kind=='choice':
   ast('new_answer');await q.message.answer(f'{number}/{total}-savol uchun to‘g‘ri variantni tanlang:',reply_markup=new_answer_kb())
  elif kind=='written':
   ast('new_written_answer');await q.message.answer(f'{number}/{total}-savol uchun to‘g‘ri yozma javobni kiriting:')
  else:return await q.answer('Savol turi noto‘g‘ri.',show_alert=True)
  await q.answer()

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
  tid=q.data.split(':',1)[1];db.set_test_active(tid,1);t=db.get_test(tid)
  await q.message.edit_text(f"TEST QAYTA OCHILDI\n\n{t['name']}\nKod: {t['code']}",reply_markup=test_kb(tid));await q.answer('Test qayta ochildi')
 @r.callback_query(F.data.startswith('t_close:'))
 async def tx(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];t=db.get_test(tid);qs=db.questions_for_test(tid);closed_count=0
  for a in db.all_attempts_for_test(tid):
   if a['submitted'] or not a['started_at']:continue
   status,_,_,_,_=finish_attempt_atomically(tid,int(a['telegram_id']),qs,datetime.now(TZ).isoformat())
   if status=='ok':closed_count+=1
  db.set_test_active(tid,0)
  await q.message.edit_text(f"TEST TO‘XTATILDI\n\n{t['name']}\nKod: {t['code']}\nYakunlanmagan urinishlarga javoblari bo‘yicha ball hisoblandi: {closed_count} ta.",reply_markup=test_kb(tid));await q.answer('Test to‘xtatildi; ballar hisoblandi')
 @r.callback_query(F.data.startswith('t_delete:'))
 async def td(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];t=db.get_test(tid)
  if not t:return await q.answer('Test topilmadi',show_alert=True)
  kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='HA, BUTUNLAY O‘CHIRISH',callback_data=f't_delete_yes:{tid}')],[InlineKeyboardButton(text='BEKOR QILISH',callback_data=f't_pick:{tid}')]])
  await q.message.edit_text(f"Diqqat! «{t['name']}» testi, savollari va natijalari butunlay o‘chiriladi. Davom etasizmi?",reply_markup=kb);await q.answer()
 @r.callback_query(F.data.startswith('t_delete_yes:'))
 async def td_yes(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];db.delete_test(tid);await q.message.edit_text('Test va unga tegishli savollar/natijalar butunlay o‘chirildi.',reply_markup=tests_kb());await q.answer('O‘chirildi')
 @r.callback_query(F.data.startswith('t_q:'))
 async def tq(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];qs=db.questions_for_test(tid);text='SAVOLLAR\n\n'+('\n'.join(f"{x['number']}. To‘g‘ri javob: {x['answer']}" for x in qs) if qs else 'Savol yo‘q');await q.message.edit_text(text[:3900],reply_markup=test_kb(tid));await q.answer()
 @r.callback_query(F.data=='t_archive_results')
 async def archive_results(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  rows=db.all_permanent_results(200)
  lines=['UMUMIY REYTING ARXIVI','Barcha testlar bo‘yicha saqlangan natijalar:','']
  for i,x in enumerate(rows,1):
   status=(f"{float(x['score'] or 0):.2f} ball · {x['grade'] or '—'}" if x['submitted'] else 'Yakunlanmagan')
   when=str(x['finished_at'] or x['started_at'] or x['archived_at'] or '')[:16].replace('T',' ')
   lines.append(f"{i}. {x['full_name'] or 'Ismsiz'} (TG:{x['telegram_id']}) · {x['test_name'] or 'Test'} [{x['test_code'] or 'kod yo‘q'}] · {status} · {when}")
  body='\n'.join(lines) if rows else 'Hozircha saqlangan natijalar yo‘q.'
  await q.message.edit_text(body[:3900],reply_markup=tests_kb());await q.answer()

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
 @r.callback_query(F.data=='broadcast_send')
 async def broadcast_send(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  pending=json.loads(db.get_setting('pending_broadcast','{}') or '{}');message=str(pending.get('text','')).strip()
  groups=json.loads(db.get_setting('known_groups','[]') or '[]')
  if not message:return await q.answer('Yuboriladigan xabar topilmadi.',show_alert=True)
  sent=0;failed=0
  for group in groups:
   try:
    await BOT.send_message(int(group['id']),message);sent+=1
   except Exception:
    failed+=1
  db.set_setting('pending_broadcast','{}');db.update_user(ADMIN,state='admin')
  await q.message.answer(f"GURUH XABARI YAKUNLANDI\\nYuborildi: {sent}\\nYuborilmadi: {failed}")
  await q.answer('Yakunlandi')
 @r.callback_query(F.data=='broadcast_cancel')
 async def broadcast_cancel(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  db.set_setting('pending_broadcast','{}');db.update_user(ADMIN,state='admin')
  await q.message.answer('Guruh xabari bekor qilindi.')
  await q.answer('Bekor qilindi')
 @r.callback_query(F.data=='notification_send')
 async def notification_send(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  pending=json.loads(db.get_setting('pending_notification','{}') or '{}');message=str(pending.get('text','')).strip()
  if not message:return await q.answer('Yuboriladigan xabar topilmadi.',show_alert=True)
  users=db.all_registered_users();sent=0;failed=0
  for user in users:
   uid=int(user['telegram_id'])
   if uid<=0 or uid==ADMIN:continue
   try:
    await BOT.send_message(uid,message);sent+=1
   except Exception:failed+=1
   if sent%25==0:await asyncio.sleep(.1)
  db.set_setting('pending_notification','{}');db.update_user(ADMIN,state='admin')
  await q.message.answer(f"BILDIRISHNOMA YAKUNLANDI\\nYuborildi: {sent}\\nYuborilmadi: {failed}")
  await q.answer('Yakunlandi')
 @r.callback_query(F.data=='notification_cancel')
 async def notification_cancel(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  db.set_setting('pending_notification','{}');db.update_user(ADMIN,state='admin')
  await q.message.answer('Bildirishnoma bekor qilindi.')
  await q.answer('Bekor qilindi')
 @r.callback_query(F.data.startswith('premium_set:'))
 async def premium_set(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tier=q.data.split(':',1)[1]
  if tier not in ('premium','default'):return await q.answer('Tarif noto‘g‘ri.',show_alert=True)
  try:target=int(db.get_setting('premium_target_user','0'))
  except Exception:target=0
  user=db.get_user(target)
  if not user:return await q.answer('Foydalanuvchi topilmadi.',show_alert=True)
  db.set_tier(target,tier,ADMIN);db.update_user(ADMIN,state='admin')
  await q.message.answer(f"Tarif yangilandi: {user['full_name'] or target} — {'PREMIUM' if tier=='premium' else 'ODDIY'}.")
  await q.answer('Saqlandi')
 dp.include_router(r)
