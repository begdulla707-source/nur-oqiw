from fastapi import Request
import asyncio
import json,secrets,os,tempfile,reportlab,urllib.request,urllib.error,urllib.parse,logging,zipfile
from datetime import datetime,time,timedelta
from aiogram import Router,F
from aiogram.filters import CommandStart
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo,FSInputFile,ReplyKeyboardMarkup,ReplyKeyboardRemove,KeyboardButton,KeyboardButtonRequestUsers
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from xml.sax.saxutils import escape
from html import escape as html_escape
from . import db, menu_settings as menu_config
PDF_FONT='Helvetica'
for _font_name,_font_path in (
 ('NurDejaVu','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
 ('NurVera',os.path.join(os.path.dirname(reportlab.__file__),'fonts','Vera.ttf')),
):
 try:
  pdfmetrics.registerFont(TTFont(_font_name,_font_path));PDF_FONT=_font_name;break
 except Exception:pass
CORE=ADMIN=BOT=TZ=None;WEBAPP='';MOCK_SUB_CACHE={};MOCK_FINISH_LOCKS={}
def mock_wizard_read():
 try:
  value=json.loads(db.get_setting('admin_mock_wizard','{}') or '{}')
  return value if isinstance(value,dict) else {}
 except Exception:return {}
def mock_wizard_write(value):
 db.set_setting('admin_mock_wizard',json.dumps(value,ensure_ascii=False))
def mock_wizard_clear():
 db.set_setting('admin_mock_wizard','{}')
def mock_ready_kb(test_id):
 url=WEBAPP.rstrip('/')+'/admin#results' if WEBAPP else 'https://nur-oqiw-web.mcweb.uz/admin#results'
 test=db.get_test(test_id);actions=[]
 if test:
  test=dict(test);remaining=mock_remaining_seconds(test);active=bool(int(test.get('active') or 0))
  if not test.get('timer_ends_at') and not any(a['started_at'] for a in db.all_attempts_for_test(test_id)):
   actions.append([InlineKeyboardButton(text='TESTNI BOSHLASH',callback_data=f'mock_start:{test_id}',style='success')])
  elif test.get('timer_ends_at') and active and remaining and remaining>0:
   actions.append([InlineKeyboardButton(text='TESTNI TO‘XTATISH',callback_data=f'mock_stop:{test_id}',style='danger')])
   actions.append([InlineKeyboardButton(text='VAQT QO‘SHISH',callback_data=f'mock_extend:{test_id}',style='primary')])
  else:
   actions.append([InlineKeyboardButton(text='QAYTA O‘TKAZISH',callback_data=f'mock_restart:{test_id}',style='success')])
 return InlineKeyboardMarkup(inline_keyboard=[
  *actions,
  [InlineKeyboardButton(text='NATIJALAR',web_app=WebAppInfo(url=url),style='primary')],
  [InlineKeyboardButton(text='TURLAR · PDF / EXCEL / TAHLIL',callback_data=f'mock_rounds:{test_id}',style='primary')],
  [InlineKeyboardButton(text='MOCK TESTLAR RO‘YXATI',callback_data='mock_list')],
  [InlineKeyboardButton(text='ORTGA QAYTISH',callback_data='mock_back')]
 ])
def mock_question_type_kb():
 return InlineKeyboardMarkup(inline_keyboard=[
  [InlineKeyboardButton(text='ODDIY VARIANT',callback_data='mock_kind:choice',style='primary')],
  [InlineKeyboardButton(text='YOZMA VARIANT',callback_data='mock_kind:written',style='primary')]
 ])
def mock_choice_answer_kb():
 return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=x,callback_data='mock_answer:'+x,style='primary') for x in 'ABCD']])
def mock_save_question(test_id,kind,answer):
 n=len(db.questions_for_test(test_id))+1
 if kind=='choice':db.upsert_test_question(test_id,n,'',['A','B','C','D'],str(answer).upper(),'choice',str(n))
 else:db.upsert_test_question(test_id,n,'',[],str(answer).strip(),'written',str(n))
 return n
async def mock_next_question(message,pending):
 test_id=str(pending.get('test_id') or '');count=int(pending.get('count') or 0);done=len(db.questions_for_test(test_id));test=db.get_test(test_id)
 if not test:return await message.answer('MOCK test topilmadi.')
 if done>=count:
  db.set_test_active(test_id,1);db.set_test_published(test_id,0);mock_wizard_clear();ast('admin')
  return await message.answer(f"MOCK TEST TAYYOR\n\n{test['name']}\nKod: {test['code']}\nSavollar: {done}\nTimer: {int(test['duration_minutes'] or 0)} daqiqa\n\nAvval admin TESTNI BOSHLASH tugmasini bosadi. Taymer shu zahoti boshlanadi; qatnashchilar keyin test kodini kiritadi. Test Aktiv testlar ro‘yxatida ko‘rinmaydi.",reply_markup=mock_admin_reply_kb())
 ast('mock_question_kind')
 return await message.answer(f'{done+1}/{count}-savol turini tanlang:',reply_markup=mock_question_type_kb())
def norm(v):return ' '.join(str(v or '').strip().casefold().split())
def grade(s):
 s=float(s);return 'A+' if s>=90 else 'A' if s>=80 else 'B' if s>=70 else 'C' if s>=60 else 'D' if s>=50 else 'F'
def user_menu():return CORE.user_menu()
async def validate_subscription_channels(channels):
 errors=[];links={}
 for channel in channels:
  try:
   info=await BOT.get_chat(channel)
   member=await BOT.get_chat_member(info.id,BOT.id)
   if member.status not in ('administrator','creator'):
    errors.append(channel+' — bot administrator emas');continue
   if channel.startswith('-100'):
    username=getattr(info,'username',None)
    link='https://t.me/'+username if username else getattr(info,'invite_link',None)
    if not link:
     invitation=await BOT.create_chat_invite_link(chat_id=info.id,name='NUR OQIW obuna')
     link=invitation.invite_link
    if not link or not link.startswith('https://t.me/'):
     errors.append(channel+' — qo‘shilish havolasini yaratib bo‘lmadi')
    else:links[channel]=link
  except Exception:
   errors.append(channel+' — kanal yoki administrator huquqini tekshiring')
 return errors,links

def subscription_admin_kb():
 active=CORE.sub_required()
 return InlineKeyboardMarkup(inline_keyboard=[
  [InlineKeyboardButton(text='YOQISH' if not active else 'YOQILGAN',callback_data='subadmin:on',style='success'),
   InlineKeyboardButton(text='O‘CHIRISH' if active else 'O‘CHIRILGAN',callback_data='subadmin:off',style='danger')],
  [InlineKeyboardButton(text='KANAL QO‘SHISH / TAHRIRLASH',callback_data='subadmin:edit',style='primary')],
  [InlineKeyboardButton(text='KANALLARNI TOZALASH',callback_data='subadmin:clear',style='danger')],
  [InlineKeyboardButton(text='YANGILASH',callback_data='subadmin:status')]
 ])

def subscription_admin_text():
 channels=CORE.sub_channels()
 return '\n'.join(['MAJBURIY OBUNA','',
   'Holat: '+('YOQILGAN' if CORE.sub_required() else 'O‘CHIRILGAN'),
   'Kanallar:',*(channels or ['Kanal belgilanmagan']),'',
   'Tugmalardan foydalaning. Kanallar vaqtincha o‘chirilganda saqlanadi.'])

def tests_kb():
 r=[]
 for t in db.all_tests():
  if int(t['is_mock'] or 0):continue
  state='OCHIQ' if int(t['active']) else 'YOPIQ'
  r.append([InlineKeyboardButton(text=f"{state} | {t['name'][:20]} | {t['code']}",callback_data=f't_pick:{t["test_id"]}',style="success" if int(t["active"]) else "danger")])
 r.append([InlineKeyboardButton(text='YANGI TEST',callback_data='t_new',style='success')])
 r.append([InlineKeyboardButton(text='UMUMIY REYTING ARXIVI',callback_data='t_archive_results')])
 r.append([InlineKeyboardButton(text='TEKSHIRISH',callback_data='t_check_list')])
 return InlineKeyboardMarkup(inline_keyboard=r)
def mock_listing():
 ready=[];drafts=[]
 for row in db.all_tests():
  test=dict(row)
  if not int(test['is_mock'] or 0):continue
  count=len(db.questions_for_test(str(test['test_id'])));has_code=bool(int(test['code_set'] or 0))
  if has_code and count:ready.append((test,count))
  elif has_code or count or str(test['name'] or '').strip().casefold() not in ('','mock'):drafts.append((test,count))
 lines=['MOCK TESTLAR','']
 if ready:lines.append('TAYYOR TESTLAR')
 buttons=[]
 for test,count in ready[:40]:
  test_id=str(test['test_id']);code=str(test['code']);attempts=db.all_attempts_for_test(test_id)
  archived=db.permanent_results_for_test(test_id,5000) if hasattr(db,'permanent_results_for_test') else []
  total_done=len({str(a['attempt_id']) for a in archived if int(a['submitted'] or 0)}|{str(a['attempt_id']) for a in attempts if int(a['submitted'] or 0)})
  started=sum(1 for a in attempts if a['started_at'])
  remaining=mock_remaining_seconds(test);active=bool(int(test['active'] or 0))
  if not test.get('timer_ends_at'):
   timer_state=('TAYMER SOZLANMAGAN · qayta o‘tkazish kerak' if started else f"BOSHLASH KUTILMOQDA · Timer: {int(test['duration_minutes'] or 0)} daqiqa")
  elif remaining is not None and active and remaining>0:
   timer_state='FAOL · Qolgan vaqt: '+format_mock_timer(remaining)
  elif remaining is not None and active:
   timer_state='VAQT TUGAGAN · Yakunlanmoqda'
  elif remaining is not None and remaining>0:
   timer_state='TO‘XTATILGAN · '+format_mock_timer(remaining)+' qoldi'
  else:timer_state='YAKUNLANGAN'
  schedule=''
  if test.get('scheduled_start_at'):
   try:schedule=datetime.fromisoformat(str(test['scheduled_start_at']).replace('Z','+00:00')).astimezone(TZ).strftime('%d/%m/%Y %H:%M')
   except (TypeError,ValueError):schedule='belgilangan'
  cap=int(test.get('participant_limit') or 0)
  lines.append(f"{test['name']} · {code} · {count} savol · {int(test['duration_minutes'] or 0)} daqiqa\n  {timer_state} · Qatnashgan: {started}"+(f'/{cap}' if cap else '')+f' · Natijalar: {total_done}'+(f' · Boshlanish: {schedule}' if schedule else ''))
  if not test.get('timer_ends_at') and not started:
   buttons.append([InlineKeyboardButton(text='TESTNI BOSHLASH · '+str(test['name'])[:20],callback_data=f'mock_start:{test_id}',style='success')])
  elif test.get('timer_ends_at') and active and remaining is not None and remaining>0:
   buttons.append([InlineKeyboardButton(text='TESTNI TO‘XTATISH · '+str(test['name'])[:18],callback_data=f'mock_stop:{test_id}',style='danger')])
   buttons.append([InlineKeyboardButton(text='VAQT QO‘SHISH · '+code[:18],callback_data=f'mock_extend:{test_id}',style='primary')])
  else:
   buttons.append([InlineKeyboardButton(text='QAYTA O‘TKAZISH · '+str(test['name'])[:22],callback_data=f'mock_restart:{test_id}',style='success')])
  buttons.append([InlineKeyboardButton(text='ISHTIROKCHILAR · '+code[:18],callback_data=f'mock_participants:{test_id}',style='primary')])
  if db.mock_rounds_for_test(test_id) or total_done:
   buttons.append([InlineKeyboardButton(text='TURLAR · PDF / EXCEL / TAHLIL · '+code[:15],callback_data=f'mock_rounds:{test_id}',style='primary')])
  if total_done:buttons.append([InlineKeyboardButton(text='UMUMIY PDF · '+code[:18],callback_data=f'mock_pdf:{test_id}',style='primary')])
 if drafts:
  lines.extend(['','TAYYORLANAYOTGAN TESTLAR'])
  for test,count in drafts[:20]:
   test_id=str(test['test_id']);code=str(test['code']) if int(test['code_set'] or 0) else 'kod kiritilmagan'
   lines.append(f"{test['name']} · {code} · {count} savol · {int(test['duration_minutes'] or 0)} daqiqa")
   buttons.append([InlineKeyboardButton(text='TAYYORLASHNI DAVOM ETTIRISH · '+str(test['name'])[:18],callback_data=f'mock_continue:{test_id}')])
 if not ready and not drafts:lines.extend(['','Hozircha tayyor MOCK test yo‘q. Yangi MOCK test yarating.'])
 buttons.extend([[InlineKeyboardButton(text='NATIJALAR PANELI',web_app=WebAppInfo(url=(WEBAPP.rstrip('/')+'/admin#results' if WEBAPP else 'https://nur-oqiw-web.mcweb.uz/admin#results')),style='primary')],[InlineKeyboardButton(text='ORTGA QAYTISH',callback_data='mock_back')]])
 return '\n'.join(lines),InlineKeyboardMarkup(inline_keyboard=buttons)

def mock_admin_reply_kb():
 return menu_config.keyboard(db,'mock_admin',WEBAPP)

def mock_key_check(tid):
 test=db.get_test(tid)
 if not test or not int(test['is_mock'] or 0):return ['MOCK test topilmadi.']
 qs=db.questions_for_test(tid);errors=[]
 if not int(test['code_set'] or 0):errors.append('Test kodi kiritilmagan')
 if not qs:errors.append('Savollar yo‘q')
 expected=int(test['expected_questions'] or 0)
 if expected and len(qs)!=expected:errors.append(f'Savollar soni: {len(qs)}/{expected}')
 numbers=[int(q['number']) for q in qs]
 if numbers!=list(range(1,len(qs)+1)):errors.append('Savollar raqami ketma-ket emas')
 for q in qs:
  number=q['number'];kind=str(q['kind'] or '').lower();answer=str(q['answer'] or '').strip()
  if kind=='choice':
   if answer.upper() not in 'ABCD' or len(answer)!=1:errors.append(f'{number}-savol: A/B/C/D javob kaliti noto‘g‘ri')
   try:options=json.loads(q['options_json'] or '[]')
   except (TypeError,ValueError):options=[]
   if not isinstance(options,list) or len(options)!=4:errors.append(f'{number}-savol: 4 ta variant bo‘lishi kerak')
  elif kind=='written':
   if not answer:errors.append(f'{number}-savol: yozma javob bo‘sh')
  else:errors.append(f'{number}-savol: turi noma’lum')
 return errors

def mock_admin_kb():
 url=WEBAPP.rstrip('/')+'/admin#results' if WEBAPP else 'https://nur-oqiw-web.mcweb.uz/admin#results'
 return mock_admin_reply_kb()
def paid_menu_kb():
 tests=db.paid_tests_for_user(ADMIN,ADMIN)
 rows=[]
 for t in tests[:50]:
  label=('● ' if int(t['active']) else '○ ')+str(t['name'])[:32]+'  ·  '+str(t['code'])[:12]
  rows.append([InlineKeyboardButton(text=label,callback_data='paid_admin:'+str(t['test_id']),
    style='success' if int(t['active']) else 'default')])
 rows.append([InlineKeyboardButton(text='+ YANGI PULLI TEST',callback_data='paid_new',style='primary')])
 return InlineKeyboardMarkup(inline_keyboard=rows)

def paid_test_kb(test_id):
 t=db.get_test(test_id)
 if not t or not db.is_paid_test(test_id):return paid_menu_kb()
 active=bool(int(t['active']))
 return InlineKeyboardMarkup(inline_keyboard=[
  [InlineKeyboardButton(text='SAVOL QO‘SHISH',callback_data='t_add:'+str(test_id),style='primary'),
   InlineKeyboardButton(text='SAVOLLARNI KO‘RISH',callback_data='t_q:'+str(test_id))],
  [InlineKeyboardButton(text='QATNASHCHI QO‘SHISH',callback_data='paid_grant:'+str(test_id),style='success')],
  [InlineKeyboardButton(text='RUXSATLARNI KO‘RISH / O‘CHIRISH',callback_data='paid_members:'+str(test_id))],
  [InlineKeyboardButton(text='NATIJALAR',callback_data='t_results:'+str(test_id))],
  [InlineKeyboardButton(text='TESTNI YOPISH' if active else 'TESTNI OCHISH',
    callback_data=('t_close:' if active else 't_open:')+str(test_id),
    style='danger' if active else 'success')],
  [InlineKeyboardButton(text='PULLI TESTLAR RO‘YXATI',callback_data='paid_list')]
 ])

def group_admin_keyboard(groups):
 rows=[]
 for g in groups[:30]:
  name=str(g.get('title') or g['id'])[:24]
  rows.append([InlineKeyboardButton(text='TARK ETISH · '+name,
      callback_data='group_leave:'+str(g['id']),style='danger')])
 rows.append([InlineKeyboardButton(text='GURUHLARGA XABAR YOZISH',callback_data='group_compose',style='primary')])
 rows.append([InlineKeyboardButton(text='RO‘YXATNI YANGILASH',callback_data='group_refresh')])
 return InlineKeyboardMarkup(inline_keyboard=rows)

def test_kb(t):
 if db.is_paid_test(t):return paid_test_kb(t)
 test=db.get_test(t);active=bool(test and int(test['active']))
 toggle=InlineKeyboardButton(text='TESTNI TO‘XTATISH' if active else 'QAYTA OCHISH',callback_data=f't_close:{t}' if active else f't_open:{t}',style='danger' if active else 'success')
 return InlineKeyboardMarkup(inline_keyboard=[
  [InlineKeyboardButton(text='Savol qo‘shish',callback_data=f't_add:{t}')],
  [InlineKeyboardButton(text='Oddiy variant',callback_data=f't_choice:{t}'),InlineKeyboardButton(text='Yozma variant',callback_data=f't_written:{t}')],
  [InlineKeyboardButton(text='Savollar',callback_data=f't_q:{t}'),InlineKeyboardButton(text='Natijalar',callback_data=f't_results:{t}',style='primary')],
  [InlineKeyboardButton(text='Mini App link',callback_data=f't_link:{t}',style='primary')],
  [InlineKeyboardButton(text='Guruhga yuborish',callback_data=f't_group:{t}')],
  [toggle],
  [InlineKeyboardButton(text='O‘CHIRISH',callback_data=f't_delete:{t}',style='danger')],
  [InlineKeyboardButton(text='Orqaga',callback_data='t_list')]
 ])

def type_kb(t):return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ODDIY VARIANT',callback_data=f't_choice:{t}')],[InlineKeyboardButton(text='YOZMA VARIANT',callback_data=f't_written:{t}')]])
def abcd(t,n):return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=x,callback_data=f't_ans:{t}:{n}:{x}') for x in 'ABCD']])
def new_answer_kb():return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=x,callback_data=f't_new_ans:{x}') for x in 'ABCD']])
def new_question_type_kb(paid=False):
 rows=[
  [InlineKeyboardButton(text='A/B/C/D VARIANTLI',callback_data='t_new_kind:choice',style='primary')],
  [InlineKeyboardButton(text='YOZMA JAVOB',callback_data='t_new_kind:written',style='primary')]
 ]
 if not paid:rows.append([InlineKeyboardButton(text='KO‘P SAVOLLI TEST',callback_data='t_new_kind:multi')])
 return InlineKeyboardMarkup(inline_keyboard=rows)
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
 if not t or not int(t['is_mock'] or 0) or not t['timer_ends_at'] or not a or not a['started_at'] or a['submitted']:return False
 return mock_clock_expired(t)
def mock_clock_expired(t,now=None):
 if not t or not int(t['is_mock'] or 0) or not t['timer_ends_at']:return False
 try:
  ends=datetime.fromisoformat(str(t['timer_ends_at']).replace('Z','+00:00'))
  if ends.tzinfo is None:ends=ends.replace(tzinfo=TZ)
  return (now or datetime.now(TZ))>=ends.astimezone(TZ)
 except Exception:return False
def attempt_ends_at(a,t):
 if not t or not int(t['is_mock'] or 0) or not a or not a['started_at'] or not t['timer_ends_at']:return None
 return str(t['timer_ends_at'])
def ensure_mock_clock(t,now=None):
 if not t or not int(t['is_mock'] or 0) or t['timer_ends_at'] or int(t['duration_minutes'] or 0)<=0:return t
 started=now or datetime.now(TZ);ended=started+timedelta(minutes=int(t['duration_minutes']))
 return db.start_mock_timer(str(t['test_id']),started.isoformat(),ended.isoformat()) or t
def score(t,a):
 q=db.questions_for_test(t['test_id']);return round(sum(norm(a.get(str(x['number']),' '))==norm(x['answer']) for x in q)/len(q)*100,2) if q else 0
def finalize_expired(a,t):
 state,sc,gr,_,_=finish_attempt_atomically(str(t['test_id']),int(a['telegram_id']),db.questions_for_test(t['test_id']),datetime.now(TZ).isoformat())
 return (float(sc or 0),str(gr or ''))

def result_label(a):
 return f"{float(a['score'] or 0):.2f} ball · {a['grade'] or '—'}" if a['submitted'] else 'Natija kutilmoqda'

def mock_grade(s):
 s=float(s)
 return 'A+' if s>=70 else 'A' if s>=65 else 'B+' if s>=60 else 'B' if s>=55 else 'C+' if s>=50 else 'C' if s>=46 else 'NC'

def _sigmoid(v):
 if v>=0:
  z=__import__('math').exp(-min(v,35));return 1/(1+z)
 z=__import__('math').exp(max(v,-35));return z/(1+z)

def rasch_scores(test_id):
 """Fit a dichotomous Rasch model to submitted mock attempts and norm scores to 50±10."""
 qs=db.questions_for_test(test_id);rows=[dict(a) for a in db.all_attempts_for_test(test_id) if int(a['submitted'] or 0)]
 if not qs or not rows:return {}
 import math
 count=len(qs);matrix=[]
 for row in rows:
  try:answers=json.loads(row.get('answers_json') or '{}')
  except Exception:answers={}
  matrix.append([1 if norm(answers.get(str(q['number']),' '))==norm(q['answer']) else 0 for q in qs])
 n=len(matrix)
 if count<2 or n<2:
  return {str(row['attempt_id']):{'score':round(sum(response)/count*100,2),'grade':mock_grade(sum(response)/count*100),'correct_count':sum(response),'total_questions':count} for row,response in zip(rows,matrix)}
 totals=[sum(r[j] for r in matrix) for j in range(count)]
 difficulties=[]
 for success in totals:
  p=(success+.5)/(n+1);difficulties.append(math.log((1-p)/p))
 abilities=[math.log((sum(r)+.5)/(count-sum(r)+.5)) for r in matrix]
 for _ in range(60):
  for i,response in enumerate(matrix):
   target=min(count-.5,max(.5,float(sum(response))))
   theta=abilities[i]
   for _step in range(20):
    expected=sum(_sigmoid(theta-b) for b in difficulties)
    variance=sum((_sigmoid(theta-b))*(1-_sigmoid(theta-b)) for b in difficulties)
    if variance<1e-8:break
    delta=(target-expected)/variance;theta=max(-8,min(8,theta+delta))
    if abs(delta)<1e-5:break
   abilities[i]=theta
  for j,success in enumerate(totals):
   expected=sum(_sigmoid(theta-difficulties[j]) for theta in abilities)
   variance=sum(_sigmoid(theta-difficulties[j])*(1-_sigmoid(theta-difficulties[j])) for theta in abilities)
   if variance>1e-8:difficulties[j]=max(-8,min(8,difficulties[j]+(expected-success)/variance))
  center=sum(difficulties)/len(difficulties) if difficulties else 0
  difficulties=[b-center for b in difficulties];abilities=[v-center for v in abilities]
 mean=sum(abilities)/len(abilities);variance=sum((v-mean)**2 for v in abilities)/len(abilities);sd=math.sqrt(variance)
 out={}
 for row,theta,response in zip(rows,abilities,matrix):
  value=50.0 if sd<1e-7 else max(0.0,min(100.0,50+10*((theta-mean)/sd)))
  out[str(row['attempt_id'])]={'score':round(value,2),'grade':mock_grade(value),'correct_count':sum(response),'total_questions':count}
 return out

