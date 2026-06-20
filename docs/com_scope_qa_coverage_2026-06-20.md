# COM Scope QA Coverage - 2026-06-20

This report records the validation pass for the COM-only responsibility of
BluetoothAssistant. The app is responsible for pairing/re-pairing Windows
Bluetooth devices until a matching COM port appears. BLE GATT, DFU, OTA, and
firmware transfer are intentionally outside the app's completion criteria.

## Source-backed scope check

- Microsoft documents `BluetoothSetServiceState` as enabling/disabling a
  Bluetooth service and installing/removing the corresponding supported driver.
  This supports the app's SPP service-enable step for COM creation.
- Microsoft documents `BluetoothRemoveDevice` as removing authentication and
  clearing cached service information. This supports retrying by unpairing first.
- Microsoft documents `BluetoothEnumerateInstalledServices` as returning enabled
  service GUIDs for a Bluetooth device. This supports the profile hint column.
- Bluetooth SIG Serial Port Profile defines emulated serial cable connections
  using RFCOMM. This is the profile aligned with Windows COM-port completion.
- Microsoft GATT/RFCOMM app docs and Nordic DFU docs describe service,
  characteristic, socket, notify, and write flows. Those are not equivalent to a
  Windows COM port and remain outside this app's "connected" state.
- pySerial documents that port listing metadata and ordering can vary. The app
  therefore combines Windows PnP/WMI-derived COM data with pySerial fallback.

## Local validation

- `ruff check .`: passed.
- `pycodestyle bluetooth_assistant tests bluetooth_assistant_launcher.py`: passed.
- `python -m unittest discover -s tests -p "test_*.py" -v`: passed, 83 tests
  before version-sync coverage and 84 tests after adding it.
- `python -m compileall -q bluetooth_assistant tests bluetooth_assistant_launcher.py`:
  passed.
- Safe diagnostics: passed with Python 3.14.2, Tk 8.6, pySerial 3.5, Windows
  Bluetooth backend loaded, and COM3/COM4/COM5/COM6/COM7 visible.
- Mock retry diagnostics: passed. The mock backend unpaired and paired twice,
  enabled the Serial Port service twice, then detected COM12.

## ESP32 validation

Three ESP32 USB serial ports were visible as CH340 devices:

- COM3
- COM4
- COM5

Bluetooth sequence validation was run with pairing reset enabled:

| Target | Expected COM | Result | Detail |
| --- | --- | --- | --- |
| BT-COM-MOCK-A | yes | PASS | COM6 detected |
| BT-COM-MOCK-B | yes | PASS | COM7 detected |
| BT-NO-COM-MOCK | no | PASS | no target COM found after max attempts |

After the active sequence test, the read-only hardware check still showed:

- BT-COM-MOCK-A remembered with SPP UUID `00001101-0000-1000-8000-00805F9B34FB`
  and COM6.
- BT-COM-MOCK-B remembered with SPP UUID `00001101-0000-1000-8000-00805F9B34FB`
  and COM7.
- BT-NO-COM-MOCK visible but not remembered and without a matching COM port.
- S1TW_SPP visible as a high COM candidate based on its name.

## Exe validation

- `scripts/build_exe.ps1`: passed locally with PyInstaller 6.21.0.
- `dist/BluetoothAssistant.exe --help`: exited 0.
- `dist/BluetoothAssistant.exe --mock --no-auto-scan`: process launched and was
  stopped after smoke verification.
- `dist/BluetoothAssistant.exe --no-auto-scan`: process launched and was stopped
  after smoke verification.

## CI and release validation

GitHub Actions for commit `1334630e7bda8763fe56636386c890bd92c82c29` passed on:

- `main` CI.
- `v0.12.1` CI.
- `v0.12.1` Release workflow.

The release workflow validates lint, PEP 8, unit tests, compileall, mock retry,
Windows exe build, and exe help smoke before publishing.

## Remaining boundaries

- No production smart meter was available, so actual vendor firmware tooling was
  not exercised.
- The app verifies Windows COM-port creation, not downstream firmware transfer.
- Windows may still require user consent through the OS "Add a device" prompt.
  The app can handle no-PIN SSP callbacks when Windows supplies them, but it
  cannot bypass OS-level consent.
- BLE GATT/DFU devices that never create a Windows COM port are intentionally
  not marked complete by this app.

## References

- Microsoft: `BluetoothSetServiceState`
  https://learn.microsoft.com/en-us/windows/win32/api/bluetoothapis/nf-bluetoothapis-bluetoothsetservicestate
- Microsoft: `BluetoothRemoveDevice`
  https://learn.microsoft.com/en-us/windows/win32/api/bluetoothapis/nf-bluetoothapis-bluetoothremovedevice
- Microsoft: `BluetoothEnumerateInstalledServices`
  https://learn.microsoft.com/en-us/windows/win32/api/bluetoothapis/nf-bluetoothapis-bluetoothenumerateinstalledservices
- Microsoft: `Win32_SerialPort`
  https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-serialport
- Microsoft: Bluetooth GATT Client
  https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/gatt-client
- Microsoft: Bluetooth RFCOMM
  https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/send-or-receive-files-with-rfcomm
- Bluetooth SIG: Serial Port Profile 1.2
  https://www.bluetooth.com/specifications/specs/serial-port-profile-1-2/
- pySerial: `serial.tools.list_ports`
  https://pyserial.readthedocs.io/en/latest/tools.html
- Nordic Thingy: Secure DFU service
  https://nordicsemiconductor.github.io/Nordic-Thingy52-FW/documentation/firmware_architecture.html
