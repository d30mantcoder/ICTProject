"""Read currently visible Moodle data into a small mobile-friendly document."""
import re
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import HTTPException
from playwright.async_api import TimeoutError as BrowserTimeout


async def is_authenticated(page, moodle):
    location = urlsplit(page.url)
    if location.scheme != 'https' or location.netloc != urlsplit(moodle).netloc:
        return False
    # AITU's Moodle exports userId (capital I). Keep the older spelling as a
    # fallback, but an explicit userId=0 must still mean signed out.
    return await page.evaluate('() => Number(window.M?.cfg?.userId ?? window.M?.cfg?.userid ?? 0) > 0')


def content_url(value, moodle):
    url = urlsplit(value)
    if url.scheme != 'https' or url.netloc != urlsplit(moodle).netloc:
        raise HTTPException(400, 'Можно открыть только страницу Moodle AITU.')
    query = parse_qs(url.query)
    # The overview links to course/user.php with a saved user's ID. Always open
    # the report for the currently signed-in user, never replay that user ID.
    if url.path == '/course/user.php' and query.get('mode') == ['grade']:
        course = query.get('id', [''])[0]
        if course.isdigit():
            return moodle + '/grade/report/user/index.php?id=' + course
    allowed = url.path in {'/course/view.php', '/grade/report/user/index.php', '/grade/report/overview/index.php'}
    allowed = allowed or bool(re.fullmatch(r'/mod/(assign|quiz|resource|url|folder|page|book|forum|lesson|attendance)/view\.php', url.path))
    if not allowed:
        raise HTTPException(400, 'Эта страница пока не поддерживается мобильным интерфейсом.')
    params = {k: v[0] for k, v in query.items() if k in {'id', 'chapterid'} and v[0].isdigit()}
    if 'id' not in params:
        raise HTTPException(400, 'Не указан идентификатор курса или материала.')
    if url.path == '/mod/attendance/view.php':
        # ATT_VIEW_ALL: never replay studentid, action, sesskey or a partial date filter.
        params = {'id': params['id'], 'view': '5'}
    return moodle + url.path + '?' + urlencode(params)


async def prepare_timeline(page):
    """Use Moodle's All filter and expand its read-only activity pagination."""
    timeline = page.locator('[data-region="timeline"]')
    if not await timeline.count():
        return ['На странице не найден блок Timeline.']
    try:
        dates = timeline.locator('[data-region="view-selector"] [data-filtername="sortbydates"]')
        if await dates.count():
            await timeline.locator('[data-region="view-selector"] button').first.click(timeout=3000)
            await dates.click(timeout=3000)
        all_filter = timeline.locator('[data-region="day-filter"] [data-filtername="all"]')
        if await all_filter.count():
            await timeline.locator('[data-region="day-filter"] button').first.click(timeout=3000)
            await all_filter.click(timeout=3000)
        await page.wait_for_function('''() => {
            const t = document.querySelector('[data-region="timeline"]');
            const shown = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
            return t && ![...t.querySelectorAll('[data-region="event-list-loading-placeholder"]')].some(shown)
                && [...t.querySelectorAll('[data-region="event-list-item"], [data-region="no-events-empty-message"]')].some(shown);
        }''', timeout=15000)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            more = timeline.locator('[data-action="more-events"]:visible').first
            if not await more.count():
                return []
            if not await more.is_enabled():
                await page.wait_for_function('''() => {
                    const buttons = [...document.querySelectorAll('[data-region="timeline"] [data-action="more-events"]')];
                    return !buttons.some(b => (b.offsetWidth || b.offsetHeight) && b.disabled);
                }''', timeout=15000)
                continue
            count = await timeline.locator('[data-region="event-list-item"]').count()
            await more.click(timeout=3000)
            await page.wait_for_function('''count => {
                const t = document.querySelector('[data-region="timeline"]');
                const buttons = [...t.querySelectorAll('[data-action="more-events"]')];
                return t.querySelectorAll('[data-region="event-list-item"]').length > count
                    || !buttons.some(b => b.offsetWidth || b.offsetHeight || b.getClientRects().length);
            }''', arg=count, timeout=15000)
        return ['Timeline загружен частично: Moodle продолжает выдавать события. Обнови раздел.']
    except BrowserTimeout:
        return ['Не удалось полностью обновить Timeline. Показаны уже загруженные события.']


