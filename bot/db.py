import os, sqlite3, json
from pathlib import Path
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row
else:
    DB = Path(__file__).resolve().parent.parent / "data" / "app.db"
    DB.parent.mkdir(exist_ok=True)

class DBConn:
    def __init__(self, raw, pg=False):
        self.raw = raw
        self.pg = pg
    def __enter__(self):
        self.raw.__enter__()
        return self
    def __exit__(self, *args):
        return self.raw.__exit__(*args)
    def execute(self, query, params=()):
        if self.pg:
            query = query.replace("?", "%s")
        return self.raw.execute(query, params)
    def executemany(self, query, seq):
        if self.pg:
            query = query.replace("?", "%s")
        return self.raw.executemany(query, seq)
    def __getattr__(self, name):
        return getattr(self.raw, name)

def conn():
    if USE_POSTGRES:
        return DBConn(psycopg.connect(DATABASE_URL, row_factory=dict_row), True)
    c = sqlite3.connect(DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.row_factory = sqlite3.Row
    return DBConn(c, False)

def init():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            telegram_id BIGINT PRIMARY KEY,
            full_name TEXT,
            phone TEXT,
            registered_at TEXT,
            code_ok INTEGER DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            score DOUBLE PRECISION DEFAULT 0,
            grade TEXT DEFAULT '',
            answers_json TEXT DEFAULT '{}',
            submitted INTEGER DEFAULT 0,
            state TEXT DEFAULT 'code'
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS questions(
            id INTEGER PRIMARY KEY,
            question TEXT,
            options_json TEXT DEFAULT '[]',
            answer TEXT DEFAULT '',
            kind TEXT DEFAULT 'choice',
            group_id TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            image_url TEXT DEFAULT ''
        )""")
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)")
        c.execute("""CREATE TABLE IF NOT EXISTS item_stats(
            question_id INTEGER PRIMARY KEY,
            attempts INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_code ON users(code_ok)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_submitted ON users(submitted)")

def ensure_schema():
    with conn() as c:
        if USE_POSTGRES:
            cols={r["column_name"] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'").fetchall()}
            qcols={r["column_name"] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='questions'").fetchall()}
        else:
            cols={r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
            qcols={r["name"] for r in c.execute("PRAGMA table_info(questions)").fetchall()}
        if "state" not in cols: c.execute("ALTER TABLE users ADD COLUMN state TEXT DEFAULT 'code'")
        if "image_url" not in qcols: c.execute("ALTER TABLE questions ADD COLUMN image_url TEXT DEFAULT ''")
        if "group_id" not in qcols: c.execute("ALTER TABLE questions ADD COLUMN group_id TEXT DEFAULT ''")
        if "active" not in qcols: c.execute("ALTER TABLE questions ADD COLUMN active INTEGER DEFAULT 1")

def get_setting(k,d=None):
    with conn() as c:
        r=c.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone()
        return r["value"] if r else d

def set_setting(k,v):
    with conn() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(v)))

def get_user(t):
    with conn() as c: return c.execute("SELECT * FROM users WHERE telegram_id=?",(int(t),)).fetchone()

def ensure_user(t):
    t=int(t); u=get_user(t)
    if u:return u
    now=datetime.now(timezone.utc).isoformat()
    with conn() as c:c.execute("INSERT INTO users(telegram_id,full_name,phone,registered_at,code_ok,state) VALUES(?,?,?,?,0,'code')",(t,"",None,now))
    return get_user(t)

def upsert_user(t,name,phone=None):
    with conn() as c:
        c.execute("""INSERT INTO users(telegram_id,full_name,phone,registered_at) VALUES(?,?,?,?)
        ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name,phone=COALESCE(excluded.phone,users.phone)""",(int(t),name,phone,datetime.now(timezone.utc).isoformat()))

def update_user(t,**fields):
    allowed={"full_name","phone","registered_at","code_ok","started_at","finished_at","score","grade","answers_json","submitted","state"}
    fields={k:v for k,v in fields.items() if k in allowed}
    if not fields:return
    with conn() as c:c.execute("UPDATE users SET "+", ".join(f"{k}=?" for k in fields)+" WHERE telegram_id=?",list(fields.values())+[int(t)])

def set_code(t,v=1):update_user(t,code_ok=v)
def set_started(t,ts):update_user(t,started_at=ts)
def save_answers(t,a):
    with conn() as c:c.execute("UPDATE users SET answers_json=? WHERE telegram_id=?",(json.dumps(a,ensure_ascii=False),int(t)))
def finish_user(t,score,grade,ts,a):
    with conn() as c:c.execute("UPDATE users SET finished_at=?,score=?,grade=?,answers_json=?,submitted=1 WHERE telegram_id=?",(ts,float(score),str(grade),json.dumps(a,ensure_ascii=False),int(t)))
def finish(t,score,grade,ts,a):finish_user(t,score,grade,ts,a)

def all_users():
    with conn() as c:return c.execute("SELECT * FROM users WHERE code_ok=1 ORDER BY score DESC,full_name").fetchall()
def all_registered_users():
    with conn() as c:return c.execute("SELECT * FROM users ORDER BY registered_at ASC").fetchall()
def active_questions():
    with conn() as c:return c.execute("SELECT * FROM questions WHERE active=1 ORDER BY id").fetchall()
def all_questions():
    with conn() as c:return c.execute("SELECT * FROM questions ORDER BY id").fetchall()
def get_question(qid):
    try:qid=int(qid)
    except:return None
    with conn() as c:return c.execute("SELECT * FROM questions WHERE id=? AND active=1",(qid,)).fetchone()
def get_question_any(qid):
    try:qid=int(qid)
    except:return None
    with conn() as c:return c.execute("SELECT * FROM questions WHERE id=?",(qid,)).fetchone()
def upsert_question(qid,question,options,answer,kind="choice",group_id="",image_url=""):
    with conn() as c:c.execute("""INSERT INTO questions(id,question,options_json,answer,kind,group_id,active,image_url) VALUES(?,?,?,?,?,?,1,?)
    ON CONFLICT(id) DO UPDATE SET question=excluded.question,options_json=excluded.options_json,answer=excluded.answer,kind=excluded.kind,group_id=excluded.group_id,image_url=excluded.image_url,active=1""",(int(qid),str(question),json.dumps(options,ensure_ascii=False),str(answer),str(kind),str(group_id),str(image_url)))
def delete_question(qid):
    with conn() as c:
        if not c.execute("SELECT id FROM questions WHERE id=?",(int(qid),)).fetchone():return False
        c.execute("DELETE FROM questions WHERE id=?",(int(qid),));return True
def set_active_question_count(n):
    n=max(0,int(n))
    with conn() as c:
        c.execute("UPDATE questions SET active=0")
        ids=[r["id"] for r in c.execute("SELECT id FROM questions ORDER BY id LIMIT ?",(n,)).fetchall()]
        for qid in ids:c.execute("UPDATE questions SET active=1 WHERE id=?",(qid,))
def replace_questions(items):
    with conn() as c:
        c.execute("DELETE FROM questions")
        c.executemany("INSERT INTO questions(id,question,options_json,answer,kind,group_id,image_url) VALUES(?,?,?,?,?,?,?)",items)
        c.execute("UPDATE questions SET active=1")
def normalize(v):return " ".join(str(v or "").strip().casefold().split())
def record_stats(a):
    if not a:return
    with conn() as c:
        for qid,ans in a.items():
            try:qid=int(qid)
            except:continue
            q=c.execute("SELECT answer FROM questions WHERE id=?",(qid,)).fetchone()
            if not q:continue
            good=int(normalize(ans)==normalize(q["answer"]))
            c.execute("INSERT INTO item_stats(question_id,attempts,correct) VALUES(?,?,?) ON CONFLICT(question_id) DO UPDATE SET attempts=attempts+1,correct=correct+excluded.correct",(qid,1,good))
def weighted_score(a):
    qs={int(q["id"]):q for q in active_questions()}
    if not qs:return 0.0
    total=earned=0.0
    with conn() as c:
        for qid,q in qs.items():
            st=c.execute("SELECT attempts,correct FROM item_stats WHERE question_id=?",(qid,)).fetchone()
            attempts=int(st["attempts"]) if st else 0; corrects=int(st["correct"]) if st else 0
            p=corrects/attempts if attempts else 0.5; weight=0.5+(1-p)*1.5; total+=weight
            if str(qid) in a and normalize(a[str(qid)])==normalize(q["answer"]):earned+=weight
    return round(earned/total*100,2) if total else 0.0
def grade_for(score):
    s=float(score);return "A+" if s>=90 else "A" if s>=80 else "B" if s>=70 else "C" if s>=60 else "D" if s>=50 else "F"
def seed():
    if active_questions():return
    data=[]
    for i in range(1,33):data.append((i,f"Sertifikat uslubidagi matematika savoli {i}. To‘g‘ri javobni toping.",json.dumps(["A","B","C","D"],ensure_ascii=False),"A","choice","",""))
    data += [(33,"Shu rasmdagi to‘g‘ri to‘rtburchakning enini toping.",json.dumps(["6","8","10","12"],ensure_ascii=False),"8","choice","fig33",""),(34,"Shu rasmdagi perimetrni toping.",json.dumps(["32","36","40","44"],ensure_ascii=False),"40","choice","fig33",""),(35,"Shu rasmdagi yuzani toping.",json.dumps(["72","84","96","108"],ensure_ascii=False),"96","choice","fig33","")]
    for i in range(36,46):data.append((i,f"{i}. Yozma javobli sertifikat savoli.","[]","","written","",""))
    with conn() as c:c.executemany("INSERT INTO questions(id,question,options_json,answer,kind,group_id,image_url) VALUES(?,?,?,?,?,?,?)",data)
def seed_defaults():init();ensure_schema();seed()
