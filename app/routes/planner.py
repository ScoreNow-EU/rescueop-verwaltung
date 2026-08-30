from types import SimpleNamespace

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.access import assign_active_savegame, scoped, scoped_get_or_404
from app.models import (VehicleType, VehicleModule, WacheType, WacheLevel,
                        MyWache, MyVehicle, PlanItem, WacheUpgrade,
                        NamingOrgType, NamingLocation, NamingPreset)
import re

planner_bp = Blueprint('planner', __name__)


def _next_priority(done_state=None):
    query = scoped(PlanItem)
    if done_state is not None:
        query = query.filter(PlanItem.done == done_state)
    return query.with_entities(db.func.max(PlanItem.priority)).scalar() or 0


def _parse_wache_ref(ref):
    if not ref:
        return None, None
    kind = 'w'
    raw_id = ref
    if ':' in ref:
        kind, raw_id = ref.split(':', 1)
    try:
        return kind, int(raw_id)
    except (TypeError, ValueError):
        return None, None


def _make_real_wache_entry(wache):
    return SimpleNamespace(
        ref=f'w:{wache.id}',
        kind='real',
        id=wache.id,
        name=wache.name,
        wache_type=wache.wache_type,
        current_level=wache.current_level,
        vehicles=list(wache.vehicles),
        org_type=wache.org_type,
        location=wache.location,
        max_vehicles=wache.effective_max_vehicles,
        effective_max_vehicles=wache.effective_max_vehicles,
    )


def _make_planned_wache_entry(plan_item):
    first_level = min(plan_item.wache_type.levels, key=lambda l: l.level_number) if plan_item.wache_type and plan_item.wache_type.levels else None
    max_vehicles = first_level.max_vehicles if first_level else 0
    initial_level = first_level.level_number if first_level else 0
    return SimpleNamespace(
        ref=f'p:{plan_item.id}',
        kind='planned',
        id=plan_item.id,
        name=plan_item.wache_name,
        wache_type=plan_item.wache_type,
        current_level=initial_level,
        vehicles=[],
        org_type=None,
        location=None,
        max_vehicles=max_vehicles,
        effective_max_vehicles=max_vehicles,
    )


def _resolve_wache_entry(ref):
    kind, raw_id = _parse_wache_ref(ref)
    if kind == 'w' and raw_id is not None:
        wache = scoped(MyWache).filter_by(id=raw_id).first()
        if wache:
            return _make_real_wache_entry(wache)
    if kind == 'p' and raw_id is not None:
        plan_item = scoped(PlanItem).filter_by(id=raw_id).first()
        if plan_item and plan_item.category == 'wache_buy':
            return _make_planned_wache_entry(plan_item)
    return None


def _resolve_active_wache(ref):
    entry = _resolve_wache_entry(ref)
    if not entry:
        return None
    if entry.kind == 'real':
        return scoped(MyWache).filter_by(id=entry.id).first()
    plan_item = scoped(PlanItem).filter_by(id=entry.id).first()
    return plan_item.created_wache if plan_item and plan_item.created_wache else None


def _planned_wache_ref_from_item(item):
    if item.target_wache_plan_item_id:
        return f'p:{item.target_wache_plan_item_id}'
    if item.extension_wache_plan_item_id:
        return f'p:{item.extension_wache_plan_item_id}'
    if item.vehicle_wache_plan_item_id:
        return f'p:{item.vehicle_wache_plan_item_id}'
    return None


