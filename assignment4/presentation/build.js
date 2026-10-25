const pptxgen = require('/tmp/presentation-tools/node_modules/pptxgenjs');
const fs = require('fs');
const path = require('path');
const p = new pptxgen();
p.layout = 'LAYOUT_WIDE';
p.author = 'Salima Zimbekkyzy, Azhar Saparzholova, Nurassyl Oralbekov';
p.subject = 'ICT Assignment 4 — My AITU / LMS bridge';
p.title = 'Multimedia Technologies — My AITU';
p.company = 'Astana IT University';
p.lang = 'en-GB';
p.theme = {headFontFace:'Arial', bodyFontFace:'Arial', lang:'en-GB'};
const W=13.333333, H=7.5;
const C={ink:'241C3F', muted:'746C85', purple:'6540DB', deep:'241448', lilac:'E9E1FC', bg:'F7F5FB', white:'FFFFFF', teal:'12836F', tealBg:'E5F5EE', amber:'8C5D16', amberBg:'FFF1D8', border:'E2DBEE'};
const A=path.join(__dirname,'assets');
const source=JSON.parse(fs.readFileSync(path.join(__dirname,'source-text.json'),'utf8'));
const measures=JSON.parse(fs.readFileSync(path.join(A,'measurements.json'),'utf8'));
const layout=[];
function text(s,str,x,y,w,h,size=18,color=C.ink,bold=false,extra={}) {
  s.addText(str,{x,y,w,h,fontFace:'Arial',fontSize:size,color,bold,margin:0,vertAlign:'baseline',valign:'top',paraSpaceAfterPt:0,breakLine:false,...extra});
  layout.push({slide:p._slides.length,text:typeof str==='string'?str:'[rich text]',x,y,w,h,size,color});
}
function box(s,x,y,w,h,fill=C.white,r=.15,border=null){
  s.addShape(r?p.ShapeType.roundRect:p.ShapeType.rect,{x,y,w,h,radius:r,rectRadius:r,fill:{color:fill},line:{color:border||fill,width:border?0.8:0},radius:r});
}
function circle(s,x,y,d,fill){s.addShape(p.ShapeType.ellipse,{x,y,w:d,h:d,fill:{color:fill},line:{color:fill,width:0}});}
function chip(s,label,x,y,w=1.6,fill=C.lilac,color=C.purple){box(s,x,y,w,.33,fill,.16);text(s,label,x+.1,y+.065,w-.2,.19,10,color,true,{align:'center'});}
function dots(s,x,y,color){for(let i=0;i<4;i++)for(let j=0;j<4;j++)box(s,x+i*.18,y+j*.18,.065,.065,color,0);}
function footer(s,n,dark=false){text(s,'MY AITU  /  ICT ASSIGNMENT 4',.58,7.04,9,.18,9.3,dark?'C7B9EC':C.muted,true);text(s,String(n).padStart(2,'0')+' / 19',11.7,7.04,1.04,.18,9.3,dark?'C7B9EC':C.muted,false,{align:'right'});}
function slide(n,section,title,subtitle='',dark=false){
 const s=p.addSlide();s.background={color:dark?C.deep:C.bg};
 if(section)text(s,section.toUpperCase(),.58,.38,11.9,.2,10.5,dark?'C9B7FA':C.purple,true,{charSpacing:1.4});
 if(title)text(s,title,.58,.87,12.15,.65,33,dark?C.white:C.ink,true);
 if(subtitle)text(s,subtitle,.6,1.62,12.03,.4,14,dark?'D7CBF1':C.muted);
 footer(s,n,dark);
 s.addNotes('SOURCE CONTENT FROM ORIGINAL SLIDE '+n+'\n'+(source[n-1]||'')+'\n\nDesign revision: explicit text areas, stable fonts and editable tables. JPEG measurements added from supplied screenshot.');
 return s;
}
function table(s,heads,rows,x,y,width,colW,rowH=.46,fontSize=13,highlight=-1){
 let all=[heads,...rows].map((r,i)=>r.map((v,j)=>({text:String(v),options:{bold:i===0||j===0,color:i===0?C.white:(i===highlight?C.purple:C.ink),fill:i===0?C.purple:(i===highlight?C.lilac:(i%2?C.white:'F0ECF8')),margin:[5,8,5,8]}})));
 const totalH=rowH*(rows.length+1),headerH=Math.min(.52,rowH);
 const rowHeights=[headerH,...rows.map(()=>(totalH-headerH)/rows.length)];
 s.addTable(all,{x,y,w:width,h:totalH,colW,rowH:rowHeights,fontFace:'Arial',fontSize,border:{type:'solid',pt:.6,color:C.bg},autoPage:false,margin:6,valign:'middle',color:C.ink,paraSpaceAfterPt:0});
}
function card(s,x,y,w,h,kicker,title,body,fill=C.white){box(s,x,y,w,h,fill);text(s,kicker,x+.25,y+.23,w-.5,.22,10.2,C.purple,true);text(s,title,x+.25,y+.7,w-.5,.62,24,C.ink,true);text(s,body,x+.25,y+1.5,w-.5,h-1.7,15,C.muted);}
function phone(s,x,y,h){const sw=h*390/844;box(s,x-.11,y-.11,sw+.22,h+.22,'141125',.16);s.addImage({path:path.join(A,'attendance.png'),x,y,w:sw,h});}
function qr(s,file,x,y,size){if(fs.existsSync(path.join(A,file))){box(s,x-.12,y-.12,size+.24,size+.24,C.white,.12);s.addImage({path:path.join(A,file),x,y,w:size,h:size});}}
function linkButton(s,label,url,x,y,w,fill=C.purple){box(s,x,y,w,.57,fill,.16);text(s,label,x+.2,y+.15,w-.4,.24,14,C.white,true,{hyperlink:{url},align:'center'});}

