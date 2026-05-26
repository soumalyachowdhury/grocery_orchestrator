$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not $env:TWILIO_WHATSAPP_PORT) {
    $env:TWILIO_WHATSAPP_PORT = "8080"
}

if (-not $env:ORCHESTRATOR_API_URL) {
    $env:ORCHESTRATOR_API_URL = "http://127.0.0.1:8000/api/chat"
}

Write-Host "Starting Twilio WhatsApp bridge on port $env:TWILIO_WHATSAPP_PORT"
Write-Host "Forwarding to orchestrator: $env:ORCHESTRATOR_API_URL"

$BundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
if (Test-Path $BundledNode) {
    & $BundledNode .\node_server\twilio_whatsapp_server.js
    exit $LASTEXITCODE
}

$NodeCommand = Get-Command node -ErrorAction SilentlyContinue
if ($NodeCommand) {
    & $NodeCommand.Source .\node_server\twilio_whatsapp_server.js
    exit $LASTEXITCODE
}

Write-Error "Node.js was not found. Install Node.js from https://nodejs.org, then run this script again."
