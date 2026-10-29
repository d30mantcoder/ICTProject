from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse,unquote
import re
ROOT=Path(__file__).resolve().parents[2]
VAR=Path(__file__).resolve().parent/'table-variants'
ROUTES={
 '/':(ROOT/'ICT Assignment 4 — Improved.pdf','application/pdf',False),
 '/presentation.pdf':(ROOT/'ICT Assignment 4 — Improved.pdf','application/pdf',False),
 '/presentation.pptx':(ROOT/'ICT Assignment 4 — Improved.pptx','application/vnd.openxmlformats-officedocument.presentationml.presentation',True),
 '/variants/':(VAR/'index.html','text/html; charset=utf-8',False),
 '/variants/presentation.pdf':(VAR/'Table variations.pdf','application/pdf',False),
 '/variants/presentation.pptx':(VAR/'Table variations.pptx','application/vnd.openxmlformats-officedocument.presentationml.presentation',True),
}
class Handler(BaseHTTPRequestHandler):
 def do_HEAD(self):self.serve(False)
 def do_GET(self):self.serve(True)
 def serve(self,body):
  path=unquote(urlparse(self.path).path)
  if path=='/variants':
   self.send_response(302);self.send_header('Location','/variants/');self.end_headers();return
  target=ROUTES.get(path)
  if not target and re.fullmatch(r'/variants/previews/(?:thumb-)?\d{2}\.(?:jpg|png)',path):
   target=(VAR/'previews'/path.rsplit('/',1)[1],'image/png' if path.endswith('.png') else 'image/jpeg',False)
  if not target or not target[0].is_file():self.send_error(404);return
  file,mime,download=target;size=file.stat().st_size;start=0;end=size-1;partial=False
  value=self.headers.get('Range','')
  if value:
   m=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
   if m and (m[1] or m[2]):
    if m[1]:start=int(m[1]);end=min(int(m[2]) if m[2] else end,end)
    else:start=max(0,size-int(m[2]))
    if start>end or start>=size:self.send_error(416);return
    partial=True
  self.send_response(206 if partial else 200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-cache')
  if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  if download:self.send_header('Content-Disposition','attachment; filename="'+('table-variations.pptx' if path.startswith('/variants/') else 'presentation.pptx')+'"')
  self.end_headers()
  if body:
   try:
    with file.open('rb') as stream:
     stream.seek(start);remaining=end-start+1
     while remaining:
      chunk=stream.read(min(65536,remaining))
      if not chunk:break
      self.wfile.write(chunk);remaining-=len(chunk)
   except (BrokenPipeError,ConnectionResetError):pass
if __name__=='__main__':
 print('Presentation server: http://0.0.0.0:1700/variants/',flush=True)
 ThreadingHTTPServer(('0.0.0.0',1700),Handler).serve_forever()
