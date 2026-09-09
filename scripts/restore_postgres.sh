#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <backup.sql.gz>"
  exit 1
fi

BACKUP_PATH="$1"
if [[ ! -f "${BACKUP_PATH}" ]]; then
  echo "Backup file not found: ${BACKUP_PATH}"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

set -a
source "${ROOT_DIR}/.env"
set +a

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  echo "POSTGRES_PASSWORD is not set in .env"
  exit 1
fi

cd "${ROOT_DIR}"
gunzip -c "${BACKUP_PATH}" | docker compose exec -T db psql -U "${POSTGRES_USER:-rescueop}" -d "${POSTGRES_DB:-rescueop}"

echo "Restore completed from ${BACKUP_PATH}"
