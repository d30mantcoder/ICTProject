/* Student features use only the current bridge session and public directory data. */
const extraSections = {calendar:'Календарь',notifications:'Уведомления',map:'Карта кампуса',clubs:'Клубы',assistant:'AI-помощник'};
const campusMapURL = 'https://yuujiso.github.io/aitumap/';
const baseLoadContent = loadContent;
let featureVersion=0, calendarEvents=[], selectedDay='', calendarMonth='', calendarYear=0;
const dateKey=seconds=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Almaty',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(seconds*1000));
const todayKey=()=>dateKey(Date.now()/1000);
function safeLink(url,label){
  const a=node('a',label);
  try{const target=new URL(url);if(target.protocol!=='https:')return node('span','Ссылка не опубликована');a.href=target.href}
  catch{return node('span','Ссылка не опубликована')}
  a.target='_blank';a.rel='noopener noreferrer';return a;
}
function featureButton(section,label){
  const b=node('button',label);b.type='button';b.dataset.feature=section;
  b.onclick=()=>{setDrawer(false);loadContent(section)};return b;
}
const quick=node('nav',undefined,'quick-nav');quick.setAttribute('aria-label','Быстрые разделы');
for(const [section,label] of Object.entries({home:'Курсы',dashboard:'Задания',attendance:'Посещаемость',calendar:'Календарь',notifications:'Уведомления',map:'Карта'}))
  quick.append(featureButton(section,label));