@planner_bp.route('/planner')
def index():
    items = scoped(PlanItem).filter_by(done=False).order_by(PlanItem.priority).all()
    done_items = scoped(PlanItem).filter_by(done=True).order_by(PlanItem.priority).all()
    vehicle_types = scoped(VehicleType).order_by(VehicleType.is_standard.desc(), VehicleType.name).all()
    wache_types = scoped(WacheType).order_by(WacheType.name).all()
    my_wachen = scoped(MyWache).order_by(MyWache.name).all()
    planner_wachen = [_make_real_wache_entry(w) for w in my_wachen]
    planner_wachen.extend(
        _make_planned_wache_entry(item)
        for item in items
        if item.category == 'wache_buy'
    )
    planner_wachen.sort(key=lambda w: (w.name or '').lower())
    all_modules = scoped(VehicleModule).order_by(VehicleModule.name).all()
    org_types = scoped(NamingOrgType).order_by(NamingOrgType.abbreviation).all()
    locations = scoped(NamingLocation).order_by(NamingLocation.abbreviation).all()
    naming_presets = scoped(NamingPreset).order_by(NamingPreset.is_default.desc(), NamingPreset.name).all()

    # Used by planner naming helpers in the template script.
    wache_veh_counts = {}
    for w in planner_wachen:
        wache_veh_counts[w.ref] = {}
    for w in my_wachen:
        counts = wache_veh_counts.setdefault(f'w:{w.id}', {})
        for v in w.vehicles:
            key = str(v.vehicle_type_id)
            counts[key] = counts.get(key, 0) + 1

    # Also count planned (not done) vehicle purchases so generated nicknames
    # continue with the next free number after existing + planned vehicles.
    for item in items:
        if item.category != 'vehicle' or not item.vehicle_type_id:
            continue
        wkey = f'w:{item.vehicle_wache_id}' if item.vehicle_wache_id else _planned_wache_ref_from_item(item)
        if not wkey:
            continue
        tkey = str(item.vehicle_type_id)
        if wkey not in wache_veh_counts:
            wache_veh_counts[wkey] = {}
        wache_veh_counts[wkey][tkey] = wache_veh_counts[wkey].get(tkey, 0) + 1

    org_wache_next = {}
    for org in org_types:
        if not org.no_location:
            continue
        max_num = 0
        pattern = re.compile(rf'^{re.escape(org.abbreviation)}(\d+)$')
        for w in my_wachen:
            match = pattern.match((w.name or '').strip())
            if not match:
                continue
            max_num = max(max_num, int(match.group(1)))
        for item in items:
            if item.category != 'wache_buy' or not item.wache_name:
                continue
            match = pattern.match(item.wache_name.strip())
            if not match:
                continue
            max_num = max(max_num, int(match.group(1)))
        org_wache_next[org.abbreviation] = max_num + 1

    # Running total (skipping dividers which have cost 0)
    running = []
    total = 0
    for item in items:
        total += item.cost
        running.append(total)

    # Build section subtotals: split items at dividers
    sections = []  # list of {'label': str|None, 'subtotal': float, 'start': int}
    current_label = None
    current_subtotal = 0
    current_start = 0
    for idx, item in enumerate(items):
        if item.category == 'divider':
            if idx > 0:
                sections.append({'label': current_label, 'subtotal': current_subtotal,
                                 'start': current_start, 'end': idx})
            current_label = item.notes or 'Abschnitt'
            current_subtotal = 0
            current_start = idx
        else:
            current_subtotal += item.cost
    if items:
        sections.append({'label': current_label, 'subtotal': current_subtotal,
                         'start': current_start, 'end': len(items)})

    # ---------- Vehicle capacity info per item ----------------------------
    wache_state = {}
    for w in planner_wachen:
        if w.kind == 'real':
            base_max = 0
            for l in w.wache_type.levels:
                if l.level_number == w.current_level:
                    base_max = l.max_vehicles
                    break
            wache_state[w.ref] = {
                'count': len(w.vehicles),
                'max': w.max_vehicles,
                '_base_max': base_max,
                'level': w.current_level,
                'name': w.name,
                'wache_type': w.wache_type,
            }
        else:
            wache_state[w.ref] = {
                'count': 0,
                'max': w.max_vehicles,
                '_base_max': w.max_vehicles,
                'level': 1,
                'name': w.name,
                'wache_type': w.wache_type,
            }

    for item in items:
        if item.category != 'vehicle' or not item.vehicle_type_id:
            continue
        ref = f'w:{item.vehicle_wache_id}' if item.vehicle_wache_id else _planned_wache_ref_from_item(item)
        if not ref:
            continue
        st = wache_state.get(ref)
        if st:
            st['count'] += 1

    capacity_info = []  # parallel to items: dict or None
    for item in items:
        info = None
        if item.category == 'wache_buy' and item.wache_type_id:
            wt = item.wache_type
            first_level = min(wt.levels, key=lambda l: l.level_number) if wt and wt.levels else None
            max_v = first_level.max_vehicles if first_level else 0
            key = f'p:{item.id}'
            wache_state[key] = {
                'count': 0, 'max': max_v, '_base_max': max_v, 'level': 1,
                'name': item.wache_name, 'wache_type': wt,
            }
            info = {'current': 0, 'max': max_v}

        elif item.category == 'wache_upgrade' and item.target_wache_id and item.target_level:
            key = f'w:{item.target_wache_id}'
            st = wache_state.get(key)
            if st:
                wache_type = st.get('wache_type') or (item.target_wache.wache_type if item.target_wache else None)
                new_base = 0
                if wache_type:
                    for l in wache_type.levels:
                        if l.level_number == item.target_level:
                            new_base = l.max_vehicles
                            break
                old_base = st.get('_base_max', st['max'])
                bonus_slots = st['max'] - old_base
                st['_base_max'] = new_base
                st['max'] = new_base + bonus_slots
                st['level'] = item.target_level
                info = {'current': st['count'], 'max': st['max']}
        elif item.category == 'wache_upgrade' and item.target_wache_plan_item_id and item.target_level:
            key = f'p:{item.target_wache_plan_item_id}'
            st = wache_state.get(key)
            if st:
                wache_type = st.get('wache_type') or (item.target_wache.wache_type if item.target_wache else None)
                new_base = 0
                if wache_type:
                    for l in wache_type.levels:
                        if l.level_number == item.target_level:
                            new_base = l.max_vehicles
                            break
                old_base = st.get('_base_max', st['max'])
                bonus_slots = st['max'] - old_base
                st['_base_max'] = new_base
                st['max'] = new_base + bonus_slots
                st['level'] = item.target_level
                info = {'current': st['count'], 'max': st['max']}

        elif item.category == 'wache_extension' and item.extension_wache_id and item.wache_upgrade:
            key = f'w:{item.extension_wache_id}'
            st = wache_state.get(key)
            if st:
                st['max'] += item.wache_upgrade.extra_slots
                info = {'current': st['count'], 'max': st['max']}
        elif item.category == 'wache_extension' and item.extension_wache_plan_item_id and item.wache_upgrade:
            key = f'p:{item.extension_wache_plan_item_id}'
            st = wache_state.get(key)
            if st:
                st['max'] += item.wache_upgrade.extra_slots
                info = {'current': st['count'], 'max': st['max']}

        elif item.category == 'vehicle' and item.vehicle_wache_id:
            key = f'w:{item.vehicle_wache_id}'
            st = wache_state.get(key)
            if st:
                st['count'] += 1
                info = {'current': st['count'], 'max': st['max']}
        elif item.category == 'vehicle' and item.vehicle_wache_plan_item_id:
            key = f'p:{item.vehicle_wache_plan_item_id}'
            st = wache_state.get(key)
            if st:
                st['count'] += 1
                info = {'current': st['count'], 'max': st['max']}

        capacity_info.append(info)

    return render_template('planner.html', active_tab='planner',
                           items=items, done_items=done_items, running=running,
                           sections=sections,
                           vehicle_types=vehicle_types, wache_types=wache_types,
                           my_wachen=my_wachen, planner_wachen=planner_wachen,
                           all_modules=all_modules,
                           capacity_info=capacity_info,
                           org_types=org_types, locations=locations,
                           naming_presets=naming_presets,
                           wache_veh_counts_json=wache_veh_counts,
                           org_wache_next_json=org_wache_next)


