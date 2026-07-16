#!/usr/bin/env python3
"""Friendly interactive launcher for SkyCharts Mac tools."""

import argparse
import json
import pathlib
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
        else:
            print("Unknown option.")


def main():
    parser = argparse.ArgumentParser(description="SkyCharts Mac Client")
    parser.add_argument("--menu", action="store_true", help="open the interactive menu")
    args = parser.parse_args()
    return interactive()


if __name__ == "__main__":
    raise SystemExit(main())
