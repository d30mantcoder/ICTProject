// Render the generated ERD and architecture SVG files to PNG with Chrome's CDP.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const out = path.join(root, 'evidence');
const chrome = spawn('/usr/bin/google-chrome', [
  '--headless=new', '--no-sandbox', '--disable-gpu',
  '--remote-debugging-port=9223', '--remote-allow-origins=*',
  '--user-data-dir=/tmp/study-lms-diagram-profile', 'about:blank'
], { stdio: 'ignore' });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  await sleep(500);
  for (const [svg, png] of [['erd.svg', 'erd.png'], ['architecture.svg', 'architecture.png'], ['updated-architecture.svg', 'updated-architecture.png']]) {
    const target = await fetch('http://127.0.0.1:9223/json/new?about:blank', { method: 'PUT' }).then(r => r.json());
    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.addEventListener('open', resolve, { once: true });
      ws.addEventListener('error', reject, { once: true });
    });
    let id = 0;
    const pending = new Map();
    ws.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      const resolve = pending.get(message.id);
      if (resolve) { pending.delete(message.id); message.error ? resolve.reject(message.error) : resolve.resolve(message.result); }
    });
    const call = (method, params = {}) => new Promise((resolve, reject) => {
      const requestId = ++id;
      pending.set(requestId, { resolve, reject });
      ws.send(JSON.stringify({ id: requestId, method, params }));
    });
    await call('Page.enable');
    await call('Page.navigate', { url: `file://${path.join(out, svg)}` });
    await sleep(700);
    const screenshot = await call('Page.captureScreenshot', { format: 'png', fromSurface: true, captureBeyondViewport: true });
    fs.writeFileSync(path.join(out, png), Buffer.from(screenshot.data, 'base64'));
    ws.close();
  }
  console.log('Rendered ERD and architecture screenshots.');
} finally {
  chrome.kill('SIGTERM');
}
