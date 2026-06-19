from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from dataclasses import asdict, dataclass
from typing import Any

from .com_ports import list_com_ports
from .mock_backend import MockBluetoothBackend
from .retry import PairingRetrier, RetryConfig
from .windows_bluetooth import BluetoothError, UnsupportedPlatformError, WindowsBluetoothBackend


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    data: Any = None


def run_safe_diagnostics(*, scan_bluetooth: bool = False) -> list[CheckResult]:
    results = [
        CheckResult(
            "python",
            True,
            f"{sys.version.split()[0]} on {platform.platform()}",
            {"executable": sys.executable},
        )
    ]
    results.append(_check_tkinter())
    results.append(_check_pyserial())
    results.append(_check_com_ports())
    results.append(_check_windows_backend_load(scan_bluetooth=scan_bluetooth))
    return results


def run_mock_retry(
    *,
    target_address: str = "AA:BB:CC:DD:EE:FF",
    target_com_port: str = "COM12",
    appear_after_pair_count: int = 2,
) -> list[CheckResult]:
    backend = MockBluetoothBackend(
        target_address=target_address,
        target_com_port=target_com_port,
        appear_after_pair_count=appear_after_pair_count,
    )
    events: list[str] = []
    outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
        backend.target_address,
        RetryConfig(max_attempts=3, com_wait_seconds=0, settle_seconds=0),
        on_event=lambda event: events.append(f"{event.stage}:{event.attempt}:{event.message}"),
    )
    return [
        CheckResult(
            "mock_retry",
            outcome.success and outcome.ports and outcome.ports[0].device == target_com_port,
            outcome.message,
            {
                "target_address": backend.target_address,
                "target_com_port": target_com_port,
                "pair_count": backend.pair_count,
                "unpair_count": backend.unpair_count,
                "service_count": backend.service_count,
                "slow_device_pair_count": backend.pair_count_for("11:22:33:44:55:66"),
                "history": backend.history,
                "events": events,
                "ports": [asdict(port) for port in outcome.ports],
            },
        )
    ]


def _check_tkinter() -> CheckResult:
    try:
        import tkinter

        return CheckResult("tkinter_import", True, f"Tk {tkinter.TkVersion}")
    except Exception as exc:
        return CheckResult("tkinter_import", False, str(exc))


def _check_pyserial() -> CheckResult:
    try:
        version = importlib.metadata.version("pyserial")
        return CheckResult("pyserial", True, version)
    except importlib.metadata.PackageNotFoundError:
        return CheckResult("pyserial", False, "pyserial is not installed")


def _check_com_ports() -> CheckResult:
    try:
        ports = list_com_ports()
        return CheckResult("com_ports", True, f"{len(ports)} port(s)", [asdict(port) for port in ports])
    except Exception as exc:
        return CheckResult("com_ports", False, str(exc))


def _check_windows_backend_load(*, scan_bluetooth: bool) -> CheckResult:
    try:
        backend = WindowsBluetoothBackend()
    except UnsupportedPlatformError as exc:
        return CheckResult("windows_bluetooth_backend", True, str(exc))
    except BluetoothError as exc:
        return CheckResult("windows_bluetooth_backend", False, str(exc))
    except Exception as exc:
        return CheckResult("windows_bluetooth_backend", False, str(exc))

    if not scan_bluetooth:
        return CheckResult("windows_bluetooth_backend", True, "backend loaded; Bluetooth scan skipped")

    try:
        devices = backend.list_devices(issue_inquiry=True)
        return CheckResult(
            "windows_bluetooth_scan",
            True,
            f"{len(devices)} device(s)",
            [asdict(device) for device in devices],
        )
    except Exception as exc:
        return CheckResult("windows_bluetooth_scan", False, str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run safe BluetoothAssistant diagnostics.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument(
        "--scan-bluetooth",
        action="store_true",
        help="Also run a read-only Bluetooth device scan. This does not pair or unpair devices.",
    )
    parser.add_argument("--mock-retry", action="store_true", help="Run the built-in mock pairing retry scenario.")
    parser.add_argument(
        "--mock-target-address",
        default="AA:BB:CC:DD:EE:FF",
        help="Target MAC address for --mock-retry.",
    )
    parser.add_argument("--mock-com-port", default="COM12", help="COM port name expected from --mock-retry.")
    parser.add_argument(
        "--mock-appear-after",
        type=int,
        default=2,
        help="Number of mock pair attempts before --mock-retry returns a COM port.",
    )
    args = parser.parse_args(argv)

    results = run_safe_diagnostics(scan_bluetooth=args.scan_bluetooth)
    if args.mock_retry:
        results.extend(
            run_mock_retry(
                target_address=args.mock_target_address,
                target_com_port=args.mock_com_port,
                appear_after_pair_count=args.mock_appear_after,
            )
        )

    if args.json:
        print(json.dumps([asdict(result) for result in results], ensure_ascii=True, indent=2))
    else:
        for result in results:
            status = "OK" if result.ok else "FAIL"
            print(f"[{status}] {result.name}: {result.detail}")

    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
