from flask import abort, session
from flask_login import current_user


GLOBAL_CATALOG_MODELS = {
    'VehicleType',
    'VehicleModule',
    'WacheType',
    'WacheLevel',
    'WacheUpgrade',
    'NamingPreset',
}


def get_active_savegame_id():
    return session.get('active_savegame_id')


def get_admin_savegame_id():
    from app.models import Savegame

    admin_savegame = Savegame.query.filter_by(is_admin=True).order_by(Savegame.id).first()
    if admin_savegame:
        return admin_savegame.id
    fallback = Savegame.query.order_by(Savegame.id).first()
    return fallback.id if fallback else None


def is_global_catalog_model(model):
    return getattr(model, '__name__', '') in GLOBAL_CATALOG_MODELS


def active_savegame_is_admin():
    active_id = get_active_savegame_id()
    admin_id = get_admin_savegame_id()
    return bool(active_id and admin_id and active_id == admin_id)


def user_can_access_savegame(savegame_id):
    if not current_user.is_authenticated:
        return False
    return any(m.savegame_id == savegame_id for m in current_user.memberships)


def require_savegame_access(savegame_id):
    if not user_can_access_savegame(savegame_id):
        abort(403)


def scoped(model):
    query = model.query
    if hasattr(model, 'savegame_id'):
        sgid = get_admin_savegame_id() if is_global_catalog_model(model) else get_active_savegame_id()
        if sgid is None:
            return query.filter(False)
        query = query.filter_by(savegame_id=sgid)
    return query


def scoped_get_or_404(model, item_id):
    item = scoped(model).filter_by(id=item_id).first()
    if not item:
        abort(404)
    return item


def assign_active_savegame(model_instance):
    if hasattr(model_instance, 'savegame_id') and not getattr(model_instance, 'savegame_id', None):
        if is_global_catalog_model(model_instance.__class__):
            model_instance.savegame_id = get_admin_savegame_id()
        else:
            model_instance.savegame_id = get_active_savegame_id()
