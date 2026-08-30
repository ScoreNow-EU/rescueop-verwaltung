import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from app import db, ASSETS_DIR
from app.access import assign_active_savegame, scoped, scoped_get_or_404
from app.models import VehicleType, VehicleModule

vehicles_bp = Blueprint('vehicles', __name__)

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}


def _allowed(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def _existing_images():
    """List image files already in assets/vehicles/."""
    folder = os.path.join(ASSETS_DIR, 'vehicles')
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder)
                  if os.path.isfile(os.path.join(folder, f)) and _allowed(f))


# ---------- Vehicle Types -------------------------------------------------

@vehicles_bp.route('/')
@vehicles_bp.route('/vehicles')
def index():
    types = scoped(VehicleType).order_by(VehicleType.is_standard.desc(), VehicleType.name).all()
    all_modules = scoped(VehicleModule).order_by(VehicleModule.name).all()
    return render_template('vehicles.html', active_tab='vehicles',
                           vehicle_types=types, existing_images=_existing_images(),
                           all_modules=all_modules)


@vehicles_bp.route('/vehicles/add', methods=['POST'])
def add_type():
    name = request.form.get('name', '').strip()
    price = request.form.get('base_price', 0, type=float)
    maintenance_cost = request.form.get('maintenance_cost', 0, type=float)
    is_standard = request.form.get('is_standard') == 'on'
    if not name:
        flash('Name darf nicht leer sein.', 'danger')
        return redirect(url_for('vehicles.index'))

    image = None
    # Option 1: choose existing image
    existing = request.form.get('existing_image', '').strip()
    if existing and existing in _existing_images():
        image = existing
    # Option 2: upload new image
    file = request.files.get('image_upload')
    if file and file.filename and _allowed(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(ASSETS_DIR, 'vehicles', filename))
        image = filename

    vt = VehicleType(
        name=name,
        base_price=price,
        maintenance_cost=maintenance_cost,
        image=image,
        is_standard=is_standard,
    )
    assign_active_savegame(vt)
    db.session.add(vt)
    db.session.commit()
    flash(f'Fahrzeugtyp „{name}" erstellt.', 'success')
    return redirect(url_for('vehicles.index'))


@vehicles_bp.route('/vehicles/<int:vid>/edit', methods=['POST'])
def edit_type(vid):
    vt = scoped_get_or_404(VehicleType, vid)
    vt.name = request.form.get('name', vt.name).strip()
    vt.base_price = request.form.get('base_price', vt.base_price, type=float)
    vt.maintenance_cost = request.form.get('maintenance_cost', vt.maintenance_cost, type=float)
    vt.is_standard = request.form.get('is_standard') == 'on'

    existing = request.form.get('existing_image', '').strip()
    if existing and existing in _existing_images():
        vt.image = existing
    file = request.files.get('image_upload')
    if file and file.filename and _allowed(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(ASSETS_DIR, 'vehicles', filename))
        vt.image = filename

    db.session.commit()
    flash(f'Fahrzeugtyp „{vt.name}" aktualisiert.', 'success')
    return redirect(url_for('vehicles.index'))


@vehicles_bp.route('/vehicles/<int:vid>/delete', methods=['POST'])
def delete_type(vid):
    vt = scoped_get_or_404(VehicleType, vid)
    name = vt.name
    db.session.delete(vt)
    db.session.commit()
    flash(f'Fahrzeugtyp „{name}" gelöscht.', 'success')
    return redirect(url_for('vehicles.index'))


# ---------- Module assignment (checkboxes) --------------------------------

@vehicles_bp.route('/vehicles/<int:vid>/modules', methods=['POST'])
def save_modules(vid):
    vt = scoped_get_or_404(VehicleType, vid)
    selected_ids = request.form.getlist('module_ids', type=int)
    selected_modules = scoped(VehicleModule).filter(VehicleModule.id.in_(selected_ids)).all() if selected_ids else []
    vt.modules = selected_modules
    db.session.commit()
    flash(f'Module für „{vt.name}" aktualisiert.', 'success')
    return redirect(url_for('vehicles.index'))
