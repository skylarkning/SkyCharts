#!/usr/bin/env python3
"""Friendly interactive launcher for SkyCharts Mac tools."""

import argparse
import getpass
import json
import os
import pathlib
import shutil
import subprocess
import sys

from skycharts_auth import browser_login

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON = sys.executable
SSH_OPTIONS = [
    "-o", "ConnectTimeout=10",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "HostKeyAlgorithms=+ssh-rsa",
    "-o", "KexAlgorithms=+diffie-hellman-group14-sha1",
]
BREW_REQUIREMENTS = (
    ("python3", "Python 3 runtime", "python@3.14"),
    ("make", "Build driver", "make"),
    ("git", "Git", "git"),
    ("curl", "HTTP downloader", "curl"),
    ("ssh", "SSH client", "openssh"),
    ("scp", "SCP client", "openssh"),
    ("sshpass", "Non-interactive iPad password helper", "sshpass"),
)


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


def latest_deb(output_dir=None):
    output_dir = pathlib.Path(output_dir or ROOT / "outputs")
    matches = list(output_dir.glob("SkyCharts-*-ios6-armv7.deb")) if output_dir.exists() else []
    return max(matches, key=lambda path: path.stat().st_mtime) if matches else None


def authenticated_command(command, password):
    environment = os.environ.copy()
    if password:
        if not shutil.which("sshpass"):
            raise RuntimeError("sshpass is missing. Run Mac environment repair from the SkyCharts menu.")
        environment["SSHPASS"] = password
        return ["sshpass", "-e"] + list(command), environment
    return list(command), environment


def run_private(command, password, acceptable=(0,)):
    prepared, environment = authenticated_command(command, password)
    print("\n$ " + " ".join(str(item) for item in prepared) + "\n")
    status = subprocess.call([str(item) for item in prepared], cwd=str(ROOT), env=environment)
    if status not in acceptable:
        raise RuntimeError("Command failed with status %d." % status)
    return status


def install_deb(deb, host, password="alpine"):
    deb = pathlib.Path(deb).expanduser().resolve()
    if not deb.is_file():
        raise RuntimeError("DEB package was not found: %s" % deb)
    if deb.suffix.lower() != ".deb":
        raise RuntimeError("Selected file is not a DEB package: %s" % deb)
    missing = [command for command in ("ssh", "scp") if not shutil.which(command)]
    if password and not shutil.which("sshpass"):
        missing.append("sshpass")
    if missing:
        raise RuntimeError("Missing Mac command%s: %s. Run Mac environment repair first." % (
            "s" if len(missing) != 1 else "", ", ".join(missing)))

    print("\nInstalling %s on root@%s" % (deb.name, host))
    print("1/3 Transferring DEB package…")
    run_private(["scp", "-O"] + SSH_OPTIONS + [str(deb), "root@%s:/tmp/SkyCharts.deb" % host], password)

    print("2/3 Migrating old SkyCharts data and installing…")
    remote_install = (
        "set -e; "
        "mkdir -p /var/mobile/Library/SkyCharts/ChartPacks; "
        "for app in /var/mobile/Applications/*/SkyCharts.app; do "
        "[ -d \"$app\" ] || continue; container=${app%/SkyCharts.app}; "
        "if [ -d \"$container/Documents/SkyCharts/ChartPacks\" ]; then "
        "cp -Rp \"$container/Documents/SkyCharts/ChartPacks/.\" /var/mobile/Library/SkyCharts/ChartPacks/ 2>/dev/null || true; fi; "
        "rm -rf \"$container\"; done; "
        "killall SkyCharts >/dev/null 2>&1 || true; "
        "dpkg -i /tmp/SkyCharts.deb; "
        "chown -R root:wheel /Applications/SkyCharts.app; "
        "chmod -R a+rX /Applications/SkyCharts.app; "
        "chown -R mobile:mobile /var/mobile/Library/SkyCharts; "
        "su mobile -c /usr/bin/uicache; "
        "rm -f /tmp/SkyCharts.deb"
    )
    run_private(["ssh"] + SSH_OPTIONS + ["root@%s" % host, remote_install], password)

    print("3/3 Restarting SpringBoard…")
    run_private(
        ["ssh"] + SSH_OPTIONS + ["root@%s" % host, "killall SpringBoard >/dev/null 2>&1 || true"],
        password,
        acceptable=(0, 255),
    )
    print("\nSkyCharts DEB installation completed. The existing offline chart library was preserved.\n")
    return 0