def recalculate_mock_scores(test_id):
 values=rasch_scores(test_id)
 for attempt_id,result in values.items():
  db.update_attempt(attempt_id,score=result['score'],grade=result['grade'])
  db.archive_attempt_result(attempt_id)
 return values

async def send_mock_results_pdf(test,force=False):
 test_id=str(test['test_id']);key='mock_results_pdf_sent_'+test_id
 if not force and db.get_setting(key,''):return False
 path=''
 try:
  with tempfile.NamedTemporaryFile(prefix='nur-mock-results-',suffix='.pdf',delete=False) as tmp:path=tmp.name
  build_test_pdf(test_id,path)
  code=str(test['code'] or 'MOCK')
  await BOT.send_document(ADMIN,FSInputFile(path,filename=f"{code}-mock-natijalar.pdf"),caption=f"{test['name']} — yakuniy MOCK natijalari")
  db.set_setting(key,'1');return True
 except Exception:
  logging.getLogger('nur-oqiw.mock').exception('Mock results PDF delivery failed')
  return False
 finally:
  if path:
   try:os.remove(path)
   except OSError:pass

async def send_mock_questions_pdf(test):
 test=dict(test);test_id=str(test.get('test_id') or '');path=''
 if not test_id or not int(test.get('code_set') or 0) or not db.questions_for_test(test_id):return False
 channel=str(test.get('questions_channel') or '').strip()
 if not channel:return False
 try:
  with tempfile.NamedTemporaryFile(prefix='nur-mock-questions-',suffix='.pdf',delete=False) as tmp:path=tmp.name
  build_questions_pdf(test_id,path)
  await BOT.send_document(channel,FSInputFile(path,filename=f"{test['code']}-savollar.pdf"),caption=f"{test['name']} · MOCK test savollari")
  db.set_mock_questions_pdf_sent(test_id,1)
  return True
 except Exception:
  logging.getLogger('nur-oqiw.mock').exception('Mock questions PDF delivery failed')
  return False
 finally:
  if path:
   try:os.remove(path)
   except OSError:pass

def mock_admin_results_kb():
 url=WEBAPP.rstrip('/')+'/admin#results' if WEBAPP else 'https://nukuspro.uz/admin#results'
 return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ADMIN PANEL · NATIJALAR',web_app=WebAppInfo(url=url),style='primary')]])

async def update_mock_admin_status(test,message_key,text):
 message_id=db.get_setting(message_key,'')
 if message_id:
  try:
   await BOT.edit_message_text(text,chat_id=ADMIN,message_id=int(message_id),reply_markup=mock_admin_results_kb())
   return
  except Exception as exc:
   error=str(exc).lower()
   if 'message is not modified' in error:return
   if 'message to edit not found' not in error and 'message_id_invalid' not in error and "message can't be edited" not in error:return
 sent=await BOT.send_message(ADMIN,text,reply_markup=mock_admin_results_kb());db.set_setting(message_key,str(sent.message_id))

async def finish_mock_test(test,reason='timer'):
 test=dict(test);test_id=str(test['test_id']);lock=MOCK_FINISH_LOCKS.setdefault(test_id,asyncio.Lock())
 async with lock:
  test=dict(db.get_test(test_id) or test);questions=db.questions_for_test(test_id);closed=0
  for attempt in db.all_attempts_for_test(test_id):
   if int(attempt['submitted'] or 0) or not attempt['started_at']:continue
   state,_,_,_,_=finish_attempt_atomically(test_id,int(attempt['telegram_id']),questions,datetime.now(TZ).isoformat(),recalculate=False)
   if state=='ok':closed+=1
  db.set_test_active(test_id,0);db.set_test_published(test_id,0)
  db.close_mock_round(test_id,datetime.now(TZ).isoformat())
  recalculate_mock_scores(test_id)
  for attempt in db.all_attempts_for_test(test_id):
   if int(attempt['finish_notified'] or 0) or not db.mark_attempt_finish_notified(attempt['attempt_id']):continue
   try:await BOT.send_message(int(attempt['telegram_id']),'Test tugadi. Javoblar tez orada e’lon qilinadi.')
   except Exception:logging.getLogger('nur-oqiw.mock').info('Could not notify MOCK participant %s',attempt['telegram_id'])
  await send_mock_results_pdf(test)
  return closed

async def start_mock_test_session(test_id):
 test_id=str(test_id or '').strip();test=db.get_test(test_id)
 if not test or not int(test['is_mock'] or 0):return {'ok':False,'error':'mock_test_not_found'}
 test=dict(test)
 if test.get('timer_started_at') and not test.get('timer_ends_at'):
  test=db.reset_mock_timer(test_id) or db.get_test(test_id);test=dict(test)
 issues=mock_key_check(test_id)
 if issues:return {'ok':False,'error':'mock_test_not_ready','message':'Test tayyor emas:\n'+'\n'.join(issues[:12])}
 if test['timer_ends_at']:
  remaining=mock_remaining_seconds(dict(test))
  if int(test['active'] or 0) and remaining and remaining>0:
   return {'ok':True,'message':f"{test['name']} allaqachon boshlangan. Qolgan vaqt: {format_mock_timer(remaining)}."}
  return {'ok':False,'error':'mock_needs_retake','message':'Bu test avval boshlangan. Yangi tur uchun QAYTA O‘TKAZISH tugmasini bosing.'}
 attempts=db.all_attempts_for_test(test_id)
 if any(a['started_at'] for a in attempts):
  return {'ok':False,'error':'mock_needs_retake','message':'Bu testda oldingi urinish bor. Avval QAYTA O‘TKAZISH tugmasini bosing.'}
 duration=max(1,int(test['duration_minutes'] or 0));started=datetime.now(TZ);ends=started+timedelta(minutes=duration)
 db.set_test_active(test_id,1);db.set_test_published(test_id,0)
 test=db.start_mock_timer(test_id,started.isoformat(),ends.isoformat()) or db.get_test(test_id)
 if not test or not test['timer_ends_at']:return {'ok':False,'error':'mock_start_failed','message':'Taymerni boshlashda xatolik bo‘ldi.'}
 remaining=mock_remaining_seconds(dict(test)) or duration*60
 try:
  await update_mock_admin_status(dict(test),'mock_timer_message_'+test_id,
   f"QOLGAN VAQT: {format_mock_timer(remaining)}\nMOCK TEST BOSHLANDI\n{test['name']} · kod: {test['code']}")
 except Exception:logging.getLogger('nur-oqiw.mock').exception('Could not update started MOCK status')
 return {'ok':True,'message':f"{test['name']} boshlandi. Taymer: {format_mock_timer(remaining)}. Qatnashchilar endi test kodini kiritishi mumkin."}

async def restart_mock_test_session(test_id):
 test_id=str(test_id or '').strip();test=db.get_test(test_id)
 if not test or not int(test['is_mock'] or 0):return {'ok':False,'error':'mock_test_not_found'}
 if not int(test['code_set'] or 0) or not db.questions_for_test(test_id):return {'ok':False,'error':'mock_test_not_ready'}
 remaining=mock_remaining_seconds(dict(test))
 if int(test['active'] or 0) and remaining is not None and remaining>0:
  return {'ok':False,'error':'mock_in_progress','message':'Test hali davom etmoqda. Timer tugagach qayta o‘tkazish mumkin.'}
 unfinished=[a for a in db.all_attempts_for_test(test_id) if a['started_at'] and not int(a['submitted'] or 0)]
 if unfinished:
  await finish_mock_test(test,'admin_restart')
 attempts=db.all_attempts_for_test(test_id)
 if any(a['started_at'] and not int(a['submitted'] or 0) for a in attempts):
  return {'ok':False,'error':'mock_finalize_failed','message':'Yakunlanmagan urinishlarni yopib bo‘lmadi. Natijalar saqlangan; birozdan keyin qayta urinib ko‘ring.'}
 for attempt in attempts:
  if not int(attempt['submitted'] or 0):continue
  result=db.restart_completed_attempt(test_id,int(attempt['telegram_id']))
  if result=='restarted':
   fresh=db.get_attempt(test_id,int(attempt['telegram_id']))
   if fresh:db.update_attempt(fresh['attempt_id'],participant_name='',finish_notified=0)
  elif result=='already_active':
   continue
  elif result not in ('not_started',):
   logging.getLogger('nur-oqiw.mock').error('Could not reset MOCK attempt %s: %s',attempt['attempt_id'],result)
   return {'ok':False,'error':'mock_restart_failed','message':'Bitta urinishni arxivlashda xatolik bo‘ldi. Eski natijalar saqlangan; qayta tekshiring.'}
 reopened=db.reset_mock_timer(test_id)
 if not reopened:return {'ok':False,'error':'mock_restart_failed'}
 for suffix,value in (('mock_results_pdf_sent_'+test_id,''),('mock_results_pdf_try_'+test_id,'0'),('mock_timer_message_final_'+test_id,''),('mock_timer_updated_'+test_id,'0')):
  db.set_setting(suffix,value)
 try:
  await update_mock_admin_status(dict(reopened),'mock_timer_message_'+test_id,
   f"MOCK TEST QAYTA OCHILDI\n{reopened['name']} · kod: {reopened['code']}\nTaymer birinchi qatnashchi kirganda boshlanadi.")
 except Exception:logging.getLogger('nur-oqiw.mock').exception('Could not update restarted MOCK status')
 return {'ok':True,'message':f"{reopened['name']} qayta ochildi. Test kodi o‘zgarmadi, avvalgi natijalar arxivda saqlandi. Taymer birinchi qatnashchi kirganda boshlanadi."}

async def mock_timer_tick():
 """Expire shared MOCK timers and keep one editable Telegram status message per test."""
 if not BOT or not ADMIN:return
 now=datetime.now(TZ)
 for row in db.all_tests():
  test=dict(row)
  if not int(test.get('is_mock') or 0):continue
  if test.get('scheduled_start_at') and not test.get('timer_ends_at'):
   try:scheduled=datetime.fromisoformat(str(test['scheduled_start_at']).replace('Z','+00:00'))
   except (TypeError,ValueError):scheduled=None
   if scheduled:
    if scheduled.tzinfo is None:scheduled=scheduled.replace(tzinfo=TZ)
    if now>=scheduled.astimezone(TZ):
     result=await start_mock_test_session(str(test['test_id']))
     if not result.get('ok'):
      db.set_mock_schedule(test['test_id'],'')
      await BOT.send_message(ADMIN,f"{test['name']} belgilangan vaqtda boshlanmadi: {result.get('message') or result.get('error')}")
     continue
  if not test.get('timer_ends_at'):continue
  try:
   end=datetime.fromisoformat(str(test['timer_ends_at']).replace('Z','+00:00'))
   if end.tzinfo is None:end=end.replace(tzinfo=TZ)
   seconds_left=(end.astimezone(TZ)-now).total_seconds();remaining=max(0,int(__import__('math').ceil(seconds_left)))
  except Exception:continue
  test_id=str(test['test_id']);message_key='mock_timer_message_'+test_id;time_key='mock_timer_updated_'+test_id;final_key='mock_timer_message_final_'+test_id;pdf_key='mock_results_pdf_sent_'+test_id;pdf_try_key='mock_results_pdf_try_'+test_id
  try:
   if remaining<=0:
    fresh=db.get_test(test_id)
    if fresh and (mock_remaining_seconds(dict(fresh)) or 0)>0:continue
    last_pdf_try=float(db.get_setting(pdf_try_key,'0') or 0)
    if int(test.get('active') or 0) or (not db.get_setting(pdf_key,'') and now.timestamp()-last_pdf_try>=60):
     db.set_setting(pdf_try_key,str(now.timestamp()))
     await finish_mock_test(test,'timer')
    sent_pdf=bool(db.get_setting(pdf_key,''));state='sent' if sent_pdf else 'retry'
    if db.get_setting(final_key,'')!=state:
     detail='Natijalar PDF’i admin chatiga yuborildi.' if sent_pdf else 'Natijalar PDF’i yuborilmoqda; xatolik bo‘lsa bot qayta urinadi.'
     attempts=db.all_attempts_for_test(test_id);started=sum(1 for a in attempts if a['started_at']);completed=sum(1 for a in attempts if a['started_at'] and int(a['submitted'] or 0))
     text=f"QOLGAN VAQT: 00:00:00\nMOCK TEST YAKUNLANDI\n{test['name']} · kod: {test['code']}\nQatnashgan: {started} · Natijasi tayyor: {completed}\nVaqt tugadi. {detail}"
     await update_mock_admin_status(test,message_key,text);db.set_setting(final_key,state)
    continue
   if not int(test.get('active') or 0):
    if not db.get_setting(pdf_key,'') and now.timestamp()-float(db.get_setting(pdf_try_key,'0') or 0)>=60:
     db.set_setting(pdf_try_key,str(now.timestamp()));await finish_mock_test(test,'admin')
    sent_pdf=bool(db.get_setting(pdf_key,''));state='sent' if sent_pdf else 'retry'
    if db.get_setting(final_key,'')!=state:
     detail='Natijalar PDF’i admin chatiga yuborildi.' if sent_pdf else 'Natijalar PDF’i yuborilmoqda; xatolik bo‘lsa bot qayta urinadi.'
     attempts=db.all_attempts_for_test(test_id);started=sum(1 for a in attempts if a['started_at']);completed=sum(1 for a in attempts if a['started_at'] and int(a['submitted'] or 0))
     text=f"QOLGAN VAQT: 00:00:00\nMOCK TEST TO‘XTATILDI\n{test['name']} · kod: {test['code']}\nQatnashgan: {started} · Natijasi tayyor: {completed}\n{detail}"
     await update_mock_admin_status(test,message_key,text);db.set_setting(final_key,state)
    continue
   last=float(db.get_setting(time_key,'0') or 0)
   if now.timestamp()-last<0.95:continue
   text=f"QOLGAN VAQT: {format_mock_timer(remaining)}\nMOCK TEST · {test['name']}\nKod: {test['code']}"
   message_id=db.get_setting(message_key,'')
   if message_id:
    try:await BOT.edit_message_text(text,chat_id=ADMIN,message_id=int(message_id),reply_markup=mock_admin_results_kb())
    except Exception as exc:
     error=str(exc).lower()
     if 'message is not modified' in error:pass
     elif 'message to edit not found' in error or 'message_id_invalid' in error or "message can't be edited" in error:
      sent=await BOT.send_message(ADMIN,text,reply_markup=mock_admin_results_kb());db.set_setting(message_key,str(sent.message_id))
     else:continue
   else:
    sent=await BOT.send_message(ADMIN,text,reply_markup=mock_admin_results_kb());db.set_setting(message_key,str(sent.message_id))
   db.set_setting(time_key,str(now.timestamp()))
  except Exception:logging.getLogger('nur-oqiw.mock').exception('Could not update MOCK timer status')

def format_mock_timer(value):
 seconds=max(0,int(value));return f"{seconds//3600:02d}:{(seconds%3600)//60:02d}:{seconds%60:02d}"

def mock_remaining_seconds(test,now=None):
 try:
  if not test or not test.get('timer_ends_at'):return None
  end=datetime.fromisoformat(str(test['timer_ends_at']).replace('Z','+00:00'))
  if end.tzinfo is None:end=end.replace(tzinfo=TZ)
  current=now or datetime.now(TZ)
  return max(0,int(__import__('math').ceil((end.astimezone(TZ)-current).total_seconds())))
 except Exception:return None

def build_test_pdf(tid,path,selected_rows=None,round_label=''):
 t=db.get_test(tid)
 if not t:raise ValueError('Test topilmadi')
 styles=getSampleStyleSheet();title_style=ParagraphStyle('NurMockTitle',parent=styles['Title'],fontName=PDF_FONT,fontSize=14,leading=17,alignment=1,textColor=colors.HexColor('#123d29'),spaceAfter=3)
 small=ParagraphStyle('NurMockSub',parent=styles['Normal'],fontName=PDF_FONT,fontSize=8,leading=10,alignment=1,textColor=colors.HexColor('#486555'))
 body=ParagraphStyle('NurMockBody',parent=styles['BodyText'],fontName=PDF_FONT,fontSize=7.3,leading=8.5,wordWrap='CJK',textColor=colors.black)
 header=ParagraphStyle('NurMockHead',parent=body,fontSize=7.3,leading=8.5,alignment=1)
 qs=db.questions_for_test(tid);rows_by_id={}
 if selected_rows is not None:
  for selected in selected_rows:
   row=dict(selected)
   if int(row.get('submitted') or 0):rows_by_id[str(row.get('attempt_id') or '')]=row
 else:
  if hasattr(db,'permanent_results_for_test'):
   for archived in db.permanent_results_for_test(tid,5000):
    row=dict(archived)
    if int(row.get('submitted') or 0):row['full_name']=row.get('full_name') or '';rows_by_id[str(row.get('attempt_id') or '')]=row
  for current in db.all_attempts_for_test(tid):
   if not int(current['submitted'] or 0):continue
   row=dict(current);rows_by_id[str(row.get('attempt_id') or '')]=row
 rows_all=list(rows_by_id.values())
 rows_all.sort(key=lambda a:(-float(a['score'] or 0),str(a.get('full_name') or '').casefold()))
 headings=['№','To‘g‘ri','Ball','Baho','Ism-familiya']
 rows=[[Paragraph('<b>'+escape(x)+'</b>',header) for x in headings]];row_colors=[]
 for rank,a in enumerate(rows_all,1):
  try:answers=json.loads(a['answers_json'] or '{}')
  except Exception:answers={}
  correct=sum(1 for q in qs if norm(answers.get(str(q['number']),' '))==norm(q['answer']))
  s=float(a['score'] or 0);g=str(a['grade'] or mock_grade(s) if int(t['is_mock'] or 0) else a['grade'] or grade(s))
  color='#63F83C' if g in ('A+','A') else '#00AF50' if g in ('B+','B') else '#FFF000' if g in ('C+','C') else '#F4B183' if g=='NC' else '#DCE9F2'
  row_colors.append(colors.HexColor(color))
  name=escape(str(a['full_name'] or 'Ismsiz'))
  rows.append([str(rank),str(correct),f"{s:.2f}".replace('.',','),escape(g),Paragraph(name,body)])
 doc=SimpleDocTemplate(path,pagesize=A4,rightMargin=12,leftMargin=12,topMargin=14,bottomMargin=20)
 tab=Table(rows,repeatRows=1,colWidths=[36,70,55,47,363],hAlign='LEFT')
 style=[('FONTNAME',(0,0),(-1,-1),PDF_FONT),('GRID',(0,0),(-1,-1),.45,colors.black),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8efe9')),('FONTSIZE',(0,0),(-1,-1),7.3),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(0,0),(3,-1),'CENTER'),('ALIGN',(4,0),(4,-1),'LEFT'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),2.3),('BOTTOMPADDING',(0,0),(-1,-1),2.3)]
 for row_no,color in enumerate(row_colors,1):style.append(('BACKGROUND',(0,row_no),(-1,row_no),color))
 tab.setStyle(TableStyle(style))
 title=Paragraph(escape(f"NUR O‘QIW ORAYI · {t['name']}"),title_style)
 subtitle_label='MOCK natijalari' if int(t['is_mock'] or 0) else 'Test natijalari'
 subtitle=Paragraph(escape(f"{subtitle_label}"+(f" · {round_label}" if round_label else "")+f" · Savollar: {len(qs)} · Natijalar: {len(rows_all)}"+(f" · Kod: {t['code']}" if int(t['code_set'] or 0) else "")),small)
 def draw_footer(canvas,document):
  canvas.saveState()
  canvas.setFont(PDF_FONT,7)
  canvas.setFillColor(colors.HexColor('#43594D'))
  canvas.drawRightString(A4[0]-12,7,'by Жанзаков')
  canvas.restoreState()
 doc.build([title,subtitle,Spacer(1,7),tab],onFirstPage=draw_footer,onLaterPages=draw_footer)



def mock_participant_rows(test_id):
 rows={}
 for a in db.permanent_results_for_test(test_id,5000):
  if a['started_at'] or int(a['submitted'] or 0):rows[str(a['attempt_id'])]=dict(a)
 for a in db.all_attempts_for_test(test_id):
  if a['started_at'] or int(a['submitted'] or 0):rows[str(a['attempt_id'])]=dict(a)
 return sorted(rows.values(),key=lambda a:str(a.get('started_at') or a.get('finished_at') or ''),reverse=True)

def mock_personal_row(telegram_id,test_id=None):
 if test_id:
  candidates=[a for a in mock_participant_rows(test_id) if int(a['telegram_id'])==int(telegram_id) and int(a['submitted'] or 0)]
 else:
  candidates=[]
  for t in db.all_tests():
   if int(t['is_mock'] or 0):
    candidates.extend(a for a in mock_participant_rows(t['test_id']) if int(a['telegram_id'])==int(telegram_id) and int(a['submitted'] or 0))
 candidates.sort(key=lambda a:str(a.get('finished_at') or ''),reverse=True)
 for row in candidates:
  t=db.get_test(row['test_id'])
  if t and (not int(t['active'] or 0) or mock_clock_expired(t)):return t,row
 return None,None

def build_mock_personal_pdf(test,row,path):
 qs=db.questions_for_test(test['test_id'])
 try:answers=json.loads(row.get('answers_json') or '{}')
 except (ValueError,TypeError):answers={}
 correct=sum(1 for q in qs if norm(answers.get(str(q['number'])))==norm(q['answer']))
 name=str(row.get('full_name') or row.get('participant_name') or 'Ismsiz')
 styles=getSampleStyleSheet()
 title_style=ParagraphStyle('MockPersonalTitle',parent=styles['Title'],fontName=PDF_FONT,fontSize=16,leading=20,textColor=colors.HexColor('#123d29'),alignment=1)
 body=ParagraphStyle('MockPersonalBody',parent=styles['Normal'],fontName=PDF_FONT,fontSize=10,leading=15)
 doc=SimpleDocTemplate(path,pagesize=A4,leftMargin=38,rightMargin=38,topMargin=35,bottomMargin=32)
 info=[['Ism familiya',name],['Test',str(test['name'])],['Test kodi',str(test['code'])],['To‘g‘ri javoblar',f'{correct}/{len(qs)}'],['Rasch balli',f"{float(row.get('score') or 0):.2f}"],['Baho',str(row.get('grade') or '—')],['Yakunlangan',str(row.get('finished_at') or '—')]]
 table=Table([[Paragraph(escape(str(a)),body),Paragraph(escape(str(b)),body)] for a,b in info],colWidths=[150,350],hAlign='LEFT')
 table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.3,colors.HexColor('#b4cbbd')),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#e8efe9')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
 details=[f"{q['number']}-savol: {'To‘g‘ri' if norm(answers.get(str(q['number'])))==norm(q['answer']) else 'Xato' if str(answers.get(str(q['number'])) or '').strip() else 'Bo‘sh'}" for q in qs]
 story=[Paragraph('NUR O‘QIW ORAYI · MOCK NATIJA',title_style),Spacer(1,18),table,Spacer(1,18),Paragraph('Savollar bo‘yicha',body)]
 story.extend(Paragraph(escape(line),body) for line in details)
 def footer(canvas,document):
  canvas.setFont(PDF_FONT,7);canvas.setFillColor(colors.HexColor('#43594D'));canvas.drawRightString(A4[0]-20,12,'by Жанзаков')
 doc.build(story,onFirstPage=footer,onLaterPages=footer)

