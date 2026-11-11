"""Stable personal activity keys; never store filtered snapshots over Moodle data."""
import hashlib
from urllib.parse import urlsplit
from fastapi import HTTPException
from moodle_reader import content_url


def activity_key(url, moodle):
    try:
        target = content_url(url or '', moodle)
    except (HTTPException, ValueError):
        return None
    if not urlsplit(target).path.startswith('/mod/'):
        return None
    return hashlib.sha256(target.encode()).hexdigest()


def visible_activities(items, hidden, moodle):
    return [item for item in items if activity_key(item.get('url'), moodle) not in hidden]
