import os, sqlite3, json, secrets
from pathlib import Path
from datetime import datetime, timezone
DATABASE_URL=os.getenv("DATABASE_URL","").strip();USE_POSTGRES=bool(DATABASE_URL)
if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row
else:
    DB=Path(__file__).resolve().parent.parent/"data"/"app.db";DB.parent.mkdir(exist_ok=True)
class DBConn:
    def __init__(self,raw,pg=False):self.raw,self.pg=raw,pg
    def __enter__(self):self.raw.__enter__();return self
    def __exit__(self,*args):return self.raw.__exit__(*args)
    def execute(self,q,p=()):return self.raw.execute(q.replace("?","%s") if self.pg else q,p)
    def executemany(self,q,s):return self.raw.executemany(q.replace("?","%s") if self.pg else q,s)
    def __getattr__(self,n):return getattr(self.raw,n)
def conn():
    if USE_POSTGRES:return DBConn(psycopg.connect(DATABASE_URL,row_factory=dict_row),True)
    c=sqlite3.connect(DB,timeout=30);c.execute("PRAGMA journal_mode=WAL");c.execute("PRAGMA busy_timeout=30000");c.row_factory=sqlite3.Row;return DBConn(c)

def init():
    with conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS users(telegram_id BIGINT PRIMARY KEY,full_name TEXT,phone TEXT,registered_at TEXT,code_ok INTEGER DEFAULT 0,started_at TEXT,finished_at TEXT,score DOUBLE PRECISION DEFAULT 0,grade TEXT DEFAULT '',answers_json TEXT DEFAULT '{}',submitted INTEGER DEFAULT 0,state TEXT DEFAULT 'code',tier TEXT DEFAULT 'default',premium_since TEXT,premium_granted_by BIGINT,test_id TEXT DEFAULT '')")
        c.execute("CREATE TABLE IF NOT EXISTS tests(test_id TEXT PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,start_time TEXT DEFAULT '08:30',end_time TEXT DEFAULT '09:30',mode TEXT DEFAULT 'auto',active INTEGER DEFAULT 1,created_at TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY,question TEXT,options_json TEXT DEFAULT '[]',answer TEXT DEFAULT '',kind TEXT DEFAULT 'choice',group_id TEXT DEFAULT '',active INTEGER DEFAULT 1,image_url TEXT DEFAULT '',test_id TEXT DEFAULT '',number INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS item_stats(question_id INTEGER PRIMARY KEY,attempts INTEGER DEFAULT 0,correct INTEGER DEFAULT 0)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_test ON users(test_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_questions_test ON questions(test_id,number)")

def ensure_schema():
    with conn() as c:
        if USE_POSTGRES:
            cols={x["column_name"] for x in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'").fetchall()};qcols={x["column_name"] for x in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='questions'").fetchall()}
        else:
            cols={x["name"] for x in c.execute("PRAGMA table_info(users)").fetchall()};qcols={x["name"] for x in c.execute("PRAGMA table_info(questions)").fetchall()}
        for name,typ in [("state","TEXT DEFAULT 'code'"),("tier","TEXT DEFAULT 'default'"),("premium_since","TEXT"),("premium_granted_by","BIGINT"),("test_id","TEXT DEFAULT ''")]:
            if name not in cols:c.execute(f"ALTER TABLE users ADD COLUMN {name} {typ}")
        for name,typ in [("image_url","TEXT DEFAULT ''"),("group_id","TEXT DEFAULT ''"),("active","INTEGER DEFAULT 1"),("test_id","TEXT DEFAULT ''"),("number","INTEGER DEFAULT 0")]:
            if name not in qcols:c.execute(f"ALTER TABLE questions ADD COLUMN {name} {typ}")
        # Attach legacy questions to the first test after the test is created.

def get_setting(k,d=None):
    with conn() as c:r=c.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone();return r["value"] if r else d
def set_setting(k,v):
    with conn() as c:c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,str(v)))
def get_user(t):
    with conn() as c:return c.execute("SELECT * FROM users WHERE telegram_id=?",(int(t),)).fetchone()
def ensure_user(t):
    u=get_user(t)
    if u:return u
    with conn() as c:c.execute("INSERT INTO users(telegram_id,full_name,phone,registered_at,state,tier,test_id) VALUES(?,?,?,?, 'code','default','')",(int(t),"",None,datetime.now(timezone.utc).isoformat()))
    return get_user(t)
