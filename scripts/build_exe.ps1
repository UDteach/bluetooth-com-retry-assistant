param(
    [string]$Name = "BluetoothAssistant",
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if (-not (Test-Path $Python)) {
    $pythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python not found: $Python. Create a venv and install requirements-dev.txt first."
    }
    $Python = $pythonCommand.Source
} else {
    $Python = (Resolve-Path $Python).Path
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name $Name `
    --collect-submodules serial `
    bluetooth_assistant_launcher.py

$exe = Join-Path $root "dist\$Name.exe"
if (-not (Test-Path $exe)) {
    throw "Build finished without expected exe: $exe"
}

Get-Item $exe | Select-Object FullName, Length, LastWriteTime
