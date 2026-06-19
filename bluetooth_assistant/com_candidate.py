from __future__ import annotations

from dataclasses import dataclass, field

from .models import BluetoothDevice, ComPortInfo, find_matching_ports

_NAME_HINTS = ("spp", "serial", "rfcomm", "com", "uart", "rs232")
_NEGATIVE_NAME_HINTS = ("no-com", "nocom", "ble", "beacon", "keyboard", "mouse", "audio")


@dataclass(slots=True)
class ComCandidateAssessment:
    label: str
    score: int
    reasons: list[str] = field(default_factory=list)


def assess_com_candidate(device: BluetoothDevice, ports: list[ComPortInfo]) -> ComCandidateAssessment:
    score = 0
    reasons: list[str] = []

    matched_ports = find_matching_ports(device.address, ports)
    if matched_ports:
        score += 100
        reasons.append("このMACに紐づくCOMが既にあります")

    name_text = _device_name_text(device)
    if any(hint in name_text for hint in _NAME_HINTS):
        score += 35
        reasons.append("名前にSPP/Serial/COM系のヒントがあります")

    if any(hint in name_text for hint in _NEGATIVE_NAME_HINTS):
        score -= 45
        reasons.append("名前にCOMが出にくいヒントがあります")

    if device.authenticated:
        score += 15
        reasons.append("ペアリング済みです")
    elif device.remembered:
        score += 8
        reasons.append("Windowsに記憶されています")

    if device.connected:
        score += 8
        reasons.append("接続中です")

    if device.raw_count > 1:
        score += 5
        reasons.append("同じMACが複数見えています")

    if score >= 80:
        label = "COMあり"
    elif score >= 35:
        label = "COM候補 高"
    elif score >= 10:
        label = "COM候補 中"
    else:
        label = "COM候補 低"

    if not reasons:
        reasons.append("COMが出る手がかりはまだ少なめです")

    return ComCandidateAssessment(label=label, score=score, reasons=reasons)


def _device_name_text(device: BluetoothDevice) -> str:
    names = [device.name, *device.raw_names]
    return " ".join(name for name in names if name).casefold()