$('dashboard').insertBefore(quick,$('document'));
const footer=$('mobileDrawer').querySelector('.nav-footer');
for(const [section,label] of Object.entries(extraSections))footer.before(featureButton(section,label));
const mapBeforeLogin=featureButton('map','Открыть карту кампуса');mapBeforeLogin.className='text-button';
$('signIn').append(mapBeforeLogin);
async function updateBadge(){
  if(!connected||demo)return;
  try{
    const data=await api('notifications');
    for(const b of document.querySelectorAll('[data-feature="notifications"]')){
      b.querySelector('.unread-badge')?.remove();
      if(data.unread){const badge=node('span',String(data.unread),'unread-badge');badge.setAttribute('aria-label','Непрочитано: '+data.unread);b.append(badge)}
    }
  }catch{/* Section actions report actionable errors; polling does not replace them. */}
}
const baseRender=render;
render=function(data){baseRender(data);updateBadge()};
function selectFeature(section){
  document.querySelectorAll('[data-feature]').forEach(b=>b.setAttribute('aria-current',String(b.dataset.feature===section)));
  document.querySelectorAll('[data-section]').forEach(b=>b.setAttribute('aria-current',String(b.dataset.section===section)));
}
function featureShell(section){
  currentSection=section;currentUrl=null;
  $('welcome').hidden=true;$('signIn').hidden=true;$('authProgress').hidden=true;
  $('dashboard').hidden=false;$('tabs').hidden=false;$('backButton').hidden=true;
  $('textDetails').hidden=true;$('pageTitle').textContent=extraSections[section];
  $('updated').textContent='';$('document').replaceChildren();selectFeature(section);
}
loadContent=async function(section='home',url=null,refresh=false){
  if(!extraSections[section]||url){
    if(busy)return;
    featureVersion++;$('textDetails').hidden=false;selectFeature(section);
    return baseLoadContent(section,url,refresh);
  }
  if(busy)return;
  const version=++featureVersion;busy=true;featureShell(section);message('');
  $('reload').disabled=true;$('document').setAttribute('aria-busy','true');
  try{
    if(section==='map'){
      $('document').append(node('p','Интерактивная карта AITU: аудитории и этажи. Данных о занятости аудиторий нет.','hint'));
      $('document').append(safeLink(campusMapURL,'Открыть карту в отдельной вкладке'));
      const frame=node('iframe',undefined,'campus-map');frame.src=campusMapURL;frame.title='Интерактивная карта Astana IT University';
      frame.referrerPolicy='no-referrer';frame.setAttribute('sandbox','allow-scripts allow-same-origin allow-popups');
      $('document').append(frame);
      const credit=node('p',undefined,'hint');credit.append('Карта: ',safeLink('https://github.com/Yuujiso/aitumap','Yuujiso / aitumap'),' · лицензия MIT.');$('document').append(credit);
    }else if(section==='assistant'){
      renderAssistant();
    }else if(section==='clubs'){
      const data=await api('community');if(version!==featureVersion)return;
      renderClubs(data);
      $('updated').textContent=data.cache_updated_at?'Справочник сохранён · '+new Date(data.cache_updated_at).toLocaleString('ru-RU',{timeZone:'Asia/Almaty'}):'';
    }else{
      // Timeline provides deadlines; read status remains on the server for this session.
      const data=await api('content',{section:demo?'demo':'dashboard',refresh});
      if(version!==featureVersion)return;
      if(section==='calendar'){
        calendarEvents=(data.timeline||[]).filter(e=>Number.isFinite(e.due)&&e.due>0);
        if(!selectedDay){selectedDay=todayKey();calendarYear=+selectedDay.slice(0,4);calendarMonth=+selectedDay.slice(5,7)-1}
        renderCalendar();
        if((data.timeline||[]).some(e=>!e.due))$('document').append(node('p','У части событий нет точной даты: смотри раздел «Задания».','hint'));
      }else{
        const notices=demo?{items:(data.timeline||[]).map((item,i)=>({...item,id:String(i),read:false}))}:await api('notifications');
        if(version!==featureVersion)return;
        renderNotifications(notices);
      }
      $('updated').textContent=(data.cached?'Из кэша · ':'Обновлено · ')+(data.updated||'');
      message(demo?'Тестовые данные. Для своих дедлайнов войди в Microsoft.':(data.warnings||[]).join(' '));
    }
    document.querySelector('main').scrollTo({top:0,behavior:'instant'});
    await updateBadge();
  }catch(error){
    if(version===featureVersion){
      message(error.message,true);
      const retry=node('button','Вернуться ко входу','secondary');retry.onclick=()=>{reset();ready()};$('document').append(retry);
    }
  }finally{busy=false;$('reload').disabled=false;$('document').setAttribute('aria-busy','false')}
};
function eventCard(item,cls='card'){
  const card=node('section',undefined,cls);card.append(node('h2',item.title),node('p',item.course||''));
  card.append(node('p',[item.date,item.time].filter(Boolean).join(' · '),'hint'));
  if(item.url){const b=node('button','Открыть задание','text-button');b.onclick=()=>loadContent('dashboard',item.url);card.append(b)}
  return card;
}
function renderCalendar(){
  const root=$('document');root.replaceChildren();
  root.append(node('p','Дедлайны из Timeline Moodle · время Астаны (UTC+5). Отдельные экзаменационные периоды появятся после подключения академического календаря.','hint'));
  const toolbar=node('div',undefined,'calendar-toolbar');
  const previous=node('button','‹','secondary'),next=node('button','›','secondary');
  previous.setAttribute('aria-label','Предыдущий месяц');next.setAttribute('aria-label','Следующий месяц');
  const label=new Intl.DateTimeFormat('ru',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(Date.UTC(calendarYear,calendarMonth,1)));
  toolbar.append(previous,node('h2',label),next);root.append(toolbar);
  function move(delta){const d=new Date(Date.UTC(calendarYear,calendarMonth+delta,1));calendarYear=d.getUTCFullYear();calendarMonth=d.getUTCMonth();selectedDay=calendarYear+'-'+String(calendarMonth+1).padStart(2,'0')+'-01';renderCalendar()}
  previous.onclick=()=>move(-1);next.onclick=()=>move(1);
  const grid=node('div',undefined,'calendar-grid');
  for(const name of ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'])grid.append(node('span',name,'weekday'));
  const offset=(new Date(Date.UTC(calendarYear,calendarMonth,1)).getUTCDay()+6)%7;
  for(let i=0;i<offset;i++)grid.append(node('span'));
  const days=new Date(Date.UTC(calendarYear,calendarMonth+1,0)).getUTCDate();
  for(let day=1;day<=days;day++){
    const key=calendarYear+'-'+String(calendarMonth+1).padStart(2,'0')+'-'+String(day).padStart(2,'0');
    const events=calendarEvents.filter(e=>dateKey(e.due)===key);
    const button=node('button',String(day),'calendar-day');
    button.setAttribute('aria-label',key+', событий: '+events.length);
    button.setAttribute('aria-pressed',String(key===selectedDay));
    if(key===todayKey())button.setAttribute('aria-current','date');
    if(events.length)button.append(node('small',String(events.length)));
    button.onclick=()=>{selectedDay=key;renderCalendar()};grid.append(button);
  }
  root.append(grid,node('h2',selectedDay));
  const events=calendarEvents.filter(e=>dateKey(e.due)===selectedDay);
  if(!events.length)root.append(node('p','На выбранную дату загруженных дедлайнов нет.','empty'));
  for(const item of events)root.append(eventCard(item,'card calendar-event'));
}
function renderNotifications(data){
  const root=$('document');root.replaceChildren();
  root.append(node('p','Уведомления о загруженных дедлайнах. Прочитанные остаются отмеченными при перезагрузке страницы в течение текущей сессии.','hint'));
  const mark=node('button','Прочитать все','secondary');mark.disabled=demo||!data.items.some(item=>!item.read);
  mark.onclick=async()=>{
    mark.disabled=true;
    try{await api('notifications/read-all',{});renderNotifications(await api('notifications'));await updateBadge()}
    catch(e){message(e.message,true);mark.disabled=false}
  };
  root.append(mark);
  if(!data.items.length)root.append(node('p','Новых уведомлений нет.','empty'));
  for(const item of data.items)root.append(eventCard(item,'card notification-card'+(item.read?'':' unread')));
}
function renderClubs(data){
  const root=$('document');root.append(node('p','Контакты опубликованы университетом. Проверено: '+data.checked+'. Категории сгруппированы для удобства поиска.','hint'),safeLink(data.source,'Источник: сайт AITU'));
  const search=node('input');search.type='search';search.placeholder='Название клуба';search.setAttribute('aria-label','Поиск клуба');search.className='club-filter';
  const category=node('select');category.setAttribute('aria-label','Категория клуба');
  for(const value of ['Все категории',...new Set(data.clubs.map(c=>c.category))]){const o=node('option',value);o.value=value;category.append(o)}
  const selected=new Set(data.selected||[]);
  const mine=node('input');mine.type='checkbox';mine.id='myClubs';
  const mineLabel=node('label',' Только мои клубы');mineLabel.prepend(mine);
  if(data.can_select)root.append(node('p','Отметь интересующие клубы: выбор сохранится в твоём профиле. Это не заявка на вступление.','hint'));
  const list=node('div');root.append(search,category,mineLabel,list);
  function filter(){
    list.replaceChildren();const q=search.value.toLocaleLowerCase();
    for(const club of data.clubs.filter(c=>c.title.toLocaleLowerCase().includes(q)&&(category.selectedIndex===0||c.category===category.value)&&(!mine.checked||selected.has(c.title)))){
      const card=node('section',undefined,'card club-card');card.append(node('h2',club.title),node('p',club.category,'hint'));
      card.append(club.url?safeLink(club.url,'Открыть страницу клуба'):node('p','Контакт не опубликован университетом.','hint'));if(data.can_select){
        const label=node('label',' Мой клуб'),choice=node('input');choice.type='checkbox';choice.checked=selected.has(club.title);
        choice.setAttribute('aria-label','Мой клуб: '+club.title);label.prepend(choice);card.append(label);
        choice.onchange=async()=>{
          const checked=choice.checked;choice.disabled=true;
          try{await api('profile/clubs',{title:club.title,selected:checked});if(checked)selected.add(club.title);else selected.delete(club.title);message('Выбор сохранён');if(mine.checked)filter()}
          catch(error){choice.checked=!checked;message(error.message,true)}
          finally{choice.disabled=false}
        };
      }
      list.append(card);
    }
    if(!list.children.length)list.append(node('p','Клубы не найдены.','empty'));
  }
  search.oninput=category.onchange=mine.onchange=filter;filter();
}
const baseReset=reset;
reset=function(){
  featureVersion++;calendarEvents=[];selectedDay='';baseReset();
  document.querySelectorAll('.unread-badge').forEach(b=>b.remove());
  $('textDetails').hidden=false;
};
$('reload').onclick=()=>loadContent(currentSection,currentUrl,true);
setInterval(()=>{if(!$('dashboard').hidden)updateBadge()},15000);

function renderAssistant(){
  const root=$('document');
  root.append(node('p','Помощник отвечает по загруженным курсам и дедлайнам. Сначала открой нужные разделы. Ответы генерируются локально и могут содержать ошибки; сверяй даты с Moodle.','hint'));
  const form=node('form'),label=node('label','Твой вопрос'),input=node('input'),send=node('button','Спросить','primary');
  input.id='assistantQuestion';input.name='question';input.required=true;input.maxLength=1000;input.placeholder='Какие дедлайны есть в моих заданиях?';label.htmlFor=input.id;
  send.type='submit';const reply=node('p',undefined,'paragraph');reply.id='assistantReply';reply.setAttribute('role','status');
  form.append(label,input,send);root.append(form,reply);
  form.onsubmit=async event=>{
    event.preventDefault();if(send.disabled)return;send.disabled=true;reply.textContent='Готовлю ответ…';
    const version=featureVersion;
    try{const result=await api('assistant',{question:input.value});if(version===featureVersion)reply.textContent=result.answer}
    catch(error){if(version===featureVersion)reply.textContent=error.message}
    finally{send.disabled=false}
  };
}
