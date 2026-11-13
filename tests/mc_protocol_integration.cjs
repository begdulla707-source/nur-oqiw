'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const mc = require('minecraft-protocol');
const mineflayer = require('mineflayer');
const FlayerCaptcha = require('flayercaptcha');
const { Manager } = require('../bot/mc_client.cjs');

test('connects, sends chat and reconnects to an isolated local Minecraft server', { timeout: 20000 }, async () => {
  const server = mc.createServer({ 'online-mode': false, version: '1.16.5', host: '127.0.0.1', port: 0 });
  await once(server, 'listening');
  const login = require('minecraft-data')(server.version).loginPacket;
  let joined = 0, received; const receivedPackets = [];
  let firstClient = null;
  let chatResolve;
  const chat = new Promise(resolve => { chatResolve = resolve; });
  server.on('playerJoin', client => {
    joined++; if (!firstClient) firstClient = client;
    client.on('error', () => {});
    client.on('packet', (_data, meta) => receivedPackets.push(meta.name));
    client.on('chat', packet => { received = packet.message; chatResolve(); });
    client.write('login', { entityId: client.id, isHardcore: false, gameMode: 0,
      previousGameMode: 1, worldNames: login.worldNames, dimensionCodec: login.dimensionCodec,
      dimension: login.dimension, worldName: 'minecraft:overworld', hashedSeed: [0, 0],
      maxPlayers: 20, viewDistance: 10, reducedDebugInfo: false, enableRespawnScreen: true,
      isDebug: false, isFlat: false });
    client.write('position', { x: 0, y: 2, z: 0, yaw: 0, pitch: 0, flags: 0 });
    client.write('update_health', { health: 20, food: 20, foodSaturation: 5 });
  });
  const events = [];
  let connected;
  const spawned = new Promise(resolve => { connected = resolve; });
  const manager = new Manager({ createBot: mineflayer.createBot, Captcha: FlayerCaptcha,
    emit: e => { events.push(e); if (e.event === 'status' && e.status === 'connected') connected(); } });
  try {
    manager.start({ id: 'abcde123', username: 'TestBot', host: '127.0.0.1',
      port: server.socketServer.address().port, version: '1.16.5' });
    await Promise.race([spawned, new Promise((_, reject) => setTimeout(() => reject(new Error('no spawn; joins=' + joined + ' events=' + JSON.stringify(events))), 5000))]);
    assert.equal(manager.message('abcde123', '/testcommand'), true);
    await Promise.race([chat, new Promise((_, reject) => setTimeout(() => reject(new Error('chat not received; packets=' + JSON.stringify(receivedPackets) + ' events=' + JSON.stringify(events))), 5000))]);
    assert.equal(received, '/testcommand');
    manager.sessions.get('abcde123').delay = 150;
    firstClient.end('simulated restart');
    for (let i = 0; i < 80 && joined < 2; i++) await new Promise(resolve => setTimeout(resolve, 50));
    assert.ok(joined >= 2, 'reconnected after disconnect');
    assert.ok(events.some(e => e.status === 'reconnecting'));
  } finally {
    manager.stop('abcde123', false);
    server.close();
  }
});