# ---------- Add: Wache kaufen ---------------------------------------------

@planner_bp.route('/planner/add/wache_buy', methods=['POST'])
def add_wache_buy():
    wache_type_id = request.form.get('wache_type_id', type=int)
    wache_name = request.form.get('wache_name', '').strip()
    notes = request.form.get('notes', '').strip() or None

    if not wache_type_id or not wache_name:
        flash('Name und Wachen-Typ sind erforderlich.', 'danger')
        return redirect(url_for('planner.index'))


    max_prio = _next_priority()
    item = PlanItem(
        category='wache_buy',
        wache_name=wache_name,
        wache_type_id=wache_type_id,
        priority=max_prio + 1,
        notes=notes,
    )
    assign_active_savegame(item)
    db.session.add(item)
    db.session.commit()
    flash(f'Wache „{wache_name}" zum Planer hinzugefügt.', 'success')
    return redirect(url_for('planner.index'))


# ---------- Add: Wache ausbauen -------------------------------------------

@planner_bp.route('/planner/add/wache_upgrade', methods=['POST'])
def add_wache_upgrade():
    target_wache_ref = request.form.get('target_wache_ref', '').strip()
    target_level = request.form.get('target_level', type=int)
    notes = request.form.get('notes', '').strip() or None

    target_kind, target_id = _parse_wache_ref(target_wache_ref)

    if not target_kind or not target_id or not target_level:
        flash('Wache und Ziel-Stufe sind erforderlich.', 'danger')
        return redirect(url_for('planner.index'))

    target_wache = None
    target_plan_item = None
    if target_kind == 'w':
        target_wache = scoped(MyWache).filter_by(id=target_id).first()
    elif target_kind == 'p':
        target_plan_item = scoped(PlanItem).filter_by(id=target_id).first()
        if not target_plan_item or target_plan_item.category != 'wache_buy':
            target_plan_item = None

    if not target_wache and not target_plan_item:
        flash('Wache konnte nicht gefunden werden.', 'danger')
        return redirect(url_for('planner.index'))

    max_prio = _next_priority()
    item = PlanItem(
        category='wache_upgrade',
        target_wache_id=target_wache.id if target_wache else None,
        target_wache_plan_item_id=target_plan_item.id if target_plan_item else None,
        target_level=target_level,
        priority=max_prio + 1,
        notes=notes,
    )
    assign_active_savegame(item)
    db.session.add(item)
    db.session.commit()
    flash('Wachen-Ausbau zum Planer hinzugefügt.', 'success')
    return redirect(url_for('planner.index'))


