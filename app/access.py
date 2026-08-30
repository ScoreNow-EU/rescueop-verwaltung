from flask import abort, session
from flask_login import current_user


def get_active_savegame_id():
    return session.get('active_savegame_id')


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
        sgid = get_active_savegame_id()
        if sgid is None:
            return query.filter(False)
        query = query.filter_by(savegame_id=sgid)
    return query


def scoped_get_or_404(model, item_id):
    item = model.query.get_or_404(item_id)
    if hasattr(item, 'savegame_id'):
        sgid = get_active_savegame_id()
        if sgid is None or item.savegame_id != sgid:
            abort(404)
    return item


def assign_active_savegame(model_instance):
    if hasattr(model_instance, 'savegame_id') and not getattr(model_instance, 'savegame_id', None):
        model_instance.savegame_id = get_active_savegame_id()
