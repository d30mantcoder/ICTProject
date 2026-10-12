// Capture reproducible UI evidence using installed Google Chrome and its built-in CDP client.
// The teacher demo change is always restored to its original database values afterward.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const out = path.join(root, 'evidence');
fs.mkdirSync(out, { recursive: true });
const chrome = spawn('/usr/bin/google-chrome', [
  '--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage',
  '--remote-debugging-port=9222','--remote-allow-origins=*',
  '--allow-file-access-from-files','--user-data-dir=/tmp/study-lms-evidence-profile','about:blank'
], { stdio: 'ignore' });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function target(url) {
  for (let i=0; i<60; i++) {
    try { return await fetch(`http://127.0.0.1:9222/json/new?${encodeURIComponent(url)}`, {method:'PUT'}).then(r=>r.json()); }
    catch { await sleep(200); }
  }
  throw new Error('Chrome DevTools did not start');
}
function connect(info) {
  const ws = new WebSocket(info.webSocketDebuggerUrl); let seq=0; const pending=new Map();
  ws.addEventListener('message', e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}});
  const ready=new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true})});
  const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
  const evaluate=async expression=>(await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true})).result.value;
  return {ws,ready,call,evaluate};
}
async function snap(url, filename, setup) {
 const c=connect(await target(url)); await c.ready; await c.call('Page.enable'); await c.call('Runtime.enable');
 await c.call('Emulation.setDeviceMetricsOverride',{width:1440,height:640,deviceScaleFactor:1,mobile:false});
 await sleep(1800); if(setup) await setup(c);
 const data=await c.call('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:true});
 fs.writeFileSync(path.join(out,filename),Buffer.from(data.data,'base64')); c.ws.close();
}
try {
 await snap('file://' + path.join(out,'database-schema.html'),'database-schema.png');
 await snap('file://' + path.join(out,'database-test-data.html'),'database-test-data.png');
 const c=connect(await target('http://127.0.0.1:1734/app')); await c.ready;
 await c.call('Page.enable'); await c.call('Runtime.enable');
 await c.call('Emulation.setDeviceMetricsOverride',{width:1440,height:640,deviceScaleFactor:1,mobile:false});
 await c.call('Page.navigate',{url:'http://127.0.0.1:1734/app'}); await sleep(1500);
 await c.evaluate(`(()=>{const s=document.createElement('style');s.textContent='.phone{width:1200px;height:592px}.staff-panel{padding:28px 34px}.staff-card{max-width:1120px}.staff-table{font-size:16px}';document.head.appendChild(s);document.querySelector('[data-demo-user="teacher001"]').click()})()`);
 let ready=false;
 for(let i=0;i<50;i++){await sleep(250);const v=await c.evaluate(`({identity:document.querySelector('#staffIdentity')?.textContent||'',rows:!!document.querySelector('[data-grade]'),status:document.querySelector('#staffStatus')?.textContent||''})`);if(v.identity&&v.rows){ready=true;break}}
 if(!ready)throw new Error('Teacher roster did not load');
 await sleep(500);const original=await c.evaluate(`({grade:document.querySelector('[data-grade]').value,attendance:document.querySelector('[data-attendance]').value,token:sessionStorage.getItem('lms-token'),enrollment:document.querySelector('[data-grade]').dataset.grade,student:document.querySelector('[data-attendance]').dataset.attendance,schedule:document.querySelector('[data-attendance]').dataset.schedule})`);
 const readShot=await c.call('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:true});
 fs.writeFileSync(path.join(out,'teacher-roster-read.png'),Buffer.from(readShot.data,'base64'));
 let changed=false;
 try {
  await c.evaluate(`(()=>{document.querySelector('[data-grade]').value='94';document.querySelector('[data-attendance]').value='late';document.querySelector('[data-save-row]').click()})()`);
  for(let i=0;i<40;i++){await sleep(250);if((await c.evaluate(`document.querySelector('#staffStatus')?.textContent||''`)).includes('saved')){changed=true;break}}
  if(!changed)throw new Error('UI did not confirm grade/attendance save');
  await sleep(400);const writeShot=await c.call('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:true});
  fs.writeFileSync(path.join(out,'teacher-grade-attendance-write.png'),Buffer.from(writeShot.data,'base64'));
 } finally {
  // Restore the synthetic row exactly to its values before this capture.
  const restore=`(async()=>{const h={'Authorization':'Bearer '+${JSON.stringify(original.token)},'Content-Type':'application/json'};await fetch('/api/teacher/enrollments/${original.enrollment}/grade',{method:'PUT',headers:h,body:JSON.stringify({grade:${JSON.stringify(original.grade===''?null:Number(original.grade))}})});if(${JSON.stringify(original.attendance)})await fetch('/api/teacher/attendance',{method:'PUT',headers:h,body:JSON.stringify({schedule_id:${original.schedule},student_id:${original.student},status:${JSON.stringify(original.attendance)}})});return 'restored'})()`;
  const result=await c.evaluate(restore); if(result!=='restored')throw new Error('Could not restore demo values');
 }
 c.ws.close();
 console.log('Captured 4 screenshots. Teacher demo grade/attendance values restored.');
} finally { chrome.kill('SIGTERM'); }
