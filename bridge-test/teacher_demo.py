"""Teacher view helpers. Rosters come from SchoolDatabase; demo marks stay isolated."""
from datetime import datetime
from zoneinfo import ZoneInfo

ASTANA = ZoneInfo('Asia/Almaty')
STATUSES = {'present', 'absent', 'late', 'excused'}


def workspace_view(workspace, now=None):
    now = now or datetime.now(ASTANA)
    lessons = [{**lesson, 'is_current': datetime.fromisoformat(lesson['starts_at']) <= now < datetime.fromisoformat(lesson['ends_at'])}
               for lesson in workspace['lessons']]
    current = next((lesson['id'] for lesson in lessons if lesson['is_current']), None)
    upcoming = next((lesson['id'] for lesson in lessons if datetime.fromisoformat(lesson['starts_at']) > now), None)
    return {**{key: workspace[key] for key in ('teacher', 'demo', 'source')}, 'lessons': lessons,
            'now': now.isoformat(), 'current_lesson_id': current, 'next_lesson_id': upcoming}


def lesson(workspace, lesson_id):
    found = next((item for item in workspace['lessons'] if item['id'] == lesson_id), None)
    if found is None:
        raise LookupError('Занятие не относится к этому преподавателю.')
    return found


def roster(workspace, lesson_id, students):
    lesson(workspace, lesson_id)
    marks = workspace['attendance'].get(lesson_id, {})
    return [{**student, 'status': marks.get(student['id'], {}).get('status'),
             'marked_at': marks.get(student['id'], {}).get('marked_at')} for student in students]


def mark_attendance(workspace, lesson_id, student_id, status, students):
    lesson(workspace, lesson_id)
    if student_id not in {student['id'] for student in students}:
        raise LookupError('Ученик не относится к этому занятию.')
    if status not in STATUSES:
        raise ValueError('Неизвестный статус посещаемости.')
    mark = {'status': status, 'marked_at': datetime.now(ASTANA).isoformat()}
    workspace['attendance'].setdefault(lesson_id, {})[student_id] = mark
    return mark
