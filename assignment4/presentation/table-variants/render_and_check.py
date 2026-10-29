import pymupdf as fitz
from PIL import Image,ImageDraw
from pathlib import Path
import json
q=Path(__file__).parent; d=fitz.open(q/'Table variations.pdf');issues=[]
assert len(d)==19
for i,p in enumerate(d):
 p.get_pixmap(matrix=fitz.Matrix(1.25,1.25)).save(q/'previews'/f'{i:02}.png')
 im=Image.open(q/'previews'/f'{i:02}.png');im.thumbnail((1600,900));im.save(q/'previews'/f'{i:02}.jpg',quality=91)
 small=im.copy();small.thumbnail((700,394));small.save(q/'previews'/f'thumb-{i:02}.jpg',quality=87)
 spans=[s for b in p.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans'] if s['text'].strip()]
 for j,a in enumerate(spans):
  ra=fitz.Rect(a['bbox'])
  if not p.rect.contains(ra):issues.append([i,'outside',a['text']])
  for b in spans[j+1:]:
   rb=fitz.Rect(b['bbox']);r=ra&rb
   if not r.is_empty and r.width>3 and r.height>min(ra.height,rb.height)*.25:issues.append([i,'overlap',a['text'],b['text']])
thumb=Image.new('RGB',(1800,7*360),'#e2e2e2')
for i in range(len(d)):
 im=Image.open(q/'previews'/f'{i:02}.png');im.thumbnail((588,331));x=(i%3)*600;y=(i//3)*360;thumb.paste(im,(x,y));ImageDraw.Draw(thumb).text((x+5,y+333),'OVERVIEW' if i==0 else f'VARIANT {i:02}',fill='black')
thumb.save(q/'previews/contact.jpg')
report={'pages':len(d),'text_problems':issues,'editable_tables':None}
from zipfile import ZipFile
from lxml import etree as E
with ZipFile(q/'Table variations.pptx') as z:
 report['editable_tables']=sum(z.read(n).count(b'<a:tbl>') for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
(q/'qa.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
assert not issues
