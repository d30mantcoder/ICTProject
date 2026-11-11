/* Read-only demo administration. Metrics and counts come from the running server. */
Object.assign(UI_EN,{
 'Войти как администратор · демо':'Sign in as administrator · demo',
 'Кабинет администратора':'Administrator workspace','Обзор системы':'System overview',
 'Базы данных':'Databases','Пользователи и группы':'People and groups',
 'Демо администратора · только просмотр':'Administrator demo · read only',
 'Система работает':'System operational','Требует внимания':'Needs attention',
 'Подключена':'Connected','Недоступна':'Unavailable','Ещё не создана':'Not created yet',
 'Студентов':'Students','Активных студентов':'Active students','Учителей':'Teachers','Администраторов':'Administrators',
 'Групп':'Groups','Курсов':'Courses','Зачислений':'Enrolments','Занятий':'Scheduled lessons',
 'Сеансы':'Sessions','Время работы':'Uptime','Запросов':'Requests','Ошибок сервера':'Server errors',
 'Средний ответ сервера':'Mean server response','Память процесса':'Process memory','Свободно на диске':'Free disk space',
 'Таблица':'Table','Строк':'Rows','Размер':'Size','Источник':'Source','Статус':'Status',
 'Учебная база':'School database','Кэш кабинета':'Workspace cache','Демо-работы учителя':'Teacher demo coursework',
 'Данные от ':'Data as of ','Автообновление каждые 15 секунд.':'Refreshes every 15 seconds.',
 'Показываются реальные счётчики. Демо не позволяет менять пользователей или выполнять SQL.':'Counts are live. This demo cannot edit users or execute SQL.',
 'Нет записей.':'No records.','Имя':'Name','Логин':'Username','Студенты по группам':'Students by group',
 'Преподаватели и их ученики':'Teachers and their students','Ученики из учебной базы':'Students from the school database',
 'Ученики и расписание загружены из базы. Отметки и оценки в демо не изменяют учебную базу.':'Students and schedules are loaded from the database. Demo attendance and grades do not modify the school database.',
 'У преподавателя нет занятий в расписании.':'No lessons are scheduled for this teacher.',
 'У преподавателя нет назначенных групп.':'No groups are assigned to this teacher.',
 'Учебная база временно недоступна.':'The school database is temporarily unavailable.'
});
let adminMode=false;
const adminHidden=new Map(),adminNav=[];
for(const parent of [document.querySelector('.quick-nav'),$('mobileDrawer')]){
 const buttons=[];
 for(const [section,label] of [['admin','Обзор системы'],['admin-database','Базы данных'],['admin-users','Пользователи и группы']]){
  const button=node('button',tr(label));button.type='button';button.hidden=true;button.dataset.adminSection=section;
  button.onclick=()=>{setDrawer(false);openAdmin(false,section)};buttons.push(button);adminNav.push(button);
 }
 parent.prepend(...buttons);
}
function leaveAdmin(){
 adminMode=false;
 for(const [button,hidden] of adminHidden)button.hidden=hidden;
 adminHidden.clear();adminNav.forEach(button=>button.hidden=true);
}
const adminBaseLoad=loadContent;
loadContent=async function(section='home',url=null,refresh=false){
 if(adminMode)return openAdmin(false,section.startsWith('admin')?section:'admin');
 return adminBaseLoad(section,url,refresh);
};
function adminBytes(bytes){return bytes===null||bytes===undefined?'—':new Intl.NumberFormat(uiLocale(),{maximumFractionDigits:1}).format(bytes>=1048576?bytes/1048576:bytes/1024)+' '+tr(bytes>=1048576?'МБ':'КБ')}
function adminMetric(root,label,value){const card=node('section',undefined,'admin-metric');card.append(node('span',tr(label),'hint'),node('strong',String(value??'—')));root.append(card)}
function adminTable(root,title,headers,rows){
 const card=node('section',undefined,'card');card.append(node('h2',tr(title)));
 const wrap=node('div',undefined,'table-wrap'),table=node('table'),head=node('thead'),line=node('tr'),body=node('tbody');
 for(const label of headers){const cell=node('th',tr(label));cell.scope='col';line.append(cell)}head.append(line);
 for(const row of rows){const line=node('tr');for(const value of row)line.append(node('td',String(value)));body.append(line)}
 table.append(head,body);wrap.append(table);card.append(wrap);if(!rows.length)card.append(node('p',tr('Нет записей.'),'hint'));root.append(card);
}
async function openAdmin(start=false,section='admin'){
 if(busy)return;busy=true;$('reload').disabled=true;
 try{
  if(start)await api('admin/demo',{});
  const data=await api('admin/overview');
  adminMode=true;demo=true;currentSection=section;currentUrl=null;
  for(const button of document.querySelectorAll('[data-feature],[data-section],[data-teacher-section]')){
   if(!adminHidden.has(button))adminHidden.set(button,button.hidden);button.hidden=true;
  }
  adminNav.forEach(button=>{button.hidden=false;button.setAttribute('aria-current',String(button.dataset.adminSection===section))});
  ['welcome','signIn','authProgress','textDetails','backButton','moodleReconnect','support','demoTag'].forEach(id=>$(id).hidden=true);
  ['dashboard','tabs','logout'].forEach(id=>$(id).hidden=false);
  $('pageTitle').textContent=tr(section==='admin-database'?'Базы данных':section==='admin-users'?'Пользователи и группы':'Кабинет администратора');
  $('profileLabel').textContent=tr('Демо администратора · только просмотр');document.querySelector('.account-label').textContent='admin.demo';
  $('updated').textContent=tr('Данные от ')+new Date(data.checked_at).toLocaleString(uiLocale(),{timeZone:'Asia/Almaty'})+' · '+tr('Автообновление каждые 15 секунд.');
  const root=$('document');root.replaceChildren();message('');
  root.append(node('p',tr('Показываются реальные счётчики. Демо не позволяет менять пользователей или выполнять SQL.'),'hint'));
  const status=node('p',tr(data.status==='ok'?'Система работает':'Требует внимания'),'admin-status '+(data.status==='ok'?'ok':'degraded'));status.setAttribute('role','status');root.append(status);
  const counts=data.database.counts;
  if(section==='admin'){
   const grid=node('div',undefined,'admin-grid');root.append(grid);
   for(const [label,key] of [['Студентов','students'],['Учителей','teachers'],['Администраторов','admins'],['Активных студентов','active_students'],['Групп','groups'],['Курсов','courses'],['Зачислений','enrollments'],['Занятий','schedule']])adminMetric(grid,label,counts?.[key]);
   const system=data.system,metrics=node('div',undefined,'admin-grid');root.append(node('h2',tr('Обзор системы')),metrics);
   adminMetric(metrics,'Сеансы',system.sessions+' / '+system.session_capacity);
   adminMetric(metrics,'Время работы',Math.floor(system.uptime_seconds/3600)+':'+String(Math.floor(system.uptime_seconds%3600/60)).padStart(2,'0')+':'+String(system.uptime_seconds%60).padStart(2,'0'));
   adminMetric(metrics,'Запросов',system.requests);adminMetric(metrics,'Ошибок сервера',system.errors_5xx);
   adminMetric(metrics,'Средний ответ сервера',system.response_ms===null?'—':system.response_ms+' ms');
   adminMetric(metrics,'Память процесса',adminBytes(system.memory_bytes));adminMetric(metrics,'Свободно на диске',adminBytes(system.disk_free_bytes));
  }
  if(section==='admin'||section==='admin-database'){
   const databases=[{...data.database,label:'Учебная база'},...data.local_databases.map((item,i)=>({...item,label:['Кэш кабинета','Демо-работы учителя','Telegram'][i],engine:item.engine||'SQLite'}))];
   for(const item of databases){const card=node('section',undefined,'card admin-database');
    card.append(node('h2',tr(item.label)),node('p',[item.engine,item.name].filter(Boolean).join(' · '),'hint'),node('p',tr(item.status==='ok'?'Подключена':item.status==='not_created'?'Ещё не создана':'Недоступна')));
    if(item.message)card.append(node('p',tr(item.message),'hint'));
    if(item.size_bytes!==undefined)card.append(node('p',tr('Размер')+': '+adminBytes(item.size_bytes),'hint'));
    if(item.tables.length)adminTable(card,'Таблица',['Таблица','Строк'],item.tables.map(table=>[table.name,table.rows]));root.append(card);
   }
  }
  if(section==='admin-users'){
   if(counts){adminTable(root,'Студенты по группам',['Группа','Студентов'],data.database.groups.map(group=>[group.name,group.students]));
    adminTable(root,'Преподаватели и их ученики',['Имя','Логин','Курсов','Студентов'],data.database.teachers.map(teacher=>[teacher.first_name+' '+teacher.last_name,teacher.username,teacher.courses,teacher.students]));
   }else root.append(node('p',tr('Учебная база временно недоступна.'),'empty'));
  }
 }catch(error){message(error.message,true)}finally{busy=false;$('reload').disabled=false}
}
$('adminDemoButton').textContent=tr('Войти как администратор · демо');
$('adminDemoButton').onclick=()=>openAdmin(true);
setInterval(()=>{if(adminMode&&!busy&&!document.hidden)openAdmin(false,currentSection)},15000);
