from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    memberships = db.relationship('SavegameMembership', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Savegame(db.Model):
    __tablename__ = 'savegame'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    memberships = db.relationship('SavegameMembership', back_populates='savegame', cascade='all, delete-orphan')


class SavegameMembership(db.Model):
    __tablename__ = 'savegame_membership'

    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default='editor')

    savegame = db.relationship('Savegame', back_populates='memberships')
    user = db.relationship('User', back_populates='memberships')

    __table_args__ = (
        db.UniqueConstraint('savegame_id', 'user_id', name='uq_savegame_user'),
    )


# ---------------------------------------------------------------------------
# Catalog: Vehicle Types & Modules
# ---------------------------------------------------------------------------

# Many-to-many: which modules are available for which vehicle types
vehicle_type_modules = db.Table(
    'vehicle_type_modules',
    db.Column('vehicle_type_id', db.Integer, db.ForeignKey('vehicle_type.id'), primary_key=True),
    db.Column('vehicle_module_id', db.Integer, db.ForeignKey('vehicle_module.id'), primary_key=True),
)

vehicle_type_standard_modules = db.Table(
    'vehicle_type_standard_modules',
    db.Column('vehicle_type_id', db.Integer, db.ForeignKey('vehicle_type.id'), primary_key=True),
    db.Column('vehicle_module_id', db.Integer, db.ForeignKey('vehicle_module.id'), primary_key=True),
)


class VehicleType(db.Model):
    __tablename__ = 'vehicle_type'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    abbreviation = db.Column(db.String(20), nullable=True)  # short code for naming, e.g. HLF, RTW
    base_price = db.Column(db.Float, nullable=False, default=0)
    maintenance_cost = db.Column(db.Float, nullable=False, default=0)
    image = db.Column(db.String(255), nullable=True)  # filename in assets/vehicles/
    is_standard = db.Column(db.Boolean, nullable=False, default=False)  # mark as standard vehicle type

    modules = db.relationship('VehicleModule', secondary=vehicle_type_modules,
                              backref='vehicle_types', lazy=True)
    standard_modules = db.relationship('VehicleModule', secondary=vehicle_type_standard_modules,
                                        backref='standard_for_vehicle_types', lazy=True)
    vehicles = db.relationship('MyVehicle', backref='vehicle_type', lazy=True)

    def total_module_cost(self):
        return sum(m.price for m in self.modules)


class VehicleModule(db.Model):
    __tablename__ = 'vehicle_module'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False, default=0)


# ---------------------------------------------------------------------------
# Catalog: Wache Types & Levels
# ---------------------------------------------------------------------------

class WacheType(db.Model):
    __tablename__ = 'wache_type'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    image = db.Column(db.String(255), nullable=True)  # filename in assets/wachen/

    levels = db.relationship('WacheLevel', backref='wache_type', lazy=True,
                             cascade='all, delete-orphan',
                             order_by='WacheLevel.level_number')
    wachen = db.relationship('MyWache', backref='wache_type', lazy=True)


class WacheLevel(db.Model):
    __tablename__ = 'wache_level'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    wache_type_id = db.Column(db.Integer, db.ForeignKey('wache_type.id'), nullable=False)
    level_number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(120), nullable=True)
    cost = db.Column(db.Float, nullable=False, default=0)
    maintenance_cost = db.Column(db.Float, nullable=False, default=0)
    max_vehicles = db.Column(db.Integer, nullable=False, default=0)


