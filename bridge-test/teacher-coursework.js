/* Group rosters and persistent assessments belong to the signed-in demo teacher. */
let teacherGroup='',teacherAssessment=null,teacherGroups=[],teacherCourseworkVersion=0,teacherWrites=0;
const assessmentTypes={midterm:'Midterm',endterm:'Endterm',final:'Final',homework:tr('Домашнее задание')};
function teacherField(form,label,id,type='text'){
  const control=node(type==='textarea'?'textarea':'input');control.id=id;control.name=id;
  if(type!=='textarea')control.type=type;
  const caption=node('label',tr(label),'field');caption.htmlFor=id;form.append(caption,control);return control;
}
function teacherSelect(form,label,id,values){
  const caption=node('label',tr(label),'field'),select=node('select');caption.htmlFor=id;select.id=id;select.name=id;
  for(const [value,title] of values){const option=node('option',title);option.value=value;select.append(option)}
  form.append(caption,select);return select;
}
function teacherStamp(value){return new Date(value).toLocaleString(uiLocale(),{timeZone:'Asia/Almaty',day:'numeric',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false})+tr(' · Астана')}
async function renderTeacherSection(section){
  const version=teacherCourseworkVersion;
  const data=await api('teacher/groups');
  if(version!==teacherCourseworkVersion||!teacherMode)return;
  teacherGroups=data.groups;
  const titles={'teacher-students':'Ученики и группы','teacher-exams':'Экзамены','teacher-homework':'Домашние задания'};
  $('pageTitle').textContent=tr(titles[section]);
  const filters=node('section',undefined,'card teacher-filters');
  const group=teacherSelect(filters,'Группа','teacherGroup',[['',tr('Все группы')],...teacherGroups.map(item=>[item.name,item.name])]);
  group.value=teacherGroups.some(item=>item.name===teacherGroup)?teacherGroup:'';teacherGroup=group.value;
  $('document').append(filters);
  const content=node('section');content.id='teacherSectionContent';$('document').append(content);
  group.onchange=async()=>{
    teacherGroup=group.value;teacherAssessment=null;
    if(section==='teacher-students')await renderTeacherDirectory(content);else await renderTeacherAssessments(content,section);
  };
  if(section==='teacher-students')await renderTeacherDirectory(content);
  else await renderTeacherAssessments(content,section);
}
async function renderTeacherDirectory(host){
  const version=++teacherCourseworkVersion,group=teacherGroup;
  host.replaceChildren(node('p',tr('Загружаем учеников…'),'hint'));
  try{
    const chosen=teacherGroups.filter(item=>!group||item.name===group);
    const results=await Promise.all(chosen.map(item=>api('teacher/groups/'+encodeURIComponent(item.name)+'/students')));
    if(version!==teacherCourseworkVersion||!host.isConnected)return;
    const students=results.flatMap(result=>result.students);
    host.replaceChildren();host.append(node('h2',tr('Ученики · ')+students.length));
    const search=teacherField(host,'Поиск ученика','teacherDirectorySearch');search.type='search';search.placeholder=tr('Имя или фамилия');
    const list=node('div',undefined,'teacher-students'),empty=node('p',tr('Ученики не найдены'),'empty');empty.hidden=true;
    for(const student of students){
      const card=node('article',undefined,'card teacher-directory-student');card.dataset.student=student.id;
      card.append(sourceNode('h3',student.name),node('p',tr('Группа')+': '+student.group,'hint'));list.append(card);
    }
    host.append(list,empty);
    search.oninput=()=>{let count=0;for(const card of list.children){card.hidden=!card.textContent.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase());if(!card.hidden)count++}empty.hidden=count>0};
  }catch(error){if(version===teacherCourseworkVersion){host.replaceChildren();message(error.message,true)}}
}
async function renderTeacherAssessments(host,section){
  const version=++teacherCourseworkVersion,category=section==='teacher-exams'?'exam':'homework';
  host.replaceChildren(node('p',tr('Загружаем работы…'),'hint'));
  try{
    const result=await api('teacher/assessments?category='+category+(teacherGroup?'&group='+encodeURIComponent(teacherGroup):''));
    if(version!==teacherCourseworkVersion||!host.isConnected)return;
    host.replaceChildren();
    if(teacherAssessment&&result.assessments.some(item=>item.id===teacherAssessment)){
      await renderTeacherGradebook(host,teacherAssessment,section);return;
    }
    teacherAssessment=null;
    const create=node('details',undefined,'card teacher-create');create.open=!result.assessments.length;
    create.append(node('summary',tr(category==='exam'?'Добавить экзамен':'Добавить ДЗ')));
    renderTeacherCreateForm(create,category,section,host);host.append(create);
    const filter=node('div');
    let kindFilter=null;
    if(category==='exam')kindFilter=teacherSelect(filter,'Тип экзамена','teacherExamFilter',[['',tr('Все экзамены')],['midterm','Midterm'],['endterm','Endterm'],['final','Final']]);
    host.append(filter);
    const list=node('div',undefined,'teacher-assessments');host.append(list);
    function draw(){
      list.replaceChildren();const items=result.assessments.filter(item=>!kindFilter?.value||item.kind===kindFilter.value);
      if(!items.length)list.append(node('p',tr(category==='exam'?'Экзаменов пока нет. Добавь первый экзамен для группы.':'Домашних заданий пока нет. Добавь первое ДЗ для группы.'),'empty'));
      for(const item of items){
        const card=node('article',undefined,'card teacher-assessment');card.dataset.assessment=item.id;
        card.append(node('span',assessmentTypes[item.kind],'tag'),sourceNode('h2',item.title),node('p',item.course+' · '+item.group_name,'hint'));
        card.append(localizedNode('p',()=>teacherStamp(item.scheduled_at),'hint'));
        if(category==='exam')card.append(node('p',tr('Длительность, мин')+': '+item.duration_minutes+' · '+tr(item.can_grade?'Завершён':'Запланирован'),'hint'));
        if(item.description)card.append(sourceNode('p',item.description,'paragraph'));
        if(item.file_count)card.append(node('p',tr('Файлы: ')+item.file_count,'hint'));
        const open=node('button',tr('Открыть журнал'),'primary wide');open.onclick=async()=>{teacherAssessment=item.id;await renderTeacherGradebook(host,item.id,section)};card.append(open);list.append(card);
      }
    }
    if(kindFilter)kindFilter.onchange=draw;draw();
  }catch(error){if(version===teacherCourseworkVersion){host.replaceChildren();message(error.message,true)}}
}
function renderTeacherCreateForm(host,category,section,sectionHost){
  if(!teacherGroups.length){host.append(node('p',tr('У преподавателя нет назначенных групп.'),'empty'));return}
  const form=node('form');form.id='teacherAssessmentForm';
  const group=teacherSelect(form,'Группа','assessmentGroup',teacherGroups.map(item=>[item.name,item.name]));group.value=teacherGroup||teacherGroups[0].name;
  const course=teacherSelect(form,'Курс','assessmentCourse',[]);
  function courses(){course.replaceChildren();for(const item of teacherGroups.find(item=>item.name===group.value).courses){const option=sourceNode('option',item.title);option.value=item.id;course.append(option)}}
  group.onchange=courses;courses();
  let type;
  if(category==='exam')type=teacherSelect(form,'Тип экзамена','assessmentKind',[['midterm','Midterm'],['endterm','Endterm'],['final','Final']]);
  const title=teacherField(form,'Название работы','assessmentTitle');title.required=true;title.maxLength=200;
  const description=teacherField(form,'Описание и инструкции','assessmentDescription','textarea');description.rows=4;description.maxLength=8000;
  const date=teacherField(form,category==='exam'?'Начало экзамена · время Астаны':'Срок сдачи · время Астаны','assessmentDate','datetime-local');date.required=true;
  let duration;
  if(category==='exam'){duration=teacherField(form,'Длительность, мин','assessmentDuration','number');duration.min=1;duration.max=480;duration.step=1;duration.value=90;duration.required=true}
  const files=teacherFilePicker(form,'assessmentFiles');
  files.input.addEventListener('change',()=>{if(!title.value.trim()&&files.input.files.length){title.value=files.input.files[0].name.slice(0,200);title.setCustomValidity('')}});
  const save=node('button',tr(category==='exam'?'Создать экзамен':'Создать ДЗ'),'primary wide');save.type='submit';
  const feedback=node('p',undefined,'teacher-feedback');feedback.setAttribute('role','status');
  form.append(save,feedback);host.append(form);
  form.onsubmit=async event=>{
    event.preventDefault();if(save.disabled)return;
    if(!title.value.trim()){title.setCustomValidity(tr('Укажи название работы.'));title.reportValidity();title.oninput=()=>title.setCustomValidity('');return}
    const selectedFiles=[...files.input.files];
    try{validateTeacherFiles(selectedFiles)}catch(error){feedback.textContent=error.message;return}
    const version=teacherCourseworkVersion;
    const payload={kind:category==='exam'?type.value:'homework',group:group.value,course_id:course.value,title:title.value,
      description:description.value,scheduled_at:date.value+':00+05:00',duration_minutes:category==='exam'?+duration.value:90};
    const controls=[...form.querySelectorAll('input,select,textarea,button')];controls.forEach(control=>control.disabled=true);teacherWrites++;
    feedback.textContent=tr('Сохраняем…');
    try{
      const created=await api('teacher/assessments',payload);
      let uploadError=null;
      try{await uploadTeacherFiles(created.id,selectedFiles,feedback)}catch(error){uploadError=error}
      if(version!==teacherCourseworkVersion||!sectionHost.isConnected)return;
      teacherGroup=created.group_name;$('teacherGroup').value=teacherGroup;teacherAssessment=created.id;
      await renderTeacherGradebook(sectionHost,created.id,section);
      message(uploadError?tr('Работа создана. Не все файлы загружены: ')+uploadError.message:tr('Работа добавлена.'),!!uploadError);
    }catch(error){feedback.textContent=error.message;message(error.message,true)}
    finally{teacherWrites--;controls.forEach(control=>control.disabled=false)}
  };
}
async function renderTeacherGradebook(host,id,section){
  const version=++teacherCourseworkVersion;
  host.replaceChildren(node('p',tr('Загружаем работы…'),'hint'));
  try{
    const data=await api('teacher/assessments/'+id);
    if(version!==teacherCourseworkVersion||!host.isConnected)return;
    const item=data.assessment;teacherAssessment=item.id;
    host.replaceChildren();
    const back=node('button',tr('‹ Назад к списку'),'text-button');back.onclick=async()=>{teacherAssessment=null;await renderTeacherAssessments(host,section)};host.append(back);
    const header=node('section',undefined,'card teacher-gradebook-header');
    header.append(node('span',assessmentTypes[item.kind],'tag'),sourceNode('h2',item.title),node('p',item.course+' · '+item.group_name,'hint'),localizedNode('p',()=>teacherStamp(item.scheduled_at),'hint'));
    if(item.kind!=='homework')header.append(localizedNode('p',()=>tr('Окончание: ')+teacherStamp(item.ends_at),'hint'));
    if(item.description)header.append(sourceNode('p',item.description,'paragraph'));
    if(!item.can_grade)header.append(node('p',tr('Экзамен ещё не завершён. Оценки можно выставить после окончания.'),'hint'));
    header.append(node('p',tr('Оценка от 0 до 100. Комментарий сохраняется вместе с оценкой.'),'hint'));host.append(header);
    renderTeacherAttachments(host,item.id,data.files||[]);
    const summary=node('p',undefined,'teacher-summary');summary.id='teacherGradeSummary';summary.setAttribute('aria-live','polite');host.append(summary);
    const update=()=>{summary.textContent=tr('Оценено ')+data.students.filter(student=>student.grade!==null).length+' / '+data.students.length};update();
    const search=teacherField(host,'Поиск ученика','teacherGradeSearch');search.type='search';
    const list=node('div',undefined,'teacher-students');host.append(list);
    for(const student of data.students){
      const card=node('article',undefined,'card teacher-grade-student');card.dataset.student=student.id;
      card.append(sourceNode('h3',student.name),node('p',student.group,'hint'));
      const form=node('form',undefined,'teacher-grade-form');form.dataset.student=student.id;
      const grade=teacherField(form,'Оценка (0–100)','grade-'+student.id,'number');grade.min=0;grade.max=100;grade.step='0.01';grade.value=student.grade??'';grade.disabled=!item.can_grade;
      const comment=teacherField(form,'Комментарий ученику','comment-'+student.id,'textarea');comment.rows=3;comment.maxLength=4000;comment.value=student.comment;comment.disabled=!item.can_grade;
      const save=node('button',tr('Сохранить оценку и комментарий'),'primary wide');save.type='submit';save.disabled=!item.can_grade;
      const status=node('p',student.updated_at?tr('Сохранено'):'','teacher-feedback');status.setAttribute('role','status');
      form.append(save,status);card.append(form);list.append(card);
      form.onsubmit=async event=>{
        event.preventDefault();if(save.disabled)return;
        const payload={student_id:student.id,grade:grade.value===''?null:+grade.value,comment:comment.value};
        grade.disabled=comment.disabled=save.disabled=true;teacherWrites++;status.textContent=tr('Сохраняем…');
        try{
          const result=await api('teacher/assessments/'+item.id+'/grades',payload);
          student.grade=result.grade;student.comment=result.comment;student.updated_at=result.updated_at;
          status.textContent=tr('Сохранено · ')+teacherStamp(result.updated_at);if(summary.isConnected)update();
        }catch(error){status.textContent=error.message;message(error.message,true)}
        finally{teacherWrites--;grade.disabled=comment.disabled=save.disabled=false}
      };
    }
    const empty=node('p',tr('Ученики не найдены'),'empty');empty.hidden=true;host.append(empty);
    search.oninput=()=>{let count=0;for(const card of list.children){card.hidden=!card.querySelector('h3').textContent.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase());if(!card.hidden)count++}empty.hidden=count>0};
  }catch(error){if(version===teacherCourseworkVersion){host.replaceChildren();message(error.message,true)}}
}


