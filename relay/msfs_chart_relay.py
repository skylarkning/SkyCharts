#!/usr/bin/env python3
"""Small KJFK AGC compatibility relay for the legacy iPad prototype."""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PLANNER = "https://planner.flightsimulator.com"
AIRPORT_FSID = "A      KJFK "
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "1800"))


class RelayError(RuntimeError):
    pass


class ChartCache:
    def __init__(self):
        self.lock = threading.Lock()
        self.expires = 0
        self.light = None
        self.dark = None
        self.metadata = None

    def get(self):
        with self.lock:
            if time.time() < self.expires and self.light:
                return self.metadata, self.light, self.dark
            metadata, light, dark = fetch_agc()
            self.metadata, self.light, self.dark = metadata, light, dark
            self.expires = time.time() + CACHE_SECONDS
            return metadata, light, dark


cache = ChartCache()
dynamic_cache = {}
dynamic_lock = threading.Lock()


def planner_request(path, expect_json=True):
    cookie = os.environ.get("MSFS_SESSION_COOKIE", "").strip()
    cookie_file = os.environ.get("MSFS_COOKIE_FILE", "").strip()
    if not cookie and cookie_file:
        try:
            with open(cookie_file, "r", encoding="utf-8") as handle:
                cookie = handle.read().strip()
        except OSError as error:
            raise RelayError("Could not read MSFS_COOKIE_FILE") from error
    if not cookie:
        raise RelayError("MSFS_SESSION_COOKIE is not configured")
    request = urllib.request.Request(
        PLANNER + path,
        headers={
            "Cookie": cookie,
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "KJFK-AGC-Relay/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise RelayError("MSFS session is expired or unauthorized") from error
        raise RelayError("Planner returned HTTP %s" % error.code) from error
    except urllib.error.URLError as error:
        raise RelayError("Planner connection failed: %s" % error.reason) from error
    return json.loads(payload.decode("utf-8")) if expect_json else payload.decode("utf-8").strip()


def flatten_charts(index):
    """Yield chart-like dictionaries from current and older index layouts."""
    if isinstance(index, list):
        for item in index:
            yield from flatten_charts(item)
        return
    if not isinstance(index, dict):
        return
    if ("guid" in index or "id" in index) and ("name" in index or "chartName" in index):
        yield index
    for value in index.values():
        if isinstance(value, (dict, list)):
            yield from flatten_charts(value)


def fetch_binary(url):
    request = urllib.request.Request(url, headers={"User-Agent": "KJFK-AGC-Relay/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return response.read()
    except (urllib.error.HTTPError, urllib.error.URLError) as error:
        raise RelayError("Chart image download failed") from error


def fetch_agc():
    override = os.environ.get("MSFS_CHART_LIGHT_URL", "").strip()
    if override:
        light = fetch_binary(override)
        dark_url = os.environ.get("MSFS_CHART_DARK_URL", "").strip()
        dark = fetch_binary(dark_url) if dark_url else None
        return {"airport": "KJFK", "type": "AGC", "name": "Airport Ground Chart AGC"}, light, dark

    fsid = urllib.parse.quote(AIRPORT_FSID, safe="")
    index = planner_request("/api/v1/charts/index/%s?provider=LIDO" % fsid)
    matches = []
    for chart in flatten_charts(index):
        name = chart.get("name") or chart.get("chartName") or ""
        normalized = " ".join(str(name).split()).casefold()
        chart_type = str(chart.get("type") or chart.get("chartType") or "").upper()
        aircraft_types = chart.get("aircraftTypes") or []
        if chart_type == "AGC" and normalized in ("agc", "airport ground chart agc") and not aircraft_types:
            matches.append(chart)
    if not matches:
        raise RelayError("Standard KJFK Airport Ground Chart AGC was not found")
    chart = matches[0]
    guid = chart.get("guid") or chart.get("id")
    if not guid:
        raise RelayError("Chart metadata did not contain a GUID")

    pages = planner_request("/api/v1/charts/pages/%s" % urllib.parse.quote(str(guid), safe=""))
    page_list = pages.get("pages", []) if isinstance(pages, dict) else []
    if not page_list:
        raise RelayError("Chart has no image pages")
    urls = page_list[0].get("urls", {})
    sas = planner_request("/api/v1/charts-sas", expect_json=False).lstrip("?")
    light_base = urls.get("light_png")
    dark_base = urls.get("dark_png")
    if not light_base:
        raise RelayError("Chart has no light PNG")
    light = fetch_binary(light_base + "?" + sas)
    dark = fetch_binary(dark_base + "?" + sas) if dark_base else None
    metadata = {
        "airport": "KJFK",
        "type": "AGC",
        "name": "Airport Ground Chart AGC",
        "provider": "LIDO",
        "hasDark": bool(dark),
    }
    return metadata, light, dark


def search_airports(term):
    payload = planner_request("/api/v1/facilities/search?searchTerm=" + urllib.parse.quote(term))
    airports = []
    for item in payload if isinstance(payload, list) else []:
        struct = item.get("icaoStruct", {}) if isinstance(item, dict) else {}
        if item.get("__Type") != "JS_FacilityAirportLight" and struct.get("type") != "A":
            continue
        ident = struct.get("ident") or ""
        if ident:
            airports.append({
                "ident": ident.strip(), "fsid": item.get("icao", ""),
                "name": item.get("name", ""), "region": item.get("region", ""),
                "city": item.get("city", ""), "lat": item.get("lat"), "lon": item.get("lon"),
            })
    return airports


def chart_catalog(fsid, provider="LIDO"):
    encoded = urllib.parse.quote(fsid, safe="")
    payload = planner_request("/api/v1/charts/index/%s?provider=%s" % (encoded, urllib.parse.quote(provider)))
    categories = []
    groups = payload.get("charts", {}) if isinstance(payload, dict) else {}
    for category, values in groups.items() if isinstance(groups, dict) else []:
        charts = []
        for chart in values if isinstance(values, list) else []:
            if not isinstance(chart, dict) or not chart.get("guid"):
                continue
            runways = []
            for runway in chart.get("runways", []) or []:
                if isinstance(runway, dict):
                    runways.append((runway.get("number", "") + runway.get("designator", "")).strip())
            charts.append({
                "guid": chart["guid"], "type": chart.get("type", category),
                "name": chart.get("name", chart.get("type", category)),
                "runways": runways, "aircraftTypes": chart.get("aircraftTypes", []) or [],
            })
        if charts:
            categories.append({"name": category, "charts": charts})
    return {"airportFsid": fsid, "provider": provider, "categories": categories}


def chart_page_manifest(guid):
    pages = planner_request("/api/v1/charts/pages/%s" % urllib.parse.quote(guid, safe=""))
    values = pages.get("pages", []) if isinstance(pages, dict) else []
    result = []
    for index, page in enumerate(values):
        urls = page.get("urls", {}) if isinstance(page, dict) else {}
        result.append({
            "index": index,
            "lightImage": "/api/charts/%s/pages/%d/light.png" % (guid, index),
            "darkImage": "/api/charts/%s/pages/%d/dark.png" % (guid, index) if urls.get("dark_png") else None,
        })
    if not result:
        raise RelayError("Chart has no image pages")
    return {"guid": guid, "pages": result}, values


def fetch_chart_page(guid, page_index, theme):
    key = (guid, page_index, theme)
    with dynamic_lock:
        cached = dynamic_cache.get(key)
        if cached and cached[0] > time.time():
            return cached[1]
    _, pages = chart_page_manifest(guid)
    if page_index < 0 or page_index >= len(pages):
        raise RelayError("Chart page does not exist")
    urls = pages[page_index].get("urls", {})
    base = urls.get("dark_png" if theme == "dark" else "light_png")
    if not base:
        raise RelayError("Requested chart theme does not exist")
    sas = planner_request("/api/v1/charts-sas", expect_json=False).lstrip("?")
    image = fetch_binary(base + "?" + sas)
    with dynamic_lock:
        dynamic_cache[key] = (time.time() + CACHE_SECONDS, image)
    return image


class Handler(BaseHTTPRequestHandler):
    server_version = "KJFKAGCRelay/0.1"

    def send_payload(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/health":
            self.send_payload(200, "application/json", b'{"ok":true}')
            return
        try:
            if path == "/api/search":
                term = urllib.parse.parse_qs(parsed.query).get("q", [""])[0].strip()
                if len(term) < 2:
                    raise RelayError("Enter at least two characters")
                payload = json.dumps({"airports": search_airports(term)}, separators=(",", ":")).encode("utf-8")
                self.send_payload(200, "application/json", payload)
                return
            if path == "/api/charts":
                query = urllib.parse.parse_qs(parsed.query)
                fsid = query.get("fsid", [""])[0]
                if not fsid:
                    raise RelayError("Missing airport fsid")
                payload = json.dumps(chart_catalog(fsid), separators=(",", ":")).encode("utf-8")
                self.send_payload(200, "application/json", payload)
                return
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["api", "charts"]:
                manifest, _ = chart_page_manifest(parts[2])
                self.send_payload(200, "application/json", json.dumps(manifest, separators=(",", ":")).encode("utf-8"))
                return
            if len(parts) == 6 and parts[0:2] == ["api", "charts"] and parts[3] == "pages":
                guid, page_text, filename = parts[2], parts[4], parts[5]
                theme = filename.split(".")[0]
                image = fetch_chart_page(guid, int(page_text), theme)
                self.send_payload(200, "image/png", image)
                return
            metadata, light, dark = cache.get()
            if path == "/api/airports/KJFK/charts/agc":
                result = dict(metadata)
                result["lightImage"] = "/api/airports/KJFK/charts/agc/light.png"
                result["darkImage"] = "/api/airports/KJFK/charts/agc/dark.png" if dark else None
                payload = json.dumps(result, separators=(",", ":")).encode("utf-8")
                self.send_payload(200, "application/json", payload)
            elif path == "/api/airports/KJFK/charts/agc/light.png":
                self.send_payload(200, "image/png", light)
            elif path == "/api/airports/KJFK/charts/agc/dark.png" and dark:
                self.send_payload(200, "image/png", dark)
            else:
                self.send_payload(404, "application/json", b'{"error":"not found"}')
        except RelayError as error:
            payload = json.dumps({"error": str(error)}).encode("utf-8")
            self.send_payload(502, "application/json", payload)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def main():
    host = os.environ.get("RELAY_HOST", "0.0.0.0")
    port = int(os.environ.get("RELAY_PORT", "8765"))
    print("KJFK AGC relay listening on http://%s:%d" % (host, port))
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
