# KJFK AGC relay

The relay terminates modern TLS, calls the authenticated MSFS planner API, caches the chart PNG, and presents a tiny HTTP interface suitable for iOS 6.

In a desktop browser session you own, open Developer Tools → Network, select a successful planner `/api/v1/charts/…` request, and copy only its `Cookie` request-header value into a private file. Then run:

```sh
chmod 600 /path/to/msfs-cookie.txt
MSFS_COOKIE_FILE=/path/to/msfs-cookie.txt python3 msfs_chart_relay.py
```

`MSFS_SESSION_COOKIE` is also supported, but a file avoids placing the value in shell history. Sign out of the planner to revoke the session if the cookie is ever exposed.

For a transport-only test, skip planner authentication and supply an already-authorized temporary chart URL:

```sh
MSFS_CHART_LIGHT_URL='https://…png?…' python3 msfs_chart_relay.py
```

Endpoints:

- `GET /health`
- `GET /api/airports/KJFK/charts/agc`
- `GET /api/airports/KJFK/charts/agc/light.png`
- `GET /api/airports/KJFK/charts/agc/dark.png`

Do not commit cookies or signed chart URLs. They are credentials and expire.
