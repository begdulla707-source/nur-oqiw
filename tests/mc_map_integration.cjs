'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const FlayerCaptcha = require('flayercaptcha');
const { Manager } = require('../bot/mc_client.cjs');

test('a real framed-map renderer emits a PNG and forwards the answer', { timeout: 8000 }, async () => {
  const sent = [];
  let captchaEvent;
  const eventReady = new Promise(resolve => { captchaEvent = resolve; });
  let fakeBot;
  class Captcha extends FlayerCaptcha {
    constructor(bot, options) { super(bot, options); bot.captcha = this; }
  }
  const manager = new Manager({ Captcha,
    createBot: () => {
      const bot = new EventEmitter(); bot._client = new EventEmitter(); bot._client.state = 'play';
      bot.entity = { position: { x: 0, y: 64, z: 0 }, yaw: Math.PI, pitch: 0 };
      bot.chat = msg => sent.push(msg); bot.quit = () => {};
      fakeBot = bot; return bot;
    },
    emit: event => { if (event.event === 'captcha') captchaEvent(event); }
  });
  try {
    manager.start({ id: 'abcde123', username: 'TestBot', host: 'mc.minestax.uz', port: 25565 });
    fakeBot.captcha.setEntityMapData({ entityFrameId: 1, mapId: 10, rotate: 0,
      coordinate: { x: 0, y: 64, z: 2 }, viewDirection: 'north' });
    fakeBot.captcha.setMapImageBuffer(10, Buffer.alloc(128 * 128, 34));
    const result = await eventReady;
    assert.equal(Buffer.from(result.image, 'base64').subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
    assert.equal(manager.answer('abcde123', result.challenge, 'Aa09'), true);
    assert.deepEqual(sent, ['Aa09']);
  } finally { manager.stop('abcde123', false); }
});
