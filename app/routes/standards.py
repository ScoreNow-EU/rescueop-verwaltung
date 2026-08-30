import os
import shutil
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from app import db
from app import DATA_DIR
from app.access import assign_active_savegame, scoped, scoped_get_or_404
from app.models import NamingOrgType, NamingLocation, VehicleType, VehicleModule

standards_bp = Blueprint('standards', __name__)


def _database_path():
    return os.path.join(DATA_DIR, 'resqop.db')


@standards_bp.route('/standards')
def index():
    org_types = scoped(NamingOrgType).order_by(NamingOrgType.abbreviation).all()
    locations = scoped(NamingLocation).order_by(NamingLocation.abbreviation).all()
    vehicle_types = scoped(VehicleType).order_by(VehicleType.name).all()
    all_modules = scoped(VehicleModule).order_by(VehicleModule.name).all()
    return render_template('standards.html', active_tab='standards',
                           org_types=org_types, locations=locations,
                           vehicle_types=vehicle_types, all_modules=all_modules)


# ---------- Org Types -------------------------------------------------------

@standards_bp.route('/standards/org/add', methods=['POST'])
def add_org():
    abbr = request.form.get('abbreviation', '').strip().upper()
    full = request.form.get('full_name', '').strip()
    if not abbr or not full:
        flash('Kürzel und Name sind erforderlich.', 'danger')
        return redirect(url_for('standards.index'))
    if scoped(NamingOrgType).filter_by(abbreviation=abbr).first():
        flash(f'Kürzel „{abbr}" ist bereits vorhanden.', 'danger')
        return redirect(url_for('standards.index'))
    no_loc = 'no_location' in request.form
    org = NamingOrgType(abbreviation=abbr, full_name=full, no_location=no_loc)
    assign_active_savegame(org)
    db.session.add(org)
    db.session.commit()
    flash(f'Organisations-Typ „{abbr}" hinzugefügt.', 'success')
    return redirect(url_for('standards.index'))


@standards_bp.route('/standards/org/<int:oid>/edit', methods=['POST'])
def edit_org(oid):
    org = scoped_get_or_404(NamingOrgType, oid)
    abbr = request.form.get('abbreviation', '').strip().upper()
    full = request.form.get('full_name', '').strip()
    if not abbr or not full:
        flash('Kürzel und Name sind erforderlich.', 'danger')
        return redirect(url_for('standards.index'))
    existing = scoped(NamingOrgType).filter_by(abbreviation=abbr).first()
    if existing and existing.id != oid:
        flash(f'Kürzel „{abbr}" ist bereits vorhanden.', 'danger')
        return redirect(url_for('standards.index'))
    org.abbreviation = abbr
    org.full_name = full
    org.no_location = 'no_location' in request.form
    db.session.commit()
    flash(f'Organisations-Typ „{abbr}" aktualisiert.', 'success')
    return redirect(url_for('standards.index'))


@standards_bp.route('/standards/org/<int:oid>/delete', methods=['POST'])
def delete_org(oid):
    org = scoped_get_or_404(NamingOrgType, oid)
    abbr = org.abbreviation
    db.session.delete(org)
    db.session.commit()
    flash(f'Organisations-Typ „{abbr}" gelöscht.', 'success')
    return redirect(url_for('standards.index'))


# ---------- Locations -------------------------------------------------------

@standards_bp.route('/standards/location/add', methods=['POST'])
def add_location():
    abbr = request.form.get('abbreviation', '').strip().upper()
    full = request.form.get('full_name', '').strip()
    if not abbr or not full:
        flash('Kürzel und Name sind erforderlich.', 'danger')
        return redirect(url_for('standards.index'))
    if scoped(NamingLocation).filter_by(abbreviation=abbr).first():
        flash(f'Kürzel „{abbr}" ist bereits vorhanden.', 'danger')
        return redirect(url_for('standards.index'))
    loc = NamingLocation(abbreviation=abbr, full_name=full)
    assign_active_savegame(loc)
    db.session.add(loc)
    db.session.commit()
    flash(f'Standort „{abbr}" hinzugefügt.', 'success')
    return redirect(url_for('standards.index'))


