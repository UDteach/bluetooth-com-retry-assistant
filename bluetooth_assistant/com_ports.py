from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterable

from .models import ComPortInfo

_COM_NAME_RE = re.compile(r"\bCOM\d+\b", re.IGNORECASE)


def list_com_ports() -> list[ComPortInfo]:
    if os.name == "nt":
        windows_ports = [*_list_wmi_serial_ports(), *_list_pnp_com_ports()]
        if windows_ports:
            return _dedupe_ports(windows_ports)
        return _dedupe_ports(_list_pyserial_ports())

    ports = _list_pyserial_ports()
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

    rows = _parse_json_rows(completed.stdout.strip())
    if rows is None:
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


def _list_pnp_com_ports() -> list[ComPortInfo]:
    if os.name != "nt":
        return []

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "Get-CimInstance Win32_PnPEntity | "
            "Where-Object { $_.Name -match '\\(COM\\d+\\)' -or $_.PNPClass -eq 'Ports' } | "
            "Select-Object Name,Caption,Description,PNPDeviceID,PNPClass | "
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

    rows = _parse_json_rows(completed.stdout.strip())
    if rows is None:
        return []

    results: list[ComPortInfo] = []
    for row in rows:
        name = str(row.get("Name") or row.get("Caption") or "")
        device = _extract_com_name(name)
        if not device:
            continue
        results.append(
            ComPortInfo(
                device=device,
                name=name or device,
                description=str(row.get("Description") or ""),
                hwid=str(row.get("PNPDeviceID") or ""),
                source="pnp",
            )
        )
    return results


def _parse_json_rows(payload: str) -> list[dict[str, object]] | None:
    if not payload:
        return []

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    return None


def _extract_com_name(text: str) -> str:
    match = _COM_NAME_RE.search(text or "")
    return match.group(0).upper() if match else ""


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
