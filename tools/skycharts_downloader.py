#!/usr/bin/env python3
"""Build and install offline SkyCharts chart packs."""

import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "relay"))
import msfs_chart_relay as planner  # noqa: E402
import skycharts_airport_map  # noqa: E402

AIRPORTS_CSV = "https://davidmegginson.github.io/ourairports-data/airports.csv"
COUNTRIES_CSV = "https://davidmegginson.github.io/ourairports-data/countries.csv"
REGIONS_CSV = "https://davidmegginson.github.io/ourairports-data/regions.csv"
CONTINENT_NAMES = {"AF": "Africa", "AN": "Antarctica", "AS": "Asia", "EU": "Europe", "NA": "North America", "OC": "Oceania", "SA": "South America"}
MACHINE_PROGRESS = os.environ.get("SKYCHARTS_MACHINE_PROGRESS") == "1"


def safe_name(value):
    return "".join(c for c in value if c.isalnum() or c in "-_")


def display_region(value):
    value = value or "Unknown Region"
    return value[:-9] if value.endswith(" Province") else value


def display_city(value):
    value = value or "Unknown City"
    return value.split(" (", 1)[0]


def find_airport(ident):
    results = planner.search_airports(ident.upper())
    for airport in results:
        if airport["ident"].upper() == ident.upper():
            return airport
    return None


def link_or_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def cached_chart(guid, destination, cache_dir, include_dark):
    metadata_path = cache_dir / safe_name(guid) / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text())
    except (OSError, ValueError):
        return None
    pages = metadata.get("pages", [])
    for page in pages:
        if not (cache_dir / page.get("light", "")).is_file():
            return None
        if include_dark and page.get("dark") and not (cache_dir / page["dark"]).is_file():
            return None
    output = []
    for page in pages:
        installed = {}
        for theme in ("light", "dark"):
            relative = page.get(theme)
            if relative and (theme == "light" or include_dark):
                link_or_copy(cache_dir / relative, destination / relative)
                installed[theme] = relative
        output.append(installed)
    return output


def download_page(guid, index, page, destination, cache_dir, sas, include_dark=False):
    urls = page.get("urls", {})
    output = {}
    for theme, key in (("light", "light_png"), ("dark", "dark_png")):
        if theme == "dark" and not include_dark:
            continue
        base = urls.get(key)
        if not base:
            continue
        relative = pathlib.Path("charts") / safe_name(guid) / ("%d-%s.png" % (index, theme))
        cache_target = cache_dir / relative
        if not cache_target.exists():
            cache_target.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_target.with_suffix(".part")
            temporary.write_bytes(planner.fetch_binary(base + "?" + sas))
            temporary.replace(cache_target)
        link_or_copy(cache_target, destination / relative)
        output[theme] = str(relative)
    return output


