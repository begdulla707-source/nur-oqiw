'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { Manager } = require('../bot/mc_client.cjs');

function fixture() {
  const events = [], bots = [], scheduled = [];
  class Captcha extends EventEmitter { constructor(bot) { super(); bot.captcha = this; } }
  const manager = new Manager({
    Captcha,
    createBot: options => {
      const bot = new EventEmitter(); bot.options = options; bot.sent = [];
      bot.chat = text => bot.sent.push(text); bot.quit = () => {}; bot.players = { Alex: {}, Steve: {} };
      bots.push(bot); return bot;
    },
    emit: event => events.push(event),
    setTimer: (fn, ms) => { const t = { fn, ms, cancelled: false }; scheduled.push(t); return t; },
    clearTimer: t => { t.cancelled = true; }
  });
  const start = id => manager.start({ id, username: 'TestBot', host: 'mc.minestax.uz', port: 25565 });
  return { manager, events, bots, scheduled, start };
}

test('captcha challenge is account-scoped, answered once, and old code rejected', async () => {
  const f = fixture(); f.start('abcde123'); f.start('abcde456');
  const image = { png: () => ({ toBuffer: async () => Buffer.from('png-test') }) };
  f.bots[0].captcha.emit('imageReady', { data: { facing: 'forward' }, image });
  await f.scheduled.find(t => t.ms === 800).fn();
  const event = f.events.find(x => x.event === 'captcha');
  assert.equal(event.id, 'abcde123');
  assert.equal(f.manager.answer('abcde456', event.challenge, 'Ab9'), false);
  assert.equal(f.manager.answer('abcde123', 'stale', 'Ab9'), false);
  assert.equal(f.manager.answer('abcde123', event.challenge, 'Ab9'), true);
  assert.equal(f.manager.answer('abcde123', event.challenge, 'Ab9'), false);
  assert.deepEqual(f.bots[0].sent, ['Ab9']);
  assert.deepEqual(f.bots[1].sent, []);
});

test('disconnect invalidates captcha and schedules increasing reconnect delay', () => {
  const f = fixture(); f.start('abcde123'); const first = f.bots[0];
  first.emit('end');
  assert.equal(f.manager.message('abcde123', 'hello'), false);
  const timer = f.scheduled.find(t => t.ms === 30000 && !t.cancelled);
  assert.ok(timer); timer.fn();
  assert.equal(f.bots.length, 2);
  f.bots[1].emit('end');
  assert.ok(f.scheduled.some(t => t.ms === 60000 && !t.cancelled));
  f.manager.stop('abcde123');
});

test('commands, player list, login waiting and BoxPvP start are isolated', () => {
  const f = fixture(); f.start('abcde123'); const bot = f.bots[0];
  assert.deepEqual(f.manager.tab('abcde123'), ['Alex', 'Steve']);
  assert.equal(f.manager.message('abcde123', '/spawn'), true);
  assert.equal(f.manager.message('abcde123', 'a\nb'), false);
  bot.emit('spawn');
  bot.emit('messagestr', 'Please /login password', 'system', null, null);
  f.scheduled.find(t => t.ms === 12000).fn();
  assert.deepEqual(bot.sent, ['/spawn']);
  bot.emit('messagestr', 'Successfully logged in', 'system', null, null);
  f.scheduled.find(t => t.ms === 4000).fn();
  assert.deepEqual(bot.sent, ['/spawn', '/boxpvp']);
});
