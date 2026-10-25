"""Isolated browser checks for the mobile UI. API responses are synthetic fixtures."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
HTML=Path(__file__).with_name('index.html').read_text()
errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 page=b.new_page(viewport={'width':1000,'height':1000})
 page.on('pageerror',lambda e:errors.append(str(e)))
 phase={'phase':'idle','message':'Готово'}
 connected={'value':False}
 def api(route):
  path=route.request.url.split('/api/')[1]
  if path=='state':
   route.fulfill(status=200 if connected['value'] else 401,json={'active':False,'detail':'Подключитесь к ноутбуку'});return
  if path=='connect':connected['value']=True;route.fulfill(json={'ok':True});return
  if path=='resume':route.fulfill(json={'message':'Готово к входу'});return
  if path=='login/status':route.fulfill(json=phase);return
  if path=='login':phase.update(phase='mfa',number='42',message='Подтверди вход в Microsoft Authenticator');route.fulfill(json=phase);return
  if path=='attendance':
   events=[
    {'day':'2026-10-22','date_label':'22 октября 2026 09:00','course':'Linear Algebra','course_url':'course1','journal':'Attendance','description':'Практика','status':'Absent','kind':'absent','points':'0 / 2','remarks':''},
    {'day':'2026-10-22','date_label':'22 октября 2026 12:00','course':'Calculus','course_url':'course2','journal':'Attendance','description':'Лекция','status':'Present','kind':'present','points':'2 / 2','remarks':''},
    {'day':'2026-10-23','date_label':'23 октября 2026 09:00','course':'Linear Algebra','course_url':'course1','journal':'Attendance','description':'Практика','status':'?','kind':'unmarked','points':'? / 2','remarks':''},
    {'day':None,'date_label':'Дата не указана','course':'Linear Algebra','course_url':'course1','journal':'Attendance','description':'Без даты','status':'Custom','kind':'other','points':'','remarks':''}
   ]
   route.fulfill(json={'section':'attendance','attendance_view':'calendar','profile':'Test Student','updated':'12:00','events':events,
    'courses':[{'title':'Linear Algebra','url':'course1'},{'title':'Calculus','url':'course2'}],
    'reports':[{'course':'Linear Algebra','journal':'Attendance','tables':[[['Percentage','0.00%']]]}],'warnings':[]});return
  if path=='content':
   body=route.request.post_data_json;section=body.get('section','home')
   data={'section':section,'title':'Материалы курса' if body.get('url') else 'Мои курсы','profile':'Test Student','updated':'12:00','text':'Тестовые данные для проверки интерфейса','courses':[],'activities':[],'grades':[],'timeline':[],'detail':bool(body.get('url'))}
   if section=='attendance':
    if not body.get('url'):
     data.update(attendance_view='courses',courses=[{'title':'Linear Algebra','url':'https://lms.astanait.edu.kz/course/view.php?id=1'}])
    elif '/course/view.php' in body['url']:
     data.update(title='Linear Algebra',attendance_view='course',activities=[{'title':'Attendance — практика','url':'https://lms.astanait.edu.kz/mod/attendance/view.php?id=10&view=5'}])
    else:
     data.update(title='Attendance — практика',attendance_view='report',table_headers=[True,False],tables=[[['Дата','Занятие','Статус','Баллы','Комментарий'],['22 октября 09:00','Практика','Absent','0 / 2',''],['23 октября 09:00','Лекция','?','? / 2','']], [['Процент посещаемости','0.00%']]])
    route.fulfill(json=data);return
   if body.get('url'):data['paragraphs']=['Материалы курса и задания'];data['tables']=[[['Работа','Балл'],['Quiz 1','95']]]
   elif section=='home':data['courses']=[{'title':x,'url':'https://lms.astanait.edu.kz/course/view.php?id='+str(i)} for i,x in enumerate(['Information and Communication Technologies','Linear Algebra','Introduction to Programming','Foreign Language','Calculus','Cultural Studies','Physical Education'])]
   elif section=='grades':data['grades']=[{'course':'Linear Algebra','grade':'0.00','url':'https://lms.astanait.edu.kz/grade/report/user/index.php?id=1'},{'course':'Calculus','grade':'95.50'}]
   elif section=='dashboard':data['timeline']=[{'title':'Assignment 3','course':'Information and Communication Technologies','date':'25 октября','time':'23:59','event':'Задание','action':'Добавить ответ','url':'https://lms.astanait.edu.kz/mod/assign/view.php?id=1'}]
   route.fulfill(json=data);return
  route.fulfill(json={'ok':True})
 page.route('http://bridge.test/',lambda route:route.fulfill(content_type='text/html',body=HTML))
 page.route('**/api/**',api)
 page.route('**/attendance.js',lambda route:route.fulfill(content_type='text/javascript',body=Path(__file__).with_name('attendance.js').read_text()))
 page.route('**/features.js',lambda route:route.fulfill(content_type='text/javascript',body=Path(__file__).with_name('features.js').read_text()))
 page.route('**/features.css',lambda route:route.fulfill(content_type='text/css',body=Path(__file__).with_name('features.css').read_text()))
 page.goto('http://bridge.test/',wait_until='domcontentloaded')
 page.wait_for_timeout(700)
 assert page.locator('#code').count()==0
 assert connected['value']
 page.locator('#signIn').wait_for(state='visible')
 connected['value']=False
 page.evaluate("api('state')")
 assert connected['value'], 'Expired sessions must reconnect automatically'
 page.locator('#email').fill('test@example.test');page.locator('#password').fill('fixture-password')
 page.locator('#passwordToggle').click();assert page.locator('#password').get_attribute('type')=='text'
 page.locator('#passwordToggle').click();assert page.locator('#password').get_attribute('type')=='password'
 page.locator('#loginButton').click();page.locator('#mfaNumber').wait_for(state='visible');assert page.locator('#mfaNumber').inner_text()=='42'
 assert page.locator('#password').input_value()==''
 phase.update(phase='authenticated',number=None)
 page.locator('.course').first.wait_for(state='visible',timeout=6000)
 page.wait_for_timeout(500);
 search=page.get_by_role('searchbox');search.fill('linear');assert page.locator('.course:visible').count()==1
 search.fill('no match');assert page.get_by_text('Ничего не найдено').is_visible();search.fill('')
 page.locator('.course').first.click();page.locator('#backButton').wait_for(state='visible');page.locator('#backButton').click();page.locator('.course').first.wait_for(state='visible')
 page.locator('#menuButton').click();page.wait_for_timeout(450);assert page.locator('main').evaluate('(e)=>e.inert')

 page.locator('#mobileDrawer [data-section=grades]').click();page.locator('.grade-table').wait_for(state='visible');assert '0.00' in page.locator('.grade-table').inner_text()
 assert not page.locator('main').evaluate('(e)=>e.inert')
 page.locator('.grade-link').click();page.locator('#backButton').wait_for(state='visible');page.locator('#backButton').click()
 page.locator('#menuButton').click();page.locator('#mobileDrawer [data-section=dashboard]').click();page.locator('.timeline-card').wait_for(state='visible')
 page.locator('[data-feature=attendance]').click()
 page.locator('.att-calendar').wait_for(state='visible')
 assert page.locator('.course:visible').count()==0, 'No course/journal navigation step'
 assert page.locator('.att-day[data-day="2026-10-22"] .att-dot').count()==2
 page.locator('.att-day[data-day="2026-10-22"]').click()
 assert page.locator('.att-sessions .att-session').count()==2
 page.locator('#attendanceCourse').select_option('course1')
 assert page.locator('.att-sessions .att-session').count()==2
 assert 'Absent' in page.locator('.att-sessions').inner_text()
 assert '?' in page.locator('.att-sessions').inner_text()
 assert page.locator('.att-undated .att-session').count()==1
 page.get_by_role('button',name='Предыдущий месяц',exact=True).click()
 assert 'нет отметок' in page.locator('.att-sessions').inner_text()
 page.get_by_role('button',name='Следующий месяц',exact=True).click()
 page.locator('.att-source summary').click()
 assert '0.00%' in page.locator('.att-source').inner_text()
 page.locator('.att-source summary').click()
 assert page.locator('.icon-credit a').get_attribute('href')=='https://www.flaticon.com/uicons'
 assert page.locator('symbol#ui-calendar path').get_attribute('d')
 assert page.locator('.status-bar,.status-icons,.home-indicator').count()==0
 for width,height in [(320,568),(390,844),(430,700),(1440,900)]:
  page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(100)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
  assert page.locator('main').evaluate('(e)=>e.scrollWidth<=e.clientWidth'),width
  assert page.locator('header').evaluate('(e)=>e.offsetTop===0'),width
  page.locator('#menuButton').click();page.wait_for_timeout(420);assert page.locator('#mobileDrawer').is_visible();page.keyboard.press('Escape')
 page.set_viewport_size({'width':390,'height':844});page.evaluate("document.querySelector('main').scrollTop=0");page.wait_for_timeout(500);page.screenshot(path=str(Path(__file__).with_name('attendance-preview.png')))
 page.set_viewport_size({'width':390,'height':844});page.locator('#menuButton').click();page.locator('#mobileDrawer [data-section=home]').click();page.locator('.course').first.wait_for(state='visible');page.wait_for_timeout(450);
 assert not errors,errors
 print('PASS: connection, sign-in, password toggle, MFA, courses, search, detail/back, menu/Escape, grades including zero, timeline, one-click attendance calendar, day selection, month navigation, course filter and unknown dates/statuses; no overflow at 320/390/430/1440 px; no JavaScript errors. API responses are fixtures.')
 b.close()
