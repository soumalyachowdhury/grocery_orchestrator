$ErrorActionPreference = "Stop"

$Connections = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $Connections) {
    Write-Host "No chatbot server is listening on port 8000."
    exit 0
}

$ProcessIds = $Connections | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($ProcessId in $ProcessIds) {
    Write-Host "Stopping process $ProcessId on port 8000..."
    Stop-Process -Id $ProcessId -Force
}

Write-Host "Chatbot server stopped."

*** Add File: scripts/restart-chatbot.ps1
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

& ".\scripts\stop-chatbot.ps1"
& ".\scripts\run-chatbot.ps1"