class WacheUpgrade(db.Model):
    """Catalog: purchasable upgrades for a wache type (e.g. Anbau, extra bay)."""
    __tablename__ = 'wache_upgrade'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    wache_type_id = db.Column(db.Integer, db.ForeignKey('wache_type.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    cost = db.Column(db.Float, nullable=False, default=0)
    maintenance_cost = db.Column(db.Float, nullable=False, default=0)
    extra_slots = db.Column(db.Integer, nullable=False, default=0)

    wache_type = db.relationship('WacheType', backref=db.backref(
        'upgrades', lazy=True, cascade='all, delete-orphan',
        order_by='WacheUpgrade.name'))


class WacheStandardVehicle(db.Model):
    """Standard vehicle quantities to auto-create for a wache type."""
    __tablename__ = 'wache_standard_vehicle'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    wache_type_id = db.Column(db.Integer, db.ForeignKey('wache_type.id'), nullable=False, index=True)
    vehicle_type_id = db.Column(db.Integer, db.ForeignKey('vehicle_type.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    wache_type = db.relationship('WacheType', backref=db.backref(
        'standard_vehicle_configs', lazy=True, cascade='all, delete-orphan'))
    vehicle_type = db.relationship('VehicleType', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('savegame_id', 'wache_type_id', 'vehicle_type_id',
                            name='uq_wache_std_vehicle_per_type'),
    )


wache_standard_vehicle_item_modules = db.Table(
    'wache_standard_vehicle_item_modules',
    db.Column('wache_standard_vehicle_item_id', db.Integer,
              db.ForeignKey('wache_standard_vehicle_item.id'), primary_key=True),
    db.Column('vehicle_module_id', db.Integer, db.ForeignKey('vehicle_module.id'), primary_key=True),
)


class WacheStandardVehicleItem(db.Model):
    """Planner-like standard vehicles per wache type with custom module selection."""
    __tablename__ = 'wache_standard_vehicle_item'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    wache_type_id = db.Column(db.Integer, db.ForeignKey('wache_type.id'), nullable=False, index=True)
    vehicle_type_id = db.Column(db.Integer, db.ForeignKey('vehicle_type.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    wache_type = db.relationship('WacheType', backref=db.backref(
        'standard_vehicle_items', lazy=True, cascade='all, delete-orphan'))
    vehicle_type = db.relationship('VehicleType', lazy=True)
    selected_modules = db.relationship('VehicleModule', secondary=wache_standard_vehicle_item_modules, lazy=True)


# M2M: which upgrades are installed on a specific MyWache
my_wache_upgrades = db.Table(
    'my_wache_upgrades',
    db.Column('my_wache_id', db.Integer, db.ForeignKey('my_wache.id'), primary_key=True),
    db.Column('wache_upgrade_id', db.Integer, db.ForeignKey('wache_upgrade.id'), primary_key=True),
)


# ---------------------------------------------------------------------------
# Standards: Naming Conventions (defined before MyWache due to FK refs)
# ---------------------------------------------------------------------------

class NamingOrgType(db.Model):
    __tablename__ = 'naming_org_type'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    abbreviation = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    no_location = db.Column(db.Boolean, nullable=False, default=False)
    default_wache_type_id = db.Column(db.Integer, db.ForeignKey('wache_type.id'), nullable=True)

    default_wache_type = db.relationship('WacheType', foreign_keys=[default_wache_type_id])

    __table_args__ = (
        db.UniqueConstraint('savegame_id', 'abbreviation', name='uq_org_abbr_per_savegame'),
    )


class NamingLocation(db.Model):
    __tablename__ = 'naming_location'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    abbreviation = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('savegame_id', 'abbreviation', name='uq_location_abbr_per_savegame'),
    )


class NamingPreset(db.Model):
    __tablename__ = 'naming_preset'

    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    template = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint('savegame_id', 'name', name='uq_naming_preset_name_per_savegame'),
    )


# ---------------------------------------------------------------------------
# Fleet: My Wachen & Vehicles
# ---------------------------------------------------------------------------

class MyWache(db.Model):
    __tablename__ = 'my_wache'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    wache_type_id = db.Column(db.Integer, db.ForeignKey('wache_type.id'), nullable=False)
    current_level = db.Column(db.Integer, nullable=False, default=0)
    naming_org_type_id = db.Column(db.Integer, db.ForeignKey('naming_org_type.id'), nullable=True)
    naming_location_id = db.Column(db.Integer, db.ForeignKey('naming_location.id'), nullable=True)

    vehicles = db.relationship('MyVehicle', backref='wache', lazy=True,
                               cascade='all, delete-orphan')
    installed_upgrades = db.relationship('WacheUpgrade', secondary=my_wache_upgrades, lazy=True)
    org_type = db.relationship('NamingOrgType', foreign_keys=[naming_org_type_id])
    location = db.relationship('NamingLocation', foreign_keys=[naming_location_id])

    @property
    def effective_max_vehicles(self):
        """Max vehicles from current level + bonus from installed upgrades."""
        base = 0
        for l in self.wache_type.levels:
            if l.level_number == self.current_level:
                base = l.max_vehicles
                break
        bonus = sum(u.extra_slots for u in self.installed_upgrades)
        return base + bonus

    @property
    def maintenance_cost(self):
        """Current maintenance based on selected level of this wache."""
        level_maintenance = 0
        for l in self.wache_type.levels:
            if l.level_number == self.current_level:
                level_maintenance = l.maintenance_cost or 0
                break
        upgrade_maintenance = sum((u.maintenance_cost or 0) for u in self.installed_upgrades)
        return level_maintenance + upgrade_maintenance


