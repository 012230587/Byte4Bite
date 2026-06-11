# Byte4Bite dev helper for Windows (PowerShell)
# Mirrors Makefile targets when GNU Make is not installed.
#
# Usage:
#   .\dev.ps1 help
#   .\dev.ps1 setup
#   .\dev.ps1 up
#   .\dev.ps1 backend
#   .\dev.ps1 down

param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "help", "setup", "setup-env", "install", "install-backend", "install-frontend",
        "up", "backend", "frontend", "down", "build", "lint", "verify", "backfill",
        "ingest", "migrate", "db-check", "health"
    )]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Backend = Join-Path $Root "Backend"
$Frontend = Join-Path $Root "Frontend"
$HostAddr = "127.0.0.1"
$BackendPort = 8000
$FrontendPort = 3000

function Show-Help {
    Write-Host "Byte4Bite dev.ps1 (Windows)"
    Write-Host ""
    Write-Host "  .\dev.ps1 setup          First-time env + dependencies"
    Write-Host "  .\dev.ps1 up             Start backend + frontend"
    Write-Host "  .\dev.ps1 backend        API only (:8000)"
    Write-Host "  .\dev.ps1 frontend       Dashboard only (:3000)"
    Write-Host "  .\dev.ps1 down           Stop ports 8000 and 3000"
    Write-Host "  .\dev.ps1 verify         Semantic search health check"
    Write-Host "  .\dev.ps1 backfill       Embed missing recipes"
    Write-Host "  .\dev.ps1 ingest         Sync CSV datasets"
    Write-Host "  .\dev.ps1 migrate        Apply DB migration 002"
    Write-Host "  .\dev.ps1 db-check       Test MySQL connection"
    Write-Host "  .\dev.ps1 health         db-check + verify"
}

function Invoke-SetupEnv {
    $envFile = Join-Path $Backend ".env"
    $example = Join-Path $Backend ".env.example"
    if (-not (Test-Path $envFile)) {
        Copy-Item $example $envFile
        Write-Host "Created Backend/.env - set GEMINI_API_KEY and MySQL credentials"
    } else {
        Write-Host "Backend/.env already exists"
    }
    $localEnv = Join-Path $Frontend ".env.local"
    if (-not (Test-Path $localEnv)) {
        Set-Content -Path $localEnv -Value "NEXT_PUBLIC_API_URL=http://${HostAddr}:${BackendPort}"
        Write-Host "Created Frontend/.env.local"
    } else {
        Write-Host "Frontend/.env.local already exists"
    }
}

function Stop-PortListeners {
    param([int[]]$Ports)
    foreach ($port in $Ports) {
        Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
            ForEach-Object {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            }
    }
    Write-Host "Stopped listeners on ports $($Ports -join ', ') (if any)"
}

switch ($Command) {
    "help" { Show-Help }
    "setup-env" { Invoke-SetupEnv }
    "install-backend" {
        Push-Location $Backend
        pip install -r requirements.txt
        Pop-Location
    }
    "install-frontend" {
        Push-Location $Frontend
        npm install
        Pop-Location
    }
    "install" {
        & $PSCommandPath install-backend
        & $PSCommandPath install-frontend
    }
    "setup" {
        & $PSCommandPath setup-env
        & $PSCommandPath install
        Write-Host "Setup complete. Edit Backend/.env then run: .\dev.ps1 up"
    }
    "backend" {
        Push-Location $Backend
        python -m uvicorn main:app --host $HostAddr --port $BackendPort --reload
    }
    "frontend" {
        Push-Location $Frontend
        npm run dev
    }
    "up" {
        Write-Host "Starting Byte4Bite - backend http://${HostAddr}:${BackendPort}  frontend http://${HostAddr}:${FrontendPort}"
        $backendCmd = "Set-Location -LiteralPath '$Backend'; python -m uvicorn main:app --host $HostAddr --port $BackendPort --reload"
        $frontendCmd = "Set-Location -LiteralPath '$Frontend'; npm run dev"
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd
        Write-Host "Opened two terminals (backend + frontend). Use .\dev.ps1 down to stop."
    }
    "down" { Stop-PortListeners -Ports @($BackendPort, $FrontendPort) }
    "build" {
        Push-Location $Frontend
        npm run build
        Pop-Location
    }
    "lint" {
        Push-Location $Frontend
        npm run lint
        Pop-Location
    }
    "verify" {
        Push-Location $Backend
        python scripts/verify_semantic_search.py
        Pop-Location
    }
    "backfill" {
        Push-Location $Backend
        python -m rag.backfill_embeddings
        Pop-Location
    }
    "ingest" {
        Push-Location $Backend
        python -m rag.ingest
        Pop-Location
    }
    "migrate" {
        Push-Location $Backend
        python -m scripts.apply_migration_002
        Pop-Location
    }
    "db-check" {
        Push-Location $Backend
        python -c "from database.connection import ping_database; print('MySQL OK' if ping_database() else 'MySQL FAILED')"
        Pop-Location
    }
    "health" {
        & $PSCommandPath db-check
        & $PSCommandPath verify
    }
}
