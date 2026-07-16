#!/usr/bin/env python3
"""Friendly interactive launcher for SkyCharts Mac tools."""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys

from skycharts_auth import browser_login

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def ask(label, default=None):
    suffix = " [%s]" % default if default else ""
    value = input("%s%s: " % (label, suffix)).strip()
    return value or default


def run(command):
    print("\n$ " + " ".join(str(item) for item in command) + "\n")
    return subprocess.call([str(item) for item in command], cwd=str(ROOT))


def agent(cookie, port):
    return run([PYTHON, ROOT / "tools" / "skycharts_pack_agent.py", "--cookie-file", cookie, "--port", str(port)])


def country(cookie, code, output, name, pack_id, limit, workers):
    command = [PYTHON, ROOT / "tools" / "skycharts_downloader.py", "country", code.upper(), "--cookie-file", cookie, "--pack-id", pack_id, "--name", name, "--output", output, "--workers", str(workers)]
    if limit:
        command += ["--limit", str(limit)]
    return run(command)


def airports(cookie, idents, output, name, pack_id, workers):
    return run([PYTHON, ROOT / "tools" / "skycharts_downloader.py", "airport"] + [item.upper() for item in idents] + ["--cookie-file", cookie, "--pack-id", pack_id, "--name", name, "--output", output, "--workers", str(workers)])


def install(pack, host):
    return run([PYTHON, ROOT / "tools" / "skycharts_downloader.py", "install", pack, "--host", host])


def airport_map(ident, output, refresh=False):
    command = [PYTHON, ROOT / "tools" / "skycharts_airport_map.py", ident.upper(), "--output", output]
    if refresh:
        command.append("--refresh")
    return run(command)