def playwright_status(python=PYTHON):
    script = (
        "from pathlib import Path; "
        "from playwright.sync_api import sync_playwright; "
        "p=sync_playwright().start(); path=p.chromium.executable_path; p.stop(); "
        "raise SystemExit(0 if Path(path).is_file() else 1)"
    )
    return subprocess.call(
        [str(python), "-c", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def environment_status(which=None, python=PYTHON):
    which = which or shutil.which
    status = []
    for command, label, formula in BREW_REQUIREMENTS:
        path = which(command)
        status.append({
            "command": command,
            "label": label,
            "formula": formula,
            "available": bool(path),
            "path": path or "",
        })
    status.append({
        "command": "playwright",
        "label": "Browser sign-in support",
        "formula": "",
        "available": playwright_status(python),
        "path": str(pathlib.Path(python).resolve()),
    })
    theos = pathlib.Path(os.environ.get("THEOS", pathlib.Path.home() / "theos")).expanduser()
    status.append({
        "command": "theos",
        "label": "Theos build system",
        "formula": "",
        "available": (theos / "makefiles" / "common.mk").is_file(),
        "path": str(theos),
    })
    sdks = sorted((theos / "sdks").glob("iPhoneOS*.sdk")) if (theos / "sdks").exists() else []
    status.append({
        "command": "ios-sdk",
        "label": "Theos iPhoneOS SDK",
        "formula": "",
        "available": bool(sdks),
        "path": ", ".join(path.name for path in sdks),
    })
    xcrun = which("xcrun")
    status.append({
        "command": "xcode-cli",
        "label": "Xcode command-line tools",
        "formula": "",
        "available": bool(xcrun),
        "path": xcrun or "",
    })
    return status


def print_environment_status(status=None):
    status = status or environment_status()
    print("\nSkyCharts Mac Environment")
    print("=========================\n")
    for item in status:
        state = "READY" if item["available"] else "MISSING"
        detail = " — %s" % item["path"] if item["available"] and item["path"] else ""
        print("[%s] %s%s" % (state, item["label"], detail))
    missing = [item for item in status if not item["available"]]
    print("\n%s\n" % ("Environment is ready." if not missing else "%d component(s) need attention." % len(missing)))
    return not missing


def install_homebrew_requirements(status=None):
    status = status or environment_status()
    formulas = []
    for item in status:
        if not item["available"] and item["formula"] and item["formula"] not in formulas:
            formulas.append(item["formula"])
    if not formulas:
        print("No missing Homebrew packages were found.")
        return 0
    if not shutil.which("brew"):
        print("Homebrew is not installed. Install it from https://brew.sh and run this option again.")
        return 1
    print("Homebrew will install: %s" % ", ".join(formulas))
    if not ask("Continue? (y/N)", "N").lower().startswith("y"):
        return 0
    return run(["brew", "install"] + formulas)


def install_browser_environment():
    venv = ROOT / ".venv"
    venv_python = venv / "bin" / "python3"
    print("This creates or repairs .venv and installs Playwright with Chromium for planner browser login.")
    if not ask("Continue? (y/N)", "N").lower().startswith("y"):
        return 0
    if not venv_python.exists():
        status = run([PYTHON, "-m", "venv", venv])
        if status:
            return status
    status = run([venv_python, "-m", "pip", "install", "--upgrade", "pip", "playwright"])
    if status:
        return status
    return run([venv_python, "-m", "playwright", "install", "chromium"])


def manage_environment():
    while True:
        status = environment_status()
        print_environment_status(status)
        print("""1. Install missing command-line packages with Homebrew
2. Install/repair browser sign-in environment
0. Back
""")
        choice = input("Choose an option: ").strip()
        if choice == "0":
            return
        if choice == "1":
            install_homebrew_requirements(status)
        elif choice == "2":
            install_browser_environment()
        else:
            print("Unknown option.")


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
        if path.name.endswith(".unavailable.json"):
            continue
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
            "stands": counts.get("parking_position", 0) + counts.get("gate", 0),
            "source": str(data.get("source") or "unknown source"),
            "size": path.stat().st_size,
            "path": path,
        })
    return entries


