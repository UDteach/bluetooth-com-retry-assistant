param(
    [string]$InstallRoot = "C:\ba_arduino",
    [string]$Esp32Core = "esp32:esp32",
    [switch]$SkipCoreInstall
)

$ErrorActionPreference = "Stop"

function Enable-ModernTls {
    if ($PSVersionTable.PSEdition -eq "Desktop") {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    }
}

function Join-NormalizedPath([string]$Base, [string]$Child) {
    return [System.IO.Path]::GetFullPath((Join-Path $Base $Child))
}

function Save-Url([string]$Url, [string]$Path) {
    $client = New-Object System.Net.WebClient
    try {
        $client.Headers["User-Agent"] = "BluetoothAssistant-setup"
        $client.DownloadFile($Url, $Path)
    }
    finally {
        $client.Dispose()
    }
}

Enable-ModernTls

$installRootFull = [System.IO.Path]::GetFullPath($InstallRoot)
$binDirectory = Join-NormalizedPath $installRootFull "bin"
$downloadDirectory = Join-NormalizedPath $installRootFull "downloads"
$dataDirectory = Join-NormalizedPath $installRootFull "data"
$userDirectory = Join-NormalizedPath $installRootFull "user"
$configFile = Join-NormalizedPath $installRootFull "arduino-cli.yaml"

New-Item -ItemType Directory -Force -Path $binDirectory, $downloadDirectory, $dataDirectory, $userDirectory | Out-Null

$release = Invoke-RestMethod `
    -Uri "https://api.github.com/repos/arduino/arduino-cli/releases/latest" `
    -Headers @{ "User-Agent" = "BluetoothAssistant-setup" }

$asset = $release.assets | Where-Object { $_.name -like "*Windows_64bit.zip" } | Select-Object -First 1
$checksums = $release.assets | Where-Object { $_.name -like "*checksums.txt" } | Select-Object -First 1

if (-not $asset) {
    throw "Arduino CLI Windows_64bit.zip asset was not found."
}
if (-not $checksums) {
    throw "Arduino CLI checksums asset was not found."
}

$zipPath = Join-NormalizedPath $downloadDirectory $asset.name
$checksumPath = Join-NormalizedPath $downloadDirectory $checksums.name

Write-Host "Downloading Arduino CLI $($release.tag_name)..."
Save-Url $asset.browser_download_url $zipPath
Save-Url $checksums.browser_download_url $checksumPath

$expectedLine = Get-Content $checksumPath | Where-Object { $_ -match [regex]::Escape($asset.name) } | Select-Object -First 1
if (-not $expectedLine) {
    throw "Checksum entry was not found for $($asset.name)."
}

$expectedHash = ($expectedLine -split "\s+")[0].ToLowerInvariant()
$actualHash = (Get-FileHash -Algorithm SHA256 $zipPath).Hash.ToLowerInvariant()
if ($expectedHash -ne $actualHash) {
    throw "Checksum mismatch for $($asset.name). Expected $expectedHash but got $actualHash."
}

Expand-Archive -LiteralPath $zipPath -DestinationPath $binDirectory -Force
$arduinoCli = Join-NormalizedPath $binDirectory "arduino-cli.exe"
if (-not (Test-Path $arduinoCli)) {
    throw "arduino-cli.exe was not found after extraction."
}

& $arduinoCli config init --dest-file $configFile --overwrite
& $arduinoCli --config-file $configFile config set directories.data ($dataDirectory -replace "\\", "/")
& $arduinoCli --config-file $configFile config set directories.downloads ($downloadDirectory -replace "\\", "/")
& $arduinoCli --config-file $configFile config set directories.user ($userDirectory -replace "\\", "/")
& $arduinoCli --config-file $configFile config set `
    board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json

& $arduinoCli --config-file $configFile core update-index
if (-not $SkipCoreInstall) {
    & $arduinoCli --config-file $configFile core install $Esp32Core
}

Write-Host "Arduino CLI ready:"
Write-Host "  CLI:    $arduinoCli"
Write-Host "  Config: $configFile"
& $arduinoCli --config-file $configFile version
& $arduinoCli --config-file $configFile core list
