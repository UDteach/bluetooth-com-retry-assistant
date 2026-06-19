param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$DeviceName = "BT-COM-MOCK",
    [string]$Address = "",
    [string]$ComPort = "",
    [int]$WaitSeconds = 60,
    [int]$PollSeconds = 3,
    [string]$OutputPath = ".\esp32-hardware-check.json"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if (-not (Test-Path $Python)) {
    $pythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python not found: $Python"
    }
    $Python = $pythonCommand.Source
} else {
    $Python = (Resolve-Path $Python).Path
}

$argsList = @(
    "-m", "bluetooth_assistant.diagnostics",
    "--json",
    "--esp32-check",
    "--expect-device-name", $DeviceName,
    "--wait-seconds", $WaitSeconds,
    "--poll-seconds", $PollSeconds
)

if ($Address) {
    $argsList += @("--expect-address", $Address)
}

if ($ComPort) {
    $argsList += @("--expect-com-port", $ComPort)
}

Write-Host "Running ESP32 hardware check..."
Write-Host "DeviceName: $DeviceName"
if ($Address) { Write-Host "Address: $Address" }
if ($ComPort) { Write-Host "ComPort: $ComPort" }

$output = & $Python @argsList
$exitCode = $LASTEXITCODE
$output | Set-Content -Encoding UTF8 -Path $OutputPath
$output

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "Hardware check failed. Common fixes:"
    Write-Host "- Confirm the ESP32 sketch is running and Serial Monitor shows BT-COM-MOCK."
    Write-Host "- Keep the ESP32 close to the PC and reset the board."
    Write-Host "- Remove old Windows Bluetooth pairing for the same device and scan again."
    Write-Host "- If COM is expected, pair BT-COM-MOCK from Windows Bluetooth settings first."
    exit $exitCode
}

Write-Host "Hardware check passed. Saved JSON: $OutputPath"
