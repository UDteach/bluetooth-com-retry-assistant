# ESP32 Profile Simulation

This project can simulate the Bluetooth profile cases that matter for
BluetoothAssistant's COM-port responsibility. It cannot perfectly impersonate an
arbitrary commercial smart meter, but it can reproduce the Windows-visible
signals that decide whether this app should keep waiting for a COM port.

## What Can Be Simulated

| Case | Sketch | Windows Bluetooth list | COM port | Purpose |
| --- | --- | --- | --- | --- |
| Classic SPP / COM | `hardware/esp32_spp_mock/esp32_spp_mock.ino` | visible | expected | Positive case. Windows should create a Bluetooth serial COM port. |
| Classic visible / no COM | `hardware/esp32_no_com_mock/esp32_no_com_mock.ino` | visible | not expected | Negative case. The device can be seen but does not expose SPP. |
| Classic DFU-looking / no COM | `hardware/esp32_classic_dfu_hint_mock/esp32_classic_dfu_hint_mock.ino` | visible | not expected | App-facing hint case. The name looks firmware/DFU-related but no COM should appear. |
| BLE DFU-shaped | `hardware/esp32_ble_dfu_mock/esp32_ble_dfu_mock.ino` | depends on Windows BLE UI/tooling | not expected | BLE GATT case. Advertises Nordic Secure DFU-like UUIDs but does not create COM. |

## What Cannot Be Fully Simulated

- A real vendor smart meter firmware update protocol.
- A real signed DFU image transfer, validation, rollback, or recovery flow.
- A Windows COM port from BLE-only GATT. BLE GATT services are not Classic
  Bluetooth SPP/RFCOMM serial ports.
- Bypassing Windows user consent. Windows may still show an "Add a device"
  consent prompt even when no PIN is required.

## Recommended Test Setup

Use three boards when available:

1. Flash `esp32_spp_mock` as `BT-COM-MOCK-A` or `BT-COM-MOCK-B`.
2. Flash `esp32_no_com_mock` as `BT-NO-COM-MOCK`.
3. Flash either `esp32_classic_dfu_hint_mock` or `esp32_ble_dfu_mock`.

If only one spare board is available, reflash it per scenario.

## Local Compile Setup

The ESP32 Arduino toolchain can fail when the project path contains Japanese
characters. Use an ASCII-only install and work directory:

```powershell
.\scripts\setup_esp32_arduino_cli.ps1
.\scripts\compile_esp32_sketches.ps1
.\scripts\upload_esp32_sketches.ps1
```

Current verified local setup:

- Arduino CLI: `1.5.1`
- ESP32 Arduino core: `esp32:esp32 3.3.10`
- CLI/config root: `C:\ba_arduino`
- temporary compile root: `C:\ba_esp32_compile`
- board target: `esp32:esp32:esp32`
- upload root: `C:\ba_esp32_upload`
- PowerShell verified on this PC: Windows PowerShell `5.1.26100.8655`

The setup script downloads Arduino CLI from the official GitHub release,
verifies the published SHA-256 checksum, configures Espressif's board manager
URL, and installs the ESP32 core. The compile script copies sketches to an
ASCII-only temporary folder before invoking `arduino-cli compile`.
The upload script uses the same ASCII-only approach and defaults to
`COM3=BT-COM-MOCK-A`, `COM4=BT-COM-MOCK-B`, and `COM5=BT-NO-COM-MOCK`.

## Expected BluetoothAssistant Behavior

- `BT-COM-MOCK-*`: should eventually become `COMあり` / `SPP/COM`.
- `BT-NO-COM-MOCK`: should stay low-score and never complete as COM connected.
- `BT-DFU-NO-COM-MOCK`: should look firmware/DFU-related but should not complete
  unless Windows actually creates a matching COM port.
- `BT-BLE-DFU-MOCK`: should not be treated as a COM success. It may be visible in
  Windows BLE tools, but this app's completion condition remains a Windows COM
  port tied to the target device.

## Reference Basis

- Espressif's Arduino Bluetooth example uses Classic Bluetooth SPP and notes
  `CONFIG_BT_SPP_ENABLED` is available for ESP32 chips.
- Espressif's ESP-IDF SPP API describes SPP as serial communication over a
  virtual serial link.
- Espressif's Arduino BLE example creates a BLE server, service,
  characteristics, and advertising. That is the model used by the BLE DFU-shaped
  sketch.
- Espressif's ESP32-S3 BLE documentation states ESP32-S3 Bluetooth hosts support
  Bluetooth LE only and Classic Bluetooth is not supported.
