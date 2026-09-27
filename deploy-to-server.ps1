# Deploy the frontend (static Next.js export) to tender.kortexd.com
# Default: root@185.229.226.37, path /opt/buqata-processes/frontend/dist (see DEPLOY_SERVER.md)
# Override: DEPLOY_HOST, DEPLOY_USER, DEPLOY_PATH, DEPLOY_APP_URL
# Skip confirmation: $env:DEPLOY_SKIP_CONFIRM = "1"

$ErrorActionPreference = "Stop"

# Deploy committed code only: the scripts upload the working tree, so any
# uncommitted change (including another session's work in progress) would go
# live. Override deliberately with $env:DEPLOY_ALLOW_DIRTY = "1".
if (-not $env:DEPLOY_ALLOW_DIRTY) {
    $dirty = & git -C $PSScriptRoot status --porcelain
    if ($LASTEXITCODE -ne 0) { Write-Host "git status failed - deploy aborted." -ForegroundColor Red; exit 1 }
    if ($dirty) {
        Write-Host "Uncommitted changes in the repository - deploy aborted:" -ForegroundColor Red
        $dirty | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" }
        Write-Host "Commit (or stash) them first, or set DEPLOY_ALLOW_DIRTY=1 on purpose." -ForegroundColor Yellow
        exit 1
    }
}
$SERVER = if ($env:DEPLOY_HOST) { $env:DEPLOY_HOST } else { "185.229.226.37" }
$USER = if ($env:DEPLOY_USER) { $env:DEPLOY_USER } else { "root" }
$REMOTE_PATH = if ($env:DEPLOY_PATH) { $env:DEPLOY_PATH.TrimEnd("/") } else { "/opt/buqata-processes/frontend/dist" }
$APP_URL = if ($env:DEPLOY_APP_URL) { $env:DEPLOY_APP_URL } else { "https://tender.kortexd.com/" }

Write-Host ""
Write-Host "========== DEPLOY TARGET ==========" -ForegroundColor Yellow
Write-Host "  Server:    $USER@$SERVER"
Write-Host "  Path:      $REMOTE_PATH"
Write-Host "  App URL:   $APP_URL"
Write-Host "===================================" -ForegroundColor Yellow
Write-Host ""

if (-not $env:DEPLOY_SKIP_CONFIRM) {
    $confirm = Read-Host "Deploy to the above target? [y/N]"
    if ($confirm -notmatch '^[yY]') {
        Write-Host "Deploy cancelled." -ForegroundColor Yellow
        exit 0
    }
}

Write-Host "Building frontend..." -ForegroundColor Cyan
Push-Location (Join-Path $PSScriptRoot "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
Pop-Location

# Next.js static export writes to out/ (the equivalent of Vite's dist/).
$distPath = Join-Path (Join-Path $PSScriptRoot "frontend") "out"
if (-not (Test-Path $distPath)) {
    Write-Host "Error: out folder not found at $distPath. Build failed?" -ForegroundColor Red
    exit 1
}

Write-Host "Deploying to ${USER}@${SERVER}:${REMOTE_PATH}" -ForegroundColor Cyan
$remoteTemp = "/tmp/buqata_processes_frontend_deploy"
$scpTarget = "${USER}@${SERVER}:${remoteTemp}"
& ssh "${USER}@${SERVER}" "rm -rf $remoteTemp"
Write-Host "Uploading out to $scpTarget ..."
& scp -r "$distPath" $scpTarget
if ($LASTEXITCODE -ne 0) {
    Write-Host "SCP failed. Ensure you have SSH key access: ssh $USER@$SERVER" -ForegroundColor Red
    exit $LASTEXITCODE
}

$remoteCmd = "mkdir -p $REMOTE_PATH && rm -rf ${REMOTE_PATH}/* && (mv ${remoteTemp}/out/* $REMOTE_PATH/ 2>/dev/null || mv ${remoteTemp}/* $REMOTE_PATH/) && rm -rf $remoteTemp && chmod -R a+rX $REMOTE_PATH"
Write-Host "Moving files into place on server..."
& ssh "${USER}@${SERVER}" $remoteCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "SSH command failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Frontend deploy complete. App: $APP_URL" -ForegroundColor Green
