#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${ROOT_DIR}/backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/rescueop_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

set -a
source "${ROOT_DIR}/.env"
set +a

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  echo "POSTGRES_PASSWORD is not set in .env"
  exit 1
fi

cd "${ROOT_DIR}"
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-rescueop}" -d "${POSTGRES_DB:-rescueop}" | gzip > "${BACKUP_FILE}"

echo "Backup written to ${BACKUP_FILE}"
