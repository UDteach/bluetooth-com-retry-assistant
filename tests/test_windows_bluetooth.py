import ctypes
import unittest
from unittest.mock import patch

import bluetooth_assistant.windows_bluetooth as windows_bluetooth
from bluetooth_assistant.windows_bluetooth import (
    BLUETOOTH_DEVICE_INFO,
    BLUETOOTH_MAX_PASSKEY_SIZE,
    ERROR_SUCCESS,
    SPP_SERVICE_GUID,
    SYSTEMTIME,
    _address_from_string,
    _BluetoothApi,
    _device_info,
    _format_address,
    _system_time_text,
)


class WindowsBluetoothStructTests(unittest.TestCase):
    def test_device_info_sets_required_size(self):
        info = _device_info()
        self.assertEqual(info.dwSize, ctypes.sizeof(BLUETOOTH_DEVICE_INFO))

    def test_bluetooth_address_round_trips(self):
        address = _address_from_string("AA:BB:CC:DD:EE:FF")
        self.assertEqual(_format_address(address), "AA:BB:CC:DD:EE:FF")

    def test_spp_service_guid_constant(self):
        self.assertEqual(SPP_SERVICE_GUID.Data1, 0x00001101)
        self.assertEqual(SPP_SERVICE_GUID.Data2, 0x0000)
        self.assertEqual(SPP_SERVICE_GUID.Data3, 0x1000)
        self.assertEqual(list(SPP_SERVICE_GUID.Data4), [0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB])

    def test_bluetooth_pin_limit_matches_windows_api(self):
        self.assertEqual(BLUETOOTH_MAX_PASSKEY_SIZE, 16)

    def test_unset_windows_system_time_is_blank(self):
        value = SYSTEMTIME()
        value.wYear = 1601
        value.wMonth = 1
        value.wDay = 1

        self.assertEqual(_system_time_text(value), "")


class FakeWinFunction:
    def __init__(self, result=ERROR_SUCCESS):
        self.result = result
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class FakeBluetoothDll:
    def __init__(self):
        self.BluetoothFindFirstDevice = FakeWinFunction()
        self.BluetoothFindNextDevice = FakeWinFunction()
        self.BluetoothFindDeviceClose = FakeWinFunction()
        self.BluetoothAuthenticateDeviceEx = FakeWinFunction()
        self.BluetoothAuthenticateDevice = FakeWinFunction()
        self.BluetoothRemoveDevice = FakeWinFunction()
        self.BluetoothFindFirstRadio = FakeWinFunction()
        self.BluetoothFindNextRadio = FakeWinFunction()
        self.BluetoothFindRadioClose = FakeWinFunction()
        self.BluetoothSetServiceState = FakeWinFunction()


class FakeKernel32Dll:
    def __init__(self, console_hwnd=0):
        self.GetConsoleWindow = FakeWinFunction(console_hwnd)
        self.CloseHandle = FakeWinFunction()


class WindowsBluetoothApiTests(unittest.TestCase):
    def test_pair_uses_parent_window_for_authentication_ui(self):
        fake_bth = FakeBluetoothDll()
        fake_kernel32 = FakeKernel32Dll()

        def fake_windll(name, **_kwargs):
            if name == "bthprops.cpl":
                return fake_bth
            if name == "kernel32":
                return fake_kernel32
            raise AssertionError(name)

        with patch.object(windows_bluetooth.ctypes, "WinDLL", side_effect=fake_windll, create=True):
            api = _BluetoothApi(parent_hwnd=12345)

        result = api.pair("AA:BB:CC:DD:EE:FF")

        self.assertTrue(result.ok)
        hwnd = fake_bth.BluetoothAuthenticateDeviceEx.calls[0][0]
        self.assertEqual(hwnd.value, 12345)

    def test_pair_uses_console_window_when_parent_is_not_supplied(self):
        fake_bth = FakeBluetoothDll()
        fake_kernel32 = FakeKernel32Dll(console_hwnd=6789)

        def fake_windll(name, **_kwargs):
            if name == "bthprops.cpl":
                return fake_bth
            if name == "kernel32":
                return fake_kernel32
            raise AssertionError(name)

        with patch.object(windows_bluetooth.ctypes, "WinDLL", side_effect=fake_windll, create=True):
            api = _BluetoothApi()

        result = api.pair("AA:BB:CC:DD:EE:FF")

        self.assertTrue(result.ok)
        hwnd = fake_bth.BluetoothAuthenticateDeviceEx.calls[0][0]
        self.assertEqual(hwnd.value, 6789)
