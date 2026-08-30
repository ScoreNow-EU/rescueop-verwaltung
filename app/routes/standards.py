import os
import sqlite3
import shutil
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from app import db
from app import DATA_DIR
from app.access import (
    active_savegame_is_admin,
    assign_active_savegame,
    get_active_savegame_id,
    get_admin_savegame_id,
    scoped,
    scoped_get_or_404,
)
from app.models import (
    NamingLocation,
    NamingOrgType,
    MyVehicle,
    MyWache,
    PlanItem,
    VehicleModule,
    VehicleType,
    WacheLevel,
    WacheType,
    WacheUpgrade,
    my_vehicle_modules,
    my_wache_upgrades,
    plan_item_modules,
    vehicle_type_modules,
    vehicle_type_standard_modules,
)

standards_bp = Blueprint('standards', __name__)


def _database_path():
    return os.path.join(DATA_DIR, 'resqop.db')


def _sqlite_has_table(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _sqlite_fetch_rows(conn, table_name):
    if not _sqlite_has_table(conn, table_name):
        return []
    cur = conn.execute(f'SELECT * FROM {table_name}')
    return [dict(r) for r in cur.fetchall()]


def _clear_savegame_runtime_data(savegame_id):
    plan_item_ids = [r.id for r in PlanItem.query.filter_by(savegame_id=savegame_id).all()]
    vehicle_ids = [r.id for r in MyVehicle.query.filter_by(savegame_id=savegame_id).all()]
    wache_ids = [r.id for r in MyWache.query.filter_by(savegame_id=savegame_id).all()]

    if plan_item_ids:
        db.session.execute(
            plan_item_modules.delete().where(plan_item_modules.c.plan_item_id.in_(plan_item_ids))
        )
    if vehicle_ids:
        db.session.execute(
            my_vehicle_modules.delete().where(my_vehicle_modules.c.my_vehicle_id.in_(vehicle_ids))
        )
    if wache_ids:
        db.session.execute(
            my_wache_upgrades.delete().where(my_wache_upgrades.c.my_wache_id.in_(wache_ids))
        )

    PlanItem.query.filter_by(savegame_id=savegame_id).delete(synchronize_session=False)
    MyVehicle.query.filter_by(savegame_id=savegame_id).delete(synchronize_session=False)
    MyWache.query.filter_by(savegame_id=savegame_id).delete(synchronize_session=False)
    NamingOrgType.query.filter_by(savegame_id=savegame_id).delete(synchronize_session=False)
    NamingLocation.query.filter_by(savegame_id=savegame_id).delete(synchronize_session=False)


def _clear_global_catalog(admin_savegame_id):
    db.session.execute(vehicle_type_modules.delete())
    db.session.execute(vehicle_type_standard_modules.delete())
    WacheLevel.query.filter_by(savegame_id=admin_savegame_id).delete(synchronize_session=False)
    WacheUpgrade.query.filter_by(savegame_id=admin_savegame_id).delete(synchronize_session=False)
    WacheType.query.filter_by(savegame_id=admin_savegame_id).delete(synchronize_session=False)
    VehicleType.query.filter_by(savegame_id=admin_savegame_id).delete(synchronize_session=False)
    VehicleModule.query.filter_by(savegame_id=admin_savegame_id).delete(synchronize_session=False)


def _import_backup_into_active_savegame(sqlite_path, include_global):
    active_savegame_id = get_active_savegame_id()
    admin_savegame_id = get_admin_savegame_id()
    if not active_savegame_id:
        raise ValueError('Kein aktiver Spielstand vorhanden.')
    if include_global and not admin_savegame_id:
        raise ValueError('Admin-Spielstand konnte nicht bestimmt werden.')

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    try:
        source = {
            'vehicle_module': _sqlite_fetch_rows(conn, 'vehicle_module'),
            'vehicle_type': _sqlite_fetch_rows(conn, 'vehicle_type'),
            'vehicle_type_modules': _sqlite_fetch_rows(conn, 'vehicle_type_modules'),
            'vehicle_type_standard_modules': _sqlite_fetch_rows(conn, 'vehicle_type_standard_modules'),
            'wache_type': _sqlite_fetch_rows(conn, 'wache_type'),
            'wache_level': _sqlite_fetch_rows(conn, 'wache_level'),
            'wache_upgrade': _sqlite_fetch_rows(conn, 'wache_upgrade'),
            'naming_org_type': _sqlite_fetch_rows(conn, 'naming_org_type'),
            'naming_location': _sqlite_fetch_rows(conn, 'naming_location'),
            'my_wache': _sqlite_fetch_rows(conn, 'my_wache'),
            'my_vehicle': _sqlite_fetch_rows(conn, 'my_vehicle'),
            'plan_item': _sqlite_fetch_rows(conn, 'plan_item'),
            'my_wache_upgrades': _sqlite_fetch_rows(conn, 'my_wache_upgrades'),
            'my_vehicle_modules': _sqlite_fetch_rows(conn, 'my_vehicle_modules'),
            'plan_item_modules': _sqlite_fetch_rows(conn, 'plan_item_modules'),
        }
    finally:
        conn.close()

    module_id_map = {}
    vehicle_type_id_map = {}
    wache_type_id_map = {}
    wache_upgrade_id_map = {}

    _clear_savegame_runtime_data(active_savegame_id)

    if include_global:
        _clear_global_catalog(admin_savegame_id)

        for row in source['vehicle_module']:
            mod = VehicleModule(
                savegame_id=admin_savegame_id,
                name=row.get('name') or '',
                price=row.get('price') or 0,
            )
            db.session.add(mod)
            db.session.flush()
            module_id_map[row.get('id')] = mod.id

        for row in source['vehicle_type']:
            vt = VehicleType(
                savegame_id=admin_savegame_id,
                name=row.get('name') or '',
                abbreviation=row.get('abbreviation'),
                base_price=row.get('base_price') or 0,
                maintenance_cost=row.get('maintenance_cost') or 0,
                image=row.get('image'),
                is_standard=bool(row.get('is_standard')),
            )
            db.session.add(vt)
            db.session.flush()
            vehicle_type_id_map[row.get('id')] = vt.id

        for row in source['wache_type']:
            wt = WacheType(
                savegame_id=admin_savegame_id,
                name=row.get('name') or '',
                image=row.get('image'),
            )
            db.session.add(wt)
            db.session.flush()
            wache_type_id_map[row.get('id')] = wt.id

        for row in source['wache_level']:
            mapped_wt_id = wache_type_id_map.get(row.get('wache_type_id'))
            if not mapped_wt_id:
                continue
            db.session.add(WacheLevel(
                savegame_id=admin_savegame_id,
                wache_type_id=mapped_wt_id,
                level_number=row.get('level_number') or 0,
                name=row.get('name'),
                cost=row.get('cost') or 0,
                maintenance_cost=row.get('maintenance_cost') or 0,
                max_vehicles=row.get('max_vehicles') or 0,
            ))

        for row in source['wache_upgrade']:
            mapped_wt_id = wache_type_id_map.get(row.get('wache_type_id'))
            if not mapped_wt_id:
                continue
            upg = WacheUpgrade(
                savegame_id=admin_savegame_id,
                wache_type_id=mapped_wt_id,
                name=row.get('name') or '',
                cost=row.get('cost') or 0,
                maintenance_cost=row.get('maintenance_cost') or 0,
                extra_slots=row.get('extra_slots') or 0,
            )
            db.session.add(upg)
            db.session.flush()
            wache_upgrade_id_map[row.get('id')] = upg.id

        for row in source['vehicle_type_modules']:
            vtid = vehicle_type_id_map.get(row.get('vehicle_type_id'))
            mid = module_id_map.get(row.get('vehicle_module_id'))
            if not vtid or not mid:
                continue
            db.session.execute(vehicle_type_modules.insert().values(
                vehicle_type_id=vtid,
                vehicle_module_id=mid,
            ))

        for row in source['vehicle_type_standard_modules']:
            vtid = vehicle_type_id_map.get(row.get('vehicle_type_id'))
            mid = module_id_map.get(row.get('vehicle_module_id'))
            if not vtid or not mid:
                continue
            db.session.execute(vehicle_type_standard_modules.insert().values(
                vehicle_type_id=vtid,
                vehicle_module_id=mid,
            ))
    else:
        source_modules = {r.get('id'): (r.get('name') or '') for r in source['vehicle_module']}
        source_vehicle_types = {r.get('id'): (r.get('name') or '') for r in source['vehicle_type']}
        source_wache_types = {r.get('id'): (r.get('name') or '') for r in source['wache_type']}
        source_wache_upgrades = {
            r.get('id'): (r.get('name') or '', r.get('wache_type_id')) for r in source['wache_upgrade']
        }

        module_lookup = {m.name: m.id for m in scoped(VehicleModule).all()}
        vehicle_type_lookup = {v.name: v.id for v in scoped(VehicleType).all()}
        wache_type_lookup = {w.name: w.id for w in scoped(WacheType).all()}

        for old_id, name in source_modules.items():
            if name in module_lookup:
                module_id_map[old_id] = module_lookup[name]
        for old_id, name in source_vehicle_types.items():
            if name in vehicle_type_lookup:
                vehicle_type_id_map[old_id] = vehicle_type_lookup[name]
        for old_id, name in source_wache_types.items():
            if name in wache_type_lookup:
                wache_type_id_map[old_id] = wache_type_lookup[name]

        upgrades = scoped(WacheUpgrade).all()
        upgrade_lookup = {}
        for upg in upgrades:
            upgrade_lookup[(upg.name, upg.wache_type_id)] = upg.id
        for old_id, (name, old_wt_id) in source_wache_upgrades.items():
            mapped_wt_id = wache_type_id_map.get(old_wt_id)
            if not mapped_wt_id:
                continue
            mapped_upg = upgrade_lookup.get((name, mapped_wt_id))
            if mapped_upg:
                wache_upgrade_id_map[old_id] = mapped_upg

    org_id_map = {}
    loc_id_map = {}
    wache_id_map = {}
    vehicle_id_map = {}
    plan_item_id_map = {}
    plan_item_pending_refs = {}

    for row in source['naming_org_type']:
        org = NamingOrgType(
            savegame_id=active_savegame_id,
            abbreviation=row.get('abbreviation') or '',
            full_name=row.get('full_name') or '',
            no_location=bool(row.get('no_location')),
        )
        db.session.add(org)
        db.session.flush()
        org_id_map[row.get('id')] = org.id

    for row in source['naming_location']:
        loc = NamingLocation(
            savegame_id=active_savegame_id,
            abbreviation=row.get('abbreviation') or '',
            full_name=row.get('full_name') or '',
        )
        db.session.add(loc)
        db.session.flush()
        loc_id_map[row.get('id')] = loc.id

    for row in source['my_wache']:
        mapped_wache_type_id = wache_type_id_map.get(row.get('wache_type_id'))
        if not mapped_wache_type_id:
            continue
        wache = MyWache(
            savegame_id=active_savegame_id,
            name=row.get('name') or '',
            wache_type_id=mapped_wache_type_id,
            current_level=row.get('current_level') or 0,
            naming_org_type_id=org_id_map.get(row.get('naming_org_type_id')),
            naming_location_id=loc_id_map.get(row.get('naming_location_id')),
        )
        db.session.add(wache)
        db.session.flush()
        wache_id_map[row.get('id')] = wache.id

    for row in source['my_vehicle']:
        mapped_wache_id = wache_id_map.get(row.get('my_wache_id'))
        mapped_vehicle_type_id = vehicle_type_id_map.get(row.get('vehicle_type_id'))
        if not mapped_wache_id or not mapped_vehicle_type_id:
            continue
        veh = MyVehicle(
            savegame_id=active_savegame_id,
            my_wache_id=mapped_wache_id,
            vehicle_type_id=mapped_vehicle_type_id,
            nickname=row.get('nickname'),
        )
        db.session.add(veh)
        db.session.flush()
        vehicle_id_map[row.get('id')] = veh.id

    for row in source['plan_item']:
        mapped_vehicle_type_id = vehicle_type_id_map.get(row.get('vehicle_type_id')) if row.get('vehicle_type_id') else None
        mapped_wache_type_id = wache_type_id_map.get(row.get('wache_type_id')) if row.get('wache_type_id') else None
        mapped_wache_upgrade_id = wache_upgrade_id_map.get(row.get('wache_upgrade_id')) if row.get('wache_upgrade_id') else None

        item = PlanItem(
            savegame_id=active_savegame_id,
            category=row.get('category') or 'divider',
            priority=row.get('priority') or 0,
            done=bool(row.get('done')),
            notes=row.get('notes'),
            wache_name=row.get('wache_name'),
            wache_type_id=mapped_wache_type_id,
            created_wache_id=wache_id_map.get(row.get('created_wache_id')),
            target_wache_id=wache_id_map.get(row.get('target_wache_id')),
            target_level=row.get('target_level'),
            vehicle_type_id=mapped_vehicle_type_id,
            vehicle_nickname=row.get('vehicle_nickname'),
            vehicle_wache_id=wache_id_map.get(row.get('vehicle_wache_id')),
            wache_upgrade_id=mapped_wache_upgrade_id,
            extension_wache_id=wache_id_map.get(row.get('extension_wache_id')),
        )
        db.session.add(item)
        db.session.flush()
        old_id = row.get('id')
        plan_item_id_map[old_id] = item.id
        plan_item_pending_refs[item.id] = {
            'target_wache_plan_item_id': row.get('target_wache_plan_item_id'),
            'vehicle_wache_plan_item_id': row.get('vehicle_wache_plan_item_id'),
            'extension_wache_plan_item_id': row.get('extension_wache_plan_item_id'),
        }

    db.session.flush()

    for new_item_id, refs in plan_item_pending_refs.items():
        item = PlanItem.query.get(new_item_id)
        if not item:
            continue
        item.target_wache_plan_item_id = plan_item_id_map.get(refs.get('target_wache_plan_item_id'))
        item.vehicle_wache_plan_item_id = plan_item_id_map.get(refs.get('vehicle_wache_plan_item_id'))
        item.extension_wache_plan_item_id = plan_item_id_map.get(refs.get('extension_wache_plan_item_id'))

    for row in source['my_wache_upgrades']:
        wid = wache_id_map.get(row.get('my_wache_id'))
        uid = wache_upgrade_id_map.get(row.get('wache_upgrade_id'))
        if not wid or not uid:
            continue
        db.session.execute(my_wache_upgrades.insert().values(
            my_wache_id=wid,
            wache_upgrade_id=uid,
        ))

    for row in source['my_vehicle_modules']:
        vid = vehicle_id_map.get(row.get('my_vehicle_id'))
        mid = module_id_map.get(row.get('vehicle_module_id'))
        if not vid or not mid:
            continue
        db.session.execute(my_vehicle_modules.insert().values(
            my_vehicle_id=vid,
            vehicle_module_id=mid,
        ))

    for row in source['plan_item_modules']:
        pid = plan_item_id_map.get(row.get('plan_item_id'))
        mid = module_id_map.get(row.get('vehicle_module_id'))
        if not pid or not mid:
            continue
        db.session.execute(plan_item_modules.insert().values(
            plan_item_id=pid,
            vehicle_module_id=mid,
        ))

    db.session.commit()

    return {
        'global_included': include_global,
        'wachen': len(wache_id_map),
        'vehicles': len(vehicle_id_map),
        'planner_items': len(plan_item_id_map),
    }


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
    db_uri = str(db.engine.url)

    try:
        upload.save(tmp_path)

        with open(tmp_path, 'rb') as f:
            header = f.read(16)
        if header != b'SQLite format 3\x00':
            os.remove(tmp_path)
            flash('Die hochgeladene Datei ist keine gültige SQLite-Datenbank.', 'danger')
            return redirect(url_for('standards.index'))

        include_global_requested = request.form.get('include_global') == '1'
        include_global = bool(include_global_requested and active_savegame_is_admin())
        if include_global_requested and not include_global:
            flash('Globale Kataloge dürfen nur im Admin-Spielstand importiert werden.', 'danger')
            return redirect(url_for('standards.index'))

        if db_uri.startswith('sqlite:') and include_global:
            db.session.remove()
            db.engine.dispose()

            if os.path.isfile(db_path):
                timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                bak_path = db_path + f'.preimport-{timestamp}.bak'
                shutil.copy2(db_path, bak_path)

            os.replace(tmp_path, db_path)
            flash('SQLite-Datenbank vollständig importiert (Admin-Modus).', 'success')
            return redirect(url_for('standards.index'))

        summary = _import_backup_into_active_savegame(tmp_path, include_global=include_global)
        mode_label = 'Admin-Vollimport' if summary['global_included'] else 'Spielstand-Import ohne globale Kataloge'
        flash(
            f'Import erfolgreich: {mode_label}. Wachen: {summary["wachen"]}, Fahrzeuge: {summary["vehicles"]}, Planer: {summary["planner_items"]}.',
            'success',
        )
    except Exception:
        db.session.rollback()
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
        flash('Import fehlgeschlagen. Die aktuelle Datenbank wurde nicht ersetzt.', 'danger')
        return redirect(url_for('standards.index'))

    if os.path.isfile(tmp_path):
        os.remove(tmp_path)

    return redirect(url_for('standards.index'))
