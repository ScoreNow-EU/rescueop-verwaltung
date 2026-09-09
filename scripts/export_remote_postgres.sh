#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${ROOT_DIR}/backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DEFAULT_OUT="${BACKUP_DIR}/remote_postgres_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

DB_URL="${1:-}"
OUT_FILE="${2:-${DEFAULT_OUT}}"

if [[ -z "${DB_URL}" && -f "${ROOT_DIR}/.env" ]]; then
  set -a
  source "${ROOT_DIR}/.env"
  set +a
  DB_URL="${RENDER_DATABASE_URL:-}"
fi

if [[ -z "${DB_URL}" ]]; then
  echo "Usage: $0 <database_url> [output.sql.gz]"
  echo "Alternative: set RENDER_DATABASE_URL in .env"
  exit 1
fi

# Render URLs often require SSL; add sslmode=require when missing.
if [[ "${DB_URL}" != *"sslmode="* ]]; then
  if [[ "${DB_URL}" == *"?"* ]]; then
    DB_URL="${DB_URL}&sslmode=require"
  else
    DB_URL="${DB_URL}?sslmode=require"
  fi
fi

docker run --rm \
  -e DATABASE_URL="${DB_URL}" \
  postgres:16-alpine \
  sh -c 'pg_dump "$DATABASE_URL"' | gzip > "${OUT_FILE}"

echo "Export completed: ${OUT_FILE}"
