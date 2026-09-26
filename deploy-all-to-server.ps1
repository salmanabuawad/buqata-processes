# Deploy frontend + backend to tender.kortexd.com in one go
# Runs deploy-to-server.ps1 then deploy-backend-to-server.ps1 (see DEPLOY_SERVER.md)
# Skip confirmation: $env:DEPLOY_SKIP_CONFIRM = "1"

$ErrorActionPreference = "Stop"
$SERVER = if ($env:DEPLOY_HOST) { $env:DEPLOY_HOST } else { "185.229.226.37" }
$USER = if ($env:DEPLOY_USER) { $env:DEPLOY_USER } else { "root" }
$REMOTE_PATH = if ($env:DEPLOY_PATH) { $env:DEPLOY_PATH.TrimEnd("/") } else { "/opt/buqata-processes/frontend/dist" }
$REMOTE_APP = if ($env:BACKEND_REMOTE_PATH) { $env:BACKEND_REMOTE_PATH.TrimEnd("/") } else { "/opt/buqata-processes" }
$APP_URL = if ($env:DEPLOY_APP_URL) { $env:DEPLOY_APP_URL } else { "https://tender.kortexd.com/" }

Write-Host ""
Write-Host "========== DEPLOY ALL (FRONTEND + BACKEND) ==========" -ForegroundColor Yellow
Write-Host "  Server:       $USER@$SERVER"
Write-Host "  Frontend:     $REMOTE_PATH"
Write-Host "  Backend:      $REMOTE_APP"
Write-Host "  App URL:      $APP_URL"
Write-Host "=====================================================" -ForegroundColor Yellow
Write-Host ""

if (-not $env:DEPLOY_SKIP_CONFIRM) {
    $confirm = Read-Host "Deploy frontend and backend to the above target? [y/N]"
    if ($confirm -notmatch '^[yY]') {
        Write-Host "Deploy cancelled." -ForegroundColor Yellow
        exit 0
    }
}

$env:DEPLOY_SKIP_CONFIRM = "1"
try {
    Write-Host "[1/2] Deploying frontend..." -ForegroundColor Cyan
    & "$PSScriptRoot\deploy-to-server.ps1"
    if ($LASTEXITCODE -ne 0) { Write-Host "Frontend deploy failed." -ForegroundColor Red; exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "[2/2] Deploying backend..." -ForegroundColor Cyan
    & "$PSScriptRoot\deploy-backend-to-server.ps1"
    if ($LASTEXITCODE -ne 0) { Write-Host "Backend deploy failed." -ForegroundColor Red; exit $LASTEXITCODE }
} finally {
    Remove-Item Env:\DEPLOY_SKIP_CONFIRM -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Deploy complete. Frontend + backend live at $APP_URL" -ForegroundColor Green
