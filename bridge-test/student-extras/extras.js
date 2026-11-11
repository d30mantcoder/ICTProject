/* Public campus features; demo data is explicitly labelled. */
Object.assign(UI_EN, {
 'Силлабусы':'Syllabuses','Расписание':'Schedule','AITUSA · скидки':'AITUSA · discounts',
 'Демоданные · не официальная информация':'Demo data · not official information',
 'Скидки партнёров AITUSA':'AITUSA partner discounts',
 'Покажи студенческий билет.':'Show your student ID.',
 'Условия уточняй у партнёра.':'Ask the partner about the terms.',
 'Демонстрационное расписание · время Астаны (UTC+5).':'Sample schedule · Astana time (UTC+5).',
 'Показать на карте':'Show on map','К расписанию':'Back to schedule','Блок':'Block','Этаж':'Floor',
 'Лекция':'Lecture','Практика':'Practice','аудитория':'room',
 'Силлабусов пока нет. Добавь PDF в папку syllabuses и нажми обновление.':'No syllabuses yet. Add PDFs to the syllabuses folder and refresh.',
 'Открыть силлабус: ':'Open syllabus: ', 'К списку силлабусов':'Back to syllabuses',
 'Загрузка PDF…':'Loading PDF…','Предыдущая страница':'Previous page','Следующая страница':'Next page',
 'Масштаб PDF':'PDF zoom','По ширине':'Fit width','Страница':'Page',
 'Не удалось открыть PDF. Проверь файл и повтори попытку.':'Could not open PDF. Check the file and try again.',
 'Повторить':'Retry','Силлабус не найден.':'Syllabus not found.',
 'Данные посещаемости для демонстрации.':'Sample attendance data.'
});
Object.assign(extraSections,{syllabuses:tr('Силлабусы'),schedule:tr('Расписание'),aitusa:tr('AITUSA · скидки')});
for(const key of ['syllabuses','schedule','aitusa']){
 quick.append(featureButton(key,extraSections[key]));
 footer.before(featureButton(key,extraSections[key]));
}
const extrasBaseLoad=loadContent;
let disposePDF=()=>{};
function demoNotice(root){root.append(node('p',tr('Демоданные · не официальная информация'),'demo-notice'))}
loadContent=async function(section='home',url=null,refresh=false){
 if(busy)return;
 disposePDF();disposePDF=()=>{};
 if(section==='map'&&url?.startsWith('room:'))return openRoomMap(url.slice(5));
 if(!['syllabuses','schedule','aitusa'].includes(section)&&!(section==='attendance'&&demo))return extrasBaseLoad(section,url,refresh);
 const version=++featureVersion;busy=true;featureShell(section);message('');
 $('demoTag').hidden=!demo;$('reload').disabled=true;$('document').setAttribute('aria-busy','true');
 const root=$('document');
 try{
  if(section==='aitusa'){
   demoNotice(root);root.append(node('p',tr('Скидки партнёров AITUSA'),'hint'));
   for(const [name,discount] of [['Asgard Cyber Club','15%'],['am:pm coffee','10%']]){
    const card=node('section',undefined,'card discount-card');
    card.append(node('span',discount,'discount-value'),node('h2',name),node('p',tr('Покажи студенческий билет.')),node('p',tr('Условия уточняй у партнёра.'),'hint'));root.append(card);
   }
  }else if(section==='schedule'){
   demoNotice(root);root.append(node('p',tr('Демонстрационное расписание · время Астаны (UTC+5).'),'hint'));
   const week=[['Пн',[['09:00–09:50','Calculus 1','Лекция','C1.1.324'],['10:00–10:50','Introduction to Programming','Практика','C1.2.324']]],['Вт',[['11:00–11:50','Linear Algebra','Практика','C1.1.324']]],['Ср',[['09:00–09:50','Calculus 1','Практика','C1.1.324'],['12:00–12:50','ICT','Лекция','C1.2.324']]],['Чт',[['10:00–10:50','Foreign Language','Практика','C1.3.324']]],['Пт',[['11:00–11:50','Introduction to Programming','Лекция','C1.2.324']]]];
   for(const [day,lessons] of week){root.append(node('h2',tr(day)));for(const [time,title,kind,room] of lessons){const card=node('button',undefined,'card schedule-card');card.type='button';card.dataset.room=room;card.onclick=()=>loadContent('map','room:'+room);card.setAttribute('aria-label',title+' · '+room+' · '+tr('Показать на карте'));card.append(node('strong',time),node('h3',title),node('p',tr(kind)+' · '+tr('аудитория')+' '+room,'hint'),node('span',tr('Показать на карте')+' →','text-button'));root.append(card)}}
  }else if(section==='attendance'){
   $('pageTitle').textContent=tr('Посещаемость');demoNotice(root);
   const month=todayKey().slice(0,7),courses=[{title:'Calculus 1',url:'demo:calculus'},{title:'Linear Algebra',url:'demo:algebra'}];
   const events=Array.from({length:12},(_,i)=>({day:month+'-'+String(i*2+1).padStart(2,'0'),date_label:month+'-'+String(i*2+1).padStart(2,'0')+' 09:00',course:courses[i%2].title,course_url:courses[i%2].url,journal:'Attendance · demo',description:tr(i%2?'Практика':'Лекция'),status:i===3?'Absent':i===7?'Late':'Present',kind:i===3?'absent':i===7?'late':'present',points:i===3?'0 / 2':'2 / 2',remarks:''}));
   renderAttendance({attendance_view:'calendar',events,courses,reports:[{course:'Calculus 1',journal:'Demo',tables:[[[tr('Данные посещаемости для демонстрации.')]]]}]});
  }else{
   const data=await api('syllabuses');if(version!==featureVersion)return;
   if(!data.items.length)root.append(node('p',tr('Силлабусов пока нет. Добавь PDF в папку syllabuses и нажми обновление.'),'empty'));
   for(const item of data.items){const button=node('button',item.title,'syllabus-button');button.setAttribute('aria-label',tr('Открыть силлабус: ')+item.title);button.onclick=()=>openSyllabus(item);root.append(button)}
  }
  document.querySelector('main').scrollTo({top:0,behavior:'instant'});
 }catch(error){if(version===featureVersion){message(error.message,true);const retry=node('button',tr('Повторить'),'secondary');retry.onclick=()=>loadContent(section);root.append(retry)}}
 finally{busy=false;$('reload').disabled=false;root.setAttribute('aria-busy','false')}
};
async function openSyllabus(item){
 disposePDF();const version=++featureVersion;const root=$('document');root.replaceChildren();
 const back=node('button',tr('К списку силлабусов'),'text-button');back.onclick=()=>loadContent('syllabuses');
 const controls=node('div',undefined,'pdf-controls'),previous=node('button','‹','secondary'),next=node('button','›','secondary'),counter=node('span'),zoom=node('select');
 previous.setAttribute('aria-label',tr('Предыдущая страница'));next.setAttribute('aria-label',tr('Следующая страница'));zoom.setAttribute('aria-label',tr('Масштаб PDF'));
 for(const [value,label] of [['1',tr('По ширине')],['1.5','150%'],['2','200%']]){const option=node('option',label);option.value=value;zoom.append(option)}
 controls.append(previous,counter,next,zoom);controls.hidden=true;
 const status=node('p',tr('Загрузка PDF…'),'hint');status.setAttribute('role','status');
 const viewport=node('div',undefined,'pdf-viewport'),canvas=node('canvas');canvas.setAttribute('role','img');canvas.setAttribute('aria-label',item.title);viewport.append(canvas);root.append(back,node('h2',item.title),controls,status,viewport);
 let task,pdf,renderTask,pageNumber=1,disposed=false,drawVersion=0;
 const observer=new ResizeObserver(()=>{if(pdf)draw()});observer.observe(viewport);
 disposePDF=()=>{disposed=true;observer.disconnect();renderTask?.cancel();task?.destroy().catch(()=>{})};
 async function draw(){
  const current=++drawVersion;renderTask?.cancel();
  previous.disabled=next.disabled=true;
  try{
   const page=await pdf.getPage(pageNumber);if(disposed||current!==drawVersion)return;
   const base=page.getViewport({scale:1}),width=Math.max(200,viewport.clientWidth-2);
   const view=page.getViewport({scale:width/base.width*Number(zoom.value)}),ratio=Math.min(devicePixelRatio||1,2);
   canvas.width=Math.floor(view.width*ratio);canvas.height=Math.floor(view.height*ratio);canvas.style.width=Math.floor(view.width)+'px';canvas.style.height=Math.floor(view.height)+'px';
   canvas.setAttribute('aria-label',item.title+' · '+tr('Страница')+' '+pageNumber);
   counter.textContent=pageNumber+' / '+pdf.numPages;
   renderTask=page.render({canvasContext:canvas.getContext('2d'),viewport:view,transform:[ratio,0,0,ratio,0,0]});await renderTask.promise;
   if(!disposed&&current===drawVersion){status.textContent='';canvas.dataset.rendered='true'}
  }catch(error){if(error.name!=='RenderingCancelledException'&&!disposed)status.textContent=tr('Не удалось открыть PDF. Проверь файл и повтори попытку.')}
  finally{if(!disposed&&current===drawVersion){previous.disabled=pageNumber<=1;next.disabled=pageNumber>=pdf.numPages}}
 }
 previous.onclick=()=>{pageNumber--;draw()};next.onclick=()=>{pageNumber++;draw()};zoom.onchange=draw;
 try{
  const lib=await import('/vendor/pdfjs/build/pdf.mjs');if(disposed)return;
  lib.GlobalWorkerOptions.workerSrc='/vendor/pdfjs/build/pdf.worker.mjs';
  task=lib.getDocument({url:item.url,isEvalSupported:false,useWasm:false,cMapUrl:'/vendor/pdfjs/cmaps/',cMapPacked:true,standardFontDataUrl:'/vendor/pdfjs/standard_fonts/'});
  pdf=await task.promise;if(disposed||version!==featureVersion)return;
  controls.hidden=false;await draw();
 }catch(error){if(!disposed){status.textContent=tr('Не удалось открыть PDF. Проверь файл и повтори попытку.');const retry=node('button',tr('Повторить'),'secondary');retry.onclick=()=>openSyllabus(item);root.append(retry)}}
}
const extrasReset=reset;reset=function(){disposePDF();disposePDF=()=>{};extrasReset()};

function openRoomMap(room){
 featureVersion++;featureShell('map');currentUrl='room:'+room;
 const root=$('document'),back=node('button',tr('К расписанию'),'text-button');back.onclick=()=>loadContent('schedule');root.append(back);
 const normalized=room.toUpperCase().replace(/С/g,'C'),match=/^C1\.([1-3])\.([1-3])\d{2}[A-Z]?$/.exec(normalized);
 if(!match){message(tr('Кабинет не найден на плане.'),true);return}
 root.append(node('h2',normalized),node('p',tr('Блок')+' '+match[1]+' · '+tr('Этаж')+' '+match[2],'hint'));
 const frame=node('iframe',undefined,'campus-map');frame.src='/campus-map/?room='+encodeURIComponent(normalized)+'&lang='+uiLanguage;frame.title=tr('Показать на карте')+' · '+normalized;root.append(frame);
 const credit=node('p',undefined,'hint');credit.append(tr('Карта: '),safeLink('https://github.com/Yuujiso/aitumap','Yuujiso / aitumap'),tr(' · лицензия MIT.'));root.append(credit);
 document.querySelector('main').scrollTo({top:0,behavior:'instant'});
}