def upsert_user(t,name,phone=None):
    with conn() as c:c.execute("INSERT INTO users(telegram_id,full_name,phone,registered_at,tier,test_id) VALUES(?,?,?,?, 'default','') ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name,phone=COALESCE(excluded.phone,users.phone)",(int(t),name,phone,datetime.now(timezone.utc).isoformat()))
def update_user(t,**fields):
    allowed={"full_name","phone","registered_at","code_ok","started_at","finished_at","score","grade","answers_json","submitted","state","tier","premium_since","premium_granted_by","test_id"};fields={k:v for k,v in fields.items() if k in allowed}
    if fields:
        with conn() as c:c.execute("UPDATE users SET "+",".join(f"{k}=?" for k in fields)+" WHERE telegram_id=?",list(fields.values())+[int(t)])
def set_code(t,v=1):update_user(t,code_ok=v)
def set_started(t,ts):update_user(t,started_at=ts)
def save_answers(t,a):
    with conn() as c:c.execute("UPDATE users SET answers_json=? WHERE telegram_id=?",(json.dumps(a,ensure_ascii=False),int(t)))
def finish_user(t,score,grade,ts,a):update_user(t,finished_at=ts,score=score,grade=grade,answers_json=json.dumps(a,ensure_ascii=False),submitted=1)
def finish(t,score,grade,ts,a):finish_user(t,score,grade,ts,a)
def all_users():
    with conn() as c:return c.execute("SELECT * FROM users WHERE code_ok=1 ORDER BY score DESC,full_name").fetchall()
def all_registered_users():
    with conn() as c:return c.execute("SELECT * FROM users ORDER BY registered_at ASC").fetchall()
def public_users():
    with conn() as c:return c.execute("SELECT telegram_id,full_name,tier FROM users WHERE code_ok=1 ORDER BY registered_at ASC").fetchall()
def set_tier(t,tier,admin_id=None):update_user(t,tier="premium" if str(tier).lower()=="premium" else "default",premium_since=datetime.now(timezone.utc).isoformat() if str(tier).lower()=="premium" else None,premium_granted_by=(int(admin_id) if admin_id and str(tier).lower()=="premium" else None))
def is_premium(t):u=get_user(t);return bool(u and str(u["tier"] or "default").lower()=="premium")

def create_test(name,code,start_time="08:30",end_time="09:30",mode="auto"):
    tid=secrets.token_hex(8)
    with conn() as c:c.execute("INSERT INTO tests(test_id,code,name,start_time,end_time,mode,active,created_at) VALUES(?,?,?,?,?,?,1,?)",(tid,str(code).strip(),str(name).strip(),start_time,end_time,mode,datetime.now(timezone.utc).isoformat()))
    return get_test(tid)
def get_test(tid):
    if not tid:return None
    with conn() as c:return c.execute("SELECT * FROM tests WHERE test_id=?",(str(tid),)).fetchone()
def get_test_by_code(code):
    with conn() as c:return c.execute("SELECT * FROM tests WHERE lower(code)=lower(?) AND active=1",(str(code).strip(),)).fetchone()
def all_tests():
    with conn() as c:return c.execute("SELECT * FROM tests ORDER BY created_at DESC").fetchall()
def set_test_active(tid,active=1):
    with conn() as c:c.execute("UPDATE tests SET active=? WHERE test_id=?",(int(active),str(tid)))
def _default_test_id():
    r=None
    with conn() as c:r=c.execute("SELECT test_id FROM tests ORDER BY created_at LIMIT 1").fetchone()
    return r["test_id"] if r else ""
def questions_for_test(tid):
    with conn() as c:return c.execute("SELECT * FROM questions WHERE active=1 AND test_id=? ORDER BY number,id",(str(tid),)).fetchall()
def get_question_for_test(tid,num):
    try:num=int(num)
    except:return None
    with conn() as c:return c.execute("SELECT * FROM questions WHERE active=1 AND test_id=? AND number=?",(str(tid),num)).fetchone()
