param(
    [string]$ArduinoCli = "C:\ba_arduino\bin\arduino-cli.exe",
    [string]$ConfigFile = "C:\ba_arduino\arduino-cli.yaml",
    [string]$Fqbn = "esp32:esp32:esp32",
    [string]$WorkRoot = "C:\ba_esp32_upload",
    [string]$LogDirectory = ".\.codex\arduino-cli\upload-logs",
    [object[]]$Targets = @(
        @{ Port = "COM3"; Sketch = "hardware\esp32_spp_mock"; DeviceName = "BT-COM-MOCK-A" },
        @{ Port = "COM4"; Sketch = "hardware\esp32_spp_mock"; DeviceName = "BT-COM-MOCK-B" },
        @{ Port = "COM5"; Sketch = "hardware\esp32_no_com_mock"; DeviceName = "" }
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
foreach ($target in $Targets) {
    $port = [string]$target.Port
    $sketch = [string]$target.Sketch
    $deviceName = [string]$target.DeviceName

    if (-not $port) {
        throw "Target port is empty."
    }
    if (-not (Test-Path $sketch)) {
        throw "Sketch directory was not found: $sketch"
    }

    $sketchName = Split-Path $sketch -Leaf
    $copyName = if ($deviceName) { "$sketchName-$deviceName" } else { "$sketchName-$port" }
    $copyName = $copyName -replace "[^A-Za-z0-9._-]", "_"
    $sourceCopy = Join-Path $sourceRoot $copyName
    $buildPath = Join-Path $buildRoot $copyName
    $logPath = Join-Path $LogDirectory "$copyName.log"

    Clear-ChildDirectory $sourceRoot $sourceCopy
    Clear-ChildDirectory $buildRoot $buildPath
    Copy-Item -Path (Join-Path $sketch "*") -Destination $sourceCopy -Recurse -Force
    $mainSketch = Join-Path $sourceCopy "$sketchName.ino"
    if ($copyName -ne $sketchName) {
        if (-not (Test-Path $mainSketch)) {
            throw "Main sketch file was not found after copy: $mainSketch"
        }
        Rename-Item -LiteralPath $mainSketch -NewName "$copyName.ino"
    }

    $arguments = @(
        "--config-file", $ConfigFile,
        "compile",
        "--fqbn", $Fqbn,
        "--build-path", $buildPath,
        "--upload",
        "--port", $port
    )

    if ($deviceName) {
        $deviceDefine = 'compiler.cpp.extra_flags=-DBT_DEVICE_NAME=\"' + $deviceName + '\"'
        $arguments += @("--build-property", $deviceDefine)
    }
    $arguments += @($sourceCopy)

    Write-Host "Uploading $sketchName to $port..."
    if ($deviceName) {
        Write-Host "  Bluetooth name: $deviceName"
    }

    & $ArduinoCli @arguments *> $logPath
    $exitCode = $LASTEXITCODE

    $summary += [pscustomobject]@{
        port = $port
        sketch = $sketchName
        device_name = $deviceName
        exit_code = $exitCode
        log = (Resolve-Path $logPath).Path
    }

    if ($exitCode -ne 0) {
        Write-Host "Upload failed for $sketchName on $port. Tail of log:"
        Get-Content $logPath -Tail 160
        break
    }

    Start-Sleep -Seconds 3
}

$summary | Format-Table -AutoSize
if ($summary | Where-Object { $_.exit_code -ne 0 }) {
    exit 1
}

Write-Host "All ESP32 uploads completed successfully."
