(()=>{
 Object.assign(UI_EN,{
  'Установить':'Install','Установить приложение':'Install app','Как установить приложение':'How to install the app',
  'Для установки открой сайт через HTTPS или localhost.':'To install, open this site over HTTPS or localhost.',
  'На iPhone или iPad открой сайт в Safari: «Поделиться» → «На экран Домой» → «Добавить».':'On iPhone or iPad, open this site in Safari: Share → Add to Home Screen → Add.',
  'На Android открой меню браузера (⋮) → «Установить приложение» или «Добавить на главный экран». Если пункта нет, открой сайт в Chrome.':'On Android, open the browser menu (⋮) → Install app or Add to Home screen. If unavailable, open this site in Chrome.',
  'На компьютере открой меню Chrome или Edge → «Установить приложение» или используй значок установки в адресной строке.':'On a computer, open the Chrome or Edge menu → Install app, or use the install icon in the address bar.'
 });
 const displayMode=matchMedia('(display-mode: standalone)');
 const standalone=()=>displayMode.matches||navigator.standalone;
 const ios=/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
 const instructions=!window.isSecureContext?'Для установки открой сайт через HTTPS или localhost.':ios?
  'На iPhone или iPad открой сайт в Safari: «Поделиться» → «На экран Домой» → «Добавить».':/Android/i.test(navigator.userAgent)?
  'На Android открой меню браузера (⋮) → «Установить приложение» или «Добавить на главный экран». Если пункта нет, открой сайт в Chrome.':
  'На компьютере открой меню Chrome или Edge → «Установить приложение» или используй значок установки в адресной строке.';
 const help=node('p',tr(instructions),'pwa-help');help.id='pwaHelp';help.hidden=true;help.setAttribute('role','status');
 const button=node('button',tr('Установить'),'secondary pwa-install');button.type='button';
 button.setAttribute('aria-label',tr('Установить приложение'));button.title=tr('Установить приложение');
 button.setAttribute('aria-controls',help.id);button.setAttribute('aria-expanded','false');
 document.querySelector('header .language-select').before(button);
 document.querySelector('main').prepend(help);
 let prompt=null,installed=Boolean(standalone());
 function showHelp(){help.hidden=false;button.setAttribute('aria-expanded','true');help.scrollIntoView({block:'nearest'})}
 function sync(){button.hidden=installed||Boolean(standalone());if(button.hidden){help.hidden=true;button.setAttribute('aria-expanded','false')}}
 sync();
 window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();prompt=event;sync()});
 button.onclick=async event=>{
  event.preventDefault();
  if(!prompt){showHelp();return}
  const current=prompt;prompt=null;button.disabled=true;
  try{await current.prompt();const choice=await current.userChoice;if(choice?.outcome!=='accepted')showHelp()}
  catch{showHelp()}
  finally{button.disabled=false;sync()}
 };
 window.addEventListener('appinstalled',()=>{installed=true;prompt=null;sync()});
 displayMode.addEventListener('change',()=>{installed=Boolean(standalone());sync()});
 if('serviceWorker' in navigator&&window.isSecureContext)navigator.serviceWorker.register('/sw.js').catch(()=>{});
})();
