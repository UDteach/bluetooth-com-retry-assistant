param(
    [string]$PortName = ""
)

$ErrorActionPreference = "Stop"

$ports = Get-CimInstance Win32_SerialPort |
    Select-Object DeviceID, Name, PNPDeviceID |
    Sort-Object DeviceID

if ($PortName) {
    $match = $ports | Where-Object { $_.DeviceID -ieq $PortName }
    if (-not $match) {
        Write-Host "FAIL: $PortName was not found in Win32_SerialPort."
        Write-Host "Visible COM ports:"
        $ports | Format-Table -AutoSize
        exit 1
    }

    Write-Host "OK: $PortName is visible to Windows."
    $match | Format-List
    exit 0
}

if (-not $ports) {
    Write-Host "No COM ports were reported by Win32_SerialPort."
    exit 0
}

$ports | Format-Table -AutoSize
