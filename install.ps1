# Instalador de udemy-transcripts para Windows (PowerShell).
# Crea un entorno aislado con Playwright + Chromium y el comando global `udemy`.
$ErrorActionPreference = "Stop"

$AppDir = Join-Path $env:LOCALAPPDATA "udemy-transcripts"
$Venv   = Join-Path $AppDir "venv"
$SrcDir = $PSScriptRoot

Write-Host "Instalando udemy-transcripts..." -ForegroundColor Cyan

# 1) Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Necesitas Python 3 instalado. Descargalo de https://www.python.org/downloads/ " -ForegroundColor Red
    Write-Host "(marca 'Add Python to PATH' durante la instalacion)."
    exit 1
}

# 2) entorno aislado + script
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
Copy-Item (Join-Path $SrcDir "udemy_transcripts.py") (Join-Path $AppDir "udemy_transcripts.py") -Force

Write-Host "  - Creando entorno virtual..."
python -m venv $Venv
& (Join-Path $Venv "Scripts\python.exe") -m pip install --upgrade pip | Out-Null
Write-Host "  - Instalando Playwright..."
& (Join-Path $Venv "Scripts\pip.exe") install playwright | Out-Null
Write-Host "  - Descargando Chromium (~170 MB, puede tardar)..."
& (Join-Path $Venv "Scripts\python.exe") -m playwright install chromium

# 3) comando global `udemy` (udemy.cmd en una carpeta del PATH del usuario)
$BinDir = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"   # ya suele estar en el PATH
if (-not (Test-Path $BinDir)) { $BinDir = $AppDir }
$pyExe = Join-Path $Venv "Scripts\python.exe"
$script = Join-Path $AppDir "udemy_transcripts.py"
$cmd = "@echo off`r`n`"$pyExe`" `"$script`" %*"
Set-Content -Path (Join-Path $BinDir "udemy.cmd") -Value $cmd -Encoding ascii

Write-Host ""
Write-Host "Listo! Comando instalado: udemy" -ForegroundColor Green
if ($BinDir -eq $AppDir) {
    Write-Host "Anade esta carpeta a tu PATH: $AppDir" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Uso:"
Write-Host "    udemy --list"
Write-Host "    udemy `"https://www.udemy.com/course/...`""
Write-Host "    udemy --txt `"https://www.udemy.com/course/...`""
