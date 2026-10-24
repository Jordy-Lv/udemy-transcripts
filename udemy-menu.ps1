# Abre el menu interactivo de udemy-transcripts en PowerShell.
#
#   .\udemy-menu.ps1                         (clic derecho > Ejecutar con PowerShell tambien sirve)
#
# Usa el codigo de esta carpeta si tiene su entorno (.venv); si no, el instalado con install.ps1
# o el comando `udemy` del PATH.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$localPy   = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$installed = Join-Path $env:LOCALAPPDATA "udemy-transcripts\venv\Scripts\udemy.exe"

if (Test-Path $localPy) {
    $env:PYTHONPATH = $PSScriptRoot
    & $localPy -m udemy_transcripts --menu
} elseif (Test-Path $installed) {
    & $installed --menu
} elseif (Get-Command udemy -ErrorAction SilentlyContinue) {
    udemy --menu
} else {
    Write-Host "No encuentro udemy-transcripts. Instalalo con:" -ForegroundColor Red
    Write-Host "    powershell -ExecutionPolicy Bypass -File install.ps1"
    Read-Host "Pulsa Enter para cerrar"
    exit 1
}
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
    Read-Host "El menu termino con codigo $LASTEXITCODE. Pulsa Enter para cerrar"
}
exit $LASTEXITCODE
