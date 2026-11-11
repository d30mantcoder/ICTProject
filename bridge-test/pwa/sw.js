/* Cache only the public offline screen and app icons, never private API responses. */
const CACHE='aitu-public-v1';
const PUBLIC=['/pwa/offline.html','/pwa/icon-192.png','/pwa/icon-512.png'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(PUBLIC)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('aitu-public-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(event.request.method!=='GET'||url.origin!==self.location.origin)return;
 if(event.request.mode==='navigate'&&url.pathname==='/')event.respondWith(fetch(event.request).catch(()=>caches.match('/pwa/offline.html')));
 else if(PUBLIC.includes(url.pathname))event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request)));
});