def write_chart_cache_metadata(metadata, pages, cache_dir, airport=None, category_name=None):
    guid = metadata["guid"]
    metadata_path = cache_dir / safe_name(guid) / "metadata.json"
    existing = {}
    if metadata_path.exists():
        try:
            existing = json.loads(metadata_path.read_text())
        except (OSError, ValueError):
            existing = {}
    record = dict(existing)
    record["guid"] = guid
    if not record.get("pages"):
        record["pages"] = pages
    for key in ("name", "type"):
        if metadata.get(key):
            record[key] = metadata[key]
    airports = record.get("airports", []) if isinstance(record.get("airports"), list) else []
    if airport and airport.get("ident"):
        ident = airport["ident"].upper()
        entry = {"ident": ident, "name": airport.get("name") or ident}
        if category_name:
            entry["category"] = category_name
        airports = [value for value in airports if not isinstance(value, dict) or value.get("ident", "").upper() != ident]
        airports.append(entry)
    record["airports"] = airports
    record["updatedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(record, indent=2))


def download_chart(metadata, destination, cache_dir, sas, include_dark, airport=None, category_name=None):
    guid = metadata["guid"]
    pages = cached_chart(guid, destination, cache_dir, include_dark)
    cache_hit = pages is not None
    if pages is None:
        response = planner.planner_request("/api/v1/charts/pages/%s" % urllib.parse.quote(guid, safe=""))
        pages = []
        for index, page in enumerate(response.get("pages", [])):
            images = download_page(guid, index, page, destination, cache_dir, sas, include_dark)
            if images.get("light"):
                pages.append(images)
    if not pages:
        return None, cache_hit
    write_chart_cache_metadata(metadata, pages, cache_dir, airport, category_name)
    chart = dict(metadata)
    chart["pages"] = pages
    return chart, cache_hit


def emit_progress(airport_number, total_airports, completed=0, total_charts=1):
    if not MACHINE_PROGRESS:
        return
    chart_fraction = float(completed) / max(1, total_charts)
    overall = 0.90 * (((airport_number - 1) + chart_fraction) / max(1, total_airports))
    print("@@SKYCHARTS_PROGRESS %.6f" % min(1.0, max(0.0, overall)), flush=True)


def download_airport(airport, destination, cache_dir, workers=8, include_dark=False, airport_number=1, total_airports=1):
    catalog = planner.chart_catalog(airport["fsid"])
    sas = planner.planner_request("/api/v1/charts-sas", expect_json=False).lstrip("?")
    ordered = []
    futures = {}
    completed = 0
    total_charts = sum(len(category["charts"]) for category in catalog["categories"])
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for category_index, category in enumerate(catalog["categories"]):
            for chart_index, metadata in enumerate(category["charts"]):
                future = executor.submit(download_chart, metadata, destination, cache_dir, sas, include_dark, airport, category["name"])
                futures[future] = (category_index, chart_index, category["name"])
        for future in as_completed(futures):
            category_index, chart_index, category_name = futures[future]
            chart, cache_hit = future.result()
            completed += 1
            print("  charts %d/%d • %s • %s" % (completed, total_charts, chart["name"] if chart else "unavailable", "cached" if cache_hit else "downloaded"), flush=True)
            emit_progress(airport_number, total_airports, completed, total_charts)
            if chart:
                ordered.append((category_index, chart_index, category_name, chart))
    categories_by_index = {}
    for category_index, chart_index, category_name, chart in sorted(ordered):
        entry = categories_by_index.setdefault(category_index, {"name": category_name, "charts": []})
        entry["charts"].append(chart)
    categories = [categories_by_index[key] for key in sorted(categories_by_index)]
    result = dict(airport)
    result["categories"] = categories
    return result


def ensure_csv(url, path, refresh=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if refresh or not path.exists():
        print("Downloading %s…" % path.stem)
        with urllib.request.urlopen(url, timeout=60) as response:
            path.write_bytes(response.read())


def location_names(cache_dir, refresh=False):
    countries_path = cache_dir / "ourairports-countries.csv"
    regions_path = cache_dir / "ourairports-regions.csv"
    ensure_csv(COUNTRIES_CSV, countries_path, refresh)
    ensure_csv(REGIONS_CSV, regions_path, refresh)
    countries = {}
    with countries_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            countries[row.get("code", "").upper()] = {
                "countryName": row.get("name") or row.get("code"),
                "continent": CONTINENT_NAMES.get(row.get("continent", "").upper(), row.get("continent") or ""),
            }
    regions = {}
    with regions_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            regions[row.get("code", "").upper()] = row.get("name") or row.get("code")
    return countries, regions


def country_airports(country, cache, airport_types, refresh=False):
    cache.parent.mkdir(parents=True, exist_ok=True)
    ensure_csv(AIRPORTS_CSV, cache, refresh)
    countries, regions = location_names(cache.parent, refresh)
    allowed = None if "all" in airport_types else set(airport_types)
    with cache.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        values = {}
        for row in rows:
            if row.get("iso_country", "").upper() != country.upper():
                continue
            if allowed is not None and row.get("type") not in allowed:
                continue
            ident = (row.get("gps_code") or row.get("ident") or "").strip().upper()
            if len(ident) == 4 and ident.isalnum():
                values[ident] = {
                    "country": row.get("iso_country", "").upper(),
                    "region": row.get("iso_region", ""),
                    "regionName": display_region(regions.get(row.get("iso_region", "").upper(), row.get("iso_region", ""))),
                    "city": display_city(row.get("municipality", "")),
                }
                values[ident].update(countries.get(values[ident]["country"], {}))
        return [(ident, values[ident]) for ident in sorted(values)]


def selected_airports(idents, cache):
    ensure_csv(AIRPORTS_CSV, cache)
    countries, regions = location_names(cache.parent)
    wanted = {ident.upper() for ident in idents}
    locations = {}
    with cache.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ident = (row.get("gps_code") or row.get("ident") or "").strip().upper()
            if ident not in wanted:
                continue
            country = row.get("iso_country", "").upper()
            locations[ident] = {
                "country": country,
                "region": row.get("iso_region", ""),
                "regionName": display_region(regions.get(row.get("iso_region", "").upper(), row.get("iso_region", ""))),
                "city": display_city(row.get("municipality", "")),
            }
            locations[ident].update(countries.get(country, {}))
    return [(ident.upper(), locations.get(ident.upper(), {})) for ident in idents]


def write_cache_index(cache_dir):
    charts = []
    for metadata_path in cache_dir.glob("*/metadata.json"):
        try:
            metadata = json.loads(metadata_path.read_text())
            entry = {"guid": metadata.get("guid"), "pages": len(metadata.get("pages", []))}
            for key in ("name", "type", "airports"):
                if metadata.get(key):
                    entry[key] = metadata[key]
            charts.append(entry)
        except (OSError, ValueError):
            pass
    (cache_dir / "index.json").write_text(json.dumps({"schemaVersion": 1, "charts": charts}, indent=2))


def seed_cache_from_pack(pack_dir, cache_dir):
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.exists():
        return 0
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return 0
    seeded = 0
    for airport in manifest.get("airports", []):
        for category in airport.get("categories", []):
            for chart in category.get("charts", []):
                guid = chart.get("guid")
                pages = chart.get("pages", [])
                if not guid or not pages:
                    continue
                available = []
                for page in pages:
                    cached_page = {}
                    for theme in ("light", "dark"):
                        relative = page.get(theme)
                        source = pack_dir / relative if relative else None
                        if source and source.is_file():
                            link_or_copy(source, cache_dir / relative)
                            cached_page[theme] = relative
                    if cached_page.get("light"):
                        available.append(cached_page)
                if len(available) == len(pages):
                    write_chart_cache_metadata(chart, available, cache_dir, airport, category.get("name"))
                    seeded += 1
    return seeded


def bundle_airport_maps(airports, destination, workers=4, cache_dir=None):
    """Add one reusable offline vector map to every airport pack entry."""
    if not airports:
        return 0
    map_root = destination / "maps"
    map_root.mkdir(parents=True, exist_ok=True)
    cache_dir = pathlib.Path(cache_dir or ROOT / "work" / "airport-map-cache")

    def build(airport):
        ident = airport["ident"].upper()
        result, cached = skycharts_airport_map.build_airport_map(ident, cache_dir=cache_dir)
        return airport, ident, result, cached

    completed = 0
    finished = 0
    pool_size = max(1, min(int(workers or 1), 4, len(airports)))
    print("Adding airport maps (%d parallel worker%s)…" % (pool_size, "" if pool_size == 1 else "s"), flush=True)
    with ThreadPoolExecutor(max_workers=pool_size) as executor:
        futures = {executor.submit(build, airport): airport for airport in airports}
        for future in as_completed(futures):
            airport = futures[future]
            ident = airport.get("ident", "UNKNOWN")
            try:
                airport, ident, result, cached = future.result()
                relative = pathlib.Path("maps") / (ident + ".json")
                (destination / relative).write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
                airport["map"] = relative.as_posix()
                completed += 1
                print("  %s airport map %s" % (ident, "reused" if cached else "downloaded"), flush=True)
            except Exception as error:
                print("  %s airport map unavailable: %s" % (ident, error), flush=True)
            finished += 1
            if MACHINE_PROGRESS:
                print("@@SKYCHARTS_PROGRESS %.6f" % (0.90 + 0.09 * finished / len(airports)), flush=True)
    return completed


def build_pack(args, airport_records, country=None):
    os.environ["MSFS_COOKIE_FILE"] = str(pathlib.Path(args.cookie_file).expanduser())
    output = pathlib.Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = pathlib.Path(args.cache_dir).expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    seeded = seed_cache_from_pack(output, cache_dir) if output.exists() else 0
    if seeded:
        print("Seeded reusable cache from %d existing charts" % seeded)
    temp = pathlib.Path(tempfile.mkdtemp(prefix="skycharts-pack-", dir=str(output.parent)))
    airports = []
    try:
        records = list(airport_records)
        if getattr(args, "limit", None):
            records = records[:args.limit]
        total = len(records)
        for number, record in enumerate(records, 1):
            ident, location = record if isinstance(record, tuple) else (record, {})
            print("[%d/%d] %s" % (number, total, ident), flush=True)
            emit_progress(number, total)
            airport = find_airport(ident)
            if not airport:
                print("  skipped: planner airport not found", flush=True)
                emit_progress(number + 1, total)
                continue
            try:
                airport.update(location)
                downloaded = download_airport(airport, temp, cache_dir, args.workers, args.include_dark, number, total)
            except Exception as error:
                print("  skipped: %s" % error, flush=True)
                emit_progress(number + 1, total)
                continue
            if downloaded["categories"]:
                airports.append(downloaded)
                print("  %d categories" % len(downloaded["categories"]), flush=True)
            emit_progress(number + 1, total)
        mapped = bundle_airport_maps(airports, temp, min(args.workers, 4))
        manifest = {
            "schemaVersion": 1,
            "packId": safe_name(args.pack_id),
            "name": args.name,
            "country": country,
            "provider": "LIDO",
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "airports": airports,
        }
        (temp / "pack.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        write_cache_index(cache_dir)
        if output.exists():
            shutil.rmtree(output)
        temp.rename(output)
        print("Created %s with %d airports and %d airport maps" % (output, len(airports), mapped))
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def install_pack(args):
    source = pathlib.Path(args.pack).expanduser().resolve()
    if not (source / "pack.json").exists():
        raise SystemExit("pack.json not found")
    pack_id = json.loads((source / "pack.json").read_text())["packId"]
    remote_root = "/var/mobile/Library/SkyCharts/ChartPacks"
    ssh_options = ["-oHostKeyAlgorithms=+ssh-rsa", "-oPubkeyAcceptedAlgorithms=+ssh-rsa"]
    subprocess.check_call(["ssh", "-tt"] + ssh_options + ["root@" + args.host, "mkdir -p %s" % remote_root])
    subprocess.check_call(["scp", "-O", "-r"] + ssh_options + [str(source), "root@%s:%s/%s" % (args.host, remote_root, pack_id)])
    subprocess.check_call(["ssh", "-tt"] + ssh_options + ["root@" + args.host, "chown -R mobile:mobile %s/%s; chmod -R u+rwX,go-rwx %s/%s" % (remote_root, pack_id, remote_root, pack_id)])
    print("Installed chart pack %s on %s" % (pack_id, args.host))


def main():
    parser = argparse.ArgumentParser(description="Build SkyCharts offline chart packs")
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--cookie-file", required=True)
    common.add_argument("--output", required=True)
    common.add_argument("--pack-id", required=True)
    common.add_argument("--name", required=True)
    common.add_argument("--include-dark", action="store_true", help="also download dark chart PNGs")
    common.add_argument("--workers", type=int, default=8, help="parallel chart workers (default: 8)")
    common.add_argument("--cache-dir", default=str(ROOT / "work" / "chart-cache"), help="persistent reusable asset cache")
    airport = sub.add_parser("airport", parents=[common])
    airport.add_argument("idents", nargs="+")
    country = sub.add_parser("country", parents=[common])
    country.add_argument("country")
    country.add_argument("--types", default="large_airport,medium_airport")
    country.add_argument("--limit", type=int)
    country.add_argument("--refresh-airports", action="store_true")
    install = sub.add_parser("install")
    install.add_argument("pack")
    install.add_argument("--host", required=True)
    args = parser.parse_args()
    if args.command == "airport":
        cache=ROOT/"work"/"ourairports-airports.csv"
        build_pack(args, selected_airports(args.idents, cache))
    elif args.command == "country":
        cache=ROOT/"work"/"ourairports-airports.csv"
        records=country_airports(args.country,cache,args.types.split(","),args.refresh_airports)
        build_pack(args, records, args.country.upper())
    else:
        install_pack(args)


if __name__ == "__main__":
    main()
