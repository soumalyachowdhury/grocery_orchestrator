param(
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

Write-Host "Starting mock customer lookup agent on http://127.0.0.1:$Port"
& ".\.venv\Scripts\python.exe" -m uvicorn customer_agent_server.main:app --host 127.0.0.1 --port $Port --reload

