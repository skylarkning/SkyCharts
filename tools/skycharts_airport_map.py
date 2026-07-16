#!/usr/bin/env python3
"""Download and normalize OpenStreetMap airport geometry for SkyCharts."""

import argparse
import csv
import datetime as dt
import json
import math
import pathlib
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
AIRPORTS_CSV = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_ENDPOINTS = (
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    OVERPASS_URL,
)
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


def ensure_airports_csv(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return
    request = urllib.request.Request(AIRPORTS_CSV, headers={"User-Agent": "SkyCharts/0.11 airport-map downloader"})
    with urllib.request.urlopen(request, timeout=60) as response:
        path.write_bytes(response.read())


def airport_record(ident, airports_csv=None):
    ident = ident.strip().upper()
    airports_csv = pathlib.Path(airports_csv or ROOT / "work" / "ourairports-airports.csv")
    ensure_airports_csv(airports_csv)
    with airports_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            code = (row.get("gps_code") or row.get("ident") or "").strip().upper()
            if code != ident:
                continue
            try:
                latitude = float(row["latitude_deg"])
                longitude = float(row["longitude_deg"])
            except (KeyError, TypeError, ValueError):
                break
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
    return """[out:json][timeout:90];
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


def request_overpass(query, endpoints):
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    errors = []
    for candidate in endpoints:
        request = urllib.request.Request(candidate, data=body, headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "User-Agent": "SkyCharts/0.11 airport-map downloader (https://github.com/skylarkning/SkyCharts)",
        })
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:
            errors.append("%s: %s" % (urllib.parse.urlparse(candidate).netloc, error))
    raise AirportMapError("; ".join(errors))


def fetch_overpass(latitude, longitude, radius=5500, endpoint=None):
    endpoints = (endpoint,) if endpoint else OVERPASS_ENDPOINTS
    try:
        return request_overpass(overpass_query(latitude, longitude, radius), endpoints)
    except AirportMapError:
        pass
    elements, failures = [], []
    for kind in MAP_KINDS:
        try:
            result = request_overpass(overpass_kind_query(latitude, longitude, kind, radius), endpoints)
            elements.extend(result.get("elements", []))
        except AirportMapError as error:
            failures.append("%s (%s)" % (kind, error))
    if failures:
        raise AirportMapError("OpenStreetMap airport data could not be downloaded: %s" % "; ".join(failures))
    return {"elements": elements}


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


def normalize(raw, airport):
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
        "source": "OpenStreetMap contributors",
        "sourceURL": "https://www.openstreetmap.org/copyright",
        "counts": counts,
        "features": features,
    }


def cache_is_fresh(path, maximum_age_days):
    if not path.is_file():
        return False
    age = dt.datetime.now().timestamp() - path.stat().st_mtime
    return age < maximum_age_days * 86400


def build_airport_map(ident, cache_dir=None, refresh=False, radius=5500, maximum_age_days=30):
    ident = ident.strip().upper()
    if len(ident) != 4 or not ident.isalnum():
        raise AirportMapError("Enter a four-character ICAO airport code")
    cache_dir = pathlib.Path(cache_dir or ROOT / "work" / "airport-map-cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / (ident + ".json")
    if not refresh and cache_is_fresh(cache_path, maximum_age_days):
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached["counts"] = feature_counts(cached.get("features", []))
        return cached, True
    airport = airport_record(ident)
    raw = fetch_overpass(airport["latitude"], airport["longitude"], radius)
    result = normalize(raw, airport)
    temporary = pathlib.Path(tempfile.mkstemp(prefix=ident + "-", suffix=".json", dir=str(cache_dir))[1])
    try:
        temporary.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
        temporary.replace(cache_path)
    finally:
        if temporary.exists():
            temporary.unlink()
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
