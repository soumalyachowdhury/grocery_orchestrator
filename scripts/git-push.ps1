param(
    [string]$RepoUrl = "https://github.com/soumalyachowdhury/grocery_orchestrator.git",
    [string]$Branch = "main",
    [string]$Message = "Add grocery chatbot orchestrator"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or not available on PATH. Install Git for Windows from https://git-scm.com/download/win"
}

if (-not (Test-Path ".git")) {
    git init
}

$ExistingOrigin = git remote get-url origin 2>$null
if (-not $ExistingOrigin) {
    git remote add origin $RepoUrl
}

git add .env.example .gitignore README.md requirements.txt app customer_agent_server tests scripts
git commit -m $Message
git branch -M $Branch
git push -u origin $Branch

