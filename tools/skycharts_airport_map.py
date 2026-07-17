#!/usr/bin/env python3
"""Download and normalize reusable airport geometry for SkyCharts."""

import argparse
import base64
import csv
import datetime as dt
import io
import json
import math
import pathlib
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
AIRPORTS_CSV = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_CSV = "https://davidmegginson.github.io/ourairports-data/runways.csv"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_ENDPOINTS = (
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    OVERPASS_URL,
)
OVERPASS_REQUEST_TIMEOUT = 20
OVERPASS_FAILURE_COOLDOWN = 180
XPLANE_GATEWAY_AIRPORT_URL = "https://gateway.x-plane.com/apiv1/airport/{ident}"
XPLANE_GATEWAY_SCENERY_URL = "https://gateway.x-plane.com/apiv1/scenery/{scenery_id}"
XPLANE_GATEWAY_SOURCE_URL = "https://gateway.x-plane.com/"
XPLANE_REQUEST_TIMEOUT = 15
XPLANE_FAILURE_COOLDOWN = 120
TRANSIENT_UNAVAILABLE_SECONDS = 15 * 60
MISSING_DATA_SECONDS = 7 * 24 * 60 * 60
MAP_KINDS = (
    "runway",
    "taxiway",
    "taxilane",
    "apron",
    "parking_position",
    "gate",
    "holding_position",
    "terminal",
    "hangar",
)


class AirportMapError(RuntimeError):
    pass


class OverpassUnavailableError(AirportMapError):
    pass


class XPlaneGatewayUnavailableError(AirportMapError):
    pass


class XPlaneGatewayNoDataError(AirportMapError):
    pass


_DATASET_LOCK = threading.Lock()
_INDEX_LOCK = threading.Lock()
_ENDPOINT_LOCK = threading.Lock()
_AIRPORT_INDEX = {}
_RUNWAY_INDEX = {}
_ENDPOINT_RETRY_AFTER = {}
_ENDPOINT_IN_FLIGHT = set()
_XPLANE_RETRY_AFTER = 0


