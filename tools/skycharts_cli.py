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


def cache_status():
    index = ROOT / "work" / "chart-cache" / "index.json"
    if not index.exists():
        print("\nCache is empty. It will be created by the first download.\n")
        return
    data = json.loads(index.read_text())
    charts = data.get("charts", [])
    print("\nCached charts: %d" % len(charts))
    print("Cached pages:  %d" % sum(item.get("pages", 0) for item in charts))
    subprocess.call(["du", "-sh", str(index.parent)])
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
5. Install an existing pack over SSH
6. Show reusable cache status
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
            cache_status()
        else:
            print("Unknown option.")


def main():
    parser = argparse.ArgumentParser(description="SkyCharts Mac Client")
    parser.add_argument("--menu", action="store_true", help="open the interactive menu")
    args = parser.parse_args()
    return interactive()


if __name__ == "__main__":
    raise SystemExit(main())
