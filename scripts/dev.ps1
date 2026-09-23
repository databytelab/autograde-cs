# AutoGrade - development launcher.
#
# Double-click "Start Dev.bat" instead of running this directly.
#
# Runs the three processes that make up AutoGrade straight from the source
# tree, without Docker: the API, the grading worker, and the Streamlit
# interface. This is the developer's equivalent of "Start AutoGrade" - it
# uses the SQLite database and the .env in this folder, which is separate
# data from the Docker installation.

param([ValidateSet("start", "stop", "status")] [string]$Command = "start")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = "$Root\venv\Scripts\python.exe"
$ApiPort = 8000
$UiPort = 8501
$Url = "http://localhost:$UiPort"

function Say  { param($m) Write-Host $m }
function OK   { param($m) Write-Host "  OK   $m" -ForegroundColor Green }
function Warn { param($m) Write-Host "  ...  $m" -ForegroundColor Yellow }
function Die  {
    param($m, $fix)
    Write-Host ""
    Write-Host "  PROBLEM  $m" -ForegroundColor Red
    if ($fix) { Write-Host ""; Write-Host "  What to do: $fix" }
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

function Get-DevProcesses {
    # The three commands this script starts, and nothing else on the machine.
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $_.CommandLine -match "uvicorn backend.main" -or
            $_.CommandLine -match "streamlit run frontend_streamlit" -or
            $_.CommandLine -match "backend\.worker"
        }
}

function Test-Port {
    param([int]$Port)
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Url {
    param([string]$Address, [int]$Seconds = 90)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            if ((Invoke-WebRequest $Address -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200) {
                return $true
            }
        } catch { Start-Sleep -Seconds 2 }
    }
    return $false
}

function Do-Stop {
    $running = Get-DevProcesses
    if (-not $running) { Say "  Nothing was running."; return }
    foreach ($p in $running) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    OK "Stopped. Your data is untouched."
}

function Do-Status {
    $running = Get-DevProcesses
    if (-not $running) { Say "  Not running."; return }
    Say "  Running:"
    foreach ($p in $running) {
        $what = if ($p.CommandLine -match "uvicorn") { "API" }
                elseif ($p.CommandLine -match "backend.worker") { "worker" }
                else { "interface" }
        "    {0,-10} PID {1}" -f $what, $p.ProcessId | Write-Host
    }
    try {
        $h = (Invoke-WebRequest "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 5 -UseBasicParsing).Content
        OK "Answering: $h"
    } catch { Warn "Processes are up but the API is not answering yet." }
    Say "  $Url"
}

function Do-Start {
    Say ""
    Say "AutoGrade - development"
    Say "======================="

    if (-not (Test-Path $Python)) {
        Die "The virtual environment is missing ($Python)." `
            "Create it once: python -m venv venv, then venv\Scripts\python.exe -m pip install -r requirements.txt"
    }
    if (-not (Test-Path "$Root\.env")) {
        Die "There is no .env file in this folder." `
            "Copy .env.example to .env and put your OPENAI_API_KEY in it - or leave it out and set the key in Settings once the app is running."
    }

    if (Get-DevProcesses) {
        Warn "Already running. Opening the browser."
        Start-Process $Url
        Say ""
        return
    }
    if ((Test-Port $ApiPort) -or (Test-Port $UiPort)) {
        Die "Port $ApiPort or $UiPort is already in use by something else." `
            "Close whatever is using it, or run 'Stop Dev.bat' first."
    }

    # Cheap and idempotent. Saves the "no such table" that follows a pull
    # with a new migration in it.
    Say "  Bringing the database up to date..."
    # Alembic writes its progress to stderr, and with ErrorActionPreference
    # set to Stop, PowerShell treats any stderr from a native command as a
    # terminating error - so a perfectly successful migration killed the
    # launcher. Relaxed just for this call.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Python -m alembic upgrade head *>&1 | Out-Null
    $ErrorActionPreference = $previous

    Say "  Starting the API..."
    Start-Process $Python "-m uvicorn backend.main:app --port $ApiPort" `
        -WorkingDirectory $Root -WindowStyle Minimized
    if (-not (Wait-Url "http://127.0.0.1:$ApiPort/api/health")) {
        Die "The API did not start." "Start it in a terminal to see why: venv\Scripts\python.exe -m uvicorn backend.main:app --port $ApiPort"
    }
    OK "API"

    Say "  Starting the grading worker..."
    Start-Process $Python "-m backend.worker" `
        -WorkingDirectory $Root -WindowStyle Minimized
    OK "Worker (silent until you grade something - that is correct)"

    Say "  Starting the interface..."
    # --server.headless true stops Streamlit from opening its OWN browser tab;
    # we open exactly one below (Start-Process $Url). Without it you get two
    # tabs of the same interface.
    Start-Process $Python `
        "-m streamlit run frontend_streamlit/app.py --server.headless true" `
        -WorkingDirectory $Root -WindowStyle Minimized
    if (-not (Wait-Url $Url)) {
        Warn "The interface is taking longer than usual. Try $Url in a minute."
    } else {
        OK "Interface"
    }

    Say ""
    Say "  Open:  $Url"
    Say ""
    Say "  Three windows are now minimised in the taskbar. Closing them, or"
    Say "  double-clicking 'Stop Dev.bat', shuts AutoGrade down."
    Say ""
    Start-Process $Url
}

switch ($Command) {
    "start"  { Do-Start }
    "stop"   { Say ""; Do-Stop; Say "" }
    "status" { Say ""; Do-Status; Say "" }
}