def ensure_csv_dataset(url, path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return
    with _DATASET_LOCK:
        if path.is_file():
            return
        request = urllib.request.Request(url, headers={"User-Agent": "SkyCharts/0.15 airport-map downloader"})
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = response.read()
        temporary = pathlib.Path(tempfile.mkstemp(prefix=path.stem + "-", suffix=".csv", dir=str(path.parent))[1])
        try:
            temporary.write_bytes(payload)
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()


def ensure_airports_csv(path):
    ensure_csv_dataset(AIRPORTS_CSV, path)


def ensure_runways_csv(path):
    ensure_csv_dataset(RUNWAYS_CSV, path)


def csv_index(path, cache, keys):
    path = pathlib.Path(path)
    signature = (str(path.resolve()), path.stat().st_mtime_ns, path.stat().st_size)
    with _INDEX_LOCK:
        cached = cache.get("value")
        if cache.get("signature") == signature and cached is not None:
            return cached
        indexed = {}
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                for key in keys(row):
                    key = (key or "").strip().upper()
                    if key:
                        indexed.setdefault(key, []).append(row)
        cache["signature"] = signature
        cache["value"] = indexed
        return indexed


def airport_record(ident, airports_csv=None):
    ident = ident.strip().upper()
    airports_csv = pathlib.Path(airports_csv or ROOT / "work" / "ourairports-airports.csv")
    ensure_airports_csv(airports_csv)
    index = csv_index(airports_csv, _AIRPORT_INDEX, lambda row: (row.get("gps_code"), row.get("ident")))
    for row in index.get(ident, []):
        try:
            latitude = float(row["latitude_deg"])
            longitude = float(row["longitude_deg"])
        except (KeyError, TypeError, ValueError):
            continue
        return {
            "ident": ident,
            "name": row.get("name") or ident,
            "latitude": latitude,
            "longitude": longitude,
        }
    raise AirportMapError("Airport %s was not found in the airport index" % ident)


def overpass_query(latitude, longitude, radius=5500):
    south, west, north, east = coordinate_bounds(latitude, longitude, radius)
    bbox = "{:.7f},{:.7f},{:.7f},{:.7f}".format(south, west, north, east)
    ways = "\n".join('  way["aeroway"="%s"](%s);' % (kind, bbox) for kind in MAP_KINDS)
    return """[out:json][timeout:25];
(
{ways}
  node[\"aeroway\"=\"parking_position\"]({bbox});
  node[\"aeroway\"=\"gate\"]({bbox});
  node[\"aeroway\"=\"holding_position\"]({bbox});
);
out tags geom;""".format(ways=ways, bbox=bbox)


def coordinate_bounds(latitude, longitude, radius):
    latitude_delta = radius / 111320.0
    longitude_delta = radius / (111320.0 * max(0.2, math.cos(math.radians(latitude))))
    return latitude - latitude_delta, longitude - longitude_delta, latitude + latitude_delta, longitude + longitude_delta


def overpass_kind_query(latitude, longitude, kind, radius=5500):
    south, west, north, east = coordinate_bounds(latitude, longitude, radius)
    bbox = "{:.7f},{:.7f},{:.7f},{:.7f}".format(south, west, north, east)
    selectors = ['way["aeroway"="%s"](%s);' % (kind, bbox)]
    if kind in ("parking_position", "gate", "holding_position"):
        selectors.append('node["aeroway"="%s"](%s);' % (kind, bbox))
    return "[out:json][timeout:45];(%s);out tags geom;" % "".join(selectors)


def short_network_error(error):
    if isinstance(error, urllib.error.HTTPError):
        return "HTTP %s" % error.code
    reason = getattr(error, "reason", error)
    text = str(reason).strip() or error.__class__.__name__
    return text if len(text) <= 72 else text[:69] + "..."


def request_overpass(query, endpoints, timeout=OVERPASS_REQUEST_TIMEOUT):
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    errors = []
    attempted = set()
    while True:
        now = time.monotonic()
        with _ENDPOINT_LOCK:
            candidate = next((value for value in endpoints
                              if value not in attempted
                              and value not in _ENDPOINT_IN_FLIGHT
                              and _ENDPOINT_RETRY_AFTER.get(value, 0) <= now), None)
            if candidate:
                _ENDPOINT_IN_FLIGHT.add(candidate)
        if not candidate:
            break
        attempted.add(candidate)
        request = urllib.request.Request(candidate, data=body, headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "User-Agent": "SkyCharts/0.15 airport-map downloader (https://github.com/skylarkning/SkyCharts)",
        })
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
            with _ENDPOINT_LOCK:
                _ENDPOINT_RETRY_AFTER.pop(candidate, None)
                _ENDPOINT_IN_FLIGHT.discard(candidate)
            return result
        except Exception as error:
            host = urllib.parse.urlparse(candidate).netloc
            errors.append("%s: %s" % (host, short_network_error(error)))
            with _ENDPOINT_LOCK:
                _ENDPOINT_RETRY_AFTER[candidate] = time.monotonic() + OVERPASS_FAILURE_COOLDOWN
                _ENDPOINT_IN_FLIGHT.discard(candidate)
    if errors:
        raise OverpassUnavailableError("all available Overpass services failed (%s)" % "; ".join(errors))
    raise OverpassUnavailableError("Overpass services are busy or in a short retry cooldown")


def fetch_overpass(latitude, longitude, radius=5500, endpoint=None):
    endpoints = (endpoint,) if endpoint else OVERPASS_ENDPOINTS
    return request_overpass(overpass_query(latitude, longitude, radius), endpoints)


def parse_osm_xml(payload, nodes, ways):
    root = ET.fromstring(payload)
    for element in root:
        if element.tag == "node":
            node_id = element.attrib.get("id")
            tags = {tag.attrib.get("k"): tag.attrib.get("v") for tag in element.findall("tag")}
            nodes[node_id] = {
                "type": "node",
                "id": int(node_id),
                "lat": float(element.attrib["lat"]),
                "lon": float(element.attrib["lon"]),
                "tags": tags,
            }
        elif element.tag == "way":
            way_id = element.attrib.get("id")
            ways[way_id] = {
                "type": "way",
                "id": int(way_id),
                "refs": [node.attrib.get("ref") for node in element.findall("nd")],
                "tags": {tag.attrib.get("k"): tag.attrib.get("v") for tag in element.findall("tag")},
            }


