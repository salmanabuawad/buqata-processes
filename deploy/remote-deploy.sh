#!/usr/bin/env bash
#
# Server side of a deploy to tender.kortexd.com. Run as root by deploy.ps1
# after it has unpacked the payload into $PAYLOAD.
#
# Idempotent and conservative on a shared host:
#   * installs only packages that are genuinely missing, never upgrades;
#   * creates the service user, database, .env and units only if absent,
#     and never overwrites an existing .env (secrets are generated once);
#   * installs the nginx site and reverts it if `nginx -t` fails, leaving
#     every other site on the host untouched;
#   * runs migrations and baseline seeding once per deploy, before restart.
set -euo pipefail

PAYLOAD="${1:?payload directory}"
APP_USER="buqata-processes"
APP_DIR="/opt/buqata-processes"
WEB_ROOT="/var/www/buqata-processes"
DB_NAME="buqata_processes"
DB_USER="buqata_processes"
DOMAIN="tender.kortexd.com"
API_PORT="8093"
API_SERVICE="buqata-processes-api"
WORKER_SERVICE="buqata-processes-worker"
SITE="buqata-processes"

say() { printf '\n==> %s\n' "$1"; }

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

say "Packages"
missing=()
command -v python3 >/dev/null || missing+=(python3)
python3 -c 'import venv' 2>/dev/null || missing+=(python3-venv)
command -v psql >/dev/null || missing+=(postgresql postgresql-contrib)
command -v nginx >/dev/null || missing+=(nginx)
command -v rsync >/dev/null || missing+=(rsync)
command -v openssl >/dev/null || missing+=(openssl)
if (( ${#missing[@]} )); then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq && apt-get install -y -qq "${missing[@]}"
fi
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    sys.exit(f"Python >= 3.10 required, found {sys.version.split()[0]}")
PY

say "Service account and directories"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR/backend" "$APP_DIR/storage" "$APP_DIR/outbox" "$WEB_ROOT"

say "PostgreSQL"
systemctl is-active --quiet postgresql || systemctl enable --now postgresql
DB_PASS=""
if [[ ! -f "$APP_DIR/.env" ]]; then
  DB_PASS="$(openssl rand -base64 30 | tr -d '/+=\n' | head -c 32)"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
  [[ -n "$DB_PASS" ]] || { echo ".env exists but the database role does not — fix manually" >&2; exit 1; }
  sudo -u postgres psql -qc "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';"
elif [[ -n "$DB_PASS" ]]; then
  sudo -u postgres psql -qc "ALTER ROLE $DB_USER WITH PASSWORD '$DB_PASS';"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
  sudo -u postgres createdb -O "$DB_USER" -E UTF8 -T template0 "$DB_NAME"
fi

say "Environment file"
if [[ ! -f "$APP_DIR/.env" ]]; then
  VAULT_KEY="$(openssl rand -base64 32 | tr -d '\n')"
  cat > "$APP_DIR/.env" <<ENVEOF
# Quoted values: valid for systemd EnvironmentFile and for "set -a; . .env".
# ENVIRONMENT=staging: this host is a demonstration environment with demo
# data and the development key-management adapter. Real tenders need
# ENVIRONMENT=production and a managed KMS/HSM (docs/SECURITY_MODEL.md).
ENVIRONMENT="staging"
DEMO_MODE="true"
EXPOSE_DOCS="false"
DATABASE_URL="postgresql+psycopg://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME"
PUBLIC_BASE_URL="https://$DOMAIN"
COOKIE_SECURE="true"
TRUSTED_PROXIES="127.0.0.1,::1"
STORAGE_BACKEND="local"
STORAGE_DIR="$APP_DIR/storage"
KMS_PROVIDER="local"
VAULT_MASTER_KEY="$VAULT_KEY"
MAIL_BACKEND="file"
MAIL_OUTBOX_DIR="$APP_DIR/outbox"
MAIL_FROM="Buq'ata Digital Processes <no-reply@$DOMAIN>"
REDIS_URL=""
ENVEOF
  echo "    wrote a new .env with generated secrets"
else
  echo "    keeping the existing .env"
fi
chmod 600 "$APP_DIR/.env"

say "Backend code"
rsync -a --delete --exclude=.venv --exclude=__pycache__ --exclude='*.pyc' --exclude=var --exclude=.env \
  "$PAYLOAD/backend/" "$APP_DIR/backend/"
[[ -x "$APP_DIR/venv/bin/python" ]] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 700 "$APP_DIR/storage"

say "Migrations and seed"
cd "$APP_DIR/backend"
sudo -u "$APP_USER" bash -c "set -a; . '$APP_DIR/.env'; set +a; '$APP_DIR/venv/bin/python' -m app.cli migrate && '$APP_DIR/venv/bin/python' -m app.cli seed && '$APP_DIR/venv/bin/python' -m app.cli seed-demo"

say "systemd units"
for unit in "$API_SERVICE" "$WORKER_SERVICE"; do
  install -m 644 "$PAYLOAD/deploy/systemd/$unit.service" "/etc/systemd/system/$unit.service"
done
systemctl daemon-reload
systemctl enable --quiet "$API_SERVICE" "$WORKER_SERVICE"
systemctl restart "$API_SERVICE" "$WORKER_SERVICE"

say "Frontend"
rsync -a --delete "$PAYLOAD/frontend/" "$WEB_ROOT/"
chown -R www-data:www-data "$WEB_ROOT"

say "nginx"
install -m 644 "$PAYLOAD/deploy/nginx/security-headers.conf" /etc/nginx/snippets/buqata-processes-security.conf
CERT_DIR=""
for dir in /etc/letsencrypt/live/*/; do
  [[ -f "$dir/fullchain.pem" ]] || continue
  if openssl x509 -in "$dir/fullchain.pem" -noout -ext subjectAltName 2>/dev/null | grep -qE "DNS:($DOMAIN|\*\.kortexd\.com)(,|$)"; then
    if openssl x509 -in "$dir/fullchain.pem" -noout -checkend 0 >/dev/null 2>&1; then CERT_DIR="${dir%/}"; break; fi
  fi
done
if [[ -n "$CERT_DIR" ]]; then
  sed "s#__CERT_DIR__#$CERT_DIR#g" "$PAYLOAD/deploy/nginx/$SITE.https.conf" > "/etc/nginx/sites-available/$SITE"
  echo "    TLS certificate: $CERT_DIR"
else
  cp "$PAYLOAD/deploy/nginx/$SITE.http.conf" "/etc/nginx/sites-available/$SITE"
  echo "    no certificate for $DOMAIN yet — serving HTTP only (see DEPLOYMENT.md to issue one)"
fi
ln -sf "/etc/nginx/sites-available/$SITE" "/etc/nginx/sites-enabled/$SITE"
if nginx -t 2>/dev/null; then
  systemctl reload nginx
else
  rm -f "/etc/nginx/sites-enabled/$SITE"
  echo "nginx config test failed — site disabled again, nginx left on its previous config" >&2
  nginx -t || true
  exit 1
fi

say "Health"
for i in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$API_PORT/api/v1/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "http://127.0.0.1:$API_PORT/api/v1/health" && echo
systemctl is-active "$API_SERVICE" "$WORKER_SERVICE"
sudo -u "$APP_USER" bash -c "set -a; . '$APP_DIR/.env'; set +a; cd '$APP_DIR/backend'; '$APP_DIR/venv/bin/python' -m app.cli audit-verify"
if [[ -n "$CERT_DIR" ]]; then echo "Deployed: https://$DOMAIN/"; else echo "Deployed (HTTP only): http://$DOMAIN/"; fi