# ---------- Add: Wache erweitern ------------------------------------------

@planner_bp.route('/planner/add/wache_extension', methods=['POST'])
def add_wache_extension():
    extension_wache_ref = request.form.get('extension_wache_ref', '').strip()
    wache_upgrade_id = request.form.get('wache_upgrade_id', type=int)
    notes = request.form.get('notes', '').strip() or None

    extension_kind, extension_id = _parse_wache_ref(extension_wache_ref)

    if not extension_kind or not extension_id or not wache_upgrade_id:
        flash('Wache und Erweiterung sind erforderlich.', 'danger')
        return redirect(url_for('planner.index'))

    extension_wache = None
    extension_plan_item = None
    if extension_kind == 'w':
        extension_wache = scoped(MyWache).filter_by(id=extension_id).first()
    elif extension_kind == 'p':
        extension_plan_item = scoped(PlanItem).filter_by(id=extension_id).first()
        if not extension_plan_item or extension_plan_item.category != 'wache_buy':
            extension_plan_item = None

    if not extension_wache and not extension_plan_item:
        flash('Wache konnte nicht gefunden werden.', 'danger')
        return redirect(url_for('planner.index'))

    max_prio = _next_priority()
    item = PlanItem(
        category='wache_extension',
        extension_wache_id=extension_wache.id if extension_wache else None,
        extension_wache_plan_item_id=extension_plan_item.id if extension_plan_item else None,
        wache_upgrade_id=wache_upgrade_id,
        priority=max_prio + 1,
        notes=notes,
    )
    assign_active_savegame(item)
    db.session.add(item)
    db.session.commit()
    flash('Wachen-Erweiterung zum Planer hinzugefügt.', 'success')
    return redirect(url_for('planner.index'))