def delete_airport_map_cache(idents, cache_dir=None):
    requested = {str(ident).upper() for ident in idents}
    cache_dir = pathlib.Path(cache_dir or ROOT / "work" / "airport-map-cache")
    removed = []
    for entry in airport_map_cache_entries(cache_dir):
        if entry["ident"] not in requested:
            continue
        entry["path"].unlink()
        removed.append(entry["ident"])
    for ident in requested:
        marker = cache_dir / (ident + ".unavailable.json")
        if marker.exists():
            marker.unlink()
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
            print("   %s • %d features • %d stands • %s • %s" % (
                format_bytes(entry["size"]), entry["features"], entry["stands"], entry["source"], entry["generated"]))
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


def airport_package_cache_entries(chart_entries=None, map_entries=None):
    chart_entries = list(chart_entries if chart_entries is not None else chart_cache_entries())
    map_entries = list(map_entries if map_entries is not None else airport_map_cache_entries())
    packages = {}
    for ident, chart in chart_cache_airports(chart_entries).items():
        packages[ident] = {
            "ident": ident,
            "name": chart["name"],
            "guids": set(chart["guids"]),
            "charts": len(chart["guids"]),
            "pages": chart["pages"],
            "chart_size": chart["size"],
            "map_size": 0,
            "map_features": 0,
            "stands": 0,
            "map_generated": "",
            "has_map": False,
        }
    for airport_map in map_entries:
        ident = airport_map["ident"]
        package = packages.setdefault(ident, {
            "ident": ident,
            "name": airport_map["name"],
            "guids": set(),
            "charts": 0,
            "pages": 0,
            "chart_size": 0,
            "map_size": 0,
            "map_features": 0,
            "stands": 0,
            "map_generated": "",
            "has_map": False,
        })
        if not package["name"] or package["name"] == ident:
            package["name"] = airport_map["name"]
        package.update({
            "map_size": airport_map["size"],
            "map_features": airport_map["features"],
            "stands": airport_map["stands"],
            "map_generated": airport_map["generated"],
            "has_map": True,
        })
    for package in packages.values():
        package["size"] = package["chart_size"] + package["map_size"]
    return packages


def delete_airport_package_cache(idents, chart_cache_dir=None, map_cache_dir=None, manifest_roots=None):
    selected = sorted({str(ident).upper() for ident in idents})
    charts, chart_size = delete_chart_cache_airports(selected, chart_cache_dir, manifest_roots)
    maps = delete_airport_map_cache(selected, map_cache_dir)
    return {"airports": selected, "charts": charts, "maps": maps, "chart_size": chart_size}


def print_airport_packages(packages, query=""):
    query = query.strip().upper()
    matches = [value for value in packages.values() if not query or query in value["ident"] or query in value["name"].upper()]
    matches.sort(key=lambda item: item["ident"])
    if not matches:
        print("No cached airport packages matched %s." % query)
        return
    for package in matches[:50]:
        map_text = "%d map features" % package["map_features"] if package["has_map"] else "map unavailable"
        print("%s — %s" % (package["ident"], package["name"]))
        print("   %d charts • %d pages • %s • %s" % (
            package["charts"], package["pages"], map_text, format_bytes(package["size"])))
    if len(matches) > 50:
        print("…and %d more; enter a narrower search." % (len(matches) - 50))


