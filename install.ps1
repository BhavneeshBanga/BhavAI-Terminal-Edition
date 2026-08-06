# ============================================================
# BhavAI installer (Windows / PowerShell)
# Usage:
#   irm https://raw.githubusercontent.com/BhavneeshBanga/bhavai-terminal-edition/main/install.ps1 | iex
# ============================================================

$ErrorActionPreference = "Stop"

# --- EDIT THIS: your GitHub repo ---
$RepoUrl  = "https://github.com/BhavneeshBanga/bhavai-terminal-edition.git"
$InstallDir = "$env:LOCALAPPDATA\bhavai"

function Write-Info($msg)  { Write-Host "[bhavai] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "[bhavai] $msg" -ForegroundColor Green }
function Write-Err($msg)   { Write-Host "[bhavai] $msg" -ForegroundColor Red }

# 1. Check Python
Write-Info "Checking Python..."
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Err "Python 3.10+ not found. Install it from https://python.org and re-run this script."
    exit 1
}
$pythonExe = $python.Source

$verOutput = & $pythonExe --version
Write-Info "Found $verOutput"

# 2. Check git
Write-Info "Checking git..."
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Write-Err "git not found. Install it from https://git-scm.com and re-run this script."
    exit 1
}

# 3. Clone or update repo
if (Test-Path $InstallDir) {
    Write-Info "Existing install found, updating..."
    Push-Location $InstallDir
    git pull --ff-only
    Pop-Location
} else {
    Write-Info "Cloning bhavai into $InstallDir ..."
    git clone --depth 1 $RepoUrl $InstallDir
}

# 4. Install with pip (editable-free, isolated via pipx if available, else pip --user)
$pipx = Get-Command pipx -ErrorAction SilentlyContinue
if ($pipx) {
    Write-Info "Installing with pipx..."
    pipx install $InstallDir --force
} else {
    Write-Info "pipx not found, installing with pip --user..."
    & $pythonExe -m pip install --user --upgrade $InstallDir
}

# 5. Verify
Write-Info "Verifying installation..."
$bhav = Get-Command bhav -ErrorAction SilentlyContinue
if ($bhav) {
    Write-Ok "bhavai installed successfully! Run 'bhav' to start."
} else {
    Write-Ok "Install finished. If 'bhav' is not recognized, add your Python Scripts folder to PATH:"
    Write-Host "   $((& $pythonExe -m site --user-base))\Scripts" -ForegroundColor Yellow
    Write-Host "Then restart your terminal."
}

# 6. Prompt for API key (Sarvam-105B)
if (-not $env:SARVAM_API_KEY) {
    Write-Host ""
    Write-Info "Set your Sarvam API key before first use:"
    Write-Host '   setx SARVAM_API_KEY "your-key-here"' -ForegroundColor Yellow
}