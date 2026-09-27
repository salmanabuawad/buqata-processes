# Deploy the backend to tender.kortexd.com
# Default: root@185.229.226.37, app path /opt/buqata-processes (code synced to .../backend/)
# Override: DEPLOY_HOST, DEPLOY_USER, BACKEND_REMOTE_PATH (see DEPLOY_SERVER.md)
# Skip confirmation: $env:DEPLOY_SKIP_CONFIRM = "1"
#
# Runs the test suite first and aborts if it fails. On the server: rsync,
# pip install, migrate, seed (once per deploy, never per worker), restart.

$ErrorActionPreference = "Stop"
$SERVER = if ($env:DEPLOY_HOST) { $env:DEPLOY_HOST } else { "185.229.226.37" }
$USER = if ($env:DEPLOY_USER) { $env:DEPLOY_USER } else { "root" }
$REMOTE_APP = if ($env:BACKEND_REMOTE_PATH) { $env:BACKEND_REMOTE_PATH.TrimEnd("/") } else { "/opt/buqata-processes" }
$REMOTE_TEMP = "/tmp/buqata_processes_backend_deploy"
$SERVICE_NAME = if ($env:BACKEND_SERVICE) { $env:BACKEND_SERVICE } else { "buqata-processes-backend" }
$WORKER_NAME = "buqata-processes-worker"
$APP_USER = "buqata-processes"

Write-Host ""
Write-Host "========== BACKEND DEPLOY TARGET ==========" -ForegroundColor Yellow
Write-Host "  Server:     $USER@$SERVER"
Write-Host "  App path:   $REMOTE_APP"
Write-Host "  Services:   $SERVICE_NAME, $WORKER_NAME"
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

if (-not $env:DEPLOY_SKIP_CONFIRM) {
    $confirm = Read-Host "Deploy backend to the above target? [y/N]"
    if ($confirm -notmatch '^[yY]') {
        Write-Host "Deploy cancelled." -ForegroundColor Yellow
        exit 0
    }
}

$backendPath = Join-Path $PSScriptRoot "backend"
if (-not (Test-Path $backendPath)) {
    Write-Host "Error: backend folder not found at $backendPath" -ForegroundColor Red
    exit 1
}

Write-Host "Running tests..." -ForegroundColor Cyan
$venvPython = Join-Path $backendPath ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Push-Location $backendPath
    try { & $venvPython -m pytest -q; $testsExit = $LASTEXITCODE } finally { Pop-Location }
    if ($testsExit -ne 0) { Write-Host "Tests failed - deploy aborted." -ForegroundColor Red; exit $testsExit }
} else {
    Write-Host "  (no local venv; skipping tests)" -ForegroundColor DarkYellow
}

# One filtered archive instead of "scp -r backend": the local .venv and var/
# (dev database, keys, outbox) must never leave this machine.
$archive = Join-Path ([System.IO.Path]::GetTempPath()) "buqata_processes_backend.tar.gz"
if (Test-Path $archive) { Remove-Item $archive -Force }
& tar -czf $archive "--exclude=.venv" "--exclude=var" "--exclude=__pycache__" "--exclude=*.pyc" `
    "--exclude=.pytest_cache" "--exclude=.env" "--exclude=*.db" -C $PSScriptRoot backend
if ($LASTEXITCODE -ne 0) { Write-Host "Packing failed." -ForegroundColor Red; exit $LASTEXITCODE }

Write-Host "Uploading backend to ${USER}@${SERVER}:${REMOTE_TEMP} ..." -ForegroundColor Cyan
& ssh "${USER}@${SERVER}" "rm -rf $REMOTE_TEMP && mkdir -p $REMOTE_TEMP"
& scp $archive "${USER}@${SERVER}:${REMOTE_TEMP}/backend.tar.gz"
if ($LASTEXITCODE -ne 0) {
    Write-Host "SCP failed. Ensure SSH access: ssh $USER@$SERVER" -ForegroundColor Red
    exit $LASTEXITCODE
}
Remove-Item $archive -Force

Write-Host "Syncing to $REMOTE_APP, migrating and restarting..." -ForegroundColor Cyan
$remoteCmd = @"
set -e
[ -f $REMOTE_APP/.env ] || { echo 'Server not set up: run deploy/setup-server.sh first (DEPLOY_SERVER.md).'; exit 1; }
tar -xzf $REMOTE_TEMP/backend.tar.gz -C $REMOTE_TEMP
SRC=$REMOTE_TEMP/backend
[ -f "`$SRC/requirements.txt" ] || { echo 'Error: upload is missing requirements.txt'; exit 1; }
mkdir -p $REMOTE_APP/backend
rsync -a --delete --exclude=.env --exclude=venv --exclude=.venv --exclude=var --exclude=__pycache__ --exclude='*.pyc' "`$SRC/" $REMOTE_APP/backend/
rm -rf $REMOTE_TEMP
$REMOTE_APP/venv/bin/pip install -q -r $REMOTE_APP/backend/requirements.txt
# Archives made on Windows carry 0777 modes; normalise before anything runs.
chown -R ${APP_USER}:${APP_USER} $REMOTE_APP/backend
chmod -R u=rwX,go=rX $REMOTE_APP/backend
cd $REMOTE_APP/backend
sudo -u $APP_USER env PYTHONPATH=$REMOTE_APP/backend bash -c "cd $REMOTE_APP/backend && set -a && . $REMOTE_APP/.env && set +a && $REMOTE_APP/venv/bin/python -m app.cli migrate && $REMOTE_APP/venv/bin/python -m app.cli seed"
systemctl restart $SERVICE_NAME $WORKER_NAME
for i in `$(seq 1 20); do curl -fsS http://127.0.0.1:8097/api/v1/health >/dev/null 2>&1 && break; sleep 1; done
curl -fsS http://127.0.0.1:8097/api/v1/health && echo
systemctl is-active --quiet $SERVICE_NAME && systemctl is-active --quiet $WORKER_NAME || { journalctl -u $SERVICE_NAME -n 30 --no-pager; exit 1; }
echo Backend deploy done.
"@
# PowerShell here-strings are CRLF; bash needs LF.
$remoteCmd = $remoteCmd -replace "`r`n", "`n"
# Migration and seeding log to stderr; judge success by the exit code, not by
# PowerShell's treatment of stderr lines as errors.
$ErrorActionPreference = "Continue"
& ssh "${USER}@${SERVER}" $remoteCmd 2>&1 | ForEach-Object { "$_" }
$remoteExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($remoteExit -ne 0) {
    Write-Host "SSH command failed." -ForegroundColor Red
    exit $remoteExit
}

Write-Host "Backend deploy complete. Services restarted." -ForegroundColor Green