function validateTeacherFiles(files,existingCount=0){
  if(existingCount+files.length>10)throw new Error(tr('К работе можно прикрепить не более 10 файлов.'));
  for(const file of files){
    if(!file.size)throw new Error(tr('Нельзя загрузить пустой файл.')+' '+file.name);
    if(file.size>20*1024*1024)throw new Error(tr('Размер файла превышает 20 МБ.')+' '+file.name);
  }
}
function teacherFileSize(size){return new Intl.NumberFormat(uiLocale(),{maximumFractionDigits:1}).format(size>=1048576?size/1048576:size/1024)+' '+tr(size>=1048576?'МБ':'КБ')}
function teacherFilePicker(host,id){
  const input=teacherField(host,'Прикрепить файлы',id,'file');input.multiple=true;
  const help=node('p',tr('Любые файлы: PDF, Word, презентации, изображения, ZIP и другие. До 20 МБ каждый, не более 10 файлов на работу.'),'hint');
  const selected=node('p',undefined,'hint teacher-selected-files');selected.setAttribute('aria-live','polite');
  input.addEventListener('change',()=>{selected.textContent=[...input.files].map(file=>file.name+' · '+teacherFileSize(file.size)).join('\n')});
  host.append(help,selected);return {input,selected};
}
async function uploadTeacherFiles(assessmentId,files,status){
  let uploaded=0;
  for(const file of files){
    status.textContent=tr('Загружаем файл ')+(uploaded+1)+' / '+files.length+': '+file.name;
    // A raw File body allows bounded streaming on the server without multipart overhead.
    const response=await fetch('/api/teacher/assessments/'+assessmentId+'/files?filename='+encodeURIComponent(file.name),{
      method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file
    });
    const result=await response.json();
    if(!response.ok)throw new Error(tr(result.detail||'Не удалось загрузить файл.'));
    uploaded++;
  }
  return uploaded;
}
function renderTeacherAttachments(host,assessmentId,initialFiles){
  let savedFiles=initialFiles;
  const section=node('section',undefined,'card teacher-attachments');section.id='teacherAttachments';
  section.append(node('h2',tr('Файлы работы')));
  const list=node('div',undefined,'teacher-file-list');section.append(list);
  function draw(){
    list.replaceChildren();
    if(!savedFiles.length)list.append(node('p',tr('Файлов пока нет.'),'hint'));
    for(const file of savedFiles){
      const item=node('div',undefined,'teacher-file');
      const link=node('a',file.filename);link.href='/api/teacher/assessments/'+assessmentId+'/files/'+file.id;
      link.download=file.filename;link.setAttribute('aria-label',tr('Скачать файл: ')+file.filename);
      item.append(link,node('span',teacherFileSize(file.size),'hint'));list.append(item);
    }
  }
  draw();
  const form=node('form');form.id='teacherUploadForm';
  const picker=teacherFilePicker(form,'teacherAdditionalFiles');picker.input.required=true;
  const send=node('button',tr('Загрузить файлы'),'secondary wide');send.type='submit';
  const status=node('p',undefined,'teacher-feedback');status.setAttribute('role','status');
  form.append(send,status);section.append(form);host.append(section);
  form.onsubmit=async event=>{
    event.preventDefault();if(send.disabled)return;
    const files=[...picker.input.files];
    try{validateTeacherFiles(files,savedFiles.length)}catch(error){status.textContent=error.message;return}
    picker.input.disabled=send.disabled=true;teacherWrites++;
    let uploadError=null;
    try{
      try{await uploadTeacherFiles(assessmentId,files,status)}catch(error){uploadError=error}
      // Refresh metadata even after a partial failure: already stored files remain visible.
      const detail=await api('teacher/assessments/'+assessmentId);
      savedFiles=detail.files;draw();
      picker.input.value='';picker.selected.textContent='';
      status.textContent=uploadError?tr('Не все файлы загружены: ')+uploadError.message:tr('Файлы загружены.');
    }catch(error){status.textContent=error.message}
    finally{teacherWrites--;picker.input.disabled=send.disabled=false}
  };
}