@standards_bp.route('/standards/location/<int:lid>/edit', methods=['POST'])
def edit_location(lid):
    loc = scoped_get_or_404(NamingLocation, lid)
    abbr = request.form.get('abbreviation', '').strip().upper()
    full = request.form.get('full_name', '').strip()
    if not abbr or not full:
        flash('Kürzel und Name sind erforderlich.', 'danger')
        return redirect(url_for('standards.index'))
    existing = scoped(NamingLocation).filter_by(abbreviation=abbr).first()
    if existing and existing.id != lid:
        flash(f'Kürzel „{abbr}" ist bereits vorhanden.', 'danger')
        return redirect(url_for('standards.index'))
    loc.abbreviation = abbr
    loc.full_name = full
    db.session.commit()
    flash(f'Standort „{abbr}" aktualisiert.', 'success')
    return redirect(url_for('standards.index'))


@standards_bp.route('/standards/location/<int:lid>/delete', methods=['POST'])
def delete_location(lid):
    loc = scoped_get_or_404(NamingLocation, lid)
    abbr = loc.abbreviation
    db.session.delete(loc)
    db.session.commit()
    flash(f'Standort „{abbr}" gelöscht.', 'success')
    return redirect(url_for('standards.index'))


# ---------- Standard Modules ------------------------------------------------

@standards_bp.route('/standards/modules/<int:vtid>/save', methods=['POST'])
def save_standard_modules(vtid):
    vt = scoped_get_or_404(VehicleType, vtid)
    selected_ids = request.form.getlist('module_ids', type=int)
    vt.standard_modules = scoped(VehicleModule).filter(
        VehicleModule.id.in_(selected_ids)
    ).all() if selected_ids else []
    db.session.commit()
    flash(f'Standard-Module für „{vt.name}" gespeichert.', 'success')
    return redirect(url_for('standards.index'))


# ---------- Backup / Restore ----------------------------------------------

@standards_bp.route('/backup/export', methods=['GET'])
def export_database():
    db_uri = str(db.engine.url)
    if not db_uri.startswith('sqlite:'):
        flash('Export ist nur für SQLite verfügbar. Für PostgreSQL nutze bitte Datenbank-Backups beim Hoster.', 'danger')
        return redirect(url_for('standards.index'))

    db_path = _database_path()
    if not os.path.isfile(db_path):
        flash('Datenbankdatei wurde nicht gefunden.', 'danger')
        return redirect(url_for('standards.index'))

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    filename = f'resqop-backup-{timestamp}.db'
    return send_file(db_path, as_attachment=True, download_name=filename)


@standards_bp.route('/backup/import', methods=['POST'])
def import_database():
    db_uri = str(db.engine.url)
    if not db_uri.startswith('sqlite:'):
        flash('Import ist nur für SQLite verfügbar. Für PostgreSQL nutze bitte Datenbank-Restore beim Hoster.', 'danger')
        return redirect(url_for('standards.index'))

    upload = request.files.get('backup_file')
    if not upload or not upload.filename:
        flash('Bitte eine Backup-Datei auswählen.', 'danger')
        return redirect(url_for('standards.index'))

    ext = os.path.splitext(upload.filename)[1].lower()
    if ext not in {'.db', '.sqlite', '.sqlite3'}:
        flash('Ungültiges Dateiformat. Erlaubt sind .db, .sqlite, .sqlite3.', 'danger')
        return redirect(url_for('standards.index'))

    db_path = _database_path()
    tmp_path = db_path + '.import.tmp'

    try:
        upload.save(tmp_path)

        with open(tmp_path, 'rb') as f:
            header = f.read(16)
        if header != b'SQLite format 3\x00':
            os.remove(tmp_path)
            flash('Die hochgeladene Datei ist keine gültige SQLite-Datenbank.', 'danger')
            return redirect(url_for('standards.index'))

        db.session.remove()
        db.engine.dispose()

        if os.path.isfile(db_path):
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            bak_path = db_path + f'.preimport-{timestamp}.bak'
            shutil.copy2(db_path, bak_path)

        os.replace(tmp_path, db_path)
        flash('Datenbank erfolgreich importiert.', 'success')
    except Exception:
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
        flash('Import fehlgeschlagen. Die aktuelle Datenbank wurde nicht ersetzt.', 'danger')

    return redirect(url_for('standards.index'))
