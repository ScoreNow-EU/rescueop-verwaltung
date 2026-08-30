from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.access import assign_active_savegame, scoped, scoped_get_or_404
from app.models import (VehicleType, VehicleModule, WacheType, WacheLevel,
                        MyWache, MyVehicle, WacheUpgrade, my_vehicle_modules,
                        NamingOrgType, NamingLocation)

fleet_bp = Blueprint('fleet', __name__)


@fleet_bp.route('/fleet')
def index():
    wachen = scoped(MyWache).order_by(MyWache.name).all()
    wache_types = scoped(WacheType).order_by(WacheType.name).all()
    vehicle_types = scoped(VehicleType).order_by(VehicleType.name).all()
    org_types = scoped(NamingOrgType).order_by(NamingOrgType.abbreviation).all()
    locations = scoped(NamingLocation).order_by(NamingLocation.abbreviation).all()
    selected_id = request.args.get('wache', type=int)
    selected = scoped(MyWache).filter_by(id=selected_id).first() if selected_id else (wachen[0] if wachen else None)
    return render_template('fleet.html', active_tab='fleet',
                           wachen=wachen, wache_types=wache_types,
                           vehicle_types=vehicle_types, selected=selected,
                           org_types=org_types, locations=locations)


# ---------- My Wachen -----------------------------------------------------

@fleet_bp.route('/fleet/wache/add', methods=['POST'])
def add_wache():
    name = request.form.get('name', '').strip()
    wache_type_id = request.form.get('wache_type_id', type=int)
    org_type_id = request.form.get('naming_org_type_id', type=int) or None
    location_id = request.form.get('naming_location_id', type=int) or None
    if not name or not wache_type_id:
        flash('Name und Typ sind erforderlich.', 'danger')
        return redirect(url_for('fleet.index'))
    wt = scoped_get_or_404(WacheType, wache_type_id)
    initial_level = min((l.level_number for l in wt.levels), default=0)
    w = MyWache(name=name, wache_type_id=wt.id, current_level=initial_level,
                naming_org_type_id=org_type_id, naming_location_id=location_id)
    assign_active_savegame(w)
    db.session.add(w)
    db.session.commit()
    flash(f'Wache „{name}" erstellt.', 'success')
    return redirect(url_for('fleet.index', wache=w.id))


@fleet_bp.route('/fleet/wache/<int:wid>/edit', methods=['POST'])
def edit_wache(wid):
    w = scoped_get_or_404(MyWache, wid)
    w.name = request.form.get('name', w.name).strip()
    w.naming_org_type_id = request.form.get('naming_org_type_id', type=int) or None
    w.naming_location_id = request.form.get('naming_location_id', type=int) or None
    db.session.commit()
    flash(f'Wache „{w.name}" aktualisiert.', 'success')
    return redirect(url_for('fleet.index', wache=w.id))


@fleet_bp.route('/fleet/wache/<int:wid>/upgrade', methods=['POST'])
def upgrade_wache(wid):
    w = scoped_get_or_404(MyWache, wid)
    max_level = max((l.level_number for l in w.wache_type.levels), default=0)
    if w.current_level < max_level:
        w.current_level += 1
        db.session.commit()
        flash(f'Wache „{w.name}" auf Stufe {w.current_level} ausgebaut.', 'success')
    else:
        flash('Maximale Stufe bereits erreicht.', 'danger')
    return redirect(url_for('fleet.index', wache=w.id))


@fleet_bp.route('/fleet/wache/<int:wid>/downgrade', methods=['POST'])
def downgrade_wache(wid):
    w = scoped_get_or_404(MyWache, wid)
    min_level = min((l.level_number for l in w.wache_type.levels), default=0)
    if w.current_level > min_level:
        w.current_level -= 1
        db.session.commit()
        flash(f'Wache „{w.name}" auf Stufe {w.current_level} zurückgestuft.', 'success')
    return redirect(url_for('fleet.index', wache=w.id))


@fleet_bp.route('/fleet/wache/<int:wid>/delete', methods=['POST'])
def delete_wache(wid):
    w = scoped_get_or_404(MyWache, wid)
    name = w.name
    db.session.delete(w)
    db.session.commit()
    flash(f'Wache „{name}" gelöscht.', 'success')
    return redirect(url_for('fleet.index'))


# ---------- My Vehicles ---------------------------------------------------

@fleet_bp.route('/fleet/wache/<int:wid>/vehicle/add', methods=['POST'])
def add_vehicle(wid):
    w = scoped_get_or_404(MyWache, wid)
    vt_id = request.form.get('vehicle_type_id', type=int)
    nickname = request.form.get('nickname', '').strip() or None
    if not vt_id:
        flash('Fahrzeugtyp ist erforderlich.', 'danger')
        return redirect(url_for('fleet.index', wache=w.id))
    vt = scoped_get_or_404(VehicleType, vt_id)
    v = MyVehicle(my_wache_id=w.id, vehicle_type_id=vt.id, nickname=nickname)
    assign_active_savegame(v)
    v.installed_modules = list(vt.standard_modules)
    db.session.add(v)
    db.session.commit()
    flash('Fahrzeug hinzugefügt.', 'success')
    return redirect(url_for('fleet.index', wache=w.id))


@fleet_bp.route('/fleet/vehicle/<int:vid>/edit', methods=['POST'])
def edit_vehicle(vid):
    v = scoped_get_or_404(MyVehicle, vid)
    v.nickname = request.form.get('nickname', '').strip() or None
    db.session.commit()
    flash('Fahrzeug aktualisiert.', 'success')
    return redirect(url_for('fleet.index', wache=v.my_wache_id))


@fleet_bp.route('/fleet/vehicle/<int:vid>/delete', methods=['POST'])
def delete_vehicle(vid):
    v = scoped_get_or_404(MyVehicle, vid)
    wid = v.my_wache_id
    db.session.delete(v)
    db.session.commit()
    flash('Fahrzeug gelöscht.', 'success')
    return redirect(url_for('fleet.index', wache=wid))


@fleet_bp.route('/fleet/vehicle/<int:vid>/toggle_module/<int:mid>', methods=['POST'])
def toggle_module(vid, mid):
    from flask import jsonify
    v = scoped_get_or_404(MyVehicle, vid)
    mod = scoped_get_or_404(VehicleModule, mid)
    if mod in v.installed_modules:
        v.installed_modules.remove(mod)
        installed = False
    else:
        v.installed_modules.append(mod)
        installed = True
    db.session.commit()
    return jsonify(ok=True, installed=installed, mod_name=mod.name)


@fleet_bp.route('/fleet/wache/<int:wid>/toggle_upgrade/<int:uid>', methods=['POST'])
def toggle_wache_upgrade(wid, uid):
    from flask import jsonify
    w = scoped_get_or_404(MyWache, wid)
    u = scoped_get_or_404(WacheUpgrade, uid)
    if u in w.installed_upgrades:
        w.installed_upgrades.remove(u)
        installed = False
    else:
        w.installed_upgrades.append(u)
        installed = True
    db.session.commit()
    return jsonify(ok=True, installed=installed, name=u.name,
                   effective_max=w.effective_max_vehicles)
