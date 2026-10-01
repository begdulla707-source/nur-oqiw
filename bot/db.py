import sqlite3,json
from pathlib import Path
from datetime import datetime,timezone

DB=Path(__file__).resolve().parent.parent/"data"/"app.db"
DB.parent.mkdir(exist_ok=True)

def conn():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    return c

def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            telegram_id INTEGER PRIMARY KEY,
            full_name TEXT,
            phone TEXT,
            registered_at TEXT,
            code_ok INTEGER DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            score REAL DEFAULT 0,
            grade TEXT DEFAULT '',
            answers_json TEXT DEFAULT '{}',
            submitted INTEGER DEFAULT 0,
            state TEXT DEFAULT 'code'
        );
        CREATE TABLE IF NOT EXISTS questions(
            id INTEGER PRIMARY KEY,
            question TEXT,
            options_json TEXT DEFAULT '[]',
            answer TEXT DEFAULT '',
            kind TEXT DEFAULT 'choice',
            group_id TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            image_url TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS item_stats(
            question_id INTEGER PRIMARY KEY,
            attempts INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0
        );
        """)

def ensure_schema():
    with conn() as c:
        cols={r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        if "state" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN state TEXT DEFAULT 'code'")
        qcols={r["name"] for r in c.execute("PRAGMA table_info(questions)").fetchall()}
        if "image_url" not in qcols:
            c.execute("ALTER TABLE questions ADD COLUMN image_url TEXT DEFAULT ''")
        if "group_id" not in qcols:
            c.execute("ALTER TABLE questions ADD COLUMN group_id TEXT DEFAULT ''")
        if "active" not in qcols:
            c.execute("ALTER TABLE questions ADD COLUMN active INTEGER DEFAULT 1")

def get_setting(k,d=None):
    with conn() as c:
        r=c.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone()
        return r["value"] if r else d

def set_setting(k,v):
    with conn() as c:
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (k,str(v))
        )

def get_user(t):
    with conn() as c:
        return c.execute("SELECT * FROM users WHERE telegram_id=?",(int(t),)).fetchone()

def ensure_user(t):
    t=int(t)
    u=get_user(t)
    if u:
        return u
    now=datetime.now(timezone.utc).isoformat()
    with conn() as c:
        c.execute(
            "INSERT INTO users(telegram_id,full_name,phone,registered_at,code_ok,state) "
            "VALUES(?,?,?,?,0,'code')",
            (t,"",None,now)
        )
    return get_user(t)

def upsert_user(t,name,phone=None):
    t=int(t)
    with conn() as c:
        c.execute(
            "INSERT INTO users(telegram_id,full_name,phone,registered_at) "
            "VALUES(?,?,?,?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET "
            "full_name=excluded.full_name, phone=COALESCE(excluded.phone,users.phone)",
            (t,name,phone,datetime.now(timezone.utc).isoformat())
        )

def update_user(t,**fields):
    allowed={
        "full_name","phone","registered_at","code_ok","started_at",
        "finished_at","score","grade","answers_json","submitted","state"
    }
    fields={k:v for k,v in fields.items() if k in allowed}
    if not fields:
        return
    t=int(t)
    set_sql=", ".join(f"{k}=?" for k in fields)
    vals=list(fields.values())+[t]
    with conn() as c:
        c.execute(f"UPDATE users SET {set_sql} WHERE telegram_id=?",vals)

def set_code(t,v=1):
    update_user(t,code_ok=v)

def set_started(t,ts):
    update_user(t,started_at=ts)

def save_answers(t,a):
    with conn() as c:
        c.execute(
            "UPDATE users SET answers_json=? WHERE telegram_id=?",
            (json.dumps(a,ensure_ascii=False),int(t))
        )

def finish_user(t,score,grade,ts,a):
    with conn() as c:
        c.execute(
            "UPDATE users SET finished_at=?,score=?,grade=?,answers_json=?,submitted=1 "
            "WHERE telegram_id=?",
            (ts,float(score),str(grade),json.dumps(a,ensure_ascii=False),int(t))
        )

def finish(t,score,grade,ts,a):
    finish_user(t,score,grade,ts,a)

def all_users():
    with conn() as c:
        return c.execute(
            "SELECT * FROM users WHERE code_ok=1 ORDER BY score DESC,full_name"
        ).fetchall()

def active_questions():
    with conn() as c:
        return c.execute(
            "SELECT * FROM questions WHERE active=1 ORDER BY id"
        ).fetchall()

def get_question(qid):
    try:
        qid=int(qid)
    except (TypeError,ValueError):
        return None
    with conn() as c:
        return c.execute(
            "SELECT * FROM questions WHERE id=? AND active=1",(qid,)
        ).fetchone()

def replace_questions(items):
    with conn() as c:
        c.execute("DELETE FROM questions")
        c.executemany(
            "INSERT INTO questions(id,question,options_json,answer,kind,group_id,image_url) "
            "VALUES(?,?,?,?,?,?,?)",
            items
        )

def normalize(v):
    return " ".join(str(v or "").strip().casefold().split())

def record_stats(a):
    if not a:
        return
    with conn() as c:
        for qid,ans in a.items():
            try:
                qid=int(qid)
            except (TypeError,ValueError):
                continue
            q=c.execute("SELECT answer FROM questions WHERE id=?",(qid,)).fetchone()
            if not q:
                continue
            is_correct=int(normalize(ans)==normalize(q["answer"]))
            c.execute(
                "INSERT INTO item_stats(question_id,attempts,correct) VALUES(?,?,?) "
                "ON CONFLICT(question_id) DO UPDATE SET "
                "attempts=attempts+1, correct=correct+excluded.correct",
                (qid,1,is_correct)
            )

def weighted_score(a):
    qs={int(q["id"]):q for q in active_questions()}
    if not qs:
        return 0.0

    total_weight=0.0
    earned_weight=0.0
    for qid,q in qs.items():
        with conn() as c:
            st=c.execute(
                "SELECT attempts,correct FROM item_stats WHERE question_id=?",(qid,)
            ).fetchone()
        attempts=int(st["attempts"]) if st else 0
        corrects=int(st["correct"]) if st else 0
        p=(corrects/attempts) if attempts else 0.5
        weight=0.5+(1.0-p)*1.5
        total_weight += weight
        if str(qid) in a and normalize(a[str(qid)])==normalize(q["answer"]):
            earned_weight += weight

    return round((earned_weight/total_weight*100.0) if total_weight else 0.0,2)

def grade_for(score):
    s=float(score)
    if s>=90:return "A+"
    if s>=80:return "A"
    if s>=70:return "B"
    if s>=60:return "C"
    if s>=50:return "D"
    return "F"

def seed():
    if active_questions():
        return
    data=[]
    for i in range(1,33):
        data.append((
            i,
            f"Sertifikat uslubidagi matematika savoli {i}. To‘g‘ri javobni toping.",
            json.dumps(["A","B","C","D"],ensure_ascii=False),
            "A","choice","",""
        ))
    data += [
        (33,"Shu rasmdagi to‘g‘ri to‘rtburchakning enini toping.",
         json.dumps(["6","8","10","12"],ensure_ascii=False),"8","choice","fig33",""),
        (34,"Shu rasmdagi perimetrni toping.",
         json.dumps(["32","36","40","44"],ensure_ascii=False),"40","choice","fig33",""),
        (35,"Shu rasmdagi yuzani toping.",
         json.dumps(["72","84","96","108"],ensure_ascii=False),"96","choice","fig33","")
    ]
    for i in range(36,46):
        data.append((i,f"{i}. Yozma javobli sertifikat savoli.","[]","","written","",""))
    with conn() as c:
        c.executemany(
            "INSERT INTO questions(id,question,options_json,answer,kind,group_id,image_url) "
            "VALUES(?,?,?,?,?,?,?)",
            data
        )

def seed_defaults():
    init()
    ensure_schema()
    seed()