async def send_mock_personal_result(chat_id,telegram_id,test_id=None):
 test,row=mock_personal_row(telegram_id,test_id)
 if not test:return await BOT.send_message(chat_id,'Yakunlangan MOCK test natijangiz hali yo‘q.')
 path=''
 try:
  with tempfile.NamedTemporaryFile(prefix='nur-mock-personal-',suffix='.pdf',delete=False) as tmp:path=tmp.name
  build_mock_personal_pdf(test,row,path)
  await BOT.send_document(chat_id,FSInputFile(path,filename='mock-shaxsiy-natija.pdf'),caption=f"{test['name']} · shaxsiy natija")
 except Exception:
  logging.getLogger('nur-oqiw.mock').exception('Personal MOCK result failed')
  await BOT.send_message(chat_id,'Shaxsiy natija faylini tayyorlab bo‘lmadi. Keyinroq qayta urinib ko‘ring.')
 finally:
  if path:
   try:os.remove(path)
   except OSError:pass

def build_mock_round_xlsx(tid,label,rows,path):
 t=db.get_test(tid);qs=db.questions_for_test(tid)
 if not t:raise ValueError('MOCK test topilmadi')
 headers=['№','Ism familiya','To‘g‘ri','Savollar','Ball','Baho','Yakunlangan vaqt']
 data=[headers]
 for rank,a in enumerate(rows,1):
  try:answers=json.loads(a.get('answers_json') or '{}')
  except (ValueError,TypeError):answers={}
  correct=sum(norm(answers.get(str(q['number'])))==norm(q['answer']) for q in qs)
  data.append([rank,str(a.get('full_name') or 'Ismsiz'),correct,len(qs),round(float(a.get('score') or 0),2),str(a.get('grade') or mock_grade(a.get('score') or 0)),str(a.get('finished_at') or '')])
 def cell(col,value,row):
  ref=chr(65+col)+str(row)
  if isinstance(value,(int,float)):
   return f'<c r="{ref}"><v>{value}</v></c>'
  return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
 sheet='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"/></sheetViews><cols><col min="1" max="1" width="7" customWidth="1"/><col min="2" max="2" width="34" customWidth="1"/><col min="3" max="6" width="13" customWidth="1"/><col min="7" max="7" width="28" customWidth="1"/></cols><sheetData>'+''.join('<row r="'+str(n)+'">'+''.join(cell(i,v,n) for i,v in enumerate(row))+'</row>' for n,row in enumerate(data,1))+'</sheetData></worksheet>'
 parts={
  '[Content_Types].xml':'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
  '_rels/.rels':'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
  'xl/workbook.xml':'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="MOCK natijalar" sheetId="1" r:id="rId1"/></sheets></workbook>',
  'xl/_rels/workbook.xml.rels':'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
  'xl/worksheets/sheet1.xml':sheet
 }
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
  for name,value in parts.items():archive.writestr(name,value)

def mock_round_analysis(tid,rows):
 questions=db.questions_for_test(tid);total=len(rows);lines=[f'SAVOLLAR TAHLILI · {total} qatnashchi']
 for q in questions:
  key=str(q['number']);correct=wrong=blank=0;choices={v:0 for v in 'ABCD'}
  for a in rows:
   try:answers=json.loads(a.get('answers_json') or '{}')
   except (ValueError,TypeError):answers={}
   answer=str(answers.get(key) or '').strip()
   if not answer:blank+=1
   elif norm(answer)==norm(q['answer']):correct+=1
   else:wrong+=1
   if answer.upper() in choices:choices[answer.upper()]+=1
  percent=round(correct*100/total) if total else 0
  detail=' · '.join(f'{v}:{n}' for v,n in choices.items()) if str(q['kind'])=='choice' else 'Yozma'
  lines.append(f"{key}-savol · To‘g‘ri {correct} ({percent}%) · Xato {wrong} · Bo‘sh {blank}\n{detail}")
 return lines

def build_questions_pdf(tid,path):
 t=db.get_test(tid)
 if not t:raise ValueError('Test topilmadi')
 styles=getSampleStyleSheet();title=ParagraphStyle('NurQuestionTitle',parent=styles['Title'],fontName=PDF_FONT,fontSize=15,leading=18,textColor=colors.HexColor('#123d29'))
 body=ParagraphStyle('NurQuestionBody',parent=styles['BodyText'],fontName=PDF_FONT,fontSize=10,leading=14,spaceAfter=3)
 story=[Paragraph(escape(str(t['name'])),title),Paragraph(escape(f"MOCK test · {t['code'] if int(t['code_set'] or 0) else 'kod belgilanmagan'} · {int(t['duration_minutes'] or 0)} daqiqa"),body),Spacer(1,8)]
 for q in db.questions_for_test(tid):
  try:options=json.loads(q['options_json'] or '[]')
  except Exception:options=[]
  label=escape(str(q['group_id'] or q['number']))
  story.append(Paragraph(f"<b>{label}. {escape(str(q['question'] or 'Savol'))}</b>",body))
  if q['image_url']:story.append(Paragraph(escape(str(q['image_url'])),body))
  if q['kind']=='choice' and options:story.append(Paragraph('   '.join(f"{chr(65+i)}. {escape(str(value))}" for i,value in enumerate(options)),body))
  story.append(Spacer(1,7))
 doc=SimpleDocTemplate(path,pagesize=A4,rightMargin=36,leftMargin=36,topMargin=32,bottomMargin=32)
 doc.build(story)

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


def finish_attempt_atomically(test_id, telegram_id, questions, finished_at, recalculate=True):
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
  test=db.get_test(test_id)
  score_value=(50.0 if test and int(test['is_mock'] or 0) else round(correct/total*100,2) if total else 0)
  grade_value=mock_grade(score_value) if test and int(test['is_mock'] or 0) else grade(score_value)
  c.execute("UPDATE test_attempts SET score=?,grade=?,submitted=1,status='submitted',finished_at=? WHERE attempt_id=? AND submitted=0",(score_value,grade_value,finished_at,a["attempt_id"]))
 db.archive_attempt_result(a["attempt_id"])
 test=db.get_test(test_id)
 if test and int(test['is_mock'] or 0) and recalculate:
  recalculate_mock_scores(test_id)
  updated=db.get_attempt(test_id,telegram_id)
  if updated:score_value=float(updated['score'] or 0);grade_value=str(updated['grade'] or '')
 return ("ok",score_value,grade_value,correct,total)

