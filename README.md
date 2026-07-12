# SkyCharts

SkyCharts is a native UIKit chart viewer for jailbroken iPads running iOS 6. It presents Microsoft Flight Simulator 2024 LIDO charts in a Jeppesen-inspired interface and is designed to work offline after chart packs have been installed.

The app does not contain an Xbox login, planner cookie, relay, or web browser. A Mac downloads authorized chart assets from the planner, builds a local pack, and transfers that pack to the iPad. The app reads packs from `/var/mobile/Library/SkyCharts/ChartPacks`. Version 0.8 automatically migrates packs and preferences from an existing AtlasSix installation.

The earlier `relay/` service remains as an optional compatibility prototype; it is not required for the offline workflow.

## Repository layout

```text
SkyCharts/                Objective-C UIKit application
SkyCharts.plist           iOS application property list
Makefile and control      Theos armv7/iOS 6 build configuration
tools/                    Mac downloader, cache, pack agent, and CLI
relay/                    Optional authenticated planner relay prototype
work/                     Cookies, jobs, cache, and generated packs (ignored)
outputs/                  Local build artifacts (ignored)
```

## Requirements

On the Mac:

- macOS with Xcode command-line tools
- Theos at `/Users/skyning/theos` (or set `THEOS` elsewhere)
- Theos-compatible iOS 6 SDK and armv7 toolchain
- Python 3
- A signed-in Microsoft Flight Simulator planner account
- Same-LAN access to the iPad for Pack Agent transfers

On the iPad:

- Jailbroken iPad running iOS 6
- SSH access as `root`
- Its LAN address, for example `192.168.2.19`

The downloader requires planner authentication. The Mac client opens a dedicated Chromium window, lets the user complete the normal Microsoft/Xbox login, detects the planner's `ApiToken`, and saves the Cookie header privately. Treat the saved file as a password: never commit or publish it.

## First-time setup

```sh
cd /Users/skyning/Documents/Codex/2026-07-11/i-a
export THEOS=/Users/skyning/theos
chmod 700 tools/skycharts tools/*.py
mkdir -p work
chmod 700 work
python3 -m venv .venv
.venv/bin/python3 -m pip install playwright
.venv/bin/python3 -m playwright install chromium
./tools/skycharts
```

Choose **Sign in / refresh planner authentication**. Complete the Microsoft/Xbox login in the browser window; the client automatically writes `work/msfs-cookie.txt` with mode `0600`. Its persistent browser profile is stored under ignored `work/` data, so later refreshes normally reuse the existing Microsoft session.

The browser flow can also be run directly:

```sh
python3 tools/skycharts_auth.py
```

If browser automation cannot be installed, the previous manual Cookie-header method remains a fallback: put the complete header value on one line in `work/msfs-cookie.txt` and run `chmod 600 work/msfs-cookie.txt`.

Validate the session without downloading a chart:

```sh
MSFS_COOKIE_FILE="$PWD/work/msfs-cookie.txt"
curl -sS -o /dev/null \
  -w 'HTTP %{http_code} — %{content_type}\n' \
  -H "Cookie: $(<"$MSFS_COOKIE_FILE")" \
  https://planner.flightsimulator.com/api/v1/token/expiry
```

HTTP 200 means the session is accepted. Renew the browser session and replace the file after a 401/403.

## Build the iOS 6 package

```sh
export THEOS=/Users/skyning/theos
make clean package
```

The package is written to `packages/`. To keep a convenient local copy:

```sh
mkdir -p outputs
cp packages/com.skyning.skycharts_*_iphoneos-arm.deb \
  outputs/SkyCharts-ios6-armv7.deb
```

The Makefile targets `iphone:clang:10.3:6.0` and `armv7`.

## Install, restart, and refresh SpringBoard

The iPad uses an old SSH server, so modern OpenSSH needs RSA compatibility flags:

```sh
IP=192.168.2.19
DEB=packages/com.skyning.skycharts_0.10.2-1+debug_iphoneos-arm.deb

scp -O -o StrictHostKeyChecking=no \
  -o HostKeyAlgorithms=+ssh-rsa \
  -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  "$DEB" root@$IP:/tmp/SkyCharts.deb

ssh -o StrictHostKeyChecking=no \
  -o HostKeyAlgorithms=+ssh-rsa \
  -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  root@$IP 'dpkg -i /tmp/SkyCharts.deb'
```

The default password on many test jailbreaks is `alpine`; change it on a real device.

Restart the app:

```sh
ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  root@$IP 'killall SkyCharts 2>/dev/null || true'
```

Refresh the icon cache:

```sh
ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  root@$IP 'uicache'
```

If old jailbreaks report `cannot open cache file. incorrect user?`, run the cache refresh as mobile and respring:

```sh
ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  root@$IP 'su -s /bin/sh mobile -c "uicache"'
ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
  root@$IP 'killall SpringBoard 2>/dev/null || true'
```

## Build an offline chart pack

The downloader keeps reusable assets in `work/chart-cache`. Rebuilding a pack reuses cached pages and hard-links them into new output when possible. Light assets are downloaded by default.

Selected airports:

```sh
python3 tools/skycharts_downloader.py airport KJFK KLGA \
  --cookie-file work/msfs-cookie.txt \
  --pack-id new-york-demo --name "New York Demo" \
  --output outputs/new-york-demo --workers 8
```

Country pack:

