import ctypes
import unittest
from unittest.mock import patch

import bluetooth_assistant.windows_bluetooth as windows_bluetooth
from bluetooth_assistant.windows_bluetooth import (
    BLUETOOTH_AUTHENTICATE_RESPONSE,
    BLUETOOTH_AUTHENTICATION_CALLBACK_PARAMS,
    BLUETOOTH_AUTHENTICATION_METHOD_NUMERIC_COMPARISON,
    BLUETOOTH_DEVICE_INFO,
    BLUETOOTH_MAX_PASSKEY_SIZE,
    ERROR_MORE_DATA,
    ERROR_SUCCESS,
    SPP_SERVICE_GUID,
    SYSTEMTIME,
    _address_from_string,
    _BluetoothApi,
    _device_info,
    _format_address,
    _guid_to_string,
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
        self.assertEqual(_guid_to_string(SPP_SERVICE_GUID), "00001101-0000-1000-8000-00805F9B34FB")

    def test_bluetooth_pin_limit_matches_windows_api(self):
        self.assertEqual(BLUETOOTH_MAX_PASSKEY_SIZE, 16)

    def test_unset_windows_system_time_is_blank(self):
        value = SYSTEMTIME()
        value.wYear = 1601
        value.wMonth = 1
        value.wDay = 1

        self.assertEqual(_system_time_text(value), "")


class FakeWinFunction:
    def __init__(self, result=ERROR_SUCCESS, handler=None):
        self.result = result
        self.handler = handler
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        if self.handler:
            return self.handler(*args)
        return self.result


class FakeBluetoothDll:
    def __init__(self, *, callback_method=None, installed_services=None, enumerate_services_code=ERROR_SUCCESS):
        self.callback_method = callback_method
        self.installed_services = list(installed_services or [])
        self.enumerate_services_code = enumerate_services_code
        self.auth_callback = None
        self.auth_callback_param = None
        self.auth_responses = []
        self.enumerate_services_calls = []
        self.BluetoothFindFirstDevice = FakeWinFunction()
        self.BluetoothFindNextDevice = FakeWinFunction()
        self.BluetoothFindDeviceClose = FakeWinFunction()
        self.BluetoothAuthenticateDeviceEx = FakeWinFunction(handler=self._authenticate_device_ex)
        self.BluetoothAuthenticateDevice = FakeWinFunction()
        self.BluetoothRegisterForAuthenticationEx = FakeWinFunction(handler=self._register_authentication_ex)
        self.BluetoothUnregisterAuthentication = FakeWinFunction()
        self.BluetoothSendAuthenticationResponseEx = FakeWinFunction(
            handler=self._send_authentication_response_ex
        )
        self.BluetoothRemoveDevice = FakeWinFunction()
        self.BluetoothFindFirstRadio = FakeWinFunction()
        self.BluetoothFindNextRadio = FakeWinFunction()
        self.BluetoothFindRadioClose = FakeWinFunction()
        self.BluetoothSetServiceState = FakeWinFunction()
        self.BluetoothEnumerateInstalledServices = FakeWinFunction(handler=self._enumerate_installed_services)

    def _register_authentication_ex(self, _info, registration, callback, callback_param):
        registration._obj.value = 1
        self.auth_callback = callback
        self.auth_callback_param = callback_param
        return ERROR_SUCCESS

    def _authenticate_device_ex(self, _hwnd, _radio, info, _oob, _requirements):
        if self.callback_method is not None and self.auth_callback:
            params = BLUETOOTH_AUTHENTICATION_CALLBACK_PARAMS()
            params.deviceInfo = info._obj
            params.authenticationMethod = self.callback_method
            params.Numeric_Value = 123456
            self.auth_callback(self.auth_callback_param, ctypes.byref(params))
        return ERROR_SUCCESS

    def _send_authentication_response_ex(self, _radio, response):
        self.auth_responses.append(response._obj)
        return ERROR_SUCCESS

    def _enumerate_installed_services(self, radio, _info, count, services):
        self.enumerate_services_calls.append((radio, count._obj.value, services is None))
        if self.enumerate_services_code != ERROR_SUCCESS:
            return self.enumerate_services_code
        if services is None:
            count._obj.value = len(self.installed_services)
            return ERROR_SUCCESS

        requested_count = count._obj.value
        returned_count = min(requested_count, len(self.installed_services))
        for index in range(returned_count):
            services[index] = self.installed_services[index]
        count._obj.value = returned_count
        return ERROR_MORE_DATA if returned_count < len(self.installed_services) else ERROR_SUCCESS


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
        self.assertEqual(len(fake_bth.BluetoothRegisterForAuthenticationEx.calls), 1)
        self.assertEqual(len(fake_bth.BluetoothUnregisterAuthentication.calls), 1)

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

    def test_pair_accepts_numeric_comparison_callback(self):
        fake_bth = FakeBluetoothDll(callback_method=BLUETOOTH_AUTHENTICATION_METHOD_NUMERIC_COMPARISON)
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
        self.assertIn("numeric comparison accepted", result.message)
        self.assertEqual(len(fake_bth.auth_responses), 1)
        response = fake_bth.auth_responses[0]
        self.assertIsInstance(response, BLUETOOTH_AUTHENTICATE_RESPONSE)
        self.assertEqual(response.authMethod, BLUETOOTH_AUTHENTICATION_METHOD_NUMERIC_COMPARISON)
        self.assertEqual(response.numericCompInfo.NumericValue, 123456)
        self.assertEqual(response.negativeResponse, 0)

    def test_installed_service_uuids_uses_null_probe_then_reads_services(self):
        fake_bth = FakeBluetoothDll(installed_services=[SPP_SERVICE_GUID])
        fake_kernel32 = FakeKernel32Dll()

        def fake_windll(name, **_kwargs):
            if name == "bthprops.cpl":
                return fake_bth
            if name == "kernel32":
                return fake_kernel32
            raise AssertionError(name)

        with patch.object(windows_bluetooth.ctypes, "WinDLL", side_effect=fake_windll, create=True):
            api = _BluetoothApi(parent_hwnd=12345)
        info = _device_info()
        info.fRemembered = True

        service_uuids = api._installed_service_uuids(info)

        self.assertEqual(service_uuids, ("00001101-0000-1000-8000-00805F9B34FB",))
        self.assertEqual(len(fake_bth.enumerate_services_calls), 2)
        self.assertIsNone(fake_bth.enumerate_services_calls[0][0])
        self.assertTrue(fake_bth.enumerate_services_calls[0][2])

    def test_installed_service_uuids_skips_unremembered_devices(self):
        fake_bth = FakeBluetoothDll(installed_services=[SPP_SERVICE_GUID])
        fake_kernel32 = FakeKernel32Dll()

        def fake_windll(name, **_kwargs):
            if name == "bthprops.cpl":
                return fake_bth
            if name == "kernel32":
                return fake_kernel32
            raise AssertionError(name)

        with patch.object(windows_bluetooth.ctypes, "WinDLL", side_effect=fake_windll, create=True):
            api = _BluetoothApi(parent_hwnd=12345)

        self.assertEqual(api._installed_service_uuids(_device_info()), ())
        self.assertEqual(fake_bth.enumerate_services_calls, [])

    def test_installed_service_uuids_handles_zero_services(self):
        fake_bth = FakeBluetoothDll(installed_services=[])
        fake_kernel32 = FakeKernel32Dll()

        def fake_windll(name, **_kwargs):
            if name == "bthprops.cpl":
                return fake_bth
            if name == "kernel32":
                return fake_kernel32
            raise AssertionError(name)

        with patch.object(windows_bluetooth.ctypes, "WinDLL", side_effect=fake_windll, create=True):
            api = _BluetoothApi(parent_hwnd=12345)
        info = _device_info()
        info.fAuthenticated = True

        self.assertEqual(api._installed_service_uuids(info), ())
        self.assertEqual(len(fake_bth.enumerate_services_calls), 1)

    def test_installed_service_uuids_handles_api_error(self):
        fake_bth = FakeBluetoothDll(installed_services=[SPP_SERVICE_GUID], enumerate_services_code=5)
        fake_kernel32 = FakeKernel32Dll()

        def fake_windll(name, **_kwargs):
            if name == "bthprops.cpl":
                return fake_bth
            if name == "kernel32":
                return fake_kernel32
            raise AssertionError(name)

        with patch.object(windows_bluetooth.ctypes, "WinDLL", side_effect=fake_windll, create=True):
            api = _BluetoothApi(parent_hwnd=12345)
        info = _device_info()
        info.fConnected = True

        self.assertEqual(api._installed_service_uuids(info), ())

    def test_installed_service_uuids_handles_more_than_default_buffer(self):
        services = [
            windows_bluetooth.GUID(
                0x10000000 + index,
                0x0000,
                0x1000,
                (ctypes.c_ubyte * 8)(0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB),
            )
            for index in range(33)
        ]
        fake_bth = FakeBluetoothDll(installed_services=services)
        fake_kernel32 = FakeKernel32Dll()

        def fake_windll(name, **_kwargs):
            if name == "bthprops.cpl":
                return fake_bth
            if name == "kernel32":
                return fake_kernel32
            raise AssertionError(name)

        with patch.object(windows_bluetooth.ctypes, "WinDLL", side_effect=fake_windll, create=True):
            api = _BluetoothApi(parent_hwnd=12345)
        info = _device_info()
        info.fRemembered = True

        service_uuids = api._installed_service_uuids(info)

        self.assertEqual(len(service_uuids), 33)
        self.assertEqual(service_uuids[0], "10000000-0000-1000-8000-00805F9B34FB")
        self.assertEqual(service_uuids[-1], "10000020-0000-1000-8000-00805F9B34FB")
