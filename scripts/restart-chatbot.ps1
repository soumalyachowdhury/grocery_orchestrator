$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

& ".\scripts\stop-chatbot.ps1"
& ".\scripts\run-chatbot.ps1"
