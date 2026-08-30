import os

from flask import Flask, flash, redirect, request, session, url_for
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
login_manager = LoginManager()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')


@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))


def create_app():
    app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'app', 'static'))

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(ASSETS_DIR, 'vehicles'), exist_ok=True)
    os.makedirs(os.path.join(ASSETS_DIR, 'wachen'), exist_ok=True)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'CHANGE-ME-IN-PRODUCTION')
    database_url = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(DATA_DIR, 'resqop.db')
    )
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif database_url.startswith('postgresql://') and not database_url.startswith('postgresql+psycopg://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    from flask import send_from_directory

    @app.route('/assets/<path:filename>')
    def serve_asset(filename):
        return send_from_directory(ASSETS_DIR, filename)

    @app.before_request
    def enforce_login_and_savegame():
        endpoint = request.endpoint or ''
        if endpoint.startswith('auth.') or endpoint in {'static', 'serve_asset'}:
            return None
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.path))
        _ensure_active_savegame()
        membership = _active_membership()
        if (
            request.method not in {'GET', 'HEAD', 'OPTIONS'}
            and membership
            and membership.role == 'viewer'
        ):
            flash('Dieser Spielstand ist für deinen Benutzer schreibgeschützt.', 'danger')
            return redirect(url_for('vehicles.index'))
        return None

    @app.context_processor
    def inject_nav_context():
        if not current_user.is_authenticated:
            return {
                'nav_maintenance_total': 0,
                'current_savegame': None,
                'user_savegames': [],
                'current_membership_role': None,
                'current_savegame_members': [],
            }

        from app.access import get_active_savegame_id
        from app.models import MyWache, MyVehicle, Savegame

        sgid = get_active_savegame_id()
        current_savegame = Savegame.query.get(sgid) if sgid else None
        wachen = MyWache.query.filter_by(savegame_id=sgid).all() if sgid else []
        vehicles = MyVehicle.query.filter_by(savegame_id=sgid).all() if sgid else []
        total_wachen_maintenance = sum((w.maintenance_cost or 0) for w in wachen)
        total_vehicle_maintenance = sum((v.maintenance_cost or 0) for v in vehicles)
        savegames = [m.savegame for m in current_user.memberships if m.savegame]
        membership = _active_membership()
        savegame_members = []
        if current_savegame:
            savegame_members = sorted(
                current_savegame.memberships,
                key=lambda m: ((m.user.username if m.user else '').lower(), m.id),
            )

        return {
            'nav_maintenance_total': total_wachen_maintenance + total_vehicle_maintenance,
            'current_savegame': current_savegame,
            'user_savegames': savegames,
            'current_membership_role': membership.role if membership else None,
            'current_savegame_members': savegame_members,
        }

    from app.routes.auth import auth_bp
    from app.routes.vehicles import vehicles_bp
    from app.routes.modules import modules_bp
    from app.routes.wachen import wachen_bp
    from app.routes.fleet import fleet_bp
    from app.routes.planner import planner_bp
    from app.routes.stats import stats_bp
    from app.routes.standards import standards_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(vehicles_bp)
    app.register_blueprint(modules_bp)
    app.register_blueprint(wachen_bp)
    app.register_blueprint(fleet_bp)
    app.register_blueprint(planner_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(standards_bp)

    with app.app_context():
        from app import models  # noqa: F401

        db.create_all()
        _migrate_modules_if_needed(db)
        _migrate_planner_if_needed(db)
        _migrate_max_vehicles_if_needed(db)
        _migrate_wache_extensions_if_needed(db)
        _migrate_plan_item_refs_if_needed(db)
        _migrate_standards_if_needed(db)
        _migrate_maintenance_costs_if_needed(db)
        _migrate_wache_initial_levels_if_needed(db)
        _migrate_auth_and_savegames_if_needed(db)
        _bootstrap_auth_defaults()

    return app


def _ensure_active_savegame():
    if not current_user.is_authenticated:
        return
    memberships = [m for m in current_user.memberships if m.savegame]
    if not memberships:
        return
    active = session.get('active_savegame_id')
    if not any(m.savegame_id == active for m in memberships):
        session['active_savegame_id'] = memberships[0].savegame_id


def _active_membership():
    if not current_user.is_authenticated:
        return None
    active = session.get('active_savegame_id')
    for membership in current_user.memberships:
        if membership.savegame_id == active:
            return membership
    return None


def _bootstrap_auth_defaults():
    from app.models import (
        MyVehicle,
        MyWache,
        NamingLocation,
        NamingOrgType,
        PlanItem,
        Savegame,
        SavegameMembership,
        User,
        VehicleModule,
        VehicleType,
        WacheLevel,
        WacheType,
        WacheUpgrade,
    )

    admin_user = User.query.order_by(User.id).first()
    if not admin_user:
        username = os.environ.get('ADMIN_USERNAME', 'admin')
        password = os.environ.get('ADMIN_PASSWORD', 'admin12345')
        admin_user = User(username=username)
        admin_user.set_password(password)
        db.session.add(admin_user)
        db.session.flush()

    default_savegame = Savegame.query.order_by(Savegame.id).first()
    if not default_savegame:
        default_savegame = Savegame(name='Standard', created_by_user_id=admin_user.id)
        db.session.add(default_savegame)
        db.session.flush()

    membership = SavegameMembership.query.filter_by(
        user_id=admin_user.id,
        savegame_id=default_savegame.id,
    ).first()
    if not membership:
        db.session.add(
            SavegameMembership(
                user_id=admin_user.id,
                savegame_id=default_savegame.id,
                role='owner',
            )
        )

    scoped_models = [
        VehicleType,
        VehicleModule,
        WacheType,
        WacheLevel,
        WacheUpgrade,
        NamingOrgType,
        NamingLocation,
        MyWache,
        MyVehicle,
        PlanItem,
    ]

    for model in scoped_models:
        model.query.filter(model.savegame_id.is_(None)).update(
            {model.savegame_id: default_savegame.id},
            synchronize_session=False,
        )

    db.session.commit()


def _migrate_modules_if_needed(database):
    import sqlalchemy

    engine = database.engine
    inspector = sqlalchemy.inspect(engine)

    if 'vehicle_module' not in inspector.get_table_names():
        return
    columns = [c['name'] for c in inspector.get_columns('vehicle_module')]
    if 'vehicle_type_id' not in columns:
        return

    with engine.begin() as conn:
        conn.execute(sqlalchemy.text(
            'CREATE TABLE IF NOT EXISTS vehicle_type_modules ('
            '  vehicle_type_id INTEGER NOT NULL REFERENCES vehicle_type(id),'
            '  vehicle_module_id INTEGER NOT NULL REFERENCES vehicle_module(id),'
            '  PRIMARY KEY (vehicle_type_id, vehicle_module_id))'
        ))
        conn.execute(sqlalchemy.text(
            'INSERT OR IGNORE INTO vehicle_type_modules (vehicle_type_id, vehicle_module_id) '
            'SELECT vehicle_type_id, id FROM vehicle_module WHERE vehicle_type_id IS NOT NULL'
        ))
        conn.execute(sqlalchemy.text(
            'CREATE TABLE vehicle_module_new ('
            '  id INTEGER PRIMARY KEY,'
            '  name VARCHAR(120) NOT NULL,'
            '  price FLOAT NOT NULL DEFAULT 0)'
        ))
        conn.execute(sqlalchemy.text(
            'INSERT INTO vehicle_module_new (id, name, price) '
            'SELECT id, name, price FROM vehicle_module'
        ))
        conn.execute(sqlalchemy.text('DROP TABLE vehicle_module'))
        conn.execute(sqlalchemy.text('ALTER TABLE vehicle_module_new RENAME TO vehicle_module'))


def _migrate_planner_if_needed(database):
    import sqlalchemy

    engine = database.engine
    inspector = sqlalchemy.inspect(engine)

    if 'plan_item' not in inspector.get_table_names():
        return
    columns = [c['name'] for c in inspector.get_columns('plan_item')]
    if 'description' in columns and 'wache_name' not in columns:
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text('DROP TABLE plan_item'))