def manage_airport_package_cache():
    while True:
        chart_entries = chart_cache_entries()
        map_entries = airport_map_cache_entries()
        packages = airport_package_cache_entries(chart_entries, map_entries)
        unknown = [entry for entry in chart_entries if not entry["airports"]]
        physical_size = sum(entry["size"] for entry in chart_entries) + sum(entry["size"] for entry in map_entries)
        print("\nCached Airport Package Manager")
        print("==============================")
        print("%d airports • %d charts • %d maps • %s" % (
            len(packages), len(chart_entries), len(map_entries), format_bytes(physical_size)))
        if unknown:
            print("%d legacy charts are not linked to a known airport." % len(unknown))
        if not packages and not unknown:
            print("Airport package cache is empty.\n")
            return
        print("""
1. Find/list cached airport packages
2. Delete package cache by airport ICAO
3. Delete unidentified legacy chart cache
4. Delete all cached airport packages
0. Back
""")
        choice = input("Choose an option: ").strip()
        if choice == "0":
            return
        if choice == "1":
            print_airport_packages(packages, ask("ICAO or airport-name filter (blank lists first 50)", "") or "")
        elif choice == "2":
            codes = [value.upper() for value in ask("Airport ICAO codes separated by spaces", "").replace(",", " ").split()]
            selected = [packages[code] for code in codes if code in packages]
            if not selected:
                print("No matching cached airport packages were selected.")
                continue
            for package in selected:
                print("%s — %d charts • %s • %s" % (
                    package["ident"], package["charts"], "map cached" if package["has_map"] else "no map", format_bytes(package["size"])))
            print("This removes reusable chart and map cache entries together; exported packs, Pack Agent jobs, and iPad content remain unchanged.")
            if not ask("Delete cached package data for %s? (y/N)" % ", ".join(item["ident"] for item in selected), "N").lower().startswith("y"):
                continue
            result = delete_airport_package_cache(item["ident"] for item in selected)
            print("Deleted %d chart entries and %d airport maps (%s chart logical size)." % (
                len(result["charts"]), len(result["maps"]), format_bytes(result["chart_size"])))
        elif choice == "3":
            if not unknown:
                print("There are no unidentified chart cache entries.")
                continue
            if not ask("Delete %d unidentified chart entries (%s)? (y/N)" % (len(unknown), format_bytes(sum(item["size"] for item in unknown))), "N").lower().startswith("y"):
                continue
            removed, size = delete_chart_cache_guids(item["guid"] for item in unknown)
            print("Deleted %d unidentified entries (%s logical size)." % (len(removed), format_bytes(size)))
        elif choice == "4":
            print("This clears the reusable chart and airport-map caches. Exported packs, Pack Agent jobs, and iPad content are preserved.")
            if ask("Delete all cached airport packages? Type DELETE to confirm", "N") != "DELETE":
                continue
            removed_charts, size = delete_chart_cache_guids(item["guid"] for item in chart_entries)
            removed_maps = delete_airport_map_cache(item["ident"] for item in map_entries)
            print("Deleted %d chart entries and %d airport maps (%s chart logical size)." % (
                len(removed_charts), len(removed_maps), format_bytes(size)))
        else:
            print("Unknown option.")


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
    packages = airport_package_cache_entries(chart_cache_entries(), maps)
    print("Combined airport packages: %d" % len(packages))
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
5. Install an existing chart pack over SSH
6. Install a SkyCharts DEB package on an iPad
7. Check / repair the Mac environment
8. Show reusable cache status
9. Manage cached airport packages
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
            pack = ask("Pack directory", str(ROOT / "outputs"))
            host = ask("iPad IP address", "192.168.2.19")
            install(pack, host)
        elif choice == "6":
            default_deb = latest_deb()
            deb = ask("Path to DEB package", str(default_deb) if default_deb else str(ROOT / "outputs"))
            host = ask("iPad IP address", "192.168.2.19")
            password = getpass.getpass("iPad root password [alpine]: ") or "alpine"
            try:
                install_deb(deb, host, password)
            except RuntimeError as error:
                print("\nInstallation failed: %s\n" % error)
        elif choice == "7":
            manage_environment()
        elif choice == "8":
            cache_status()
        elif choice == "9":
            manage_airport_package_cache()
        else:
            print("Unknown option.")


def main():
    parser = argparse.ArgumentParser(description="SkyCharts Mac Client")
    parser.add_argument("--menu", action="store_true", help="open the interactive menu")
    subparsers = parser.add_subparsers(dest="command")
    installer = subparsers.add_parser("install-deb", help="install a SkyCharts DEB on a jailbroken iPad")
    installer.add_argument("deb", help="path to the SkyCharts DEB package")
    installer.add_argument("--host", default="192.168.2.19", help="iPad IP address")
    subparsers.add_parser("check-environment", help="audit the Mac environment without changing it")
    args = parser.parse_args()
    if args.command == "install-deb":
        password = os.environ.get("SKYCHARTS_IPAD_PASSWORD")
        if password is None:
            password = getpass.getpass("iPad root password [alpine]: ") or "alpine"
        try:
            return install_deb(args.deb, args.host, password)
        except RuntimeError as error:
            print("Installation failed: %s" % error, file=sys.stderr)
            return 1
    if args.command == "check-environment":
        return 0 if print_environment_status() else 1
    return interactive()


if __name__ == "__main__":
    raise SystemExit(main())