```sh
python3 tools/skycharts_downloader.py country CA \
  --cookie-file work/msfs-cookie.txt \
  --pack-id canada --name "Canada" \
  --output outputs/canada --workers 8
```

Useful options are `--limit 10` for a trial, `--workers 16` for more concurrency, `--cache-dir PATH` to relocate the reusable cache, `--refresh-airports` to refresh the OurAirports index, `--types all` to include every airport type, and `--include-dark` when dark PNG assets are explicitly needed.

Install an existing pack directly over SSH:

```sh
python3 tools/skycharts_downloader.py install \
  outputs/new-york-demo --host 192.168.2.19
```

The installer stages into a temporary directory, validates `pack.json`, and atomically moves the pack into `ChartPacks`. Failed transfers remove partial files.

## Interactive Mac client

```sh
./tools/skycharts
```

The menu handles browser authentication, starts the Pack Agent, builds country or selected-airport packs, installs packs over SSH, and reports cache status. If no cookie file exists, authenticated operations automatically offer browser login.

## In-app downloads through Pack Agent

Start the LAN agent:

```sh
python3 tools/skycharts_pack_agent.py \
  --cookie-file work/msfs-cookie.txt --host 0.0.0.0 --port 8770
```

Check it from the Mac:

```sh
curl http://127.0.0.1:8770/health
```

In SkyCharts, open the gear menu, choose a download option, and enter `http://MAC-LAN-IP:8770`. The app can request a country or comma-separated ICAO codes, polls the job, downloads light PNGs, and atomically installs the pack. Keep the agent running until installation completes.

While a pack is being built, the footer shows overall completion percentage and an estimated remaining time. The estimate uses elapsed time plus global airport/chart progress and becomes more accurate after the first few charts complete.

## Chart categories

Provider categories are normalized into five compact Jeppesen-style sections:

```text
STAR        STAR, STARPT, arrival procedure types
SID         SID, SIDPT, departure procedure types
APP         IAC and approach procedure types
TAXI        AGC, APC, AFC, LVC, ADC, APT
MISC        Any remaining provider type, including AOI
```

The five controls sit inside a single dark vertical pill. The active category uses an inset orange selector with a dark central label, following the classic Jeppesen iPad visual language. Within a section, runway charts are grouped under headers such as `RWY 10L` and `RWY 19R`; charts without runway metadata appear under `GENERAL`.

Downloaded content is presented as a collapsible location hierarchy: continent → country → state/province/region → city. Airport totals appear at the city level instead of listing every airport as a separate row. Pack deletion remains available under the collapsible **Installed Packages** branch.

The app includes iOS 6 icon assets at 57, 72, 114, and 144 pixels, generated from `SkyCharts/Resources/SkyChartsIcon-1024.png` with transparent outer corners and prerendered artwork.

## METAR weather

The beveled `Wx` button at the bottom of the category rail matches the airport selector and opens a compact iOS 6 weather window for the selected airport. It offers Raw and Decoded views plus manual refresh. Weather is read directly from the latest worldwide station files published by the U.S. National Weather Service over anonymous FTP, avoiding modern HTTPS requirements that iOS 6 cannot satisfy.

## Optional legacy relay

The relay is for troubleshooting and API experiments only:

```sh
cd relay
chmod 600 ../work/msfs-cookie.txt
MSFS_COOKIE_FILE=../work/msfs-cookie.txt python3 msfs_chart_relay.py
```

See [relay/README.md](relay/README.md) for endpoints. Never commit cookies, signed URLs, or logs containing request headers.

## Troubleshooting

- **401/403 from planner:** choose **Sign in / refresh planner authentication** in `./tools/skycharts`.
- **Browser login dependency missing:** run `python3 -m venv .venv`, `.venv/bin/python3 -m pip install playwright`, and `.venv/bin/python3 -m playwright install chromium`. The launcher automatically uses this isolated environment.
- **Weather unavailable:** confirm the iPad has Internet access. Some airports do not publish METAR reports, and the NWS station may temporarily be unavailable.
- **Pack build failed:** inspect terminal output and `work/pack-agent/*.log`; check cookie, Internet access, and planner availability.
- **Pack transfer failed:** verify the iPad and Mac are on the same LAN, port 8770 is reachable, and iPad storage is available. Cached assets make retries faster.
- **`uicache` cache-file error:** run it as `mobile` and respring SpringBoard using the commands above.
- **Missing chart:** use the gear menu's content manager to confirm the pack and airport are installed; rebuild if `pack.json` references missing PNGs.

## GitHub backup

Generated credentials, packs, caches, build products, and Python bytecode are excluded by `.gitignore`. Create the first local commit:

```sh
git init
git add .
git status
git commit -m "Initial SkyCharts iOS 6 offline chart viewer"
```

The canonical repository is `skylarkning/SkyCharts`. Add its URL and push:

```sh
git branch -M main
git remote add origin git@github.com:skylarkning/SkyCharts.git
git push -u origin main
```

HTTPS alternative:

```sh
git remote add origin https://github.com/skylarkning/SkyCharts.git
git push -u origin main
```

Verify future backups with:

```sh
git status
git log --oneline --decorate -5
git remote -v
```

## Responsible use

Chart data comes from the Microsoft Flight Simulator planner and its provider. Access, caching, redistribution, and validity are governed by the applicable account and provider terms. Download only data you are authorized to use and do not publish cookies, signed URLs, or restricted chart packs.