# Association table for installed modules on a vehicle
my_vehicle_modules = db.Table(
    'my_vehicle_modules',
    db.Column('my_vehicle_id', db.Integer, db.ForeignKey('my_vehicle.id'), primary_key=True),
    db.Column('vehicle_module_id', db.Integer, db.ForeignKey('vehicle_module.id'), primary_key=True),
)


class MyVehicle(db.Model):
    __tablename__ = 'my_vehicle'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    my_wache_id = db.Column(db.Integer, db.ForeignKey('my_wache.id'), nullable=False)
    vehicle_type_id = db.Column(db.Integer, db.ForeignKey('vehicle_type.id'), nullable=False)
    nickname = db.Column(db.String(120), nullable=True)

    installed_modules = db.relationship('VehicleModule', secondary=my_vehicle_modules, lazy=True)

    @property
    def maintenance_cost(self):
        return self.vehicle_type.maintenance_cost if self.vehicle_type else 0


# ---------------------------------------------------------------------------
# Planner: Shopping List
# ---------------------------------------------------------------------------

# M2M: modules selected for a planned vehicle purchase
plan_item_modules = db.Table(
    'plan_item_modules',
    db.Column('plan_item_id', db.Integer, db.ForeignKey('plan_item.id'), primary_key=True),
    db.Column('vehicle_module_id', db.Integer, db.ForeignKey('vehicle_module.id'), primary_key=True),
)


