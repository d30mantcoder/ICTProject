"""Bounded process metrics and aggregate-only health of the bridge's local stores."""
from collections import deque
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import time


class SystemStatus:
    def __init__(self):
        self.started = time.monotonic()
        self.requests = self.errors = 0
        self.durations = deque(maxlen=200)

    def record(self, status, duration):
        self.requests += 1
        self.errors += status >= 500
        self.durations.append(duration * 1000)

    def snapshot(self, root, sessions, capacity):
        disk = shutil.disk_usage(root)
        rss = None
        try:
            line = next(row for row in Path('/proc/self/status').read_text().splitlines() if row.startswith('VmRSS:'))
            rss = int(line.split()[1]) * 1024
        except (OSError, StopIteration, ValueError):
            pass
        return {'uptime_seconds': round(time.monotonic()-self.started), 'requests': self.requests,
                'errors_5xx': self.errors, 'response_ms': round(sum(self.durations)/len(self.durations), 1) if self.durations else None,
                'memory_bytes': rss, 'load_1m': os.getloadavg()[0] if hasattr(os, 'getloadavg') else None,
                'disk_total_bytes': disk.total, 'disk_free_bytes': disk.free,
                'sessions': len(sessions), 'session_capacity': capacity,
                'student_sessions': sum(item.identity is not None for item in sessions),
                'teacher_sessions': sum(item.teacher_demo is not None for item in sessions),
                'admin_sessions': sum(item.admin_demo for item in sessions)}


def local_database(path):
    path = Path(path)
    if not path.exists():
        return {'status': 'not_created', 'name': path.name, 'tables': [], 'size_bytes': 0}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
            # Names are from our schema, never user input; no row contents are returned.
            names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            tables = [{'name': name, 'rows': db.execute('SELECT COUNT(*) FROM "'+name.replace('"','""')+'"').fetchone()[0]} for name in names]
            db.execute('SELECT 1')
        size = sum(file.stat().st_size for file in (path, Path(str(path)+'-wal')) if file.exists())
        return {'status': 'ok', 'name': path.name, 'size_bytes': size,
                'tables': tables}
    except (sqlite3.Error, OSError):
        return {'status': 'unavailable', 'name': path.name, 'tables': [], 'size_bytes': None}