def fetch_osm_api(latitude, longitude, radius=5500):
    south, west, north, east = coordinate_bounds(latitude, longitude, radius)
    middle_latitude = (south + north) / 2
    middle_longitude = (west + east) / 2
    tiles = (
        (south, west, middle_latitude, middle_longitude),
        (south, middle_longitude, middle_latitude, east),
        (middle_latitude, west, north, middle_longitude),
        (middle_latitude, middle_longitude, north, east),
    )
    nodes, ways, errors = {}, {}, []

    def fetch_tile(tile, depth=0):
        tile_south, tile_west, tile_north, tile_east = tile
        url = "https://api.openstreetmap.org/api/0.6/map?bbox={:.7f},{:.7f},{:.7f},{:.7f}".format(tile_west, tile_south, tile_east, tile_north)
        request = urllib.request.Request(url, headers={"User-Agent": "SkyCharts/0.11 airport-map downloader (https://github.com/skylarkning/SkyCharts)"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                parse_osm_xml(response.read(), nodes, ways)
                return
        except urllib.error.HTTPError as error:
            if error.code == 400 and depth < 2:
                middle_lat = (tile_south + tile_north) / 2
                middle_lon = (tile_west + tile_east) / 2
                for smaller in (
                    (tile_south, tile_west, middle_lat, middle_lon),
                    (tile_south, middle_lon, middle_lat, tile_east),
                    (middle_lat, tile_west, tile_north, middle_lon),
                    (middle_lat, middle_lon, tile_north, tile_east),
                ):
                    fetch_tile(smaller, depth + 1)
                return
            errors.append("HTTP %s for airport tile" % error.code)
        except Exception as error:
            errors.append(str(error))

    for tile in tiles:
        fetch_tile(tile)
    if errors:
        raise AirportMapError("OpenStreetMap map tiles could not be downloaded: %s" % "; ".join(errors))
    elements = []
    point_kinds = ("parking_position", "gate", "holding_position")
    for node in nodes.values():
        if (node.get("tags") or {}).get("aeroway") in point_kinds:
            elements.append(node)
    for way in ways.values():
        if feature_kind(way.get("tags") or {}) not in MAP_KINDS:
            continue
        geometry = [{"lat": nodes[ref]["lat"], "lon": nodes[ref]["lon"]} for ref in way["refs"] if ref in nodes]
        if geometry:
            element = dict(way)
            element.pop("refs", None)
            element["geometry"] = geometry
            elements.append(element)
    return {"elements": elements}


def optional_float(row, key):
    try:
        value = str(row.get(key) or "").strip()
        return float(value) if value else None
    except (TypeError, ValueError):
        return None


def destination_coordinate(latitude, longitude, heading, distance_metres):
    radians = math.radians(heading)
    latitude_delta = math.cos(radians) * distance_metres / 111320.0
    longitude_delta = math.sin(radians) * distance_metres / (111320.0 * max(0.2, math.cos(math.radians(latitude))))
    return latitude + latitude_delta, longitude + longitude_delta


def ourairports_runway_raw(ident, airport, runways_csv=None):
    runways_csv = pathlib.Path(runways_csv or ROOT / "work" / "ourairports-runways.csv")
    ensure_runways_csv(runways_csv)
    index = csv_index(runways_csv, _RUNWAY_INDEX, lambda row: (row.get("airport_ident"),))
    elements = []
    for number, row in enumerate(index.get(ident.strip().upper(), []), 1):
        if str(row.get("closed") or "0").strip() == "1":
            continue
        length_metres = (optional_float(row, "length_ft") or 0) * 0.3048
        width_metres = (optional_float(row, "width_ft") or 0) * 0.3048
        le_latitude, le_longitude = optional_float(row, "le_latitude_deg"), optional_float(row, "le_longitude_deg")
        he_latitude, he_longitude = optional_float(row, "he_latitude_deg"), optional_float(row, "he_longitude_deg")
        le_heading, he_heading = optional_float(row, "le_heading_degT"), optional_float(row, "he_heading_degT")
        if le_latitude is not None and le_longitude is not None and (he_latitude is None or he_longitude is None) and length_metres and le_heading is not None:
            he_latitude, he_longitude = destination_coordinate(le_latitude, le_longitude, le_heading, length_metres)
        elif he_latitude is not None and he_longitude is not None and (le_latitude is None or le_longitude is None) and length_metres:
            reverse_heading = he_heading if he_heading is not None else ((le_heading + 180) % 360 if le_heading is not None else None)
            if reverse_heading is not None:
                le_latitude, le_longitude = destination_coordinate(he_latitude, he_longitude, reverse_heading, length_metres)
        elif (le_latitude is None or le_longitude is None or he_latitude is None or he_longitude is None) and length_metres and le_heading is not None:
            le_latitude, le_longitude = destination_coordinate(airport["latitude"], airport["longitude"], le_heading + 180, length_metres / 2)
            he_latitude, he_longitude = destination_coordinate(airport["latitude"], airport["longitude"], le_heading, length_metres / 2)
        if None in (le_latitude, le_longitude, he_latitude, he_longitude):
            continue
        low = str(row.get("le_ident") or "").strip().upper()
        high = str(row.get("he_ident") or "").strip().upper()
        reference = "/".join(value for value in (low, high) if value) or "RWY%d" % number
        tags = {"aeroway": "runway", "ref": reference, "operator": "OurAirports"}
        surface = str(row.get("surface") or "").strip()
        if surface:
            tags["surface"] = surface
        if width_metres:
            tags["width"] = "%.2f" % width_metres
        elements.append({
            "type": "way",
            "id": "ourairports-%s-%s" % (ident, row.get("id") or number),
            "tags": tags,
            "geometry": [
                {"lat": le_latitude, "lon": le_longitude},
                {"lat": he_latitude, "lon": he_longitude},
            ],
        })
    return {"elements": elements}


def request_xplane_json(url):
    global _XPLANE_RETRY_AFTER
    with _ENDPOINT_LOCK:
        if _XPLANE_RETRY_AFTER > time.monotonic():
            raise XPlaneGatewayUnavailableError("X-Plane Scenery Gateway is in a short retry cooldown")
    request = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "SkyCharts/0.15 airport-map downloader (https://github.com/skylarkning/SkyCharts)",
    })
    try:
        with urllib.request.urlopen(request, timeout=XPLANE_REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        with _ENDPOINT_LOCK:
            _XPLANE_RETRY_AFTER = 0
        return payload
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise XPlaneGatewayNoDataError("airport is not present in the X-Plane Scenery Gateway")
        with _ENDPOINT_LOCK:
            _XPLANE_RETRY_AFTER = time.monotonic() + XPLANE_FAILURE_COOLDOWN
        raise XPlaneGatewayUnavailableError("X-Plane Scenery Gateway returned HTTP %s" % error.code)
    except XPlaneGatewayNoDataError:
        raise
    except Exception as error:
        with _ENDPOINT_LOCK:
            _XPLANE_RETRY_AFTER = time.monotonic() + XPLANE_FAILURE_COOLDOWN
        raise XPlaneGatewayUnavailableError("X-Plane Scenery Gateway request failed: %s" % short_network_error(error))


def scenery_identifier(airport):
    recommended = airport.get("recommendedSceneryId") or airport.get("recommended_scenery_id")
    if recommended:
        return str(recommended)
    candidates = airport.get("scenery") or airport.get("sceneries") or []
    if isinstance(candidates, dict):
        candidates = list(candidates.values())
    approved = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        status = str(candidate.get("status") or candidate.get("Status") or "").lower()
        identifier = candidate.get("sceneryId") or candidate.get("id")
        if identifier and ("approv" in status or "recommend" in status):
            approved.append((str(candidate.get("dateApproved") or candidate.get("date") or ""), str(identifier)))
    return max(approved)[1] if approved else None


def extract_xplane_apt(zip_payload, ident):
    if len(zip_payload) > 40 * 1024 * 1024:
        raise AirportMapError("X-Plane airport scenery archive is unexpectedly large")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_payload)) as archive:
            candidates = [entry for entry in archive.infolist()
                          if not entry.is_dir() and entry.filename.lower().endswith(".dat")
                          and entry.file_size <= 20 * 1024 * 1024]
            preferred = next((entry for entry in candidates
                              if pathlib.PurePosixPath(entry.filename).name.upper() == ident.upper() + ".DAT"), None)
            entry = preferred or (candidates[0] if candidates else None)
            if entry is None:
                raise XPlaneGatewayNoDataError("recommended X-Plane scenery does not contain airport data")
            payload = archive.read(entry)
    except zipfile.BadZipFile:
        raise XPlaneGatewayUnavailableError("X-Plane Scenery Gateway returned an invalid scenery archive")
    try:
        return payload.decode("utf-8-sig"), entry.filename
    except UnicodeDecodeError:
        return payload.decode("latin-1"), entry.filename


