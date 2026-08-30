from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.models import Savegame, SavegameMembership, User


auth_bp = Blueprint('auth', __name__)


def _safe_next_url(candidate):
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return None
    if not candidate.startswith('/'):
        return None
    return candidate


def _current_owner_membership(savegame_id):
    return SavegameMembership.query.filter_by(
        user_id=current_user.id,
        savegame_id=savegame_id,
        role='owner',
    ).first()


@auth_bp.route('/auth/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('vehicles.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash('Ungültiger Benutzername oder Passwort.', 'danger')
            return render_template('auth_login.html', show_register=(User.query.count() == 0))

        login_user(user)
        first_membership = SavegameMembership.query.filter_by(user_id=user.id).order_by(SavegameMembership.id).first()
        if first_membership:
            session['active_savegame_id'] = first_membership.savegame_id

        next_url = _safe_next_url(request.args.get('next')) or url_for('vehicles.index')
        return redirect(next_url)

    return render_template('auth_login.html', show_register=(User.query.count() == 0))


@auth_bp.route('/auth/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password_repeat', '')

        if len(username) < 3:
            flash('Benutzername muss mindestens 3 Zeichen haben.', 'danger')
            return render_template('auth_register.html')
        if len(password) < 8:
            flash('Passwort muss mindestens 8 Zeichen haben.', 'danger')
            return render_template('auth_register.html')
        if password != password2:
            flash('Passwörter stimmen nicht überein.', 'danger')
            return render_template('auth_register.html')
        if User.query.filter_by(username=username).first():
            flash('Benutzername ist bereits vergeben.', 'danger')
            return render_template('auth_register.html')

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        savegame = Savegame(name=f'{username} Spielstand', created_by_user_id=user.id)
        db.session.add(savegame)
        db.session.flush()

        db.session.add(SavegameMembership(user_id=user.id, savegame_id=savegame.id, role='owner'))
        db.session.commit()

        login_user(user)
        session['active_savegame_id'] = savegame.id
        flash('Benutzerkonto erstellt.', 'success')
        return redirect(url_for('vehicles.index'))

    return render_template('auth_register.html')


@auth_bp.route('/auth/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    session.pop('active_savegame_id', None)
    return redirect(url_for('auth.login'))


@auth_bp.route('/auth/savegame/switch', methods=['POST'])
@login_required
def switch_savegame():
    savegame_id = request.form.get('savegame_id', type=int)
    membership = SavegameMembership.query.filter_by(user_id=current_user.id, savegame_id=savegame_id).first()
    if not membership:
        flash('Kein Zugriff auf diesen Spielstand.', 'danger')
        return redirect(url_for('vehicles.index'))
    session['active_savegame_id'] = savegame_id
    flash('Spielstand gewechselt.', 'success')
    return redirect(request.referrer or url_for('vehicles.index'))


@auth_bp.route('/auth/savegame/create', methods=['POST'])
@login_required
def create_savegame():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name darf nicht leer sein.', 'danger')
        return redirect(request.referrer or url_for('vehicles.index'))

    sg = Savegame(name=name, created_by_user_id=current_user.id)
    db.session.add(sg)
    db.session.flush()
    db.session.add(SavegameMembership(user_id=current_user.id, savegame_id=sg.id, role='owner'))
    db.session.commit()

    session['active_savegame_id'] = sg.id
    flash(f'Spielstand "{name}" erstellt.', 'success')
    return redirect(request.referrer or url_for('vehicles.index'))


@auth_bp.route('/auth/savegame/member/add', methods=['POST'])
@login_required
def add_savegame_member():
    savegame_id = request.form.get('savegame_id', type=int)
    username = request.form.get('username', '').strip()
    role = request.form.get('role', 'editor').strip().lower()
    if role not in {'editor', 'viewer'}:
        role = 'editor'

    owner_membership = _current_owner_membership(savegame_id)
    if not owner_membership:
        flash('Nur Owner können Benutzer hinzufügen.', 'danger')
        return redirect(request.referrer or url_for('vehicles.index'))

    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Benutzer nicht gefunden.', 'danger')
        return redirect(request.referrer or url_for('vehicles.index'))

    existing = SavegameMembership.query.filter_by(user_id=user.id, savegame_id=savegame_id).first()
    if existing:
        flash('Benutzer ist bereits Mitglied.', 'danger')
        return redirect(request.referrer or url_for('vehicles.index'))

    db.session.add(SavegameMembership(user_id=user.id, savegame_id=savegame_id, role=role))
    db.session.commit()
    flash(f'Benutzer "{username}" hinzugefügt.', 'success')
    return redirect(request.referrer or url_for('vehicles.index'))


@auth_bp.route('/auth/savegame/member/<int:membership_id>/role', methods=['POST'])
@login_required
def update_savegame_member_role(membership_id):
    membership = SavegameMembership.query.get_or_404(membership_id)

    if not _current_owner_membership(membership.savegame_id):
        flash('Nur Owner können Rollen ändern.', 'danger')
        return redirect(request.referrer or url_for('vehicles.index'))

    role = request.form.get('role', 'editor').strip().lower()
    if role not in {'owner', 'editor', 'viewer'}:
        role = 'editor'

    if membership.user_id == current_user.id and role != 'owner':
        flash('Du kannst dir selbst die Owner-Rolle nicht entziehen.', 'danger')
        return redirect(request.referrer or url_for('vehicles.index'))

    if membership.role == 'owner' and role != 'owner':
        owner_count = SavegameMembership.query.filter_by(
            savegame_id=membership.savegame_id,
            role='owner',
        ).count()
        if owner_count <= 1:
            flash('Mindestens ein Owner muss im Spielstand bleiben.', 'danger')
            return redirect(request.referrer or url_for('vehicles.index'))

    membership.role = role
    db.session.commit()
    flash('Rolle aktualisiert.', 'success')
    return redirect(request.referrer or url_for('vehicles.index'))


@auth_bp.route('/auth/savegame/member/<int:membership_id>/remove', methods=['POST'])
@login_required
def remove_savegame_member(membership_id):
    membership = SavegameMembership.query.get_or_404(membership_id)

    if not _current_owner_membership(membership.savegame_id):
        flash('Nur Owner können Mitglieder entfernen.', 'danger')
        return redirect(request.referrer or url_for('vehicles.index'))

    if membership.user_id == current_user.id:
        flash('Du kannst dich nicht selbst entfernen.', 'danger')
        return redirect(request.referrer or url_for('vehicles.index'))

    if membership.role == 'owner':
        owner_count = SavegameMembership.query.filter_by(
            savegame_id=membership.savegame_id,
            role='owner',
        ).count()
        if owner_count <= 1:
            flash('Der letzte Owner kann nicht entfernt werden.', 'danger')
            return redirect(request.referrer or url_for('vehicles.index'))

    db.session.delete(membership)
    db.session.commit()
    flash('Mitglied entfernt.', 'success')
    return redirect(request.referrer or url_for('vehicles.index'))
