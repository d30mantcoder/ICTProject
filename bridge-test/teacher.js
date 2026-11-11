/* Database-backed teacher roster; demo attendance never writes to the school database. */
let teacherMode=false, teacherLesson=null, teacherRows=[], teacherData=null, teacherRosterVersion=0;
const attendanceLabels={present:tr('Присутствует'),absent:tr('Отсутствует'),late:tr('Опоздал'),excused:tr('Уважительная причина')};
const studentLoadContent=loadContent;
const teacherNav=[];
for(const parent of [document.querySelector('.quick-nav'),$('mobileDrawer')]){
  const buttons=[];
  for(const [section,label] of Object.entries({'teacher':'Мой урок','teacher-students':'Ученики и группы','teacher-exams':'Экзамены','teacher-homework':'Домашние задания'})){
    const button=node('button',tr(label));button.type='button';button.hidden=true;
    button.dataset.teacherNav='true';button.dataset.teacherSection=section;
    button.onclick=()=>{setDrawer(false);openTeacher(false,section)};
    buttons.push(button);teacherNav.push(button);
  }
  if(parent.id==='mobileDrawer') parent.querySelector('h2').after(...buttons);
  else parent.prepend(...buttons);
}
const teacherHidden=new Map();
function leaveTeacher(){
  teacherCourseworkVersion++;teacherAssessment=null;teacherGroup='';
  teacherMode=false;teacherLesson=null;teacherRows=[];teacherRosterVersion++;
  document.body.classList.remove('teacher-mode');
  for(const [button,hidden] of teacherHidden)button.hidden=hidden;
  teacherHidden.clear();teacherNav.forEach(button=>button.hidden=true);
}
loadContent=async function(section='home',url=null,refresh=false){
  if(teacherMode&&section!=='map')return openTeacher(false,section.startsWith('teacher')?section:'teacher');
  return studentLoadContent(section,url,refresh);
};
function lessonTime(lesson){
  const day=new Date(lesson.starts_at).toLocaleDateString(uiLocale(),{timeZone:'Asia/Almaty',day:'numeric',month:'long'});
  const time=value=>new Date(value).toLocaleTimeString(uiLocale(),{timeZone:'Asia/Almaty',hour:'2-digit',minute:'2-digit'});
  return day+' · '+time(lesson.starts_at)+'–'+time(lesson.ends_at)+tr(' · Астана');
}
async function openTeacher(start=false,section='teacher'){
  if(busy)return;
  busy=true;teacherRosterVersion++;
  try{
    const data=await api(start?'teacher/demo':'teacher/workspace',start?{}:undefined);
    teacherMode=true;demo=true;teacherData=data;currentSection=section;currentUrl=null;
    document.body.classList.add('teacher-mode');
    for(const button of document.querySelectorAll('[data-feature], [data-section]')){
      if(button.dataset.feature==='map')continue;
      if(!teacherHidden.has(button))teacherHidden.set(button,button.hidden);
      button.hidden=true;
    }
    teacherNav.forEach(button=>{button.hidden=false;button.setAttribute('aria-current',String(button.dataset.teacherSection===section))});
    ['welcome','signIn','authProgress','textDetails','backButton','moodleReconnect','support'].forEach(id=>$(id).hidden=true);
    ['dashboard','tabs','logout','demoTag'].forEach(id=>$(id).hidden=false);
    $('pageTitle').textContent=tr('Кабинет учителя');$('profileLabel').textContent=data.teacher.name+tr(' · преподаватель');
    document.querySelector('.account-label').textContent=data.teacher.username+tr(' · учитель · демо');
    $('updated').textContent=tr('Ученики из учебной базы')+' · '+data.source;
    $('document').replaceChildren();
    message('');
    $('document').append(node('p',tr('Ученики и расписание загружены из базы. Отметки и оценки в демо не изменяют учебную базу.'),'hint'));
    teacherCourseworkVersion++;
    if(section!=='teacher'){await renderTeacherSection(section);return}
    const current=data.lessons.find(lesson=>lesson.id===data.current_lesson_id);
    const next=data.lessons.find(lesson=>lesson.id===data.next_lesson_id);
    const card=node('section',undefined,'card teacher-current');card.id='teacherCurrent';
    card.append(node('span',current?tr('Сейчас идёт урок'):tr('Сейчас занятий нет'),'tag'));
    const shown=current||next;
    if(shown){card.append(sourceNode('h2',shown.course),localizedNode('p',()=>shown.group+' · '+lessonTime(shown),'hint'));
      const location=node('p',undefined,'teacher-location');location.append(uiIcon('calendar'),node('strong',tr('Аудитория ')+shown.room));
      card.append(location,node('p',tr(shown.building),'hint'));
      const map=node('button',tr('Показать карту кампуса'),'text-button');map.onclick=()=>loadContent('map');card.append(map);
      if(!current)card.append(node('p',tr('Это ближайшее занятие.'),'hint'));
    }else card.append(node('p',tr('Выбери прошедшее занятие ниже, чтобы проверить журнал.'),'hint'));
    $('document').append(card);
    const lessons=node('section',undefined,'card'),label=node('label',tr('Занятие и группа'),'field'),select=node('select');
    label.htmlFor='teacherLesson';select.id='teacherLesson';
    for(const lesson of data.lessons){const option=localizedNode('option',()=>(lesson.is_current?tr('Сейчас · '):'')+lesson.course+' · '+lesson.group+' · '+lessonTime(lesson));option.value=lesson.id;select.append(option)}
    teacherLesson=data.lessons.some(lesson=>lesson.id===teacherLesson)?teacherLesson:(data.current_lesson_id||data.next_lesson_id||data.lessons[0]?.id);
    lessons.append(label,select);$('document').append(lessons);
    const roster=node('section',undefined,'teacher-roster');roster.id='teacherRoster';$('document').append(roster);
    if(!data.lessons.length)$('document').append(node('p',tr('У преподавателя нет занятий в расписании.'),'empty'));
    if(teacherLesson){select.value=teacherLesson;select.onchange=()=>loadTeacherStudents(+select.value);await loadTeacherStudents(teacherLesson)}
    document.querySelector('main').scrollTo({top:0,behavior:'instant'});
  }catch(error){message(error.message,true)}finally{busy=false}
}
async function loadTeacherStudents(lessonId){
  teacherLesson=lessonId;const version=++teacherRosterVersion,host=$('teacherRoster');
  host.replaceChildren(node('p',tr('Загружаем учеников…'),'hint'));
  try{
    const data=await api('teacher/lessons/'+lessonId+'/students');
    if(version!==teacherRosterVersion||!teacherMode)return;
    teacherRows=data.students;renderTeacherStudents();
  }catch(error){if(version===teacherRosterVersion){host.replaceChildren();message(error.message,true)}}
}
function renderTeacherStudents(){
  const host=$('teacherRoster');host.replaceChildren();
  const lesson=teacherData.lessons.find(lesson=>lesson.id===teacherLesson);
  host.append(node('h2',tr('Ученики · ')+teacherRows.length),node('p',lesson.group+tr(' · аудитория ')+lesson.room,'hint'));
  const summary=node('p',undefined,'teacher-summary');summary.id='teacherSummary';summary.setAttribute('aria-live','polite');host.append(summary);
  summary.dataset.localize='';summary.addEventListener('languagechange',updateTeacherSummary);
  const label=node('label',tr('Поиск ученика'),'field'),search=node('input');label.htmlFor='teacherSearch';search.id='teacherSearch';search.type='search';search.placeholder=tr('Имя или фамилия');
  host.append(label,search);
  const all=node('button',tr('Отметить всех присутствующими'),'secondary wide');all.id='teacherMarkAll';host.append(all);
  const list=node('div',undefined,'teacher-students'),empty=node('p',tr('Ученики не найдены'),'empty');empty.hidden=teacherRows.length>0;all.disabled=!teacherRows.length;host.append(list,empty);
  for(const student of teacherRows){
    const card=node('article',undefined,'card teacher-student');card.dataset.student=student.id;
    card.append(sourceNode('h3',student.name),sourceNode('p',student.group,'hint'));
    const control=node('label',tr('Посещаемость'),'field');control.htmlFor='teacher-status-'+student.id;
    const select=node('select');select.id=control.htmlFor;select.setAttribute('aria-label',tr('Посещаемость: ')+student.name);
    const blank=node('option',tr('Не отмечен'));blank.value='';blank.disabled=true;select.append(blank);
    for(const [value,title] of Object.entries(attendanceLabels)){const option=node('option',title);option.value=value;select.append(option)}
    select.value=student.status||'';
    const feedback=node('p',student.status?tr('Сохранено'):tr('Пока без отметки'),'teacher-feedback');feedback.setAttribute('aria-live','polite');
    card.append(control,select,feedback);list.append(card);
    select.onchange=async()=>{
      const previous=student.status;select.disabled=true;feedback.textContent=tr('Сохраняем…');
      try{const result=await api('teacher/attendance',{lesson_id:lesson.id,student_id:student.id,status:select.value});
        student.status=select.value;student.marked_at=result.marked_at;feedback.textContent=tr('Сохранено · ')+new Date(result.marked_at).toLocaleTimeString(uiLocale(),{timeZone:'Asia/Almaty',hour:'2-digit',minute:'2-digit'});updateTeacherSummary();
      }catch(error){select.value=previous||'';feedback.textContent=tr('Не сохранено. Повтори выбор.');message(error.message,true)}finally{select.disabled=false}
    };
  }
  search.oninput=()=>{let count=0;for(const card of list.children){card.hidden=!card.querySelector('h3').textContent.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase());if(!card.hidden)count++}empty.hidden=count>0};
  all.onclick=async()=>{
    all.disabled=true;search.disabled=true;const selects=[...list.querySelectorAll('select')];selects.forEach(select=>select.disabled=true);
    let saved=0;
    try{for(const student of teacherRows){await api('teacher/attendance',{lesson_id:lesson.id,student_id:student.id,status:'present'});student.status='present';saved++}
      message(tr('Все ученики отмечены присутствующими. Сохранено в демо-сессии.'));
    }catch(error){message(tr('Сохранено ')+saved+tr(' из ')+teacherRows.length+'. '+error.message,true)}
    finally{if(teacherMode&&teacherLesson===lesson.id)renderTeacherStudents()}
  };
  updateTeacherSummary();
}
function updateTeacherSummary(){
  const marked=teacherRows.filter(student=>student.status).length;
  const present=teacherRows.filter(student=>student.status==='present').length;
  const absent=teacherRows.filter(student=>student.status==='absent').length;
  if(!$('teacherSummary'))return;
  $('teacherSummary').textContent=tr('Отмечено ')+marked+' / '+teacherRows.length+tr(' · присутствуют ')+present+tr(' · отсутствуют ')+absent;
}
$('teacherDemoButton').onclick=()=>openTeacher(true);