def upsert_test_question(tid,num,question,options,answer,kind="choice",group_id="",image_url=""):
    with conn() as c:
        old=c.execute("SELECT id FROM questions WHERE test_id=? AND number=?",(str(tid),int(num))).fetchone()
        if old:
            c.execute("UPDATE questions SET question=?,options_json=?,answer=?,kind=?,group_id=?,image_url=?,active=1 WHERE id=?",(str(question),json.dumps(options,ensure_ascii=False),str(answer),str(kind),str(group_id),str(image_url),old["id"]));return int(old["id"])
        r=c.execute("SELECT COALESCE(MAX(id),0)+1 AS n FROM questions").fetchone();qid=int(r["n"])
        c.execute("INSERT INTO questions(id,question,options_json,answer,kind,group_id,active,image_url,test_id,number) VALUES(?,?,?,?,?,?,1,?,?,?)",(qid,str(question),json.dumps(options,ensure_ascii=False),str(answer),str(kind),str(group_id),str(image_url),str(tid),int(num)));return qid
def delete_test_question(tid,num):
    with conn() as c:return c.execute("DELETE FROM questions WHERE test_id=? AND number=?",(str(tid),int(num))).rowcount>0
def active_questions(test_id=None):
    tid=test_id or get_setting("admin_test_id") or _default_test_id();return questions_for_test(tid) if tid else []
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
def upsert_question(qid,question,options,answer,kind="choice",group_id="",image_url="",test_id=None):return upsert_test_question(test_id or get_setting("admin_test_id") or _default_test_id(),qid,question,options,answer,kind,group_id,image_url)
def delete_question(qid):return delete_test_question(get_setting("admin_test_id") or _default_test_id(),qid)
def set_active_question_count(n):
    tid=get_setting("admin_test_id") or _default_test_id();n=max(0,int(n))
    with conn() as c:
        c.execute("UPDATE questions SET active=0 WHERE test_id=?",(tid,));ids=[r["id"] for r in c.execute("SELECT id FROM questions WHERE test_id=? ORDER BY number LIMIT ?",(tid,n)).fetchall()]
        for qid in ids:c.execute("UPDATE questions SET active=1 WHERE id=?",(qid,))
def replace_questions(items):
    with conn() as c:c.execute("DELETE FROM questions")
    for x in items:upsert_test_question(x[0],x[1],x[2],x[3],x[4],x[5],x[6],x[7])
def normalize(v):return " ".join(str(v or "").strip().casefold().split())
def record_stats(a):
    for qid,ans in (a or {}).items():
        try:
            q=get_question(qid)
            if not q:continue
            good=int(normalize(ans)==normalize(q["answer"]))
            with conn() as c:c.execute("INSERT INTO item_stats(question_id,attempts,correct) VALUES(?,?,?) ON CONFLICT(question_id) DO UPDATE SET attempts=attempts+1,correct=correct+excluded.correct",(int(qid),1,good))
        except Exception:pass
def weighted_score(a):
    qs=active_questions();
    if not qs:return 0.0
    correct=sum(1 for q in qs if normalize((a or {}).get(str(q["id"]),""))==normalize(q["answer"]));return round(correct/len(qs)*100,2)
def grade_for(score):
    s=float(score);return "A+" if s>=90 else "A" if s>=80 else "B" if s>=70 else "C" if s>=60 else "D" if s>=50 else "F"
def seed():
    if all_tests():return
    t=create_test("Asosiy test",os.getenv("ACCESS_CODE","0924"),os.getenv("TEST_START","08:30"),os.getenv("TEST_END","09:30"),"auto");tid=t["test_id"]
    for i in range(1,33):upsert_test_question(tid,i,f"Sertifikat uslubidagi matematika savoli {i}. To‘g‘ri javobni toping.",["A","B","C","D"],"A")
    for n,q,opts,a in [(33,"Shu rasmdagi to‘g‘ri to‘rtburchakning enini toping.",["6","8","10","12"],"8"),(34,"Shu rasmdagi perimetrni toping.",["32","36","40","44"],"40"),(35,"Shu rasmdagi yuzani toping.",["72","84","96","108"],"96")]:upsert_test_question(tid,n,q,opts,a,group_id="fig33")
    for i in range(36,46):upsert_test_question(tid,i,f"{i}. Yozma javobli sertifikat savoli.",[],"","written")
def seed_defaults():init();ensure_schema();seed()