def _migrate_max_vehicles_if_needed(database):
    import sqlalchemy

    engine = database.engine
    inspector = sqlalchemy.inspect(engine)

    if 'wache_level' not in inspector.get_table_names():
        return
    columns = [c['name'] for c in inspector.get_columns('wache_level')]
    if 'max_vehicles' not in columns:
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text(
                'ALTER TABLE wache_level ADD COLUMN max_vehicles INTEGER NOT NULL DEFAULT 0'
            ))


def _migrate_wache_extensions_if_needed(database):
    import sqlalchemy

    engine = database.engine
    inspector = sqlalchemy.inspect(engine)

    if 'plan_item' not in inspector.get_table_names():
        return
    columns = [c['name'] for c in inspector.get_columns('plan_item')]
    with engine.begin() as conn:
        if 'wache_upgrade_id' not in columns:
            conn.execute(sqlalchemy.text(
                'ALTER TABLE plan_item ADD COLUMN wache_upgrade_id INTEGER REFERENCES wache_upgrade(id)'
            ))
        if 'extension_wache_id' not in columns:
            conn.execute(sqlalchemy.text(
                'ALTER TABLE plan_item ADD COLUMN extension_wache_id INTEGER REFERENCES my_wache(id)'
            ))


def _migrate_plan_item_refs_if_needed(database):
    import sqlalchemy

    engine = database.engine
    inspector = sqlalchemy.inspect(engine)

    if 'plan_item' not in inspector.get_table_names():
        return
    columns = [c['name'] for c in inspector.get_columns('plan_item')]
    with engine.begin() as conn:
        if 'created_wache_id' not in columns:
            conn.execute(sqlalchemy.text(
                'ALTER TABLE plan_item ADD COLUMN created_wache_id INTEGER REFERENCES my_wache(id)'
            ))
        if 'target_wache_plan_item_id' not in columns:
            conn.execute(sqlalchemy.text(
                'ALTER TABLE plan_item ADD COLUMN target_wache_plan_item_id INTEGER REFERENCES plan_item(id)'
            ))
        if 'vehicle_wache_plan_item_id' not in columns:
            conn.execute(sqlalchemy.text(
                'ALTER TABLE plan_item ADD COLUMN vehicle_wache_plan_item_id INTEGER REFERENCES plan_item(id)'
            ))
        if 'extension_wache_plan_item_id' not in columns:
            conn.execute(sqlalchemy.text(
                'ALTER TABLE plan_item ADD COLUMN extension_wache_plan_item_id INTEGER REFERENCES plan_item(id)'
            ))


