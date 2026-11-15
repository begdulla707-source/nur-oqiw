import asyncio
import importlib.util
import json
import sys
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

MODULE=Path(__file__).resolve().parents[1]/"bot"/"minecraft_chat.py"
sys.path.insert(0,str(MODULE.parents[1]))
spec=importlib.util.spec_from_file_location("bot.minecraft_chat",MODULE)
mc=importlib.util.module_from_spec(spec);spec.loader.exec_module(mc)


class Observer:
    def __init__(self):self.callbacks=[]
    def __call__(self,*args,**kwargs):
        def decorate(fn):self.callbacks.append(fn);return fn
        return decorate


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        import os
        self.old=os.environ.get("NUR_CHAT_DB")
        os.environ["NUR_CHAT_DB"]=str(Path(self.temp.name)/"chat.db")
        self.addCleanup(lambda: os.environ.pop("NUR_CHAT_DB",None) if self.old is None else os.environ.__setitem__("NUR_CHAT_DB",self.old))
        self.core=SimpleNamespace(app=FastAPI(),dp=SimpleNamespace(message=Observer(),callback_query=Observer()),ADMIN=12345,bot=SimpleNamespace(send_message=AsyncMock()),update_user=lambda *a,**k:None,set_setting=lambda *a:None,admin_kb=lambda:None)
        self.store=mc.install(self.core)
        self.http=TestClient(self.core.app)
        self.addCleanup(self.http.close)

    def pair(self):
        code=self.store.new_code(self.core.ADMIN)
        response=self.http.post(mc.PREFIX+"/pair",json={"code":code,"player":"janzakov","installed_at":mc.now(),"consent":True})
        self.assertEqual(response.status_code,200,response.text)
        return response.json(),code

    def event(self,kind="chat",text="Salom"):
        return {"id":str(uuid.uuid4()),"session":str(uuid.uuid4()),"player":"janzakov","server":"mineblaze.net","kind":kind,"text":text,"at":mc.now()}

    def send(self,pair,events):
        return self.http.post(mc.PREFIX+"/events",json={"events":events},headers={"Authorization":"Bearer "+pair["token"]})

    def test_health(self):
        self.assertTrue(self.http.get(mc.PREFIX+"/health").json()["consent_required"])

    def auto_pair(self,key=None,install=None,consent=True):
        key=key or self.store.new_enrollment(12345)
        install=install or str(uuid.uuid4())+str(uuid.uuid4())
        r=self.http.post(mc.PREFIX+'/auto-pair',json={'enrollment':key,'install_key':install,'player':'janzakov','installed_at':mc.now(),'consent':consent})
        return r,key,install

    def test_code_free_pairing_requires_visible_consent(self):
        r,_,_=self.auto_pair(consent=False)
        self.assertEqual(r.status_code,400)

    def test_code_free_one_installation_and_safe_retry(self):
        first,key,install=self.auto_pair()
        self.assertEqual(first.status_code,200,first.text)
        again,_,_=self.auto_pair(key,install)
        self.assertEqual(first.json()['device_id'],again.json()['device_id'])
        self.assertEqual(first.json()['token'],again.json()['token'])
        other,_,_=self.auto_pair(key)
        self.assertEqual(other.status_code,403)

    def test_code_free_revocation_cannot_repair_silently(self):
        r,key,install=self.auto_pair();p=r.json()
        self.store.revoke(12345,p['device_id'])
        self.assertEqual(self.auto_pair(key,install)[0].status_code,403)

    def test_global_sms_off_stops_collection_and_on_resumes(self):
        p,_=self.pair();headers={'Authorization':'Bearer '+p['token']}
        self.store.set_pref('reports_enabled',False)
        self.assertFalse(self.http.get(mc.PREFIX+'/status',headers=headers).json()['reporting'])
        response=self.send(p,[self.event()])
        self.assertEqual(response.json()['accepted'],0)
        self.assertFalse(response.json()['reporting'])
        self.assertEqual(self.store.history(12345,p['device_id']),[])
        self.store.set_pref('reports_enabled',True)
        self.assertTrue(self.http.get(mc.PREFIX+'/status',headers=headers).json()['reporting'])
        self.assertEqual(self.send(p,[self.event()]).json()['accepted'],1)

    def test_device_off_stops_collection(self):
        p,_=self.pair();self.store.toggle(12345,p['device_id'])
        self.assertEqual(self.send(p,[self.event()]).json()['accepted'],0)
        device=self.store.authenticate(p['token'])
        self.assertEqual(self.store.record(device,[self.event()]),0)

    def test_old_queue_cannot_replay_after_sms_off_on(self):
        p,_=self.pair();old=self.store.control(p['device_id'])
        self.store.set_pref('reports_enabled',False)
        self.store.set_pref('reports_enabled',True)
        response=self.http.post(mc.PREFIX+'/events',json={'events':[self.event()],'control':old},headers={'Authorization':'Bearer '+p['token']})
        self.assertEqual(response.json()['accepted'],0)
        self.assertNotEqual(response.json()['control'],old)

    def test_report_custom_emoji_keeps_escaping(self):
        icon={'id':'1234567890123','fallback':'⭐'}
        self.assertIn('<tg-emoji emoji-id="1234567890123">⭐</tg-emoji>',mc.report(self.event(text='<fake>'),icon))
        self.assertIn('&lt;fake&gt;',mc.report(self.event(text='<fake>'),icon))

    def test_section_premium_emoji_input_is_persisted(self):
        self.store.set_pref('emoji_pending','messages')
        receiver=next(fn for fn in self.core.dp.message.callbacks if fn.__name__=='receive_emoji')
        message=SimpleNamespace(from_user=SimpleNamespace(id=12345),chat=SimpleNamespace(type='private'),text='⭐',entities=[SimpleNamespace(type='custom_emoji',custom_emoji_id='1234567890123',offset=0,length=1)],answer=AsyncMock())
        asyncio.run(receiver(message))
        self.assertEqual(self.store.get_pref('emoji:messages'),{'id':'1234567890123','fallback':'⭐'})
        self.assertIsNone(self.store.get_pref('emoji_pending'))

    def test_section_buttons_have_native_styles_and_custom_icons(self):
        m=mc.markup([[('Saqlash','a'),('To‘xtatish','b'),('Ko‘k','c')]],'1234567890123')
        buttons=m.model_dump(exclude_none=True)['inline_keyboard'][0]
        self.assertEqual([b['style'] for b in buttons],['success','danger','primary'])
        self.assertTrue(all(b['icon_custom_emoji_id']=='1234567890123' for b in buttons))

    def test_requires_consent(self):
        code=self.store.new_code(12345)
        r=self.http.post(mc.PREFIX+"/pair",json={"code":code,"player":"janzakov","installed_at":mc.now()})
        self.assertEqual(r.status_code,400)

    def test_pairing_one_time_and_token_hashed(self):
        pair,code=self.pair()
        r=self.http.post(mc.PREFIX+"/pair",json={"code":code,"player":"janzakov","installed_at":mc.now(),"consent":True})
        self.assertEqual(r.status_code,403)
        with self.store.connect() as c:
            row=c.execute("SELECT * FROM devices").fetchone()
            self.assertNotEqual(row["token_hash"],pair["token"])
            self.assertEqual(row["token_hash"],mc.digest(pair["token"]))

    def test_expired_pairing(self):
        code=self.store.new_code(12345)
        with self.store.connect() as c:c.execute("UPDATE pairing SET expires=?",(time.time()-1,))
        self.assertIsNone(self.store.pair(code,"janzakov",mc.now()))

    def test_no_auth_rejected(self):
        self.assertEqual(self.http.post(mc.PREFIX+"/events",json={"events":[self.event()]}).status_code,403)

    def test_idempotent_chat_and_promo(self):
        p,_=self.pair();events=[self.event("join",""),self.event(),self.event("command","promo TEST123")]
        self.assertEqual(self.send(p,events).json()["accepted"],3)
        self.assertEqual(self.send(p,events).json()["accepted"],0)
        h=self.store.history(12345,p["device_id"])
        self.assertEqual(len(h),3);self.assertEqual(h[0]["text"],"/promo TEST123")

    def test_secret_commands_discarded_on_server(self):
        p,_=self.pair()
        events=[self.event("command","login test-password"),self.event("command","authme:register test-password test-password"),self.event("chat","/l test-password"),self.event("command","nurchat PAIRCODE")]
        self.assertEqual(self.send(p,events).json()["accepted"],0)
        self.assertEqual(self.store.history(12345,p["device_id"]),[])

    def test_labeled_credentials_redacted(self):
        p,_=self.pair();raw="parol: test-password token=sk-123456789012345678901234"
        self.send(p,[self.event("chat",raw)])
        text=self.store.history(12345,p["device_id"])[0]["text"]
        self.assertNotIn("test-password",text);self.assertNotIn("sk-123",text)

    def test_batch_validation_atomic(self):
        p,_=self.pair();e=self.event();e["kind"]="keystroke"
        self.assertEqual(self.send(p,[self.event(),e]).status_code,400)
        self.assertEqual(self.store.history(12345,p["device_id"]),[])

    def test_revoke_immediate(self):
        p,_=self.pair();self.store.revoke(12345,p["device_id"])
        self.assertEqual(self.send(p,[self.event()]).status_code,403)

    def test_owner_isolation(self):
        p,_=self.pair();self.send(p,[self.event()])
        self.assertIsNone(self.store.device(98765,p["device_id"]))
        self.assertEqual(self.store.history(98765,p["device_id"]),[])
        self.store.revoke(98765,p["device_id"])
        self.assertIsNotNone(self.store.authenticate(p["token"]))

    def test_heartbeat_updates_without_log_or_notification(self):
        p,_=self.pair()
        self.assertEqual(self.send(p,[self.event("heartbeat","")]).json()["accepted"],0)
        self.assertEqual(self.store.device(12345,p["device_id"])["last_server"],"mineblaze.net")
        self.assertEqual(self.store.pending(),[])

    def test_html_escaped(self):
        e=self.event(text="<b>user text</b>")
        self.assertIn("&lt;b&gt;",mc.report(e))
        self.assertNotIn("<b>user text",mc.report(e))

    def test_only_admin_private_callback(self):
        callback=self.core.dp.callback_query.callbacks[0]
        for uid,kind in [(999,"private"),(12345,"group")]:
            q=SimpleNamespace(from_user=SimpleNamespace(id=uid),message=SimpleNamespace(chat=SimpleNamespace(type=kind)),answer=AsyncMock(),data="mcchat:code")
            asyncio.run(callback(q))
            self.assertTrue(q.answer.call_args.kwargs.get("show_alert"))
        with self.store.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM pairing").fetchone()[0],0)

    def test_delivery_worker_format_and_persistence(self):
        p,_=self.pair();self.send(p,[self.event("join","")])
        with TestClient(self.core.app):time.sleep(0.2)
        self.core.bot.send_message.assert_awaited()
        call=self.core.bot.send_message.call_args
        self.assertEqual(call.args[0],12345)
        self.assertIn("IP: <code>mineblaze.net</code>",call.args[1])
        self.assertIn("Kirdi:",call.args[1])
        with self.store.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM events").fetchone()[0],1)


if __name__=="__main__":unittest.main(verbosity=2)