def register(core,dp,bot,webapp_url):
 global CORE,ADMIN,BOT,TZ,WEBAPP
 CORE,ADMIN,BOT,TZ,WEBAPP=core,core.ADMIN,bot,core.TZ,webapp_url;r=Router(name='test_v3')
 saved_profile_metadata={}
 async def group_admin_page():
  groups=CORE.known_groups()
  lines=['<b>BOT QO‘SHILGAN GURUHLAR</b>','',
    'Guruhlar soni: <b>'+str(len(groups))+'</b>',
    'Bot guruhga qo‘shilganda avtomatik qayd etiladi.',
    'Chiqish uchun pastdagi tugmani bosing. Tasdiqsiz bot chiqmaydi.','']
  active=[]
  async def inspect(group):
   gid=int(group['id'])
   try:
    member=await asyncio.wait_for(BOT.get_chat_member(gid,BOT.id),timeout=5)
    status=str(member.status)
    if status in ('left','kicked'):return (group,'left')
    return (group,status)
   except Exception:return (group,'unknown')
  checks=await asyncio.gather(*(inspect(g) for g in groups[:30]))
  for idx,(g,status) in enumerate(checks,1):
   title=html_escape(str(g.get('title') or g['id']))
   if status=='left':continue
   active.append(g)
   label='tekshirib bo‘lmadi' if status=='unknown' else 'faol ('+status+')'
   lines.append(f"{idx}. <b>{title}</b>\n   ID: <code>{g['id']}</code>\n   Holat: {label}")
  if not active:lines.append('Hozircha faol guruh qayd etilmagan. Guruhga botni qo‘shing.')
  if len(groups)>30:lines.append('30 ta guruh ko‘rsatildi.')
  return '\n\n'.join(lines)[:3900],group_admin_keyboard(active)

 @r.callback_query(F.data=='group_refresh')
 async def group_refresh(q:CallbackQuery):
  if q.from_user.id!=ADMIN or q.message.chat.type!='private':
   return await q.answer('Bu bo‘lim faqat admin uchun.',show_alert=True)
  text,kb=await group_admin_page()
  await q.message.edit_text(text,parse_mode='HTML',reply_markup=kb)
  await q.answer('Yangilandi')

 @r.callback_query(F.data=='group_compose')
 async def group_compose(q:CallbackQuery):
  if q.from_user.id!=ADMIN or q.message.chat.type!='private':
   return await q.answer('Bu bo‘lim faqat admin uchun.',show_alert=True)
  if not CORE.known_groups():
   return await q.answer('Bot qo‘shilgan guruhlar ro‘yxati bo‘sh.',show_alert=True)
  ast('broadcast_message')
  await q.message.answer(
   '<b>GURUHLARGA XABAR YUBORISH</b>\n\n'
   'Xabar matnini yozing. Yuborishdan oldin alohida tasdiqlash tugmasi chiqadi.',
   parse_mode='HTML')
  await q.answer()

 @r.callback_query(F.data.startswith('group_leave:'))
 async def group_leave_prepare(q:CallbackQuery):
  if q.from_user.id!=ADMIN or q.message.chat.type!='private':
   return await q.answer('Faqat admin foydalanadi.',show_alert=True)
  try:gid=int(q.data.split(':',1)[1])
  except (TypeError,ValueError):return await q.answer('Guruh ID noto‘g‘ri.',show_alert=True)
  group=next((g for g in CORE.known_groups() if int(g['id'])==gid),None)
  if not group:return await q.answer('Bu guruh ro‘yxatda yo‘q.',show_alert=True)
  buttons=InlineKeyboardMarkup(inline_keyboard=[
   [InlineKeyboardButton(text='HA, BOT GURUHDAN CHIQSIN',
      callback_data='group_confirm_leave:'+str(gid),style='danger')],
   [InlineKeyboardButton(text='BEKOR QILISH',callback_data='group_refresh')]])
  await q.message.edit_text(
   '<b>GURUHDAN CHIQISHNI TASDIQLANG</b>\n\n'
   '<b>'+html_escape(group['title'])+'</b>\n'
   'ID: <code>'+str(gid)+'</code>\n\n'
   'Bot bu guruhdan chiqadi va guruhga xabar yuborish to‘xtaydi. '
   'Qayta ishlatish uchun botni guruhga yana qo‘shish kerak.',
   parse_mode='HTML',reply_markup=buttons)
  await q.answer()

 @r.callback_query(F.data.startswith('group_confirm_leave:'))
 async def group_leave_execute(q:CallbackQuery):
  if q.from_user.id!=ADMIN or q.message.chat.type!='private':
   return await q.answer('Faqat admin foydalanadi.',show_alert=True)
  try:gid=int(q.data.split(':',1)[1])
  except (TypeError,ValueError):return await q.answer('Guruh ID noto‘g‘ri.',show_alert=True)
  group=next((g for g in CORE.known_groups() if int(g['id'])==gid),None)
  if not group:return await q.answer('Guruh ro‘yxatdan allaqachon o‘chgan.',show_alert=True)
  try:
   result=await BOT.leave_chat(gid)
   if result is not True:return await q.answer('Telegram chiqishni tasdiqlamadi.',show_alert=True)
  except Exception as exc:
   logging.getLogger('nur-oqiw.group').warning('Could not leave group %s: %s',gid,type(exc).__name__)
   return await q.answer('Guruhdan chiqib bo‘lmadi. Bot huquqini tekshiring.',show_alert=True)
  remaining=[g for g in CORE.known_groups() if int(g['id'])!=gid]
  db.set_setting('known_groups',json.dumps(remaining,ensure_ascii=False))
  text,kb=await group_admin_page()
  await q.message.edit_text('Bot guruhdan chiqdi: <b>'+html_escape(group['title'])+'</b>\n\n'+text,
     parse_mode='HTML',reply_markup=kb)
  await q.answer('Guruh tark etildi')

 async def auth(req):
  raw=req.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or req.query_params.get('initData','');tid=CORE.telegram_user(raw)
  if tid and raw:
   try:
    from urllib.parse import parse_qsl
    profile=json.loads(dict(parse_qsl(raw,keep_blank_values=True)).get('user','{}'))
    username=str(profile.get('username') or '').lstrip('@').lower()
    photo=str(profile.get('photo_url') or '')
    key=(username,photo)
    if (username or photo) and saved_profile_metadata.get(tid)!=key:
     if photo:db.update_user(tid,telegram_photo=photo)
     if username:db.set_setting('telegram_username_'+str(tid),username)
     if len(saved_profile_metadata)>2000:saved_profile_metadata.clear()
     saved_profile_metadata[tid]=key
   except Exception:pass
  return tid,db.get_user(tid) if tid else None
 @core.app.get('/api/admin/menus')
 async def admin_menus(req:Request):
  tid,u=await auth(req)
  if tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  return {'ok':True,'menus':{role:menu_config.items(db,role) for role in menu_config.DEFAULTS}}

 @core.app.post('/api/admin/menus')
 async def admin_menus_update(p:dict,req:Request):
  tid,u=await auth(req)
  if tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  role=str(p.get('role',''))
  name=str(p.get('key',''))
  if role not in menu_config.DEFAULTS:return {'ok':False,'error':'invalid_role'}
  entries=menu_config.items(db,role)
  current=next((x for x in entries if x['key']==name),None)
  if not current:return {'ok':False,'error':'button_not_found'}
  action=p.get('action','save')
  stored=menu_config.load(db)
  settings=stored.setdefault(role,{})
  if action=='reset':
   settings.pop(name,None)
  elif action=='move':
   distance=int(p.get('direction',0))
   if distance not in (-1,1):return {'ok':False,'error':'invalid_direction'}
   index=entries.index(current);target=index+distance
   if target<0 or target>=len(entries):return {'ok':False,'error':'out_of_range'}
   for i,item in enumerate(entries):settings.setdefault(item['key'],{})['order']=i
   settings[name]['order']=target
   settings[entries[target]['key']]['order']=index
  elif action=='save':
   label=str(p.get('label',current['label'])).strip()
   color=str(p.get('style',current['style']))
   emoji=str(p.get('emoji_id',current['emoji_id'])).strip()
   visible=bool(p.get('visible',current['visible']))
   if not 1<=len(label)<=55 or '\n' in label or label.startswith('/'):return {'ok':False,'error':'invalid_label'}
   if color not in menu_config.COLORS:return {'ok':False,'error':'invalid_style'}
   if emoji and (not emoji.isdecimal() or len(emoji)>30):return {'ok':False,'error':'invalid_emoji_id'}
   if label in ('Admin paneliga o‘tish','Telegram ismim bilan davom etish'):return {'ok':False,'error':'reserved_label'}
   if any(x['label']==label and (other!=role or x['key']!=name) for other in menu_config.DEFAULTS for x in menu_config.items(db,other)):
    return {'ok':False,'error':'duplicate_label'}
   if name in ('Menyu sozlamalari','Aktiv testlar','MOCK menyu sozlamalari','Orqaga qaytish'):visible=True
   settings.setdefault(name,{}).update({'label':label,'style':color,'emoji_id':emoji,'visible':visible})
  else:return {'ok':False,'error':'invalid_action'}
  menu_config.save(db,stored)
  return {'ok':True,'menus':{r:menu_config.items(db,r) for r in menu_config.DEFAULTS}}
 async def mock_subscription(tid,test):
  channel=str(test['required_channel'] or '').strip()
  if not channel:return True,None
  key=(int(tid),channel);now=asyncio.get_running_loop().time();cached=MOCK_SUB_CACHE.get(key)
  if cached and cached[1] and now-cached[0]<30:return True,None
  try:
   member=await asyncio.wait_for(bot.get_chat_member(channel,int(tid)),timeout=5)
   joined=member.status in ('member','administrator','creator') or (member.status=='restricted' and bool(getattr(member,'is_member',False)))
   MOCK_SUB_CACHE[key]=(now,joined)
   if joined:return True,None
  except Exception:
   logging.getLogger('nur-oqiw.mock').warning('Mock subscription check failed for channel %s',channel)
  link=str(test['required_channel_link'] or '').strip()
  if not link and channel.startswith('@'):link='https://t.me/'+channel[1:]
  if not link and channel.startswith('-100'):link='https://t.me/c/'+channel[4:]
  return False,link or None
 async def notify_mock_finished(telegram_id,test,attempt):
  if not attempt or int(attempt['finish_notified'] or 0):return
  if not db.mark_attempt_finish_notified(attempt['attempt_id']):return
  text='Test tugadi. Javoblar tez orada e’lon qilinadi.'
  try:await bot.send_message(int(telegram_id),text)
  except Exception:logging.getLogger('nur-oqiw.mock').info('Could not notify mock participant %s',telegram_id)
 @core.app.get('/api/test/profile')
 async def profile_api(req:Request):
  tid,u=await auth(req)
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  rows=db.test_history_for_user(tid,tid,ADMIN)
  history=[{'test_id':x['test_id'],'test_name':x['test_name'] or 'Test','code':x['code'] or '', 'started_at':x['started_at'],'finished_at':x['finished_at'],'score':float(x['score'] or 0),'grade':x['grade'] or '', 'submitted':bool(x['submitted'])} for x in rows]
  return {'ok':True,'full_name':u['full_name'] or '','photo_url':u['telegram_photo'] or '','tier':u['tier'] or 'default','tests':history}
 @core.app.get('/api/test/public-profile')
 async def public_profile_api(req:Request):
  tid,u=await auth(req)
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  try:target=int(req.query_params.get('telegram_id','0'))
  except Exception:target=0
  if target<=0:return {'ok':False,'error':'invalid_target'}
  target_user=db.get_user(target)
  if not target_user:return {'ok':False,'error':'user_not_found'}
  rows=db.test_history_for_user(target,tid,ADMIN,only_submitted=True)
  history=[{'test_id':x['test_id'],'test_name':x['test_name'] or 'Test','code':x['code'] or '', 'started_at':x['started_at'],'finished_at':x['finished_at'],'score':float(x['score'] or 0),'grade':x['grade'] or '', 'submitted':bool(x['submitted'])} for x in rows]
  return {'ok':True,'telegram_id':target,'username':db.get_setting('telegram_username_'+str(target),'') or '', 'full_name':target_user['full_name'] or 'Foydalanuvchi','photo_url':target_user['telegram_photo'] or '', 'tests':history}
 @core.app.get('/api/test/ranking')
 async def ranking_api(req:Request):
  tid,u=await auth(req);code=req.query_params.get('code','').strip()
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  t=db.get_test_by_code_or_name(code) if code else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not t or not db.can_access_test(t['test_id'],tid,ADMIN):return {'ok':False,'error':'test_not_found'}
  rows=db.completed_ranking_for_test(t['test_id'])
  rows.sort(key=lambda x:(-float(x['score'] or 0),str(x['finished_at'] or '9999')))
  # Apply only positions explicitly overridden by an admin. All other places remain score-sorted automatically.
  for rank_no in range(1,16):
   raw_id=db.get_setting('admin_rank_'+str(t['test_id'])+'_'+str(rank_no),'')
   if not raw_id and rank_no==1:raw_id=db.get_setting('admin_top1_'+str(t['test_id']),'')
   try:manual_id=int(raw_id or 0)
   except Exception:manual_id=0
   if manual_id:
    chosen=next((x for x in rows if int(x['telegram_id'])==manual_id),None)
    if chosen:
     rows=[x for x in rows if int(x['telegram_id'])!=manual_id]
     rows.insert(min(rank_no-1,len(rows)),chosen)
  top=[{'rank':i+1,'telegram_id':int(x['telegram_id']),'username':db.get_setting('telegram_username_'+str(x['telegram_id']),'') or '', 'full_name':x['full_name'] or 'Ismsiz','photo_url':x['telegram_photo'] or '', 'score':float(x['score'] or 0),'grade':x['grade'] or '', 'finished_at':x['finished_at']} for i,x in enumerate(rows[:15])]
  my_rank=next((i+1 for i,x in enumerate(rows) if int(x['telegram_id'])==int(tid)),None)
  return {'ok':True,'test_name':t['name'],'code':t['code'],'total':len(rows),'my_rank':my_rank,'ranking':top}

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
 @core.app.get('/api/admin/diagnostics')
 async def admin_diagnostics(req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  try:
   tests=db.all_tests();questions=sum(len(db.questions_for_test(t['test_id'])) for t in tests)
   storage='PostgreSQL' if db.USE_POSTGRES else 'SQLite (Render restartida ma’lumot yo‘qolishi mumkin)'
   return {'ok':True,'service':'online','storage':storage,'tests':len(tests),'questions':questions,'openai_key_configured':bool(os.getenv('OPENAI_API_KEY','').strip()),'render_key_configured':bool(os.getenv('RENDER_API_KEY','').strip()),'telegram_token_configured':bool(os.getenv('BOT_TOKEN','').strip()),'admin_authorized':True}
  except Exception:
   logging.getLogger('nur-oqiw.admin').exception('Admin diagnostics failed')
   return {'ok':False,'error':'diagnostics_failed'}
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
  system='Your name and identity are Jarvis. Never introduce yourself as ChatGPT, OpenAI, or another assistant/model; if asked your name, answer only that you are Jarvis, the admin assistant for Nur oqıw orayı. You are a capable assistant for the admin of Nur oqıw orayı Milliy sertifikat test system. Understand informal Uzbek Latin, Qaraqalpaq Latin, spelling mistakes, missing letters, phonetic typing, mixed languages, and context just as a helpful human assistant would. Infer intended meaning cautiously; if the test or setting is ambiguous, ask a short clarification. Reply in polished, formal, concise Uzbek Latin or Qaraqalpaq Latin matching the user’s language. Address the administrator respectfully. Use plain text without decorative emojis, do not use RGB/neon styling, and never claim an operation succeeded before its confirmation endpoint returns success. Format replies with clear short paragraphs and numbered steps when useful. Never output Markdown tables. Use LIVE SNAPSHOT for actual current statistics. You must output ONLY a valid JSON object with keys reply (string) and action (object or null). Allowed actions: {"type":"test_toggle","code":"EXACT_TEST_CODE","active":true_or_false}; {"type":"test_delete","code":"EXACT_TEST_CODE"}; {"type":"test_create","name":"TEST_NAME","code":"NEW_CODE"}; {"type":"test_pdf","code":"EXACT_TEST_CODE"}; {"type":"question_add","code":"EXACT_TEST_CODE","number":1,"question":"QUESTION_TEXT","kind":"choice|written","answer":"A|B|C|D or written answer","options":["choice A text","choice B text","choice C text","choice D text"]}; {"type":"subscription_required","enabled":true_or_false}; {"type":"awake_window","start":"HH:MM","end":"HH:MM"}. For creating a test, ask for a name and code if missing. Never delete unless the admin explicitly asks; results are archived, but the test itself is removed. Only use exact existing codes for deletion. Never invent test codes; match code/name from LIVE SNAPSHOT and if uncertain ask which test. For changes, propose the action but never claim it is done; admin must confirm via a separate button. If request is outside the supported action list, explain what you can do or give steps through existing admin controls and set action null. Never expose secrets or ask for API keys. LIVE SNAPSHOT: '+json.dumps({'stats':safe_stats,'tests':safe_tests},ensure_ascii=False)
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
   # Let the model interpret misspellings, but validate every requested action on the server.
   try:
    parsed=json.loads(answer)
    if not isinstance(parsed,dict):raise ValueError('not an object')
    reply=str(parsed.get('reply','')).strip()[:5000]
    proposed=parsed.get('action')
   except Exception:
    # Recover JSON even if the model wrapped it in a code fence or added surrounding text.
    try:
     match=re.search(r'\{[\s\S]*\}',answer)
     if not match: raise ValueError('JSON not found')
     parsed=json.loads(match.group(0))
     if not isinstance(parsed,dict): raise ValueError('not an object')
     reply=str(parsed.get('reply','')).strip()[:5000]
     proposed=parsed.get('action')
    except Exception:
     logging.getLogger('nur-oqiw.jarvis').warning('Jarvis returned malformed structured output')
     return {'ok':True,'reply':'⚠️ Javob formati to‘liq o‘qilmadi. Iltimos, savolingizni qisqaroq va aniqroq yozing.','action':None}
   safe_action=None
   if isinstance(proposed,dict):
    kind=proposed.get('type')
    if kind=='test_toggle':
     code=str(proposed.get('code','')).strip()[:40]
     desired=proposed.get('active')
     test=db.get_test_by_code(code) if code else None
     if test and isinstance(desired,bool):
      if bool(int(test['active']))==desired:
       reply=(reply+'\n\nBu test hozirning o‘zida '+('ochiq.' if desired else 'yopiq.')).strip()
      else:
       safe_action={'type':'test_toggle','test_id':str(test['test_id']),'code':str(test['code']),'name':str(test['name']),'active':desired}
    elif kind=='test_delete':
     code=str(proposed.get('code','')).strip()[:40]
     test=db.get_test_by_code(code) if code else None
     if test:
      safe_action={'type':'test_delete','test_id':str(test['test_id']),'code':str(test['code']),'name':str(test['name'])}
     else: reply='O‘chirish uchun aniq test kodi topilmadi. Test kodini yuboring.'
    elif kind=='test_create':
     name=str(proposed.get('name','')).strip()[:120]
     code=str(proposed.get('code','')).strip()[:40]
     if name and re.fullmatch(r'[A-Za-z0-9_-]{3,40}',code):
      if db.test_code_exists(code): reply='Bu test kodi band. Boshqa kod tanlang.'
      else: safe_action={'type':'test_create','name':name,'code':code}
     else: reply='Yangi test uchun nom va 3–40 belgili lotin harf/raqamli kod kerak.'
    elif kind=='test_pdf':
     code=str(proposed.get('code','')).strip()[:40];test=db.get_test_by_code(code) if code else None
     if test:safe_action={'type':'test_pdf','test_id':str(test['test_id']),'code':str(test['code']),'name':str(test['name'])}
     else:reply='PDF tayyorlash uchun aniq test kodi topilmadi.'
    elif kind=='question_add':
     code=str(proposed.get('code','')).strip()[:40];test=db.get_test_by_code(code) if code else None
     try:
      number=int(proposed.get('number',0));question=str(proposed.get('question','')).strip()[:2000];qkind=str(proposed.get('kind','choice')).lower();answer=str(proposed.get('answer','')).strip();options=proposed.get('options',[])
      if not test or not (1<=number<=1000) or not question:raise ValueError()
      if qkind=='choice':
       if not isinstance(options,list) or len(options)!=4 or any(not str(x).strip() for x in options) or answer.upper() not in ('A','B','C','D'):raise ValueError()
       options=[str(x).strip()[:500] for x in options];answer=answer.upper()
      elif qkind=='written':
       if not answer:raise ValueError()
       options=[]
      else:raise ValueError()
      safe_action={'type':'question_add','test_id':str(test['test_id']),'code':str(test['code']),'name':str(test['name']),'number':number,'question':question,'kind':qkind,'answer':answer,'options':options,'replaces_existing':bool(db.get_question_for_test(test['test_id'],number))}
     except Exception:reply='Savolni qo‘shish uchun test kodi, savol raqami, matn va to‘g‘ri javob kerak. Oddiy savolda A/B/C/D matnlari ham bo‘lishi shart.'
    elif kind=='subscription_required' and isinstance(proposed.get('enabled'),bool):
     enabled=proposed['enabled'];channels=db.get_setting('subscription_channels','')
     if enabled and (not channels or channels in ('[]','{}')):
      reply=(reply+'\n\nAvval majburiy obuna kanallarini sozlash kerak.').strip()
     else:safe_action={'type':'subscription_required','enabled':enabled}
    elif kind=='awake_window':
     start_time=str(proposed.get('start',''));end_time=str(proposed.get('end',''))
     if re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',start_time) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',end_time):
      safe_action={'type':'awake_window','start':start_time,'end':end_time}
   if not reply:reply='Tushundim. Aniqroq ayta olasizmi?'
   return {'ok':True,'reply':reply,'action':safe_action}
  except urllib.error.HTTPError as exc:
   if exc.code==401:return {'ok':False,'error':'api_key_invalid'}
   if exc.code==429:return {'ok':False,'error':'api_quota_exceeded'}
   if exc.code==403:return {'ok':False,'error':'api_permission_denied'}
   if exc.code==400:return {'ok':False,'error':'api_request_invalid'}
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
   archived=[dict(a) for a in db.permanent_results_for_test(t['test_id'],5000) if int(a['submitted'] or 0)] if hasattr(db,'permanent_results_for_test') else []
   current_ids={str(a['attempt_id']) for a in done}
   historical=[a for a in archived if str(a.get('attempt_id') or '') not in current_ids]
   result_rows={str(a.get('attempt_id') or ''):a for a in archived}
   for a in done:result_rows[str(a['attempt_id'])]=dict(a)
   ranked=sorted(result_rows.values(),key=lambda a:(-float(a.get('score') or 0),str(a.get('finished_at') or '9999')))
   test_remaining=0
   if int(t['is_mock'] or 0) and t['timer_ends_at'] and int(t['active'] or 0):
    try:
     end=datetime.fromisoformat(str(t['timer_ends_at']).replace('Z','+00:00'))
     if end.tzinfo is None:end=end.replace(tzinfo=TZ)
     test_remaining=max(0,int(__import__('math').ceil((end-datetime.now(TZ)).total_seconds())))
    except Exception:test_remaining=0
   participants=[]
   for a in sorted(attempts,key=lambda a:str(a['started_at'] or ''),reverse=True):
    ends=attempt_ends_at(a,t);remaining=0
    if ends and not a['submitted']:
     try:remaining=max(0,int(__import__('math').ceil((datetime.fromisoformat(ends)-datetime.now(TZ)).total_seconds())))
     except Exception:remaining=0
    participants.append({'full_name':a['full_name'] or 'Ismsiz','telegram_id':int(a['telegram_id']),'score':float(a['score'] or 0),'grade':a['grade'] or '', 'submitted':bool(a['submitted']),'started_at':a['started_at'],'finished_at':a['finished_at'],'ends_at':ends,'remaining_seconds':remaining})
   tests.append({'test_id':str(t['test_id']),'name':t['name'],'code':str(t['code']) if int(t['code_set'] or 0) else '', 'code_set':bool(int(t['code_set'] or 0)),'questions_pdf_sent':bool(int(t['questions_pdf_sent'] or 0)),'active':bool(int(t['active'])),'is_mock':bool(int(t['is_mock'] or 0)),'published':bool(int(t['published'] or 0)),'duration_minutes':int(t['duration_minutes'] or 0),'timer_started_at':str(t['timer_started_at'] or ''),'timer_ends_at':str(t['timer_ends_at'] or ''),'timer_remaining_seconds':test_remaining,'required_channel':str(t['required_channel'] or ''),'required_channel_link':str(t['required_channel_link'] or ''),'questions_channel':str(t['questions_channel'] or ''),'questions':len(db.questions_for_test(t['test_id'])),'participants':len(attempts),'completed':len(done),'historical_completed':len(historical),'total_completed':len(ranked),'has_results':bool(ranked),'ranking':[{'rank':i+1,'full_name':a.get('full_name') or 'Ismsiz','score':float(a.get('score') or 0),'grade':a.get('grade') or ''} for i,a in enumerate(ranked[:10])],'active_timers':[p for p in participants if p['ends_at'] and not p['submitted']],'recent':participants[:50]})
   all_rows.extend(participants)
  registered=db.all_registered_users();admin_users=[]
  for user in registered[:200]:
   uid=int(user['telegram_id']);admin_users.append({'telegram_id':uid,'full_name':user['full_name'] or 'Ismsiz','username':str(db.get_setting('telegram_username_'+str(uid),'') or '').lstrip('@')})
  return {'ok':True,'stats':{'users':len(registered),'tests':len(tests),'participants':len(all_rows),'completed':sum(1 for a in all_rows if a['submitted'])},'tests':tests,'users':admin_users}
 @core.app.post('/api/admin/mock/create')
 async def admin_mock_create(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  name=str(p.get('name','')).strip()[:120];code=str(p.get('code','')).strip()
  try:duration=int(p.get('duration_minutes',0))
  except Exception:return {'ok':False,'error':'invalid_duration'}
  import re
  if not name or not re.fullmatch(r'[A-Za-z0-9_-]{3,40}',code):return {'ok':False,'error':'invalid_test'}
  if db.test_code_exists(code):return {'ok':False,'error':'code_exists'}
  if not 1<=duration<=600:return {'ok':False,'error':'invalid_duration'}
  try:
   test=db.create_mock_test(name,duration,expected_questions=max(0,min(200,int(p.get('question_count') or 0))))
   result=db.set_mock_test_code(test['test_id'],code)
   if result!='ok':db.delete_test(test['test_id']);return {'ok':False,'error':result}
   return {'ok':True,'test':{'test_id':str(test['test_id']),'name':test['name'],'code':code,'code_set':True,'active':bool(test['active']),'published':False},'message':'MOCK test kodi orqali ochiladi; savollar va timer sozlamasi tayyor.'}
  except Exception:
   logging.getLogger('nur-oqiw.mock').exception('Could not create mock test')
   return {'ok':False,'error':'create_failed'}
 @core.app.post('/api/admin/mock/question/add')
 async def admin_mock_question_add(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id','')).strip();test=db.get_test(test_id)
  if not test or not int(test['is_mock'] or 0):return {'ok':False,'error':'mock_test_not_found'}
  if test['timer_started_at'] or any(a['started_at'] for a in db.all_attempts_for_test(test_id)):return {'ok':False,'error':'mock_already_started','message':'Test boshlangan. Savollar endi o‘zgartirilmaydi.'}
  question=str(p.get('question','')).strip()[:4000];kind=str(p.get('kind','choice')).strip().lower();options=p.get('options',[]);answer=str(p.get('answer','')).strip()
  try:number=int(p.get('number') or (len(db.questions_for_test(test_id))+1))
  except Exception:return {'ok':False,'error':'invalid_question'}
  if not 1<=number<=200 or (question and len(question)>4000):return {'ok':False,'error':'invalid_question'}
  if kind=='choice':
   answer=answer.upper()
   if answer not in ('A','B','C','D'):return {'ok':False,'error':'invalid_answer'}
   if not isinstance(options,list) or (options and (len(options)!=4 or any(not str(v).strip() for v in options))):return {'ok':False,'error':'invalid_options'}
   options=[str(v).strip()[:1000] for v in options] if options else ['A','B','C','D']
  elif kind=='written':
   if not answer:return {'ok':False,'error':'invalid_answer'}
   options=[]
  else:return {'ok':False,'error':'invalid_question_kind'}
  db.upsert_test_question(test_id,number,question,options,answer,kind,str(number))
  return {'ok':True,'message':f'{number}-savol MOCK testga qo‘shildi.'}
 @core.app.post('/api/admin/mock/code/set')
 async def admin_mock_code_set(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id','')).strip();test=db.get_test(test_id);code=str(p.get('code','')).strip()
  if not test or not int(test['is_mock'] or 0):return {'ok':False,'error':'mock_test_not_found'}
  import re
  if not re.fullmatch(r'[A-Za-z0-9_-]{3,40}',code):return {'ok':False,'error':'invalid_code'}
  if int(test['published'] or 0) or test['timer_started_at'] or any(a['started_at'] for a in db.all_attempts_for_test(test_id)):
   return {'ok':False,'error':'mock_already_started','message':'Test boshlangan yoki aktiv ro‘yxatga chiqarilgan; kod o‘zgartirilmaydi.'}
  result=db.set_mock_test_code(test_id,code)
  if result=='code_exists':return {'ok':False,'error':'code_exists'}
  if result!='ok':return {'ok':False,'error':'mock_test_not_found'}
  return {'ok':True,'code':code,'message':'MOCK test kodi saqlandi.'}
 @core.app.post('/api/admin/mock/publish')
 async def admin_mock_publish(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id','')).strip();test=db.get_test(test_id)
  if not test or not int(test['is_mock'] or 0):return {'ok':False,'error':'mock_test_not_found'}
  db.set_test_active(test_id,1);db.set_test_published(test_id,0)
  return {'ok':True,'published':False,'message':'MOCK test Aktiv testlar ro‘yxatida ko‘rinmaydi. Qatnashchilar uchun avval TESTNI BOSHLASHni bosing.'}
 @core.app.post('/api/admin/mock/questions-pdf')
 async def admin_mock_questions_pdf(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id','')).strip();test=db.get_test(test_id)
  if not test or not int(test['is_mock'] or 0):return {'ok':False,'error':'mock_test_not_found'}
  return {'ok':False,'error':'not_required','message':'Savollar PDF’i kanali talab qilinmaydi. Natijalar Admin panelidagi Natijalar bo‘limida ko‘rinadi.'}
 @core.app.get('/api/admin/mock/share')
 async def admin_mock_share(req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(req.query_params.get('test_id','')).strip();test=db.get_test(test_id)
  if not test or not int(test['is_mock'] or 0):return {'ok':False,'error':'mock_test_not_found'}
  if not int(test['code_set'] or 0):return {'ok':False,'error':'code_required'}
  try:
   me=await bot.get_me();code=urllib.parse.quote(str(test['code']),safe='_-')
   return {'ok':True,'bot_link':f'https://t.me/{me.username}?start={code}','mini_app_link':f"{WEBAPP.rstrip('/')}/test?code={code}"}
  except Exception:
   logging.getLogger('nur-oqiw.mock').exception('Could not create MOCK share links')
   return {'ok':False,'error':'share_link_failed'}
 @core.app.post('/api/admin/mock/start')
 async def admin_mock_start(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  return await start_mock_test_session(str(p.get('test_id','')).strip())

 @core.app.post('/api/admin/mock/restart')
 async def admin_mock_restart(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  return await restart_mock_test_session(str(p.get('test_id','')).strip())

 @core.app.post('/api/admin/mock/results-pdf')
 async def admin_mock_results_pdf(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id','')).strip();test=db.get_test(test_id)
  if not test or not int(test['is_mock'] or 0):return {'ok':False,'error':'mock_test_not_found'}
  recalculate_mock_scores(test_id)
  current=any(int(a['submitted'] or 0) for a in db.all_attempts_for_test(test_id))
  archived=any(int(a['submitted'] or 0) for a in db.permanent_results_for_test(test_id,5000))
  if not (current or archived):return {'ok':False,'error':'no_results'}
  path=''
  try:
   with tempfile.NamedTemporaryFile(prefix='nur-mock-results-',suffix='.pdf',delete=False) as tmp:path=tmp.name
   build_test_pdf(test_id,path)
   await bot.send_document(ADMIN,FSInputFile(path,filename=f"{test['code'] if int(test['code_set'] or 0) else 'MOCK'}-mock-natijalar.pdf"),caption=f"{test['name']} — MOCK natijalari")
   return {'ok':True,'message':'Rangli MOCK natijalari PDF’i admin chatiga yuborildi.'}
  except Exception:
   logging.getLogger('nur-oqiw.mock').exception('Mock results PDF delivery failed')
   return {'ok':False,'error':'results_pdf_failed'}
  finally:
   if path:
    try:os.remove(path)
    except OSError:pass
 @core.app.post('/api/admin/test/create')
 async def admin_create_test(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  name=str(p.get('name','')).strip()[:120];code=str(p.get('code','')).strip()
  import re
  if not name or not re.fullmatch(r'[A-Za-z0-9_-]{3,40}',code):return {'ok':False,'error':'invalid_test'}
  if db.test_code_exists(code):return {'ok':False,'error':'code_exists'}
  try:
   test=db.create_paid_test(name,code) if p.get('paid') is True else db.create_test(name,code)
   return {'ok':True,'test':{'test_id':str(test['test_id']),'name':test['name'],'code':test['code'],'active':bool(test['active']),'paid':db.is_paid_test(test['test_id'])},'message':'Test yaratildi. Savollarni shu Mini App admin panelida yoki botda qo‘shing.'}
  except Exception:
   logging.getLogger('nur-oqiw.admin').exception('Could not create test')
   return {'ok':False,'error':'create_failed'}
 @core.app.get('/api/admin/test/questions')
 async def admin_test_questions(req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(req.query_params.get('test_id','')).strip();t=db.get_test(test_id)
  if not t:return {'ok':False,'error':'test_not_found'}
  rows=db.questions_for_test(test_id)
  out=[]
  for q in rows:
   try:opts=json.loads(q['options_json'] or '[]')
   except Exception:opts=[]
   out.append({'id':int(q['number'] or q['id']),'number':int(q['number'] or q['id']),'question':q['question'] or '', 'options':opts,'answer':q['answer'] or '', 'kind':q['kind'] or 'choice','image_url':q['image_url'] or ''})
  return {'ok':True,'test':{'test_id':str(t['test_id']),'name':t['name'],'code':t['code']},'questions':out}
 @core.app.post('/api/admin/test/question/update')
 async def admin_test_question_update(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id','')).strip();t=db.get_test(test_id)
  if not t:return {'ok':False,'error':'test_not_found'}
  if int(t['is_mock'] or 0) and (t['timer_started_at'] or any(a['started_at'] for a in db.all_attempts_for_test(test_id))):return {'ok':False,'error':'mock_already_started'}
  try:
   number=int(p.get('number',0));kind=str(p.get('kind','choice')).lower();question=str(p.get('question','')).strip()[:4000];answer=str(p.get('answer','')).strip();options=p.get('options',[])
   if not 1<=number<=1000 or not question:return {'ok':False,'error':'invalid_question'}
   if kind=='choice':
    if not isinstance(options,list) or len(options)!=4 or any(not str(x).strip() for x in options):return {'ok':False,'error':'invalid_options'}
    if answer.upper() not in ('A','B','C','D'):return {'ok':False,'error':'invalid_answer'}
    options=[str(x).strip()[:1000] for x in options];answer=answer.upper()
   elif kind=='written':
    if not answer:return {'ok':False,'error':'invalid_answer'}
    options=[]
   else:return {'ok':False,'error':'invalid_kind'}
   db.upsert_test_question(test_id,number,question,options,answer,kind)
   if int(t['is_mock'] or 0):db.set_mock_questions_pdf_sent(test_id,0)
   return {'ok':True,'message':f'{number}-savol va uning to‘g‘ri javobi saqlandi.'}
  except Exception:
   logging.getLogger('nur-oqiw.admin').exception('Admin question update failed')
   return {'ok':False,'error':'question_save_failed'}
 @core.app.post('/api/admin/test/top1')
 async def admin_test_top1(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id','')).strip();t=db.get_test(test_id)
  if not t:return {'ok':False,'error':'test_not_found'}
  username=str(p.get('username','')).strip().lstrip('@').lower()
  try:target=int(p.get('telegram_id',0) or 0);rank_no=int(p.get('rank',1) or 0)
  except Exception:return {'ok':False,'error':'invalid_target'}
  if username:
   target=0
   for user in db.all_registered_users():
    if (db.get_setting('telegram_username_'+str(user['telegram_id']),'') or '').lower()==username:
     target=int(user['telegram_id']);break
   if not target:return {'ok':False,'error':'username_not_found'}
  if rank_no==0:
   for pos in range(1,16):
    if (db.get_setting('admin_rank_'+test_id+'_'+str(pos),'') or '')==str(target):
     db.set_setting('admin_rank_'+test_id+'_'+str(pos),'')
   if (db.get_setting('admin_top1_'+test_id,'') or '')==str(target):db.set_setting('admin_top1_'+test_id,'')
   return {'ok':True,'message':'Qo‘lda belgilangan o‘rin olib tashlandi; reyting avtomatik hisoblanadi.'}
  if not 1<=rank_no<=15 or target<=0:return {'ok':False,'error':'invalid_target'}
  attempt=db.get_attempt(test_id,target)
  if not attempt or not attempt['submitted']:return {'ok':False,'error':'result_not_found'}
  for pos in range(1,16):
   if (db.get_setting('admin_rank_'+test_id+'_'+str(pos),'') or '')==str(target):
    db.set_setting('admin_rank_'+test_id+'_'+str(pos),'')
  # Clear the legacy Top 1 pin so it cannot override a newer position edit.
  db.set_setting('admin_top1_'+test_id,'')
  db.set_setting('admin_rank_'+test_id+'_'+str(rank_no),str(target))
  if rank_no==1:db.set_setting('admin_top1_'+test_id,str(target))
  return {'ok':True,'message':'@'+(username or (db.get_setting('telegram_username_'+str(target),'') or str(target)))+' uchun '+str(rank_no)+'-o‘rin qo‘lda belgilandi. Qolgan o‘rinlar avtomatik.'}
 @core.app.get('/api/admin/test/results')
 async def admin_test_results(req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(req.query_params.get('test_id','')).strip();t=db.get_test(test_id)
  if not t:return {'ok':False,'error':'test_not_found'}
  questions=db.questions_for_test(test_id);current=db.all_attempts_for_test(test_id);combined={}
  if hasattr(db,'permanent_results_for_test'):
   for a in db.permanent_results_for_test(test_id,5000):combined[str(a['attempt_id'])]=dict(a)
  for a in current:combined[str(a['attempt_id'])]=dict(a)
  rows=list(combined.values());out=[]
  for a in rows:
   try:answers=json.loads(a.get('answers_json') or '{}')
   except Exception:answers={}
   correct_count=sum(1 for question in questions if norm(answers.get(str(question['number']),''))==norm(question['answer']))
   out.append({'telegram_id':int(a['telegram_id']),'username':db.get_setting('telegram_username_'+str(a['telegram_id']),'') or '', 'full_name':a.get('full_name') or 'Ismsiz','phone':a.get('phone') or '', 'submitted':bool(a.get('submitted')),'status':a.get('status') or '', 'score':float(a.get('score') or 0),'grade':a.get('grade') or '', 'correct_count':correct_count,'total_questions':len(questions),'started_at':a.get('started_at'),'finished_at':a.get('finished_at'),'answers':answers})
  out.sort(key=lambda a:(not a['submitted'],-a['score'] if a['submitted'] else 0,str(a['full_name'] or '').casefold()))
  rank=0
  for row in out:
   if row['submitted']:rank+=1;row['rank']=rank
   else:row['rank']=None
  return {'ok':True,'test':{'name':t['name'],'code':t['code']},'results':out}
 @core.app.post('/api/admin/test/toggle')
 async def admin_toggle_test(p:dict,req:Request):
  tid,u=await auth(req)
  if not tid or tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id','')).strip();t=db.get_test(test_id)
  if not t:return {'ok':False,'error':'test_not_found'}
  if int(t['is_mock'] or 0) and int(t['active']):
   finalized=await finish_mock_test(t,'admin')
   return {'ok':True,'active':False,'finalized':finalized,'message':'MOCK test to‘xtatildi. Qatnashchilar hisoblandi va natijalar PDF’i yuborildi.'}
  if int(t['is_mock'] or 0):
   return {'ok':False,'error':'mock_needs_retake','message':'MOCK testni qayta o‘tkazish tugmasi bilan yangi turga tayyorlang, so‘ng TESTNI BOSHLASHni bosing.'}
  if int(t['active']):
   # Closing pauses, rather than forcibly submitting, in-progress answers.
   # Reopening therefore lets learners resume their existing attempt.
   db.set_test_active(test_id,0)
   return {'ok':True,'active':False,'finalized':0,'message':'Test vaqtincha yopildi. Yakunlanmagan urinishlar va javoblar saqlandi; qayta ochilganda davom ettirish mumkin.'}
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
  if kind=='test_delete':
   test_id=str(action.get('test_id','')).strip();code=str(action.get('code','')).strip()
   test=db.get_test(test_id) if test_id else (db.get_test_by_code(code) if code else None)
   if not test or str(test['code']).casefold()!=code.casefold():return {'ok':False,'error':'test_not_found'}
   deleted=db.delete_test(test['test_id'])
   return {'ok':bool(deleted),'message':f"{test['name']} testi o‘chirildi. Saqlangan natijalar arxivda qoldi." if deleted else 'Testni o‘chirib bo‘lmadi.'}
  if kind=='test_create':
   name=str(action.get('name','')).strip()[:120];code=str(action.get('code','')).strip()
   import re
   if not name or not re.fullmatch(r'[A-Za-z0-9_-]{3,40}',code):return {'ok':False,'error':'invalid_action'}
   if db.test_code_exists(code):return {'ok':False,'error':'code_exists'}
   try:
    test=db.create_test(name,code)
    return {'ok':True,'message':f"{test['name']} testi yaratildi. Kod: {test['code']}. Savollarni botdagi Test sozlamalari orqali qo‘shing."}
   except Exception:return {'ok':False,'error':'create_failed'}
  if kind=='test_pdf':
   test=db.get_test(str(action.get('test_id','')));code=str(action.get('code','')).strip()
   if not test or str(test['code']).casefold()!=code.casefold():return {'ok':False,'error':'test_not_found'}
   path=''
   try:
    with tempfile.NamedTemporaryFile(prefix='nur-test-',suffix='.pdf',delete=False) as tmp:path=tmp.name
    build_test_pdf(test['test_id'],path)
    await BOT.send_document(ADMIN,FSInputFile(path,filename=f"{test['code']}-natijalar.pdf"),caption=f"{test['name']} — qatnashchilar va natijalar")
    return {'ok':True,'message':f"{test['name']} testi bo‘yicha PDF adminning Telegram chatiga yuborildi."}
   except Exception:
    logging.getLogger('nur-oqiw.jarvis').exception('Jarvis PDF export failed')
    return {'ok':False,'error':'pdf_export_failed'}
   finally:
    if path:
     try:os.remove(path)
     except OSError:pass
  if kind=='question_add':
   test=db.get_test(str(action.get('test_id','')));code=str(action.get('code','')).strip()
   if not test or str(test['code']).casefold()!=code.casefold():return {'ok':False,'error':'test_not_found'}
   try:
    number=int(action.get('number',0));question=str(action.get('question','')).strip();qkind=str(action.get('kind','choice'));answer=str(action.get('answer','')).strip();options=action.get('options',[])
    if not (1<=number<=1000) or not question:return {'ok':False,'error':'invalid_action'}
    if qkind=='choice':
     if not isinstance(options,list) or len(options)!=4 or answer.upper() not in ('A','B','C','D') or any(not str(x).strip() for x in options):return {'ok':False,'error':'invalid_action'}
     answer=answer.upper();options=[str(x).strip()[:500] for x in options]
    elif qkind=='written':
     if not answer:return {'ok':False,'error':'invalid_action'}
     options=[]
    else:return {'ok':False,'error':'invalid_action'}
    db.upsert_test_question(test['test_id'],number,question,options,answer,qkind)
    return {'ok':True,'message':f"{test['name']} testiga {number}-savol saqlandi. To‘g‘ri javob: {answer}."}
   except Exception:
    logging.getLogger('nur-oqiw.jarvis').exception('Jarvis question save failed')
    return {'ok':False,'error':'question_save_failed'}
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
 @core.app.get('/api/test/paid')
 async def paid_tests_api(req:Request):
  tid,u=await auth(req)
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  items=[]
  for t in db.paid_tests_for_user(tid,ADMIN):
   if not int(t['active']):continue
   questions=db.questions_for_test(t['test_id'])
   if not questions:continue
   items.append({'test_id':str(t['test_id']),'name':str(t['name']),'code':str(t['code']),'questions':len(questions)})
  return {'ok':True,'tests':items,'contact':'https://t.me/up17b'}

 @core.app.get('/api/admin/paid/access')
 async def admin_paid_access(req:Request):
  tid,u=await auth(req)
  if tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(req.query_params.get('test_id',''))
  if not db.is_paid_test(test_id):return {'ok':False,'error':'paid_test_not_found'}
  users=[{'telegram_id':int(x['telegram_id']),'full_name':x['full_name'] or 'Ismsiz','granted_at':x['granted_at']} for x in db.paid_access_list(test_id)]
  return {'ok':True,'users':users}

 @core.app.post('/api/admin/paid/access')
 async def admin_paid_access_update(req:Request,p:dict):
  tid,u=await auth(req)
  if tid!=ADMIN:return {'ok':False,'error':'admin_only'}
  test_id=str(p.get('test_id',''))
  if not db.is_paid_test(test_id):return {'ok':False,'error':'paid_test_not_found'}
  try:target=int(p.get('telegram_id','0'))
  except (TypeError,ValueError):return {'ok':False,'error':'invalid_user_id'}
  if target<=0:return {'ok':False,'error':'invalid_user_id'}
  if not db.get_user(target):return {'ok':False,'error':'user_not_registered'}
  if str(p.get('action','grant'))=='revoke':
   db.paid_revoke(test_id,target)
  else:
   db.paid_grant(test_id,target,ADMIN)
  return {'ok':True,'users':[{'telegram_id':int(x['telegram_id']),'full_name':x['full_name'] or 'Ismsiz','granted_at':x['granted_at']} for x in db.paid_access_list(test_id)]}

 @core.app.get('/api/test/active')
 async def active_tests_api(req:Request):
  tid,u=await auth(req)
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  tests=[]
  for t in db.all_tests():
   if not int(t['active']) or db.is_paid_test(t['test_id']) or int(t['is_mock'] or 0):continue
   qs=db.questions_for_test(t['test_id'])
   if not qs:continue
   if int(t['is_mock'] or 0) and t['timer_ends_at']:
    try:
     deadline=datetime.fromisoformat(str(t['timer_ends_at']).replace('Z','+00:00'))
     if deadline.tzinfo is None:deadline=deadline.replace(tzinfo=TZ)
     if datetime.now(TZ)>=deadline.astimezone(TZ):continue
    except Exception:pass
   tests.append({'test_id':str(t['test_id']),'name':str(t['name']),'code':str(t['code']),'questions':len(qs),'is_mock':bool(int(t['is_mock'] or 0))})
  return {'ok':True,'tests':tests}

 @core.app.get('/api/test/state')
 async def state(req: Request):
  tid,u=await auth(req);c=req.query_params.get('code','').strip();t=db.get_test_by_code_or_name(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u:return {'ok':False,'error':'not_authorized'}
  if not t or not db.can_access_test(t['test_id'],tid,ADMIN):return {'ok':False,'error':'test_not_found'}
  is_mock=bool(int(t['is_mock'] or 0))
  if tid!=ADMIN and not is_mock and not await CORE.subscribed(tid):return {'ok':False,'error':'subscription_required'}
  if is_mock and mock_clock_expired(t):
   await finish_mock_test(t,'timer')
   return {'ok':False,'error':'mock_timer_ended','is_mock':True,'test_name':t['name']}
  if not db.questions_for_test(t['test_id']):return {'ok':False,'error':'test_not_ready','test_name':t['name'],'is_mock':is_mock}
  if is_mock and not t['timer_started_at']:
   return {'ok':False,'error':'mock_not_started','is_mock':True,'test_name':t['name']}
  if u['test_id']!=t['test_id']:db.update_user(tid,test_id=t['test_id'],code_ok=1,state='ready');u=db.get_user(tid)
  a=db.ensure_attempt(t['test_id'],tid)
  if is_mock:
   display_name=str(a['participant_name'] or '').strip()
  else:
   if not u['full_name']:return {'ok':False,'error':'registration_required','test_name':t['name']}
   display_name=str(u['full_name'] or '')
  if a['submitted']:
   answers=json.loads(a['answers_json'] or '{}');correct,total,unanswered=result_counts(answers,db.questions_for_test(t['test_id']))
   if is_mock:return {'ok':False,'error':'already_submitted','is_mock':True,'test_name':t['name'],'full_name':display_name}
   return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade'],'correct_count':correct,'total_questions':total,'unanswered_count':unanswered,'test_name':t['name'],'full_name':display_name}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name'],'is_mock':is_mock}
  if is_mock:t=ensure_mock_clock(t)
  if not a['started_at']:
   if not opened(t):return {'ok':False,'error':'test_closed','test_name':t['name']}
   if is_mock:
    reserved=db.start_mock_attempt_if_slot(t['test_id'],tid,datetime.now(TZ).isoformat())
    if reserved=='full':return {'ok':False,'error':'mock_participants_full','message':'MOCK test uchun qatnashchilar limiti to‘lgan.'}
    if reserved!='started':return {'ok':False,'error':'mock_timer_ended','message':'MOCK test yopilgan.'}
   else:db.update_attempt(a['attempt_id'],started_at=datetime.now(TZ).isoformat(),status='active')
   a=db.get_attempt(t['test_id'],tid)
  if expired(a,t):
   sc,gr=finalize_expired(a,t);a=db.get_attempt(t['test_id'],tid);await notify_mock_finished(tid,t,a)
   if is_mock:return {'ok':False,'error':'already_submitted','is_mock':True,'test_name':t['name'],'full_name':display_name}
   return {'ok':False,'error':'already_submitted','score':sc,'grade':gr,'test_name':t['name'],'full_name':display_name}
  qs=db.questions_for_test(t['test_id']);order=([int(q['number']) for q in qs] if is_mock else question_order_for_attempt(a,qs));by_number={int(q['number']):q for q in qs}
  answers=json.loads(a['answers_json'] or '{}');answers.pop('_question_order',None)
  results={} if is_mock else {str(q['number']):('correct' if db.normalize(answers.get(str(q['number']),''))==db.normalize(q['answer']) else 'wrong') for q in qs if str(q['number']) in answers and q['kind']!='written'}
  return {'ok':True,'full_name':display_name,'answers':answers,'results':results,'ends_at':attempt_ends_at(a,t),'is_mock':is_mock,'duration_minutes':int(t['duration_minutes'] or 0),'test_name':t['name'],'test_code':t['code'],'total_questions':len(qs),'questions':[{'id':by_number[n]['number'],'display_number':by_number[n]['group_id'] or str(i+1),'question':by_number[n]['question'] or '', 'options':((json.loads(by_number[n]['options_json'] or '[]') if by_number[n]['options_json'] else []) or ['A','B','C','D']), 'kind':by_number[n]['kind'],'image_url':by_number[n]['image_url'] or ''} for i,n in enumerate(order)]}
 @core.app.post('/api/test/retry')
 async def retry_completed_test(p:dict,req:Request):
  """Explicitly start a new attempt; previous score is retained in archives."""
  tid,u=await auth(req)
  if not tid or not u or not u['full_name']:
   return {'ok':False,'error':'not_authorized'}
  if tid!=ADMIN and not await CORE.subscribed(tid):
   return {'ok':False,'error':'subscription_required'}
  code=str(p.get('code','')).strip()
  t=db.get_test_by_code_or_name(code) if code else None
  if not t or not db.can_access_test(t['test_id'],tid,ADMIN):
   return {'ok':False,'error':'test_not_found'}
  if int(t['is_mock'] or 0):return {'ok':False,'error':'mock_retry_disabled'}
  if not int(t['active']) or not opened(t):
   return {'ok':False,'error':'test_closed'}
  if not db.questions_for_test(t['test_id']):
   return {'ok':False,'error':'test_not_ready'}
  # Safe re-submission is allowed only after explicit user confirmation.
  result=db.restart_completed_attempt(t['test_id'],tid)
  if result=='restarted':
   db.update_user(tid,test_id=t['test_id'],code_ok=1,state='ready')
   return {'ok':True,'restarted':True,'test_code':t['code'],'message':'Yangi urinish boshlandi. Eski natija arxivda saqlandi.'}
  if result=='already_active':
   return {'ok':True,'restarted':False,'test_code':t['code'],'message':'Urinish allaqachon ochiq.'}
  return {'ok':False,'error':result}

 @core.app.get('/api/test/questions')
 async def questions(req: Request):
  tid,u=await auth(req);c=req.query_params.get('code','').strip();t=db.get_test_by_code_or_name(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
  if not db.can_access_test(t['test_id'],tid,ADMIN):return {'ok':False,'error':'test_not_found'}
  is_mock=bool(int(t['is_mock'] or 0))
  if tid!=ADMIN and not is_mock and not await CORE.subscribed(tid):return {'ok':False,'error':'subscription_required'}
  if is_mock:
   if mock_clock_expired(t):
    await finish_mock_test(t,'timer')
    return {'ok':False,'error':'mock_timer_ended','is_mock':True,'test_name':t['name']}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
  if (not int(t['is_mock'] or 0) and not u['full_name']) or u['test_id']!=t['test_id'] or not opened(t):return {'ok':False,'error':'test_not_started'}
  a=db.get_attempt(t['test_id'],tid)
  if not a or not a['started_at'] or a['submitted']:return {'ok':False,'error':'test_not_started'}
  qs=db.questions_for_test(t['test_id']);order=([int(q['number']) for q in qs] if is_mock else question_order_for_attempt(a,qs));by_number={int(q['number']):q for q in qs}
  is_mock=bool(int(t['is_mock'] or 0))
  return {'ok':True,'questions':[{'id':by_number[n]['number'],'display_number':i+1,'question':by_number[n]['question'] or '', 'options':((json.loads(by_number[n]['options_json'] or '[]') if by_number[n]['options_json'] else []) or ['A','B','C','D']), 'kind':by_number[n]['kind'],'image_url':by_number[n]['image_url'] or ''} for i,n in enumerate(order)]}
 @core.app.post('/api/test/answer')
 async def answer(p:dict, request: Request):
  raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or p.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;c=str(p.get('code','')).strip();t=db.get_test_by_code_or_name(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
  is_mock=bool(int(t['is_mock'] or 0))
  existing_attempt=db.get_attempt(t['test_id'],tid)
  if (not is_mock and not u['full_name']):return {'ok':False,'error':'not_authorized'}
  if not db.can_access_test(t['test_id'],tid,ADMIN):return {'ok':False,'error':'test_not_found'}
  if tid!=ADMIN and not is_mock and not await CORE.subscribed(tid):return {'ok':False,'error':'subscription_required'}
  if is_mock:
   if mock_clock_expired(t):
    await finish_mock_test(t,'timer')
    return {'ok':False,'error':'already_submitted','is_mock':True,'message':'Test tugadi. Javoblar tez orada e’lon qilinadi.'}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
  a=db.get_attempt(t['test_id'],tid)
  if u['test_id']!=t['test_id'] and (not a or not a['started_at']):return {'ok':False,'error':'test_not_started'}
  if not a or not a['started_at']:return {'ok':False,'error':'test_not_started'}
  if not int(t['is_mock'] or 0) and not u['full_name']:return {'ok':False,'error':'not_authorized'}
  if a['submitted']:return {'ok':False,'error':'already_submitted'}
  if expired(a,t):
   sc,gr=finalize_expired(a,t);a=db.get_attempt(t['test_id'],tid)
   if int(t['is_mock'] or 0):await notify_mock_finished(tid,t,a)
   return {'ok':False,'error':'already_submitted','is_mock':bool(int(t['is_mock'] or 0)),'score':None if int(t['is_mock'] or 0) else sc,'grade':None if int(t['is_mock'] or 0) else gr}
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
  raw=request.headers.get('Authorization','');raw=raw[4:] if raw.startswith('tma ') else raw;raw=raw or p.get('initData','');tid=CORE.telegram_user(raw);u=db.get_user(tid) if tid else None;c=str(p.get('code','')).strip();t=db.get_test_by_code_or_name(c) if c else (db.get_test(u['test_id']) if u and u['test_id'] else None)
  if not tid or not u or not t:return {'ok':False,'error':'not_authorized'}
  is_mock=bool(int(t['is_mock'] or 0));existing_attempt=db.get_attempt(t['test_id'],tid)
  if not db.can_access_test(t['test_id'],tid,ADMIN):return {'ok':False,'error':'test_not_found'}
  if not is_mock and not u['full_name']:return {'ok':False,'error':'not_authorized'}
  if tid!=ADMIN and not is_mock and not await CORE.subscribed(tid):return {'ok':False,'error':'subscription_required'}
  participant_name=' '.join(str(p.get('participant_name','')).strip().split())[:120] if is_mock else ''
  if is_mock and len(participant_name.split())<2 and existing_attempt:
   participant_name=' '.join(str(existing_attempt['participant_name'] or '').strip().split())[:120]
  if is_mock and existing_attempt and not int(existing_attempt['submitted'] or 0) and len(participant_name.split())>=2:
   db.update_attempt(existing_attempt['attempt_id'],participant_name=participant_name);existing_attempt=db.get_attempt(t['test_id'],tid)
  if is_mock and mock_clock_expired(t):
   if not existing_attempt or not existing_attempt['started_at']:return {'ok':False,'error':'test_not_started'}
   await finish_mock_test(t,'timer')
   final_attempt=db.get_attempt(t['test_id'],tid)
   return {'ok':True,'is_mock':True,'message':'Test tugadi. Javoblar tez orada e’lon qilinadi.','full_name':str(final_attempt['participant_name'] or '') if final_attempt else '','test_name':t['name']}
  if is_mock and len(participant_name.split())<2 and not (existing_attempt and int(existing_attempt['submitted'] or 0)):
   return {'ok':False,'error':'participant_name_required','is_mock':True,'test_name':t['name'],'message':'Testni yakunlash uchun ism va familiyangizni kiriting.'}
  if u['test_id']!=t['test_id'] and (not existing_attempt or not existing_attempt['started_at']):return {'ok':False,'error':'test_not_started'}
  a=db.get_attempt(t['test_id'],tid)
  if not a or not a['started_at']:return {'ok':False,'error':'test_not_started'}
  if a['submitted']:
   answers=json.loads(a['answers_json'] or '{}');correct,total,_=result_counts(answers,db.questions_for_test(t['test_id']))
   if is_mock:return {'ok':True,'is_mock':True,'message':'Javoblaringiz saqlangan. Natijalar tez orada e’lon qilinadi.'}
   return {'ok':False,'error':'already_submitted','score':a['score'],'grade':a['grade'],'correct_count':correct,'total_questions':total}
  if not int(t['active']):return {'ok':False,'error':'test_stopped','test_name':t['name']}
  if expired(a,t):
   sc,gr=finalize_expired(a,t)
   if is_mock:
    await notify_mock_finished(tid,t,db.get_attempt(t['test_id'],tid))
    return {'ok':True,'is_mock':True,'message':'Test tugadi. Javoblar tez orada e’lon qilinadi.','full_name':a['participant_name'],'test_name':t['name']}
   return {'ok':True,'score':sc,'grade':gr,'full_name':u['full_name'],'test_name':t['name']}
  if not opened(t):return {'ok':False,'error':'test_closed'}
  status,sc,gr,correct,total=finish_attempt_atomically(t['test_id'],tid,db.questions_for_test(t['test_id']),datetime.now(TZ).isoformat())
  if status=='not_started':return {'ok':False,'error':'test_not_started'}
  if status=='already_submitted':
   if is_mock:return {'ok':False,'error':'already_submitted','is_mock':True,'message':'Test tugadi. Javoblar tez orada e’lon qilinadi.'}
   return {'ok':False,'error':'already_submitted','score':sc,'grade':gr,'correct_count':correct,'total_questions':total}
  if is_mock:
   await notify_mock_finished(tid,t,db.get_attempt(t['test_id'],tid))
   return {'ok':True,'is_mock':True,'message':'Test tugadi. Javoblar tez orada e’lon qilinadi.','full_name':participant_name,'test_name':t['name']}
  return {'ok':True,'score':sc,'grade':gr,'correct_count':correct,'total_questions':total,'wrong_count':max(0,total-correct),'full_name':u['full_name'],'test_name':t['name']}
 @r.message(CommandStart(deep_link=True))
 async def deep(m:Message,command):
  t=db.get_test_by_code_or_name((command.args or '').strip())
  if not t or not db.can_access_test(t['test_id'],m.from_user.id,ADMIN):return await m.answer('Test topilmadi yoki pulli testga ruxsatingiz yo‘q.')
  u=db.ensure_user(m.from_user.id);db.update_user(m.from_user.id,test_id=t['test_id'],code_ok=1,state='ready' if u['full_name'] else 'name');db.ensure_attempt(t['test_id'],m.from_user.id);u=db.get_user(m.from_user.id)
  if not u['full_name']:
   return await m.answer(f"{t['name']}\n\nIsm-familiyangizni yozing yoki Telegram ismingiz bilan davom eting:",reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Telegram ismim bilan davom etish')]],resize_keyboard=True,one_time_keyboard=True))
  return await m.answer(f"{t['name']}\n\nTest tanlandi. Testni boshlash tugmasini bosing.",reply_markup=user_menu())
 @r.message(F.text=='Profilim')
 async def profile(m:Message):
  u=db.ensure_user(m.from_user.id);t=db.get_test(u['test_id']) if u['test_id'] else None;a=db.get_attempt(t['test_id'],m.from_user.id) if t else None;res=f"{float(a['score'] or 0):.2f} ball · {a['grade'] or '—'}" if a and a['submitted'] else 'Yakunlanmagan'
  url=f"{WEBAPP.rstrip('/')}/profile";mk=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='MINI APP PROFILIM',web_app=WebAppInfo(url=url))]])
  values={'name':u['full_name'] or '—','test':t['name'] if t else 'Tanlanmagan','code':t['code'] if t else '—','result':res}
  profile_message=menu_config.render_profile(db,values)
  try:
   await m.answer(profile_message,parse_mode='HTML',reply_markup=mk)
  except Exception:
   # An invalid third-party premium emoji must never break a user's profile.
   from html import escape as html_escape
   fallback='PROFILIM\n\n'+'\n'.join(f'{key}: {html_escape(str(value))}' for key,value in [('Ism-familiya',values['name']),('Test',values['test']),('Kod',values['code']),('Natija',values['result'])])
   await m.answer(fallback,parse_mode='HTML',reply_markup=mk)
 @r.message(F.text=='Mening natijam')
 async def user_results(m:Message):
  u=db.get_user(m.from_user.id)
  if not u:return await m.answer("Siz hali ro‘yxatdan o‘tmagansiz. /start ni bosing.",reply_markup=user_menu())
  rows=db.test_history_for_user(m.from_user.id,m.from_user.id,ADMIN,only_submitted=True)
  if not rows:return await m.answer("Hozircha yakunlangan test natijangiz yo‘q.",reply_markup=user_menu())
  lines=['MENING NATIJALARIM']
  for i,row in enumerate(rows[:15],1):
   name=str(row['test_name'] or 'Test')
   code=str(row['code'] or 'kod yo‘q')
   if row['submitted']:
    status=f"Natija: {float(row['score'] or 0):.2f} ball"
    mark=f"Baho: {row['grade'] or '—'}"
   else:
    status='Holat: Yakunlanmagan'
    mark=None
   lines.append(f"{i}. {name} · Kod: {code} · {status}"+(f" · {mark}" if mark else ''))
  await m.answer('\n'.join(lines),reply_markup=user_menu())
 @r.message(F.text=='Pulli testlar')
 async def paid_tests_menu(m:Message):
  if m.from_user.id==ADMIN:
   ast('admin')
   tests=db.paid_tests_for_user(ADMIN,ADMIN)
   return await m.answer(
    '<b>PULLI TESTLAR · ADMIN</b>\n\n'
    f'Testlar: <b>{len(tests)}</b> ta\n'
    'Test yarating, savollar va javoblarni botda sozlang. '
    'Foydalanuvchilarga kirishni Telegram chat ID orqali bering.\n'
    'O‘quvchilar testni Mini App orqali yechadi.',
    parse_mode='HTML',reply_markup=paid_menu_kb())
  allowed=db.paid_tests_for_user(m.from_user.id,ADMIN)
  rows=[]
  for t in allowed:
   if not int(t['active']) or not db.questions_for_test(t['test_id']):continue
   rows.append([InlineKeyboardButton(
    text=(str(t['name'])+' · '+str(t['code']))[:55],
    web_app=WebAppInfo(url=WEBAPP.rstrip('/')+'/test?code='+str(t['code'])),style='primary')])
  rows.append([InlineKeyboardButton(text='SOTIB OLISH / ADMIN @up17b',url='https://t.me/up17b')])
  return await m.answer(
   '<b>PULLI TESTLAR</b>\n\n'
   +('Siz uchun ochilgan testni tanlang.' if rows.__len__()>1
     else 'Hozircha sizga ruxsatli test yo‘q. Sotib olish uchun adminga yozing. '
          'Tasdiqlangach test shu menyuda ochiladi.'),
   parse_mode='HTML',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

 @r.callback_query(F.data=='paid_list')
 async def paid_list(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q.',show_alert=True)
  tests=db.paid_tests_for_user(ADMIN,ADMIN)
  await q.message.edit_text(
   '<b>PULLI TESTLAR · ADMIN</b>\n\n'
   f'Saqlangan testlar: <b>{len(tests)}</b> ta\n'
   'Testni tanlang yoki yangi test yarating.',
   parse_mode='HTML',reply_markup=paid_menu_kb())
  await q.answer()

 @r.callback_query(F.data=='paid_new')
 async def paid_new(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q.',show_alert=True)
  clear_draft()
  save_draft({'paid':True})
  ast('new_code')
  await q.message.answer(
   '<b>YANGI PULLI TEST · 1/3</b>\n\n'
   'Test uchun noyob <b>kirish kodi</b>ni yuboring.\n'
   'Masalan: PREMIUM2026\n\n'
   'Keyingi bosqichlarda nom, savollar soni va to‘g‘ri javoblar kiritiladi.',
   parse_mode='HTML')
  await q.answer()

 @r.callback_query(F.data.startswith('paid_admin:'))
 async def paid_admin_actions(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q.',show_alert=True)
  test_id=q.data.split(':',1)[1]
  t=db.get_test(test_id)
  if not t or not db.is_paid_test(test_id):
   return await q.answer('Pulli test topilmadi.',show_alert=True)
  holders=db.paid_access_list(test_id)
  questions=db.questions_for_test(test_id)
  text=('<b>'+escape(str(t['name']))+'</b>\n'
   'Kod: <code>'+escape(str(t['code']))+'</code>\n'
   'Savollar: <b>'+str(len(questions))+'</b>\n'
   'Qatnashish ruxsati: <b>'+str(len(holders))+'</b>\n'
   'Holat: <b>'+('Ochiq' if int(t['active']) else 'Yopiq')+'</b>\n\n'
   'Barcha boshqaruv tugmalari quyida.')
  await q.message.edit_text(text,parse_mode='HTML',reply_markup=paid_test_kb(test_id))
  await q.answer()

 @r.callback_query(F.data.startswith('paid_grant:'))
 async def paid_grant_enter(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q.',show_alert=True)
  test_id=q.data.split(':',1)[1]
  if not db.is_paid_test(test_id):return await q.answer('Pulli test topilmadi.',show_alert=True)
  # Telegram's native user selection works ONLY on a reply keyboard.
  # A callback button opens this short-lived reply keyboard, not a Web App.
  request_id=secrets.randbelow(2**30-1)+1
  ast('paid_select:'+test_id+':'+str(request_id))
  chooser=ReplyKeyboardMarkup(keyboard=[
   [KeyboardButton(text='FOYDALANUVCHINI TANLASH',request_users=KeyboardButtonRequestUsers(
    request_id=request_id,user_is_bot=False,max_quantity=1,request_name=True,request_username=True))],
   [KeyboardButton(text='CHAT ID NI QO‘LDA KIRITISH')],
   [KeyboardButton(text='BEKOR QILISH')]
  ],resize_keyboard=True,one_time_keyboard=True)
  await q.message.answer(
   '<b>QATNASHCHI QO‘SHISH</b>\n\n'
   'Telegram kontaktlaridan foydalanuvchini tanlang yoki chat ID ni kiriting.\n'
   'Foydalanuvchi oldin botda <code>/start</code> bosgan bo‘lishi shart.',
   parse_mode='HTML',reply_markup=chooser)
  await q.answer()

 @r.callback_query(F.data.startswith('paid_members:'))
 async def paid_members(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q.',show_alert=True)
  tid=q.data.split(':',1)[1]
  if not db.is_paid_test(tid):return await q.answer('Test topilmadi.',show_alert=True)
  users=db.paid_access_list(tid)
  kb=[]
  for u in users[:40]:
   uid=int(u['telegram_id'])
   kb.append([InlineKeyboardButton(text=('OLIB TASHLASH · '+str(u['full_name'] or uid))[:56],
     callback_data=f'paid_rm:{tid}:{uid}',style='danger')])
  kb.append([InlineKeyboardButton(text='YANGI QATNASHCHI',callback_data='paid_grant:'+tid,style='success')])
  kb.append([InlineKeyboardButton(text='ORQAGA',callback_data='paid_admin:'+tid)])
  await q.message.edit_text(
   '<b>TEST QATNASHCHILARI</b>\n\n'
   'Kirishi tasdiqlanganlar: <b>'+str(len(users))+'</b> ta.\n'
   'Olib tashlash uchun kerakli foydalanuvchini tanlang.',
   parse_mode='HTML',reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
  await q.answer()

 @r.callback_query(F.data.startswith('paid_rm:'))
 async def paid_revoke_confirm(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q.',show_alert=True)
  _,tid,uid=q.data.split(':',2)
  if not db.is_paid_test(tid):return await q.answer('Test topilmadi.',show_alert=True)
  name=db.get_user(int(uid))
  buttons=InlineKeyboardMarkup(inline_keyboard=[
   [InlineKeyboardButton(text='HA, RUXSATNI OLIB TASHLASH',callback_data=f'paid_yesrm:{tid}:{uid}',style='danger')],
   [InlineKeyboardButton(text='BEKOR QILISH',callback_data='paid_members:'+tid)]])
  await q.message.edit_text(
   '<b>RUXSATNI OLIB TASHLASH</b>\n\n'
   +escape(str(name['full_name'] if name else uid))+' · <code>'+uid+'</code>\n'
   'Ushbu odam endi pulli testni ocha olmaydi. Tasdiqlaysizmi?',
   parse_mode='HTML',reply_markup=buttons)
  await q.answer()

 @r.callback_query(F.data.startswith('paid_yesrm:'))
 async def paid_revoke_do(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q.',show_alert=True)
  _,tid,uid=q.data.split(':',2)
  if not db.is_paid_test(tid):return await q.answer('Test topilmadi.',show_alert=True)
  db.paid_revoke(tid,int(uid))
  await q.message.edit_text('Ruxsat olib tashlandi.',reply_markup=InlineKeyboardMarkup(
   inline_keyboard=[[InlineKeyboardButton(text='QATNASHCHILAR',callback_data='paid_members:'+tid,style='primary')]]))
  await q.answer('Ruxsat olib tashlandi')

 @r.callback_query(F.data.startswith('paid_ok:'))
 async def paid_grant_confirm(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q.',show_alert=True)
  _,tid,uid=q.data.split(':',2)
  current=db.get_user(ADMIN)
  if not current or str(current['state'])!='paid_confirm:'+tid+':'+uid:
   return await q.answer('Tasdiqlash sessiyasi eskirgan.',show_alert=True)
  if not db.is_paid_test(tid):return await q.answer('Test topilmadi.',show_alert=True)
  person=db.get_user(int(uid))
  if not person:return await q.answer('Foydalanuvchi botga /start bosmagan.',show_alert=True)
  db.paid_grant(tid,int(uid),ADMIN)
  ast('admin')
  test=db.get_test(tid)
  try:
   await BOT.send_message(int(uid),
     'Sizga «'+test['name']+'» pulli testiga ruxsat berildi. Testni botdagi «Pulli testlar» orqali yeching.',
     reply_markup=InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text='TESTNI OCHISH',web_app=WebAppInfo(url=WEBAPP.rstrip()+'/test?code='+str(test['code'])),style='success')]]))
  except Exception:pass
  await q.message.edit_text(
   '<b>RUXSAT BERILDI</b>\n\n'
   +escape(str(person['full_name'] or 'Ismsiz'))+' · <code>'+uid+'</code>\n'
   'Test: <b>'+escape(str(test['name']))+'</b>',
   parse_mode='HTML',reply_markup=InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='TESTGA QAYTISH',callback_data='paid_admin:'+tid,style='primary')]]))
  await q.answer('Ruxsat saqlandi')

 @r.callback_query(F.data.startswith('paid_cancel:'))
 async def paid_grant_cancel(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q.',show_alert=True)
  tid=q.data.split(':',1)[1]
  ast('admin')
  await q.message.edit_text('Qatnashchi qo‘shish bekor qilindi.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[
   [InlineKeyboardButton(text='TESTGA QAYTISH',callback_data='paid_admin:'+tid)]]))
  await q.answer()

 @r.message(F.text=='Yordam')
 async def help_user(m:Message):
  await m.answer('Savol yoki muammo bo‘lsa, administratorga yozing: @up17b',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ADMIN BILAN BOG‘LANISH',url='https://t.me/up17b')]]))
 async def check_prompt(tid,fake_id,index):
  t=db.get_test(tid);qs=db.questions_for_test(tid);u=db.get_user(fake_id);a=db.get_attempt(tid,fake_id)
  if not t or not u or not a:return await BOT.send_message(ADMIN,'Tekshirish sessiyasi topilmadi.')
  if index>=len(qs):
   answers=json.loads(a['answers_json'] or '{}')
   score_value=round(sum(1 for x in qs if norm(answers.get(str(x['number']),' '))==norm(x['answer']))/len(qs)*100,2) if qs else 0
   grade_value=grade(score_value);finished=datetime.now(TZ).isoformat()
   db.update_attempt(a['attempt_id'],score=score_value,grade=grade_value,submitted=1,status='submitted',finished_at=finished)
   db.update_user(fake_id,score=score_value,grade=grade_value,submitted=1,finished_at=finished)
   return await BOT.send_message(ADMIN,f"TEKSHIRISH TUGADI\nAkkaunt: {u['full_name']}\nTest: {t['name']}\nNatija: {score_value:.2f} ball · {grade_value}",reply_markup=test_kb(tid))
  x=qs[index];head=f"TEKSHIRISH — {u['full_name']}\n{t['name']}\nSavol {index+1}/{len(qs)}\n{x['question'] or (str(x['number'])+'-savol')}\n"
  if x['kind']=='written':
   ast(f"check_written:{tid}:{fake_id}:{index}")
   return await BOT.send_message(ADMIN,head+"\nTo‘g‘ri yozma javobni kiriting (simulyatsiya):")
  kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=z,callback_data=f"t_check_ans:{tid}:{fake_id}:{index}:{z}") for z in 'ABCD']])
  return await BOT.send_message(ADMIN,head+"\nVariantni tanlang:",reply_markup=kb)
 @r.message(F.from_user.id==ADMIN,F.users_shared)
 async def paid_user_shared(m:Message):
  """Telegram-native selected users, never trust a request_id from an old menu."""
  u=db.get_user(ADMIN)
  state=str((u['state'] if u else '') or '')
  if not state.startswith('paid_select:'):
   return await m.answer('Foydalanuvchini tanlash sessiyasi yo‘q.',reply_markup=ReplyKeyboardRemove())
  try:
   _,tid,expected=state.split(':',2)
   if not db.is_paid_test(tid) or int(m.users_shared.request_id)!=int(expected):
    raise ValueError('old picker')
   selected=m.users_shared.users
   user_id=int(selected[0].user_id) if selected else int(m.users_shared.user_ids[0])
   if user_id<=0:raise ValueError('invalid user')
  except (ValueError,IndexError,TypeError,AttributeError):
   ast('admin')
   return await m.answer('Tanlash muddati tugagan. Pulli testlar bo‘limidan qayta tanlang.',reply_markup=ReplyKeyboardRemove())
  person=db.get_user(user_id)
  if not person:
   await m.answer('Tanlash oynasi yopildi.',reply_markup=ReplyKeyboardRemove())
   return await m.answer('Tanlangan odam hali botga /start bosmagan. U ro‘yxatdan o‘tgach qayta tanlang.')
  ast('paid_confirm:'+tid+':'+str(user_id))
  keyboard=InlineKeyboardMarkup(inline_keyboard=[
   [InlineKeyboardButton(text='HA, TESTGA QO‘SHISH',callback_data='paid_ok:'+tid+':'+str(user_id),style='success')],
   [InlineKeyboardButton(text='BEKOR QILISH',callback_data='paid_cancel:'+tid)]])
  await m.answer('Foydalanuvchi tanlandi.',reply_markup=ReplyKeyboardRemove())
  await m.answer(
   '<b>QATNASHCHINI TASDIQLASH</b>\n\n'
   +escape(str(person['full_name'] or 'Ismsiz'))+'\nID: <code>'+str(user_id)+'</code>\n'
   'Bu odamga pulli testga kirish huquqini berasizmi?',
   parse_mode='HTML',reply_markup=keyboard)

 @r.message(F.from_user.id==ADMIN)
 async def admin_text(m:Message):
  u=db.ensure_user(ADMIN);s=u['state'] or 'admin';txt=(m.text or '').strip()
  if s.startswith('mock_') and txt.casefold() in {'/cancel','bekor qilish','cancel'}:
   pending=mock_wizard_read();mock_wizard_clear();ast('admin')
   message='MOCK sozlash bekor qilindi. Yaratilgan test bo‘lsa, maxfiy holatda saqlandi.'
   if pending.get('test_id'):message+=' Ro‘yxat orqali keyin davom ettirishingiz mumkin.'
   return await m.answer(message,reply_markup=mock_admin_kb())
  if s.startswith('mock_') and txt=='Orqaga qaytish':
   mock_wizard_clear();ast('admin');db.set_setting('mock_menu_'+str(ADMIN),'')
   return await m.answer('Admin boshqaruv menyusi. Test sozlamalari va Statistika shu yerda.',reply_markup=CORE.admin_kb())
  if s.startswith('mock_schedule:'):
   tid=s.split(':',1)[1];test=db.get_test(tid)
   if not test or not int(test['is_mock'] or 0):ast('admin');return await m.answer('MOCK test topilmadi.',reply_markup=mock_admin_reply_kb())
   if txt.upper()=='OFF':
    db.set_mock_schedule(tid,'');ast('admin')
    return await m.answer('Avtomatik boshlanish bekor qilindi.',reply_markup=mock_admin_reply_kb())
   try:
    when=datetime.strptime(txt,'%d/%m/%Y %H:%M').replace(tzinfo=TZ)
   except (ValueError,TypeError):return await m.answer('Format: kun/oy/yil soat:daqiqa. Masalan: 12/11/2026 14:30')
   if when<=datetime.now(TZ):return await m.answer('Kelajakdagi vaqtni kiriting.')
   if mock_key_check(tid):return await m.answer('Avval javoblarni tekshiring:\n'+'\n'.join(mock_key_check(tid)[:10]))
   if not db.set_mock_schedule(tid,when.isoformat()):return await m.answer('Test boshlangan; vaqtni belgilab bo‘lmaydi.')
   ast('admin');return await m.answer(f"{test['name']} avtomatik boshlanadi: {when.strftime('%d/%m/%Y %H:%M')} (Toshkent).",reply_markup=mock_admin_reply_kb())
  if s.startswith('mock_limit:'):
   tid=s.split(':',1)[1]
   try:limit=int(txt)
   except (ValueError,TypeError):return await m.answer('Faqat butun son kiriting. 0 — cheklanmagan.')
   if not 0<=limit<=100000:return await m.answer('Limit 0–100000 oralig‘ida bo‘lsin.')
   started=len(db.all_attempts_for_test(tid))
   if limit and limit<started:return await m.answer(f'Allaqachon {started} kishi qatnashgan. Limit bundan kichik bo‘lmasin.')
   if not db.set_mock_participant_limit(tid,limit):return await m.answer('MOCK test topilmadi.')
   ast('admin');return await m.answer('Qatnashchilar limiti: '+(str(limit) if limit else 'cheklanmagan'),reply_markup=mock_admin_reply_kb())
  if s=='mock_code':
   import re
   if not re.fullmatch(r'[A-Za-z0-9_-]{3,40}',txt):return await m.answer('Test kodi 3–40 ta lotin harfi, raqam, _ yoki - dan iborat bo‘lsin.')
   if db.test_code_exists(txt):return await m.answer('Bu test kodi band. Boshqa kod kiriting.')
   pending=mock_wizard_read();pending['code']=txt
   if pending.get('test_id'):
    result=db.set_mock_test_code(pending['test_id'],txt)
    if result=='code_exists':return await m.answer('Bu test kodi band. Boshqa kod kiriting.')
    if result!='ok':return await m.answer('Test kodi saqlanmadi. Qayta urinib ko‘ring.')
    mock_wizard_write(pending);ast('mock_question_kind')
    return await m.answer(f"{len(db.questions_for_test(pending['test_id']))+1}/{pending.get('count',1)}-savol turini tanlang:",reply_markup=mock_question_type_kb())
   mock_wizard_write(pending);ast('mock_name')
   return await m.answer('Test nomini kiriting:')
  if s=='mock_name':
   if not txt or len(txt)>120:return await m.answer('Test nomini 1–120 belgi oralig‘ida kiriting.')
   pending=mock_wizard_read();pending['name']=txt;mock_wizard_write(pending);ast('mock_count')
   return await m.answer('Testda nechta savol bo‘ladi? (1–200)')
  if s=='mock_count':
   try:count=int(txt)
   except Exception:return await m.answer('Savollar sonini 1 dan 200 gacha butun son bilan kiriting.')
   if not 1<=count<=200:return await m.answer('Savollar sonini 1 dan 200 gacha kiriting.')
   pending=mock_wizard_read();pending['count']=count;mock_wizard_write(pending);ast('mock_duration')
   return await m.answer('Test timeri necha daqiqa bo‘lsin? Faqat daqiqada kiriting. Masalan: 40')
  if s=='mock_duration':
   try:duration=int(txt)
   except Exception:return await m.answer('Timer faqat daqiqada butun son bilan yoziladi. Masalan: 40')
   if not 1<=duration<=600:return await m.answer('Timer 1–600 daqiqa oralig‘ida bo‘lishi kerak.')
   pending=mock_wizard_read()
   if not pending.get('test_id'):
    try:
     test=db.create_mock_test(pending['name'],duration,expected_questions=int(pending.get('count') or 0))
     result=db.set_mock_test_code(test['test_id'],pending['code'])
     if result=='code_exists':db.delete_test(test['test_id']);return await m.answer('Bu kod boshqa admin testida band. Yangi test kodini kiriting.')
     if result!='ok':db.delete_test(test['test_id']);return await m.answer('Test kodi saqlanmadi. Qayta urinib ko‘ring.')
     pending['test_id']=str(test['test_id'])
    except Exception:
     logging.getLogger('nur-oqiw.mock').exception('Telegram MOCK creation failed')
     return await m.answer('MOCK test yaratilmadi. Qayta urinib ko‘ring.')
   pending['duration_minutes']=duration;mock_wizard_write(pending)
   test=db.get_test(pending['test_id'])
   # Timer begins when the first participant opens the code-only test.
   return await mock_next_question(m,pending)
  if s=='mock_written_answer':
   if not txt or len(txt)>1000:return await m.answer('Yozma javobni 1–1000 belgi oralig‘ida kiriting.')
   pending=mock_wizard_read();test_id=str(pending.get('test_id') or '')
   test=db.get_test(test_id)
   if not test or not int(test['is_mock'] or 0):mock_wizard_clear();ast('admin');return await m.answer('MOCK test topilmadi.',reply_markup=mock_admin_kb())
   if test['timer_started_at']:return await m.answer('Test boshlangan. Savollar endi o‘zgartirilmaydi.')
   mock_save_question(test_id,'written',txt)
   return await mock_next_question(m,pending)
  if txt in {'MOCK testlar','Yangi MOCK test','MOCK testlar ro‘yxati','MOCK ishtirokchilari','MOCK natijalari','MOCK testni boshlash','MOCK vaqt qo‘shish','MOCK testni to‘xtatish','MOCK qayta o‘tkazish','MOCK boshlanish vaqti','MOCK qatnashchi limiti','MOCK javoblarni tekshirish','Orqaga qaytish','Test sozlamalari','Ishtirokchilar','Statistika','Guruhlar holati','Guruhga xabar yuborish','Bildirishnoma','Ish vaqti jadvali','Majburiy obuna','PDF natijalar','Tekshirish','Tariflar','Botni uyg‘otish','Render limitini ko‘rish'}:
   ast('admin');u=db.ensure_user(ADMIN);s='admin'
  if txt=='MOCK testlar':
   db.set_setting('mock_menu_'+str(ADMIN),'admin')
   return await m.answer('MOCK testlar boshqaruvi. Pastki menyudan amalni tanlang.',reply_markup=mock_admin_reply_kb())
  if txt=='Yangi MOCK test':
   mock_wizard_write({});ast('mock_code')
   return await m.answer('Yangi MOCK test uchun test kodini kiriting. Qatnashchilar shu kod orqali Mini App’da kiradi. Bekor qilish: /cancel')
  if txt=='MOCK testlar ro‘yxati':
   body,markup=mock_listing()
   return await m.answer(body,reply_markup=markup)
  mock_actions={'MOCK ishtirokchilari':'mock_participants','MOCK natijalari':'mock_rounds','MOCK testni boshlash':'mock_start','MOCK vaqt qo‘shish':'mock_extend','MOCK testni to‘xtatish':'mock_stop','MOCK qayta o‘tkazish':'mock_restart','MOCK boshlanish vaqti':'mock_schedule','MOCK qatnashchi limiti':'mock_limit','MOCK javoblarni tekshirish':'mock_preflight'}
  if txt in mock_actions:
   tests=[dict(t) for t in db.all_tests() if int(t['is_mock'] or 0) and int(t['code_set'] or 0)]
   if not tests:return await m.answer('Hali MOCK test yo‘q. Yangi MOCK test yarating.',reply_markup=mock_admin_reply_kb())
   action=mock_actions[txt]
   rows=[[InlineKeyboardButton(text=str(t['name'])[:35]+' · '+str(t['code'])[:14],callback_data=f"{action}:{t['test_id']}",style='primary')] for t in tests[:40]]
   return await m.answer(txt+' uchun testni tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
  if txt=='Orqaga qaytish':
   db.set_setting('mock_menu_'+str(ADMIN),'')
   return await m.answer('Admin boshqaruv menyusi. Test sozlamalari va Statistika shu yerda.',reply_markup=core.admin_kb())
  if s.startswith('check_written:'):
   try:
    _,tid,fake_id,index=s.split(':');fake_id=int(fake_id);index=int(index)
    a=db.get_attempt(tid,fake_id);qs=db.questions_for_test(tid)
    if not a or index>=len(qs):raise ValueError()
    answers=json.loads(a['answers_json'] or '{}');answers[str(qs[index]['number'])]=txt
    db.update_attempt(a['attempt_id'],answers_json=json.dumps(answers,ensure_ascii=False));ast('admin')
    return await check_prompt(tid,fake_id,index+1)
   except Exception:return await m.answer('Tekshirish javobi saqlanmadi. Tekshirishni qaytadan boshlang.')
  if txt in {'/statistika','Statistika'}:
   users=db.all_registered_users()
   tests=db.all_tests()
   attempts=[attempt for t in tests for attempt in db.all_attempts_for_test(t['test_id'])]
   groups=json.loads(db.get_setting('known_groups','[]') or '[]')
   lines=[
    'BOT STATISTIKASI','',
    f"Foydalanuvchilar: {len(users)}",
    f"Testlar: {len(tests)}",
    f"Urinishlar: {len(attempts)}",
    f"Yakunlangan testlar: {sum(1 for attempt in attempts if attempt['submitted'])}",
    f"Guruhlar: {len(groups)}",
    'Vaqt zonasi: Asia/Tashkent'
   ]
   return await m.answer('\n'.join(lines),reply_markup=CORE.admin_kb())
  if txt=='Guruhlar holati':
   text,kb=await group_admin_page()
   return await m.answer(text,parse_mode='HTML',reply_markup=kb)
  if txt=='Majburiy obuna':
   ast('admin')
   return await m.answer(subscription_admin_text(),reply_markup=subscription_admin_kb())
  if s=='subscription_channels':
   command=txt.strip().upper()
   if command=='OFF':
    db.set_setting('subscription_required','0');CORE.SUB_CACHE.clear();ast('admin')
    return await m.answer('Majburiy obuna vaqtincha o‘chirildi. Kanal ro‘yxati saqlanib qoldi.')
   if command=='CLEAR':
    db.set_setting('subscription_channels','[]');db.set_setting('subscription_required','0');CORE.SUB_CACHE.clear();ast('admin')
    return await m.answer('Kanallar tozalandi. Majburiy obuna o‘chirildi.')
   if command=='ON':
    channels=CORE.sub_channels()
    if not channels:return await m.answer('Avval kamida bitta kanal kiriting.')
   else:
    import re
    channels=list(dict.fromkeys(part.strip() for part in re.split(r'[,\n]+',txt) if part.strip()))
    invalid=[ch for ch in channels if not re.fullmatch(r'@[A-Za-z0-9_]{5,32}|-100\d{8,16}',ch)]
    if invalid:return await m.answer('Noto‘g‘ri kanal: '+', '.join(invalid[:5])+'\nMasalan: @kanalnomi yoki -1001234567890')
   failed,links=await validate_subscription_channels(channels)
   if failed:return await m.answer('Obuna yoqilmadi. Botni kanallarga admin qilib qo‘shing va taklif havolasi ruxsatini bering:\n'+'\n'.join(failed[:10]))
   db.set_setting('subscription_invite_links',json.dumps(links,ensure_ascii=False))
   db.set_setting('subscription_channels',json.dumps(channels,ensure_ascii=False))
   db.set_setting('subscription_required','1');CORE.SUB_CACHE.clear();ast('admin')
   return await m.answer(subscription_admin_text(),reply_markup=subscription_admin_kb())
  if s.startswith('paid_select:'):
   if txt=='BEKOR QILISH' or txt=='/cancel':
    ast('admin')
    return await m.answer('Qatnashchi tanlash bekor qilindi.',reply_markup=ReplyKeyboardRemove())
   if txt=='CHAT ID NI QO‘LDA KIRITISH':
    tid=s.split(':')[1]
    ast('paid_manual:'+tid)
    await m.answer('Tanlash oynasi yopildi.',reply_markup=ReplyKeyboardRemove())
    return await m.answer('Telegram chat ID raqamini yuboring. Bekor qilish: /cancel.')
   return await m.answer('«FOYDALANUVCHINI TANLASH» tugmasidan foydalaning yoki CHAT ID NI QO‘LDA KIRITISH ni tanlang.')
  if s.startswith('paid_manual:'):
   if txt=='/cancel' or txt=='BEKOR QILISH':
    ast('admin')
    return await m.answer('Bekor qilindi.',reply_markup=CORE.admin_kb())
   tid=s.split(':',1)[1]
   if not db.is_paid_test(tid):
    ast('admin');return await m.answer('Pulli test topilmadi.')
   try:target=int(txt)
   except (TypeError,ValueError):
    return await m.answer('Chat ID faqat raqam bo‘lishi kerak.')
   if target<=0:return await m.answer('Musbat Telegram chat ID yuboring.')
   user=db.get_user(target)
   if not user:return await m.answer('Bu foydalanuvchi botda /start bosmagan. Avval ro‘yxatdan o‘tsin.')
   ast('paid_confirm:'+tid+':'+str(target))
   buttons=InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='HA, TESTGA QO‘SHISH',callback_data='paid_ok:'+tid+':'+str(target),style='success')],
    [InlineKeyboardButton(text='BEKOR QILISH',callback_data='paid_cancel:'+tid)]])
   return await m.answer('<b>QATNASHCHINI TASDIQLASH</b>\n\n'
      +escape(str(user['full_name'] or 'Ismsiz'))
      +'\nID: <code>'+str(target)+'</code>\n\n'
      'Ushbu odamga pulli test ruxsati berilsinmi?',
      parse_mode='HTML',reply_markup=buttons)
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
   db.set_setting('pending_notification',json.dumps({'text':txt,'source_chat_id':m.chat.id,'source_message_id':m.message_id},ensure_ascii=False));ast('notification_confirm')
   keyboard=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='YUBORISH',callback_data='notification_send',style='success'),InlineKeyboardButton(text='BEKOR QILISH',callback_data='notification_cancel',style='danger')]])
   await m.answer('XABAR NAMUNASI — premium emoji va format saqlanadi. Yuborishni quyidagi xabardan tasdiqlang:')
   return await BOT.copy_message(chat_id=m.chat.id,from_chat_id=m.chat.id,message_id=m.message_id,reply_markup=keyboard)
  if txt=='Ishtirokchilar':
   from html import escape as html_escape
   users=db.all_registered_users()
   if not users:return await m.answer('Hozircha foydalanuvchilar yo‘q.')
   lines=['<b>FOYDALANUVCHILAR RO‘YXATI</b>','Ism ustiga bosing — Telegram profili ochiladi.','']
   for i,user in enumerate(users[:60],1):
    name=html_escape(str(user['full_name'] or '').strip() or 'Ismsiz')
    uid=int(user['telegram_id'])
    username=str(db.get_setting('telegram_username_'+str(uid),'') or '').strip().lstrip('@')
    if uid>0:
     link=('https://t.me/'+username if username and username.replace('_','').isalnum() else 'tg://user?id='+str(uid))
     name='<a href="'+html_escape(link,quote=True)+'">'+name+'</a>'
    row=f"{i}. {name}\n   ID: {uid}"
    if sum(len(x) for x in lines)+len(row)>3550:break
    lines.append(row)
   return await m.answer('\n\n'.join(lines),parse_mode='HTML',disable_web_page_preview=True)
  if txt=='Guruhga xabar yuborish':
   ast('admin')
   text,kb=await group_admin_page()
   return await m.answer(text,parse_mode='HTML',reply_markup=kb)
  if s=='broadcast_message':
   if not txt:return await m.answer("Xabar bo‘sh bo‘lmasin. Matnni qayta yuboring.")
   db.set_setting('pending_broadcast',json.dumps({'text':txt},ensure_ascii=False));ast('broadcast_confirm')
   return await m.answer(f"XABAR NAMUNASI\n\n{txt[:2500]}\n\nBarcha ro‘yxatdagi guruhlarga yuborilsinmi?",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='YUBORISH',callback_data='broadcast_send'),InlineKeyboardButton(text='BEKOR QILISH',callback_data='broadcast_cancel')]]))
  if txt=='Ish vaqti jadvali':
   current=db.get_setting('awake_window','08:00-22:00');ast('awake_window')
   return await m.answer(f"Toshkent vaqti bilan HH:MM-HH:MM ko‘rinishida kiriting. Hozirgi sozlama: {current}.\nEslatma: Render bepul xizmat uyquga ketgan bo‘lsa, bot ichidagi jadvalning o‘zi uni uyg‘ota olmaydi; tashqi uptime monitor kerak bo‘ladi.")
  if s=='awake_window':
   import re
   if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d',txt):return await m.answer("Format noto‘g‘ri. Masalan: 07:30-23:00")
   db.set_setting('awake_window',txt);ast('admin')
   return await m.answer(f"Jadval saqlandi: {txt} (Asia/Tashkent). Uyqudagi Render instansiyasini tashqaridan uyg‘otmaydi.")
  if txt in {'Test sozlamalari','Ishtirokchilar'}:return await m.answer('TESTLAR — saqlangan testlar',reply_markup=tests_kb())
  if s=='new_code':
   if not txt or ' ' in txt:return await m.answer('Kodni bitta so‘z qilib kiriting. Masalan: MAT2026')
   if db.test_code_exists(txt):return await m.answer('Bu kod avval ishlatilgan. Boshqa kod tanlang.')
   old_d=draft();save_draft({'code':txt,'paid':bool(old_d.get('paid'))});ast('new_name')
   return await m.answer('Test nomini kiriting:')
  if s=='new_name':
   if not txt:return await m.answer('Test nomini kiriting:')
   d=draft();d['name']=txt;save_draft(d);ast('new_count');return await m.answer('Testda jami nechta savol bo‘ladi? (1–200)')
  if s=='new_count':
   try:n=int(txt);assert 1<=n<=200
   except:return await m.answer('Savollar sonini 1 dan 200 gacha butun son bilan kiriting.')
   d=draft();d['count']=n;d['items']=[];save_draft(d);ast('new_kind')
   return await m.answer(f'1/{n}-savol turini tanlang:',reply_markup=new_question_type_kb(paid=bool(d.get('paid'))))
  if s=='new_multi_count':
   try:n=int(txt);assert 2<=n<=20
   except:return await m.answer('2 dan 20 gacha kichik savol sonini kiriting.')
   d=draft();d['multi_total']=n;d['multi_items']=[];save_draft(d);ast('new_multi_kind')
   return await m.answer('1/'+str(n)+' kichik savol turini tanlang:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='A/B/C/D',callback_data='t_multi_kind:choice')],[InlineKeyboardButton(text='Yozma',callback_data='t_multi_kind:written')]]))
  if s=='new_multi_written':
   if not txt.strip():return await m.answer('To‘g‘ri javobni kiriting:')
   return await complete_multi_part(m,'written',txt)
  if s.startswith('paid_add_question:'):
   _,tid,kind=s.split(':',2)
   d=draft()
   if not db.is_paid_test(tid) or d.get('test_id')!=tid:return await m.answer('Test sessiyasi eskirgan.')
   if not txt or len(txt)>1500:return await m.answer('Savol matni 1 dan 1500 belgigacha bo‘lsin.')
   d['question']=txt;save_draft(d)
   if kind=='choice':
    ast('paid_add_options:'+tid)
    return await m.answer('4 ta variant matnini yuboring:\n<code>1 | 2 | 3 | 4</code>\n'
       'Faqat A/B/C/D bo‘lsa <code>SKIP</code> deb yuboring.',parse_mode='HTML')
   ast('paid_add_written_answer:'+tid)
   return await m.answer('Yozma savolning to‘g‘ri javobini yuboring.')
  if s.startswith('paid_add_options:'):
   tid=s.split(':',1)[1];d=draft()
   if not db.is_paid_test(tid) or d.get('test_id')!=tid or not d.get('question'):
    return await m.answer('Savol sessiyasi eskirgan.')
   options=['A','B','C','D'] if txt.upper()=='SKIP' else [x.strip() for x in txt.split('|')]
   if len(options)!=4 or not all(options) or any(len(o)>400 for o in options):
    return await m.answer('4 ta variantni yuboring: <code>A | B | C | D</code>',parse_mode='HTML')
   d['options']=options;save_draft(d);ast('paid_add_choice_answer:'+tid)
   return await m.answer('To‘g‘ri A/B/C/D variantini tanlang:',reply_markup=InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text=k,callback_data='paid_qanswer:'+tid+':'+k,style='primary') for k in 'ABCD']]))
  if s.startswith('paid_add_written_answer:'):
   tid=s.split(':',1)[1];d=draft()
   if not db.is_paid_test(tid) or d.get('test_id')!=tid or not d.get('question'):
    return await m.answer('Savol sessiyasi eskirgan.')
   if not txt:return await m.answer('To‘g‘ri yozma javobni kiriting.')
   n=max((int(x['number']) for x in db.questions_for_test(tid)),default=0)+1
   db.upsert_test_question(tid,n,d['question'],[],txt,'written')
   clear_draft();ast('admin')
   return await m.answer(f'<b>{n}-SAVOL SAQLANDI</b>\nTur: Yozma javob',
     parse_mode='HTML',reply_markup=paid_test_kb(tid))
  if s=='paid_new_question':
   d=draft()
   if not d.get('paid') or not d.get('current_kind'):return await m.answer('Yangi pulli test sessiyasi topilmadi.')
   if not txt or len(txt)>1500:return await m.answer('Savol matni 1–1500 belgidan iborat bo‘lsin.')
   d['current_question']=txt;save_draft(d)
   if d['current_kind']=='choice':
    ast('paid_new_options')
    return await m.answer('A/B/C/D variantlari matnini <b>bir qatorda</b> yuboring:\n'
     '<code>12 | 13 | 14 | 15</code>\n'
     'Agar variantlarning o‘zi A/B/C/D bo‘lsa, <code>SKIP</code> yuboring.',parse_mode='HTML')
   ast('new_written_answer')
   return await m.answer('To‘g‘ri yozma javobni yuboring:')
  if s=='paid_new_options':
   d=draft()
   if not d.get('paid') or not d.get('current_question'):return await m.answer('Savol sessiyasi eskirgan.')
   if txt.strip().upper()=='SKIP':options=['A','B','C','D']
   else:options=[part.strip() for part in txt.split('|')]
   if len(options)!=4 or not all(options) or any(len(p)>400 for p in options):
    return await m.answer('To‘rtta variant kiriting. Misol: <code>1 | 2 | 3 | 4</code>',parse_mode='HTML')
   d['current_options']=options;save_draft(d);ast('new_answer')
   return await m.answer('To‘g‘ri javob qaysi variant? A, B, C yoki D ni tanlang:',
    reply_markup=new_answer_kb())
  if s=='new_written_answer':
   if not txt:return await m.answer('Yozma javob bo‘sh bo‘lmasin. To‘g‘ri javobni kiriting:')
   d=draft()
   item={'kind':'written','answer':txt}
   if d.get('paid'):
    if not d.get('current_question'):return await m.answer('Avval savol matnini kiriting.')
    item['question']=d.pop('current_question')
   d.setdefault('items',[]).append(item);save_draft(d);done=len(d['items']);total=int(d['count'])
   if done<total:
    ast('new_kind');return await m.answer(f'{done+1}/{total}-savol turini tanlang:',reply_markup=new_question_type_kb(paid=bool(d.get('paid'))))
   try:
    if len(d['items'])!=total:return await m.answer('Savollar to‘liq emas. Test hali saqlanmadi.')
    t=db.create_test_with_questions(d['name'],d['code'],d['items'],paid=bool(d.get('paid')));clear_draft();ast('admin')
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
  await q.message.answer(f"TEKSHIRISH AKKAUNTI YARATILDI\nLogin: {fake_name}\nTest: {t['name']}\nKod: {t['code']}\n\nEndi har bir savolga javob berib test oqimini tekshirishingiz mumkin.")
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
  item={'kind':'choice','answer':letter}
  if d.get('paid'):
   if not d.get('current_question') or not d.get('current_options'):
    return await q.answer('Savol matni va A/B/C/D variantlari kiritilmagan.',show_alert=True)
   item['question']=d['current_question']
   item['options']=d['current_options']
  d.setdefault('items',[]).append(item)
  d.pop('current_question',None);d.pop('current_options',None)
  save_draft(d)
  done=len(d['items']);total=int(d['count'])
  if done<total:
   ast('new_kind');await q.message.answer(f'{done+1}/{total}-savol turini tanlang:',reply_markup=new_question_type_kb(paid=bool(d.get('paid'))))
   return await q.answer(f'{done}/{total} saqlandi')
  try:
   if db.test_code_exists(d['code']):return await q.answer('Bu kod avval ishlatilgan. Boshqa kod tanlang.',show_alert=True)
   if len(d['items'])!=total:return await q.answer('Barcha savollar tugallanmagan. Test saqlanmadi.',show_alert=True)
   t=db.create_test_with_questions(d['name'],d['code'],d['items'],paid=bool(d.get('paid')))
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
  if d.get('paid'):
   if kind not in ('choice','written'):return await q.answer('Savol turi noto‘g‘ri.',show_alert=True)
   ast('paid_new_question')
   await q.message.answer(f'<b>{number}/{total}-SAVOL</b>\n\nSavol matnini yuboring. Bu matn Mini App’da o‘quvchilarga ko‘rinadi.',parse_mode='HTML')
   return await q.answer()
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
  tid=q.data.split(':',1)[1]
  if db.is_paid_test(tid):
   save_draft({'test_id':tid,'kind':'choice'})
   ast('paid_add_question:'+tid+':choice')
   await q.message.answer('<b>YANGI SAVOL</b>\n\nVariantli savol matnini yuboring.',parse_mode='HTML')
   return await q.answer()
  clear_draft();ast('choice_num:'+tid);await q.message.answer('Faqat savol raqamini kiriting. Masalan: 1');await q.answer()
 @r.callback_query(F.data.startswith('t_written:'))
 async def tw(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1]
  if db.is_paid_test(tid):
   save_draft({'test_id':tid,'kind':'written'})
   ast('paid_add_question:'+tid+':written')
   await q.message.answer('<b>YANGI SAVOL</b>\n\nYozma savol matnini yuboring.',parse_mode='HTML')
   return await q.answer()
  clear_draft();ast('written_num:'+tid);await q.message.answer('Faqat savol raqamini kiriting. Masalan: 1');await q.answer()
 @r.callback_query(F.data.startswith('t_ans:'))
 async def tans(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  _,tid,n,letter=q.data.split(':');d=draft()
  if d.get('test_id')!=tid or int(d.get('number',-1))!=int(n):return await q.answer('Savol sessiyasi eskirgan.',show_alert=True)
  db.upsert_test_question(tid,int(n),'',['A','B','C','D'],letter,'choice');clear_draft();ast('admin');await q.message.answer(f'{n}-savol saqlandi. To‘g‘ri javob: {letter}',reply_markup=test_kb(tid));await q.answer('Saqlandi')
 @r.callback_query(F.data.startswith('paid_qanswer:'))
 async def paid_save_answer(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q.',show_alert=True)
  try:_,tid,letter=q.data.split(':',2)
  except ValueError:return await q.answer('Noto‘g‘ri so‘rov.',show_alert=True)
  d=draft()
  u=db.get_user(ADMIN)
  if (not u or u['state']!='paid_add_choice_answer:'+tid or
      not db.is_paid_test(tid) or d.get('test_id')!=tid or
      not d.get('question') or not d.get('options') or letter not in 'ABCD'):
   return await q.answer('Savol sessiyasi eskirgan.',show_alert=True)
  n=max((int(x['number']) for x in db.questions_for_test(tid)),default=0)+1
  db.upsert_test_question(tid,n,d['question'],d['options'],letter,'choice')
  clear_draft();ast('admin')
  await q.message.answer(f'<b>{n}-SAVOL SAQLANDI</b>\nTur: A/B/C/D\nTo‘g‘ri javob: <b>{letter}</b>',
   parse_mode='HTML',reply_markup=paid_test_kb(tid))
  await q.answer('Savol saqlandi')

 @r.callback_query(F.data=='mock_new')
 async def mock_new_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  mock_wizard_write({});ast('mock_code')
  await q.message.answer('Yangi MOCK test uchun test kodini kiriting. Bu kodni qatnashchilar Mini Appdagi “Test kodini kiritish” orqali yozadi. Bekor qilish: /cancel')
  await q.answer()
 @r.callback_query(F.data=='mock_list')
 async def mock_list_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  body,markup=mock_listing()
  await q.message.answer(body,reply_markup=markup);await q.answer()
 @r.callback_query(F.data.startswith('mock_start:'))
 async def mock_start_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  test_id=q.data.split(':',1)[1];result=await start_mock_test_session(test_id)
  if not result.get('ok'):return await q.answer(result.get('message') or 'Testni boshlash imkoni bo‘lmadi.',show_alert=True)
  await q.message.answer(result['message'],reply_markup=mock_ready_kb(test_id));await q.answer('Taymer boshlandi.')


 @r.callback_query(F.data.startswith('mock_preflight:'))
 async def mock_preflight_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  tid=q.data.split(':',1)[1];test=db.get_test(tid)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  issues=mock_key_check(tid)
  await q.message.answer(f"{test['name']} · JAVOBLAR TEKSHIRUVI\n"+('\n'.join(issues[:30]) if issues else f"Xatolik topilmadi. {len(db.questions_for_test(tid))} ta savol va javob kaliti tayyor."),reply_markup=mock_admin_reply_kb())
  await q.answer()
 @r.callback_query(F.data.startswith('mock_schedule:'))
 async def mock_schedule_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  tid=q.data.split(':',1)[1];test=db.get_test(tid)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  if test['timer_started_at']:return await q.answer('Test boshlangan. Jadvalni o‘zgartirib bo‘lmaydi.',show_alert=True)
  ast('mock_schedule:'+tid)
  await q.message.answer(f"{test['name']} uchun boshlanish sanasini Toshkent vaqti bilan kiriting.\nFormat: kun/oy/yil soat:daqiqa (masalan: 12/11/2026 14:30).\nBekor qilish: OFF",reply_markup=mock_admin_reply_kb())
  await q.answer()
 @r.callback_query(F.data.startswith('mock_limit:'))
 async def mock_limit_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  tid=q.data.split(':',1)[1];test=db.get_test(tid)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  ast('mock_limit:'+tid)
  await q.message.answer(f"{test['name']} uchun qatnashchilar chegarasini son bilan kiriting. 0 — cheklanmagan. Hozir: {int(test['participant_limit'] or 0)}",reply_markup=mock_admin_reply_kb())
  await q.answer()
 @r.callback_query(F.data.startswith('mock_participants:'))
 async def mock_participants_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  parts=q.data.split(':')
  tid=parts[1];page=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 0
  test=db.get_test(tid)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  rows=mock_participant_rows(tid);size=20;page=min(page,max(0,(len(rows)-1)//size))
  lines=[f"<b>{html_escape(str(test['name']))} · ISHTIROKCHILAR</b>",f"Jami urinishlar: {len(rows)} · Sahifa: {page+1}",'Ism ustiga bosing — Telegram profili ochiladi.','']
  buttons=[]
  for index,a in enumerate(rows[page*size:(page+1)*size],page*size+1):
   uid=int(a['telegram_id']);name=str(a.get('full_name') or a.get('participant_name') or 'Ismsiz')
   username=str(db.get_setting('telegram_username_'+str(uid),'') or '').strip().lstrip('@')
   link=('https://t.me/'+username if username and username.replace('_','').isalnum() else 'tg://user?id='+str(uid)) if uid>0 else ''
   status=f"{float(a.get('score') or 0):.2f} ball" if int(a['submitted'] or 0) else 'Ishlamoqda'
   display=f'<a href="{html_escape(link,quote=True)}">{html_escape(name)}</a>' if link else html_escape(name)
   lines.append(f'{index}. {display} · {status}')
   if int(a['submitted'] or 0):buttons.append([InlineKeyboardButton(text=f'SHAXSIY PDF · {index}. {name[:20]}',callback_data=f'mock_personal:{tid}:{uid}',style='primary')])
  if not rows:lines.append('Hali ishtirokchi yo‘q.')
  nav=[]
  if page:nav.append(InlineKeyboardButton(text='OLDINGI',callback_data=f'mock_participants:{tid}:{page-1}'))
  if (page+1)*size<len(rows):nav.append(InlineKeyboardButton(text='KEYINGI',callback_data=f'mock_participants:{tid}:{page+1}'))
  if nav:buttons.append(nav)
  buttons.append([InlineKeyboardButton(text='MOCK TESTLAR RO‘YXATI',callback_data='mock_list')])
  await q.message.answer('\n'.join(lines),parse_mode='HTML',disable_web_page_preview=True,reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons));await q.answer()
 @r.callback_query(F.data.startswith('mock_personal:'))
 async def mock_personal_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  try:_,tid,uid=q.data.split(':');uid=int(uid)
  except (ValueError,TypeError):return await q.answer('Noto‘g‘ri so‘rov.',show_alert=True)
  test=db.get_test(tid)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  await q.answer('Shaxsiy PDF tayyorlanmoqda…')
  await send_mock_personal_result(ADMIN,uid,tid)

 @r.callback_query(F.data.startswith('mock_extend:'))
 async def mock_extend_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  tid=q.data.split(':',1)[1];test=db.get_test(tid)
  if not test or not int(test['is_mock'] or 0) or not int(test['active'] or 0) or not (mock_remaining_seconds(dict(test)) or 0)>0:
   return await q.answer('Faol MOCK test topilmadi.',show_alert=True)
  kb=InlineKeyboardMarkup(inline_keyboard=[
   [InlineKeyboardButton(text=f'+{minutes} DAQIQA',callback_data=f'mock_extend_add:{tid}:{minutes}',style='primary') for minutes in (5,10)],
   [InlineKeyboardButton(text=f'+{minutes} DAQIQA',callback_data=f'mock_extend_add:{tid}:{minutes}',style='primary') for minutes in (20,30)],
   [InlineKeyboardButton(text='ORTGA QAYTISH',callback_data='mock_list')]
  ])
  await q.message.answer(f"{test['name']} · Qolgan vaqt: {format_mock_timer(mock_remaining_seconds(dict(test)))}\nQancha vaqt qo‘shilsin?",reply_markup=kb);await q.answer()
 @r.callback_query(F.data.startswith('mock_extend_add:'))
 async def mock_extend_add_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  try:_,tid,minutes=q.data.split(':');minutes=int(minutes)
  except (ValueError,TypeError):return await q.answer('Noto‘g‘ri so‘rov.',show_alert=True)
  if minutes not in (5,10,20,30):return await q.answer('Noto‘g‘ri vaqt.',show_alert=True)
  test=db.get_test(tid)
  if not test or not int(test['is_mock'] or 0) or not int(test['active'] or 0) or not (mock_remaining_seconds(dict(test)) or 0)>0:
   return await q.answer('Test yakunlangan.',show_alert=True)
  old=str(test['timer_ends_at'])
  new=(datetime.fromisoformat(old.replace('Z','+00:00'))+timedelta(minutes=minutes)).isoformat()
  if not db.extend_mock_timer(tid,old,new):return await q.answer('Vaqt o‘zgargan. Qaytadan oching.',show_alert=True)
  updated=dict(db.get_test(tid))
  await q.answer(f'{minutes} daqiqa qo‘shildi.')
  await q.message.answer(f"{test['name']} · +{minutes} daqiqa\nQolgan vaqt: {format_mock_timer(mock_remaining_seconds(updated))}",reply_markup=mock_ready_kb(tid))
 @r.callback_query(F.data.startswith('mock_rounds:'))
 async def mock_rounds_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  tid=q.data.split(':',1)[1];test=db.get_test(tid)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  rounds=[dict(row) for row in db.mock_rounds_for_test(tid)]
  lines=[f"{test['name']} · O‘TKAZILGAN TURLAR"];buttons=[]
  for number,row in enumerate(rounds,1):
   count=len(db.results_for_mock_round(tid,row['round_id']) or [])
   status='yakunlangan' if row.get('closed_at') else 'davom etmoqda'
   lines.append(f"{number}-tur · {str(row['started_at'])[:16].replace('T',' ')} · {status} · {count} natija")
   buttons.append([InlineKeyboardButton(text=f'{number}-TUR · {count} NATIJA',callback_data=f"mock_round:{tid}:{row['round_id']}",style='primary')])
  old=db.results_for_mock_round(tid,'old') or []
  if old:
   lines.append(f'Avvalgi natijalar · turi aniqlanmagan · {len(old)} natija')
   buttons.append([InlineKeyboardButton(text=f'AVVALGI NATIJALAR · {len(old)}',callback_data=f'mock_round:{tid}:old',style='primary')])
  if not rounds and not old:lines.append('Hali o‘tkazilgan tur va natija yo‘q.')
  buttons.append([InlineKeyboardButton(text='ORTGA QAYTISH',callback_data='mock_list')])
  await q.message.answer('\n'.join(lines),reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons));await q.answer()
 @r.callback_query(F.data.startswith('mock_round:'))
 async def mock_round_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  _,tid,rid=q.data.split(':',2);test=db.get_test(tid)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  rows=db.results_for_mock_round(tid,rid)
  if rows is None:return await q.answer('Tur topilmadi.',show_alert=True)
  rounds=[dict(row) for row in db.mock_rounds_for_test(tid)]
  label='Avvalgi natijalar' if rid=='old' else f"{next((i for i,r in enumerate(rounds,1) if r['round_id']==rid),0)}-tur"
  kb=InlineKeyboardMarkup(inline_keyboard=[
   [InlineKeyboardButton(text='PDF',callback_data=f'mock_export:{tid}:{rid}:pdf',style='primary'),InlineKeyboardButton(text='EXCEL',callback_data=f'mock_export:{tid}:{rid}:xlsx',style='primary')],
   [InlineKeyboardButton(text='SAVOLLAR TAHLILI',callback_data=f'mock_analyze:{tid}:{rid}',style='primary')],
   [InlineKeyboardButton(text='ORTGA QAYTISH',callback_data=f'mock_rounds:{tid}')]
  ])
  await q.message.answer(f"{test['name']} · {label}\nNatijalar: {len(rows)}",reply_markup=kb);await q.answer()
 @r.callback_query(F.data.startswith('mock_export:'))
 async def mock_export_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  try:_,tid,rid,kind=q.data.split(':')
  except ValueError:return await q.answer('Noto‘g‘ri so‘rov.',show_alert=True)
  test=db.get_test(tid);rows=db.results_for_mock_round(tid,rid) if test and int(test['is_mock'] or 0) else None
  if rows is None or kind not in ('pdf','xlsx'):return await q.answer('Tur topilmadi.',show_alert=True)
  if not rows:return await q.answer('Bu turda hali natija yo‘q.',show_alert=True)
  rounds=[dict(row) for row in db.mock_rounds_for_test(tid)]
  number=next((i for i,r in enumerate(rounds,1) if r['round_id']==rid),0)
  label='Avvalgi natijalar' if rid=='old' else f'{number}-tur'
  await q.answer('Hisobot tayyorlanmoqda…')
  path=''
  try:
   with tempfile.NamedTemporaryFile(prefix='nur-mock-round-',suffix='.'+kind,delete=False) as tmp:path=tmp.name
   if kind=='pdf':build_test_pdf(tid,path,selected_rows=rows,round_label=label)
   else:build_mock_round_xlsx(tid,label,rows,path)
   code=''.join(x for x in str(test['code'] or 'MOCK') if x.isalnum() or x in '-_')[:32] or 'MOCK'
   await BOT.send_document(ADMIN,FSInputFile(path,filename=f'{code}-{rid}-{label.replace(" ","-")}.{kind}'),caption=f"{test['name']} · {label} · {len(rows)} qatnashchi")
  except Exception:
   logging.getLogger('nur-oqiw.mock').exception('MOCK round export failed')
   await BOT.send_message(ADMIN,'Hisobot tayyorlashda xatolik yuz berdi. Keyinroq qayta urinib ko‘ring.')
  finally:
   if path:
    try:os.remove(path)
    except OSError:pass
 @r.callback_query(F.data.startswith('mock_analyze:'))
 async def mock_analyze_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  _,tid,rid=q.data.split(':',2);test=db.get_test(tid)
  rows=db.results_for_mock_round(tid,rid) if test and int(test['is_mock'] or 0) else None
  if rows is None:return await q.answer('Tur topilmadi.',show_alert=True)
  if not rows:return await q.answer('Bu turda hali natija yo‘q.',show_alert=True)
  await q.answer('Tahlil tayyorlanmoqda…')
  lines=mock_round_analysis(tid,rows);chunk=''
  for line in lines:
   if len(chunk)+len(line)>3500:
    await BOT.send_message(ADMIN,chunk);chunk=''
   chunk+=line+'\n\n'
  if chunk:await BOT.send_message(ADMIN,chunk)

 @r.callback_query(F.data.startswith('mock_stop:'))
 async def mock_stop_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  test_id=q.data.split(':',1)[1];test=db.get_test(test_id)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='HA, TO‘XTATISH VA HISOBLASH',callback_data=f'mock_stop_yes:{test_id}',style='danger')],[InlineKeyboardButton(text='BEKOR QILISH',callback_data='mock_list')]])
  await q.message.answer(f"{test['name']} testini to‘xtatib, hozirgi urinishlarni hisoblaymi?",reply_markup=kb);await q.answer()
 @r.callback_query(F.data.startswith('mock_stop_yes:'))
 async def mock_stop_confirm_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  test_id=q.data.split(':',1)[1];test=db.get_test(test_id)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  await q.answer('Urinishlar hisoblanmoqda…')
  await finish_mock_test(test,'admin')
  await q.message.answer(f"{test['name']} test to‘xtatildi. Yakunlangan natijalarni PDF tugmasidan olasiz.",reply_markup=mock_ready_kb(test_id))
 @r.callback_query(F.data.startswith('mock_pdf:'))
 async def mock_pdf_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  test_id=q.data.split(':',1)[1];test=db.get_test(test_id)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  current=any(int(a['submitted'] or 0) for a in db.all_attempts_for_test(test_id))
  archived=any(int(a['submitted'] or 0) for a in db.permanent_results_for_test(test_id,5000))
  if not (current or archived):return await q.answer('Hali test natijasi yo‘q.',show_alert=True)
  await q.answer('Natijalar PDF’i tayyorlanmoqda…')
  ok=await send_mock_results_pdf(dict(test),force=True)
  if not ok:return await BOT.send_message(ADMIN,'PDF yuborilmadi. Bot logini tekshiring.')
 @r.callback_query(F.data.startswith('mock_restart:'))
 async def mock_restart_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  test_id=q.data.split(':',1)[1];test=db.get_test(test_id)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  if not int(test['code_set'] or 0) or not db.questions_for_test(test_id):return await q.answer('Test kodi yoki savollari tayyor emas.',show_alert=True)
  kb=InlineKeyboardMarkup(inline_keyboard=[
   [InlineKeyboardButton(text='HA, QAYTA OCHISH',callback_data=f'mock_restart_yes:{test_id}',style='success')],
   [InlineKeyboardButton(text='BEKOR QILISH',callback_data='mock_list')]
  ])
  await q.message.answer(f"{test['name']} testini qayta o‘tkazasizmi?\n\nEski natijalar arxivda saqlanadi. Tasdiqlansa, test kodi o‘zgarmaydi; yangi taymer esa TESTNI BOSHLASH tugmasi bosilganda boshlanadi.",reply_markup=kb)
  await q.answer()
 @r.callback_query(F.data.startswith('mock_restart_yes:'))
 async def mock_restart_confirm_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  test_id=q.data.split(':',1)[1];result=await restart_mock_test_session(test_id)
  if not result.get('ok'):return await q.answer(result.get('message') or 'Testni qayta ochib bo‘lmadi.',show_alert=True)
  await q.message.answer(result['message'],reply_markup=mock_ready_kb(test_id));await q.answer('Test qayta ochildi.')
 @r.callback_query(F.data.startswith('mock_continue:'))
 async def mock_continue_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  test_id=q.data.split(':',1)[1];test=db.get_test(test_id)
  if not test or not int(test['is_mock'] or 0):return await q.answer('MOCK test topilmadi.',show_alert=True)
  if test['timer_started_at'] or any(a['started_at'] for a in db.all_attempts_for_test(test_id)):return await q.answer('Test boshlangan; savollar o‘zgartirilmaydi.',show_alert=True)
  count=len(db.questions_for_test(test_id))+1
  pending={'test_id':str(test_id),'name':str(test['name']),'code':str(test['code']) if int(test['code_set'] or 0) else '', 'count':count,'duration_minutes':int(test['duration_minutes'] or 40)}
  mock_wizard_write(pending)
  if not pending['code']:
   ast('mock_code');await q.message.answer('Avval test kodini kiriting:');return await q.answer()
  ast('mock_question_kind')
  await q.message.answer(f"{count}/{count}-savol turini tanlang:",reply_markup=mock_question_type_kb());await q.answer()
 @r.callback_query(F.data.startswith('mock_kind:'))
 async def mock_kind_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  kind=q.data.rsplit(':',1)[-1];pending=mock_wizard_read();u=db.get_user(ADMIN)
  test=db.get_test(str(pending.get('test_id') or ''))
  if kind not in ('choice','written') or not test or not int(test['is_mock'] or 0) or not u or u['state']!='mock_question_kind':
   return await q.answer('Savol sessiyasi eskirgan.',show_alert=True)
  if test['timer_started_at']:return await q.answer('Test boshlangan; savollar o‘zgartirilmaydi.',show_alert=True)
  pending['current_kind']=kind;mock_wizard_write(pending)
  number=len(db.questions_for_test(test['test_id']))+1;total=int(pending.get('count') or 1)
  if kind=='choice':
   ast('mock_choice_answer');await q.message.answer(f'{number}/{total}-savol uchun to‘g‘ri A/B/C/D javobini tanlang:',reply_markup=mock_choice_answer_kb())
  else:
   ast('mock_written_answer');await q.message.answer(f'{number}/{total}-savolning to‘g‘ri yozma javobini yuboring:')
  await q.answer()
 @r.callback_query(F.data.startswith('mock_answer:'))
 async def mock_answer_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  letter=q.data.rsplit(':',1)[-1];pending=mock_wizard_read();u=db.get_user(ADMIN);test=db.get_test(str(pending.get('test_id') or ''))
  if letter not in {'A','B','C','D'} or not test or not u or u['state']!='mock_choice_answer' or pending.get('current_kind')!='choice':
   return await q.answer('Savol sessiyasi eskirgan.',show_alert=True)
  if test['timer_started_at']:return await q.answer('Test boshlangan; savollar o‘zgartirilmaydi.',show_alert=True)
  mock_save_question(str(test['test_id']),'choice',letter);pending.pop('current_kind',None);mock_wizard_write(pending)
  await q.answer('Javob saqlandi');await mock_next_question(q.message,pending)
 @r.callback_query(F.data.startswith('mock_publish:'))
 async def mock_publish_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  await q.answer('MOCK testlar Aktiv testlar ro‘yxatida chiqmaydi. Test kodini kiriting.',show_alert=True)
 @r.callback_query(F.data.startswith('mock_pdf:'))
 async def mock_pdf_removed_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  await q.answer('Savollar uchun alohida kanal yoki PDF talab qilinmaydi.',show_alert=True)
 @r.callback_query(F.data.startswith('mock_link:'))
 async def mock_link_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  test=db.get_test(q.data.split(':',1)[1])
  if not test or not int(test['is_mock'] or 0) or not int(test['code_set'] or 0):return await q.answer('MOCK test kodi topilmadi.',show_alert=True)
  try:me=await BOT.get_me();link=f"https://t.me/{me.username}?start={test['code']}"
  except Exception:return await q.answer('Bot havolasi olinmadi.',show_alert=True)
  await q.message.answer(f"{test['name']} · MOCK test\nKod: {test['code']}\nBot havolasi: {link}\n\nHavolani qatnashchilarga yoki kanalga yuboring.")
  await q.answer('Havola tayyor.')
 @r.callback_query(F.data=='mock_back')
 async def mock_back_callback(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator.',show_alert=True)
  db.update_user(ADMIN,state='admin');db.set_setting('mock_menu_'+str(ADMIN),'');await q.message.answer('Admin boshqaruv menyusi.',reply_markup=core.admin_kb());await q.answer()
 @r.callback_query(F.data.startswith('t_open:'))
 async def to(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];db.set_test_active(tid,1);t=db.get_test(tid)
  await q.message.edit_text(f"TEST QAYTA OCHILDI\n\n{t['name']}\nKod: {t['code']}",reply_markup=test_kb(tid));await q.answer('Test qayta ochildi')
 @r.callback_query(F.data.startswith('t_close:'))
 async def tx(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return
  tid=q.data.split(':',1)[1];t=db.get_test(tid)
  if not t:return await q.answer('Test topilmadi.',show_alert=True)
  db.set_test_active(tid,0)
  await q.message.edit_text(f"TEST VAQTINCHA YOPILDI\n\n{t['name']}\nKod: {t['code']}\nYakunlanmagan urinishlar va javoblar saqlandi. Qayta ochilganda davom ettirish mumkin.",reply_markup=test_kb(tid))
  await q.answer('Test yopildi; javoblar saqlandi')
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
  tid=q.data.split(':',1)[1];qs=db.questions_for_test(tid)
  if db.is_paid_test(tid):
   parts=['<b>PULLI TEST SAVOLLARI</b>','']
   for x in qs:
    summary=str(x['question'] or 'Savol')[:200]
    parts.append(f"<b>{x['number']}.</b> {escape(summary)}\nTo‘g‘ri javob: <code>{escape(str(x['answer']))}</code>")
   if not qs:parts.append('Savol yo‘q.')
   text='\n\n'.join(parts)[:3800]
   await q.message.edit_text(text,parse_mode='HTML',reply_markup=paid_test_kb(tid))
  else:
   text='SAVOLLAR\n\n'+('\n'.join(f"{x['number']}. To‘g‘ri javob: {x['answer']}" for x in qs) if qs else 'Savol yo‘q')
   await q.message.edit_text(text[:3900],reply_markup=test_kb(tid))
  await q.answer()
 @r.callback_query(F.data.startswith('t_archive_results'))
 async def archive_results(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Ruxsat yo‘q',show_alert=True)
  from html import escape as html_escape
  rows=db.all_permanent_results(200)
  try:page=max(0,int(q.data.split(':',1)[1])) if ':' in q.data else 0
  except (ValueError,IndexError):page=0
  page_count=max(1,(len(rows)+9)//10)
  page=min(page,page_count-1)
  body=['<b>UMUMIY REYTING ARXIVI</b>','Natija egasining ismiga bosing — Telegram profili ochiladi.','']
  for i,x in enumerate(rows[page*10:(page+1)*10],page*10+1):
   uid=int(x['telegram_id'] or 0)
   username=str(db.get_setting('telegram_username_'+str(uid),'') or '').strip().lstrip('@')
   safe_name=html_escape(str(x['full_name'] or 'Ismsiz'))
   if uid>0:
    address='https://t.me/'+username if username and username.replace('_','').isalnum() else 'tg://user?id='+str(uid)
    user_display='<a href="'+html_escape(address,quote=True)+'">'+safe_name+'</a>'
   else:user_display=safe_name
   status=(f"{float(x['score'] or 0):.2f} ball · {x['grade'] or '—'}" if x['submitted'] else 'Yakunlanmagan')
   when=str(x['finished_at'] or x['started_at'] or x['archived_at'] or '')[:16].replace('T',' ')
   details=html_escape(str(x['test_name'] or 'Test'))+' ['+html_escape(str(x['test_code'] or 'kod yo‘q'))+']'
   body.append(f"{i}. {user_display} · ID: {uid}\n{details} · {html_escape(status)} · {html_escape(when)}")
  if not rows:body.append('Hozircha saqlangan natijalar yo‘q.')
  nav=[]
  if page>0:nav.append(InlineKeyboardButton(text='Oldingi',callback_data=f't_archive_results:{page-1}'))
  if page+1<page_count:nav.append(InlineKeyboardButton(text='Keyingi',callback_data=f't_archive_results:{page+1}',style='primary'))
  kb=InlineKeyboardMarkup(inline_keyboard=([nav] if nav else [])+[[InlineKeyboardButton(text='Testlarga qaytish',callback_data='t_list')]])
  await q.message.edit_text('\n\n'.join(body),parse_mode='HTML',reply_markup=kb,disable_web_page_preview=True)
  await q.answer()
 @r.callback_query(F.data.startswith('subadmin:'))
 async def subscription_buttons(q:CallbackQuery):
  if q.from_user.id!=ADMIN:return await q.answer('Faqat administrator uchun.',show_alert=True)
  op=q.data.split(':',1)[1]
  if op=='edit':
   db.update_user(ADMIN,state='subscription_channels')
   await q.message.answer('Kanallarni yangi qatordan kiriting:\n@kanalnomi\n-1001234567890\n\nBot har bir kanalda administrator bo‘lishi kerak.')
  elif op=='off':
   db.set_setting('subscription_required','0');CORE.SUB_CACHE.clear();db.update_user(ADMIN,state='admin')
  elif op=='on':
   channels=CORE.sub_channels()
   if not channels:return await q.answer('Avval kanal qo‘shing.',show_alert=True)
   errors,links=await validate_subscription_channels(channels)
   if errors:return await q.answer('Obuna yoqilmadi: '+', '.join(errors[:2]),show_alert=True)
   db.set_setting('subscription_invite_links',json.dumps(links,ensure_ascii=False))
   db.set_setting('subscription_required','1');CORE.SUB_CACHE.clear();db.update_user(ADMIN,state='admin')
  elif op=='clear':
   kb=InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='HA, TOZALASH',callback_data='subadmin:confirm_clear',style='danger')],
    [InlineKeyboardButton(text='BEKOR QILISH',callback_data='subadmin:status')]])
   return await q.message.edit_text('Hamma kanallarni rostdan o‘chirasizmi?',reply_markup=kb)
  elif op=='confirm_clear':
   db.set_setting('subscription_channels','[]')
   db.set_setting('subscription_invite_links','{}')
   db.set_setting('subscription_required','0');CORE.SUB_CACHE.clear();db.update_user(ADMIN,state='admin')
  await q.message.edit_text(subscription_admin_text(),reply_markup=subscription_admin_kb())
  await q.answer()

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
  groups=CORE.known_groups()
  if not message:return await q.answer('Yuboriladigan xabar topilmadi.',show_alert=True)
  sent=0;failed=0
  for group in groups:
   try:
    await BOT.send_message(int(group['id']),message);sent+=1
   except Exception:
    failed+=1
  db.set_setting('pending_broadcast','{}');db.update_user(ADMIN,state='admin')
  await q.message.answer(f"GURUH XABARI YAKUNLANDI\nYuborildi: {sent}\nYuborilmadi: {failed}")
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
  pending=json.loads(db.get_setting('pending_notification','{}') or '{}')
  try:
   source_chat_id=int(pending['source_chat_id']);source_message_id=int(pending['source_message_id'])
  except (KeyError,TypeError,ValueError):
   return await q.answer('Eski xabarda premium emoji saqlanmagan. Bildirishnomani qayta yuboring.',show_alert=True)
  users=db.all_registered_users();sent=0;failed=0
  for user in users:
   uid=int(user['telegram_id'])
   if uid<=0 or uid==ADMIN:continue
   try:
    await BOT.copy_message(chat_id=uid,from_chat_id=source_chat_id,message_id=source_message_id)
    sent+=1
   except Exception:
    failed+=1
   if (sent+failed)%25==0:await asyncio.sleep(.2)
  db.set_setting('pending_notification','{}');db.update_user(ADMIN,state='admin')
  await q.message.answer(f"BILDIRISHNOMA YAKUNLANDI\nYuborildi: {sent}\nYuborilmadi: {failed}")
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
