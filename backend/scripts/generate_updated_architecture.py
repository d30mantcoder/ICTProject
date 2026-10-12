"""Create the midterm-aligned and current Study LMS architecture diagram."""
from pathlib import Path
from xml.sax.saxutils import escape

out = Path('evidence')
out.mkdir(exist_ok=True)

svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1840" viewBox="0 0 1920 1840">
<defs>
 <marker id="arrowBlue" markerWidth="14" markerHeight="12" refX="12" refY="6" orient="auto"><path d="M0 0L13 6L0 12Z" fill="#32658a"/></marker>
 <marker id="arrowGreen" markerWidth="14" markerHeight="12" refX="12" refY="6" orient="auto"><path d="M0 0L13 6L0 12Z" fill="#287a58"/></marker>
 <marker id="arrowAmber" markerWidth="14" markerHeight="12" refX="12" refY="6" orient="auto"><path d="M0 0L13 6L0 12Z" fill="#a56716"/></marker>
</defs>
<style>
 text{font-family:Arial,Helvetica,sans-serif;fill:#1d2d3a}.title{font-size:43px;font-weight:700}.subtitle{font-size:21px;fill:#526578}.section{font-size:30px;font-weight:700}.sectionNote{font-size:19px;fill:#526578}.card{fill:#fff;stroke:#87a0b3;stroke-width:2}.blueHead{fill:#eaf3f9;stroke:#5b86a3;stroke-width:2}.greenHead{fill:#eaf5ef;stroke:#5d9275;stroke-width:2}.amberHead{fill:#fff6e8;stroke:#c49a5d;stroke-width:2}.cardTitle{font-size:23px;font-weight:700}.body{font-size:18px}.small{font-size:16px;fill:#536778}.label{font-size:16px;font-weight:700;fill:#315b79}.labelGreen{font-size:16px;font-weight:700;fill:#287a58}.labelAmber{font-size:16px;font-weight:700;fill:#925d17}.flowBlue{fill:none;stroke:#32658a;stroke-width:4;marker-end:url(#arrowBlue)}.flowGreen{fill:none;stroke:#287a58;stroke-width:4;marker-end:url(#arrowGreen)}.flowAmber{fill:none;stroke:#a56716;stroke-width:3;stroke-dasharray:10 8;marker-end:url(#arrowAmber)}.panelBlue{fill:#f5f9fc;stroke:#a5bac9;stroke-width:2}.panelGreen{fill:#f4faf6;stroke:#9bbca9;stroke-width:2}.foot{font-size:17px;fill:#40586a}
</style>
<rect width="100%" height="100%" fill="#f4f7f9"/>
<text x="65" y="72" class="title">Study LMS · Updated Architecture</text>
<text x="66" y="111" class="subtitle">Midterm proposal reconciled with the current database-backed educational prototype</text>

<!-- Stage 1 proposal -->
<rect x="55" y="150" width="1810" height="500" rx="20" class="panelBlue"/>
<text x="88" y="205" class="section">A · Midterm proposal (Project Stage 1, Part C)</text>
<text x="89" y="237" class="sectionNote">Planned live integration: fetch academic information from existing university platforms on demand.</text>
<rect x="85" y="280" width="300" height="190" rx="14" class="blueHead"/>
<text x="110" y="323" class="cardTitle">Student browser</text>
<text x="110" y="359" class="body">Mobile-first Study LMS UI</text>
<text x="110" y="390" class="body">Microsoft university SSO</text>
<text x="110" y="433" class="small">Request course / quiz data</text>
<path d="M385 375H445" class="flowBlue"/>
<text x="391" y="348" class="label">HTTPS</text>
<rect x="455" y="280" width="300" height="190" rx="14" class="card"/>
<text x="480" y="323" class="cardTitle">Secure network</text>
<text x="480" y="359" class="body">Encrypted client traffic</text>
<text x="480" y="390" class="body">Request and response path</text>
<text x="480" y="433" class="small">Data returned to browser UI</text>
<path d="M755 375H815" class="flowBlue"/>
<text x="756" y="348" class="label">request</text>
<rect x="825" y="280" width="300" height="190" rx="14" class="blueHead"/>
<text x="850" y="323" class="cardTitle">Server / cloud</text>
<text x="850" y="359" class="body">Python · FastAPI · Uvicorn</text>
<text x="850" y="390" class="body">Nginx reverse proxy</text>
<text x="850" y="433" class="small">ps.kz in Kazakhstan proposed</text>
<path d="M1125 375H1185" class="flowBlue"/>
<text x="1129" y="348" class="label">fetch</text>
<rect x="1195" y="280" width="300" height="190" rx="14" class="card"/>
<text x="1220" y="323" class="cardTitle">LMS connector</text>
<text x="1220" y="359" class="body">Official LMS API preferred</text>
<text x="1220" y="390" class="body">Playwright / BeautifulSoup</text>
<text x="1220" y="433" class="small">Fallback if no API is available</text>
<path d="M1495 375H1555" class="flowBlue"/>
<text x="1497" y="348" class="label">read</text>
<rect x="1565" y="280" width="270" height="190" rx="14" class="blueHead"/>
<text x="1590" y="323" class="cardTitle">Existing platforms</text>
<text x="1590" y="359" class="body">MyDU · LMS · Learn</text>
<text x="1590" y="390" class="body">University-owned sources</text>
<text x="1590" y="433" class="small">Remain source of truth</text>
<rect x="85" y="505" width="1750" height="105" rx="12" class="amberHead"/>
<text x="112" y="548" class="cardTitle">Stage 1 storage decision</text>
<text x="112" y="581" class="body">No persistent project database was planned: fetched user data would exist transiently in the server session and university LMS.</text>
<text x="112" y="601" class="small">Kazakhstan hosting and HTTPS/TLS were requirements for deployment, not claims about the current local prototype.</text>

<!-- Current prototype -->
<rect x="55" y="690" width="1810" height="1015" rx="20" class="panelGreen"/>
<text x="88" y="747" class="section">B · Current prototype (implemented for the database assignment)</text>
<text x="89" y="779" class="sectionNote">The prototype reads and writes local synthetic demo data; it does not yet connect to MyDU, LMS or Learn.</text>

<rect x="85" y="835" width="300" height="345" rx="14" class="greenHead"/>
<text x="110" y="880" class="cardTitle">People and actions</text>
<text x="110" y="922" class="body">Student</text>
<text x="135" y="951" class="small">Reads profile, preferences,</text>
<text x="135" y="976" class="small">courses and schedule</text>
<text x="110" y="1019" class="body">Teacher</text>
<text x="135" y="1048" class="small">Reads assigned rosters;</text>
<text x="135" y="1073" class="small">updates grades / attendance</text>
<text x="110" y="1116" class="body">Administrator</text>
<text x="135" y="1145" class="small">Manages staff and assignments</text>

<path d="M385 1000H445" class="flowGreen"/>
<text x="390" y="970" class="labelGreen">UI</text>
<rect x="455" y="875" width="300" height="250" rx="14" class="greenHead"/>
<text x="480" y="920" class="cardTitle">Frontend in browser</text>
<text x="480" y="961" class="body">index.html · /app</text>
<text x="480" y="997" class="body">Role-based interface</text>
<text x="480" y="1040" class="small">Served by FastAPI</text>
<text x="480" y="1070" class="small">Session JWT for API calls</text>
<path d="M755 1000H815" class="flowGreen"/>
<text x="757" y="970" class="labelGreen">JWT</text>
<rect x="825" y="835" width="430" height="345" rx="14" class="greenHead"/>
<text x="850" y="880" class="cardTitle">FastAPI + Uvicorn</text>
<text x="850" y="922" class="body">0.0.0.0:1734 · access via Tailscale</text>
<text x="850" y="960" class="body">JWT role checks · request validation</text>
<text x="850" y="1004" class="body">Student / teacher / admin endpoints</text>
<text x="850" y="1048" class="small">SQLAlchemy engine reads DATABASE_URL</text>
<text x="850" y="1078" class="small">PyMySQL driver · ORM maps 10 tables</text>
<text x="850" y="1130" class="small">User data shown here is synthetic</text>
<path d="M1255 1000H1315" class="flowGreen"/>
<text x="1254" y="970" class="labelGreen">SQL</text>
<rect x="1325" y="835" width="510" height="490" rx="14" class="greenHead"/>
<text x="1355" y="880" class="cardTitle">MariaDB · database: study_lms</text>
<text x="1355" y="922" class="body">MariaDB 11.8 · 127.0.0.1:3306</text>
<text x="1355" y="958" class="small">FastAPI connects locally using the DB account</text>
<text x="1355" y="984" class="small">in DATABASE_URL (.env); DB port is not remote.</text>
<text x="1355" y="1031" class="body">10 related tables with PK / FK constraints</text>
<text x="1355" y="1065" class="small">students · groups · preferences · instructors</text>
<text x="1355" y="1092" class="small">staff_accounts · courses · enrollments · rooms</text>
<text x="1355" y="1119" class="small">schedule · attendance_records</text>
<text x="1355" y="1164" class="body">Seed data: 100 students + staff / courses</text>
<text x="1355" y="1198" class="small">Synthetic records only; no live LMS fetching</text>

<rect x="1325" y="1370" width="510" height="190" rx="14" class="card"/>
<text x="1355" y="1414" class="cardTitle">Database administration GUI</text>
<text x="1355" y="1452" class="body">phpMyAdmin · HTTP port 5000</text>
<text x="1355" y="1484" class="small">Local network and Tailscale access</text>
<text x="1355" y="1513" class="small">GUI connects to MariaDB on this host;</text>
<text x="1355" y="1542" class="small">remote clients do not connect to port 3306.</text>
<path d="M1580 1370V1328" class="flowGreen"/>
<text x="1600" y="1353" class="labelGreen">local DB connection</text>

<rect x="85" y="1245" width="1170" height="315" rx="14" class="card"/>
<text x="115" y="1292" class="cardTitle">How application data is integrated</text>
<text x="115" y="1336" class="body">1. The frontend sends a role-authenticated request to the FastAPI endpoint.</text>
<text x="115" y="1376" class="body">2. FastAPI validates the JWT / role and opens a SQLAlchemy session.</text>
<text x="115" y="1416" class="body">3. SQLAlchemy uses PyMySQL and the local DATABASE_URL to query MariaDB.</text>
<text x="115" y="1456" class="body">4. ORM models link students, groups, courses, staff, schedule and attendance.</text>
<text x="115" y="1508" class="small">Current store: MariaDB database name `study_lms`; password values are bcrypt hashes.</text>
<text x="115" y="1537" class="small">In a future LMS connector, fetched records must follow an agreed sync / retention design.</text>

<rect x="55" y="1730" width="1810" height="75" rx="12" class="amberHead"/>
<text x="82" y="1777" class="foot">Status: MariaDB is the local coursework prototype store. Stage 1's live LMS fetch, Microsoft SSO, ps.kz hosting and production HTTPS are not implemented.</text>
<text x="65" y="1828" class="small">Sources: supplied Project Stage 1 (Midterm), Part C1/C2/C4; current backend/app models.py, database.py, config.py and API routes. Current environment checked 12 Oct 2026.</text>
</svg>'''

(out / 'updated-architecture.svg').write_text(svg, encoding='utf-8')
print('Wrote evidence/updated-architecture.svg')