def fetch_xplane_gateway_apt(ident):
    airport_response = request_xplane_json(XPLANE_GATEWAY_AIRPORT_URL.format(ident=urllib.parse.quote(ident)))
    airport = airport_response.get("airport") if isinstance(airport_response, dict) else None
    airport = airport if isinstance(airport, dict) else airport_response
    if not isinstance(airport, dict):
        raise XPlaneGatewayUnavailableError("X-Plane Scenery Gateway returned an invalid airport record")
    identifier = scenery_identifier(airport)
    if not identifier:
        raise XPlaneGatewayNoDataError("airport has no approved scenery in the X-Plane Scenery Gateway")
    scenery_response = request_xplane_json(XPLANE_GATEWAY_SCENERY_URL.format(scenery_id=urllib.parse.quote(identifier)))
    scenery = scenery_response.get("scenery") if isinstance(scenery_response, dict) else None
    scenery = scenery if isinstance(scenery, dict) else scenery_response
    if not isinstance(scenery, dict):
        raise XPlaneGatewayUnavailableError("X-Plane Scenery Gateway returned an invalid scenery record")
    blob = scenery.get("masterZipBlob")
    if not blob:
        raise XPlaneGatewayNoDataError("recommended X-Plane scenery has no downloadable airport data")
    try:
        zip_payload = base64.b64decode(blob)
    except (TypeError, ValueError) as error:
        raise XPlaneGatewayUnavailableError("X-Plane scenery archive could not be decoded: %s" % error)
    apt_text, apt_name = extract_xplane_apt(zip_payload, ident)
    return apt_text, {
        "sceneryId": identifier,
        "aptName": apt_name,
        "artist": scenery.get("userName") or scenery.get("artist") or "",
        "approvedAt": scenery.get("dateApproved") or "",
    }


