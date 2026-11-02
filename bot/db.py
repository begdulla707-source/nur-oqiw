import os, sqlite3, json, secrets
from pathlib import Path
from datetime import datetime, timezone
DATABASE_URL=os.getenv("DATABASE_URL","").strip();USE_POSTGRES=bool(DATABASE_URL)
DB=Path(__file__).resolve().parent.parent/"data"/"app.db";DB.parent.mkdir(exist_ok=True)
if not USE_POSTGRES:
    import logging
    logging.getLogger("nur-oqiw.db").warning("DATABASE_URL is not configured: using local SQLite. On Render this storage can be lost on redeploy/restart; configure a durable PostgreSQL DATABASE_URL to preserve registrations, tests, answers, and results.")
if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row
class DBConn:
    def __init__(self,raw,pg=False):self.raw,self.pg=raw,pg
    def __enter__(self):self.raw.__enter__();return self
    def __exit__(self,*args):return self.raw.__exit__(*args)
    def execute(self,q,p=()):return self.raw.execute(q.replace("?","%s") if self.pg else q,p)
    def executemany(self,q,s):return self.raw.executemany(q.replace("?","%s") if self.pg else q,s)
    def __getattr__(self,n):return getattr(self.raw,n)
def conn():
    if USE_POSTGRES:return DBConn(psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=10),True)
    c=sqlite3.connect(DB,timeout=30);c.execute("PRAGMA journal_mode=WAL");c.execute("PRAGMA busy_timeout=30000");c.row_factory=sqlite3.Row;return DBConn(c)