def format_bytes(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return "%d %s" % (value, unit) if unit == "B" else "%.1f %s" % (value, unit)
        value /= 1024


def airport_map_cache_entries(cache_dir=None):
    cache_dir = pathlib.Path(cache_dir or ROOT / "work" / "airport-map-cache")
    entries = []
    for path in sorted(cache_dir.glob("*.json")) if cache_dir.exists() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
        entries.append({
            "ident": str(data.get("ident") or path.stem).upper(),
            "name": str(data.get("name") or "Unreadable cache entry"),
            "generated": str(data.get("generatedAt") or "")[:10] or "unknown date",
            "features": len(data.get("features", [])) if isinstance(data.get("features"), list) else 0,
            "stands": counts.get("parking_position", 0),
            "size": path.stat().st_size,
            "path": path,
        })
    return entries


def delete_airport_map_cache(idents, cache_dir=None):
    requested = {str(ident).upper() for ident in idents}
    removed = []
    for entry in airport_map_cache_entries(cache_dir):
        if entry["ident"] not in requested:
            continue
        entry["path"].unlink()
        removed.append(entry["ident"])
    return removed


def chart_cache_entries(cache_dir=None, manifest_roots=None):
    cache_dir = pathlib.Path(cache_dir or ROOT / "work" / "chart-cache")
    entries = {}
    if cache_dir.exists():
        for metadata_path in cache_dir.glob("*/metadata.json"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                metadata = {}
            guid = metadata_path.parent.name
            if not guid:
                continue
            entry = {
                "guid": guid,
                "name": str(metadata.get("name") or ""),
                "type": str(metadata.get("type") or ""),
                "airports": {},
                "pages": 0,
                "size": metadata_path.stat().st_size,
                "metadata_path": metadata_path,
                "asset_dir": cache_dir / "charts" / guid,
            }
            for airport in metadata.get("airports", []) if isinstance(metadata.get("airports"), list) else []:
                if isinstance(airport, dict) and airport.get("ident"):
                    entry["airports"][str(airport["ident"]).upper()] = str(airport.get("name") or airport["ident"])
            assets = set()
            for page in metadata.get("pages", []) if isinstance(metadata.get("pages"), list) else []:
                for theme in ("light", "dark"):
                    relative = page.get(theme) if isinstance(page, dict) else None
                    if relative:
                        assets.add(cache_dir / relative)
            if entry["asset_dir"].exists():
                assets.update(path for path in entry["asset_dir"].iterdir() if path.is_file())
            entry["pages"] = len(assets)
            entry["size"] += sum(path.stat().st_size for path in assets if path.is_file())
            entries[guid] = entry

    roots = manifest_roots
    if roots is None:
        roots = (ROOT / "work" / "pack-agent", ROOT / "outputs")
    for root in (pathlib.Path(value) for value in roots):
        if not root.exists():
            continue
        for manifest_path in root.glob("**/pack.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for airport in manifest.get("airports", []):
                ident = str(airport.get("ident") or "").upper()
                if not ident:
                    continue
                airport_name = str(airport.get("name") or ident)
                for category in airport.get("categories", []):
                    for chart in category.get("charts", []):
                        entry = entries.get(str(chart.get("guid") or ""))
                        if not entry:
                            continue
                        entry["airports"][ident] = airport_name
                        if not entry["name"]:
                            entry["name"] = str(chart.get("name") or "")
                        if not entry["type"]:
                            entry["type"] = str(chart.get("type") or category.get("name") or "")
    for entry in entries.values():
        if not entry["airports"] or not entry["metadata_path"].exists():
            continue
        try:
            metadata = json.loads(entry["metadata_path"].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            metadata = {"guid": entry["guid"], "pages": []}
        current_airports = metadata.get("airports") if isinstance(metadata.get("airports"), list) else []
        current_by_ident = {str(value.get("ident") or "").upper(): value for value in current_airports if isinstance(value, dict) and value.get("ident")}
        changed = {ident: str(value.get("name") or ident) for ident, value in current_by_ident.items()} != entry["airports"]
        if changed:
            merged = []
            for ident, name in sorted(entry["airports"].items()):
                value = dict(current_by_ident.get(ident, {}))
                value.update({"ident": ident, "name": name})
                merged.append(value)
            metadata["airports"] = merged
        for key in ("name", "type"):
            if entry[key] and metadata.get(key) != entry[key]:
                metadata[key] = entry[key]
                changed = True
        if changed:
            entry["metadata_path"].write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return list(entries.values())


def chart_cache_airports(entries):
    airports = {}
    for entry in entries:
        for ident, name in entry["airports"].items():
            airport = airports.setdefault(ident, {"ident": ident, "name": name, "guids": set(), "pages": 0, "size": 0})
            if entry["guid"] in airport["guids"]:
                continue
            airport["guids"].add(entry["guid"])
            airport["pages"] += entry["pages"]
            airport["size"] += entry["size"]
    return airports


def rewrite_chart_cache_index(cache_dir):
    cache_dir = pathlib.Path(cache_dir)
    charts = []
    for entry in chart_cache_entries(cache_dir, manifest_roots=()):
        charts.append({"guid": entry["guid"], "pages": entry["pages"]})
    index = cache_dir / "index.json"
    if charts:
        index.write_text(json.dumps({"schemaVersion": 1, "charts": sorted(charts, key=lambda item: item["guid"])}, indent=2), encoding="utf-8")
    elif index.exists():
        index.unlink()


def delete_chart_cache_guids(guids, cache_dir=None):
    cache_dir = pathlib.Path(cache_dir or ROOT / "work" / "chart-cache")
    requested = {str(guid) for guid in guids}
    removed, removed_size = [], 0
    for entry in chart_cache_entries(cache_dir, manifest_roots=()):
        if entry["guid"] not in requested:
            continue
        removed_size += entry["size"]
        if entry["metadata_path"].parent.exists():
            shutil.rmtree(str(entry["metadata_path"].parent))
        if entry["asset_dir"].exists():
            shutil.rmtree(str(entry["asset_dir"]))
        removed.append(entry["guid"])
    rewrite_chart_cache_index(cache_dir)
    return removed, removed_size


def delete_chart_cache_airports(idents, cache_dir=None, manifest_roots=None):
    selected = {str(ident).upper() for ident in idents}
    entries = chart_cache_entries(cache_dir, manifest_roots)
    removable = []
    for entry in entries:
        owners = set(entry["airports"])
        if owners and owners.issubset(selected):
            removable.append(entry["guid"])
    removed, removed_size = delete_chart_cache_guids(removable, cache_dir)
    return removed, removed_size


def print_chart_airports(airports, query=""):
    query = query.strip().upper()
    matches = [value for value in airports.values() if not query or query in value["ident"] or query in value["name"].upper()]
    matches.sort(key=lambda item: item["ident"])
    if not matches:
        print("No cached airports matched %s." % query)
        return
    for airport in matches[:50]:
        print("%s — %s" % (airport["ident"], airport["name"]))
        print("   %d charts • %d pages • %s" % (len(airport["guids"]), airport["pages"], format_bytes(airport["size"])))
    if len(matches) > 50:
        print("…and %d more; enter a narrower search." % (len(matches) - 50))


def manage_chart_cache():
    while True:
        entries = chart_cache_entries()
        airports = chart_cache_airports(entries)
        unknown = [entry for entry in entries if not entry["airports"]]
        total_size = sum(entry["size"] for entry in entries)
        print("\nCached Chart Asset Manager")
        print("==========================")
        print("%d airports • %d charts • %d pages • %s" % (
            len(airports), len(entries), sum(entry["pages"] for entry in entries), format_bytes(total_size)))
        if unknown:
            print("%d legacy charts are not linked to a known airport." % len(unknown))
        if not entries:
            print("Chart cache is empty.\n")
            return
        print("""
1. Find/list cached airports
2. Delete chart cache by airport ICAO
3. Delete unidentified legacy chart cache
4. Delete all cached chart assets
0. Back
""")
        choice = input("Choose an option: ").strip()
        if choice == "0":
            return
        if choice == "1":
            query = ask("ICAO or airport-name filter (blank lists first 50)", "")
            print_chart_airports(airports, query or "")
        elif choice == "2":
            codes = [value.upper() for value in ask("Airport ICAO codes separated by spaces", "").replace(",", " ").split()]
            selected = [airports[code] for code in codes if code in airports]
            if not selected:
                print("No matching cached airports were selected.")
                continue
            for airport in selected:
                print("%s — %d charts • %s" % (airport["ident"], len(airport["guids"]), format_bytes(airport["size"])))
            print("This removes reusable cache links only; exported packs, Pack Agent jobs, and iPad content remain unchanged.")
            if not ask("Delete cached charts for %s? (y/N)" % ", ".join(item["ident"] for item in selected), "N").lower().startswith("y"):
                continue
            removed, size = delete_chart_cache_airports((item["ident"] for item in selected))
            print("Deleted %d chart cache entries (%s logical size)." % (len(removed), format_bytes(size)))
        elif choice == "3":
            if not unknown:
                print("There are no unidentified chart cache entries.")
                continue
            if not ask("Delete %d unidentified chart entries (%s)? (y/N)" % (len(unknown), format_bytes(sum(item["size"] for item in unknown))), "N").lower().startswith("y"):
                continue
            removed, size = delete_chart_cache_guids(item["guid"] for item in unknown)
            print("Deleted %d unidentified entries (%s logical size)." % (len(removed), format_bytes(size)))
        elif choice == "4":
            print("This clears only the reusable chart cache. Exported packs, Pack Agent jobs, and iPad content are preserved.")
            if not ask("Delete all %d cached charts? Type DELETE to confirm" % len(entries), "N") == "DELETE":
                continue
            removed, size = delete_chart_cache_guids(item["guid"] for item in entries)
            print("Deleted %d chart cache entries (%s logical size)." % (len(removed), format_bytes(size)))
        else:
            print("Unknown option.")


def manage_airport_map_cache():
    while True:
        entries = airport_map_cache_entries()
        print("\nCached Airport Map Manager")
        print("==========================")
        if not entries:
            print("No cached airport maps.\n")
            return
        total = sum(item["size"] for item in entries)
        for index, entry in enumerate(entries, 1):
            print("%d. %s — %s" % (index, entry["ident"], entry["name"]))
            print("   %s • %d features • %d stands • %s" % (
                format_bytes(entry["size"]), entry["features"], entry["stands"], entry["generated"]))
        print("\nTotal: %d maps • %s" % (len(entries), format_bytes(total)))
        print("A. Delete all cached airport maps")
        print("0. Back")
        selection = input("Delete map number(s), e.g. 1 3: ").strip()
        if selection == "0" or not selection:
            return
        if selection.lower() == "a":
            selected = entries
        else:
            selected = []
            for value in selection.replace(",", " ").split():
                try:
                    number = int(value)
                except ValueError:
                    continue
                if 1 <= number <= len(entries) and entries[number - 1] not in selected:
                    selected.append(entries[number - 1])
        if not selected:
            print("No valid airport-map entries were selected.")
            continue
        names = ", ".join(item["ident"] for item in selected)
        print("This deletes only the reusable Mac cache; exported files and iPad content are unchanged.")
        if not ask("Delete %s? (y/N)" % names, "N").lower().startswith("y"):
            continue
        removed = delete_airport_map_cache(item["ident"] for item in selected)
        print("Deleted %d cached airport map(s): %s\n" % (len(removed), ", ".join(removed)))


def cache_status():
    index = ROOT / "work" / "chart-cache" / "index.json"
    charts = []
    if index.exists():
        data = json.loads(index.read_text())
        charts = data.get("charts", [])
    print("\nCached charts: %d" % len(charts))
    print("Cached pages:  %d" % sum(item.get("pages", 0) for item in charts))
    if index.exists():
        subprocess.call(["du", "-sh", str(index.parent)])
    maps = airport_map_cache_entries()
    print("Cached airport maps: %d (%s)" % (len(maps), format_bytes(sum(item["size"] for item in maps))))
    print()


def ensure_cookie(cookie):
    path = pathlib.Path(cookie)
    if path.is_file() and path.stat().st_size:
        return True
    print("\nNo saved planner authentication was found. Starting browser login…\n")
    return browser_login(path)


def interactive():
    cookie = str(ROOT / "work" / "msfs-cookie.txt")
    while True:
        print("""
SkyCharts Mac Client
===================
1. Sign in / refresh planner authentication
2. Start Pack Agent for the iPad
3. Download a country pack on this Mac
4. Download selected airports
5. Download an interactive airport map
6. Install an existing pack over SSH
7. Show reusable cache status
8. Manage cached airport maps
9. Manage cached chart assets
0. Quit
""")
        choice = input("Choose an option: ").strip()
        if choice == "0":
            return 0
        if choice == "1":
            browser_login(cookie)
        elif choice == "2":
            if not ensure_cookie(cookie):
                continue
            port = int(ask("Agent port", "8770"))
            agent(cookie, port)
        elif choice == "3":
            if not ensure_cookie(cookie):
                continue
            code = ask("Two-letter country code", "CA").upper()
            pack_id = ask("Package ID", code.lower())
            name = ask("Display name", code + " Charts")
            output = ask("Output directory", str(ROOT / "outputs" / pack_id))
            limit_text = ask("Maximum airports (blank means all)", "")
            workers = int(ask("Parallel chart workers", "8"))
            country(cookie, code, output, name, pack_id, int(limit_text) if limit_text else None, workers)
        elif choice == "4":
            if not ensure_cookie(cookie):
                continue
            idents = ask("Airport codes separated by spaces", "KJFK").split()
            pack_id = ask("Package ID", "custom-airports")
            name = ask("Display name", "Custom Airports")
            output = ask("Output directory", str(ROOT / "outputs" / pack_id))
            workers = int(ask("Parallel chart workers", "8"))
            airports(cookie, idents, output, name, pack_id, workers)
        elif choice == "5":
            ident = ask("Four-character airport ICAO code", "KJFK").upper()
            output = ask("Output file", str(ROOT / "outputs" / (ident + "-airport-map.json")))
            refresh = ask("Refresh cached OSM data? (y/N)", "N").lower().startswith("y")
            airport_map(ident, output, refresh)
        elif choice == "6":
            pack = ask("Pack directory", str(ROOT / "outputs"))
            host = ask("iPad IP address", "192.168.2.19")
            install(pack, host)
        elif choice == "7":
            cache_status()
        elif choice == "8":
            manage_airport_map_cache()
        elif choice == "9":
            manage_chart_cache()
        else:
            print("Unknown option.")


def main():
    parser = argparse.ArgumentParser(description="SkyCharts Mac Client")
    parser.add_argument("--menu", action="store_true", help="open the interactive menu")
    args = parser.parse_args()
    return interactive()


if __name__ == "__main__":
    raise SystemExit(main())
