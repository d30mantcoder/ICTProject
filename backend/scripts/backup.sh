#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/backups"
if [[ -z "${DATABASE_URL:-}" && -f "$ROOT/.env" ]]; then
  DATABASE_URL="$("$ROOT/.venv/bin/python" -c 'from dotenv import dotenv_values; print(dotenv_values(".env").get("DATABASE_URL", ""))')"
fi
DATABASE_URL="${DATABASE_URL:-mysql+pymysql://root:@127.0.0.1:3306/study_lms?charset=utf8mb4}"
DB_PART="${DATABASE_URL#*://}"; DB_PART="${DB_PART#*/}"; DB_NAME="${DB_PART%%\?*}"
DB_AUTH="${DATABASE_URL#*://}"; DB_AUTH="${DB_AUTH%%@*}"
DB_USER="${DB_AUTH%%:*}"; DB_PASS="${DB_AUTH#*:}"
BACKUP_FILE="$ROOT/backups/${DB_NAME}_$(date +%Y%m%d_%H%M%S).sql.gz"
if [[ -n "$DB_PASS" ]]; then MYSQL_PWD="$DB_PASS" mariadb-dump -h 127.0.0.1 -u "$DB_USER" --single-transaction --routines --triggers "$DB_NAME" | gzip > "$BACKUP_FILE"
else mariadb-dump -h 127.0.0.1 -u "$DB_USER" --single-transaction --routines --triggers "$DB_NAME" | gzip > "$BACKUP_FILE"; fi
find "$ROOT/backups" -type f -name '*.sql.gz' -mtime +14 -delete
echo "Backup created: $BACKUP_FILE"