def init():
    with conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS users(telegram_id BIGINT PRIMARY KEY,full_name TEXT,phone TEXT,registered_at TEXT,code_ok INTEGER DEFAULT 0,started_at TEXT,finished_at TEXT,score DOUBLE PRECISION DEFAULT 0,grade TEXT DEFAULT '',answers_json TEXT DEFAULT '{}',submitted INTEGER DEFAULT 0,state TEXT DEFAULT 'code',tier TEXT DEFAULT 'default',premium_since TEXT,premium_granted_by BIGINT,test_id TEXT DEFAULT '',telegram_photo TEXT DEFAULT '')")
        c.execute("CREATE TABLE IF NOT EXISTS tests(test_id TEXT PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,start_time TEXT DEFAULT '08:30',end_time TEXT DEFAULT '09:30',mode TEXT DEFAULT 'auto',active INTEGER DEFAULT 1,created_at TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY,question TEXT,options_json TEXT DEFAULT '[]',answer TEXT DEFAULT '',kind TEXT DEFAULT 'choice',group_id TEXT DEFAULT '',active INTEGER DEFAULT 1,image_url TEXT DEFAULT '',test_id TEXT DEFAULT '',number INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS item_stats(question_id INTEGER PRIMARY KEY,attempts INTEGER DEFAULT 0,correct INTEGER DEFAULT 0)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_test ON users(test_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_questions_test ON questions(test_id,number)")
        c.execute("""CREATE TABLE IF NOT EXISTS test_attempts(
            attempt_id TEXT PRIMARY KEY,
            test_id TEXT NOT NULL,
            telegram_id BIGINT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            score DOUBLE PRECISION DEFAULT 0,
            grade TEXT DEFAULT '',
            answers_json TEXT DEFAULT '{}',
            submitted INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            UNIQUE(test_id,telegram_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_attempts_test ON test_attempts(test_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_attempts_user ON test_attempts(telegram_id)")
        c.execute("""CREATE TABLE IF NOT EXISTS permanent_results(
            attempt_id TEXT PRIMARY KEY,
            test_id TEXT NOT NULL DEFAULT '',
            test_code TEXT NOT NULL DEFAULT '',
            test_name TEXT NOT NULL DEFAULT '',
            telegram_id BIGINT NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            phone TEXT DEFAULT '',
            started_at TEXT,
            finished_at TEXT,
            score DOUBLE PRECISION DEFAULT 0,
            grade TEXT DEFAULT '',
            answers_json TEXT DEFAULT '{}',
            submitted INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            archived_at TEXT NOT NULL
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_permanent_results_test ON permanent_results(test_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_permanent_results_user ON permanent_results(telegram_id)")
        c.execute("""CREATE TABLE IF NOT EXISTS paid_tests (
            test_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS paid_test_access (
            test_id TEXT NOT NULL,
            telegram_id BIGINT NOT NULL,
            granted_by BIGINT NOT NULL,
            granted_at TEXT NOT NULL,
            PRIMARY KEY (test_id,telegram_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_paid_access_user ON paid_test_access(telegram_id)")

    # Large migration and result backfill run after webhook setup, not during cold start.

def startup_maintenance():
    """Run nonessential bulk work after the bot is reachable."""
    import logging, time
    log=logging.getLogger("nur-oqiw.db")
    started=time.monotonic()
    try:
        if USE_POSTGRES:
            _migrate_local_sqlite()
        archive_completed_results()
        log.info("Background database maintenance completed in %.2fs",time.monotonic()-started)
    except Exception:
        log.exception("Background database maintenance failed after %.2fs",time.monotonic()-started)

def _migrate_local_sqlite():
    """Best-effort one-time import of any SQLite data still present on the instance."""
    if not USE_POSTGRES or not DB.exists():
        return
    try:
        with conn() as pg:
            marker=pg.execute("SELECT value FROM settings WHERE key=?",("sqlite_import_complete",)).fetchone()
            if marker and str(marker["value"])=="1":
                return
        with sqlite3.connect(DB,timeout=10) as old:
            old.row_factory=sqlite3.Row
            existing={r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            with conn() as pg:
                for table in ("users","tests","questions","settings","item_stats","test_attempts"):
                    if table not in existing:
                        continue
                    columns=[r[1] for r in old.execute(f"PRAGMA table_info({table})").fetchall()]
                    if not columns:
                        continue
                    rows=old.execute(f"SELECT * FROM {table}").fetchall()
                    if not rows:
                        continue
                    cols=",".join(columns);placeholders=",".join("?" for _ in columns)
                    query=f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                    pg.executemany(query,[tuple(row[col] for col in columns) for row in rows])
                pg.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",("sqlite_import_complete","1"))
    except Exception:
        import logging
        logging.getLogger("nur-oqiw.db").exception("Could not import local SQLite data into PostgreSQL; startup will continue with PostgreSQL storage.")

def ensure_schema():
    with conn() as c:
        if USE_POSTGRES:
            cols={x["column_name"] for x in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'").fetchall()};qcols={x["column_name"] for x in c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='questions'").fetchall()}
        else:
            cols={x["name"] for x in c.execute("PRAGMA table_info(users)").fetchall()};qcols={x["name"] for x in c.execute("PRAGMA table_info(questions)").fetchall()}
        for name,typ in [("state","TEXT DEFAULT 'code'"),("tier","TEXT DEFAULT 'default'"),("premium_since","TEXT"),("premium_granted_by","BIGINT"),("test_id","TEXT DEFAULT ''"),("telegram_photo","TEXT DEFAULT ''")]:
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
    allowed={"full_name","phone","registered_at","code_ok","started_at","finished_at","score","grade","answers_json","submitted","state","tier","premium_since","premium_granted_by","test_id","telegram_photo"};fields={k:v for k,v in fields.items() if k in allowed}
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

def is_paid_test(test_id):
    with conn() as c:
        return bool(c.execute("SELECT 1 FROM paid_tests WHERE test_id=? LIMIT 1",(str(test_id),)).fetchone())

def can_access_test(test_id,telegram_id,admin_id):
    if not is_paid_test(test_id):
        return True
    if int(telegram_id or 0)==int(admin_id):
        return True
    with conn() as c:
        return bool(c.execute("SELECT 1 FROM paid_test_access WHERE test_id=? AND telegram_id=? LIMIT 1",(str(test_id),int(telegram_id or 0))).fetchone())

def create_paid_test(name,code):
    tid=secrets.token_hex(8)
    now=datetime.now(timezone.utc).isoformat()
    with conn() as c:
        c.execute("INSERT INTO tests(test_id,code,name,start_time,end_time,mode,active,created_at) VALUES(?,?,?,?,?,?,1,?)",
                  (tid,str(code).strip(),str(name).strip(),"00:00","23:59","open",now))
        c.execute("INSERT INTO paid_tests(test_id,created_at) VALUES(?,?)",(tid,now))
    return get_test(tid)

def paid_access_list(test_id):
    with conn() as c:
        return c.execute("SELECT a.telegram_id,a.granted_at,u.full_name FROM paid_test_access a LEFT JOIN users u ON u.telegram_id=a.telegram_id WHERE a.test_id=? ORDER BY a.granted_at DESC",(str(test_id),)).fetchall()

def paid_grant(test_id,telegram_id,admin_id):
    if not is_paid_test(test_id):
        return False
    with conn() as c:
        c.execute("INSERT INTO paid_test_access(test_id,telegram_id,granted_by,granted_at) VALUES(?,?,?,?) ON CONFLICT(test_id,telegram_id) DO NOTHING",
                  (str(test_id),int(telegram_id),int(admin_id),datetime.now(timezone.utc).isoformat()))
    return True

def paid_revoke(test_id,telegram_id):
    with conn() as c:
        return c.execute("DELETE FROM paid_test_access WHERE test_id=? AND telegram_id=?",(str(test_id),int(telegram_id))).rowcount>0

def paid_tests_for_user(telegram_id,admin_id,active_only=False):
    rows=all_tests()
    result=[]
    for t in rows:
        if not is_paid_test(t['test_id']):continue
        if active_only and not int(t['active']):continue
        if can_access_test(t['test_id'],telegram_id,admin_id):result.append(t)
    return result

def get_test_by_code_or_name(code):
    # Exact code is always preferred; a unique exact name is a user-friendly fallback.
    t=get_test_by_code(code)
    if t:return t
    key=str(code or '').strip()
    if not key:return None
    with conn() as c:
        matches=c.execute("SELECT * FROM tests WHERE lower(name)=lower(?) LIMIT 2",(key,)).fetchall()
    return matches[0] if len(matches)==1 else None

def create_test(name,code,start_time="00:00",end_time="23:59",mode="open"):
    tid=secrets.token_hex(8)
    with conn() as c:c.execute("INSERT INTO tests(test_id,code,name,start_time,end_time,mode,active,created_at) VALUES(?,?,?,?,?,?,1,?)",(tid,str(code).strip(),str(name).strip(),start_time,end_time,mode,datetime.now(timezone.utc).isoformat()))
    return get_test(tid)

def create_test_with_questions(name,code,items,paid=False):
    """Create a complete answer key, including multi-part questions, atomically."""
    normalized=[]
    for number,item in enumerate(items,1):
        kind=str(item.get('kind','choice')).lower()
        parts=item.get('parts',[]) if kind=='multi' else [item]
        if kind=='multi' and not (2<=len(parts)<=20):
            raise ValueError('Ko‘p savolda 2–20 kichik savol bo‘lishi kerak.')
        for index,part in enumerate(parts):
            subkind=str(part.get('kind','choice')).lower()
            answer=str(part.get('answer','')).strip()
            if subkind=='choice':
                answer=answer.upper()
                if answer not in ('A','B','C','D'):raise ValueError('Variant A/B/C/D bo‘lishi kerak.')
                choices=part.get('options',['A','B','C','D'])
                if not isinstance(choices,list) or len(choices)!=4 or any(not str(x).strip() for x in choices):
                    raise ValueError('To‘rtta A/B/C/D variant matni kiritilsin.')
                options=[str(x).strip()[:400] for x in choices]
            elif subkind=='written':
                if not answer:raise ValueError('Yozma javob bo‘sh bo‘lmasin.')
                options=[]
            else:raise ValueError('Savol turi noto‘g‘ri.')
            label=str(number)+(chr(97+index) if kind=='multi' else '')
            question=str(part.get('question') or item.get('question') or (label+'-savol')).strip()[:1500]
            normalized.append((label,subkind,answer,options,question))
    if not normalized:raise ValueError('Kamida bitta savol bo‘lishi kerak.')
    tid=secrets.token_hex(8)
    with conn() as c:
        if c.execute('SELECT 1 FROM tests WHERE lower(code)=lower(?) LIMIT 1',(str(code).strip(),)).fetchone():
            raise ValueError('Bu test kodi avval ishlatilgan.')
        c.execute('INSERT INTO tests(test_id,code,name,start_time,end_time,mode,active,created_at) VALUES(?,?,?,?,?,?,1,?)',(tid,str(code).strip(),str(name).strip(),'00:00','23:59','open',datetime.now(timezone.utc).isoformat()))
        if paid:
            c.execute("INSERT INTO paid_tests(test_id,created_at) VALUES(?,?)",
                      (tid,datetime.now(timezone.utc).isoformat()))
        next_id=int(c.execute('SELECT COALESCE(MAX(id),0)+1 AS n FROM questions').fetchone()['n'])
        for offset,(label,kind,answer,options,question) in enumerate(normalized):
            c.execute('INSERT INTO questions(id,question,options_json,answer,kind,group_id,active,image_url,test_id,number) VALUES(?,?,?,?,?,?,1,?,?,?)',(next_id+offset,question,json.dumps(options,ensure_ascii=False),answer,kind,'','',tid,offset+1))
            c.execute('UPDATE questions SET group_id=? WHERE id=?',(label,next_id+offset))
    return get_test(tid)

def create_test_with_answers(name,code,answers):
    """Backward-compatible helper for legacy all-multiple-choice tests."""
    return create_test_with_questions(name,code,[{'kind':'choice','answer':x} for x in answers])
def get_test(tid):
    if not tid:return None
    with conn() as c:return c.execute("SELECT * FROM tests WHERE test_id=?",(str(tid),)).fetchone()
def get_test_by_code(code):
    # Return stopped tests too, so clients can distinguish them from unknown codes.
    with conn() as c:return c.execute("SELECT * FROM tests WHERE lower(code)=lower(?)",(str(code).strip(),)).fetchone()

def test_code_exists(code):
    with conn() as c:return bool(c.execute("SELECT 1 FROM tests WHERE lower(code)=lower(?) LIMIT 1",(str(code).strip(),)).fetchone())
def all_tests():
    # Keep stopped tests visible in the admin list; stopping is not deletion.
    with conn() as c:return c.execute("SELECT * FROM tests ORDER BY created_at DESC").fetchall()
def get_attempt(test_id,telegram_id):
    with conn() as c:return c.execute("SELECT * FROM test_attempts WHERE test_id=? AND telegram_id=?",(str(test_id),int(telegram_id))).fetchone()

def ensure_attempt(test_id,telegram_id):
    aid=secrets.token_hex(12)
    with conn() as c:
        c.execute("INSERT INTO test_attempts(attempt_id,test_id,telegram_id,answers_json,status) VALUES(?,?,?,?,?) ON CONFLICT(test_id,telegram_id) DO NOTHING",
                  (aid,str(test_id),int(telegram_id),"{}","active"))
    return get_attempt(test_id,telegram_id)

def restart_completed_attempt(test_id,telegram_id):
    """Start a fresh attempt without deleting the previous graded result.

    One active row per user/test is maintained for compatibility with the
    current schema. The completed row is copied to permanent_results before
    being reset with a NEW attempt_id, so past results remain distinct.
    """
    test_id=str(test_id)
    telegram_id=int(telegram_id)
    prior=get_attempt(test_id,telegram_id)
    if not prior:
        return "not_started"
    if not int(prior["submitted"] or 0):
        return "already_active"
    if not archive_attempt_result(prior["attempt_id"]):
        return "archive_failed"
    new_id=secrets.token_hex(12)
    with conn() as c:
        if not USE_POSTGRES:
            c.execute("BEGIN IMMEDIATE")
        suffix=" FOR UPDATE" if USE_POSTGRES else ""
        row=c.execute("SELECT attempt_id,submitted FROM test_attempts WHERE test_id=? AND telegram_id=?"+suffix,
                      (test_id,telegram_id)).fetchone()
        if not row:
            return "not_started"
        if not int(row["submitted"] or 0):
            return "already_active"
        if str(row["attempt_id"])!=str(prior["attempt_id"]):
            return "already_active"
        c.execute("""UPDATE test_attempts SET attempt_id=?,started_at=NULL,
                     finished_at=NULL,score=0,grade='',answers_json='{}',
                     submitted=0,status='active'
                     WHERE attempt_id=? AND submitted=1""",(new_id,str(row["attempt_id"])))
    return "restarted"

def update_attempt(attempt_id,**fields):
    allowed={"started_at","finished_at","score","grade","answers_json","submitted","status"}
    fields={k:v for k,v in fields.items() if k in allowed}
    if fields:
        with conn() as c:c.execute("UPDATE test_attempts SET "+",".join(f"{k}=?" for k in fields)+" WHERE attempt_id=?",list(fields.values())+[str(attempt_id)])
        if fields.get("submitted"):
            archive_attempt_result(attempt_id)

def archive_attempt_result(attempt_id):
    """Save a durable snapshot of who took which test and their result."""
    with conn() as c:
        a=c.execute("SELECT * FROM test_attempts WHERE attempt_id=?",(str(attempt_id),)).fetchone()
        if not a:return False
        t=c.execute("SELECT name,code FROM tests WHERE test_id=?",(str(a["test_id"]),)).fetchone()
        u=c.execute("SELECT full_name,phone FROM users WHERE telegram_id=?",(int(a["telegram_id"]),)).fetchone()
        now=datetime.now(timezone.utc).isoformat()
        c.execute("""INSERT INTO permanent_results
            (attempt_id,test_id,test_code,test_name,telegram_id,full_name,phone,started_at,finished_at,score,grade,answers_json,submitted,status,archived_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(attempt_id) DO UPDATE SET
              test_code=excluded.test_code,test_name=excluded.test_name,
              full_name=excluded.full_name,phone=excluded.phone,
              started_at=excluded.started_at,finished_at=excluded.finished_at,
              score=excluded.score,grade=excluded.grade,answers_json=excluded.answers_json,
              submitted=excluded.submitted,status=excluded.status""",
            (str(a["attempt_id"]),str(a["test_id"]),str(t["code"] if t else ""),str(t["name"] if t else "Test o‘chirilgan"),
             int(a["telegram_id"]),str(u["full_name"] if u else ""),str(u["phone"] if u else ""),
             a["started_at"],a["finished_at"],float(a["score"] or 0),str(a["grade"] or ""),
             str(a["answers_json"] or "{}"),int(a["submitted"] or 0),str(a["status"] or ""),now))
    return True

def archive_completed_results():
    """Backfill submitted attempts to the permanent archive on startup."""
    with conn() as c:
        ids=[r["attempt_id"] for r in c.execute("SELECT attempt_id FROM test_attempts WHERE submitted=1").fetchall()]
    for attempt_id in ids:
        try:archive_attempt_result(attempt_id)
        except Exception:
            import logging
            logging.getLogger("nur-oqiw.db").exception("Could not archive result %s",attempt_id)

def all_permanent_results(limit=200):
    with conn() as c:
        return c.execute("SELECT * FROM permanent_results ORDER BY COALESCE(finished_at,started_at,archived_at) DESC LIMIT ?",(max(1,min(int(limit),1000)),)).fetchall()

def save_attempt_answers(attempt_id,answers):
    update_attempt(attempt_id,answers_json=json.dumps(answers,ensure_ascii=False))

def completed_ranking_for_test(test_id):
    """Highest confirmed score per user, including earlier saved retakes."""
    with conn() as c:
        rows=c.execute("""SELECT r.telegram_id,r.score,r.grade,r.finished_at,
                          COALESCE(u.full_name,r.full_name,'') AS full_name,
                          COALESCE(u.telegram_photo,'') AS telegram_photo
                          FROM permanent_results r LEFT JOIN users u ON u.telegram_id=r.telegram_id
                          WHERE r.test_id=? AND r.submitted=1
                          UNION ALL
                          SELECT a.telegram_id,a.score,a.grade,a.finished_at,
                          COALESCE(u.full_name,'') AS full_name,
                          COALESCE(u.telegram_photo,'') AS telegram_photo
                          FROM test_attempts a LEFT JOIN users u ON u.telegram_id=a.telegram_id
                          WHERE a.test_id=? AND a.submitted=1
                            AND NOT EXISTS (SELECT 1 FROM permanent_results r WHERE r.attempt_id=a.attempt_id)
                       """,(str(test_id),str(test_id))).fetchall()
    winners={}
    for r in rows:
        uid=int(r["telegram_id"])
        old=winners.get(uid)
        score=float(r["score"] or 0)
        if old is None or (score,str(r["finished_at"] or ""))>(float(old["score"] or 0),str(old["finished_at"] or "")):
            winners[uid]=dict(r)
    return list(winners.values())


def test_history_for_user(user_id,viewer_id,admin_id,only_submitted=False):
    """Include archived retakes, exclude duplicates and enforce paid-test visibility."""
    with conn() as c:
        return c.execute("""SELECT h.test_id,h.test_name,h.code,h.started_at,h.finished_at,
                              h.score,h.grade,h.submitted
            FROM (
               SELECT a.attempt_id,a.test_id,COALESCE(t.name,'Test o‘chirilgan') AS test_name,
                      COALESCE(t.code,'') AS code,a.started_at,a.finished_at,a.score,a.grade,a.submitted
               FROM test_attempts a LEFT JOIN tests t ON t.test_id=a.test_id
               WHERE a.telegram_id=?
               UNION ALL
               SELECT r.attempt_id,r.test_id,r.test_name,r.test_code AS code,
                      r.started_at,r.finished_at,r.score,r.grade,r.submitted
               FROM permanent_results r WHERE r.telegram_id=? AND r.submitted=1
                 AND NOT EXISTS (SELECT 1 FROM test_attempts a WHERE a.attempt_id=r.attempt_id)
            ) h
            WHERE (?=0 OR h.submitted=1)
              AND (?=? OR NOT EXISTS (SELECT 1 FROM paid_tests p WHERE p.test_id=h.test_id)
               OR EXISTS (SELECT 1 FROM paid_test_access g WHERE g.test_id=h.test_id AND g.telegram_id=?))
            ORDER BY COALESCE(h.finished_at,h.started_at) DESC
            LIMIT 150""",(int(user_id),int(user_id),int(bool(only_submitted)),int(viewer_id),int(admin_id),int(viewer_id))).fetchall()

def all_attempts_for_test(test_id):
    with conn() as c:return c.execute("SELECT a.*,u.full_name,u.phone,u.telegram_photo FROM test_attempts a LEFT JOIN users u ON u.telegram_id=a.telegram_id WHERE a.test_id=? AND (a.started_at IS NOT NULL OR a.submitted=1) ORDER BY COALESCE(a.finished_at,a.started_at) ASC",(str(test_id),)).fetchall()

def delete_attempt(test_id,telegram_id):
    with conn() as c:return c.execute("DELETE FROM test_attempts WHERE test_id=? AND telegram_id=?",(str(test_id),int(telegram_id))).rowcount>0

def set_test_active(tid,active=1):
    with conn() as c:c.execute("UPDATE tests SET active=? WHERE test_id=?",(int(active),str(tid)))

def delete_test(tid):
    """Delete test content while preserving attempts and permanent result snapshots."""
    tid=str(tid)
    with conn() as c:
        ids=[r["attempt_id"] for r in c.execute("SELECT attempt_id FROM test_attempts WHERE test_id=?",(tid,)).fetchall()]
    for attempt_id in ids:
        archive_attempt_result(attempt_id)
    with conn() as c:
        c.execute("DELETE FROM questions WHERE test_id=?",(tid,))
        c.execute("UPDATE users SET test_id='',code_ok=0,state='code' WHERE test_id=?",(tid,))
        return c.execute("DELETE FROM tests WHERE test_id=?",(tid,)).rowcount>0
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
    # Tests must be created explicitly by the admin; never seed placeholder questions.
    # Test status is controlled only by the admin panel.
    return
def seed_defaults():init();ensure_schema();seed()