def xplane_surface_name(value):
    return {
        "1": "asphalt", "2": "concrete", "3": "turf/grass", "4": "dirt",
        "5": "gravel", "12": "dry lakebed", "13": "water", "14": "snow/ice",
        "15": "transparent",
    }.get(str(value), str(value))


def parse_xplane_apt(text, ident):
    ident = ident.strip().upper()
    elements, taxi_nodes, taxi_edges = [], {}, []
    polygon_name, polygon_surface, polygon_points = None, None, []
    active, found_airport, serial = False, False, 0

    def add_polygon(close=False):
        nonlocal polygon_points, serial
        if len(polygon_points) < 3:
            polygon_points = []
            return
        points = list(polygon_points)
        if close and points[0] != points[-1]:
            points.append(dict(points[0]))
        serial += 1
        tags = {"aeroway": "apron", "operator": "X-Plane Scenery Gateway"}
        if polygon_name:
            tags["name"] = polygon_name
        if polygon_surface:
            tags["surface"] = xplane_surface_name(polygon_surface)
        elements.append({"type": "way", "id": "xplane-apron-%d" % serial, "tags": tags, "geometry": points})
        polygon_points = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        values = line.split()
        code = values[0]
        if code in ("1", "16", "17") and len(values) >= 5:
            add_polygon()
            airport_ident = values[4].upper()
            if active and airport_ident != ident:
                break
            active = airport_ident == ident
            found_airport = found_airport or active
            continue
        if not active:
            continue
        if code not in ("111", "112", "113", "114"):
            add_polygon()
        try:
            if code == "100" and len(values) >= 20:
                serial += 1
                low, high = values[8].upper(), values[17].upper()
                tags = {
                    "aeroway": "runway",
                    "ref": "/".join(value for value in (low, high) if value),
                    "width": values[1],
                    "surface": xplane_surface_name(values[2]),
                    "operator": "X-Plane Scenery Gateway",
                }
                elements.append({
                    "type": "way", "id": "xplane-runway-%d" % serial, "tags": tags,
                    "geometry": [
                        {"lat": float(values[9]), "lon": float(values[10])},
                        {"lat": float(values[18]), "lon": float(values[19])},
                    ],
                })
            elif code == "110" and len(values) >= 4:
                polygon_surface = values[1]
                polygon_name = " ".join(values[4:]).strip()
                polygon_points = []
            elif code in ("111", "112", "113", "114") and polygon_name is not None and len(values) >= 3:
                polygon_points.append({"lat": float(values[1]), "lon": float(values[2])})
                if code in ("113", "114"):
                    add_polygon(close=True)
            elif code == "1201" and len(values) >= 5:
                taxi_nodes[values[4]] = {"lat": float(values[1]), "lon": float(values[2])}
            elif code == "1202" and len(values) >= 5:
                taxi_edges.append(values)
            elif code == "1300" and len(values) >= 6:
                name = " ".join(values[6:]).strip()
                if not name:
                    continue
                reference = re.sub(r"^(?:gate|stand|parking(?: position)?|ramp)\s*[-#:]?\s*", "", name,
                                   flags=re.IGNORECASE).strip() or name
                serial += 1
                kind = "gate" if values[4].lower() == "gate" else "parking_position"
                elements.append({
                    "type": "node", "id": "xplane-ramp-%d" % serial,
                    "lat": float(values[1]), "lon": float(values[2]),
                    "tags": {"aeroway": kind, "ref": reference, "name": name,
                             "operator": "X-Plane Scenery Gateway"},
                })
        except (IndexError, TypeError, ValueError):
            continue
    add_polygon()
    if not found_airport:
        raise XPlaneGatewayNoDataError("downloaded X-Plane airport data does not contain %s" % ident)
    for edge in taxi_edges:
        start, end = taxi_nodes.get(edge[1]), taxi_nodes.get(edge[2])
        if not start or not end:
            continue
        route_class = edge[4]
        if route_class.lower().startswith("runway"):
            continue
        reference = " ".join(edge[5:]).strip()
        serial += 1
        tags = {"aeroway": "taxiway", "operator": "X-Plane Scenery Gateway"}
        if reference and reference != "_stop":
            tags["ref"] = reference
        elements.append({
            "type": "way", "id": "xplane-taxi-%d" % serial, "tags": tags,
            "geometry": [dict(start), dict(end)],
        })
    return {"elements": elements}


