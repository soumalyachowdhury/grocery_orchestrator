param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    & $Python -m venv .venv
}

Write-Host "Installing dependencies..."
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "Setup complete."
Write-Host "Run tests: .\scripts\test.ps1"
Write-Host "Run customer API: .\scripts\run-customer-agent.ps1"
Write-Host "Run chatbot API: .\scripts\run-chatbot.ps1"

