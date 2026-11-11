"""Normalize read-only Attendance tables without guessing missing dates or custom statuses."""
import re
from datetime import date

MONTHS = {}
for i, names in enumerate([
    "jan january янв январь января қаң қаңтар",
    "feb february фев февраль февраля ақп ақпан",
    "mar march мар март марта нау наурыз",
    "apr april апр апрель апреля сәу сәуір",
    "may май мая мам мамыр",
    "jun june июн июнь июня мау маусым",
    "jul july июл июль июля шіл шілде",
    "aug august авг август августа там тамыз",
    "sep sept september сен сент сентябрь сентября қыр қыркүйек",
    "oct october окт октябрь октября қаз қазан",
    "nov november ноя ноябрь ноября қар қараша",
    "dec december дек декабрь декабря жел желтоқсан",
], 1):
    MONTHS.update(dict.fromkeys(names.split(), i))


def day_key(value):
    """Keep the date displayed by Moodle; do not reinterpret it in the browser timezone."""
    value = str(value).lower()
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", value)
    if m:
        parts = tuple(map(int, m.groups()))
    else:
        m = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", value)
        if m:
            d, month, year = map(int, m.groups())
        else:
            m = re.search(r"\b(\d{1,2})\s+([^\W\d_]+)\.?\s+(\d{4})\b", value)
            if not m or m[2] not in MONTHS:
                return None
            d, month, year = int(m[1]), MONTHS[m[2]], int(m[3])
        parts = year, month, d
    try:
        return date(*parts).isoformat()
    except ValueError:
        return None


def status_kind(value):
    label = re.sub(r"\s+", " ", str(value)).strip().casefold().rstrip(".")
    # Custom abbreviations (including 'A', 'P') are deliberately not interpreted.
    groups = {
        "present": {"present", "присутствовал", "присутствовала", "присутствие", "қатысты"},
        "absent": {"absent", "отсутствовал", "отсутствовала", "отсутствие", "қатыспады"},
        "late": {"late", "опоздал", "опоздала", "опоздание", "кешікті"},
        "excused": {"excused", "уважительная причина", "уважительно", "себепті"},
        "unmarked": {"", "?", "-", "—", "not marked", "не отмечено", "не выставлено"},
    }
    return next((kind for kind, values in groups.items() if label in values), "other")


def report_events(report, course, journal):
    events = []
    for table in report.get("tables", []):
        if not table:
            continue
        headers = [str(x).strip().casefold() for x in table[0]]
        def col(names):
            return next((i for i, text in enumerate(headers) if text in names), None)
        date_col = col({"date", "дата", "күні"})
        status_col = col({"status", "статус", "мәртебе"})
        if date_col is None or status_col is None:
            continue
        desc = col({"description", "описание", "сипаттама", "занятие"})
        points = col({"points", "баллы", "балл", "ұпай"})
        remarks = col({"remarks", "примечания", "примечание", "комментарий", "ескертулер"})
        for row in table[1:]:
            def cell(index):
                return str(row[index]).strip() if index is not None and index < len(row) else ""
            raw_date, raw_status = cell(date_col), cell(status_col)
            if not raw_date:
                continue
            events.append({
                "day": day_key(raw_date), "date_label": raw_date,
                "course": course["title"], "course_url": course["url"],
                "journal": journal["title"], "journal_url": journal["url"],
                "description": cell(desc), "status": raw_status,
                "kind": status_kind(raw_status), "points": cell(points), "remarks": cell(remarks),
            })
    return events
