/* Samira Faria PWA: nenhum agendamento nem resposta API fica no cache. */
const CACHE='samira-shell-v7-natal';
const STATIC=['/static/offline.html','/static/style.css','/static/app.js','/static/assets/samira-monograma.webp','/static/assets/ramo-natal.svg','/static/assets/samira-retrato.webp','/static/assets/icon-192.png','/static/assets/icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(STATIC)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
 const req=e.request;
 if(req.method!=='GET'||new URL(req.url).origin!==self.location.origin)return;
 const url=new URL(req.url);
 if(url.pathname.startsWith('/api/'))return;
 if(req.mode==='navigate'){
   e.respondWith(fetch(req).catch(()=>caches.match('/static/offline.html')));
   return;
 }
 if(url.pathname.startsWith('/static/')){
   e.respondWith(fetch(req).then(response=>{
     if(response.ok){const clone=response.clone();caches.open(CACHE).then(c=>c.put(req,clone));}
     return response;
   }).catch(()=>caches.match(req)));
 }
});
