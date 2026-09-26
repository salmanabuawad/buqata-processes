#!/usr/bin/env bash
#
# One-time server setup for tender.kortexd.com (Buq'ata Digital Processes).
#
#   scp -r deploy root@185.229.226.37:/tmp/bdp_setup
#   ssh root@185.229.226.37 'bash /tmp/bdp_setup/setup-server.sh'
#
# Idempotent and conservative on a shared host: installs only missing
# packages (never upgrades), never overwrites an existing .env, and if the new
# nginx site fails `nginx -t` it is removed again and nginx keeps its previous
# config. Code is deployed afterwards with deploy-all-to-server.ps1.
set -euo pipefail

APP_USER="buqata-processes"
APP_DIR="/opt/buqata-processes"
DB_NAME="buqata_processes"
DB_USER="buqata_processes"
DOMAIN="tender.kortexd.com"
HERE="$(cd "$(dirname "$0")" && pwd)"

say() { printf '\n==> %s\n' "$1"; }
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }

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
else
  echo "    all present"
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Python >= 3.10 required")'

say "Service account and directories"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR/backend" "$APP_DIR/frontend/dist" "$APP_DIR/storage" "$APP_DIR/outbox"
chmod 755 "$APP_DIR" "$APP_DIR/frontend" "$APP_DIR/frontend/dist"

say "PostgreSQL"
systemctl is-active --quiet postgresql || systemctl enable --now postgresql
DB_PASS=""
[[ -f "$APP_DIR/.env" ]] || DB_PASS="$(openssl rand -base64 30 | tr -d '/+=\n' | head -c 32)"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
  [[ -n "$DB_PASS" ]] || { echo ".env exists but role $DB_USER does not — fix manually" >&2; exit 1; }
  sudo -u postgres psql -qc "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';"
elif [[ -n "$DB_PASS" ]]; then
  sudo -u postgres psql -qc "ALTER ROLE $DB_USER WITH PASSWORD '$DB_PASS';"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
  sudo -u postgres createdb -O "$DB_USER" -E UTF8 -T template0 "$DB_NAME"
fi

say "$APP_DIR/.env"
if [[ ! -f "$APP_DIR/.env" ]]; then
  VAULT_KEY="$(openssl rand -base64 32 | tr -d '\n')"
  cat > "$APP_DIR/.env" <<ENVEOF
# Quoted values: valid for systemd EnvironmentFile and for "set -a; . .env".
# ENVIRONMENT=staging: demonstration host with demo data and the development
# key-management adapter. Real tenders need ENVIRONMENT=production and a
# managed KMS/HSM (docs/SECURITY_MODEL.md). Back up VAULT_MASTER_KEY separately:
# sealed offers cannot be opened without it.
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

say "Virtualenv"
[[ -x "$APP_DIR/venv/bin/python" ]] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 700 "$APP_DIR/storage"

say "systemd units"
install -m 644 "$HERE/systemd/buqata-processes-backend.service" /etc/systemd/system/
install -m 644 "$HERE/systemd/buqata-processes-worker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --quiet buqata-processes-backend buqata-processes-worker
echo "    enabled (they start on the first backend deploy)"

say "nginx"
install -m 644 "$HERE/nginx/security-headers.conf" /etc/nginx/snippets/buqata-processes-security.conf
if [[ -f "/etc/nginx/sites-available/$DOMAIN" ]]; then
  echo "    /etc/nginx/sites-available/$DOMAIN exists (possibly with certbot's TLS block) — left unchanged"
else
  install -m 644 "$HERE/nginx/$DOMAIN.conf" "/etc/nginx/sites-available/$DOMAIN"
  ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
  if nginx -t 2>/dev/null; then
    systemctl reload nginx
    echo "    site enabled"
  else
    rm -f "/etc/nginx/sites-enabled/$DOMAIN" "/etc/nginx/sites-available/$DOMAIN"
    echo "nginx -t failed — site removed again, nginx untouched" >&2
    nginx -t || true
    exit 1
  fi
fi

cat <<DONE

Setup complete. Next:
  1. On the server, once:   certbot --nginx -d $DOMAIN
     (session cookies are Secure-only, so sign-in needs HTTPS)
  2. From your workstation: .\deploy-all-to-server.ps1
DONE
