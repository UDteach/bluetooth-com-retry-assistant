import ctypes
import unittest

from bluetooth_assistant.windows_bluetooth import (
    BLUETOOTH_DEVICE_INFO,
    SPP_SERVICE_GUID,
    SYSTEMTIME,
    _address_from_string,
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

    def test_unset_windows_system_time_is_blank(self):
        value = SYSTEMTIME()
        value.wYear = 1601
        value.wMonth = 1
        value.wDay = 1

        self.assertEqual(_system_time_text(value), "")
