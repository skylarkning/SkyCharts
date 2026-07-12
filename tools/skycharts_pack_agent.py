#!/usr/bin/env python3
"""LAN download appliance for SkyCharts country chart packs."""

import argparse
import json
import pathlib
import re
import subprocess
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
JOBS = {}
LOCK = threading.Lock()


def public_job(job):
    return {key: value for key, value in job.items() if key not in ("process", "directory", "logPath")}


def watch_job(job_id):
    with LOCK:
        job = JOBS[job_id]
        process = job["process"]
        log_path = job["logPath"]
    with log_path.open("w", encoding="utf-8") as log:
        for line in process.stdout:
            log.write(line)
            log.flush()
            progress = line.strip()
            if progress:
                with LOCK:
                    job["progress"] = progress
                print("[%s] %s" % (job_id, progress), flush=True)
    code = process.wait()
    with LOCK:
        job = JOBS[job_id]
        if code == 0 and (job["directory"] / "pack.json").exists():
            job["status"] = "ready"
            job["manifest"] = "/packs/%s/pack.json" % job_id
        else:
            job["status"] = "failed"
            job["error"] = readable_failure(job["logPath"])
        job["finishedAt"] = time.time()


def readable_failure(log_path):
    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except OSError:
        return "Chart pack build failed; see the Mac Pack Agent log."
    for line in reversed(lines):
        if "RelayError:" in line:
            return line.split("RelayError:", 1)[1].strip()
        if "SystemExit:" in line:
            return line.split("SystemExit:", 1)[1].strip()
    for line in reversed(lines):
        text = line.strip()
        if text and not text.startswith(("File ", "Traceback", "^")):
            return "Chart pack build failed: " + text
    return "Chart pack build failed; see the Mac Pack Agent log."


def spawn_job(job_id, command, metadata):
    directory = ROOT / "work" / "pack-agent" / job_id
    directory.parent.mkdir(parents=True, exist_ok=True)
    log_path = directory.parent / (job_id + ".log")
    process = subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    job = {"id": job_id, "status": "building", "progress": "Starting downloader…", "createdAt": time.time(), "directory": directory, "process": process, "logPath": log_path}
    job.update(metadata)
    with LOCK:
        JOBS[job_id] = job
    threading.Thread(target=watch_job, args=(job_id,), daemon=True).start()
    return public_job(job)


def start_job(country, limit=None):
    country = country.upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("Country must be a two-letter ISO code")
    job_id = "%s-%s" % (country.lower(), uuid.uuid4().hex[:8])
    directory = ROOT / "work" / "pack-agent" / job_id
    command = [
        "python3", str(ROOT / "tools" / "skycharts_downloader.py"), "country", country,
        "--cookie-file", str(ARGS.cookie_file), "--pack-id", job_id,
        "--name", "%s Charts" % country, "--output", str(directory),
    ]
    if limit:
        command += ["--limit", str(limit)]
    return spawn_job(job_id, command, {"country": country, "kind": "country"})


def start_airport_job(idents):
    values = [value.strip().upper() for value in idents.split(",") if value.strip()]
    if not values or len(values) > 50 or any(not re.fullmatch(r"[A-Z0-9]{4}", value) for value in values):
        raise ValueError("Enter 1–50 four-character ICAO codes separated by commas")
    job_id = "airports-%s" % uuid.uuid4().hex[:8]
    directory = ROOT / "work" / "pack-agent" / job_id
    command = [
        "python3", str(ROOT / "tools" / "skycharts_downloader.py"), "airport",
    ] + values + [
        "--cookie-file", str(ARGS.cookie_file), "--pack-id", job_id,
        "--name", "Airport Charts", "--output", str(directory),
    ]
    return spawn_job(job_id, command, {"idents": values, "kind": "airports"})


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status, value):
        self.send_bytes(status, "application/json", json.dumps(value, separators=(",", ":")).encode())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        try:
            if parsed.path == "/health":
                self.send_json(200, {"ok": True, "service": "SkyCharts Pack Agent"})
                return
            if parsed.path == "/api/build":
                query = urllib.parse.parse_qs(parsed.query)
                country = query.get("country", [""])[0]
                limit_text = query.get("limit", [""])[0]
                limit = int(limit_text) if limit_text else None
                self.send_json(202, start_job(country, limit))
                return
            if parsed.path == "/api/build-airports":
                query = urllib.parse.parse_qs(parsed.query)
                self.send_json(202, start_airport_job(query.get("idents", [""])[0]))
                return
            if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                with LOCK:
                    job = JOBS.get(parts[2])
                    result = public_job(job) if job else None
                self.send_json(200 if result else 404, result or {"error": "job not found"})
                return
            if len(parts) >= 3 and parts[0] == "packs":
                with LOCK:
                    job = JOBS.get(parts[1])
                if not job or job["status"] != "ready":
                    self.send_json(404, {"error": "pack not ready"})
                    return
                relative = pathlib.Path(*parts[2:])
                target = (job["directory"] / relative).resolve()
                if job["directory"].resolve() not in target.parents and target != job["directory"].resolve():
                    self.send_json(403, {"error": "invalid path"})
                    return
                if not target.is_file():
                    self.send_json(404, {"error": "file not found"})
                    return
                content_type = "application/json" if target.suffix == ".json" else "image/png"
                self.send_bytes(200, content_type, target.read_bytes())
                return
            self.send_json(404, {"error": "not found"})
        except Exception as error:
            self.send_json(400, {"error": str(error)})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


def main():
    global ARGS
    parser = argparse.ArgumentParser(description="SkyCharts LAN chart-pack agent")
    parser.add_argument("--cookie-file", required=True, type=pathlib.Path)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8770, type=int)
    ARGS = parser.parse_args()
    print("SkyCharts Pack Agent listening on http://%s:%d" % (ARGS.host, ARGS.port))
    ThreadingHTTPServer((ARGS.host, ARGS.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
