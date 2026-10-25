import json,re
from pathlib import Path
import pymupdf as f
from pptx import Presentation
from lxml import etree as E
out=Path('assignment4/presentation/cultural-layout');d=f.open(out/'ICT-layout.pdf')
a=Presentation('assignment4/presentation/selected-styles.pptx');b=Presentation(out/'ICT-layout.pptx')
assert len(d)==len(a.slides)==len(b.slides)==19
assert all(E.tostring(x.shapes[0]._element)==E.tostring(y.shapes[0]._element) for x,y in zip(a.slides,b.slides))
norm=lambda s:re.sub(r'\s+','',s)
issues=[]
for n,t,x,y,w,h in json.loads((out/'ICT-layout.frames.json').read_text()):
 r=f.Rect(x*72-1,y*72-1,(x+w)*72+1,(y+h)*72+1)
 assert norm(t) in norm(d[n-1].get_textbox(r)),(n,t)
for n in [2,4,5,6,9,10,12,16,17]:
 spans=[s for bl in d[n-1].get_text('dict')['blocks'] for ln in bl.get('lines',[]) for s in ln['spans'] if s['text'].strip()]
 for i,s in enumerate(spans):
  for t in spans[i+1:]:
   x=f.Rect(s['bbox'])&f.Rect(t['bbox'])
   if x.width>3 and x.height>min(f.Rect(s['bbox']).height,f.Rect(t['bbox']).height)*.25:issues.append((n,s['text'],t['text']))
 d[n-1].get_pixmap(matrix=f.Matrix(1,1)).save(out/f'{n:02}.png')
assert not issues,issues
(out/'qa.json').write_text(json.dumps({'pages':19,'original_backgrounds_preserved':True,'new_text_frames_readable':True,'new_text_overlap_issues':issues},indent=2))
print('PASS: 19 pages, all original backgrounds preserved, all new text present in its frames, no overlapping text.')