def _migrate_standards_if_needed(database):
    import sqlalchemy

    engine = database.engine
    inspector = sqlalchemy.inspect(engine)

    with engine.begin() as conn:
        if 'vehicle_type' in inspector.get_table_names():
            cols = [c['name'] for c in inspector.get_columns('vehicle_type')]
            if 'abbreviation' not in cols:
                conn.execute(sqlalchemy.text(
                    'ALTER TABLE vehicle_type ADD COLUMN abbreviation VARCHAR(20)'
                ))

        if 'vehicle_type_standard_modules' not in inspector.get_table_names():
            conn.execute(sqlalchemy.text(
                'CREATE TABLE vehicle_type_standard_modules ('
                '  vehicle_type_id INTEGER NOT NULL REFERENCES vehicle_type(id),'
                '  vehicle_module_id INTEGER NOT NULL REFERENCES vehicle_module(id),'
                '  PRIMARY KEY (vehicle_type_id, vehicle_module_id))'
            ))

        if 'naming_org_type' in inspector.get_table_names():
            cols = [c['name'] for c in inspector.get_columns('naming_org_type')]
            if 'no_location' not in cols:
                conn.execute(sqlalchemy.text(
                    'ALTER TABLE naming_org_type ADD COLUMN no_location BOOLEAN NOT NULL DEFAULT 0'
                ))

        if 'my_wache' in inspector.get_table_names():
            cols = [c['name'] for c in inspector.get_columns('my_wache')]
            if 'naming_org_type_id' not in cols:
                conn.execute(sqlalchemy.text(
                    'ALTER TABLE my_wache ADD COLUMN naming_org_type_id INTEGER REFERENCES naming_org_type(id)'
                ))
            if 'naming_location_id' not in cols:
                conn.execute(sqlalchemy.text(
                    'ALTER TABLE my_wache ADD COLUMN naming_location_id INTEGER REFERENCES naming_location(id)'
                ))


