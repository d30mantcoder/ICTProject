/* Verified Telegram contacts are shared only with matching group tags. */
Object.assign(UI_EN, {
 'Одногруппники':'Classmates','Основная группа':'Main group','Английский':'English','Физра':'PE',
 'Подключить Telegram':'Connect Telegram','Проверить привязку':'Check connection',
 'Сначала привяжи Telegram, чтобы найти своих одногруппников.':'Connect Telegram to find your classmates.',
 'Открыть бота и нажать Start':'Open bot and press Start','Ссылка действует 10 минут.':'This link expires in 10 minutes.',
 'Бот пока не настроен или временно недоступен.':'The bot is not configured or is temporarily unavailable.',
 'Твой @username будет виден одногруппникам с такими же тегами групп.':'Your @username will be visible to classmates with matching group tags.',
 'Отключить Telegram':'Disconnect Telegram','Сохранить группы':'Save groups','Группы сохранены':'Groups saved',
 'Поиск по имени или @username':'Search by name or @username','Найти':'Search',
 'Одногруппников пока нет. Они появятся после привязки Telegram и указания такого же тега.':'No classmates yet. They will appear after connecting Telegram and entering the same group tag.',
 'Укажи тег выбранной группы и сохрани его.':'Enter and save the selected group tag.',
 'Используй те же теги, что и твои одногруппники. Регистр букв не важен.':'Use the same tags as your classmates. Letter case does not matter.',
 'Войди в свой студенческий аккаунт AITU.':'Sign in to your AITU student account.',
 'Telegram привязан':'Telegram connected',
 'Укажи username в Telegram и отправь боту /start, чтобы обновить контакт.':'Set your Telegram username and send /start to the bot to update your contact.'
});
extraSections.classmates=tr('Одногруппники');
quick.append(featureButton('classmates',tr('Одногруппники')));
footer.before(featureButton('classmates',tr('Одногруппники')));
const classmatesBaseLoad=loadContent;
loadContent=async function(section='home',url=null,refresh=false){
 if(section!=='classmates')return classmatesBaseLoad(section,url,refresh);
 if(busy)return;
 disposePDF();
 const version=++featureVersion;busy=true;featureShell(section);message('');
 $('reload').disabled=true;
 const root=$('document');root.setAttribute('aria-busy','true');
 try{
  if(demo||!connected){root.append(node('p',tr('Войди в свой студенческий аккаунт AITU.'),'hint'));return}
  const data=await api('telegram');if(version!==featureVersion)return;
  const run=async(button,action)=>{button.disabled=true;message('');try{await action()}catch(e){if(version===featureVersion)message(e.message,true)}finally{button.disabled=false}};
  if(!data.linked){
   root.append(node('p',tr('Сначала привяжи Telegram, чтобы найти своих одногруппников.')),
    node('p',tr('Твой @username будет виден одногруппникам с такими же тегами групп.'),'hint'));
   if(!data.available)root.append(node('p',tr('Бот пока не настроен или временно недоступен.'),'hint'));
   const connect=node('button',tr('Подключить Telegram'),'primary');connect.disabled=!data.available;
   const invitation=node('div');
   connect.onclick=()=>run(connect,async()=>{
    const link=await api('telegram/link',{});if(version!==featureVersion)return;
    const a=safeLink(link.url,tr('Открыть бота и нажать Start'));a.className='primary';
    invitation.replaceChildren(a,node('p',tr('Ссылка действует 10 минут.'),'hint'));
   });
   const check=node('button',tr('Проверить привязку'),'secondary');check.onclick=()=>loadContent('classmates');
   root.append(connect,invitation,check);return;
  }
  root.append(node('p',tr('Telegram привязан')+(data.username?' · @'+data.username:'')));
  if(!data.username)root.append(node('p',tr('Укажи username в Telegram и отправь боту /start, чтобы обновить контакт.'),'hint'));
  const unlink=node('button',tr('Отключить Telegram'),'text-button');
  unlink.onclick=()=>run(unlink,async()=>{await api('telegram/unlink',{});if(version===featureVersion)await loadContent('classmates')});root.append(unlink);
  root.append(node('p',tr('Используй те же теги, что и твои одногруппники. Регистр букв не важен.'),'hint'));
  const categories={main:'Основная группа',english:'Английский',pe:'Физра'},inputs={};
  const form=node('form',undefined,'classmates-form');
  for(const [key,label] of Object.entries(categories)){
   const wrap=node('label',tr(label)),input=node('input');input.value=data.groups[key];input.maxLength=60;input.name=key;
   input.placeholder={main:'SE-2623',english:'B2-1',pe:'PE-4'}[key];wrap.append(input);form.append(wrap);inputs[key]=input;
  }
  const save=node('button',tr('Сохранить группы'),'primary');save.type='submit';form.append(save);root.append(form);
  const searchForm=node('form',undefined,'classmates-search'),category=node('select'),query=node('input'),find=node('button',tr('Найти'),'secondary');
  category.setAttribute('aria-label',tr('Основная группа'));
  for(const [key,label] of Object.entries(categories)){const option=node('option',tr(label));option.value=key;category.append(option)}
  query.placeholder=tr('Поиск по имени или @username');query.setAttribute('aria-label',query.placeholder);query.maxLength=100;
  find.type='submit';searchForm.append(category,query,find);root.append(searchForm);
  const results=node('div');results.setAttribute('aria-live','polite');root.append(results);
  let searchVersion=0;
  async function search(){
   const request=++searchVersion,kind=category.value;
   const found=await api('classmates?category='+encodeURIComponent(kind)+'&q='+encodeURIComponent(query.value));
   if(version!==featureVersion||request!==searchVersion)return;
   results.replaceChildren();
   if(!data.groups[kind]){results.append(node('p',tr('Укажи тег выбранной группы и сохрани его.'),'hint'));return}
   if(!found.items.length)results.append(node('p',tr('Одногруппников пока нет. Они появятся после привязки Telegram и указания такого же тега.'),'hint'));
   for(const item of found.items){const card=node('section',undefined,'card');card.append(sourceNode('h3',item.name),safeLink('https://t.me/'+encodeURIComponent(item.username),'@'+item.username));results.append(card)}
  }
  form.onsubmit=e=>{e.preventDefault();run(save,async()=>{const saved=await api('classmates/groups',Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,v.value])));if(version!==featureVersion)return;data.groups=saved.groups;message(tr('Группы сохранены'));await search()})};
  searchForm.onsubmit=e=>{e.preventDefault();run(find,search)};
  category.onchange=()=>run(find,search);
  await search();
 }catch(e){if(version===featureVersion)message(e.message,true)}
 finally{busy=false;$('reload').disabled=false;root.setAttribute('aria-busy','false')}
};
