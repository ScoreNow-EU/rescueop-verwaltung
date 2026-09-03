"""Overpass API client for fetching rescue-relevant stations from OpenStreetMap.

Used by the admin-only "OSM-Test" tab in Standards to look up fire stations,
EMS stations, police stations, etc. within a radius around a coordinate.

Data source: OpenStreetMap contributors, licensed under the Open Database
License (ODbL). Attribution is required wherever this data is shown.
"""
import http.client
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

OVERPASS_URL = 'https://overpass-api.de/api/interpreter'


class _IPv4HTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection that only ever resolves/connects via IPv4.

    Many VPS providers hand out a host with broken or unrouted IPv6. If a
    domain's DNS also has an AAAA record, Python may pick the IPv6 address
    first and fail with "Network is unreachable" even though IPv4 works
    fine. Forcing AF_INET here sidesteps that without touching global
    socket/DNS behaviour (safe under threaded workers).
    """

    def connect(self):
        last_error = None
        for family, socktype, proto, _canonname, sockaddr in socket.getaddrinfo(
            self.host, self.port, socket.AF_INET, socket.SOCK_STREAM
        ):
            sock = socket.socket(family, socktype, proto)
            try:
                sock.settimeout(self.timeout)
                sock.connect(sockaddr)
            except OSError as exc:
                last_error = exc
                sock.close()
                continue
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
            return
        raise last_error or OSError(f'Keine IPv4-Adresse für {self.host} gefunden.')


class _IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_IPv4HTTPSConnection, req)


_ipv4_opener = urllib.request.build_opener(_IPv4HTTPSHandler())

# Ordered list of rescue-operator-relevant OSM station types.
STATION_TYPES = [
    {'key': 'fire', 'label': 'Feuerwehr', 'tag_key': 'amenity', 'tag_value': 'fire_station'},
    {'key': 'ems', 'label': 'Rettungswache', 'tag_key': 'emergency', 'tag_value': 'ambulance_station'},
    {'key': 'police', 'label': 'Polizei', 'tag_key': 'amenity', 'tag_value': 'police'},
    {'key': 'disaster', 'label': 'THW / Katastrophenschutz', 'tag_key': 'emergency', 'tag_value': 'disaster_response'},
    {'key': 'rescue', 'label': 'Sonstige Rettungsstation', 'tag_key': 'amenity', 'tag_value': 'rescue_station'},
    {'key': 'water', 'label': 'Wasserrettung / DLRG', 'tag_key': 'emergency', 'tag_value': 'water_rescue'},
    {'key': 'mountain', 'label': 'Bergrettung', 'tag_key': 'emergency', 'tag_value': 'mountain_rescue'},
]

_STATION_TYPES_BY_KEY = {t['key']: t for t in STATION_TYPES}


class OverpassError(Exception):
    """Raised when the Overpass API can't be reached or returns bad data."""


def _station_type_for_tags(tags):
    for stype in STATION_TYPES:
        if tags.get(stype['tag_key']) == stype['tag_value']:
            return stype
    return None


def build_overpass_query(lat, lon, radius_m, type_keys=None):
    selected = [t for t in STATION_TYPES if t['key'] in type_keys] if type_keys else list(STATION_TYPES)
    if not selected:
        selected = list(STATION_TYPES)
    lines = ['[out:json][timeout:60];', '(']
    for stype in selected:
        lines.append(f'  nwr["{stype["tag_key"]}"="{stype["tag_value"]}"](around:{radius_m},{lat},{lon});')
    lines.append(');')
    lines.append('out center tags;')
    return '\n'.join(lines)


def query_overpass(query, timeout=40):
    data = urllib.parse.urlencode({'data': query}).encode('utf-8')
    req = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={'User-Agent': 'RescueOperator-Verwaltung/1.0 (Test-Tool)'},
    )
    try:
        with _ipv4_opener.open(req, timeout=timeout) as response:
            payload = response.read().decode('utf-8')
    except (urllib.error.URLError, OSError) as exc:
        raise OverpassError(f'Overpass-API nicht erreichbar: {exc}') from exc
    try:
        return json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise OverpassError('Antwort der Overpass-API konnte nicht gelesen werden.') from exc


def _format_address(tags):
    street = tags.get('addr:street')
    house_number = tags.get('addr:housenumber')
    postcode = tags.get('addr:postcode')
    city = tags.get('addr:city')
    line1 = ' '.join(part for part in [street, house_number] if part).strip()
    line2 = ' '.join(part for part in [postcode, city] if part).strip()
    return ', '.join(part for part in [line1, line2] if part) or None


def parse_overpass_stations(payload):
    stations = []
    for element in payload.get('elements', []):
        tags = element.get('tags') or {}
        stype = _station_type_for_tags(tags)
        if element.get('type') == 'node':
            lat = element.get('lat')
            lon = element.get('lon')
        else:
            center = element.get('center') or {}
            lat = center.get('lat')
            lon = center.get('lon')
        stations.append({
            'osm_type': element.get('type'),
            'osm_id': element.get('id'),
            'type_key': stype['key'] if stype else 'other',
            'type_label': stype['label'] if stype else 'Sonstige',
            'name': tags.get('name') or '(ohne Namen)',
            'operator': tags.get('operator'),
            'address': _format_address(tags),
            'phone': tags.get('phone') or tags.get('contact:phone'),
            'website': tags.get('website') or tags.get('contact:website'),
            'lat': lat,
            'lon': lon,
        })
    stations.sort(key=lambda s: (s['type_label'], (s['name'] or '').lower()))
    return stations


def search_stations(lat, lon, radius_m, type_keys=None):
    query = build_overpass_query(lat, lon, radius_m, type_keys)
    payload = query_overpass(query)
    return parse_overpass_stations(payload)