# ---------- Add: Fahrzeug kaufen ------------------------------------------

@planner_bp.route('/planner/add/vehicle', methods=['POST'])
def add_vehicle():
    vehicle_type_id = request.form.get('vehicle_type_id', type=int)
    vehicle_nickname = request.form.get('vehicle_nickname', '').strip() or None
    vehicle_wache_ref = request.form.get('vehicle_wache_ref', '').strip()
    quantity = request.form.get('quantity', 1, type=int) or 1
    module_ids = request.form.getlist('module_ids', type=int)
    notes = request.form.get('notes', '').strip() or None

    # Guardrails against invalid input and accidental huge bulk inserts.
    quantity = max(1, min(quantity, 100))

    if not vehicle_type_id:
        flash('Fahrzeugtyp ist erforderlich.', 'danger')
        return redirect(url_for('planner.index'))

    vehicle_kind, vehicle_id = _parse_wache_ref(vehicle_wache_ref)
    vehicle_wache = None
    vehicle_plan_item = None
    if vehicle_kind == 'w':
        vehicle_wache = scoped(MyWache).filter_by(id=vehicle_id).first()
    elif vehicle_kind == 'p':
        vehicle_plan_item = scoped(PlanItem).filter_by(id=vehicle_id).first()
        if not vehicle_plan_item or vehicle_plan_item.category != 'wache_buy':
            vehicle_plan_item = None

    max_prio = _next_priority()

    # Build a nickname sequence for bulk create when a base nickname is present.
    nicknames = [None] * quantity
    if vehicle_nickname:
        m = re.match(r'^(.*?)(\d+)$', vehicle_nickname)
        if quantity == 1:
            nicknames = [vehicle_nickname]
        elif m:
            prefix = m.group(1)
            start_num = int(m.group(2))
            width = len(m.group(2))
            nicknames = [f'{prefix}{start_num + i:0{width}d}' for i in range(quantity)]
        else:
            nicknames = [vehicle_nickname if i == 0 else f'{vehicle_nickname}-{i + 1}' for i in range(quantity)]

    selected_mods = []
    if module_ids:
        selected_mods = scoped(VehicleModule).filter(VehicleModule.id.in_(module_ids)).all()
    else:
        vt = scoped(VehicleType).filter_by(id=vehicle_type_id).first()
        if vt and vt.standard_modules:
            selected_mods = list(vt.standard_modules)

    for i in range(quantity):
        item = PlanItem(
            category='vehicle',
            vehicle_type_id=vehicle_type_id,
            vehicle_nickname=nicknames[i],
            vehicle_wache_id=vehicle_wache.id if vehicle_wache else None,
            vehicle_wache_plan_item_id=vehicle_plan_item.id if vehicle_plan_item else None,
            priority=max_prio + 1 + i,
            notes=notes,
        )
        assign_active_savegame(item)
        if selected_mods:
            item.selected_modules = list(selected_mods)
        db.session.add(item)

    db.session.commit()
    if quantity == 1:
        flash('Fahrzeug zum Planer hinzugefügt.', 'success')
    else:
        flash(f'{quantity} Fahrzeuge zum Planer hinzugefügt.', 'success')
    return redirect(url_for('planner.index'))


# ---------- Actions -------------------------------------------------------

