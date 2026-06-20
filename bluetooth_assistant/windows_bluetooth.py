from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from .com_ports import list_com_ports
from .models import BluetoothDevice, OperationResult, merge_duplicate_devices, normalize_address

BLUETOOTH_MAX_NAME_SIZE = 248
ERROR_SUCCESS = 0
ERROR_NO_MORE_ITEMS = 259
ERROR_NOT_FOUND = 1168
ERROR_SERVICE_DOES_NOT_EXIST = 1060
E_INVALIDARG = 0x80070057
BLUETOOTH_SERVICE_ENABLE = 0x00000001
BLUETOOTH_MITM_PROTECTION_NOT_REQUIRED = 0
BLUETOOTH_MAX_PASSKEY_SIZE = 16


class BluetoothError(RuntimeError):
    pass


class UnsupportedPlatformError(BluetoothError):
    pass


class BLUETOOTH_ADDRESS_UNION(ctypes.Union):
    _fields_ = [
        ("ullLong", ctypes.c_ulonglong),
        ("rgBytes", ctypes.c_ubyte * 6),
    ]


class BLUETOOTH_ADDRESS(ctypes.Structure):
    _fields_ = [("u", BLUETOOTH_ADDRESS_UNION)]


class SYSTEMTIME(ctypes.Structure):
    _fields_ = [
        ("wYear", wintypes.WORD),
        ("wMonth", wintypes.WORD),
        ("wDayOfWeek", wintypes.WORD),
        ("wDay", wintypes.WORD),
        ("wHour", wintypes.WORD),
        ("wMinute", wintypes.WORD),
        ("wSecond", wintypes.WORD),
        ("wMilliseconds", wintypes.WORD),
    ]


class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("Address", BLUETOOTH_ADDRESS),
        ("ulClassofDevice", ctypes.c_ulong),
        ("fConnected", wintypes.BOOL),
        ("fRemembered", wintypes.BOOL),
        ("fAuthenticated", wintypes.BOOL),
        ("stLastSeen", SYSTEMTIME),
        ("stLastUsed", SYSTEMTIME),
        ("szName", ctypes.c_wchar * BLUETOOTH_MAX_NAME_SIZE),
    ]


class BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("fReturnAuthenticated", wintypes.BOOL),
        ("fReturnRemembered", wintypes.BOOL),
        ("fReturnUnknown", wintypes.BOOL),
        ("fReturnConnected", wintypes.BOOL),
        ("fIssueInquiry", wintypes.BOOL),
        ("cTimeoutMultiplier", ctypes.c_ubyte),
        ("hRadio", wintypes.HANDLE),
    ]


class BLUETOOTH_FIND_RADIO_PARAMS(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD)]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


SPP_SERVICE_GUID = GUID(
    0x00001101,
    0x0000,
    0x1000,
    (ctypes.c_ubyte * 8)(0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB),
)


class WindowsBluetoothBackend:
    def __init__(self, parent_hwnd: int | None = None) -> None:
        if os.name != "nt":
            raise UnsupportedPlatformError("Windows のみ対応です")
        self._api = _BluetoothApi(parent_hwnd=parent_hwnd)

    def list_devices(self, *, issue_inquiry: bool = True, timeout_multiplier: int = 8) -> list[BluetoothDevice]:
        return self._api.enumerate_devices(issue_inquiry=issue_inquiry, timeout_multiplier=timeout_multiplier)

    def pair(self, address: str, pin: str = "") -> OperationResult:
        return self._api.pair(address, pin=pin)

    def unpair(self, address: str) -> OperationResult:
        return self._api.unpair(address)

    def enable_serial_service(self, address: str) -> OperationResult:
        return self._api.enable_serial_service(address)

    def list_com_ports(self):
        return list_com_ports()