def xplane_gateway_raw(ident):
    apt_text, metadata = fetch_xplane_gateway_apt(ident)
    raw = parse_xplane_apt(apt_text, ident)
    raw["gateway"] = metadata
    return raw


def point_pair(point):
    try:
        return [round(float(point["lon"]), 7), round(float(point["lat"]), 7)]
    except (KeyError, TypeError, ValueError):
        return None


def feature_kind(tags):
    kind = tags.get("aeroway")
    if kind in MAP_KINDS:
        return kind
    building = tags.get("building")
    return building if building in ("terminal", "hangar") else None


def feature_counts(features):
    counts, runway_references = {}, set()
    for feature in features:
        counts[feature["kind"]] = counts.get(feature["kind"], 0) + 1
        if feature["kind"] == "runway":
            runway_references.add(feature.get("ref") or "osm-runway-%d" % len(runway_references))
    if runway_references:
        counts["runway"] = len(runway_references)
    return counts


def map_detail_score(result):
    counts = (result or {}).get("counts") or {}
    taxiways = counts.get("taxiway", 0) + counts.get("taxilane", 0)
    stands = counts.get("parking_position", 0) + counts.get("gate", 0)
    return (counts.get("runway", 0) * 2 + taxiways * 3 + stands * 2
            + counts.get("apron", 0) + counts.get("terminal", 0) * 4
            + counts.get("hangar", 0))


def terminal_label(tags):
    reference = str(tags.get("ref") or "").strip().upper()
    if reference:
        value = reference[1:] if reference.startswith("T") and len(reference) > 1 else reference
        return "Terminal " + value
    name = str(tags.get("name") or "").strip()
    match = re.search(r"(?:terminal|terminl)\s*[-#]?\s*(?:no\.?\s*)?([a-z]|[0-9]{1,3})\b|T\s*([0-9]{1,3}|[A-Z]\b)", name, re.IGNORECASE)
    if not match:
        return None
    value = (match.group(1) or match.group(2) or "").upper()
    value = value[1:] if value.startswith("T") and len(value) > 1 else value
    return "Terminal " + value


