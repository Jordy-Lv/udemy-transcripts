# Instalador de udemy-transcripts para Windows (PowerShell).
# Crea un entorno aislado con el paquete, Playwright y Chromium, y el comando global `udemy`.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1                 instala (o actualiza)
#   ... -WithAI          ademas instala el SDK de Anthropic (para --study api; Python 3.10+)
#   ... -SkipBrowser     no descarga Chromium (ya lo tienes o lo haras luego)
#   ... -DesktopShortcut ademas del acceso del Menu Inicio, crea uno en el Escritorio
#   ... -Uninstall       borra el entorno y el comando (no toca tus descargas ni tu sesion)
#   ... -AppDir RUTA -BinDir RUTA   cambia donde se instala (default %LOCALAPPDATA%\udemy-transcripts
#                                   y %LOCALAPPDATA%\Microsoft\WindowsApps)
param(
    [string]$AppDir,
    [string]$BinDir,
    [switch]$WithAI,
    [switch]$SkipBrowser,
    [switch]$DesktopShortcut,
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"

if (-not $AppDir) { $AppDir = Join-Path $env:LOCALAPPDATA "udemy-transcripts" }
if (-not $BinDir) {
    $BinDir = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"   # ya suele estar en el PATH
    if (-not (Test-Path $BinDir)) { $BinDir = $AppDir }
}
$Venv   = Join-Path $AppDir "venv"
$SrcDir = $PSScriptRoot
$venvPy = Join-Path $Venv "Scripts\python.exe"

function Invoke-Checked {
    # Ejecuta un comando nativo y falla si termina con error (PowerShell no lo hace solo).
    param([string]$What, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Fallo al $What (codigo $LASTEXITCODE)." }
}

$StartMenuLink = Join-Path ([Environment]::GetFolderPath("Programs")) "Udemy Transcripts.lnk"
$DesktopLink   = Join-Path ([Environment]::GetFolderPath("Desktop")) "Udemy Transcripts.lnk"

function New-MenuShortcut {
    # Acceso directo que abre PowerShell directamente en el menu interactivo.
    param([string]$Path, [string]$Exe)
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($Path)
    $link.TargetPath = "powershell.exe"
    $link.Arguments = "-NoLogo -ExecutionPolicy Bypass -Command `"[Console]::OutputEncoding=[Text.Encoding]::UTF8; & '$Exe' --menu`""
    $link.WorkingDirectory = $env:USERPROFILE
    $link.Description = "Menu interactivo de udemy-transcripts"
    $link.Save()
}

if ($Uninstall) {
    Remove-Item $AppDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $BinDir "udemy.cmd") -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $BinDir "udemy-menu.cmd") -Force -ErrorAction SilentlyContinue
    Remove-Item $StartMenuLink, $DesktopLink -Force -ErrorAction SilentlyContinue
    Write-Host "udemy-transcripts desinstalado." -ForegroundColor Green
    Write-Host "Se conservan tus descargas (~\Udemy-Transcripts) y tu sesion de Udemy"
    Write-Host "(~\.cache\udemy-transcripts-profile): borralos a mano si ya no los quieres."
    exit 0
}

Write-Host "Instalando udemy-transcripts..." -ForegroundColor Cyan

# 1) Python: el primero de python / py -3 / python3 que sea 3.8+ (3.10+ con -WithAI)
$minMinor = 8
if ($WithAI) { $minMinor = 10 }
$pyCmd = $null
foreach ($candidate in @(@("python"), @("py", "-3"), @("python3"))) {
    try {
        $exe = $candidate[0]
        $extra = @($candidate | Select-Object -Skip 1)
        $out = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -match '^3\.(\d+)$' -and [int]$Matches[1] -ge $minMinor) {
            $pyCmd = $candidate
            Write-Host "  - Python: $out"
            break
        }
    } catch { }    # el alias de la Microsoft Store o un comando inexistente
}
if (-not $pyCmd) {
    Write-Host "Necesitas Python 3.$minMinor o superior. Descargalo de https://www.python.org/downloads/ " -ForegroundColor Red
    Write-Host "(marca 'Add Python to PATH' durante la instalacion)."
    if ($WithAI) { Write-Host "(-WithAI requiere 3.10+; sin el basta con 3.8)" }
    exit 1
}

# 2) entorno aislado + paquete (instala tambien Playwright)
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
Remove-Item (Join-Path $AppDir "udemy_transcripts.py") -Force -ErrorAction SilentlyContinue  # script suelto de versiones anteriores

Write-Host "  - Creando entorno virtual..."
$pyExe = $pyCmd[0]
$pyExtra = @($pyCmd | Select-Object -Skip 1)
Invoke-Checked "crear el entorno virtual" { & $pyExe @pyExtra -m venv $Venv }
Invoke-Checked "actualizar pip" { & $venvPy -m pip install --quiet --upgrade pip }
$target = $SrcDir
if ($WithAI) { $target = "${SrcDir}[ai]" }
Write-Host "  - Instalando udemy-transcripts y Playwright..."
try {
    Invoke-Checked "instalar el paquete" { & $venvPy -m pip install --quiet --upgrade $target }
} catch {
    Write-Host "Si el error habla de rutas largas, usa una carpeta corta: -AppDir C:\udemy" -ForegroundColor Yellow
    throw
}
if ($SkipBrowser) {
    Write-Host "  - Chromium: omitido (-SkipBrowser). Instalalo con: $venvPy -m playwright install chromium"
} else {
    Write-Host "  - Descargando Chromium (~170 MB, puede tardar)..."
    Invoke-Checked "descargar Chromium" { & $venvPy -m playwright install chromium }
}

# 3) comando global `udemy` (udemy.cmd en una carpeta del PATH del usuario)
$udemyExe = Join-Path $Venv "Scripts\udemy.exe"
$cmd = "@echo off`r`n`"$udemyExe`" %*"
Set-Content -Path (Join-Path $BinDir "udemy.cmd") -Value $cmd -Encoding ascii
$menuCmd = "@echo off`r`n`"$udemyExe`" --menu"
Set-Content -Path (Join-Path $BinDir "udemy-menu.cmd") -Value $menuCmd -Encoding ascii

# acceso directo "Udemy Transcripts" (Menu Inicio y, si se pide, Escritorio) que abre el menu
try {
    New-MenuShortcut -Path $StartMenuLink -Exe $udemyExe
    Write-Host "  - Acceso directo: Menu Inicio > Udemy Transcripts"
    if ($DesktopShortcut) { New-MenuShortcut -Path $DesktopLink -Exe $udemyExe }
} catch {
    Write-Host "  - No pude crear el acceso directo ($($_.Exception.Message)); usa el comando udemy-menu." -ForegroundColor Yellow
}

$version = & $udemyExe --version
Write-Host ""
Write-Host "Listo! $version -> comando: udemy" -ForegroundColor Green
$onPath = ($env:PATH -split ";") -contains $BinDir
if (-not $onPath) {
    Write-Host "Anade esta carpeta a tu PATH: $BinDir" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Uso:"
Write-Host "    udemy                 (abre el menu interactivo; tambien: udemy-menu)"
Write-Host "    udemy --list"
Write-Host "    udemy `"https://www.udemy.com/course/...`""
Write-Host "    udemy --merge `"https://www.udemy.com/course/...`"   (ademas, un .md con todo el curso)"
Write-Host "    udemy --resources --update `"https://www.udemy.com/course/...`""
Write-Host "    udemy --help          (todas las opciones)"
