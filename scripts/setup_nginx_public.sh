#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <domain> [email-for-https]"
  echo "Example: $0 rescueop.example.com admin@example.com"
  exit 1
fi

DOMAIN="$1"
EMAIL="${2:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${ROOT_DIR}/nginx/rescueop.conf"
TARGET_AVAILABLE="/etc/nginx/sites-available/rescueop"
TARGET_ENABLED="/etc/nginx/sites-enabled/rescueop"

if [[ ! -f "${TEMPLATE}" ]]; then
  echo "Missing template: ${TEMPLATE}"
  exit 1
fi

if command -v sudo >/dev/null 2>&1 && [[ "${EUID}" -ne 0 ]]; then
  SUDO="sudo"
else
  SUDO=""
fi

if ! command -v nginx >/dev/null 2>&1; then
  echo "Nginx is not installed. Install it first: apt update && apt install -y nginx"
  exit 1
fi

TMP_FILE="$(mktemp)"
LISTEN_OPT=""
if [[ "${DOMAIN}" == "_" ]]; then
  LISTEN_OPT=" default_server"
fi

sed -e "s/__DOMAIN__/${DOMAIN}/g" -e "s/__LISTEN_OPT__/${LISTEN_OPT}/g" "${TEMPLATE}" > "${TMP_FILE}"

${SUDO} cp "${TMP_FILE}" "${TARGET_AVAILABLE}"
rm -f "${TMP_FILE}"

${SUDO} ln -sf "${TARGET_AVAILABLE}" "${TARGET_ENABLED}"
if [[ -f /etc/nginx/sites-enabled/default ]]; then
  ${SUDO} rm -f /etc/nginx/sites-enabled/default
fi

${SUDO} nginx -t
${SUDO} systemctl reload nginx

echo "Nginx site enabled for ${DOMAIN}."

if [[ -n "${EMAIL}" ]]; then
  if command -v certbot >/dev/null 2>&1; then
    ${SUDO} certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "${EMAIL}" --redirect
    echo "HTTPS certificate installed and redirect enabled."
  else
    echo "certbot not found. Install and run:"
    echo "  apt install -y certbot python3-certbot-nginx"
    echo "  certbot --nginx -d ${DOMAIN} -m ${EMAIL} --agree-tos --redirect"
  fi
else
  echo "No email provided, HTTPS not configured yet."
  echo "Run later: certbot --nginx -d ${DOMAIN} -m you@example.com --agree-tos --redirect"
fi

echo "Done. App is publicly reachable via Nginx for domain: ${DOMAIN}"
