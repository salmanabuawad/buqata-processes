# Deploy to tender.kortexd.com

## How to deploy (quick)

| Command | What it does |
|--------|----------------|
| `npm run deploy:server` | Build the frontend and deploy it to the nginx root only |
| `npm run deploy:server:all` | Build + deploy frontend, then deploy backend (one confirmation) |
| `npm run deploy:backend` | Deploy backend only (tests, sync, migrate, seed, restart) |

Run them from `frontend/`, or call the scripts directly from the repository
root: `.\deploy-to-server.ps1`, `.\deploy-backend-to-server.ps1`,
`.\deploy-all-to-server.ps1`. You'll see the deploy target; type `y` to confirm.

**Skip the confirmation prompt:**
```powershell
$env:DEPLOY_SKIP_CONFIRM = "1"; npm run deploy:server:all
```

**What gets deployed:**
- Frontend: `npm run build` (static export to `frontend/out/`), upload via SCP,
  replace the contents of `/opt/buqata-processes/frontend/dist`.
- Backend: the test suite runs first and **aborts the deploy if it fails**; then
  one filtered archive of `backend/` (no `.venv`, no `var/`) is uploaded,
  rsynced to `/opt/buqata-processes/backend`, requirements installed, and
  `migrate` and `seed` (roles, organization, process types, category tree —
  no sample data) run once, before both services restart.
  A health check confirms the API is up.

Live app: **https://tender.kortexd.com/**

**Requirements:** key-based SSH access. Default `root@185.229.226.37`.

---

- **App URL:** https://tender.kortexd.com/ (DNS A → 185.229.226.37)
- **SSH host:** `185.229.226.37` (override with `$env:DEPLOY_HOST`)
- **SSH user:** `root` (override with `$env:DEPLOY_USER`)
- **Frontend path:** `/opt/buqata-processes/frontend/dist` (override: `$env:DEPLOY_PATH`)
- **Backend path:** `/opt/buqata-processes` (override: `$env:BACKEND_REMOTE_PATH`)
- **Systemd services:** `buqata-processes-backend` (uvicorn, 2 workers), `buqata-processes-worker`
- **Backend port:** `8097`, loopback only
- **Venv:** `/opt/buqata-processes/venv`
- **Database:** PostgreSQL, database and role `buqata_processes` (UTF-8)
- **Secrets:** `/opt/buqata-processes/.env` (mode 600) — written once by the setup script
- **Files:** `/opt/buqata-processes/storage` (sealed offers are ciphertext), `/opt/buqata-processes/outbox` (e-mail, until SMTP is configured)
- **Service account:** `buqata-processes` (the API does not run as root)

No Docker: everything runs natively on the host.

## Server setup (first time)

`deploy/setup-server.sh` does the one-time work and is safe to re-run. It
installs only missing packages, creates the service account, directories,
database and role, writes `.env` with generated secrets (never overwrites an
existing one), creates the virtualenv, installs and enables both systemd
units, and installs the nginx site — removing it again if `nginx -t` fails,
so the other sites on this host are never affected.

```bash
scp -r deploy root@185.229.226.37:/tmp/bdp_setup
ssh root@185.229.226.37 'bash /tmp/bdp_setup/setup-server.sh && rm -rf /tmp/bdp_setup'
```

**SSL (Let's Encrypt)** — before the first code deploy, because session
cookies are `Secure` and sign-in needs HTTPS:
```bash
certbot --nginx -d tender.kortexd.com
```

Then deploy:
```powershell
.\deploy-all-to-server.ps1
```

## Environment variables (all optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `DEPLOY_HOST` | `185.229.226.37` | SSH host |
| `DEPLOY_USER` | `root` | SSH user |
| `DEPLOY_PATH` | `/opt/buqata-processes/frontend/dist` | Frontend nginx root |
| `BACKEND_REMOTE_PATH` | `/opt/buqata-processes` | Backend app root |
| `BACKEND_SERVICE` | `buqata-processes-backend` | API systemd unit |
| `DEPLOY_APP_URL` | `https://tender.kortexd.com/` | Shown in success message only |
| `DEPLOY_SKIP_CONFIRM` | (unset) | Set to `1` to skip "Deploy? [y/N]" |
| `DEPLOY_ALLOW_DIRTY` | (unset) | The scripts refuse to deploy with uncommitted changes; `1` overrides that on purpose |

## Environment on this host

`.env` sets **`ENVIRONMENT=staging`, `DEMO_MODE=false`**: no sample data and no
one-click demo sign-in (sample data exists only in local development, via
`python -m app.cli dev-setup`). It still uses the development key-management
adapter (`LocalKms`, master key in `.env`) and writes e-mail to `outbox/`
instead of sending it. Before real procurement: `ENVIRONMENT=production`
(`LocalKms` then refuses to start), a managed KMS/HSM adapter
(`docs/SECURITY_MODEL.md` §4), `MAIL_BACKEND=smtp`, Entra ID for staff.

## Checks and operations

```bash
curl -s https://tender.kortexd.com/api/v1/health
systemctl status buqata-processes-backend buqata-processes-worker --no-pager
journalctl -u buqata-processes-backend -n 100 --no-pager
cd /opt/buqata-processes/backend && set -a && . ../.env && set +a
sudo -u buqata-processes -E ../venv/bin/python -m app.cli audit-verify
BDP_ADMIN_PASSWORD='…' sudo -u buqata-processes -E ../venv/bin/python -m app.cli create-admin --email you@example.com --name "Name"
```

**Backups:** `pg_dump buqata_processes`, `/opt/buqata-processes/storage`, and the
`VAULT_MASTER_KEY` from `.env` stored separately — sealed offers cannot be
opened without the key.

## Notes

- Do not commit passwords or `.env`. Set credentials only on the server.
- The frontend deploy replaces the contents of the nginx path with the new build.
- The deploy scripts never touch nginx or systemd; that is one-time setup.
- After a deploy, hard-refresh (Ctrl+Shift+R) to load the new frontend.
- To take the site offline: `rm /etc/nginx/sites-enabled/tender.kortexd.com && systemctl reload nginx`
  and `systemctl disable --now buqata-processes-backend buqata-processes-worker`.