@planner_bp.route('/planner/<int:pid>/done', methods=['POST'])
def mark_done(pid):
    item = scoped_get_or_404(PlanItem, pid)

    # Materialize into fleet
    if item.category == 'wache_buy' and item.wache_type_id and item.wache_name:
        wache_type = scoped(WacheType).filter_by(id=item.wache_type_id).first()
        initial_level = min((l.level_number for l in wache_type.levels), default=0) if wache_type else 0
        if item.created_wache:
            w = item.created_wache
            w.name = item.wache_name
            w.wache_type_id = item.wache_type_id
            w.current_level = max(w.current_level, initial_level)
        else:
            w = MyWache(name=item.wache_name, wache_type_id=item.wache_type_id, current_level=initial_level)
            assign_active_savegame(w)
            db.session.add(w)
            item.created_wache = w
        item.done = True
    elif item.category == 'wache_upgrade' and item.target_level:
        target_wache = item.target_wache or _resolve_active_wache(f'p:{item.target_wache_plan_item_id}' if item.target_wache_plan_item_id else '')
        if not target_wache:
            flash('Die Ziel-Wache ist noch nicht verfügbar.', 'danger')
            return redirect(url_for('planner.index'))
        target_wache.current_level = item.target_level
        item.done = True
    elif item.category == 'wache_extension' and item.extension_wache and item.wache_upgrade:
        item.done = True
        if item.wache_upgrade not in item.extension_wache.installed_upgrades:
            item.extension_wache.installed_upgrades.append(item.wache_upgrade)
    elif item.category == 'wache_extension' and item.extension_wache_plan_item_id and item.wache_upgrade:
        target_wache = _resolve_active_wache(f'p:{item.extension_wache_plan_item_id}')
        if not target_wache:
            flash('Die Ziel-Wache ist noch nicht verfügbar.', 'danger')
            return redirect(url_for('planner.index'))
        item.done = True
        if item.wache_upgrade not in target_wache.installed_upgrades:
            target_wache.installed_upgrades.append(item.wache_upgrade)
    elif item.category == 'vehicle' and item.vehicle_type_id:
        target_wache = item.vehicle_wache or _resolve_active_wache(f'p:{item.vehicle_wache_plan_item_id}' if item.vehicle_wache_plan_item_id else '')
        if not target_wache:
            flash('Die Ziel-Wache ist noch nicht verfügbar.', 'danger')
            return redirect(url_for('planner.index'))
        v = MyVehicle(my_wache_id=target_wache.id, vehicle_type_id=item.vehicle_type_id,
                      nickname=item.vehicle_nickname)
        assign_active_savegame(v)
        db.session.add(v)
        db.session.flush()
        if item.selected_modules:
            v.installed_modules = list(item.selected_modules)
        elif item.vehicle_type and item.vehicle_type.standard_modules:
            v.installed_modules = list(item.vehicle_type.standard_modules)
        item.done = True
    else:
        item.done = True

    db.session.commit()
    flash(f'„{item.description}" erledigt und in den Fuhrpark übernommen.', 'success')
    return redirect(url_for('planner.index'))


@planner_bp.route('/planner/<int:pid>/undone', methods=['POST'])
def mark_undone(pid):
    item = scoped_get_or_404(PlanItem, pid)
    item.done = False
    max_prio = _next_priority(done_state=False)
    item.priority = max_prio + 1
    db.session.commit()
    flash(f'„{item.description}" wieder in die Planung aufgenommen.', 'success')
    return redirect(url_for('planner.index'))


@planner_bp.route('/planner/<int:pid>/delete', methods=['POST'])
def delete_item(pid):
    item = scoped_get_or_404(PlanItem, pid)
    if item.category == 'wache_buy':
        dependents = scoped(PlanItem).filter(
            (PlanItem.target_wache_plan_item_id == item.id)
            | (PlanItem.extension_wache_plan_item_id == item.id)
            | (PlanItem.vehicle_wache_plan_item_id == item.id)
        ).all()
        for dep in dependents:
            db.session.delete(dep)
    db.session.delete(item)
    db.session.commit()
    flash('Eintrag gelöscht.', 'success')
    return redirect(url_for('planner.index'))