def _migrate_maintenance_costs_if_needed(database):
    import sqlalchemy

    engine = database.engine
    inspector = sqlalchemy.inspect(engine)

    with engine.begin() as conn:
        if 'vehicle_type' in inspector.get_table_names():
            vt_cols = [c['name'] for c in inspector.get_columns('vehicle_type')]
            if 'maintenance_cost' not in vt_cols:
                conn.execute(sqlalchemy.text(
                    'ALTER TABLE vehicle_type ADD COLUMN maintenance_cost FLOAT NOT NULL DEFAULT 0'
                ))

        if 'wache_level' in inspector.get_table_names():
            wl_cols = [c['name'] for c in inspector.get_columns('wache_level')]
            if 'maintenance_cost' not in wl_cols:
                conn.execute(sqlalchemy.text(
                    'ALTER TABLE wache_level ADD COLUMN maintenance_cost FLOAT NOT NULL DEFAULT 0'
                ))

        if 'wache_upgrade' in inspector.get_table_names():
            wu_cols = [c['name'] for c in inspector.get_columns('wache_upgrade')]
            if 'maintenance_cost' not in wu_cols:
                conn.execute(sqlalchemy.text(
                    'ALTER TABLE wache_upgrade ADD COLUMN maintenance_cost FLOAT NOT NULL DEFAULT 0'
                ))


def _migrate_wache_initial_levels_if_needed(database):
    import sqlalchemy

    engine = database.engine
    inspector = sqlalchemy.inspect(engine)

    if 'my_wache' not in inspector.get_table_names() or 'wache_level' not in inspector.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(sqlalchemy.text(
            'UPDATE my_wache '
            'SET current_level = ('
            '  SELECT MIN(wl.level_number) '
            '  FROM wache_level wl '
            '  WHERE wl.wache_type_id = my_wache.wache_type_id'
            ') '
            'WHERE current_level = 0 '
            'AND EXISTS ('
            '  SELECT 1 FROM wache_level wl2 '
            '  WHERE wl2.wache_type_id = my_wache.wache_type_id'
            ')'
        ))


def _migrate_auth_and_savegames_if_needed(database):
    import sqlalchemy

    engine = database.engine
    inspector = sqlalchemy.inspect(engine)
    table_names = inspector.get_table_names()

    with engine.begin() as conn:
        if 'user' not in table_names:
            conn.execute(sqlalchemy.text(
                'CREATE TABLE "user" ('
                'id INTEGER PRIMARY KEY, '
                'username VARCHAR(120) NOT NULL UNIQUE, '
                'password_hash VARCHAR(255) NOT NULL, '
                'created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)'
            ))

        if 'savegame' not in table_names:
            conn.execute(sqlalchemy.text(
                'CREATE TABLE savegame ('
                'id INTEGER PRIMARY KEY, '
                'name VARCHAR(120) NOT NULL, '
                'created_by_user_id INTEGER REFERENCES "user"(id), '
                'created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)'
            ))

        if 'savegame_membership' not in table_names:
            conn.execute(sqlalchemy.text(
                'CREATE TABLE savegame_membership ('
                'id INTEGER PRIMARY KEY, '
                'savegame_id INTEGER NOT NULL REFERENCES savegame(id), '
                'user_id INTEGER NOT NULL REFERENCES "user"(id), '
                'role VARCHAR(20) NOT NULL DEFAULT "editor", '
                'CONSTRAINT uq_savegame_user UNIQUE (savegame_id, user_id))'
            ))

    inspector = sqlalchemy.inspect(engine)
    table_names = inspector.get_table_names()

    scoped_tables = [
        'vehicle_type',
        'vehicle_module',
        'wache_type',
        'wache_level',
        'wache_upgrade',
        'naming_org_type',
        'naming_location',
        'my_wache',
        'my_vehicle',
        'plan_item',
    ]

    with engine.begin() as conn:
        for table in scoped_tables:
            if table not in table_names:
                continue
            cols = [c['name'] for c in inspector.get_columns(table)]
            if 'savegame_id' not in cols:
                conn.execute(sqlalchemy.text(
                    f'ALTER TABLE {table} ADD COLUMN savegame_id INTEGER REFERENCES savegame(id)'
                ))
