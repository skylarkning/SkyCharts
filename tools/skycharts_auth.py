#!/usr/bin/env python3
"""Interactive browser authentication for the MSFS planner."""

import argparse
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLANNER_URL = "https://planner.flightsimulator.com/"


def browser_login(cookie_file, timeout=900):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Browser login needs Playwright. Install it once with:")
        print("  python3 -m pip install --user playwright")
        print("  python3 -m playwright install chromium")
        return False

    cookie_file = pathlib.Path(cookie_file).expanduser().resolve()
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(cookie_file.parent, 0o700)
    profile = ROOT / "work" / "planner-browser-profile"
    profile.mkdir(parents=True, exist_ok=True)
    print("Opening the Microsoft Flight Simulator planner sign-in window…")
    print("Complete the Microsoft/Xbox login. SkyCharts will save authentication automatically.")
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile), headless=False, viewport={"width": 1180, "height": 820}
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(PLANNER_URL, wait_until="domcontentloaded", timeout=120000)
            deadline = time.time() + timeout
            while time.time() < deadline:
                cookies = context.cookies([PLANNER_URL])
                token = next((item for item in cookies if item.get("name") == "ApiToken" and item.get("value")), None)
                if token:
                    planner_cookies = [item for item in cookies if item.get("domain", "").endswith("flightsimulator.com")]
                    header = "; ".join("%s=%s" % (item["name"], item["value"]) for item in planner_cookies)
                    temporary = cookie_file.with_suffix(cookie_file.suffix + ".tmp")
                    temporary.write_text(header + "\n", encoding="utf-8")
                    os.chmod(temporary, 0o600)
                    temporary.replace(cookie_file)
                    os.chmod(cookie_file, 0o600)
                    print("Planner authentication saved privately to %s" % cookie_file)
                    context.close()
                    return True
                if page.is_closed():
                    break
                page.wait_for_timeout(1000)
            context.close()
    except PlaywrightError as error:
        message = str(error)
        if "Executable doesn't exist" in message:
            print("Playwright Chromium is not installed. Run:")
            print("  python3 -m playwright install chromium")
        else:
            print("Browser login failed: %s" % message)
        return False
    print("No ApiToken was received before the browser was closed or the login timed out.")
    return False


def main():
    parser = argparse.ArgumentParser(description="Sign in to the MSFS planner and save SkyCharts authentication")
    parser.add_argument("--cookie-file", default=str(ROOT / "work" / "msfs-cookie.txt"))
    parser.add_argument("--timeout", type=int, default=900, help="login timeout in seconds")
    args = parser.parse_args()
    return 0 if browser_login(args.cookie_file, args.timeout) else 1


if __name__ == "__main__":
    raise SystemExit(main())