class _BluetoothApi:
    def __init__(self, *, parent_hwnd: int | None = None) -> None:
        self._bth = ctypes.WinDLL("bthprops.cpl", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_functions()
        self._parent_hwnd = wintypes.HWND(parent_hwnd or self._kernel32.GetConsoleWindow() or 0)

    def enumerate_devices(self, *, issue_inquiry: bool, timeout_multiplier: int) -> list[BluetoothDevice]:
        params = BLUETOOTH_DEVICE_SEARCH_PARAMS()
        params.dwSize = ctypes.sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS)
        params.fReturnAuthenticated = True
        params.fReturnRemembered = True
        params.fReturnUnknown = True
        params.fReturnConnected = True
        params.fIssueInquiry = bool(issue_inquiry)
        params.cTimeoutMultiplier = max(1, min(int(timeout_multiplier), 48))
        params.hRadio = None

        info = _device_info()
        handle = self._bth.BluetoothFindFirstDevice(ctypes.byref(params), ctypes.byref(info))
        if not handle:
            error = ctypes.get_last_error()
            if error == ERROR_NO_MORE_ITEMS:
                return []
            raise BluetoothError(f"Bluetooth 機器の列挙に失敗しました: {_format_error(error)}")

        devices: list[BluetoothDevice] = []
        try:
            while True:
                devices.append(_model_from_info(info))
                info = _device_info()
                if not self._bth.BluetoothFindNextDevice(handle, ctypes.byref(info)):
                    error = ctypes.get_last_error()
                    if error == ERROR_NO_MORE_ITEMS:
                        break
                    raise BluetoothError(f"Bluetooth 機器の列挙中に失敗しました: {_format_error(error)}")
        finally:
            self._bth.BluetoothFindDeviceClose(handle)

        return merge_duplicate_devices(devices)

    def pair(self, address: str, *, pin: str = "") -> OperationResult:
        if pin:
            return self._pair_with_pin(address, pin)

        info = _device_info_for_address(address)
        code = self._bth.BluetoothAuthenticateDeviceEx(
            self._parent_window(),
            None,
            ctypes.byref(info),
            None,
            BLUETOOTH_MITM_PROTECTION_NOT_REQUIRED,
        )
        if code == ERROR_SUCCESS:
            return OperationResult(True, "ペアリングに成功しました", code)
        if code == ERROR_NO_MORE_ITEMS:
            return OperationResult(True, "すでにペアリング済みです", code)
        return OperationResult(False, f"ペアリングに失敗しました: {_format_error(code)}", code)

    def _pair_with_pin(self, address: str, pin: str) -> OperationResult:
        if len(pin) > BLUETOOTH_MAX_PASSKEY_SIZE:
            return OperationResult(False, f"PINは{BLUETOOTH_MAX_PASSKEY_SIZE}文字以内で指定してください")

        info = _device_info_for_address(address)
        code = self._bth.BluetoothAuthenticateDevice(
            self._parent_window(),
            None,
            ctypes.byref(info),
            pin,
            len(pin),
        )
        if code == ERROR_SUCCESS:
            return OperationResult(True, "PIN付きペアリングに成功しました", code)
        if code == ERROR_NO_MORE_ITEMS:
            return OperationResult(True, "すでにペアリング済みです", code)
        return OperationResult(False, f"PIN付きペアリングに失敗しました: {_format_error(code)}", code)

    def _parent_window(self) -> wintypes.HWND | None:
        return self._parent_hwnd if self._parent_hwnd.value else None

    def unpair(self, address: str) -> OperationResult:
        bt_address = _address_from_string(address)
        code = self._bth.BluetoothRemoveDevice(ctypes.byref(bt_address))
        if code == ERROR_SUCCESS:
            return OperationResult(True, "ペアリングを解除しました", code)
        if code == ERROR_NOT_FOUND:
            return OperationResult(True, "解除対象は見つかりませんでした", code)
        return OperationResult(False, f"解除に失敗しました: {_format_error(code)}", code)

    def enable_serial_service(self, address: str) -> OperationResult:
        handles = self._open_radio_handles()
        if not handles:
            return OperationResult(False, "Bluetooth ラジオが見つかりませんでした")

        last_code: int | None = None
        try:
            for handle in handles:
                info = _device_info_for_address(address)
                code = self._bth.BluetoothSetServiceState(
                    handle,
                    ctypes.byref(info),
                    ctypes.byref(SPP_SERVICE_GUID),
                    BLUETOOTH_SERVICE_ENABLE,
                )
                last_code = code
                if code == ERROR_SUCCESS:
                    return OperationResult(True, "Serial Port サービスを有効化しました", code)
                if code == E_INVALIDARG:
                    return OperationResult(True, "Serial Port サービスはすでに有効です", code)
                if code == ERROR_SERVICE_DOES_NOT_EXIST:
                    continue
        finally:
            for handle in handles:
                self._kernel32.CloseHandle(handle)

        if last_code == ERROR_SERVICE_DOES_NOT_EXIST:
            return OperationResult(False, "対象機器は Serial Port Profile を返していません", last_code)
        return OperationResult(
            False,
            f"Serial Port サービス有効化に失敗しました: {_format_error(last_code or 0)}",
            last_code,
        )

    def _open_radio_handles(self) -> list[wintypes.HANDLE]:
        params = BLUETOOTH_FIND_RADIO_PARAMS()
        params.dwSize = ctypes.sizeof(BLUETOOTH_FIND_RADIO_PARAMS)
        radio = wintypes.HANDLE()
        find_handle = self._bth.BluetoothFindFirstRadio(ctypes.byref(params), ctypes.byref(radio))
        if not find_handle:
            return []

        handles = [radio]
        try:
            while True:
                next_radio = wintypes.HANDLE()
                if not self._bth.BluetoothFindNextRadio(find_handle, ctypes.byref(next_radio)):
                    break
                handles.append(next_radio)
        finally:
            self._bth.BluetoothFindRadioClose(find_handle)
        return handles

    def _configure_functions(self) -> None:
        self._bth.BluetoothFindFirstDevice.argtypes = [
            ctypes.POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS),
            ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
        ]
        self._bth.BluetoothFindFirstDevice.restype = wintypes.HANDLE
        self._bth.BluetoothFindNextDevice.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
        ]
        self._bth.BluetoothFindNextDevice.restype = wintypes.BOOL
        self._bth.BluetoothFindDeviceClose.argtypes = [wintypes.HANDLE]
        self._bth.BluetoothFindDeviceClose.restype = wintypes.BOOL
        self._bth.BluetoothAuthenticateDeviceEx.argtypes = [
            wintypes.HWND,
            wintypes.HANDLE,
            ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self._bth.BluetoothAuthenticateDeviceEx.restype = wintypes.DWORD
        self._bth.BluetoothAuthenticateDevice.argtypes = [
            wintypes.HWND,
            wintypes.HANDLE,
            ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
            wintypes.LPCWSTR,
            ctypes.c_ulong,
        ]
        self._bth.BluetoothAuthenticateDevice.restype = wintypes.DWORD
        self._bth.BluetoothRemoveDevice.argtypes = [ctypes.POINTER(BLUETOOTH_ADDRESS)]
        self._bth.BluetoothRemoveDevice.restype = wintypes.DWORD
        self._bth.BluetoothFindFirstRadio.argtypes = [
            ctypes.POINTER(BLUETOOTH_FIND_RADIO_PARAMS),
            ctypes.POINTER(wintypes.HANDLE),
        ]
        self._bth.BluetoothFindFirstRadio.restype = wintypes.HANDLE
        self._bth.BluetoothFindNextRadio.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE)]
        self._bth.BluetoothFindNextRadio.restype = wintypes.BOOL
        self._bth.BluetoothFindRadioClose.argtypes = [wintypes.HANDLE]
        self._bth.BluetoothFindRadioClose.restype = wintypes.BOOL
        self._bth.BluetoothSetServiceState.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
            ctypes.POINTER(GUID),
            wintypes.DWORD,
        ]
        self._bth.BluetoothSetServiceState.restype = wintypes.DWORD
        self._kernel32.GetConsoleWindow.argtypes = []
        self._kernel32.GetConsoleWindow.restype = wintypes.HWND
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL


def _device_info() -> BLUETOOTH_DEVICE_INFO:
    info = BLUETOOTH_DEVICE_INFO()
    info.dwSize = ctypes.sizeof(BLUETOOTH_DEVICE_INFO)
    return info


def _device_info_for_address(address: str) -> BLUETOOTH_DEVICE_INFO:
    info = _device_info()
    info.Address = _address_from_string(address)
    return info


def _address_from_string(address: str) -> BLUETOOTH_ADDRESS:
    value = int(normalize_address(address).replace(":", ""), 16)
    bt_address = BLUETOOTH_ADDRESS()
    bt_address.u.ullLong = value
    return bt_address


def _format_address(address: BLUETOOTH_ADDRESS) -> str:
    value = int(address.u.ullLong) & 0xFFFFFFFFFFFF
    return ":".join(f"{(value >> shift) & 0xFF:02X}" for shift in range(40, -1, -8))


def _model_from_info(info: BLUETOOTH_DEVICE_INFO) -> BluetoothDevice:
    return BluetoothDevice(
        address=_format_address(info.Address),
        name=str(info.szName).rstrip("\x00"),
        class_of_device=int(info.ulClassofDevice),
        connected=bool(info.fConnected),
        remembered=bool(info.fRemembered),
        authenticated=bool(info.fAuthenticated),
        last_seen=_system_time_text(info.stLastSeen),
        last_used=_system_time_text(info.stLastUsed),
    )


def _system_time_text(value: SYSTEMTIME) -> str:
    if not value.wYear or value.wYear <= 1601:
        return ""
    return (
        f"{value.wYear:04d}-{value.wMonth:02d}-{value.wDay:02d} "
        f"{value.wHour:02d}:{value.wMinute:02d}:{value.wSecond:02d}"
    )


def _format_error(code: int) -> str:
    try:
        text = ctypes.FormatError(code).strip()
    except Exception:
        text = "unknown error"
    return f"{code} ({text})"
