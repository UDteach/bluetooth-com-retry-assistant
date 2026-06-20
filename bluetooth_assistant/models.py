from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

_HEX_RE = re.compile(r"[^0-9A-Fa-f]")


def compact_address(address: str) -> str:
    value = _HEX_RE.sub("", address or "").upper()
    if len(value) != 12:
        raise ValueError(f"Bluetooth address must contain 12 hex digits: {address!r}")
    return value


def normalize_address(address: str) -> str:
    value = compact_address(address)
    return ":".join(value[index : index + 2] for index in range(0, 12, 2))


def reverse_compact_address(address: str) -> str:
    value = compact_address(address)
    parts = [value[index : index + 2] for index in range(0, 12, 2)]
    return "".join(reversed(parts))


def address_in_text(address: str, text: str | None) -> bool:
    if not text:
        return False
    cleaned = _HEX_RE.sub("", text).upper()
    return compact_address(address) in cleaned or reverse_compact_address(address) in cleaned


@dataclass(slots=True)
class BluetoothDevice:
    address: str
    name: str = ""
    class_of_device: int = 0
    connected: bool = False
    remembered: bool = False
    authenticated: bool = False
    last_seen: str = ""
    last_used: str = ""
    raw_count: int = 1
    raw_names: tuple[str, ...] = field(default_factory=tuple)
    service_uuids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.address = normalize_address(self.address)
        if not self.raw_names and self.name:
            self.raw_names = (self.name,)
        self.service_uuids = tuple(dict.fromkeys(uuid.upper() for uuid in self.service_uuids if uuid))

    @property
    def status_text(self) -> str:
        values: list[str] = []
        if self.connected:
            values.append("接続中")
        if self.authenticated:
            values.append("ペア済み")
        elif self.remembered:
            values.append("記憶済み")
        else:
            values.append("未ペア")
        if self.raw_count > 1:
            values.append(f"同一MAC {self.raw_count}件")
        return " / ".join(values)


@dataclass(slots=True)
class ComPortInfo:
    device: str
    name: str = ""
    description: str = ""
    hwid: str = ""
    source: str = ""

    def searchable_text(self) -> str:
        return " ".join(part for part in (self.device, self.name, self.description, self.hwid) if part)


@dataclass(slots=True)
class OperationResult:
    ok: bool
    message: str = ""
    code: int | None = None


def merge_duplicate_devices(devices: Iterable[BluetoothDevice]) -> list[BluetoothDevice]:
    grouped: dict[str, BluetoothDevice] = {}
    for device in devices:
        address = normalize_address(device.address)
        existing = grouped.get(address)
        if existing is None:
            grouped[address] = replace(
                device,
                address=address,
                raw_count=max(1, device.raw_count),
                raw_names=tuple(dict.fromkeys(device.raw_names or ((device.name,) if device.name else ()))),
                service_uuids=tuple(dict.fromkeys(device.service_uuids)),
            )
            continue

        names = tuple(
            dict.fromkeys(
                [
                    *(existing.raw_names or ((existing.name,) if existing.name else ())),
                    *(device.raw_names or ((device.name,) if device.name else ())),
                ]
            )
        )
        service_uuids = tuple(dict.fromkeys([*existing.service_uuids, *device.service_uuids]))
        grouped[address] = BluetoothDevice(
            address=address,
            name=existing.name or device.name,
            class_of_device=existing.class_of_device or device.class_of_device,
            connected=existing.connected or device.connected,
            remembered=existing.remembered or device.remembered,
            authenticated=existing.authenticated or device.authenticated,
            last_seen=existing.last_seen or device.last_seen,
            last_used=existing.last_used or device.last_used,
            raw_count=existing.raw_count + max(1, device.raw_count),
            raw_names=names,
            service_uuids=service_uuids,
        )
    return sorted(grouped.values(), key=lambda item: (item.name.lower(), item.address))


def find_matching_ports(address: str, ports: Iterable[ComPortInfo]) -> list[ComPortInfo]:
    normalized = normalize_address(address)
    return [port for port in ports if address_in_text(normalized, port.searchable_text())]
