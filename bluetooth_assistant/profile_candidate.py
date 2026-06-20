from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import BluetoothDevice, ComPortInfo, find_matching_ports

SPP_SERVICE_UUID = "00001101-0000-1000-8000-00805F9B34FB"
NORDIC_SECURE_DFU_SERVICE_UUID = "0000FE59-0000-1000-8000-00805F9B34FB"

_HEX_RE = re.compile(r"[^0-9A-Fa-f]")
_SPP_NAME_HINTS = ("spp", "serial", "rfcomm", "uart", "rs232")
_COM_NAME_HINTS = ("com",)
_BLE_NAME_HINTS = ("ble", "bluetooth le", "gatt", "nrf", "nordic")
_FW_NAME_HINTS = (
    "dfu",
    "ota",
    "bootloader",
    "firmware",
    "fw",
    "update",
    "ファーム",
    "書込",
    "書き込み",
)
_NEGATIVE_COM_HINTS = ("no-com", "nocom", "no com", "beacon", "keyboard", "mouse", "audio")


@dataclass(slots=True)
class ProfileCandidateAssessment:
    label: str
    profile: str
    score: int
    icon: str
    firmware_candidate: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def display_label(self) -> str:
        return f"{self.icon} {self.label}"


def assess_profile_candidate(
    device: BluetoothDevice,
    ports: list[ComPortInfo],
) -> ProfileCandidateAssessment:
    matched_ports = find_matching_ports(device.address, ports)
    name_text = _device_name_text(device)
    service_text = _service_text(device, matched_ports)
    reasons: list[str] = []
    spp_score = 0
    ble_score = 0
    fw_score = 0

    if matched_ports:
        spp_score += 80
        reasons.append("対象MACのCOMポートが見えています")

    if _contains_uuid(service_text, SPP_SERVICE_UUID):
        spp_score += 60
        reasons.append("Serial Port ProfileのUUID 0x1101 が見えています")

    if any(hint in name_text for hint in _SPP_NAME_HINTS):
        spp_score += 35
        reasons.append("名前にSPP/Serial/RFCOMM系のヒントがあります")

    if any(hint in name_text for hint in _COM_NAME_HINTS) and not _has_negative_com_hint(name_text):
        spp_score += 35
        reasons.append("名前にCOM系のヒントがあります")

    if _has_negative_com_hint(name_text):
        spp_score -= 45
        reasons.append("名前にCOMが出にくいヒントがあります")

    if _contains_uuid(service_text, NORDIC_SECURE_DFU_SERVICE_UUID):
        fw_score += 70
        ble_score += 35
        reasons.append("Nordic Secure DFUのUUID 0xFE59 が見えています")

    if any(hint in name_text for hint in _FW_NAME_HINTS):
        fw_score += 45
        reasons.append("名前にFW書き込み/DFU/OTA系のヒントがあります")

    if any(hint in name_text for hint in _BLE_NAME_HINTS):
        ble_score += 35
        reasons.append("名前にBLE/GATT系のヒントがあります")

    firmware_candidate = fw_score > 0
    if firmware_candidate and spp_score >= 35:
        return _assessment("FW/COM候補", "SPP/RFCOMM", fw_score + spp_score, "⇧", True, reasons)
    if firmware_candidate:
        return _assessment("FW/DFU候補", "BLE GATT/DFU", fw_score + ble_score, "⇧", True, reasons)
    if spp_score >= 80:
        return _assessment("SPP/COM", "SPP/RFCOMM", spp_score, "✓", False, reasons)
    if spp_score >= 35:
        return _assessment("SPP/COM候補", "SPP/RFCOMM", spp_score, "↔", False, reasons)
    if ble_score >= 35:
        return _assessment("BLE GATT候補", "BLE GATT", ble_score, "◇", False, reasons)

    if not reasons:
        reasons.append("プロファイルの手がかりはまだ少なめです")
    return _assessment("不明", "Unknown", max(0, spp_score, ble_score, fw_score), "?", False, reasons)


def _assessment(
    label: str,
    profile: str,
    score: int,
    icon: str,
    firmware_candidate: bool,
    reasons: list[str],
) -> ProfileCandidateAssessment:
    return ProfileCandidateAssessment(
        label=label,
        profile=profile,
        score=max(0, score),
        icon=icon,
        firmware_candidate=firmware_candidate,
        reasons=reasons,
    )


def _device_name_text(device: BluetoothDevice) -> str:
    names = [device.name, *device.raw_names]
    return " ".join(name for name in names if name).casefold()


def _service_text(device: BluetoothDevice, ports: list[ComPortInfo]) -> str:
    return " ".join(
        [
            *device.service_uuids,
            *(port.searchable_text() for port in ports),
        ]
    ).casefold()


def _contains_uuid(text: str, uuid: str) -> bool:
    cleaned = _HEX_RE.sub("", text).upper()
    compact = _HEX_RE.sub("", uuid).upper()
    short = compact[4:8] if compact.startswith("0000") else compact[:8]
    bluetooth_base = f"0000{short}00001000800000805F9B34FB"
    return compact in cleaned or bluetooth_base in cleaned


def _has_negative_com_hint(name_text: str) -> bool:
    return any(hint in name_text for hint in _NEGATIVE_COM_HINTS)
