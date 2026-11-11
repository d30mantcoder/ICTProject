"""Public syllabus directory and app-owned PWA assets; no student data."""
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
SYLLABUSES = ROOT / "syllabuses"
router = APIRouter()


def syllabus_file(filename):
    path = SYLLABUSES / filename
    if (Path(filename).name != filename or path.suffix.lower() != ".pdf"
            or path.is_symlink() or not path.is_file()
            or path.resolve().parent != SYLLABUSES.resolve()):
        raise HTTPException(404, "Силлабус не найден.")
    return path


@router.get('/api/syllabuses')
async def syllabuses():
    items = []
    for path in sorted(SYLLABUSES.iterdir(), key=lambda p: p.name.casefold()):
        if path.suffix.lower() == '.pdf' and path.is_file() and not path.is_symlink():
            items.append({'title': path.stem.replace('_', ' '),
                          'url': '/syllabuses/' + quote(path.name, safe='')})
    return {'items': items}


@router.get('/syllabuses/{filename}')
async def syllabus(filename: str):
    path = syllabus_file(filename)
    return FileResponse(path, media_type='application/pdf', filename=path.name,
                        content_disposition_type='inline')


@router.get('/manifest.webmanifest', include_in_schema=False)
async def manifest():
    return FileResponse(ROOT / 'pwa/manifest.webmanifest', media_type='application/manifest+json')


@router.get('/sw.js', include_in_schema=False)
async def worker():
    return FileResponse(ROOT / 'pwa/sw.js', media_type='application/javascript',
                        headers={'Service-Worker-Allowed': '/'})


def install(app):
    app.include_router(router)
    app.mount('/campus-map', StaticFiles(directory=ROOT / 'vendor/aitumap', html=True), name='campus-map')
    app.mount('/pwa', StaticFiles(directory=ROOT / 'pwa'), name='pwa')
    app.mount('/vendor/pdfjs', StaticFiles(directory=ROOT / 'vendor/pdfjs'), name='pdfjs')
    app.mount('/student-extras', StaticFiles(directory=ROOT / 'student-extras'), name='student-extras')
