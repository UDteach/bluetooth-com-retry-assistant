param(
    [string]$ArduinoCli = "C:\ba_arduino\bin\arduino-cli.exe",
    [string]$ConfigFile = "C:\ba_arduino\arduino-cli.yaml",
    [string]$Fqbn = "esp32:esp32:esp32",
    [string]$WorkRoot = "C:\ba_esp32_compile",
    [string]$LogDirectory = ".\.codex\arduino-cli\compile-logs",
    [string[]]$Sketches = @(
        "hardware\esp32_spp_mock",
        "hardware\esp32_no_com_mock",
        "hardware\esp32_classic_dfu_hint_mock",
        "hardware\esp32_ble_dfu_mock"
    )
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Get-FullPath([string]$Path) {
    return [System.IO.Path]::GetFullPath($Path)
}

function Assert-ChildPath([string]$Parent, [string]$Child) {
    $parentFull = Get-FullPath $Parent
    $childFull = Get-FullPath $Child
    if (-not $childFull.StartsWith($parentFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside $parentFull`: $childFull"
    }
}

function Clear-ChildDirectory([string]$Parent, [string]$Child) {
    Assert-ChildPath $Parent $Child
    if (Test-Path $Child) {
        Remove-Item -LiteralPath $Child -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Child | Out-Null
}

if (-not (Test-Path $ArduinoCli)) {
    throw "arduino-cli.exe was not found: $ArduinoCli. Run scripts\setup_esp32_arduino_cli.ps1 first."
}
if (-not (Test-Path $ConfigFile)) {
    throw "Arduino CLI config was not found: $ConfigFile. Run scripts\setup_esp32_arduino_cli.ps1 first."
}

$workRootFull = Get-FullPath $WorkRoot
$sourceRoot = Join-Path $workRootFull "sketches"
$buildRoot = Join-Path $workRootFull "builds"

New-Item -ItemType Directory -Force -Path $sourceRoot, $buildRoot, $LogDirectory | Out-Null

$summary = @()
foreach ($sketch in $Sketches) {
    if (-not (Test-Path $sketch)) {
        throw "Sketch directory was not found: $sketch"
    }

    $name = Split-Path $sketch -Leaf
    $sourceCopy = Join-Path $sourceRoot $name
    $buildPath = Join-Path $buildRoot $name
    $logPath = Join-Path $LogDirectory "$name.log"

    Clear-ChildDirectory $sourceRoot $sourceCopy
    Clear-ChildDirectory $buildRoot $buildPath
    Copy-Item -Path (Join-Path $sketch "*") -Destination $sourceCopy -Recurse -Force

    Write-Host "Compiling $name..."
    & $ArduinoCli --config-file $ConfigFile compile --fqbn $Fqbn --build-path $buildPath $sourceCopy *> $logPath
    $exitCode = $LASTEXITCODE

    $summary += [pscustomobject]@{
        sketch = $name
        exit_code = $exitCode
        log = (Resolve-Path $logPath).Path
    }

    if ($exitCode -ne 0) {
        Write-Host "Compile failed for $name. Tail of log:"
        Get-Content $logPath -Tail 120
    }
}

$summary | Format-Table -AutoSize
if ($summary | Where-Object { $_.exit_code -ne 0 }) {
    exit 1
}

Write-Host "All ESP32 sketches compiled successfully."
