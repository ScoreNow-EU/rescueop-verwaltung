import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from app import db, ASSETS_DIR
from app.access import assign_active_savegame, scoped, scoped_get_or_404
from app.models import WacheType, WacheLevel, WacheUpgrade

wachen_bp = Blueprint('wachen', __name__)

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def _existing_images():
    folder = os.path.join(ASSETS_DIR, 'wachen')
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder)
                  if os.path.isfile(os.path.join(folder, f)) and _allowed(f))


# ---------- Wache Types ---------------------------------------------------

@wachen_bp.route('/wachen')
def index():
    types = scoped(WacheType).order_by(WacheType.name).all()
    return render_template('wachen.html', active_tab='wachen',
                           wache_types=types, existing_images=_existing_images())


@wachen_bp.route('/wachen/add', methods=['POST'])
def add_type():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name darf nicht leer sein.', 'danger')
        return redirect(url_for('wachen.index'))

    image = None
    existing = request.form.get('existing_image', '').strip()
    if existing and existing in _existing_images():
        image = existing
    file = request.files.get('image_upload')
    if file and file.filename and _allowed(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(ASSETS_DIR, 'wachen', filename))
        image = filename

    wt = WacheType(name=name, image=image)
    assign_active_savegame(wt)
    db.session.add(wt)
    db.session.commit()
    flash(f'Wachen-Typ „{name}" erstellt.', 'success')
    return redirect(url_for('wachen.index'))


@wachen_bp.route('/wachen/<int:wid>/edit', methods=['POST'])
def edit_type(wid):
    wt = scoped_get_or_404(WacheType, wid)
    wt.name = request.form.get('name', wt.name).strip()

    existing = request.form.get('existing_image', '').strip()
    if existing and existing in _existing_images():
        wt.image = existing
    file = request.files.get('image_upload')
    if file and file.filename and _allowed(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(ASSETS_DIR, 'wachen', filename))
        wt.image = filename

    db.session.commit()
    flash(f'Wachen-Typ „{wt.name}" aktualisiert.', 'success')
    return redirect(url_for('wachen.index'))


@wachen_bp.route('/wachen/<int:wid>/delete', methods=['POST'])
def delete_type(wid):
    wt = scoped_get_or_404(WacheType, wid)
    name = wt.name
    db.session.delete(wt)
    db.session.commit()
    flash(f'Wachen-Typ „{name}" gelöscht.', 'success')
    return redirect(url_for('wachen.index'))


# ---------- Levels --------------------------------------------------------

@wachen_bp.route('/wachen/<int:wid>/levels/add', methods=['POST'])
def add_level(wid):
    wt = scoped_get_or_404(WacheType, wid)
    name = request.form.get('level_name', '').strip()
    cost = request.form.get('level_cost', 0, type=float)
    maintenance_cost = request.form.get('level_maintenance_cost', 0, type=float)

    max_veh = request.form.get('level_max_vehicles', 0, type=int)

    # Auto-assign next level number
    max_lvl = max((l.level_number for l in wt.levels), default=0)

    lvl = WacheLevel(wache_type_id=wt.id, level_number=max_lvl + 1,
                     name=name if name else None, cost=cost,
                     maintenance_cost=maintenance_cost,
                     max_vehicles=max_veh)
    assign_active_savegame(lvl)
    db.session.add(lvl)
    db.session.commit()
    flash(f'Stufe {lvl.level_number} zu „{wt.name}" hinzugefügt.', 'success')
    return redirect(url_for('wachen.index'))


@wachen_bp.route('/wachen/levels/<int:lid>/edit', methods=['POST'])
def edit_level(lid):
    lvl = scoped_get_or_404(WacheLevel, lid)
    lvl.name = request.form.get('level_name', lvl.name or '').strip() or None
    lvl.cost = request.form.get('level_cost', lvl.cost, type=float)
    lvl.maintenance_cost = request.form.get('level_maintenance_cost', lvl.maintenance_cost, type=float)
    lvl.max_vehicles = request.form.get('level_max_vehicles', lvl.max_vehicles, type=int)
    db.session.commit()
    flash(f'Stufe {lvl.level_number} aktualisiert.', 'success')
    return redirect(url_for('wachen.index'))