def normalize(raw, airport, source="OpenStreetMap contributors", source_url="https://www.openstreetmap.org/copyright"):
    features = []
    all_points = []
    seen = set()
    for element in raw.get("elements", []):
        tags = element.get("tags") or {}
        kind = feature_kind(tags)
        if not kind:
            continue
        identity = (element.get("type"), element.get("id"), kind)
        if identity in seen:
            continue
        seen.add(identity)
        geometry = [pair for pair in (point_pair(value) for value in element.get("geometry", [])) if pair]
        if not geometry and element.get("type") == "node":
            pair = point_pair(element)
            if pair:
                geometry = [pair]
        if not geometry:
            continue
        feature = {
            "kind": kind,
            "points": geometry,
        }
        for key in ("ref", "name", "surface", "width", "operator"):
            value = tags.get(key)
            if value:
                feature[key] = str(value)
        if kind == "terminal":
            label = terminal_label(tags)
            if label:
                feature["label"] = label
        if len(geometry) > 2 and geometry[0] == geometry[-1]:
            feature["closed"] = True
        features.append(feature)
        all_points.extend(geometry)
    if not features:
        raise AirportMapError("No runway, taxiway, apron, or stand geometry was found for %s" % airport["ident"])
    minimum_lon = min(point[0] for point in all_points)
    maximum_lon = max(point[0] for point in all_points)
    minimum_lat = min(point[1] for point in all_points)
    maximum_lat = max(point[1] for point in all_points)
    latitude_padding = max((maximum_lat - minimum_lat) * 0.035, 0.0005)
    longitude_padding = max((maximum_lon - minimum_lon) * 0.035, 0.0005)
    bounds = {
        "minLon": minimum_lon - longitude_padding,
        "maxLon": maximum_lon + longitude_padding,
        "minLat": minimum_lat - latitude_padding,
        "maxLat": maximum_lat + latitude_padding,
    }
    counts = feature_counts(features)
    return {
        "schemaVersion": 1,
        "ident": airport["ident"],
        "name": airport["name"],
        "center": [airport["longitude"], airport["latitude"]],
        "bounds": bounds,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": source,
        "sourceURL": source_url,
        "counts": counts,
        "features": features,
    }


def cache_is_fresh(path, maximum_age_days):
    if not path.is_file():
        return False
    age = dt.datetime.now().timestamp() - path.stat().st_mtime
    return age < maximum_age_days * 86400


def cached_unavailable_reason(path):
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if float(record.get("retryAfter") or 0) > time.time():
            return record.get("reason") or "airport-map sources are temporarily unavailable"
    except (OSError, TypeError, ValueError):
        return None
    return None


