"""Offline regression tests for group commands and authorization boundaries."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot import group_features as g

class GroupCommandTests(unittest.TestCase):
    def test_ten_commands_and_placeholders(self):
        self.assertEqual(len(g.COMMANDS),10)
        self.assertEqual(set(g.DEFAULTS),set(g.COMMANDS))
        rendered=g._render("status","all",{
            "group_name":"A & <B>","members":"248","admins_count":"4",
            "active_24h":"63","bot_status":"Faol","online_note":"Aniq online yo‘q",
        })
        self.assertIn("A &amp; &lt;B&gt;",rendered)
        self.assertIn("63",rendered)

    def test_group_only_public_handlers_and_private_admin(self):
        fake_core=SimpleNamespace(ADMIN=12345,admin_kb=lambda:None)
        user=SimpleNamespace(id=5555)
        group=SimpleNamespace(type="supergroup")
        message=SimpleNamespace(from_user=user,chat=group,text="Guruh sozlamalari")
        result=asyncio.run(g._handle_admin_text(message,None,fake_core))
        self.assertIs(result,False)

    def test_global_template_and_group_override(self):
        storage={}
        with patch.object(g.db,"get_setting",side_effect=lambda k,d=None:storage.get(k,d)),\
             patch.object(g.db,"set_setting",side_effect=lambda k,v:storage.__setitem__(k,v)):
            g._set_record("staff",{"template":"Salom {group_name}"},"all")
            g._set_record("staff",{"template":"Boshqa {group_name}"},"-1001")
            self.assertEqual(g._template("staff","all"),"Salom {group_name}")
            self.assertEqual(g._template("staff","-1001"),"Boshqa {group_name}")
            self.assertEqual(g._template("staff","-1002"),"Salom {group_name}")
            g._set_record("staff",{},scope="-1001",reset=True)
            self.assertEqual(g._template("staff","-1001"),"Salom {group_name}")

    def test_user_link_escaped(self):
        row={"user_id":12,"display_name":"A & <B>","username":""}
        result=g._user_link(row)
        self.assertIn("A &amp; &lt;B&gt;",result)
        self.assertIn("tg://user?id=12",result)

    def test_reply_copy_limit(self):
        self.assertIsNotNone(g._copy_markup("<b>Testing</b>"))
        self.assertIsNone(g._copy_markup("x"*257))

if __name__=="__main__":
    unittest.main()