class PlanItem(db.Model):
    __tablename__ = 'plan_item'
    id = db.Column(db.Integer, primary_key=True)
    savegame_id = db.Column(db.Integer, db.ForeignKey('savegame.id'), nullable=False, index=True)
    category = db.Column(db.String(30), nullable=False)
    # 'wache_buy', 'wache_upgrade', 'wache_extension', 'vehicle', 'divider'
    priority = db.Column(db.Integer, nullable=False, default=0)
    done = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text, nullable=True)

    # For wache_buy: new wache name + type
    wache_name = db.Column(db.String(120), nullable=True)
    wache_type_id = db.Column(db.Integer, db.ForeignKey('wache_type.id'), nullable=True)
    wache_org_type_id = db.Column(db.Integer, db.ForeignKey('naming_org_type.id'), nullable=True)
    wache_location_id = db.Column(db.Integer, db.ForeignKey('naming_location.id'), nullable=True)
    created_wache_id = db.Column(db.Integer, db.ForeignKey('my_wache.id'), nullable=True)

    # For wache_upgrade: existing wache + target level
    target_wache_id = db.Column(db.Integer, db.ForeignKey('my_wache.id'), nullable=True)
    target_wache_plan_item_id = db.Column(db.Integer, db.ForeignKey('plan_item.id'), nullable=True)
    target_level = db.Column(db.Integer, nullable=True)

    # For vehicle: type, nickname, assigned wache
    vehicle_type_id = db.Column(db.Integer, db.ForeignKey('vehicle_type.id'), nullable=True)
    vehicle_nickname = db.Column(db.String(120), nullable=True)
    vehicle_wache_id = db.Column(db.Integer, db.ForeignKey('my_wache.id'), nullable=True)
    vehicle_wache_plan_item_id = db.Column(db.Integer, db.ForeignKey('plan_item.id'), nullable=True)

    # For wache_extension: upgrade to buy for a wache
    wache_upgrade_id = db.Column(db.Integer, db.ForeignKey('wache_upgrade.id'), nullable=True)
    extension_wache_id = db.Column(db.Integer, db.ForeignKey('my_wache.id'), nullable=True)
    extension_wache_plan_item_id = db.Column(db.Integer, db.ForeignKey('plan_item.id'), nullable=True)

    # Relationships
    wache_type = db.relationship('WacheType', foreign_keys=[wache_type_id])
    wache_org_type = db.relationship('NamingOrgType', foreign_keys=[wache_org_type_id])
    wache_location = db.relationship('NamingLocation', foreign_keys=[wache_location_id])
    created_wache = db.relationship('MyWache', foreign_keys=[created_wache_id])
    target_wache = db.relationship('MyWache', foreign_keys=[target_wache_id])
    target_wache_plan_item = db.relationship('PlanItem', remote_side=[id], foreign_keys=[target_wache_plan_item_id])
    vehicle_type = db.relationship('VehicleType', foreign_keys=[vehicle_type_id])
    vehicle_wache = db.relationship('MyWache', foreign_keys=[vehicle_wache_id])
    vehicle_wache_plan_item = db.relationship('PlanItem', remote_side=[id], foreign_keys=[vehicle_wache_plan_item_id])
    selected_modules = db.relationship('VehicleModule', secondary=plan_item_modules, lazy=True)
    wache_upgrade = db.relationship('WacheUpgrade', foreign_keys=[wache_upgrade_id])
    extension_wache = db.relationship('MyWache', foreign_keys=[extension_wache_id])
    extension_wache_plan_item = db.relationship('PlanItem', remote_side=[id], foreign_keys=[extension_wache_plan_item_id])

    def _planned_wache_item(self, plan_item_id):
        if not plan_item_id:
            return None
        if self.target_wache_plan_item_id == plan_item_id:
            return self.target_wache_plan_item
        if self.vehicle_wache_plan_item_id == plan_item_id:
            return self.vehicle_wache_plan_item
        if self.extension_wache_plan_item_id == plan_item_id:
            return self.extension_wache_plan_item
        return PlanItem.query.filter_by(id=plan_item_id, savegame_id=self.savegame_id).first()

    def _resolved_wache_name(self, actual_wache, planned_plan_item_id):
        if actual_wache:
            return actual_wache.name
        planned_item = self._planned_wache_item(planned_plan_item_id)
        return planned_item.wache_name if planned_item else '?'

    def _resolved_wache_type(self, actual_wache, planned_plan_item_id):
        if actual_wache:
            return actual_wache.wache_type
        planned_item = self._planned_wache_item(planned_plan_item_id)
        return planned_item.wache_type if planned_item else None

    @property
    def description(self):
        if self.category == 'wache_buy':
            type_name = self.wache_type.name if self.wache_type else '?'
            return f'Neue Wache „{self.wache_name or "?"}" ({type_name})'
        elif self.category == 'wache_upgrade':
            wache_name = self._resolved_wache_name(self.target_wache, self.target_wache_plan_item_id)
            return f'Wache „{wache_name}" → Stufe {self.target_level or "?"}'
        elif self.category == 'wache_extension':
            wache_name = self._resolved_wache_name(self.extension_wache, self.extension_wache_plan_item_id)
            upgrade_name = self.wache_upgrade.name if self.wache_upgrade else '?'
            extra = self.wache_upgrade.extra_slots if self.wache_upgrade else 0
            return f'Wache „{wache_name}": {upgrade_name} (+{extra} Stellplätze)'
        elif self.category == 'vehicle':
            vt_name = self.vehicle_type.name if self.vehicle_type else '?'
            parts = [f'{vt_name}']
            if self.vehicle_nickname:
                parts.append(f'„{self.vehicle_nickname}"')
            if self.selected_modules:
                mod_names = ', '.join(m.name for m in self.selected_modules)
                parts.append(f'+ {mod_names}')
            vehicle_wache_name = self._resolved_wache_name(self.vehicle_wache, self.vehicle_wache_plan_item_id)
            if vehicle_wache_name and vehicle_wache_name != '?':
                parts.append(f'→ {vehicle_wache_name}')
            return ' '.join(parts)
        elif self.category == 'divider':
            return self.notes or 'Abschnitt'
        return '?'

    @property
    def cost(self):
        if self.category == 'wache_buy':
            if self.wache_type and self.wache_type.levels:
                first = min(self.wache_type.levels, key=lambda l: l.level_number)
                return first.cost
            return 0
        elif self.category == 'wache_upgrade':
            target_wache_type = self._resolved_wache_type(self.target_wache, self.target_wache_plan_item_id)
            if target_wache_type and self.target_level:
                for lvl in target_wache_type.levels:
                    if lvl.level_number == self.target_level:
                        return lvl.cost
            return 0
        elif self.category == 'wache_extension':
            return self.wache_upgrade.cost if self.wache_upgrade else 0
        elif self.category == 'vehicle':
            total = self.vehicle_type.base_price if self.vehicle_type else 0
            total += sum(m.price for m in self.selected_modules)
            return total
        return 0
