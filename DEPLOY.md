# RescueOp Deployment Guide

## 1) Lokal starten (mit venv)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -c "from app import create_app; create_app(); print('ok')"
```

## 2) Ohne eigene Domain veroeffentlichen

Empfohlen: Render Free Plan mit `render.yaml`.

- Repository zu Render verbinden
- Web Service und Postgres werden aus `render.yaml` erstellt
- App ist dann unter einer Render-Subdomain erreichbar

## 3) Wichtige Umgebungsvariablen

- `SECRET_KEY`: muss in Produktion gesetzt sein
- `DATABASE_URL`: wird auf Render automatisch vom DB-Service gesetzt
- `ADMIN_USERNAME`: erster Bootstrap-User (Default: `admin`)
- `ADMIN_PASSWORD`: Bootstrap-Passwort (Default: `admin12345` wenn nicht gesetzt)
- `SESSION_COOKIE_SECURE=1` in Produktion

## 4) Login und Spielstaende

- Jeder neue Benutzer bekommt automatisch einen eigenen Spielstand
- In der Navbar kann zwischen Spielstaenden gewechselt werden
- Owner kann weitere Benutzer zu einem Spielstand hinzufuegen
- Rollen:
  - `owner`: volle Rechte + Benutzer hinzufuegen
  - `editor`: volle Bearbeitung ohne Benutzerverwaltung
  - `viewer`: nur lesend

## 5) Migration bestehender Daten

Beim ersten Start werden bestehende Daten automatisch in einen Default-Spielstand uebernommen.

## 6) Produktion starten

Gunicorn Entry:

```bash
gunicorn -w 2 -k gthread -t 120 -b 0.0.0.0:$PORT wsgi:app
```
