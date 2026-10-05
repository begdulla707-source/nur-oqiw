import os, sqlite3, json, secrets
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
    def __init__(self, raw, pg=False): self.raw, self.pg = raw, pg
    def __enter__(self): self.raw.__enter__(); return self
    def __exit__(self, *args): return self.raw.__exit__(*args)
    def execute(self, query, params=()):
        if self.pg: query=query.replace("?","%s")
        return self.raw.execute(query,params)
    def executemany(self, query, seq):
        if self.pg: query=query.replace("?","%s")
        return self.raw.executemany(query,seq)
    def __getattr__(self,name): return getattr(self.raw,name)

def conn():
    if USE_POSTGRES: return DBConn(psycopg.connect(DATABASE_URL,row_factory=dict_row),True)
    c=sqlite3.connect(DB,timeout=30); c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=30000"); c.row_factory=sqlite3.Row; return DBConn(c,False)

def init():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            telegram_id BIGINT PRIMARY KEY, full_name TEXT, phone TEXT, registered_at TEXT,
            code_ok INTEGER DEFAULT 0, started_at TEXT, finished_at TEXT, score DOUBLE PRECISION DEFAULT 0,
            grade TEXT DEFAULT '', answers_json TEXT DEFAULT '{}', submitted INTEGER DEFAULT 0,
            state TEXT DEFAULT 'code', tier TEXT DEFAULT 'default', premium_since TEXT,
            premium_granted_by BIGINT, test_id TEXT DEFAULT ''
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS tests(
            test_id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            start_time TEXT DEFAULT '08:30', end_time TEXT DEFAULT '09:30', mode TEXT DEFAULT 'auto',
            active INTEGER DEFAULT 1, created_at TEXT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS questions(
            id INTEGER PRIMARY KEY, question TEXT, options_json TEXT DEFAULT '[]', answer TEXT DEFAULT '',
            kind TEXT DEFAULT 'choice', group_id TEXT DEFAULT '', active INTEGER DEFAULT 1, image_url TEXT DEFAULT '',
            test_id TEXT DEFAULT '', number INTEGER DEFAULT 0
        )""")
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)")
        c.execute("""CREATE TABLE IF NOT EXISTS item_stats(question_id INTEGER PRIMARY KEY, attempts INTEGER DEFAULT 0, correct INTEGER DEFAULT 0)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_code ON users(code_ok)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_submitted ON users(submitted)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_test ON users(test_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_questions_test ON questions(test_id,number)")

def ensure_schema():
    with conn() as c:
        if USE_POSTGRES:
            cols={r["column_name"] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'").fetchall()}
            qcols={r["column_name"] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='questions'").fetchall()}
        else:
            cols={r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
            qcols={r["name"] for r in c.execute("PRAGMA table_info(questions)").fetchall()}
        if "state" not in cols:c.execute("ALTER TABLE users ADD COLUMN state TEXT DEFAULT 'code'")
        if "tier" not in cols:c.execute("ALTER TABLE users ADD COLUMN tier TEXT DEFAULT 'default'")
        if "premium_since" not in cols:c.execute("ALTER TABLE users ADD COLUMN premium_since TEXT")
        if "premium_granted_by" not in cols:c.execute("ALTER TABLE users ADD COLUMN premium_granted_by BIGINT")
        if "test_id" not in cols:c.execute("ALTER TABLE users ADD COLUMN test_id TEXT DEFAULT ''")
        if "image_url" not in qcols:c.execute("ALTER TABLE questions ADD COLUMN image_url TEXT DEFAULT ''")
        if "group_id" not in qcols:c.execute("ALTER TABLE questions ADD COLUMN group_id TEXT DEFAULT ''")
        if "active" not in qcols:c.execute("ALTER TABLE questions ADD COLUMN active INTEGER DEFAULT 1")
        if "test_id" not in qcols:c.execute("ALTER TABLE questions ADD COLUMN test_id TEXT DEFAULT ''")
        if "number" not in qcols:c.execute("ALTER TABLE questions ADD COLUMN number INTEGER DEFAULT 0")

def get_setting(k,d=None):
    with conn() as c:
        r=c.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone(); return r["value"] if r else d

def set_setting(k,v):
    with conn() as c:c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(v)))

def get_user(t):
    with conn() as c:return c.execute("SELECT * FROM users WHERE telegram_id=?",(int(t),)).fetchone()

def ensure_user(t):
    t=int(t);u=get_user(t)
    if u:return u
    now=datetime.now(timezone.utc).isoformat()
    with conn() as c:c.execute("INSERT INTO users(telegram_id,full_name,phone,registered_at,code_ok,state,tier,test_id) VALUES(?,?,?,?,0,'code','default','')",(t,"",None,now))
    return get_user(t)

def upsert_user(t,name,phone=None):
    with conn() as c:c.execute("""INSERT INTO users(telegram_id,full_name,phone,registered_at,tier,test_id) VALUES(?,?,?,?, 'default','')
        ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name,phone=COALESCE(excluded.phone,users.phone)""",(int(t),name,phone,datetime.now(timezone.utc).isoformat()))

def update_user(t,**fields):
    allowed={"full_name","phone","registered_at","code_ok","started_at","finished_at","score","grade","answers_json","submitted","state","tier","premium_since","premium_granted_by","test_id"}
    fields={k:v for k,v in fields.items() if k in allowed}
    if fields:
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
def public_users():
    with conn() as c:return c.execute("SELECT telegram_id,full_name,tier FROM users WHERE code_ok=1 ORDER BY registered_at ASC").fetchall()
def set_tier(t,tier,admin_id=None):
    tier="premium" if str(tier).lower()=="premium" else "default"; now=datetime.now(timezone.utc).isoformat() if tier=="premium" else None
    update_user(t,tier=tier,premium_since=now,premium_granted_by=(int(admin_id) if admin_id and tier=="premium" else None))
def is_premium(t):
    u=get_user(t);return bool(u and str(u["tier"] or "default").lower()=="premium")

def _default_test_id():
    r=None
    with conn() as c:r=c.execute("SELECT test_id FROM tests ORDER BY created_at LIMIT 1").fetchone()
    return r["test_id"] if r else ""

def create_test(name,code,start_time="08:30",end_time="09:30",mode="auto"):
    test_id=secrets.token_hex(8);code=str(code).strip();now=datetime.now(timezone.utc).isoformat()
    with conn() as c:c.execute("INSERT INTO tests(test_id,code,name,start_time,end_time,mode,active,created_at) VALUES(?,?,?,?,?,?,1,?)",(test_id,code,str(name).strip(),start_time,end_time,mode,now))
    return get_test(test_id)

def get_test(test_id):
    if not test_id:return None
    with conn() as c:return c.execute("SELECT * FROM tests WHERE test_id=?",(str(test_id),)).fetchone()

def get_test_by_code(code):
    with conn() as c:return c.execute("SELECT * FROM tests WHERE lower(code)=lower(?) AND active=1",(str(code).strip(),)).fetchone()

def all_tests():
    with conn() as c:return c.execute("SELECT * FROM tests ORDER BY created_at DESC").fetchall()

def set_test_active(test_id,active=1):
    with conn() as c:c.execute("UPDATE tests SET active=? WHERE test_id=?",(int(active),str(test_id)))

def questions_for_test(test_id):
    with conn() as c:return c.execute("SELECT * FROM questions WHERE active=1 AND test_id=? ORDER BY number,id",(str(test_id),)).fetchall()

def get_question_for_test(test_id,number):
    try:number=int(number)
    except:return None
    with conn() as c:return c.execute("SELECT * FROM questions WHERE active=1 AND test_id=? AND number=?",(str(test_id),number)).fetchone()

def next_question_id():
    with conn() as c:
        r=c.execute("SELECT COALESCE(MAX(id),0)+1 AS n FROM questions").fetchone();return int(r["n"])

def upsert_test_question(test_id,number,question,options,answer,kind="choice",group_id="",image_url=""):
    with conn() as c:
        old=c.execute("SELECT id FROM questions WHERE test_id=? AND number=?",(str(test_id),int(number))).fetchone()
        if old:
            c.execute("UPDATE questions SET question=?,options_json=?,answer=?,kind=?,group_id=?,image_url=?,active=1 WHERE id=?",(str(question),json.dumps(options,ensure_ascii=False),str(answer),str(kind),str(group_id),str(image_url),old["id"]))
            return int(old["id"])
        qid=next_question_id();c.execute("INSERT INTO questions(id,question,options_json,answer,kind,group_id,active,image_url,test_id,number) VALUES(?,?,?,?,?,?,1,?,?,?)",(qid,str(question),json.dumps(options,ensure_ascii=False),str(answer),str(kind),str(group_id),str(image_url),str(test_id),int(number)));return qid

def delete_test_question(test_id,number):
    with conn() as c:return c.execute("DELETE FROM questions WHERE test_id=? AND number=?",(str(test_id),int(number))).rowcount>0

def active_questions(test_id=None):
    test_id=test_id or get_setting("admin_test_id") or _default_test_id()
    return questions_for_test(test_id) if test_id else []

def all_questions():
    with conn() as c:return c.execute("SELECT * FROM questions ORDER BY test_id,number,id").fetchall()
def get_question(qid):
    try:qid=int(qid)
    except:return None
    with conn() as c:return c.execute("SELECT * FROM questions WHERE id=? AND active=1",(qid,)).fetchone()
def get_question_any(qid):
    try:qid=int(qid)
    except:return None
    with conn() as c:return c.execute("SELECT * FROM questions WHERE id=?",(qid,)).fetchone()
def upsert_question(qid,question,options,answer,kind="choice",group_id="",image_url="",test_id=None):
    test_id=test_id or get_setting("admin_test_id") or _default_test_id()
    number=int(qid)
    return upsert_test_question(test_id,number,question,options,answer,kind,group_id,image_url)
def delete_question(qid):return delete_test_question(get_setting("admin_test_id") or _default_test_id(),int(qid))
def set_active_question_count(n):
    n=max(0,int(n));test_id=get_setting("admin_test_id") or _default_test_id()
    with conn() as c:
        c.execute("UPDATE questions SET active=0 WHERE test_id=?",(test_id,));ids=[r["id"] for r in c.execute("SELECT id FROM questions WHERE test_id=? ORDER BY number LIMIT ?",(test_id,n)).fetchall()]
        for qid in ids:c.execute("UPDATE questions SET active=1 WHERE id=?",(qid,))
def replace_questions(items):
    with conn() as c:c.execute("DELETE FROM questions")
    for item in items:upsert_test_question(item[0],item[1],item[2],item[3],item[4],item[5],item[6],item[7])
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
    qs={int(q["id"]):q for q in active_questions()};
    if not qs:return 0.0
    total=earned=0.0
    with conn() as c:
        for qid,q in qs.items():
            st=c.execute("SELECT attempts,correct FROM item_stats WHERE question_id=?",(qid,)).fetchone();attempts=int(st["attempts"]) if st else 0;corrects=int(st["correct"]) if st else 0;p=corrects/attempts if attempts else 0.5;weight=0.5+(1-p)*1.5;total+=weight
            if str(qid) in a and normalize(a[str(qid)])==normalize(q["answer"]):earned+=weight
    return round(earned/total*100,2) if total else 0.0
def grade_for(score):
    s=float(score);return "A+" if s>=90 else "A" if s>=80 else "B" if s>=70 else "C" if s>=60 else "D" if s>=50 else "F"
def seed():
    if all_tests():return
    test=create_test("Asosiy test",os.getenv("ACCESS_CODE","0924"),os.getenv("TEST_START","08:30"),os.getenv("TEST_END","09:30"),"auto")
    test_id=test["test_id"];data=[]
    for i in range(1,33):data.append((test_id,i,f"Sertifikat uslubidagi matematika savoli {i}. To‘g‘ri javobni toping.",["A","B","C","D"],"A","choice","",""))
    data += [(test_id,33,"Shu rasmdagi to‘g‘ri to‘rtburchakning enini toping.",["6","8","10","12"],"8","choice","fig33",""),(test_id,34,"Shu rasmdagi perimetrni toping.",["32","36","40","44"],"40","choice","fig33",""),(test_id,35,"Shu rasmdagi yuzani toping.",["72","84","96","108"],"96","choice","fig33","")]
    for i in range(36,46):data.append((test_id,i,f"{i}. Yozma javobli sertifikat savoli.",[],"","written","",""))
    for row in data:upsert_test_question(*row)

def seed_defaults():init();ensure_schema();seed()
