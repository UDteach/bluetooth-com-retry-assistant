param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string[]]$ComTargets = @("BT-COM-MOCK-A", "BT-COM-MOCK-B"),
    [string[]]$NoComTargets = @("BT-NO-COM-MOCK"),
    [int]$ComWaitSeconds = 45,
    [int]$PollSeconds = 3,
    [int]$PairAttempts = 1,
    [string]$OutputDirectory = ".",
    [switch]$ResetPairing,
    [switch]$IUnderstandThisChangesBluetoothPairing
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if (-not $IUnderstandThisChangesBluetoothPairing) {
    throw "This test unpairs/pairs Bluetooth devices. Re-run with -IUnderstandThisChangesBluetoothPairing."
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

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$OutputDirectory = (Resolve-Path $OutputDirectory).Path
$targets = @()
foreach ($target in $ComTargets) {
    $targets += [pscustomobject]@{ Name = $target; ExpectedCom = $true }
}
foreach ($target in $NoComTargets) {
    $targets += [pscustomobject]@{ Name = $target; ExpectedCom = $false }
}

if (-not $targets) {
    throw "Specify at least one target."
}

if ($ResetPairing) {
    $resetCode = @'
import json
import sys

from bluetooth_assistant.windows_bluetooth import WindowsBluetoothBackend

backend = WindowsBluetoothBackend()
devices = backend.list_devices(issue_inquiry=True)
for target_name in sys.argv[1:]:
    matches = [
        device
        for device in devices
        if target_name.casefold() in (device.name or '').casefold()
    ]
    if len(matches) != 1:
        print(json.dumps({"target": target_name, "ok": False, "detail": f"matches={len(matches)}"}))
        continue
    result = backend.unpair(matches[0].address)
    print(json.dumps({"target": target_name, "ok": result.ok, "detail": result.message}))
'@
    Write-Host "Resetting Windows Bluetooth pairing for sequence targets..."
    $targetNames = @($targets | ForEach-Object { $_.Name })
    $resetCode | & $Python - @targetNames
    if ($LASTEXITCODE -ne 0) {
        throw "ResetPairing failed."
    }
}

$summary = @()
foreach ($target in $targets) {
    $safeName = ($target.Name -replace "[^A-Za-z0-9._-]", "_").ToLowerInvariant()
    $outputPath = Join-Path $OutputDirectory "esp32-sequence-$safeName.json"
    Write-Host "Running sequence target: $($target.Name)"

    $argsList = @(
        "-m", "bluetooth_assistant.diagnostics",
        "--json",
        "--hardware-pairing-test",
        "--target-name", $target.Name,
        "--com-wait-seconds", $ComWaitSeconds,
        "--poll-seconds", $PollSeconds,
        "--pair-attempts", $PairAttempts
    )

    $output = & $Python @argsList
    $exitCode = $LASTEXITCODE
    $output | Set-Content -Encoding UTF8 -Path $outputPath
    $json = $output | ConvertFrom-Json
    $outcome = $json | Where-Object { $_.name -eq "hardware_pairing_outcome" } | Select-Object -First 1
    $comAfter = $json | Where-Object { $_.name -eq "hardware_pairing_com_after" } | Select-Object -First 1
    $actualCom = [bool]($comAfter -and $comAfter.ok)
    $expectedCom = [bool]$target.ExpectedCom
    $pass = $actualCom -eq $expectedCom

    $summary += [pscustomobject]@{
        target = $target.Name
        expected_com = $expectedCom
        exit_code = $exitCode
        outcome_ok = if ($outcome) { [bool]$outcome.ok } else { $false }
        com_ok = $actualCom
        expected_result = if ($pass) { "PASS" } else { "FAIL" }
        detail = if ($outcome) { $outcome.detail } else { "missing hardware_pairing_outcome" }
        output = $outputPath
    }
}

$summaryPath = Join-Path $OutputDirectory "esp32-sequence-summary.json"
$summary | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $summaryPath
$summary | Format-Table -AutoSize
Write-Host "Saved summary: $summaryPath"

if ($summary | Where-Object { $_.expected_result -eq "FAIL" }) {
    exit 1
}
exit 0
