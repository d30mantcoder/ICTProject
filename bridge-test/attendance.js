/* Personal attendance calendar. Dates are normalized by the server, statuses stay source-backed. */
const attendanceKinds={
  present:{label:'Присутствие',icon:'check'},absent:{label:'Пропуск',icon:'absent'},
  late:{label:'Опоздание',icon:'clock'},excused:{label:'Уважительная причина',icon:'check'},
  unmarked:{label:'Без отметки',icon:'minus'},other:{label:'Другой статус',icon:'list'}
};
function renderAttendance(data){
  if(data.attendance_view!=='calendar'){renderAttendanceTables(data);return}
  $('pageTitle').textContent='Посещаемость';
  $('backButton').hidden=true;$('textDetails').hidden=true;
  const root=$('document'),events=data.events||[];
  const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Almaty',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const dates=events.map(e=>e.day).filter(Boolean).sort();
  let month=(dates.some(d=>d.startsWith(today.slice(0,7)))?today:dates.at(-1)||today).slice(0,7);
  let course='',selected=null;
  const intro=node('div',undefined,'att-intro'),mark=node('span',undefined,'att-intro-icon');
  mark.append(uiIcon('calendar'));intro.append(mark,node('p','Твоя посещаемость — по дням и курсам.','hint'));root.append(intro);
  if(!data.partial&&!data.reports?.length)root.append(node('p','В LMS пока нет доступных журналов посещаемости.','empty'));
  if(data.partial){const notice=node('p','Часть журналов пока недоступна. Показаны загруженные отметки.','att-notice');notice.setAttribute('role','status');root.append(notice)}
  const filters=node('div',undefined,'att-filter'),label=node('label','Курс'),select=node('select');
  label.htmlFor='attendanceCourse';select.id='attendanceCourse';
  const all=node('option','Все курсы');all.value='';select.append(all);
  for(const item of data.courses||[]){const option=node('option',item.title);option.value=item.url;select.append(option)}
  filters.append(label,select);root.append(filters);
  const stats=node('div',undefined,'att-stats');root.append(stats);
  const panel=node('section',undefined,'att-calendar');
  panel.setAttribute('aria-label','Календарь посещаемости');
  const toolbar=node('div',undefined,'att-toolbar'),prev=node('button',undefined,'att-arrow'),next=node('button',undefined,'att-arrow'),heading=node('h2');
  prev.append(uiIcon('left'));next.append(uiIcon('next'));
  prev.setAttribute('aria-label','Предыдущий месяц');next.setAttribute('aria-label','Следующий месяц');
  const monthTitle=node('div',undefined,'att-month-title'),thisMonth=node('button','Этот месяц','text-button');
  monthTitle.append(heading,thisMonth);toolbar.append(prev,monthTitle,next);
  const grid=node('div',undefined,'att-grid');panel.append(toolbar,grid);
  const legend=node('div',undefined,'att-legend');
  for(const [kind,{label}] of Object.entries(attendanceKinds)){
    const item=node('span',undefined,'att-legend-item'),dot=node('i',undefined,'att-dot '+kind);
    dot.setAttribute('aria-hidden','true');item.append(dot,node('span',label));legend.append(item);
  }
  panel.append(legend);root.append(panel);
  const list=node('section',undefined,'att-sessions');list.setAttribute('aria-live','polite');root.append(list);
  const undated=node('section',undefined,'att-undated');root.append(undated);
  const source=node('details',undefined,'att-source'),summary=node('summary','Итоги и исходные таблицы LMS');
  source.append(summary);root.append(source);
  function relevant(){return events.filter(e=>!course||e.course_url===course)}
  function eventCard(event){
    const kind=attendanceKinds[event.kind]?event.kind:'other',meta=attendanceKinds[kind];
    const card=node('article',undefined,'att-session '+kind),top=node('div',undefined,'att-session-top');
    const title=node('div',undefined,'grow');title.append(node('h3',event.course),node('p',event.description||event.journal,'hint'));
    const badge=node('span',undefined,'att-status '+kind);badge.append(uiIcon(meta.icon),node('span',event.status||meta.label));
    top.append(title,badge);card.append(top);
    const when=node('p',undefined,'att-when');when.append(uiIcon('clock'),node('span',event.date_label));card.append(when);
    if(event.points)card.append(node('p','Баллы: '+event.points,'att-points'));
    if(event.remarks)card.append(node('p',event.remarks,'att-remark'));
    return card;
  }
  function renderList(){
    list.replaceChildren();const active=relevant().filter(e=>e.day&&(selected?e.day===selected:e.day.startsWith(month)));
    const line=node('div',undefined,'att-list-heading');
    line.append(node('h2',selected?new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',timeZone:'UTC'}).format(new Date(selected+'T12:00:00Z')):'Занятия за месяц'));
    if(selected){const clear=node('button','Весь месяц','text-button');clear.onclick=()=>{selected=null;draw()};line.append(clear)}
    list.append(line);
    if(!active.length)list.append(node('p','На этот период в LMS нет отметок.','empty'));
    for(const event of active.slice().sort((a,b)=>a.day.localeCompare(b.day)||a.date_label.localeCompare(b.date_label)))list.append(eventCard(event));
    undated.replaceChildren();const unknown=relevant().filter(e=>!e.day);
    if(unknown.length){undated.append(node('h2','Другие записи'),node('p','LMS не указала полную дату этих записей.','hint'));for(const event of unknown)undated.append(eventCard(event))}
  }
  function draw(){
    const matching=relevant(),period=matching.filter(e=>e.day?.startsWith(month));
    heading.textContent=new Intl.DateTimeFormat('ru-RU',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(month+'-01T12:00:00Z'));
    stats.replaceChildren();
    for(const kind of ['present','absent','late','unmarked']){
      const box=node('div',undefined,'att-stat '+kind),meta=attendanceKinds[kind];
      box.append(uiIcon(meta.icon),node('strong',String(period.filter(e=>e.kind===kind).length)),node('span',meta.label));
      stats.append(box);
    }
    stats.setAttribute('aria-label','Количество отметок за выбранный месяц');
    grid.replaceChildren();for(const day of ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'])grid.append(node('span',day,'att-weekday'));
    const [year,mon]=month.split('-').map(Number),offset=(new Date(Date.UTC(year,mon-1,1)).getUTCDay()+6)%7;
    for(let n=0;n<offset;n++)grid.append(node('span',undefined,'att-spacer'));
    for(let n=1;n<=new Date(Date.UTC(year,mon,0)).getUTCDate();n++){
      const date=month+'-'+String(n).padStart(2,'0'),entries=period.filter(e=>e.day===date);
      const button=node('button',undefined,'att-day');button.append(node('span',String(n)));
      button.dataset.day=date;button.setAttribute('aria-pressed',String(selected===date));
      button.setAttribute('aria-label',date+', записей: '+entries.length+(entries.length?'; '+entries.map(e=>e.status||'Без отметки').join(', '):''));
      if(date===today)button.setAttribute('aria-current','date');
      if(entries.length){
        button.classList.add('has-records');
        const dots=node('span',undefined,'att-dots');
        for(const event of entries.slice(0,3)){const dot=node('i',undefined,'att-dot '+event.kind);dot.setAttribute('aria-hidden','true');dots.append(dot)}
        if(entries.length>3)dots.append(node('small','+'+(entries.length-3)));
        button.append(dots);
      }
      button.onclick=()=>{selected=selected===date?null:date;draw();grid.querySelector('[data-day="'+date+'"]')?.focus({preventScroll:true})};
      grid.append(button);
    }
    renderList();
  }
  function renderSource(){
    source.replaceChildren(summary);
    for(const report of data.reports||[]){
      if(course&&!(data.courses||[]).some(c=>c.url===course&&c.title===report.course))continue;
      const block=node('section');block.append(node('h3',report.course+' · '+report.journal));
      if(report.updated)block.append(node('p','Обновлено: '+report.updated,'hint'));
      for(const rows of report.tables||[]){
        const wrap=node('div',undefined,'table-wrap attendance-table'),table=node('table');
        wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',report.course+' — таблица LMS');
        for(const cells of rows){const tr=node('tr');for(const text of cells)tr.append(node('td',text));table.append(tr)}
        wrap.append(table);block.append(wrap);
      }
      source.append(block);
    }
    const missing=data.missing_courses||[];
    if(missing.length)source.append(node('p','В LMS не найден доступный журнал: '+missing.join(', ')+'.','hint'));
    if(!data.reports?.length)source.append(node('p','Доступных журналов пока нет.','hint'));
  }
  function move(delta){const [year,mon]=month.split('-').map(Number),d=new Date(Date.UTC(year,mon-1+delta,1));month=d.toISOString().slice(0,7);selected=null;draw()}
  prev.onclick=()=>move(-1);next.onclick=()=>move(1);thisMonth.onclick=()=>{month=today.slice(0,7);selected=null;draw()};
  select.onchange=()=>{course=select.value;selected=null;draw();renderSource()};
  draw();renderSource();
}
