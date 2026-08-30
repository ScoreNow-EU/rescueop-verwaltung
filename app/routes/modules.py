from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.access import assign_active_savegame, scoped, scoped_get_or_404
from app.models import VehicleModule

modules_bp = Blueprint('modules', __name__)


@modules_bp.route('/modules')
def index():
    modules = scoped(VehicleModule).order_by(VehicleModule.name).all()
    return render_template('modules.html', active_tab='modules', modules=modules)


@modules_bp.route('/modules/add', methods=['POST'])
def add_module():
    name = request.form.get('name', '').strip()
    price = request.form.get('price', 0, type=float)
    if not name:
        flash('Name darf nicht leer sein.', 'danger')
        return redirect(url_for('modules.index'))
    mod = VehicleModule(name=name, price=price)
    assign_active_savegame(mod)
    db.session.add(mod)
    db.session.commit()
    flash(f'Modul „{name}" erstellt.', 'success')
    return redirect(url_for('modules.index'))


@modules_bp.route('/modules/<int:mid>/edit', methods=['POST'])
def edit_module(mid):
    mod = scoped_get_or_404(VehicleModule, mid)
    mod.name = request.form.get('name', mod.name).strip()
    mod.price = request.form.get('price', mod.price, type=float)
    db.session.commit()
    flash(f'Modul „{mod.name}" aktualisiert.', 'success')
    return redirect(url_for('modules.index'))


@modules_bp.route('/modules/<int:mid>/delete', methods=['POST'])
def delete_module(mid):
    mod = scoped_get_or_404(VehicleModule, mid)
    name = mod.name
    db.session.delete(mod)
    db.session.commit()
    flash(f'Modul „{name}" gelöscht.', 'success')
    return redirect(url_for('modules.index'))