def write_unavailable_marker(path, reason, retry_seconds):
    temporary = pathlib.Path(tempfile.mkstemp(prefix=path.stem + "-", suffix=".json", dir=str(path.parent))[1])
    try:
        temporary.write_text(json.dumps({
            "reason": reason,
            "checkedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "retryAfter": time.time() + retry_seconds,
        }, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_airport_map(ident, cache_dir=None, refresh=False, radius=5500, maximum_age_days=30):
    ident = ident.strip().upper()
    if len(ident) != 4 or not ident.isalnum():
        raise AirportMapError("Enter a four-character ICAO airport code")
    cache_dir = pathlib.Path(cache_dir or ROOT / "work" / "airport-map-cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / (ident + ".json")
    unavailable_path = cache_dir / (ident + ".unavailable.json")
    if not refresh and cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cache_days = min(maximum_age_days, 1) if cached.get("source") == "OurAirports" else maximum_age_days
        if cache_is_fresh(cache_path, cache_days):
            cached["counts"] = feature_counts(cached.get("features", []))
            return cached, True
    if not refresh:
        unavailable_reason = cached_unavailable_reason(unavailable_path)
        if unavailable_reason:
            raise AirportMapError(unavailable_reason + " (recent result reused)")
    airport = airport_record(ident)
    raw, result, overpass_error, gateway_error, gateway_missing, runway_raw = None, None, None, None, None, None
    try:
        raw = fetch_overpass(airport["latitude"], airport["longitude"], radius)
    except OverpassUnavailableError as error:
        overpass_error = error
    if raw is not None:
        osm_elements = list(raw.get("elements", []))
        if osm_elements:
            has_runway = any(feature_kind((element.get("tags") or {})) == "runway" for element in osm_elements)
            if not has_runway:
                try:
                    runway_raw = ourairports_runway_raw(ident, airport)
                except Exception:
                    runway_raw = {"elements": []}
                if runway_raw.get("elements"):
                    osm_elements.extend(runway_raw["elements"])
            try:
                source = "OpenStreetMap contributors + OurAirports" if runway_raw and runway_raw.get("elements") else "OpenStreetMap contributors"
                result = normalize({"elements": osm_elements}, airport, source=source)
            except AirportMapError:
                result = None
    result_counts = (result or {}).get("counts") or {}
    needs_gateway_detail = (result is None
                            or result_counts.get("taxiway", 0) + result_counts.get("taxilane", 0) == 0
                            or result_counts.get("parking_position", 0) + result_counts.get("gate", 0) == 0)
    if needs_gateway_detail:
        try:
            gateway_raw = xplane_gateway_raw(ident)
            gateway_elements = list(gateway_raw.get("elements", []))
            gateway_augmented = False
            osm_buildings = [element for element in (raw or {}).get("elements", [])
                             if feature_kind(element.get("tags") or {}) in ("terminal", "hangar")]
            if osm_buildings:
                gateway_elements.extend(osm_buildings)
            if not any(feature_kind((element.get("tags") or {})) == "runway" for element in gateway_elements):
                try:
                    runway_raw = runway_raw or ourairports_runway_raw(ident, airport)
                except Exception:
                    runway_raw = {"elements": []}
                if runway_raw.get("elements"):
                    gateway_elements.extend(runway_raw["elements"])
                    gateway_augmented = True
            sources = ["X-Plane Scenery Gateway"]
            if gateway_augmented:
                sources.append("OurAirports")
            if osm_buildings:
                sources.insert(0, "OpenStreetMap contributors")
            source = " + ".join(sources)
            gateway_result = normalize({"elements": gateway_elements}, airport, source=source,
                                       source_url=XPLANE_GATEWAY_SOURCE_URL)
            if result is None or map_detail_score(gateway_result) > map_detail_score(result):
                result = gateway_result
        except XPlaneGatewayNoDataError as error:
            gateway_missing = error
        except XPlaneGatewayUnavailableError as error:
            gateway_error = error
        except AirportMapError as error:
            gateway_missing = error
    if result is None:
        try:
            runway_raw = runway_raw or ourairports_runway_raw(ident, airport)
        except Exception as error:
            runway_raw = {"elements": []}
            if overpass_error is None:
                overpass_error = OverpassUnavailableError(short_network_error(error))
        if runway_raw.get("elements"):
            result = normalize(runway_raw, airport, source="OurAirports", source_url="https://ourairports.com/data/")
    if result is None:
        if overpass_error is not None or gateway_error is not None:
            unavailable = []
            if overpass_error is not None:
                unavailable.append("OpenStreetMap: %s" % overpass_error)
            if gateway_error is not None:
                unavailable.append("X-Plane Gateway: %s" % gateway_error)
            reason = "airport-map services are temporarily unavailable for %s (%s)" % (ident, "; ".join(unavailable))
            retry_seconds = TRANSIENT_UNAVAILABLE_SECONDS
        else:
            detail = ": %s" % gateway_missing if gateway_missing else ""
            reason = "no airport-map geometry was found in OpenStreetMap, X-Plane Gateway, or OurAirports for %s%s" % (ident, detail)
            retry_seconds = MISSING_DATA_SECONDS
        write_unavailable_marker(unavailable_path, reason, retry_seconds)
        raise AirportMapError(reason)
    temporary = pathlib.Path(tempfile.mkstemp(prefix=ident + "-", suffix=".json", dir=str(cache_dir))[1])
    try:
        temporary.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
        temporary.replace(cache_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    if unavailable_path.exists():
        unavailable_path.unlink()
    return result, False


def main():
    parser = argparse.ArgumentParser(description="Download an offline SkyCharts airport vector map")
    parser.add_argument("ident", help="four-character ICAO code")
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--cache-dir", type=pathlib.Path, default=ROOT / "work" / "airport-map-cache")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--radius", type=int, default=5500, help="OSM search radius in metres")
    args = parser.parse_args()
    result, cached = build_airport_map(args.ident, args.cache_dir, args.refresh, args.radius)
    output = args.output or ROOT / "outputs" / (args.ident.upper() + "-airport-map.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    counts = result.get("counts", {})
    print("%s %s airport map: %d runways, %d taxiways, %d parking positions" % (
        "Reused" if cached else "Downloaded",
        result["ident"],
        counts.get("runway", 0),
        counts.get("taxiway", 0) + counts.get("taxilane", 0),
        counts.get("parking_position", 0),
    ))
    print("Saved %s" % output)


if __name__ == "__main__":
    main()
