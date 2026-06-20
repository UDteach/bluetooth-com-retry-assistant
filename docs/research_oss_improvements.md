# OSS / primary-source research notes

## Adopted

### Prefer Windows WMI/PnP COM enumeration before pySerial

pySerial's `serial.tools.list_ports` is useful and exposes `device`, `description`, and `hwid`, but its own docs note that returned strings vary by OS and that support/extended information differs by platform. There are also open pySerial issues reporting that Bluetooth COM ports can make `list_ports.comports()` block or become very slow on Windows.

Decision: on Windows, BluetoothAssistant now reads COM ports from `Win32_SerialPort` and `Win32_PnPEntity` first. pySerial remains a fallback for non-Windows and for Windows only when Windows sources return nothing.

Sources:

- https://pyserial.readthedocs.io/en/stable/tools.html
- https://github.com/pyserial/pyserial/issues/450
- https://github.com/pyserial/pyserial/issues/451
- https://learn.microsoft.com/en-us/windows-hardware/drivers/install/guid-devinterface-comport

### Keep Win32 Bluetooth APIs for pairing/unpair/SPP enablement

Microsoft documents the Win32 Bluetooth API surface for `BluetoothAuthenticateDeviceEx`, `BluetoothRegisterForAuthenticationEx`, `BluetoothSendAuthenticationResponseEx`, `BluetoothRemoveDevice`, and `BluetoothSetServiceState`. The current implementation uses these APIs directly from Python via `ctypes`, which keeps the app dependency-light and avoids less-maintained wrappers.

For no-PIN SSP devices, the app registers an authentication callback and accepts numeric comparison. This produced Bluetooth COM ports with ESP32 SPP firmware without requiring a PIN entry.

The app also uses `BluetoothEnumerateInstalledServices` as best-effort metadata for paired/remembered devices. When Windows exposes service GUIDs, the GUI can distinguish SPP/COM hints from BLE GATT or DFU/OTA-style firmware update hints. This does not replace full BLE GATT service discovery; it is a safe, dependency-light signal for the device list.

Sources:

- https://learn.microsoft.com/en-us/windows/win32/api/_bluetooth/
- https://learn.microsoft.com/en-us/windows/win32/api/bluetoothapis/nf-bluetoothapis-bluetoothauthenticatedeviceex
- https://learn.microsoft.com/en-us/windows/win32/api/bluetoothapis/nf-bluetoothapis-bluetoothregisterforauthenticationex
- https://learn.microsoft.com/en-us/windows/win32/api/bluetoothapis/nf-bluetoothapis-bluetoothsendauthenticationresponseex
- https://learn.microsoft.com/en-us/windows/win32/api/bluetoothapis/nf-bluetoothapis-bluetoothremovedevice
- https://learn.microsoft.com/en-us/windows/win32/api/bluetoothapis/nf-bluetoothapis-bluetoothenumerateinstalledservices

### Keep ESP32 SPP / no-COM hardware test sketches

WICG's Bluetooth serial explainer describes SPP as the Bluetooth Classic profile for RFCOMM-based serial communication and notes the standard Serial Port service UUID `0x1101`. The ESP32 SPP sketch exercises that path, while the no-COM sketch makes the negative case explicit.

Sources:

- https://github.com/WICG/serial/blob/main/EXPLAINER_BLUETOOTH.md
- https://docs.espressif.com/projects/arduino-esp32/en/latest/api/bluetooth.html

## Not adopted now

### PyBluez

PyBluez can access host Bluetooth resources and advertises Windows support, but this project already uses the direct Windows APIs needed for pairing/unpairing/SPP. Adding PyBluez would add dependency and packaging risk without solving Windows COM creation.

Source:

- https://github.com/pybluez/pybluez

### com0com automatic setup

com0com is a useful open-source virtual serial driver for Windows, but it is a kernel-mode virtual COM driver. Automatic installation would require driver/admin handling and is outside the app's safe default behavior. The project documents it as a manual COM-only test option.

Sources:

- https://com0com.sourceforge.net/
- https://github.com/paulakg4/com0com

### WinRT RFCOMM direct socket

Windows has WinRT RFCOMM APIs, but this app's user-facing target is Windows-created COM ports. Direct RFCOMM sockets would be a separate connection mode and would not prove that legacy COM software can see a port. It is a possible future advanced mode, not a replacement for COM validation.

Source:

- https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.rfcomm.rfcommdeviceservice

### Full BLE GATT/DFU flashing mode

Windows exposes BLE GATT client APIs, and Nordic documents Secure DFU Service `0xFE59`. A real firmware flashing mode would need device-specific GATT characteristics, package signing/format handling, and failure recovery. The current release only labels likely BLE GATT / DFU candidates so the user does not wait forever for a COM port when the device is not an SPP device.

Sources:

- https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/gatt-client
- https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.genericattributeprofile.gattdeviceservice
- https://nordicsemiconductor.github.io/Nordic-Thingy52-FW/documentation/firmware_architecture.html

### C++ helper process

C++ can call the same Win32 Bluetooth APIs more naturally, but the current Python `ctypes` implementation already reaches the authentication callback path and passed ESP32 hardware validation. A C++ helper would add build and release complexity without changing Windows user-consent or SPP requirements, so it is not needed for the current release.
