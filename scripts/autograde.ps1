# AutoGrade launcher - Windows.
#
# You do not run this directly. Double-click one of these instead:
#
#   Start AutoGrade.bat      Stop AutoGrade.bat      Restart AutoGrade.bat
#   Update AutoGrade.bat     Backup AutoGrade.bat    Restore AutoGrade.bat
#
# Everything AutoGrade needs - database, migrations, API, grading worker
# and the web interface - is started and stopped by this script. There is
# nothing else to run and no file to edit.

param(
    [ValidateSet("start", "stop", "restart", "update", "backup", "restore",
                 "status", "logs")]
    [string]$Command = "start"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Compose = $null
$ComposeFile = "docker-compose.local.yml"
$DefaultPort = 8501
$DefaultApiPort = 8000

# ---------------------------------------------------------------- output
function Say  { param($m) Write-Host $m }
function Head { param($m) Write-Host ""; Write-Host $m -ForegroundColor Cyan }
function OK   { param($m) Write-Host "  OK   $m" -ForegroundColor Green }
function Warn { param($m) Write-Host "  ...  $m" -ForegroundColor Yellow }
function Fail {
    param($m, $fix)
    Write-Host ""
    Write-Host "  PROBLEM  $m" -ForegroundColor Red
    if ($fix) { Write-Host ""; Write-Host "  What to do: $fix" }
    Write-Host ""
    Write-Host "  If you are stuck, see TROUBLESHOOTING.md in this folder."
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

# ---------------------------------------------------------------- docker
function Find-Compose {
    if (Test-Command "docker" @("compose")) { return @("docker", "compose") }
    if (Test-Command "docker-compose" @()) { return @("docker-compose") }
    $plugin = Join-Path $env:ProgramFiles "Docker\Docker\resources\cli-plugins\docker-compose.exe"
    if (Test-Path $plugin) { return @($plugin) }
    return $null
}

function Test-Command {
    param($Exe, $Args)
    try {
        & $Exe @Args version 2>&1 | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Invoke-Compose {
    $exe = $script:Compose[0]
    $pre = @()
    if ($script:Compose.Count -gt 1) {
        $pre = $script:Compose[1..($script:Compose.Count - 1)]
    }
    & $exe @pre -f $ComposeFile @args
}

function Start-DockerDesktop {
    $exe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $exe)) { return $false }
    Warn "Docker Desktop is not running. Starting it - this takes a minute."
    Start-Process $exe | Out-Null
    foreach ($i in 1..90) {
        Start-Sleep -Seconds 2
        docker info 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { return $true }
    }
    return $false
}

function Require-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Fail "Docker Desktop is not installed." `
             "Install it from https://docs.docker.com/get-docker/, restart your computer, then try again. INSTALL.md step 1 has pictures."
    }
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        if (-not (Start-DockerDesktop)) {
            Fail "Docker Desktop is installed but will not start." `
                 "Open Docker Desktop from the Start menu yourself, wait until the whale icon stops moving, then run Start AutoGrade again."
        }
    }
    $script:Compose = Find-Compose
    if (-not $script:Compose) {
        Fail "Docker is installed but Docker Compose is missing." `
             "Update Docker Desktop to the current version from https://docs.docker.com/get-docker/"
    }
    OK "Docker is running"
}

# ------------------------------------------------------------------ .env
function New-Secret {
    param([int]$Length = 48)
    $bytes = New-Object byte[] 96
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    ([Convert]::ToBase64String($bytes) -replace '[^A-Za-z0-9]', '').Substring(0, $Length)
}

function Test-PortFree {
    param([int]$Port)
    $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return -not $busy
}

function Find-FreePort {
    param([int]$Start)
    foreach ($p in $Start..($Start + 20)) {
        if (Test-PortFree $p) { return $p }
    }
    return $Start
}

function Get-EnvValue {
    param([string]$Name)
    if (-not (Test-Path .env)) { return $null }
    foreach ($line in Get-Content .env) {
        if ($line -match "^$Name=(.*)$") { return $Matches[1] }
    }
    return $null
}

function New-EnvFile {
    Head "First run - setting AutoGrade up"

    $port = Find-FreePort $DefaultPort
    $apiPort = Find-FreePort $DefaultApiPort
    if ($port -ne $DefaultPort) { Warn "Port $DefaultPort is in use; using $port instead" }

    $content = @"
# Written by Start AutoGrade. You do not need to edit this file.
#
# Your AI provider and your Canvas connection are configured inside
# AutoGrade, under Settings. Nothing here needs your attention.

ENVIRONMENT=production

# Where AutoGrade appears in your browser.
AUTOGRADE_PORT=$port
AUTOGRADE_API_PORT=$apiPort

# --- generated secrets: do not share, do not change once in use ---
SECRET_KEY=$(New-Secret 48)
CREDENTIAL_ENCRYPTION_KEY=$(New-Secret 48)
POSTGRES_PASSWORD=$(New-Secret 24)

# Accounts are created inside AutoGrade by whoever installed it.
ALLOW_OPEN_REGISTRATION=false

# --- uploads ---
UPLOAD_DIR=/app/uploads
MAX_FILE_SIZE_MB=50
MAX_REQUEST_BODY_MB=300

# --- automatic backups, into the backups folder next to this file ---
BACKUP_INTERVAL_HOURS=24
BACKUP_RETENTION_DAYS=30
"@
    # UTF-8 without a BOM: Docker will not parse a BOM in an env file.
    [IO.File]::WriteAllText("$Root\.env", $content,
                            (New-Object Text.UTF8Encoding $false))
    OK "Settings written"
}

function Get-Port {
    $port = Get-EnvValue "AUTOGRADE_PORT"
    if ($port) { return [int]$port }
    return $DefaultPort
}

function Get-ApiPort {
    $port = Get-EnvValue "AUTOGRADE_API_PORT"
    if ($port) { return [int]$port }
    return $DefaultApiPort
}

# ---------------------------------------------------------------- health
function Wait-Healthy {
    param([int]$ApiPort, [int]$TimeoutSeconds = 300)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $shown = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$ApiPort/api/health" `
                                   -TimeoutSec 3 -UseBasicParsing
            if ($r.StatusCode -eq 200) { return $true }
        } catch {
            if (-not $shown) { Warn "Waiting for AutoGrade to be ready..."; $shown = $true }
        }
        Start-Sleep -Seconds 3
    }
    return $false
}