@planner_bp.route('/planner/<int:pid>/set_nickname', methods=['POST'])
def set_nickname(pid):
    item = scoped_get_or_404(PlanItem, pid)
    if item.category != 'vehicle':
        flash('Rufname kann nur bei Fahrzeug-Einträgen gesetzt werden.', 'danger')
        return redirect(url_for('planner.index'))
    item.vehicle_nickname = request.form.get('vehicle_nickname', '').strip() or None
    db.session.commit()
    flash('Rufname aktualisiert.', 'success')
    return redirect(url_for('planner.index'))


# ---------- Dividers ------------------------------------------------------

@planner_bp.route('/planner/add/divider', methods=['POST'])
def add_divider():
    label = request.form.get('divider_label', '').strip() or 'Abschnitt'
    max_prio = _next_priority()
    item = PlanItem(category='divider', priority=max_prio + 1, notes=label)
    assign_active_savegame(item)
    db.session.add(item)
    db.session.commit()
    flash(f'Abschnitt „{label}" hinzugefügt.', 'success')
    return redirect(url_for('planner.index'))


@planner_bp.route('/planner/<int:pid>/rename_divider', methods=['POST'])
def rename_divider(pid):
    item = scoped_get_or_404(PlanItem, pid)
    if item.category != 'divider':
        return redirect(url_for('planner.index'))
    label = request.form.get('divider_label', '').strip()
    if label:
        item.notes = label
        db.session.commit()
    return redirect(url_for('planner.index'))


@planner_bp.route('/planner/reorder', methods=['POST'])
def reorder():
    order = request.get_json()
    if not order or not isinstance(order, list):
        return jsonify(ok=False), 400
    for idx, item_id in enumerate(order):
        item = scoped(PlanItem).filter_by(id=int(item_id)).first()
        if item:
            item.priority = idx
    db.session.commit()
    return jsonify(ok=True)


# ---------- AJAX helpers --------------------------------------------------

@planner_bp.route('/planner/api/wache_levels/<string:wache_ref>')
def wache_levels(wache_ref):
    """Return available upgrade levels for a wache (above current level)."""
    entry = _resolve_wache_entry(wache_ref)
    if not entry:
        return jsonify(levels=[])
    levels = [{'number': l.level_number,
               'name': l.name or f'Stufe {l.level_number}',
               'cost': l.cost,
               'max_vehicles': l.max_vehicles}
              for l in entry.wache_type.levels if l.level_number > entry.current_level]
    return jsonify(levels=levels, current_level=entry.current_level,
                   current_vehicles=len(entry.vehicles))


@planner_bp.route('/planner/api/vehicle_modules/<int:vtid>')
def vehicle_modules(vtid):
    """Return modules assigned to a vehicle type."""
    vt = scoped_get_or_404(VehicleType, vtid)
    standard_ids = {m.id for m in vt.standard_modules}
    mods = [
        {
            'id': m.id,
            'name': m.name,
            'price': m.price,
            'is_standard': m.id in standard_ids,
        }
        for m in vt.modules
    ]
    return jsonify(modules=mods, base_price=vt.base_price)


@planner_bp.route('/planner/api/wache_upgrades/<string:wache_ref>')
def wache_upgrades_api(wache_ref):
    """Return available upgrades for a wache (not yet installed)."""
    entry = _resolve_wache_entry(wache_ref)
    if not entry:
        return jsonify(upgrades=[])
    if entry.kind == 'real':
        wache = scoped_get_or_404(MyWache, entry.id)
        installed_ids = {u.id for u in wache.installed_upgrades}
        upgrades = [{'id': u.id, 'name': u.name, 'cost': u.cost, 'extra_slots': u.extra_slots}
                    for u in wache.wache_type.upgrades if u.id not in installed_ids]
        return jsonify(upgrades=upgrades, wache_name=wache.name)
    upgrades = [{'id': u.id, 'name': u.name, 'cost': u.cost, 'extra_slots': u.extra_slots}
                for u in entry.wache_type.upgrades]
    return jsonify(upgrades=upgrades, wache_name=entry.name)
