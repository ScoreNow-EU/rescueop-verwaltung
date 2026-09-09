# Self-Hosting (ohne externe Plattform)

Diese Variante laeuft komplett auf deinem eigenen Remote-Server.

## 1) Voraussetzungen

- Linux-Server mit SSH-Zugriff
- Docker + Docker Compose Plugin installiert
- Domain (optional, aber empfohlen)

## 2) Erstes Setup

```bash
cp .env.server.example .env
nano .env
```

Pflichtwerte in `.env` setzen:

- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `ADMIN_PASSWORD`

## 3) Starten

```bash
docker compose up -d --build
```

Status pruefen:

```bash
docker compose ps
docker compose logs -f web
```

Die App lauscht intern auf `127.0.0.1:8000`.

## 4) Reverse Proxy + HTTPS (Nginx)

Beispiel fuer `/etc/nginx/sites-available/rescueop`:

```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Danach:

```bash
sudo ln -s /etc/nginx/sites-available/rescueop /etc/nginx/sites-enabled/rescueop
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d example.com
```

## 5) Updates deployen

```bash
git pull
docker compose up -d --build
```

## 6) Backup / Restore

Backup erstellen:

```bash
./scripts/backup_postgres.sh
```

Restore einspielen:

```bash
./scripts/restore_postgres.sh backups/rescueop_YYYYMMDD_HHMMSS.sql.gz
```

## 7) Export von Render/Remote Postgres

Wenn du Daten aus Render uebernehmen willst:

Hinweis: Fuer die lokale Docker-DB auf diesem Server nutze weiter `./scripts/backup_postgres.sh`.
`export_remote_postgres.sh` ist fuer externe Postgres-Instanzen (z. B. Render) gedacht.

1. Render Connection String kopieren (External Database URL).
2. Export ziehen:

```bash
./scripts/export_remote_postgres.sh "postgresql://USER:PASSWORD@HOST:5432/DBNAME"
```

Alternativ in `.env` eintragen (`RENDER_DATABASE_URL`) und dann ohne Argument starten:

```bash
./scripts/export_remote_postgres.sh
```

3. Export in lokale Docker-DB importieren:

```bash
./scripts/restore_postgres.sh backups/remote_postgres_YYYYMMDD_HHMMSS.sql.gz
```

## 8) Optionaler taeglicher Cron-Backup

```bash
crontab -e
```

Beispiel (taeglich 03:30):

```cron
30 3 * * * cd /path/to/rescueop-verwaltung && ./scripts/backup_postgres.sh
```

## 9) Minimaler Betrieb

- Regelmaessige `apt update && apt upgrade`
- Backups off-server spiegeln (z. B. rsync auf zweites Ziel)
- UFW/FW aktivieren und nur 22/80/443 offen lassen