function Wait-Page {
    param([int]$Port, [int]$TimeoutSeconds = 120)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port" -TimeoutSec 3 -UseBasicParsing
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

# --------------------------------------------------------------- actions
function Do-Start {
    Say ""
    Say "AutoGrade"
    Say "========="
    Require-Docker

    $firstRun = -not (Test-Path .env)
    if ($firstRun) { New-EnvFile }
    if (-not (Test-Path "$Root\backups")) {
        New-Item -ItemType Directory "$Root\backups" | Out-Null
    }

    $port = Get-Port
    $apiPort = Get-ApiPort

    if ($firstRun) {
        Head "Building AutoGrade"
        Say  "  The first time takes 5 to 10 minutes and prints a lot of text."
        Say  "  You only wait this long once. Later starts take a few seconds."
        Say  ""
    } else {
        Head "Starting AutoGrade"
    }

    Invoke-Compose up -d --build
    if ($LASTEXITCODE -ne 0) {
        Fail "AutoGrade did not start." `
             "Double-click 'Show AutoGrade Logs.bat' and look at the last few lines, or see TROUBLESHOOTING.md."
    }

    Head "Checking that everything is working"
    if (-not (Wait-Healthy -ApiPort $apiPort)) {
        Fail "AutoGrade started but is not answering." `
             "Wait another minute and run Start AutoGrade again. If it keeps happening, see TROUBLESHOOTING.md."
    }
    OK "Database, grading worker and interface are all running"

    Wait-Page -Port $port | Out-Null

    $url = "http://localhost:$port"
    Head "AutoGrade is ready"
    Say  "  Opening $url in your browser."
    Say  ""
    if ($firstRun) {
        Say "  The first account you create becomes the administrator."
        Say "  Create yours now, then set your AI provider under"
        Say "  Settings -> AI providers."
    }
    Say  ""
    Say  "  Leave this window closed or open, it makes no difference."
    Say  "  AutoGrade keeps running until you use Stop AutoGrade."
    Say  ""
    Start-Process $url
}

function Do-Stop {
    Say ""
    Head "Stopping AutoGrade"
    Require-Docker
    Invoke-Compose stop
    OK "Stopped. Your courses, grades and files are safe."
    Say "  Start it again with Start AutoGrade."
    Say ""
}

function Do-Restart {
    Do-Stop
    Do-Start
}

function Do-Update {
    Say ""
    Head "Updating AutoGrade"
    Require-Docker
    Say "  Taking a backup first, so this can be undone."
    Do-Backup -Quiet
    Invoke-Compose up -d --build
    if ($LASTEXITCODE -ne 0) {
        Fail "The update did not finish." `
             "Your backup is in the backups folder. See TROUBLESHOOTING.md."
    }
    if (-not (Wait-Healthy -ApiPort (Get-ApiPort))) {
        Fail "AutoGrade did not come back after the update." `
             "Use Restore AutoGrade to go back to the backup taken a moment ago."
    }
    OK "Updated and running"
    Say ""
}

function Do-Backup {
    param([switch]$Quiet)
    if (-not $Quiet) { Say ""; Head "Backing up" }
    Require-Docker

    $stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
    $name = "autograde-$stamp"

    Invoke-Compose exec -T db pg_dump -U autograde -d autograde -Fc -f "/backups/$name.dump"
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not back up the gradebook." `
             "Is AutoGrade running? Start it first, then try again."
    }

    # Student files live outside the database, so they need their own copy
    # or a restore would bring back grades with nothing attached to them.
    Invoke-Compose exec -T api tar czf "/tmp/$name-files.tgz" -C /app/uploads .
    Invoke-Compose cp "api:/tmp/$name-files.tgz" "backups/$name-files.tgz" | Out-Null

    OK "Saved to the backups folder:"
    Say "     $name.dump          the gradebook"
    Say "     $name-files.tgz     the submitted files"
    Say ""
    Say "  Copy that folder to a USB stick or cloud drive from time to time."
    Say "  A backup on the same computer does not survive losing the computer."
    Say ""
}

