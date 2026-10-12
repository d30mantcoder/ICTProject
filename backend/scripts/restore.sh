#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 || ! -f "$1" ]]; then echo "Usage: $0 backups/file.sql.gz" >&2; exit 2; fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
if [[ -z "${DATABASE_URL:-}" && -f "$ROOT/.env" ]]; then
  DATABASE_URL="$("$ROOT/.venv/bin/python" -c 'from dotenv import dotenv_values; print(dotenv_values(".env").get("DATABASE_URL", ""))')"
fi
DATABASE_URL="${DATABASE_URL:-mysql+pymysql://root:@127.0.0.1:3306/study_lms?charset=utf8mb4}"
DB_PART="${DATABASE_URL#*://}"; DB_PART="${DB_PART#*/}"; DB_NAME="${DB_PART%%\?*}"
DB_AUTH="${DATABASE_URL#*://}"; DB_AUTH="${DB_AUTH%%@*}"
DB_USER="${DB_AUTH%%:*}"; DB_PASS="${DB_AUTH#*:}"
echo "Restoring into '$DB_NAME'; current database contents will be replaced."
if [[ -n "$DB_PASS" ]]; then gzip -dc "$1" | MYSQL_PWD="$DB_PASS" mariadb -h 127.0.0.1 -u "$DB_USER" "$DB_NAME"
else gzip -dc "$1" | mariadb -h 127.0.0.1 -u "$DB_USER" "$DB_NAME"; fi
echo "Restore complete."
