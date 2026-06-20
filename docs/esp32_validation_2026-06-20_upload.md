# ESP32 upload validation - 2026-06-20

This note records the Arduino CLI upload and Windows Bluetooth/COM validation
performed on 2026-06-20.

## Environment

- Windows PowerShell: `5.1.26100.8655`
- Arduino CLI: `1.5.1`
- ESP32 Arduino core: `esp32:esp32 3.3.10`
- FQBN: `esp32:esp32:esp32`
- Arduino CLI root: `C:\ba_arduino`
- Upload work root: `C:\ba_esp32_upload`
- USB serial ports:
  - `COM3`: `USB-SERIAL CH340`, location `1-1.2`
  - `COM4`: `USB-SERIAL CH340`, location `1-1.3`
  - `COM5`: `USB-SERIAL CH340`, location `1-1.1`

PowerShell compatibility note:

- The validation was run on Windows PowerShell 5.1.
- Scripts are written to avoid PowerShell 7-only behavior.
- `setup_esp32_arduino_cli.ps1` forces TLS 1.2 on Windows PowerShell Desktop
  and uses `System.Net.WebClient` for downloads to avoid old
  `Invoke-WebRequest` parsing differences.

## Upload mapping

```powershell
.\scripts\upload_esp32_sketches.ps1
```

Default mapping:

| USB port | Sketch | Bluetooth name |
| --- | --- | --- |
| `COM3` | `hardware\esp32_spp_mock` | `BT-COM-MOCK-A` |
| `COM4` | `hardware\esp32_spp_mock` | `BT-COM-MOCK-B` |
| `COM5` | `hardware\esp32_no_com_mock` | `BT-NO-COM-MOCK` |

`esp32_spp_mock` supports compile-time name override with
`BT_DEVICE_NAME`, so the same SPP sketch can produce `A` and `B` devices.

## Boot log check

After upload, serial boot logs confirmed:

- `COM3`: `Bluetooth SPP mock started as BT-COM-MOCK-A`
- `COM4`: `Bluetooth SPP mock started as BT-COM-MOCK-B`
- `COM5`: `Bluetooth no-COM mock started as BT-NO-COM-MOCK`

The no-COM Classic sketches require
`esp32-hal-alloc-bt-classic-mem.h` and `btStartMode(BT_MODE_CLASSIC_BT)`.
Without this, ESP32 Arduino core 3.3.10 can release Classic Bluetooth memory
before `btStart()` and the runtime log becomes `Bluetooth controller start
failed`.

## Windows scan result

After flashing the default three-board mapping, Windows Bluetooth discovery
found all three:

| Device | Address | SPP UUID | Initial Windows state |
| --- | --- | --- | --- |
| `BT-COM-MOCK-A` | `B4:BF:E9:D4:51:FA` | yes | remembered after pairing |
| `BT-COM-MOCK-B` | `70:4B:CA:7C:B1:76` | yes | remembered after pairing |
| `BT-NO-COM-MOCK` | `30:76:F5:B0:31:4E` | no | visible, not remembered |

## Three-board pairing sequence

```powershell
.\scripts\run_esp32_sequence_test.ps1 `
  -ResetPairing `
  -ComWaitSeconds 45 `
  -PollSeconds 3 `
  -PairAttempts 1 `
  -OutputDirectory .\.codex\hardware `
  -IUnderstandThisChangesBluetoothPairing
```

Observed result:

| Target | Expected COM | Result | Detail |
| --- | --- | --- | --- |
| `BT-COM-MOCK-A` | yes | pass | `COM6` detected |
| `BT-COM-MOCK-B` | yes | pass | `COM7` detected |
| `BT-NO-COM-MOCK` | no | pass | no matching COM detected |

The Bluetooth COM ports were matched by MAC fragments in PnP/WMI text:

- `COM6`: `...&B4BFE9D451FA_C00000000`
- `COM7`: `...&704BCA7CB176_C00000000`

## Additional profile simulations

`COM5` was also reflashed temporarily for profile checks:

| Sketch | Bluetooth name | Windows/app-facing result |
| --- | --- | --- |
| `hardware\esp32_classic_dfu_hint_mock` | `BT-DFU-NO-COM-MOCK` | visible in Classic scan, no COM detected |
| `hardware\esp32_ble_dfu_mock` | `BT-BLE-DFU-MOCK` | ESP32 boot log confirmed BLE advertising of `0000FE59-0000-1000-8000-00805F9B34FB`; current Classic COM-focused backend did not list it, and no COM was created |

PowerShell 5.1 could load the WinRT BLE advertisement type, but
`Register-ObjectEvent` cannot subscribe to Windows Runtime events in this
environment. BLE advertisement verification therefore remains ESP32 boot-log
based unless a dedicated BLE watcher is added.

## Final hardware state

After the profile checks, `COM5` was restored to `BT-NO-COM-MOCK` and the
three-board sequence was run again successfully.