function Do-Restore {
    Say ""
    Head "Restoring from a backup"
    Say "  This replaces everything currently in AutoGrade."
    Say ""
    Require-Docker

    $dumps = Get-ChildItem "$Root\backups\*.dump" -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending
    if (-not $dumps) {
        Fail "There are no backups in the backups folder." `
             "Use Backup AutoGrade to make one."
    }

    Say "  Which backup?"
    Say ""
    for ($i = 0; $i -lt $dumps.Count; $i++) {
        "    {0}) {1}   ({2})" -f ($i + 1), $dumps[$i].Name,
            $dumps[$i].LastWriteTime.ToString("d MMM yyyy, HH:mm") | Write-Host
    }
    Say ""
    $choice = Read-Host "  Type a number and press Enter (or press Enter to cancel)"
    if (-not $choice) { Say "  Cancelled."; Say ""; return }
    $index = [int]$choice - 1
    if ($index -lt 0 -or $index -ge $dumps.Count) { Say "  Not a valid choice."; return }
    $dump = $dumps[$index]

    Say ""
    Warn "Everything now in AutoGrade will be replaced by $($dump.Name)."
    $confirm = Read-Host "  Type RESTORE to continue"
    if ($confirm -ne "RESTORE") { Say "  Cancelled."; Say ""; return }

    Invoke-Compose stop api worker frontend | Out-Null
    Invoke-Compose start db | Out-Null
    Start-Sleep -Seconds 5

    Invoke-Compose exec -T db pg_restore -U autograde -d autograde --clean --if-exists "/backups/$($dump.Name)"
    # pg_restore reports non-zero for harmless "does not exist" notices on a
    # --clean restore into an empty database, so the health check below is
    # what decides whether this worked, not the exit code.

    $files = "$Root\backups\" + ($dump.BaseName) + "-files.tgz"
    Invoke-Compose start api worker frontend | Out-Null
    if (Test-Path $files) {
        Start-Sleep -Seconds 5
        Invoke-Compose cp $files "api:/tmp/restore-files.tgz" | Out-Null
        Invoke-Compose exec -T api tar xzf /tmp/restore-files.tgz -C /app/uploads
        OK "Submitted files restored"
    } else {
        Warn "No matching files archive; grades restored without the original submissions."
    }

    if (Wait-Healthy -ApiPort (Get-ApiPort)) {
        OK "Restored. Open AutoGrade and check a course you recognise."
    } else {
        Fail "AutoGrade did not come back after the restore." `
             "Run Start AutoGrade. If it still fails, see TROUBLESHOOTING.md."
    }
    Say ""
}

function Do-Status {
    Say ""
    Head "AutoGrade status"
    Require-Docker
    Invoke-Compose ps
    Say ""
    $apiPort = Get-ApiPort
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$apiPort/api/health" `
                               -TimeoutSec 5 -UseBasicParsing
        OK "Answering normally"
        Say "  $($r.Content)"
    } catch {
        Warn "Not answering. Use Start AutoGrade."
    }
    Say ""
    Say "  Web address: http://localhost:$(Get-Port)"
    Say ""
}

function Do-Logs {
    Require-Docker
    Say ""
    Say "  The last 100 lines from each part of AutoGrade."
    Say "  Send this to whoever supports you if you are stuck."
    Say ""
    Invoke-Compose logs --tail 100
    Say ""
}

switch ($Command) {
    "start"   { Do-Start }
    "stop"    { Do-Stop }
    "restart" { Do-Restart }
    "update"  { Do-Update }
    "backup"  { Do-Backup }
    "restore" { Do-Restore }
    "status"  { Do-Status }
    "logs"    { Do-Logs }
}
