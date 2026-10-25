from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from PIL import ImageFont
import re
BASE=Path('assignment4/presentation/previous-version.pptx')
OUT=Path('assignment4/presentation/restored-text-fixed.pptx')
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
A='{'+NS['a']+'}'
fonts={b:ImageFont.truetype('/usr/share/fonts/liberation-sans-fonts/LiberationSans-'+('Bold' if b else 'Regular')+'.ttf',1000) for b in [False,True]}
changes=[]
with ZipFile(BASE) as src, ZipFile(OUT,'w',ZIP_DEFLATED) as dst:
 for item in src.infolist():
  data=src.read(item.filename)
  if re.fullmatch(r'ppt/slides/slide\d+\.xml',item.filename):
   root=E.fromstring(data)
   for shape in root.xpath('//p:sp[p:txBody]',namespaces=NS):
    tx=shape.find('p:txBody',NS); text=''.join(tx.itertext()).strip()
    if not text: continue
    ext=shape.find('p:spPr/a:xfrm/a:ext',NS)
    if ext is None: continue
    body=tx.find('a:bodyPr',NS)
    if item.filename in ['ppt/slides/slide12.xml','ppt/slides/slide17.xml'] and not text.startswith(('C1.','D2.')):
     for attr, minimum in [('lIns',101600),('rIns',101600),('tIns',63500),('bIns',63500)]:
      body.set(attr,str(max(int(body.get(attr,'0')),minimum)))
    if item.filename=='ppt/slides/slide18.xml' and text=='D3. Team contributions':
     body.set('tIns','365760')
    w=int(ext.get('cx'))/12700;h=int(ext.get('cy'))/12700
    w-=(int(body.get('lIns','91440'))+int(body.get('rIns','91440')))/12700
    runs=tx.findall('.//a:r',NS)
    maxsz=0; length=0
    for run in runs:
     rp=run.find('a:rPr',NS)
     if rp is None: continue
     sz=int(rp.get('sz','1800'))/100; maxsz=max(maxsz,sz)
     bold=rp.get('b')=='1'
     for face in rp:
      if face.tag in [A+'latin',A+'ea',A+'cs',A+'sym'] and face.get('typeface')=='Arial Bold':
       face.set('typeface','Arial');rp.set('b','1');bold=True
     txt=run.findtext('a:t','',NS)
     length+=fonts[bold].getlength(txt)*sz/1000
    single=(len(tx.findall('a:p',NS))==1 and not tx.findall('.//a:br',NS) and h<=maxsz*1.7)
    if single:
     body.set('wrap','none')
     factor=min(1,(w-1)/length) if length else 1
     if factor<1:
      for rp in tx.findall('.//a:rPr',NS):
       if rp.get('sz'): rp.set('sz',str(int(int(rp.get('sz'))*factor)))
     for n in list(body):
      if n.tag in [A+'spAutoFit',A+'normAutofit',A+'noAutofit']:body.remove(n)
     E.SubElement(body,A+'noAutofit')
     changes.append((item.filename,text[:45],round(factor,3)))
   data=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
  dst.writestr(item,data)
print('Fixed single-line frames:',len(changes))
print('Material font reductions:',[c for c in changes if c[2]<.9])
# Verify that artwork, shape geometry, all wording, and package resources are untouched.
with ZipFile(BASE) as a, ZipFile(OUT) as b:
 for name in a.namelist():
  if not re.fullmatch(r'ppt/slides/slide\d+\.xml',name):assert a.read(name)==b.read(name),name
  else:
   ar=E.fromstring(a.read(name));br=E.fromstring(b.read(name))
   assert ar.xpath('//a:t/text()',namespaces=NS)==br.xpath('//a:t/text()',namespaces=NS),name
   for root in [ar,br]:
    for tx in root.xpath('//p:txBody',namespaces=NS):tx.getparent().remove(tx)
   assert E.tostring(ar)==E.tostring(br),name
print('PASS: all artwork, layout geometry, tables, and wording preserved.')
