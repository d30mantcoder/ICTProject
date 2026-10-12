"""Generate concise SVG diagrams for the actual Study LMS schema and deployment."""
from pathlib import Path
from xml.sax.saxutils import escape

OUT=Path('evidence'); OUT.mkdir(exist_ok=True)
entities=[
('groups','id PK · name UNIQUE · year'),
('students','id PK · username UNIQUE · names · group_id FK · bcrypt hash · active'),
('preferences','id PK · student_id FK UNIQUE · language · theme · notifications'),
('instructors','id PK · names · email UNIQUE'),
('courses','id PK · code UNIQUE · title · instructor_id FK'),
('enrollments','id PK · student_id/course_id FKs · progress · grade · UNIQUE pair'),
('rooms','id PK · name UNIQUE · building'),
('schedule','id PK · course/group/room FKs · weekday · start/end · date'),
('staff_accounts','id PK · username UNIQUE · bcrypt hash · role CHECK · instructor_id FK UNIQUE nullable'),
('attendance_records','id PK · schedule/student/staff FKs · status CHECK · marked_at'),
]
parts=[]
for i,(name,fields) in enumerate(entities):
    x=45+(i%2)*755; y=105+(i//2)*112; w=710; h=88
    parts.append(f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="card"/><rect x="{x}" y="{y}" width="{w}" height="34" rx="8" class="head"/><text x="{x+16}" y="{y+25}" class="title">{escape(name)}</text><text x="{x+16}" y="{y+61}" class="field">{escape(fields)}</text></g>')
relations=[
'groups 1:N students','students 1:0..1 preferences','students N:M courses through enrollments',
'instructors 1:N courses','courses 1:N schedule','groups 1:N schedule','rooms 1:N schedule',
'instructors 1:0..1 teacher staff_account; admins have no instructor link',
'students 1:N attendance_records','schedule 1:N attendance_records',
'staff_accounts 1:N attendance_records (marked_by_staff_id)']
rel=''.join(f'<text x="{50+(i//6)*755}" y="{724+(i%6)*24}" class="rel">{escape(r)}</text>' for i,r in enumerate(relations))
erd='''<svg xmlns="http://www.w3.org/2000/svg" width="1510" height="900" viewBox="0 0 1510 900"><style>text{font-family:Arial,sans-serif;fill:#192d3c}.title{font-size:19px;font-weight:bold;fill:white}.field{font-size:16px}.card{fill:white;stroke:#66849c;stroke-width:1.5}.head{fill:#275f85}.rel{font-size:15px;font-weight:bold;fill:#244e6b}</style><rect width="100%" height="100%" fill="#f5f7f9"/><text x="45" y="48" font-size="28" font-weight="bold">Study LMS · Entity relationship diagram</text><text x="45" y="77" font-size="15" fill="#526171">PK primary key · FK foreign key · UNIQUE unique constraint · CHECK domain validation</text>'''+''.join(parts)+'''<text x="45" y="690" font-size="20" font-weight="bold">Relationships and cardinality</text>'''+rel+'''<text x="45" y="884" font-size="14" fill="#526171">Many-to-many relationships use linking tables; attendance retains the staff author of each status.</text></svg>'''
(OUT/'erd.svg').write_text(erd)
architecture='''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="1280" viewBox="0 0 1100 1280"><defs><marker id="arr" markerWidth="14" markerHeight="12" refX="12" refY="6" orient="auto"><path d="M0 0L13 6L0 12Z" fill="#315d78"/></marker></defs><style>text{font-family:Arial,sans-serif;fill:#1d2d3a}.title{font-size:34px;font-weight:bold}.box{fill:white;stroke:#52758e;stroke-width:2}.inner{fill:#f5f9fc;stroke:#7b9caf;stroke-width:2}.boxhead{font-size:27px;font-weight:bold}.desc{font-size:22px}.small{font-size:19px;fill:#36546a}.edge{fill:none;stroke:#315d78;stroke-width:4;marker-end:url(#arr)}.boundary{fill:#f4f8fb;fill-opacity:.55;stroke:#557e9b;stroke-width:2;stroke-dasharray:10 8}</style><rect width="100%" height="100%" fill="#f5f7f9"/><text x="55" y="58" class="title">Study LMS · architecture and access controls</text><rect x="75" y="300" width="950" height="900" rx="20" class="boundary"/><text x="110" y="345" class="boxhead">Project host · local machine</text><rect x="200" y="95" width="700" height="155" rx="14" class="box"/><text x="240" y="140" class="boxhead">Student · teacher · administrator</text><text x="240" y="180" class="desc">Browser interface at /app · bearer JWT</text><text x="240" y="220" class="small">Tailnet 100.116.195.35 · API port 1734 via tailscale0 only</text><path d="M550 250V390" class="edge"/><text x="585" y="300" class="small">Tailscale / WireGuard</text><text x="585" y="330" class="small">encrypted network tunnel</text><rect x="170" y="395" width="760" height="225" rx="14" class="inner"/><text x="215" y="445" class="boxhead">FastAPI + Uvicorn · 0.0.0.0:1734</text><text x="215" y="490" class="desc">Role checks · Pydantic input validation</text><text x="215" y="530" class="desc">SQLAlchemy · least-privilege database account</text><text x="215" y="575" class="small">HTTP + JWT; application-layer HTTPS is not configured</text><path d="M550 620V700" class="edge"/><text x="585" y="665" class="small">SQLAlchemy · local TCP</text><rect x="170" y="705" width="760" height="215" rx="14" class="inner"/><text x="215" y="755" class="boxhead">MariaDB · study_lms · 127.0.0.1:3306</text><text x="215" y="800" class="desc">10 tables · foreign keys · CHECK constraints</text><text x="215" y="840" class="desc">Dedicated application account · synthetic records</text><text x="215" y="885" class="small">Loopback only; inaccessible directly over LAN or Tailscale</text><path d="M550 920V985" class="edge"/><text x="585" y="962" class="small">daily backup script (manual today)</text><rect x="170" y="990" width="760" height="145" rx="14" class="box"/><text x="215" y="1045" class="boxhead">Compressed SQL backups</text><text x="215" y="1090" class="desc">14-day local retention · no off-machine copy</text><text x="75" y="1235" class="small">Production gaps: HTTPS · Kazakhstan hosting · real LMS/SSO · scheduled backups · audit logging · MFA</text></svg>'''
(OUT/'architecture.svg').write_text(architecture)
print('Wrote evidence/erd.svg and evidence/architecture.svg')
