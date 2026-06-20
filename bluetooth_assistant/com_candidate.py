from __future__ import annotations

from dataclasses import dataclass, field

from .models import BluetoothDevice, ComPortInfo, find_matching_ports

_NAME_HINTS = ("spp", "serial", "rfcomm", "com", "uart", "rs232")
_NEGATIVE_NAME_HINTS = ("no-com", "nocom", "ble", "beacon", "keyboard", "mouse", "audio")


@dataclass(slots=True)
class ComCandidateAssessment:
    label: str
    score: int
    icon: str
    reasons: list[str] = field(default_factory=list)

    @property
    def display_label(self) -> str:
        return f"{self.icon} {self.label}"


def assess_com_candidate(
    device: BluetoothDevice,
    ports: list[ComPortInfo],
    *,
    same_address_count: int | None = None,
) -> ComCandidateAssessment:
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

    duplicate_count = same_address_count if same_address_count is not None else device.raw_count
    if duplicate_count > 1:
        score += 5
        reasons.append(f"同じMACが{duplicate_count}件見えています")

    if score >= 80:
        label = "COMあり"
        icon = "✓"
    elif score >= 35:
        label = "COM候補 高"
        icon = "▲"
    elif score >= 10:
        label = "COM候補 中"
        icon = "△"
    else:
        label = "COM候補 低"
        icon = "×"

    if not reasons:
        reasons.append("COMが出る手がかりはまだ少なめです")

    return ComCandidateAssessment(label=label, score=score, icon=icon, reasons=reasons)


def _device_name_text(device: BluetoothDevice) -> str:
    names = [device.name, *device.raw_names]
    return " ".join(name for name in names if name).casefold()
