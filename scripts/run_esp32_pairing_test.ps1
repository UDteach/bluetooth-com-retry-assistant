param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$TargetName = "BT-COM-MOCK",
    [string]$TargetAddress = "",
    [string]$PairPin = "",
    [int]$ComWaitSeconds = 60,
    [int]$PollSeconds = 3,
    [int]$PairAttempts = 1,
    [string]$OutputPath = ".\esp32-pairing-test.json",
    [switch]$IUnderstandThisChangesBluetoothPairing
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if (-not $IUnderstandThisChangesBluetoothPairing) {
    throw "This test unpairs/pairs a Bluetooth device. Re-run with -IUnderstandThisChangesBluetoothPairing."
}

if (-not $TargetName -and -not $TargetAddress) {
    throw "Specify -TargetName or -TargetAddress."
}

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
    "--hardware-pairing-test",
    "--com-wait-seconds", $ComWaitSeconds,
    "--poll-seconds", $PollSeconds,
    "--pair-attempts", $PairAttempts
)

if ($TargetAddress) {
    $argsList += @("--target-address", $TargetAddress)
} else {
    $argsList += @("--target-name", $TargetName)
}

if ($PairPin) {
    $argsList += @("--pair-pin", $PairPin)
}

Write-Host "Running ESP32 pairing test. This changes Windows Bluetooth pairing state."
if ($TargetAddress) { Write-Host "TargetAddress: $TargetAddress" }
if ($TargetName) { Write-Host "TargetName: $TargetName" }
if ($PairPin) { Write-Host "PairPin: <provided>" }
if (-not $PairPin) { Write-Host "PairPin: not used. Approve any Windows pairing prompt if it appears." }

$output = & $Python @argsList
$exitCode = $LASTEXITCODE
$output | Set-Content -Encoding UTF8 -Path $OutputPath
$output

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "Pairing test failed. Common fixes:"
    Write-Host "- Confirm the ESP32 SPP sketch is running as BT-COM-MOCK."
    Write-Host "- If multiple devices match the name, re-run with -TargetAddress."
    Write-Host "- Watch for Windows pairing prompts and approve them."
    Write-Host "- Error 1244 usually means Windows required user authentication; pair from the app or Windows Settings while watching COM changes."
    Write-Host "- Use -PairPin only for legacy devices that explicitly require a PIN."
    Write-Host "- Remove stale BT-COM-MOCK pairing from Windows settings and retry."
    Write-Host "- If no COM appears, verify this is ESP32-WROOM/DevKitC, not S3/C3/C6/S2."
    exit $exitCode
}

Write-Host "Pairing test passed. Saved JSON: $OutputPath"
