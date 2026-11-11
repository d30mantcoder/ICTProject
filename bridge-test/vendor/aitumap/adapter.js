/* Local adapter for Yuujiso's MIT-licensed map. No cross-origin DOM access. */
(()=>{
 const room=(new URLSearchParams(location.search).get('room')||'').toUpperCase().replace(/С/g,'C');
 const match=/^C1\.([1-3])\.([1-3])\d{2}[A-Z]?$/.exec(room);
 window.aituInitialRoom=match?room:'';
 if(!match)return;
 const english=new URLSearchParams(location.search).get('lang')==='en';
 let focused=false,lastText='';
 function highlight(){
  const status=document.getElementById('aitu-room-status');if(!status)return;
  const targets=[...document.querySelectorAll('[data-name]')].filter(element=>{
   const name=element.getAttribute('data-name').toUpperCase();
   return name===room||new RegExp('^'+room.replaceAll('.','\\.')+'[A-Z]?(?:$|\\|)').test(name);
  });
  for(const target of targets){target.classList.add('room-map-group-search-target','aitu-selected-room')}
  const text=room+' · '+(english?'Block ':'Блок ')+match[1]+' · '+(english?'Floor ':'Этаж ')+match[2]+(targets.length?(english?' · Highlighted on the map':' · Выделен на карте'):(english?' · Room not found on the current plan':' · Кабинет не найден на текущем плане'));
  if(text!==lastText){status.textContent=text;lastText=text}
  if(targets.length&&!focused){focused=true;targets[0].scrollIntoView({block:'center',inline:'center'})}
 }
 document.addEventListener('DOMContentLoaded',()=>{
  new MutationObserver(highlight).observe(document.getElementById('root'),{childList:true,subtree:true});highlight();
 });
})();
