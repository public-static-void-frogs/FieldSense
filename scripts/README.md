# Production launch

Run commands from the repository root. Install `npm`, `caddy` and `cloudflared`,
set up `backend/.venv` and `frontend/node_modules`, and configure `backend/.env`
as described in the backend README. Apply database migrations separately with
`cd backend && .venv/bin/python -m alembic upgrade head` before launching.
The launcher checks migrations without modifying the database.

## This Mac: use the installed system tunnel

The system LaunchDaemon `com.cloudflare.cloudflared` runs the FieldSense tunnel
(`ef2fdce3-bff8-49c0-a216-51b930dc0650`). Its token stays in the root-only file
`/Library/Application Support/com.cloudflare.cloudflared/token`.
Run the application as your normal user:

```sh
backend/.venv/bin/python scripts/serve-production.py \
  --hostname publicstaticvoidfrogs.dev --existing-tunnel
```

In Cloudflare, configure the published application for
`publicstaticvoidfrogs.dev`, with no path restriction and service URL
`http://127.0.0.1:27432`. Its proxied DNS CNAME must target
`ef2fdce3-bff8-49c0-a216-51b930dc0650.cfargotunnel.com`.
An old A record pointing at an EC2 server does not route traffic to this tunnel.

Caddy listens on `127.0.0.1:27432`, serves the production frontend with SPA
fallback, and forwards `/api/v1` requests to FastAPI on `127.0.0.1:27431`.
Cloudflare provides public HTTPS; the origin connection uses local HTTP.
The launcher overrides `VITE_API_BASE_URL`, `CORS_ORIGINS` and `COOKIE_SECURE`
for this hostname, so development `.env` values need not change.

The launcher builds into a temporary directory and runs in the foreground.
Keep it running and keep the Mac awake. Ctrl+C stops its application processes
and removes its temporary build; the independently managed tunnel stays running.
The existing tunnel service is not supervised by this launcher. Verify both
the public frontend and `/api/v1/auth/me` after launch; an unauthenticated API
request should return JSON with status 401, not HTML or a Cloudflare error.
Only the tunnel starts automatically at boot; the application does not.
Do not start the redundant Homebrew `cloudflared` service.

## Other tunnel modes

To let the launcher manage a named tunnel itself, use a token file readable by
the application user and avoid also running a separate connector for that tunnel:

```sh
backend/.venv/bin/python scripts/serve-production.py \
  --hostname app.example.com --token-file /path/to/tunnel-token
```

Without arguments, the launcher creates a temporary Quick Tunnel with a random
`trycloudflare.com` hostname. It does not use the configured production domain.