async def read_content(page, moodle, demo=False, section=None):
    if not demo and not await is_authenticated(page, moodle):
        raise HTTPException(409, 'Сессия Moodle завершилась. Войди ещё раз.')
    data = await page.evaluate("""section => {
      const root = document.querySelector('#region-main, [role=main], main') || document.body;
      const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const clean = text => text.replace(/\\s+/g, ' ').trim();
      const courseLinks = root.querySelectorAll('.coursename a[href]');
      const links = [...((section === 'home' || section === 'courses' || (section === 'attendance' && location.pathname === '/my/courses.php')) && courseLinks.length ? courseLinks : root.querySelectorAll('a[href]'))]
        .filter(a => visible(a) || (section === 'attendance' && location.pathname === '/course/view.php' && new URL(a.href).pathname === '/mod/attendance/view.php'))
        .map(a => ({title:clean(a.innerText || a.textContent || a.getAttribute('aria-label') || ''),url:a.href}))
        .filter(a => a.title && !/sesskey|token|logout/i.test(a.url));
      let date = '', day = null;
      const timeline = [];
      for (const el of root.querySelectorAll('[data-region="event-list-content-date"], [data-region="event-list-item"]')) {
        if (!visible(el)) continue;
        if (el.dataset.region === 'event-list-content-date') {
          date = clean(el.innerText); day = Number(el.dataset.timestamp) || null; continue;
        }
        const link = el.querySelector('.event-name a');
        if (!link) continue;
        const description = clean(el.querySelector('.event-name-container > small')?.innerText || '');
        const clock = clean(el.querySelector('.timeline-name > small')?.innerText || '');
        const parts = /^(\\d{1,2}):(\\d{2})$/.exec(clock);
        timeline.push({title: clean(link.innerText), url: link.href, date, time: clock,
          due: day && parts ? day + Number(parts[1])*3600 + Number(parts[2])*60 : null,
          due_label: link.getAttribute('aria-label') || '',
          course: description.includes('·') ? description.split('·').slice(1).join('·').trim() : '',
          event: description.split('·')[0].trim(),
          action: clean(el.querySelector('.event-action')?.innerText || '')});
      }
      const grades = [...root.querySelectorAll('#overview-grade tbody tr')].map(row => {
        const cells = [...row.cells]; const a = cells[0]?.querySelector('a');
        return {course: clean(cells[0]?.innerText || ''), grade: clean(cells[1]?.innerText || ''), url: a?.href || ''};
      }).filter(row => row.course);
      return {
        title: clean([...root.querySelectorAll('h1,h2')].find(e=>visible(e)&&!e.classList.contains('visually-hidden'))?.innerText || document.title),
        profile: clean(document.querySelector('.usermenu .usertext')?.innerText || ''),
        text: root.innerText.slice(0,60000),
        paragraphs:[...new Set([...root.querySelectorAll('p, .description, [data-region="event-item"]')]
          .filter(visible).map(e=>clean(e.innerText)).filter(t=>t && t.length<3000))].slice(0,50),
        table_headers:[...root.querySelectorAll('table')].filter(visible).slice(0,20).map(t => !!t.rows[0]?.querySelector('th')),
        tables:[...root.querySelectorAll('table')].filter(visible).slice(0,20).map(t=> {
          const grid=[];
          [...t.rows].filter(visible).forEach((row,ri)=>{
            grid[ri] ||= []; let col=0;
            for(const cell of row.cells){
              while(grid[ri][col]!==undefined)col++;
              for(let dy=0;dy<Math.max(1,cell.rowSpan);dy++){
                grid[ri+dy] ||= [];
                for(let dx=0;dx<cell.colSpan;dx++)grid[ri+dy][col+dx]=clean(cell.innerText);
              }
              col+=cell.colSpan;
            }
          });
          return grid.filter(row=>row.some(Boolean));
        }),
        links, timeline, grades
      };
    }""", section)
    seen = set()
    courses, activities = [], []
    for link in data.pop('links'):
        try:
            target = content_url(link['url'], moodle)
        except HTTPException:
            continue
        if target in seen:
            continue
        seen.add(target)
        item = {'title': link['title'], 'url': target}
        (courses if urlsplit(target).path == '/course/view.php' else activities).append(item)
    timeline, event_keys = [], set()
    for event in data['timeline']:
        try:
            event['url'] = content_url(event['url'], moodle)
        except HTTPException:
            continue
        key = (event['url'], event['date'], event['time'], event['event'])
        if key not in event_keys:
            event_keys.add(key)
            timeline.append(event)
    data['timeline'] = timeline
    for grade in data['grades']:
        try:
            grade['url'] = content_url(grade['url'], moodle)
        except HTTPException:
            grade['url'] = None
    path = urlsplit(page.url).path
    if path == '/mod/attendance/view.php':
        data['attendance_view'] = 'report'
    elif section == 'attendance':
        data['attendance_view'] = 'course' if path == '/course/view.php' else 'courses'
    return {**data, 'courses': courses, 'activities': activities, 'demo': demo}
