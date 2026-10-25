const pptxgen=require('/tmp/presentation-tools/node_modules/pptxgenjs');
const fs=require('fs'),path=require('path');
const p=new pptxgen();p.defineLayout({name:'PIXEL',width:20,height:11.25});p.layout='PIXEL';
p.author='ICT presentation';p.title='Multimedia Technologies — 18 table variations';p.lang='en-GB';p.theme={headFontFace:'Arial',bodyFontFace:'Arial',lang:'en-GB'};
const D=__dirname,W=20,H=11.25;
const C={ink:'282043',muted:'716785',purple:'7044DA',deep:'20133E',line:'DED5F0',lilac:'EEE7FC',mint:'D8F5E8',pink:'FFE1EE',cream:'FFF7E8',white:'FFFFFF',cyan:'84E8ED'};
const rows=[['PNG','Lossless; supports transparency','Screenshots and graphics with crisp text or edges'],['JPEG','Lossy; compact for photographs','Photos where a smaller file matters more than perfect detail'],['WebP','Lossy or lossless; compact','Web images and the attendance preview in our prototype']];
const heads=['FORMAT','KEY TRAIT','BEST FIT'];
const names=['Чистая классика','Строки-карточки','Пастельные колонки','Три карточки','Акцент на WebP','Тонкие линии','Тёмная таблица','Пиксельное окно','Отдельные ячейки','Цветные вкладки','Таблица с пояснением','Крупная нумерация','Плотная: светлая','Плотная: по группам','Плотная: акцент на применении','Плотная: тёмная','Команда: карточки','Команда: таблица'];
const desc=['Контрастная шапка, свободные поля и спокойные строки.','Каждая строка отделена от соседних; форматы видны сразу.','Один формат — одна цветная колонка.','Свойства и применение собраны в трёх независимых карточках.','Выделена колонка формата, выбранного для проекта.','Лёгкая таблица без вертикальной сетки.','Светлый текст и бирюзовые детали на тёмной поверхности.','Таблица внутри окна в стиле исходного пиксельного фона.','Мягкие ячейки с промежутками вместо сплошной сетки.','Форматы вынесены в цветные вкладки слева.','Краткий вывод слева, компактное сравнение справа.','Крупные номера задают порядок чтения.','Все 10 форматов и 7 исходных полей на одном слайде.','Изображения, аудио и видео разделены внутри одной таблицы.','Колонка применения выделена; остальные поля сохранены.','Полная таблица с тёмным фоном и спокойной сеткой.','Три человека — три самостоятельные карточки.','Обычная таблица с хорошими отступами и выравниванием.'];
const metadata=[],layout=[];
function box(s,x,y,w,h,fill,rad=0,border=null,trans=0){s.addShape(rad?p.ShapeType.roundRect:p.ShapeType.rect,{x,y,w,h,rectRadius:rad, radius:rad,fill:{color:fill,transparency:trans},line:{color:border||fill,width:border?1:0,transparency:trans}});}
function tx(s,t,x,y,w,h,size=26,color=C.ink,bold=false,opts={}){s.addText(t,{x,y,w,h,fontFace:'Arial',fontSize:size,color,bold,margin:0,breakLine:false,paraSpaceAfterPt:0,valign:'mid',...opts});layout.push({slide:p._slides.length,t:typeof t==='string'?t:'[rich]',x,y,w,h,size});}
function line(s,x,y,w,color=C.line,weight=1){s.addShape(p.ShapeType.line,{x,y,w,h:0,line:{color,width:weight}});}
function pill(s,t,x,y,w,fill=C.lilac,col=C.purple,size=19){box(s,x,y,w,.5,fill,.22);tx(s,t,x+.12,y+.06,w-.24,.36,size,col,true,{align:'center'});}
function base(id,title='Part A — Multimedia formats',bg=2){const s=p.addSlide();s.addImage({path:path.join(D,`background-${bg}.png`),x:0,y:0,w:W,h:H});
 tx(s,`${String(id).padStart(2,'0')}  /  ${names[id-1]}`,.95,.34,17.6,.34,18,C.white,true);
 tx(s,title,.95,id>=17?1.38:.95,18.1,.69,42,C.white,true);
 if(id<=12)tx(s,'PNG  /  JPEG  /  WebP — same content, different table layouts',1,1.8,17,.38,20,'F1E9FF');
 box(s,.95,10.45,18.1,.47,C.deep,.15,null,15);tx(s,desc[id-1],1.18,10.52,16.4,.27,16,C.white);tx(s,String(id).padStart(2,'0'),17.9,10.52,.85,.27,16,C.white,true,{align:'right'});
 metadata.push({id,name:names[id-1],description:desc[id-1],group:id<=12?'Слайд 2':id<=16?'10 форматов':'Команда',page:p._slides.length});
 s.addNotes(`Вариант ${id}: ${names[id-1]}. ${desc[id-1]}\nOriginal pixel-art background preserved. Editable table/text/shape objects. Visual references: https://www.canva.com/templates/s/table/ ; https://www.canva.com/graphs/tables/ . Independent layout inspired by these examples, not a copied Canva template.\n${id<=12?rows.map(r=>r.join(' | ')).join('\n'):''}`);return s;}
