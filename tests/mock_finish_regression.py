"""Exercise the Mini App endpoints against a disposable local database."""
import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ['DATABASE_URL'] = ''
os.environ['BOT_TOKEN'] = '123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi'
os.environ['MCWEB_READY'] = '0'

from bot import db

temporary = tempfile.TemporaryDirectory()
db.DB = Path(temporary.name) / 'test.db'
from bot import main as core
from bot import features_v2
from starlette.requests import Request

core.telegram_user = lambda raw: int(raw)


class FakeBot:
 async def send_message(self, *args, **kwargs):
  return None


features_v2.BOT = FakeBot()


def endpoint(path, method):
 return next(route.endpoint for route in core.app.routes
             if getattr(route, 'path', '') == path and method in getattr(route, 'methods', set()))


def request(method, user, code):
 return Request({'type': 'http', 'method': method, 'path': '/',
                 'headers': [(b'authorization', ('tma ' + str(user)).encode())],
                 'query_string': ('code=' + code).encode()})


async def main():
 test = db.create_mock_test('Regression mock', 30)
 test_id = test['test_id']
 db.set_mock_test_code(test_id, '987654')
 db.upsert_test_question(test_id, 1, '1-savol', ['A', 'B', 'C', 'D'], 'A', 'choice')
 db.upsert_test_question(test_id, 2, '2-savol', [], '1/2', 'written')
 now = datetime.now(core.TZ)
 db.start_mock_timer(test_id, now.isoformat(), (now + timedelta(minutes=30)).isoformat())
 state = endpoint('/api/test/state', 'GET')
 answer = endpoint('/api/test/answer', 'POST')
 finish = endpoint('/api/test/finish', 'POST')

 for user, initial_start in [(201, ''), (202, None)]:
  db.ensure_user(user)
  db.update_user(user, test_id=test_id, code_ok=1)
  a = db.ensure_attempt(test_id, user)
  if initial_start == '':
   db.update_attempt(a['attempt_id'], started_at='')
  result = await state(request('GET', user, '987654'))
  assert result['ok'], result
  assert db.get_attempt(test_id, user)['started_at'], 'state returned success without starting the attempt'
  for q, value in [(1, 'A'), (2, '1/2')]:
   result = await answer({'code': '987654', 'question_id': q, 'answer': value}, request('POST', user, '987654'))
   assert result['ok'], result
  result = await finish({'code': '987654', 'participant_name': 'Test User'}, request('POST', user, '987654'))
  assert result['ok'] and result['is_mock'], result
  saved = db.get_attempt(test_id, user)
  assert saved['submitted'] and json.loads(saved['answers_json'])['2'] == '1/2'
  assert db.get_test(test_id)['active'], 'one participant must not close the shared test'
  result = await finish({'code': '987654', 'participant_name': 'Test User'}, request('POST', user, '987654'))
  assert result['ok'], result

 db.ensure_user(203)
 result = await finish({'code': '987654', 'participant_name': 'Other User'}, request('POST', 203, '987654'))
 assert not result['ok'] and result['error'] == 'test_not_started', result
 print('PASS: started attempts finish and retain answers while the MOCK stays active; retries are safe; unstarted attempts are rejected')


asyncio.run(main())
