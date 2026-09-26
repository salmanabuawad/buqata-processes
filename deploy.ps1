# Deploy Buq'ata Digital Processes to tender.kortexd.com.
#
#   .\deploy.ps1                         # asks for confirmation
#   $env:DEPLOY_SKIP_CONFIRM = "1"; .\deploy.ps1
#
# Steps: backend tests (abort on failure) -> frontend static build -> one
# filtered archive -> upload -> deploy/remote-deploy.sh on the host, which
# provisions on first run and then syncs, migrates, seeds and restarts.
# Override the target with DEPLOY_HOST / DEPLOY_USER.

$ErrorActionPreference = "Stop"
$SERVER = if ($env:DEPLOY_HOST) { $env:DEPLOY_HOST } else { "185.229.226.37" }
$USER   = if ($env:DEPLOY_USER) { $env:DEPLOY_USER } else { "root" }
$TEMP   = "/tmp/buqata_processes_deploy"
$Root   = $PSScriptRoot

Write-Host ""
Write-Host "========== DEPLOY TARGET ==========" -ForegroundColor Yellow
Write-Host "  Server:  $USER@$SERVER"
Write-Host "  URL:     https://tender.kortexd.com/"
Write-Host "  Paths:   /opt/buqata-processes, /var/www/buqata-processes"
Write-Host "  Units:   buqata-processes-api (127.0.0.1:8093), buqata-processes-worker"
Write-Host "===================================" -ForegroundColor Yellow
if (-not $env:DEPLOY_SKIP_CONFIRM) {
    $answer = Read-Host "Deploy to the above target? [y/N]"
    if ($answer -notmatch '^[yY]') { Write-Host "Cancelled."; exit 0 }
}

Write-Host "Running backend tests..." -ForegroundColor Cyan
Push-Location (Join-Path $Root "backend")
try {
    & ".\.venv\Scripts\python.exe" -m pytest -q
    if ($LASTEXITCODE -ne 0) { Write-Host "Tests failed - deploy aborted." -ForegroundColor Red; exit $LASTEXITCODE }
} finally { Pop-Location }

Write-Host "Building frontend (static export)..." -ForegroundColor Cyan
Push-Location (Join-Path $Root "frontend")
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) { Write-Host "Build failed." -ForegroundColor Red; exit $LASTEXITCODE }
} finally { Pop-Location }

Write-Host "Packing..." -ForegroundColor Cyan
$stage = Join-Path ([System.IO.Path]::GetTempPath()) "bdp_stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item (Join-Path $Root "frontend\out") (Join-Path $stage "frontend") -Recurse
$archive = Join-Path ([System.IO.Path]::GetTempPath()) "bdp_payload.tar.gz"
if (Test-Path $archive) { Remove-Item $archive -Force }
& tar -czf $archive `
    "--exclude=.venv" "--exclude=__pycache__" "--exclude=*.pyc" "--exclude=.pytest_cache" `
    "--exclude=var" "--exclude=.env" "--exclude=*.db" `
    -C $Root backend deploy -C $stage frontend
if ($LASTEXITCODE -ne 0) { Write-Host "Packing failed." -ForegroundColor Red; exit $LASTEXITCODE }
Remove-Item $stage -Recurse -Force
Write-Host ("  {0:N2} MB" -f ((Get-Item $archive).Length / 1MB))

Write-Host "Uploading..." -ForegroundColor Cyan
& ssh "${USER}@${SERVER}" "rm -rf $TEMP && mkdir -p $TEMP"
if ($LASTEXITCODE -ne 0) { Write-Host "SSH failed. Check access: ssh $USER@$SERVER" -ForegroundColor Red; exit $LASTEXITCODE }
& scp $archive "${USER}@${SERVER}:${TEMP}/payload.tar.gz"
if ($LASTEXITCODE -ne 0) { Write-Host "Upload failed." -ForegroundColor Red; exit $LASTEXITCODE }
Remove-Item $archive -Force

# PowerShell strings are CRLF; bash needs LF.
$remote = "cd $TEMP && tar -xzf payload.tar.gz && sed -i 's/\r$//' deploy/remote-deploy.sh && bash deploy/remote-deploy.sh $TEMP; rc=`$?; rm -rf $TEMP; exit `$rc"
& ssh "${USER}@${SERVER}" $remote
if ($LASTEXITCODE -ne 0) { Write-Host "Remote deploy failed." -ForegroundColor Red; exit $LASTEXITCODE }
Write-Host "Deploy complete." -ForegroundColor Green