function nt(s,hdr,data,x,y,width,colW,{font=25,rh=1.48,hh=.8,header=C.purple,body=C.white,alternate=C.lilac,dark=false,highlightCol=-1,highlightRow=-1,colColors=null,pad=[12,16,12,16]}={}){
 const all=[hdr,...data].map((r,i)=>r.map((v,j)=>{let fill=i===0?header:(colColors?colColors[j]:(i%2?body:alternate));let color=i===0?C.white:(dark?'F0EAFB':C.ink);if(j===highlightCol){fill=i===0?'5930AD':C.purple;color=C.white;}if(i===highlightRow){fill=dark?'423065':'E0D3F7';}
 return {text:String(v),options:{fill,color,bold:i===0||j===0,margin:pad,fontSize:i===0&&font<21?17:font}}}));
 s.addTable(all,{x,y,w:width,h:hh+data.length*rh,colW,rowH:[hh,...data.map(()=>rh)],fontFace:'Arial',fontSize:font,color:dark?C.white:C.ink,border:{type:'solid',pt:0.6,color:dark?'574574':C.white},margin:12,valign:'middle',autoPage:false,paraSpaceAfterPt:0});
}
function useNote(s,x=1.3,y=8.55,w=17.4,color=C.white){box(s,x-.16,y-.1,w+.32,.6,C.deep,.14,null,10);tx(s,'In our prototype: WebP preview + inline SVG interface icons.',x,y,w,.38,20,color,true);}
// Overview — deliberately a selection deck, not a replacement presentation.
{
 const s=p.addSlide();s.addImage({path:path.join(D,'background-2.png'),x:0,y:0,w:W,h:H});
 box(s,.9,.7,18.2,8.9,C.deep,.25,null,3);
 tx(s,'ТАБЛИЦЫ / ВАРИАНТЫ',1.6,1.26,15,.4,19,'D7C5FF',true);
 tx(s,'18 способов оформить\nтвои таблицы',1.55,2.05,16.8,1.7,49,C.white,true);
 tx(s,'Прежние пиксельные фоны. Разные композиции,\nотступы, заголовки и акценты.',1.62,4.13,16,.95,27,'E5DCF9');
 const groups=[['01–12','Второй слайд','Три формата, двенадцать вариантов'],['13–16','10 форматов','Четыре оформления плотной таблицы'],['17–18','Команда','Два варианта распределения задач']];
 groups.forEach(([n,t,d],i)=>{const x=1.6+i*5.65;box(s,x,5.85,5.25,2.65,i===0?'7044DA':'35244F',.18);tx(s,n,x+.3,6.13,4.65,.54,32,C.white,true);tx(s,t,x+.3,6.91,4.65,.4,23,C.white,true);tx(s,d,x+.3,7.54,4.65,.52,18,'E7DEF5');});
 tx(s,'Открой варианты и выбери номера, которые нравятся.',1.62,9.01,16.7,.32,20,'E5DCF9');
}
// 01 Classic.
{
 const s=base(1);box(s,.95,2.55,18.1,5.82,C.white,.2);nt(s,heads,rows,1.23,2.86,17.54,[2.6,6.2,8.74],{font:26,rh:1.42,hh:.77,alternate:'F3EFFB'});useNote(s);
}
// 02 Floating row cards.
{
 const s=base(2);['FORMAT','KEY TRAIT','BEST FIT'].forEach((t,i)=>tx(s,t,[1.4,4.6,10.65][i],2.56,[2.6,5.6,7.6][i],.36,18,C.white,true));
 rows.forEach((r,i)=>{let y=3.15+i*1.65;box(s,.95,y,18.1,1.4,C.white,.22);pill(s,r[0],1.4,y+.43,2.3,['EEE7FC','FFE1EE','D8F5E8'][i],C.ink,25);tx(s,r[1],4.6,y+.18,5.5,1.04,26);tx(s,r[2],10.65,y+.18,7.7,1.04,25);});useNote(s);
}
// 03 Pastel columns.
{
 const s=base(3);box(s,.95,2.55,18.1,5.85,C.white,.2);
 const trans=[['Key trait',...rows.map(r=>r[1])],['Best fit',...rows.map(r=>r[2])]];
 nt(s,['COMPARE','PNG','JPEG','WebP'],trans,1.25,2.88,17.5,[2.5,5,5,5],{font:26,rh:2.05,hh:.8,colColors:['F7F4FC',C.lilac,C.pink,C.mint]});useNote(s);
}
// 04 Three independent cards.
{
 const s=base(4);rows.forEach((r,i)=>{let x=.95+i*6.15;box(s,x,2.68,5.8,5.75,C.white,.24);box(s,x,2.68,5.8,1.28,[C.lilac,C.pink,C.mint][i],.24);tx(s,r[0],x+.37,3.02,5.05,.6,36,C.ink,true);tx(s,'KEY TRAIT',x+.37,4.34,4.9,.3,17,C.muted,true);tx(s,r[1],x+.37,4.91,4.98,1.05,27,C.ink,true);line(s,x+.37,6.18,4.98);tx(s,'BEST FIT',x+.37,6.52,4.98,.3,17,C.muted,true);tx(s,r[2],x+.37,7.07,4.98,1.02,24);});useNote(s,1.3,8.72);
}
// 05 Spotlight column.
{
 const s=base(5);box(s,.95,2.56,18.1,5.86,C.white,.2);nt(s,['COMPARE','PNG','JPEG','WebP'],[['Key trait',...rows.map(r=>r[1])],['Best fit',...rows.map(r=>r[2])]],1.25,2.88,17.5,[2.5,5,5,5],{font:25,rh:2.05,hh:.8,header:'3F315B',body:'F8F6FC',alternate:'F8F6FC',highlightCol:3});useNote(s);
}
// 06 Editorial rules.
{
 const s=base(6);box(s,.95,2.56,18.1,5.86,'FFFCF7',.12);const xs=[1.45,4.67,10.72],ws=[2.7,5.45,7.6];heads.forEach((t,j)=>tx(s,t,xs[j],2.98,ws[j],.4,18,C.muted,true));line(s,1.45,3.62,17.1,C.ink,1.7);rows.forEach((r,i)=>{let y=3.82+i*1.32;r.forEach((t,j)=>tx(s,t,xs[j],y,ws[j],.97,j===0?32:25,j===0?C.purple:C.ink,j===0));if(i<2)line(s,1.45,y+1.16,17.1,C.line,1);});useNote(s);
}
// 07 Dark contrast.
{
 const s=base(7);box(s,.95,2.56,18.1,5.86,C.deep,.25,null,2);nt(s,heads,rows,1.25,2.88,17.5,[2.6,6.15,8.75],{font:26,rh:1.42,hh:.8,header:'543185',body:'30204A',alternate:'392756',dark:true});line(s,1.25,3.69,17.5,C.cyan,2.2);useNote(s);
}
// 08 Pixel UI window.
{
 const s=base(8);box(s,.99,2.63,18.06,5.91,'190D35');box(s,.91,2.55,18.06,5.91,'C9B7F1');box(s,1.02,2.66,17.84,5.69,'F6F0FF');box(s,1.02,2.66,17.84,.65,'51328C');tx(s,'MEDIA_FORMATS',1.35,2.82,14,.3,19,C.white,true,{fontFace:'Courier New'});for(let i=0;i<3;i++)box(s,17.39+i*.43,2.85,.24,.24,['93E8ED','FFD5E6','EED9A4'][i]);nt(s,heads,rows,1.3,3.57,17.2,[2.55,6.1,8.55],{font:25,rh:1.25,hh:.63,header:'7044DA',body:'EDE3FF',alternate:'F8F5FE'});useNote(s,1.3,8.77);
}
// 09 Separate cells.
{
 const s=base(9);const xs=[.95,4.1,10.45],ws=[2.9,6.1,8.6];heads.forEach((t,j)=>{box(s,xs[j],2.65,ws[j],.78,C.purple,.16);tx(s,t,xs[j]+.22,2.84,ws[j]-.44,.35,20,C.white,true);});rows.forEach((r,i)=>{let y=3.65+i*1.51;r.forEach((t,j)=>{box(s,xs[j],y,ws[j],1.29,j===0?['E3D4FF','FFDEED','D6F4E5'][i]:'FFFFFF',.16);tx(s,t,xs[j]+.25,y+.18,ws[j]-.5,.91,j===0?30:25,C.ink,j===0);});});useNote(s);
}
// 10 Colored tabs.
{
 const s=base(10);const colors=['6936C8','B84678','177D6B'];rows.forEach((r,i)=>{let y=2.7+i*1.85;box(s,.95,y,18.1,1.58,'FFFFFF',.22);box(s,.95,y,3.1,1.58,colors[i],.22);tx(s,r[0],1.28,y+.47,2.43,.6,34,C.white,true);tx(s,'KEY TRAIT',4.49,y+.22,5.2,.28,16,C.muted,true);tx(s,r[1],4.49,y+.69,5.55,.65,25);tx(s,'BEST FIT',10.67,y+.22,7.9,.28,16,C.muted,true);tx(s,r[2],10.67,y+.69,7.83,.65,24);});useNote(s,1.3,8.65);
}
// 11 Split composition.
{
 const s=base(11);box(s,.95,2.6,5.05,5.86,C.deep,.22);tx(s,'Different files.\nDifferent jobs.',1.35,3.09,4.25,1.45,34,C.white,true);tx(s,'Choose a format\nfor the content\nand its use.',1.35,5.03,4.25,1.65,27,'E8DEF8');pill(s,'WEBP IN OUR APP',1.35,7.31,4.05,'7051B3',C.white,18);box(s,6.25,2.6,12.8,5.86,C.white,.22);nt(s,heads,rows,6.5,2.88,12.3,[1.85,4.6,5.85],{font:23,rh:1.46,hh:.8,header:C.purple,alternate:'F2EDF9'});useNote(s,1.3,8.7);
}
// 12 Large numbering.
{
 const s=base(12);box(s,.95,2.6,18.1,5.86,'FFFFFF',.2);rows.forEach((r,i)=>{let y=2.94+i*1.69;tx(s,'0'+(i+1),1.35,y+.2,1.38,.74,42,'BAA5DC',true);tx(s,r[0],3.0,y+.28,2.48,.6,32,C.ink,true);tx(s,r[1],6.0,y+.15,5.15,1.03,25,C.ink,true);tx(s,r[2],11.78,y+.15,6.63,1.03,25);if(i<2)line(s,3.0,y+1.43,15.45);});useNote(s);
}
const dense=[['PNG','Image','Lossless','Alpha; APNG','Large photos','Broad','UI evidence'],['JPEG','Image','Lossy','Neither','Small photos','Broad','Photos'],['WebP','Image','Both modes','Alpha + motion','Compact','Modern','App preview'],['SVG','Image','Vector / text','Alpha + motion','Tiny icons','Broad','UI icons'],['MP3','Audio','Lossy','N/A','Small','Broad','Speech / music'],['AAC (M4A)','Audio','Lossy','N/A','Small','Broad*','Narration'],['WAV (PCM)','Audio','Uncompressed','N/A','Large','Broad*','Editing master'],['MP4 H.264','Video','Usually lossy','Motion; no alpha','Bitrate-based','Broad*','Demo delivery'],['WebM VP9','Video','Usually lossy','Motion; alpha*','Bitrate-based','Modern*','Web playback'],['MOV H.264','Video','Usually lossy','Motion; no alpha','Bitrate-based','Limited web','Editing / transfer']];
const dh=['FORMAT','TYPE','COMPRESSION','ALPHA / MOTION','TYPICAL SIZE','SUPPORT','PROJECT USE'];
function denseNote(s,dark=false){box(s,1.1,8.91,17.8,.94,C.deep,.13,null,8);tx(s,'Container = package. Codec = how the media is encoded.',1.3,9.01,17.4,.31,21,C.white,true);tx(s,'*Support varies by codec, OS and device. File size depends on content and encoding.',1.3,9.47,17.4,.28,17,C.white);}
// 13 dense classic.
{
 const s=base(13,'A1. Format comparison',3);box(s,.95,2.1,18.1,6.62,C.white,.18);nt(s,dh,dense,1.2,2.35,17.6,[2.25,1.3,2.5,2.9,2.5,1.75,4.4],{font:19.5,pad:[4,8,4,8],rh:.535,hh:.72,alternate:'F3EFF9'});denseNote(s);
}
// 14 grouped blocks: same seven fields, all rows retained.
{
 const s=base(14,'A1. Format comparison',3);box(s,.95,2.1,18.1,6.62,C.white,.18);const xs=[1.22,3.47,4.77,7.27,10.17,12.67,14.42],ws=[2.25,1.3,2.5,2.9,2.5,1.75,4.35];dh.forEach((t,j)=>tx(s,t,xs[j]+.08,2.3,ws[j]-.16,.44,16,C.purple,true));let y=2.98;
 dense.forEach((r,i)=>{if([0,4,7].includes(i)){box(s,1.22,y-.065,17.55,.07,['0','4','7'].indexOf(String(i))===0?'BAA3E3':i===4?'72C9BC':'E6A3C0');y+=.12;}r.forEach((v,j)=>tx(s,v,xs[j]+.08,y,ws[j]-.16,.4,19,C.ink,j===0));if(i<9)line(s,1.22,y+.43,17.55,'ECE5F5',.6);y+=.49;});denseNote(s);
}
// 15 application emphasis.
{
 const s=base(15,'A1. Format comparison',3);box(s,.95,2.1,18.1,6.62,C.white,.18);nt(s,dh,dense,1.2,2.35,17.6,[2.25,1.3,2.5,2.9,2.5,1.75,4.4],{font:19.5,pad:[4,8,4,8],rh:.535,hh:.72,header:'443453',alternate:'F4F0FA',highlightCol:6});denseNote(s);
}
// 16 dark data.
{
 const s=base(16,'A1. Format comparison',3);box(s,.95,2.1,18.1,6.62,C.deep,.18);nt(s,dh,dense,1.2,2.35,17.6,[2.25,1.3,2.5,2.9,2.5,1.75,4.4],{font:19.5,pad:[4,8,4,8],rh:.535,hh:.72,header:'523477',body:'2E2046',alternate:'382750',dark:true,highlightRow:3});denseNote(s);
}
const team=[['Salima','C, D','Editing the video'],['Azhar','A, D','Comparing formats'],['Nurassyl','B, D','Multimedia integration']];
// 17 team cards on same scene.
{
 const s=base(17,'D3. Team contributions',18);team.forEach((r,i)=>{const x=.95+i*6.15;box(s,x,2.73,5.8,4.85,C.white,.23);pill(s,r[1],x+.4,3.12,1.45,[C.lilac,C.pink,C.mint][i]);tx(s,r[0],x+.4,4.01,5,.65,34,C.ink,true);line(s,x+.4,5.05,5);tx(s,'CONTRIBUTION',x+.4,5.4,5,.3,17,C.muted,true);tx(s,r[2],x+.4,6.03,5,.95,27);});
}
// 18 team matrix.
{
 const s=base(18,'D3. Team contributions',18);box(s,.95,2.73,18.1,4.88,C.white,.23);nt(s,['MEMBER','PARTS','CONTRIBUTION'],team,1.25,3.03,17.5,[4.5,2.5,10.5],{font:28,rh:1.07,hh:.84,alternate:'F3EFF9'});
}
fs.writeFileSync(path.join(D,'manifest.json'),JSON.stringify(metadata,null,2));fs.writeFileSync(path.join(D,'layout.json'),JSON.stringify(layout,null,2));
p.writeFile({fileName:path.join(D,'Table variations.pptx')});
