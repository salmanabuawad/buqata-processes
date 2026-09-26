# Deployment — tender.kortexd.com

## Target

| Item | Value |
|---|---|
| URL | https://tender.kortexd.com/ (DNS A record → 185.229.226.37) |
| SSH | `root@185.229.226.37` (override `DEPLOY_HOST`, `DEPLOY_USER`) |
| Code | `/opt/buqata-processes/backend`, virtualenv `/opt/buqata-processes/venv` |
| Web root | `/var/www/buqata-processes` (static Next.js export) |
| Secrets | `/opt/buqata-processes/.env`, mode 600 — generated on first deploy, never overwritten |
| Files | `/opt/buqata-processes/storage` (sealed offers are ciphertext), `/opt/buqata-processes/outbox` (e-mail) |
| Database | PostgreSQL, database and role `buqata_processes` (UTF-8) |
| Services | `buqata-processes-api` (uvicorn, 127.0.0.1:8093, 2 workers), `buqata-processes-worker` |
| nginx | site `buqata-processes`, snippet `buqata-processes-security.conf` |

The host serves other sites. Every name above is unique to this application,
and the deploy touches nothing else: packages are installed only if missing,
and a failing `nginx -t` removes this site again and leaves nginx on its
previous configuration.

## Deploy

```powershell
.\deploy.ps1
```

It runs the backend test suite (and aborts on failure), builds the static
frontend, uploads one archive, and runs `deploy/remote-deploy.sh`, which:

1. on first run creates the service user, database, role and `.env` (with a
   generated DB password and vault master key);
2. syncs code, installs requirements;
3. runs `app.cli migrate`, `seed` and `seed-demo` once (never per worker);
4. installs and restarts the systemd units;
5. publishes the frontend;
6. installs the nginx site — HTTPS if a certificate covering
   `tender.kortexd.com` (or `*.kortexd.com`) exists, otherwise HTTP only;
7. checks `/api/v1/health` and verifies the audit chain.

SSH must work non-interactively from the machine running the script (key in
the agent, or `DEPLOY_HOST`/`DEPLOY_USER` pointing at an account that has one).

## TLS

If the first deploy reports "HTTP only", issue a certificate once on the host
and deploy again:

```bash
certbot certonly --webroot -w /var/www/html -d tender.kortexd.com
```

The next deploy detects it and switches the site to HTTPS with HSTS.

## Environment

This host runs **`ENVIRONMENT=staging` with `DEMO_MODE=true`**: demonstration
data, one-click demo sign-in, the development key-management adapter
(`LocalKms` with a master key in `.env`) and e-mail written to the outbox
directory instead of sent. That is right for presentations and wrong for real
procurement. For production:

* `ENVIRONMENT=production` (disables demo sign-in and demo seeding; `LocalKms`
  refuses to start);
* a managed KMS/HSM adapter (`docs/SECURITY_MODEL.md` §4);
* `MAIL_BACKEND=smtp` with SMTP settings;
* Entra ID sign-in for staff;
* `REDIS_URL` for immediate notification delivery (optional).

## Operations

```bash
systemctl status buqata-processes-api buqata-processes-worker --no-pager
journalctl -u buqata-processes-api -n 100 --no-pager
curl -s https://tender.kortexd.com/api/v1/health
cd /opt/buqata-processes/backend && set -a && . ../.env && set +a && ../venv/bin/python -m app.cli audit-verify
../venv/bin/python -m app.cli audit-anchor          # print the chain head for external anchoring
../venv/bin/python -m app.cli create-admin --email you@example.com --name "Name" --password '…'
```

Backups: `pg_dump buqata_processes` **and** `/opt/buqata-processes/storage`
**and** the `VAULT_MASTER_KEY` from `.env`, stored separately — sealed offers
cannot be opened without the key.

## Rollback

The deploy replaces only this application's code and static files. To take it
offline: `rm /etc/nginx/sites-enabled/buqata-processes && systemctl reload nginx`
and `systemctl disable --now buqata-processes-api buqata-processes-worker`.
The database and storage are left in place.
