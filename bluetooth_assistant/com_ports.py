from __future__ import annotations

import json
import os
import subprocess
from typing import Iterable

from .models import ComPortInfo


def list_com_ports() -> list[ComPortInfo]:
    ports = [*_list_pyserial_ports(), *_list_wmi_serial_ports()]
    return _dedupe_ports(ports)


def _list_pyserial_ports() -> list[ComPortInfo]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []

    results: list[ComPortInfo] = []
    for info in list_ports.comports():
        results.append(
            ComPortInfo(
                device=str(info.device or ""),
                name=str(info.name or ""),
                description=str(info.description or ""),
                hwid=str(info.hwid or ""),
                source="pyserial",
            )
        )
    return results


def _list_wmi_serial_ports() -> list[ComPortInfo]:
    if os.name != "nt":
        return []

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "Get-CimInstance Win32_SerialPort | "
            "Select-Object DeviceID,Name,Description,PNPDeviceID | "
            "ConvertTo-Json -Compress"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    payload = completed.stdout.strip()
    if not payload:
        return []

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return []

    rows: Iterable[dict[str, object]]
    if isinstance(parsed, dict):
        rows = (parsed,)
    elif isinstance(parsed, list):
        rows = (row for row in parsed if isinstance(row, dict))
    else:
        return []

    results: list[ComPortInfo] = []
    for row in rows:
        device = str(row.get("DeviceID") or "")
        results.append(
            ComPortInfo(
                device=device,
                name=str(row.get("Name") or device),
                description=str(row.get("Description") or ""),
                hwid=str(row.get("PNPDeviceID") or ""),
                source="wmi",
            )
        )
    return results


def _dedupe_ports(ports: Iterable[ComPortInfo]) -> list[ComPortInfo]:
    by_key: dict[tuple[str, str], ComPortInfo] = {}
    for port in ports:
        key = (port.device.upper(), port.hwid.upper())
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = port
            continue
        by_key[key] = ComPortInfo(
            device=existing.device or port.device,
            name=existing.name or port.name,
            description=existing.description or port.description,
            hwid=existing.hwid or port.hwid,
            source="+".join(dict.fromkeys(filter(None, [existing.source, port.source]))),
        )
    return sorted(by_key.values(), key=lambda item: item.device.upper())
