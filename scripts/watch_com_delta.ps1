param(
    [int]$WaitSeconds = 60,
    [int]$PollSeconds = 2,
    [switch]$ExpectNew,
    [switch]$ExpectNoNew,
    [string]$OutputPath = ".\com-delta.json"
)

$ErrorActionPreference = "Stop"

if ($ExpectNew -and $ExpectNoNew) {
    throw "Use either -ExpectNew or -ExpectNoNew, not both."
}

function Get-ComPorts {
    Get-CimInstance Win32_SerialPort |
        Select-Object DeviceID, Name, PNPDeviceID |
        Sort-Object DeviceID
}

$baseline = @(Get-ComPorts)
$baselineIds = @{}
foreach ($port in $baseline) {
    $baselineIds[$port.DeviceID.ToUpperInvariant()] = $true
}

Write-Host "Baseline COM ports:"
if ($baseline.Count -eq 0) {
    Write-Host "(none)"
} else {
    $baseline | Format-Table -AutoSize
}

Write-Host ""
Write-Host "Now pair or remove the Bluetooth device. Watching for $WaitSeconds seconds..."

$started = Get-Date
$newPorts = @()
while (((Get-Date) - $started).TotalSeconds -lt $WaitSeconds) {
    Start-Sleep -Seconds $PollSeconds
    $current = @(Get-ComPorts)
    $newPorts = @(
        $current | Where-Object {
            -not $baselineIds.ContainsKey($_.DeviceID.ToUpperInvariant())
        }
    )
    if ($ExpectNew -and $newPorts.Count -gt 0) {
        break
    }
}

$result = [ordered]@{
    ok = $true
    wait_seconds = $WaitSeconds
    poll_seconds = $PollSeconds
    baseline = $baseline
    new_ports = $newPorts
}

if ($ExpectNew -and $newPorts.Count -eq 0) {
    $result.ok = $false
    $result.reason = "Expected a new COM port, but none appeared."
}

if ($ExpectNoNew -and $newPorts.Count -gt 0) {
    $result.ok = $false
    $result.reason = "Expected no new COM port, but one or more appeared."
}

$json = $result | ConvertTo-Json -Depth 6
$json | Set-Content -Encoding UTF8 -Path $OutputPath
$json

if (-not $result.ok) {
    exit 1
}