// 01 — Cover. A real project screen anchors the visual identity.
{
 const s=slide(1,'','','',true);s.background={color:C.purple};
 circle(s,8.2,.3,4.5,'7653E2');circle(s,9.6,4.75,2.0,'825FE8');dots(s,7.9,5.95,'B8A3F4');
 chip(s,'ASSIGNMENT 04',.62,.66,1.65,'8565E5',C.white);
 text(s,'Multimedia\nTechnologies',.6,1.52,7.05,1.95,45,C.white,true,{lineSpacingMultiple:1.0});
 text(s,'The media layer of My AITU',.63,3.72,6.8,.42,23,'EEE7FF');
 text(s,'Formats, optimisation and accessible design\nfor the LMS bridge prototype.',.63,4.34,6.5,.8,18,'EEE7FF');
 text(s,'Salima Zimbekkyzy  ·  Azhar Saparzholova\nNurassyl Oralbekov',.64,5.63,6.7,.68,15.5,C.white);
 text(s,'SE-2623  /  ICT',.64,6.47,5,.22,11,'D7CBF1',true);
 phone(s,9.05,.75,5.74);
}
// 02 — The user's requested Canva-style table.
{
 const s=slide(2,'Part A / Format strategy','Choose the format for the job','Three questions guide every choice: what is it, where is it used, and what must stay sharp?');
 table(s,['MEDIA','DECISION TO MAKE','PROJECT APPLICATION'],[
  ['Images','Balance crisp interface details against file size.','WebP preview, PNG source and SVG icons'],
  ['Audio','Separate distribution files from editing masters.','If narration is added: AAC / MP3; WAV for editing'],
  ['Video','Choose both a container and a codec.','Planned: MP4 with H.264 video and AAC audio']
 ],.6,2.2,12.13,[1.8,4.85,5.48],.87,17);
 const items=[['01','QUALITY'],['02','FILE SIZE'],['03','COMPATIBILITY']];
 items.forEach(([n,l],i)=>{const x=.65+i*4.05;circle(s,x,6.02,.39,C.lilac);text(s,n,x+.06,6.12,.27,.15,9,C.purple,true,{align:'center'});text(s,l,x+.56,6.1,3.1,.25,12,C.muted,true,{charSpacing:.6});});
}
// 03 — One complete A1 table, per assignment requirements.
{
 const s=slide(3,'A1 / Format comparison','One table. Ten media formats.');
 const rows=[
  ['PNG','Image','Lossless','Alpha; APNG','Large photos','Broad','UI evidence'],
  ['JPEG','Image','Lossy','None','Small photos','Broad','Photos'],
  ['WebP','Image','Both modes','Alpha; motion','Compact','Modern','App preview'],
  ['SVG','Image','Vector / text','Alpha; motion','Tiny icons','Broad','UI icons'],
  ['MP3','Audio','Lossy','N/A','Small','Broad','Speech / music'],
  ['AAC / M4A','Audio','Lossy','N/A','Small','Broad*','Narration'],
  ['WAV / PCM','Audio','Uncompressed','N/A','Large','Broad*','Editing master'],
  ['MP4 / H.264','Video','Usually lossy','Motion','Bitrate-based','Broad*','Demo delivery'],
  ['WebM / VP9','Video','Usually lossy','Motion; alpha*','Bitrate-based','Modern*','Web playback'],
  ['MOV / H.264','Video','Usually lossy','Motion','Bitrate-based','Limited web','Editing / transfer']
 ];
 table(s,['FORMAT','TYPE','COMPRESSION','ALPHA / MOTION','TYPICAL SIZE','SUPPORT','PROJECT USE'],rows,.6,1.83,12.13,[1.62,.8,1.8,1.85,1.65,1.3,3.11],.373,12.0,3);
 text(s,'Container = the package. Codec = how the media is encoded.',.65,6.22,11.95,.3,17,C.purple,true);
 text(s,'*Support depends on codec, OS and device. Size varies with content, resolution, bitrate and duration.\nSources cited in the original: MDN Image file type guide; Media container formats.',.65,6.61,11.9,.32,9.5,C.muted);
}
// 04 — Actual measurements, not missing-image placeholders.
{
 const s=slide(4,'A2 / Measured experiment','Same screen. Four encodings.','390 × 844 pixels in every file. Measurements use binary KiB: 1 KiB = 1024 bytes.');
 const ratings=['Sharp source','Minor edge artifacts','Visible edge artifacts','Readable, compact'];
 table(s,['FORMAT / SETTING','SIZE (KiB)','VISUAL OBSERVATION'],measures.map((m,i)=>[m.label,m.kib.toFixed(2),ratings[i]]),.6,2.19,8.1,[2.4,1.6,4.1],.68,16,4);
 box(s,9.05,2.2,3.68,3.39,C.purple);text(s,'73.0%',9.33,2.77,3.12,.95,52,C.white,true);
 text(s,'smaller than PNG',9.35,3.89,3.03,.38,20,C.white,true);text(s,'WebP Q80 saves 42.64 KiB\nat the original resolution.',9.35,4.53,3.03,.68,15,'EDE5FF');
 chip(s,'VIDEO EVIDENCE PENDING',.65,6.04,2.77,C.amberBg,C.amber);
 text(s,'The same 10-second clip still needs two measured exports.',3.65,6.08,8.6,.3,15,C.muted);
 text(s,'PNG / WebP: supplied files. JPEGs: exported from the same PNG at Q80 / Q40, 4:2:0 chroma, optimised, 25 Oct 2026.',.65,6.65,12,.24,10,C.muted);
}
// 05 — Identical crops from the four actual encodings.
{
 const s=slide(5,'A2 / Visual evidence','Look at the edges, not just the number.','Identical 360 × 360 pixel crops, displayed at the same scale.');
 const labels=['PNG','JPEG Q80','JPEG Q40','WebP Q80'];
 const quality=['Crisp source text','Light halos on edges','More obvious ringing','Readable UI details'];
 for(let i=0;i<4;i++){
  let x=.6+i*3.075;box(s,x,2.17,2.9,3.95,C.white);
  text(s,labels[i],x+.18,2.37,2.54,.32,18,C.ink,true);
  s.addImage({path:path.join(A,'crop-'+i+'.png'),x:x+.17,y:2.98,w:2.56,h:2.56});
  text(s,measures[i].kib.toFixed(2)+' KiB',x+.18,5.78,2.54,.22,12.5,C.purple,true);
  text(s,quality[i],x+.05,6.35,2.8,.27,12,C.muted,false,{align:'center'});
 }
}
// 06 — Native chart plus the rationale behind the actual choices.
{
 const s=slide(6,'A2 / Our format choices','Smaller files. Same screen dimensions.');
 box(s,.6,1.95,7.03,4.74,C.white);
 text(s,'Preview image size (KiB)',.88,2.23,6.4,.31,19,C.ink,true);
 s.addChart(p.ChartType.bar,[{name:'KiB',labels:['PNG','WebP Q80'],values:[58.39,15.75]}],{x:.82,y:2.94,w:6.46,h:2.67,barDir:'bar',catAxisLabelFontFace:'Arial',catAxisLabelFontSize:14,valAxisLabelFontSize:10,valAxisMinVal:0,valAxisMaxVal:65,valAxisMajorUnit:20,showValue:true,dataLabelPosition:'outEnd',dataLabelFormatCode:'0.00',dataLabelColor:C.ink,dataLabelBkgrdColor:C.white,dataLabelFontSize:14,chartColors:['B9A8EB',C.purple],varyColors:true,showLegend:false,showCatName:false,showBorder:false,showCatName:false,showTitle:false,catAxisLineShow:false,valAxisLineShow:false,valGridLine:{color:'E8E2F2',size:.5},catGridLine:{style:'none'},showCatName:false,invertedColors:[C.purple],gapSizePct:90});
  text(s,'42.64 KiB saved per preview',.94,5.91,6.23,.33,19,C.purple,true);
  const xs=8.07;
  [['WebP Q80','Use for the attendance preview.'],['PNG','Retain the lossless evidence image.'],['Inline SVG + CSS','Use vectors for icons and CSS for motion.']].forEach(([title,body],i)=>{const y=2.04+i*1.4;circle(s,xs,y,.4,C.lilac);text(s,String(i+1),xs+.12,y+.08,.2,.2,12,C.purple,true);text(s,title,xs+.61,y,4.05,.34,20,C.ink,true);text(s,body,xs+.61,y+.49,3.91,.64,15,C.muted);});
 text(s,'File-size reduction does not prove faster network loading.',8.08,6.29,4.55,.36,12,C.muted);
}
// 07 — All 18 icons, with two readable columns rather than one long table.
{
 const s=slide(7,'B1 / Interface icons','18 icons. One HTML response.','Inline SVG markup is embedded in the page; the values below are source bytes, not separate downloads.');
 const icons=[['3 · Book','Courses / nav','740'],['4 · Calendar','Tasks / attendance','1,162'],['5 · Graduation','Grades','857'],['6 · User','Account','869'],['7 · Menu','Navigation','561'],['8 · Close','Navigation','441'],['9 · Down','Account menu','391'],['10 · Sign-out','Account menu','906'],['11 · Refresh','Reload','945'],['12 · Search','Course search','669'],['13 · Eye','Password visibility','935'],['14 · Check','Attendance','366'],['15 · Absent','Attendance','442'],['16 · Clock','Attendance time','777'],['17 · Minus','Unmarked status','284'],['18 · Left arrow','Previous month','416'],['19 · Next arrow','Next month','404'],['20 · List','Attendance status','1,010']];
 table(s,['ASSET','WHERE USED','BYTES'],icons.slice(0,9),.6,2.2,5.9,[2.0,2.95,.95],.391,12.4);
 table(s,['ASSET','WHERE USED','BYTES'],icons.slice(9),6.83,2.2,5.9,[2.0,2.95,.95],.391,12.4);
 text(s,'Flaticon Uicons Regular Rounded  ·  SVG viewBox 300 × 300  ·  Free licence with visible footer attribution.',.66,6.47,11.9,.33,11.4,C.muted);
}
// 08 — Remaining seven assets, with a native table.
{
 const s=slide(8,'B1 / Asset inventory','The rest of the media stack','25 assets in the inventory: 18 icons and these seven visual, type and support elements.');
 const rows=[['1 · Attendance preview','Sign-in','WebP · 390 × 844','15.75 KiB','Own + icons¹'],['2 · LMS wordmark','Sign-in','CSS / text · 68 × 68','Embedded','Own'],['21 · Login pulse','Login progress','CSS · 2 s loop','Embedded','Own'],['22 · Entrance motion','Transitions','CSS · 0.4 s','Embedded','Own'],['23 · Campus map','Map section','Responsive iframe','Variable','Yuujiso · MIT²'],['24 · Inter font','Interface','Web font · variable','Variable','Inter · OFL³'],['25 · Remote view','Optional support','JPEG Q70 · 1100 × 800','Variable','Private session']];
 table(s,['ASSET','WHERE','FORMAT / DIMENSIONS','SIZE','SOURCE / LICENCE'],rows,.6,2.16,12.13,[3.0,1.65,3.13,1.65,2.7],.485,12.5);
 text(s,'¹ Flaticon attribution in footer.  ² github.com/Yuujiso/aitumap.  ³ github.com/rsms/inter.',.66,6.25,11.9,.25,10.5,C.muted);
 text(s,'The remote browser view is private and must stay out of the demo. Evidence PNGs and two unused SVG symbols are not loaded by the interface.',.66,6.62,11.9,.32,10.5,C.muted);
}
// 09 — Separate measured payload from unmeasured runtime performance.
{
 const s=slide(9,'B2 / Integration & optimisation','A lighter payload, with clear limits.');
 const metrics=[['73.0%','smaller preview'],['30.8%','smaller controlled file set'],['0','expected image-request delta']];
 metrics.forEach(([num,label],i)=>{let x=.6+i*4.11;box(s,x,1.93,3.91,1.35,i===0?C.purple:C.white);text(s,num,x+.22,2.12,3.45,.59,34,i===0?C.white:C.purple,true);text(s,label,x+.22,2.83,3.45,.22,12.2,i===0?'ECE4FF':C.muted);});
 table(s,['CONTROLLED LOCAL PAYLOAD','PNG VERSION','WEBP VERSION','CHANGE'],[['Preview image','59,787 B','16,126 B','−73.0%'],['4 front-end files + preview','141,601 B','97,941 B','−30.8%']],.6,3.69,12.13,[5.13,2.35,2.35,2.3],.51,14);
 text(s,'Integrated',.65,5.57,5.8,.3,19,C.ink,true);text(s,'Responsive 250 px preview, inline SVG icons, CSS login pulse and reduced-motion support.',.65,6.0,5.72,.63,14,C.muted);
 text(s,'Still to measure',6.97,5.57,5.75,.3,19,C.ink,true);text(s,'DevTools: transferred bytes, requests and Finish/Load time on Fast 4G with cache disabled.',6.97,6.0,5.72,.63,14,C.muted);
 text(s,'Source: Part B inventory, 23 Oct 2026. Calculated local file bytes; external traffic and compression are excluded.',.65,6.74,12,.19,9.3,C.muted);
 s.addNotes('The 30.8% is a controlled local file-payload calculation, not a browser Network measurement. Headers, compression, API calls, Google Fonts and iframe traffic are excluded. The 360 px viewport check and <3 s at 1,000 users remain unverified. See assignment4/part_b.md.');
}
// 10 — Six accessibility findings, with status immediately visible.
{
 const s=slide(10,'B3 / Media accessibility','Make the experience understandable.','Implemented behaviours and checks from the prototype inventory.');
 const items=[['01','Descriptive alt text','The attendance preview describes the calendar and status counts.','IMPLEMENTED'],['02','Decorative SVGs','Icons are hidden from screen readers; controls keep text or labels.','IMPLEMENTED'],['03','Reduced motion','The user’s preference disables animations and transitions.','IMPLEMENTED'],['04','Visible progress','Login progress has text and a visual pulse. No sound-only information.','IMPLEMENTED'],['05','Captions / transcript','No speech audio or video is embedded in the prototype.','NOT APPLICABLE'],['06','Text over images','Captions sit below images; live text does not overlay raster images.','NOT APPLICABLE']];
 items.forEach(([n,title,body,status],i)=>{let x=.6+(i%3)*4.11,y=2.16+Math.floor(i/3)*2.28;box(s,x,y,3.91,2.08,C.white);chip(s,status,x+.2,y+.2,status==='IMPLEMENTED'?1.5:1.93,status==='IMPLEMENTED'?C.tealBg:C.lilac,status==='IMPLEMENTED'?C.teal:C.purple);text(s,title,x+.2,y+.75,3.51,.35,18,C.ink,true);text(s,body,x+.2,y+1.25,3.51,.65,13,C.muted);});
}
// 11 — Section transition, based on the existing storyboard.
{
 const s=slide(11,'Part C / Multimedia presentation','','',true);dots(s,11.65,.65,'8061BB');
 text(s,'Show the product.\nTell its story.',.62,1.32,8.65,1.67,43,C.white,true);
 text(s,'A narrated walkthrough of the My AITU / LMS bridge.',.65,3.48,10.7,.46,20,'D2C4EC');
 text(s,'2:10',.65,4.7,3.3,.95,57,'BFA4FF',true);text(s,'planned running time',.68,5.8,3.85,.3,15,'D2C4EC');
 const steps=[['01','Sign in'],['02','Explore'],['03','Explain'],['04','Look ahead']];
 steps.forEach(([n,title],i)=>{let x=5.05+i*1.91;circle(s,x,4.83,.52,'49316F');text(s,n,x+.105,4.99,.31,.17,11,C.white,true);text(s,title,x,5.64,1.8,.34,14,C.white,true);});
}
// 12 — Storyboard with unambiguous roles and time slots.
{
 const s=slide(12,'C1 / Storyboard','A clear role for every narrator.','Four scenes connect the working prototype to its purpose and next steps.');
 const rows=[['0:00–0:30','Login screen','Nurassyl','Explain how sign-in works.'],['0:30–1:10','Main pages and navigation','Salima','Walk through content and design decisions.'],['1:10–1:40','Statistics and Stage 1 survey','Azhar','Explain the project’s purpose.'],['1:40–2:10','Demo sketches','Azhar','Outline the project’s future.']];
 table(s,['TIME','ON SCREEN','NARRATOR','TALKING POINT'],rows,.6,2.2,12.13,[1.65,3.4,1.65,5.43],.77,15);
 chip(s,'TOTAL · 2 MIN 10 SEC',.65,6.42,2.3,C.lilac,C.purple);
}
// 13 — Existing video link, made usable in presentation mode.
{
 const s=slide(13,'C2 / The video','Open the project demonstration.');
 box(s,.6,1.96,8.12,4.78,C.deep);circle(s,3.9,2.72,1.44,C.purple);
 s.addShape(p.ShapeType.triangle,{x:4.4,y:3.17,w:.5,h:.52,rotate:90,fill:{color:C.white},line:{color:C.white,width:0},hyperlink:{url:'https://drive.google.com/drive/folders/1izH4jyb1Ooi-pvghCGhOfCXmk6A6rqKn?usp=sharing'}});
 text(s,'My AITU / LMS bridge',1.0,4.57,7.3,.48,28,C.white,true);
 text(s,'Team walkthrough · Google Drive folder',1.02,5.29,7.12,.35,17,'D7C9EE');
 linkButton(s,'OPEN VIDEO FOLDER','https://drive.google.com/drive/folders/1izH4jyb1Ooi-pvghCGhOfCXmk6A6rqKn?usp=sharing',1.03,6.0,3.17);
 qr(s,'video-qr.png',9.46,2.28,2.61);
 text(s,'Scan to open',9.09,5.28,3.5,.34,21,C.ink,true,{align:'center'});
 text(s,'Opens the project’s\nGoogle Drive folder.',9.1,5.91,3.5,.6,14,C.muted,false,{align:'center'});
}
// 14 — Honest production note: no invented recording or encoding metadata.
{
 const s=slide(14,'C3 / Production note','The plan is defined. Export details remain.');
 box(s,.6,1.99,8.0,4.78,C.white);
 text(s,'Production note',.88,2.29,7.43,.38,22,C.ink,true);
 const note='The storyboard plans a 2-minute 10-second walkthrough of the My AITU / LMS bridge, with narration from all three team members. It covers sign-in, key pages, the project’s purpose and future work. MP4 with H.264 video and AAC audio is the planned delivery format for broad device playback. The linked Drive folder is the hand-off location. Recording and editing tools, final resolution, frame rate, bitrate and file size were not supplied, so they cannot yet be reported as completed production settings. These values should be checked against the final exported video before submission.';
 text(s,note,.9,2.99,7.36,3.25,17,C.muted,false,{breakLine:false});
 box(s,8.94,1.99,3.79,4.78,C.lilac);
 chip(s,'FINAL FILE NOT INSPECTED',9.15,2.23,3.36,C.white,C.purple);
 text(s,'Confirm before\nsubmission',9.19,2.98,3.31,.91,26,C.ink,true);
 text(s,'Recording + editing tools\nResolution + frame rate\nVideo + audio bitrate\nFinal duration + file size',9.19,4.35,3.31,1.76,15.5,C.ink,false,{paraSpaceAfterPt:10});
}
// 15 — Integration concept diagram made with editable shapes.
{
 const s=slide(15,'Part D / Integration','','',true);
 text(s,'From media assets\nto a working bridge.',.65,1.25,11.8,1.6,42,C.white,true);
 text(s,'The multimedia layer supports the same project and prototype.',.68,3.26,11.5,.42,20,'D2C4EC');
 const xs=[.65,5.0,9.35];
 [['01','Sign in','Individual user session'],['02','Read LMS','Course and attendance data'],['03','Present clearly','A responsive student interface']].forEach(([n,title,desc],i)=>{box(s,xs[i],4.39,3.35,1.7,'3A2858');text(s,n,xs[i]+.2,4.62,.6,.28,13,'BFA4FF',true);text(s,title,xs[i]+.2,5.04,2.95,.38,24,C.white,true);text(s,desc,xs[i]+.2,5.61,2.95,.27,12,'D2C4EC');if(i<2)text(s,'→',xs[i]+3.65,5.02,.48,.4,25,'BFA4FF');});
}
// 16 — Runnable commands matched to the current README.
{
 const s=slide(16,'D1 / Updated prototype','Run the project from its repository.','Linux launch sequence from bridge-test/README.md.');
 const steps=[['01','Clone the project','git clone https://github.com/d30mantcoder/ICTProject'],['02','Create an environment','cd ICTProject  &&  python -m venv venv'],['03','Install dependencies and Chromium','venv/bin/python -m pip install -r bridge-test/requirements.txt\nvenv/bin/python -m playwright install chromium --only-shell'],['04','Launch the bridge','BRIDGE_HEADLESS=1 venv/bin/python bridge-test/app.py']];
 steps.forEach(([n,title,cmd],i)=>{let y=2.08+i*1.08;circle(s,.63,y,.4,C.lilac);text(s,n,.7,y+.12,.26,.16,9.5,C.purple,true);text(s,title,1.2,y,7.63,.28,17,C.ink,true);text(s,cmd,1.2,y+.42,7.65,.51,i===2?10.5:11.1,C.muted,false,{fontFace:'Courier New'});});
 qr(s,'repo-qr.png',9.64,2.42,2.45);
 linkButton(s,'OPEN REPOSITORY','https://github.com/d30mantcoder/ICTProject',9.15,5.37,3.58);
 text(s,'Local address\n127.0.0.1:1740',9.2,6.14,3.47,.51,14,C.muted,false,{align:'center'});
}
// 17 — Meaningful before / after, with limits kept visible.
{
 const s=slide(17,'D2 / Change log','Three changes that make the bridge useful.');
 table(s,['CHANGE','WHY IT WAS NEEDED','CURRENT BEHAVIOUR'],[
  ['Real LMS data','A prototype needs useful, current course information.','Reads the user’s LMS content.'],
  ['Interface redesign','Frequently used tasks were hard to reach.','Key actions are brought to the main page.'],
  ['Asynchronous sessions','The earlier flow could not support independent users.','Users have separate sessions; slow requests do not hold others.']
 ],.6,2.08,12.13,[2.7,4.35,5.08],1.08,16);
 chip(s,'SCALE LIMIT STILL OPEN',.65,6.67,2.6,C.amberBg,C.amber);
 text(s,'<3 seconds per request at 1,000 users has not been verified.',3.53,6.7,9.1,.24,12.5,C.muted);
}
// 18 — Three balanced cards, no split names.
{
 const s=slide(18,'D3 / Team contributions','One project. Three areas of ownership.');
 const people=[['SZ','Salima','Zimbekkyzy','C + D','Video editing'],['AS','Azhar','Saparzholova','A + D','Multimedia format comparison'],['NO','Nurassyl','Oralbekov','B + D','Media integration and optimisation']];
 people.forEach(([initial,first,last,parts,work],i)=>{let x=.6+i*4.11;box(s,x,2.07,3.91,4.55,C.white);circle(s,x+.26,2.38,.78,i===2?C.purple:C.lilac);text(s,initial,x+.38,2.62,.53,.24,17,i===2?C.white:C.purple,true,{align:'center'});text(s,first,x+.26,3.49,3.39,.5,29,C.ink,true);text(s,last,x+.26,4.08,3.39,.37,18,C.muted);chip(s,'PARTS '+parts,x+.26,4.77,1.66,C.lilac,C.purple);text(s,work,x+.26,5.51,3.39,.73,19,C.ink,true);});
}
// 19 — Closing connects the visual style back to the evidence.
{
 const s=slide(19,'Thank you','','',true);dots(s,11.6,.68,'8061BB');
 text(s,'Less weight.\nMore clarity.',.65,1.15,11.6,1.9,52,C.white,true);
 text(s,'Multimedia choices that support a better student experience.',.69,3.49,11.5,.44,20,'D2C4EC');
 [['73%','smaller preview'],['18','inline SVG icons'],['25','inventoried assets']].forEach(([value,label],i)=>{let x=.7+i*4.2;text(s,value,x,4.62,3.8,.89,52,i===0?'C2A7FF':C.white,true);text(s,label,x+.03,5.78,3.8,.37,18,'D2C4EC');});
}

fs.writeFileSync(path.join(__dirname,'layout.json'),JSON.stringify(layout,null,2));
p.writeFile({fileName:path.join(__dirname,'redesigned.pptx')});
