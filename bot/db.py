import sqlite3,json
from pathlib import Path
from datetime import datetime,timezone
DB=Path(__file__).resolve().parent.parent/'data'/'app.db'; DB.parent.mkdir(exist_ok=True)
def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
 with conn() as c:c.executescript('''CREATE TABLE IF NOT EXISTS users(telegram_id INTEGER PRIMARY KEY,full_name TEXT,phone TEXT,registered_at TEXT,code_ok INTEGER DEFAULT 0,started_at TEXT,finished_at TEXT,score REAL DEFAULT 0,grade TEXT DEFAULT '',answers_json TEXT DEFAULT '{}',submitted INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY,question TEXT,options_json TEXT DEFAULT '[]',answer TEXT DEFAULT '',kind TEXT DEFAULT 'choice',group_id TEXT DEFAULT '',active INTEGER DEFAULT 1,image_url TEXT DEFAULT '');CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE IF NOT EXISTS item_stats(question_id INTEGER PRIMARY KEY,attempts INTEGER DEFAULT 0,correct INTEGER DEFAULT 0);''')
def get_setting(k,d=None):
 with conn() as c:r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone();return r['value'] if r else d
def set_setting(k,v):
 with conn() as c:c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,str(v)))
def get_user(t):
 with conn() as c:return c.execute('SELECT * FROM users WHERE telegram_id=?',(t,)).fetchone()
def upsert_user(t,name,phone=None):
 with conn() as c:c.execute('INSERT INTO users(telegram_id,full_name,phone,registered_at) VALUES(?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name,phone=COALESCE(excluded.phone,users.phone)',(t,name,phone,datetime.now(timezone.utc).isoformat()))
def set_code(t,v=1):
 with conn() as c:c.execute('UPDATE users SET code_ok=? WHERE telegram_id=?',(v,t))
def set_started(t,ts):
 with conn() as c:c.execute('UPDATE users SET started_at=? WHERE telegram_id=?',(ts,t))
def save_answers(t,a):
 with conn() as c:c.execute('UPDATE users SET answers_json=? WHERE telegram_id=?',(json.dumps(a,ensure_ascii=False),t))
def finish(t,score,grade,ts,a):
 with conn() as c:c.execute('UPDATE users SET finished_at=?,score=?,grade=?,answers_json=?,submitted=1 WHERE telegram_id=?',(ts,score,grade,json.dumps(a,ensure_ascii=False),t))
def all_users():
 with conn() as c:return c.execute('SELECT * FROM users WHERE code_ok=1 ORDER BY score DESC,full_name').fetchall()
def active_questions():
 with conn() as c:return c.execute('SELECT * FROM questions WHERE active=1 ORDER BY id').fetchall()
def replace_questions(items):
 with conn() as c:c.execute('DELETE FROM questions');c.executemany('INSERT INTO questions(id,question,options_json,answer,kind,group_id,image_url) VALUES(?,?,?,?,?,?,?)',items)
def record_stats(a):
 with conn() as c:
  for qid,ans in a.items():
   q=c.execute('SELECT answer FROM questions WHERE id=?',(int(qid),)).fetchone()
   if q:c.execute('INSERT INTO item_stats(question_id,attempts,correct) VALUES(?,?,?) ON CONFLICT(question_id) DO UPDATE SET attempts=attempts+1,correct=correct+excluded.correct',(int(qid),1,int(str(ans).strip().lower()==str(q['answer']).strip().lower())))
def seed():
 if active_questions():return
 data=[]
 for i in range(1,33):data.append((i,f'Sertifikat uslubidagi murakkab matematika savoli {i}. To‘g‘ri javobni toping.',json.dumps(['A','B','C','D']), 'A','choice','',''))
 data += [(33,'Shu rasmda to‘g‘ri to‘rtburchakning enini toping.',json.dumps(['6','8','10','12']),'8','choice','fig33',''),(34,'Shu rasmdagi perimetrni toping.',json.dumps(['32','36','40','44']),'40','choice','fig33',''),(35,'Shu rasmdagi yuzani toping.',json.dumps(['72','84','96','108']),'96','choice','fig33','')]
 for i in range(36,46):data.append((i,f'{i}. Yozma javobli sertifikat savoli.', '[]','','written','',''))
 with conn() as c:c.executemany('INSERT INTO questions(id,question,options_json,answer,kind,group_id,image_url) VALUES(?,?,?,?,?,?,?)',data)


def ensure_schema():
    with conn() as c:
        cols={r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        if "state" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN state TEXT DEFAULT 'code'")

def seed_defaults():
    init(); ensure_schema(); seed()
