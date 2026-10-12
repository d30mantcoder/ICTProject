"""Create browser-viewable snapshots from the live MariaDB schema and demo rows.

Run from the project root with its virtualenv active. Generated HTML is an evidence
view of live SQL metadata/results, not a replacement database or static fixture.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import inspect, text

from backend.app.database import engine

OUT = Path("evidence")
OUT.mkdir(exist_ok=True)
inspector = inspect(engine)
with engine.connect() as db:
    database_name = db.execute(text("SELECT DATABASE()")).scalar_one()
    server_version = db.execute(text("SELECT VERSION()")).scalar_one()
    schema_rows = []
    for table in inspector.get_table_names():
        count = db.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one()
        cols = inspector.get_columns(table)
        pk = set(inspector.get_pk_constraint(table).get("constrained_columns") or [])
        fk_cols = {col for fk in inspector.get_foreign_keys(table) for col in (fk.get("constrained_columns") or [])}
        unique_constraints = [tuple(uq.get("column_names") or []) for uq in inspector.get_unique_constraints(table)]
        unique_cols = {cols[0] for cols in unique_constraints if len(cols) == 1}
        checks = inspector.get_check_constraints(table)
        fields = []
        for col in cols:
            markers = [m for m, yes in (("PK", col["name"] in pk), ("FK", col["name"] in fk_cols), ("UNIQUE", col["name"] in unique_cols)) if yes]
            nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
            fields.append(f"<li><code>{escape(col['name'])}</code> <span>{escape(str(col['type']))}</span> · {nullable} {' · '.join(markers)}</li>")
        relationships = [
            f"{', '.join(fk['constrained_columns'])} → {fk['referred_table']}.{', '.join(fk['referred_columns'])}"
            for fk in inspector.get_foreign_keys(table)
        ]
        details = "".join(f"<div class='rule'>FK: {escape(x)}</div>" for x in relationships)
        details += "".join(f"<div class='rule'>UNIQUE: ({escape(', '.join(cols))})</div>" for cols in unique_constraints if len(cols) > 1)
        details += "".join(f"<div class='rule'>CHECK: {escape(c['sqltext'])}</div>" for c in checks)
        schema_rows.append(
            f"<article><header><b>{escape(table)}</b><span>{count:,} rows · {len(cols)} columns</span></header>"
            f"<ul>{''.join(fields)}</ul>{details}</article>"
        )

    sample = db.execute(text("""SELECT s.username, s.first_name, s.last_name, g.name AS study_group,
        LEFT(s.password_hash, 7) AS bcrypt_prefix
        FROM students AS s JOIN groups AS g ON g.id=s.group_id ORDER BY s.id LIMIT 8""")).mappings().all()
    sample_rows = "".join(
        "<tr>" + "".join(f"<td>{escape(str(row[k]))}</td>" for k in ("username", "first_name", "last_name", "study_group", "bcrypt_prefix")) + "</tr>"
        for row in sample
    )

base = """<!doctype html><html lang='en'><meta charset='utf-8'><title>MariaDB evidence</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#17212b;font:15px/1.45 system-ui, sans-serif}
main{max-width:1180px;margin:32px auto;padding:0 24px}h1{font-size:27px;margin:0 0 6px}.meta{color:#526171;margin-bottom:20px}
.notice{background:#eaf3fb;border-left:4px solid #2475aa;padding:12px 16px;margin:18px 0 24px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}article{background:white;border:1px solid #d5dde5;border-radius:9px;padding:14px 16px;break-inside:avoid}
header{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid #e5e9ee;padding-bottom:8px}header span{color:#526171;font-size:13px}
ul{margin:10px 0;padding-left:20px}li{margin:3px 0}li span{color:#526171}code{font-size:13px;background:#f0f3f6;padding:1px 4px;border-radius:3px}.rule{font-size:12px;color:#43566a;margin:3px 0}
table{border-collapse:collapse;width:100%;background:#fff}th,td{text-align:left;padding:10px 12px;border:1px solid #d5dde5}th{background:#eef2f6}section{margin-top:18px}
@media(max-width:760px){.grid{grid-template-columns:1fr}main{margin:16px auto}}
</style><main>"""
footer = "</main></html>"
header = f"<h1>MariaDB · {escape(database_name)}</h1><div class='meta'>Live database metadata and query results · MariaDB {escape(str(server_version))} · local connection 127.0.0.1:3306</div>"
notice = "<div class='notice'>Generated directly from information_schema and SELECT queries against the running MariaDB instance. Student records shown are synthetic demo data.</div>"
(OUT / "database-schema.html").write_text(base + header + notice + "<div class='grid'>" + "".join(schema_rows) + "</div>" + footer)
rows_header = "".join(f"<th>{escape(k)}</th>" for k in ("username", "first_name", "last_name", "study_group", "bcrypt_prefix"))
query = "SELECT s.username, s.first_name, s.last_name, g.name AS study_group, LEFT(s.password_hash, 7) AS bcrypt_prefix FROM students AS s JOIN groups AS g ON g.id=s.group_id ORDER BY s.id LIMIT 8;"
(OUT / "database-test-data.html").write_text(
    base + header + notice + "<h2>Student test rows · password storage check</h2>"
    + f"<div class='meta'><code>{escape(query)}</code></div>"
    + "<section><table><thead><tr>" + rows_header + "</tr></thead><tbody>" + sample_rows + "</tbody></table></section>"
    + "<div class='notice'>The selected password_hash prefix uses bcrypt format ($2b$12$); the full hash is not shown in this evidence view.</div>" + footer
)
print(f"Wrote live MariaDB schema and test-row views to {OUT}/")
