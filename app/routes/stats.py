from flask import Blueprint, render_template
from app.access import scoped
from app.models import MyWache, MyVehicle

stats_bp = Blueprint('stats', __name__)


@stats_bp.route('/stats')
def index():
    wachen = scoped(MyWache).order_by(MyWache.name).all()
    vehicles = scoped(MyVehicle).all()

    # ---------- Wachen-Wert ----------
    wachen_details = []
    total_wachen_value = 0.0
    total_wachen_maintenance = 0.0
    for w in wachen:
        level_cost = sum(
            lvl.cost for lvl in w.wache_type.levels
            if lvl.level_number <= w.current_level
        )
        upgrade_cost = sum(u.cost for u in w.installed_upgrades)
        wache_total = level_cost + upgrade_cost
        wache_maintenance = w.maintenance_cost
        total_wachen_value += wache_total
        total_wachen_maintenance += wache_maintenance
        wachen_details.append({
            'wache': w,
            'level_cost': level_cost,
            'upgrade_cost': upgrade_cost,
            'maintenance_cost': wache_maintenance,
            'total': wache_total,
        })

    # ---------- Fahrzeug-Wert ----------
    vehicle_details = []
    total_vehicle_value = 0.0
    total_vehicle_maintenance = 0.0
    for v in vehicles:
        base = v.vehicle_type.base_price
        mod_cost = sum(m.price for m in v.installed_modules)
        vtotal = base + mod_cost
        vmaintenance = v.maintenance_cost
        total_vehicle_value += vtotal
        total_vehicle_maintenance += vmaintenance
        vehicle_details.append({
            'vehicle': v,
            'base': base,
            'mod_cost': mod_cost,
            'maintenance_cost': vmaintenance,
            'total': vtotal,
        })

    grand_total = total_wachen_value + total_vehicle_value
    grand_maintenance = total_wachen_maintenance + total_vehicle_maintenance

    return render_template(
        'stats.html',
        active_tab='stats',
        wachen_details=wachen_details,
        vehicle_details=vehicle_details,
        total_wachen_value=total_wachen_value,
        total_vehicle_value=total_vehicle_value,
        grand_total=grand_total,
        total_wachen_maintenance=total_wachen_maintenance,
        total_vehicle_maintenance=total_vehicle_maintenance,
        grand_maintenance=grand_maintenance,
        num_wachen=len(wachen),
        num_vehicles=len(vehicles),
    )