@wachen_bp.route('/wachen/<int:wid>/levels/save', methods=['POST'])
def save_levels(wid):
    wt = scoped_get_or_404(WacheType, wid)
    level_ids = request.form.getlist('level_ids', type=int)
    updated = 0
    for lid in level_ids:
        lvl = scoped(WacheLevel).filter_by(id=lid).first()
        if not lvl or lvl.wache_type_id != wt.id:
            continue
        lvl.name = request.form.get(f'level_name_{lid}', lvl.name or '').strip() or None
        lvl.cost = request.form.get(f'level_cost_{lid}', lvl.cost, type=float)
        lvl.maintenance_cost = request.form.get(
            f'level_maintenance_cost_{lid}', lvl.maintenance_cost, type=float
        )
        lvl.max_vehicles = request.form.get(
            f'level_max_vehicles_{lid}', lvl.max_vehicles, type=int
        )
        updated += 1
    db.session.commit()
    flash(f'{updated} Stufe(n) für „{wt.name}" gespeichert.', 'success')
    return redirect(url_for('wachen.index'))


@wachen_bp.route('/wachen/levels/<int:lid>/delete', methods=['POST'])
def delete_level(lid):
    lvl = scoped_get_or_404(WacheLevel, lid)
    db.session.delete(lvl)
    db.session.commit()
    flash('Stufe gelöscht.', 'success')
    return redirect(url_for('wachen.index'))


# ---------- Upgrades (Erweiterungen) --------------------------------------

@wachen_bp.route('/wachen/<int:wid>/upgrades/add', methods=['POST'])
def add_upgrade(wid):
    wt = scoped_get_or_404(WacheType, wid)
    name = request.form.get('upgrade_name', '').strip()
    cost = request.form.get('upgrade_cost', 0, type=float)
    maintenance_cost = request.form.get('upgrade_maintenance_cost', 0, type=float)
    extra_slots = request.form.get('upgrade_extra_slots', 0, type=int)
    if not name:
        flash('Name darf nicht leer sein.', 'danger')
        return redirect(url_for('wachen.index'))
    u = WacheUpgrade(
        wache_type_id=wt.id,
        name=name,
        cost=cost,
        maintenance_cost=maintenance_cost,
        extra_slots=extra_slots,
    )
    assign_active_savegame(u)
    db.session.add(u)
    db.session.commit()
    flash(f'Erweiterung „{name}" zu „{wt.name}" hinzugefügt.', 'success')
    return redirect(url_for('wachen.index'))


@wachen_bp.route('/wachen/upgrades/<int:uid>/edit', methods=['POST'])
def edit_upgrade(uid):
    u = scoped_get_or_404(WacheUpgrade, uid)
    u.name = request.form.get('upgrade_name', u.name).strip()
    u.cost = request.form.get('upgrade_cost', u.cost, type=float)
    u.maintenance_cost = request.form.get('upgrade_maintenance_cost', u.maintenance_cost, type=float)
    u.extra_slots = request.form.get('upgrade_extra_slots', u.extra_slots, type=int)
    db.session.commit()
    flash(f'Erweiterung „{u.name}" aktualisiert.', 'success')
    return redirect(url_for('wachen.index'))


@wachen_bp.route('/wachen/<int:wid>/upgrades/save', methods=['POST'])
def save_upgrades(wid):
    wt = scoped_get_or_404(WacheType, wid)
    upgrade_ids = request.form.getlist('upgrade_ids', type=int)
    updated = 0
    for uid in upgrade_ids:
        upg = scoped(WacheUpgrade).filter_by(id=uid).first()
        if not upg or upg.wache_type_id != wt.id:
            continue
        upg.name = request.form.get(f'upgrade_name_{uid}', upg.name).strip()
        upg.cost = request.form.get(f'upgrade_cost_{uid}', upg.cost, type=float)
        upg.maintenance_cost = request.form.get(
            f'upgrade_maintenance_cost_{uid}', upg.maintenance_cost, type=float
        )
        upg.extra_slots = request.form.get(
            f'upgrade_extra_slots_{uid}', upg.extra_slots, type=int
        )
        updated += 1
    db.session.commit()
    flash(f'{updated} Erweiterung(en) für „{wt.name}" gespeichert.', 'success')
    return redirect(url_for('wachen.index'))


@wachen_bp.route('/wachen/upgrades/<int:uid>/delete', methods=['POST'])
def delete_upgrade(uid):
    u = scoped_get_or_404(WacheUpgrade, uid)
    db.session.delete(u)
    db.session.commit()
    flash('Erweiterung gelöscht.', 'success')
    return redirect(url_for('wachen.index'))
