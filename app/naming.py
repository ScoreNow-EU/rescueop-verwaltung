import re
from datetime import datetime


DEFAULT_NAMING_TEMPLATE = '{ORG} {LOCATION}/{VEHICLE}/{NUMBER2}'


def _pad_number(raw, width):
    try:
        num = int(raw)
    except (TypeError, ValueError):
        return ''
    if num < 0:
        return ''
    return str(num).zfill(width)


def _compact_token(text):
    return re.sub(r'[^A-Za-z0-9]', '', (text or '')).upper()


def _short_token(text):
    parts = re.findall(r'[A-Za-z0-9]+', text or '')
    if len(parts) > 1:
        return ''.join(p[0].upper() for p in parts if p)
    return _compact_token(text)


def _module_code(name):
    txt = (name or '').strip()
    if not txt:
        return ''
    compact = re.sub(r'\s+', '', txt).upper()
    if '-' in compact or '/' in compact:
        return compact
    parts = re.findall(r'[A-Za-z0-9]+', txt)
    if len(parts) > 1:
        return ''.join(p[0].upper() for p in parts if p)
    return compact


def _cleanup_result(value):
    result = re.sub(r'\s{2,}', ' ', value or '').strip()
    result = result.replace('//', '/').replace('--', '-')
    return re.sub(r'^[-/\s]+|[-/\s]+$', '', result)


def render_vehicle_nickname(
    template,
    *,
    org_short='',
    org_full='',
    location_short='',
    location_full='',
    no_location=False,
    vehicle_name='',
    vehicle_short='',
    number=1,
    block1='',
    block2='',
    block3='',
    module_names=None,
    wache_name='',
    wache_type='',
    wache_level='',
    now=None,
):
    tpl = (template or DEFAULT_NAMING_TEMPLATE).strip()
    if not tpl:
        tpl = DEFAULT_NAMING_TEMPLATE

    module_names = [m for m in (module_names or []) if m]
    module_codes = [_module_code(m) for m in module_names]
    module_codes = [m for m in module_codes if m]

    dt = now or datetime.now()

    tokens = {
        'ORG': org_full or org_short,
        'ORG-SHORT': org_short or _short_token(org_full),
        'ORG_FULL': org_full or org_short,
        'LOCATION': '' if no_location else (location_full or location_short),
        'LOCATION-SHORT': '' if no_location else (location_short or _compact_token(location_full)),
        'LOCATION_FULL': '' if no_location else (location_full or location_short),
        'VEHICLE': vehicle_name or vehicle_short,
        'VEHICLE-SHORT': vehicle_short or _compact_token(vehicle_name),
        'VEHICLE_NAME': vehicle_name or vehicle_short,
        'NUMBER': str(number or ''),
        'NUMBER2': _pad_number(number, 2),
        'NUMBER3': _pad_number(number, 3),
        'NUMBER4': _pad_number(number, 4),
        'BLOCK1': block1 or '',
        'BLOCK2': block2 or '',
        'BLOCK3': block3 or '',
        'MODULES': '/'.join(module_names),
        'MODULE_CODES': '-'.join(module_codes),
        'MODULE_COUNT': str(len(module_names)),
        'WACHE': wache_name or '',
        'WACHE_TYPE': wache_type or '',
        'WACHE_LEVEL': str(wache_level or ''),
        'YEAR': dt.strftime('%y'),
        'YEAR4': dt.strftime('%Y'),
        'MONTH': dt.strftime('%m'),
        'DAY': dt.strftime('%d'),
    }

    def repl(match):
        key = match.group(1)
        return tokens.get(key, match.group(0)) or ''

    rendered = re.sub(r'\{([A-Z0-9_-]+)\}', repl, tpl)
    return _cleanup_result(rendered)
