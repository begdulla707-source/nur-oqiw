'use strict';

// One supervised child process, not another Telegram bot or public API.
// Only newline-delimited JSON over the parent's stdin/stdout is accepted.
const readline = require('node:readline');
const crypto = require('node:crypto');

function safeText(value) {
  function flatten(v) {
    if (typeof v === 'string') {
      if (/^[\s]*[\[{]/.test(v)) { try { const parsed = JSON.parse(v); if (typeof parsed === 'object') return flatten(parsed); } catch {} }
      return v;
    }
    if (Array.isArray(v)) return v.map(flatten).join('');
    if (!v || typeof v !== 'object') return '';
    if (v.type === 'string') return String(v.value || '');
    if (v.type && v.value !== undefined) return flatten(v.value);
    return ['text', 'translate', 'with', 'extra'].filter(k => v[k] !== undefined).map(k => flatten(v[k])).join('');
  }
  return flatten(value).replace(/§[0-9A-FK-OR]/ig, '')
    .replace(/\/(login|register|reg|l)\s+\S+(?:\s+\S+)?/ig, '/$1 [yashirildi]').slice(0, 1200);
}

class Manager {
  constructor({ createBot, Captcha, emit, setTimer = setTimeout, clearTimer = clearTimeout }) {
    Object.assign(this, { createBot, Captcha, emit, setTimer, clearTimer });
    this.sessions = new Map();
  }

  start(cfg) {
    if (!cfg || !/^[a-z0-9]{8,24}$/.test(cfg.id || '') ||
        !/^[A-Za-z0-9_]{3,16}$/.test(cfg.username || '') ||
        !/^[A-Za-z0-9.-]{1,253}$/.test(cfg.host || '') ||
        !Number.isInteger(cfg.port) || cfg.port < 1 || cfg.port > 65535) throw new Error('invalid account');
    this.stop(cfg.id, false);
    const s = { cfg, live: true, bot: null, delay: 30000, timers: new Set(), generation: 0,
      waiting: null, sentCaptcha: false, loginNeeded: false, lastJoin: 0, status: 'connecting' };
    this.sessions.set(cfg.id, s);
    this.connect(s);
  }

  later(s, fn, ms) {
    const t = this.setTimer(() => { s.timers.delete(t); if (s.live) fn(); }, ms);
    s.timers.add(t);
    return t;
  }

  clearTimers(s) { for (const t of s.timers) this.clearTimer(t); s.timers.clear(); }

  connect(s) {
    if (!s.live) return;
    s.status = 'connecting'; s.waiting = null; s.sentCaptcha = false; s.loginNeeded = false; s.lastKick = '';
    const generation = ++s.generation;
    this.emit({ event: 'status', id: s.cfg.id, status: 'connecting' });
    let bot;
    try {
      const version = s.cfg.version || (s.cfg.host.toLowerCase() === 'mc.minestax.uz' ? '1.16.5' : false);
      bot = this.createBot({ host: s.cfg.host, port: s.cfg.port, username: s.cfg.username,
        auth: 'offline', version, viewDistance: 'tiny', connectTimeout: 20000 });
      s.bot = bot;
      const captcha = new this.Captcha(bot, { delay: 200 });
      let imageTimer = null, bestImage = null, reachedLogin = false;
      let imageDeadline = Date.now() + 120000;
      const capture = ({ data, image }) => {
        if (!s.live || generation !== s.generation || s.sentCaptcha || Date.now() > imageDeadline || !image) return;
        const score = (data?.facing === 'forward' ? 1000 : 0) + (data?.frames?.length || 0);
        if (!bestImage || score >= bestImage.score) bestImage = { image, score };
        s.waiting = { state: 'assembling' };
        if (imageTimer) return;
        imageTimer = this.later(s, async () => {
          try {
            if (!s.live || generation !== s.generation || s.sentCaptcha) return;
            const candidate = bestImage; imageTimer = null; bestImage = null;
            if (!candidate) return;
            const bytes = await candidate.image.png().toBuffer();
            if (!s.live || generation !== s.generation || s.sentCaptcha || bytes.length > 1500000) return;
            const challenge = crypto.randomBytes(8).toString('hex');
            s.waiting = { state: 'ready', challenge };
            s.sentCaptcha = true;
            this.emit({ event: 'captcha', id: s.cfg.id, challenge, image: bytes.toString('base64') });
          } catch { this.emit({ event: 'error', id: s.cfg.id, code: 'captcha_image_failed' }); }
        }, 1100);
      };
      captcha.on('imageReady', capture);
      captcha.on('inventoryInfo', capture);
      bot.on('login', () => {
        if (!s.live || generation !== s.generation) return;
        reachedLogin = true; s.status = 'verifying';
        this.emit({ event: 'status', id: s.cfg.id, status: 'verifying' });
      });
      this.later(s, () => {
        if (!reachedLogin && s.bot && generation === s.generation) {
          s.lastKick = 'Ulanish vaqti tugadi';
          try { s.bot.quit(); } catch {}
        }
      }, 30000);
      bot.on('spawn', () => {
        if (!s.live || generation !== s.generation) return;
        s.status = 'connected'; this.emit({ event: 'status', id: s.cfg.id, status: 'connected' });
        this.later(s, () => { s.delay = 30000; }, 90000);
        this.scheduleJoin(s, generation, 12000);
      });
      bot.on('messagestr', (message, position, _json, sender) => {
        if (!s.live || generation !== s.generation) return;
        const safe = safeText(String(message || ''));
        if (!safe) return;
        // Ordinary chat is shown only to the owner's private Telegram chat.
        this.emit({ event: 'chat', id: s.cfg.id, text: safe, position });
        if (sender) return;
        if (/(?:captcha|капч).{0,40}(?:wrong|incorrect|invalid|неверн|noto.g.ri|xato)/i.test(safe)) {
          s.sentCaptcha = false; s.waiting = null; imageDeadline = Date.now() + 120000;
        }
        if (/\/(?:login|register|reg)\b|авторизац|войдите|log\s*in/i.test(safe)) {
          s.loginNeeded = true;
          this.emit({ event: 'status', id: s.cfg.id, status: 'login_needed', auth_mode: /register|регистрац|\breg\b/i.test(safe) ? 'register' : 'login' });
        }
        if (/successfully (?:logged|authenticated)|успешн.{0,30}(?:вход|авторизац)|muvaffaqiyatli.{0,30}(?:kir|tasdiq)/i.test(safe)) {
          s.loginNeeded = false; this.scheduleJoin(s, generation, 4000);
        }
        if (/\b(?:lobby|hub)\b|лобби|хаб/i.test(safe)) this.scheduleJoin(s, generation, 10000);
        if (/(?:server|сервер).{0,30}(?:full|полон|to.la)|(?:full|полон).{0,30}(?:server|сервер)/i.test(safe))
          this.scheduleJoin(s, generation, 60000);
      });
      bot.on('kicked', reason => { if (generation === s.generation) s.lastKick = safeText(reason); });
      bot.on('error', error => this.emit({ event: 'error', id: s.cfg.id, code: 'connection_error', detail: safeText(error?.message || '') }));
      let ended = false;
      bot.on('end', () => {
        if (ended || generation !== s.generation) return; ended = true;
        this.clearTimers(s); s.bot = null; s.waiting = null; s.status = 'reconnecting';
        this.emit({ event: 'status', id: s.cfg.id, status: 'reconnecting', reason: s.lastKick, retry_seconds: Math.round(s.delay / 1000) });
        const delay = s.delay; s.delay = Math.min(s.delay * 2, 300000);
        this.later(s, () => this.connect(s), delay);
      });
    } catch {
      s.bot = null; s.status = 'reconnecting';
      this.emit({ event: 'error', id: s.cfg.id, code: 'start_failed' });
      const delay = s.delay; s.delay = Math.min(s.delay * 2, 300000);
      this.later(s, () => this.connect(s), delay);
    }
  }

  scheduleJoin(s, generation, delay) {
    this.later(s, () => {
      if (!s.bot || s.bot._client?.state !== 'play' || generation !== s.generation || s.waiting || s.loginNeeded ||
          Date.now() - s.lastJoin < 55000) return;
      if (s.cfg.host.toLowerCase() !== 'mc.minestax.uz') return;
      try { s.bot.chat('/boxpvp'); s.lastJoin = Date.now(); this.emit({ event: 'status', id: s.cfg.id, status: 'joining_mode' }); }
      catch { this.emit({ event: 'error', id: s.cfg.id, code: 'join_failed' }); }
    }, delay);
  }

  answer(id, challenge, text) {
    const s = this.sessions.get(id);
    if (!s?.bot || s.bot._client?.state !== 'play' || !s.waiting || s.waiting.challenge !== challenge || !/^[A-Za-z0-9]{1,32}$/.test(text)) return false;
    try { s.bot.chat(text); } catch { return false; }
    s.waiting = null;
    this.emit({ event: 'captcha_submitted', id, challenge });
    this.scheduleJoin(s, s.generation, 10000);
    return true;
  }

  message(id, text) {
    const s = this.sessions.get(id);
    if (!s?.bot || s.bot._client?.state !== 'play' || typeof text !== 'string' || !text.trim() || text.length > 256 || /[\r\n]/.test(text)) return false;
    try { s.bot.chat(text); return true; } catch { return false; }
  }

  tab(id) {
    const s = this.sessions.get(id);
    if (!s?.bot || s.bot._client?.state !== 'play' || !s.bot.players) return null;
    return Object.keys(s.bot.players).filter(name => /^[A-Za-z0-9_]{1,16}$/.test(name)).sort().slice(0, 200);
  }

  stop(id, notify = true) {
    const s = this.sessions.get(id); if (!s) return;
    s.live = false; s.generation++; this.clearTimers(s); this.sessions.delete(id);
    try { s.bot?.quit(); } catch {}
    if (notify) this.emit({ event: 'status', id, status: 'stopped' });
  }

  command(c) {
    try {
      let result = true;
      if (c.action === 'start') this.start(c.account);
      else if (c.action === 'stop') this.stop(c.id);
      else if (c.action === 'message') result = this.message(c.id, c.text);
      else if (c.action === 'answer') result = this.answer(c.id, c.challenge, c.text);
      else if (c.action === 'tab') result = this.tab(c.id);
      else if (c.action === 'shutdown') { for (const id of this.sessions.keys()) this.stop(id, false); }
      else result = false;
      if (c.request) this.emit({ event: 'result', request: c.request, result });
    } catch { if (c.request) this.emit({ event: 'result', request: c.request, result: false }); }
  }
}

if (require.main === module) {
  const { createBot } = require('mineflayer');
  const Captcha = require('flayercaptcha');
  // Third-party diagnostics go to stderr; stdout is reserved for framed JSON.
  console.log = console.info = console.warn = console.error = (...args) => process.stderr.write(args.map(String).join(' ') + '\n');
  const manager = new Manager({ createBot, Captcha, emit: data => process.stdout.write(JSON.stringify(data) + '\n') });
  readline.createInterface({ input: process.stdin, crlfDelay: Infinity }).on('line', line => {
    if (line.length > 8192) return;
    try { manager.command(JSON.parse(line)); } catch {}
  }).on('close', () => { manager.command({ action: 'shutdown' }); process.exit(0); });
}

module.exports = { Manager, safeText };
