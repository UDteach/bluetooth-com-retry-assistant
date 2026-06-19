from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from .com_candidate import assess_com_candidate
from .com_ports import list_com_ports
from .mock_backend import MockBluetoothBackend
from .models import BluetoothDevice, ComPortInfo, find_matching_ports, normalize_address
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


DeviceLoader = Callable[[], list[BluetoothDevice]]
PortLoader = Callable[[], list[ComPortInfo]]
Sleeper = Callable[[float], None]


def run_hardware_expectations(
    *,
    expect_device_name: str = "",
    expect_address: str = "",
    expect_com_port: str = "",
    wait_seconds: float = 0.0,
    poll_seconds: float = 3.0,
    device_loader: DeviceLoader | None = None,
    port_loader: PortLoader | None = None,
    sleeper: Sleeper = time.sleep,
) -> list[CheckResult]:
    device_loader = device_loader or _load_windows_devices
    port_loader = port_loader or list_com_ports
    wait_seconds = max(0.0, float(wait_seconds))
    poll_seconds = max(0.5, float(poll_seconds))
    started = time.monotonic()
    polls = 0

    while True:
        polls += 1
        results = _run_hardware_poll(
            expect_device_name=expect_device_name,
            expect_address=expect_address,
            expect_com_port=expect_com_port,
            device_loader=device_loader,
            port_loader=port_loader,
        )
        expectation_results = [result for result in results if result.name.startswith("expect_")]
        if expectation_results:
            passed = all(result.ok for result in expectation_results)
        else:
            passed = all(result.ok for result in results)
        elapsed = time.monotonic() - started
        if passed or elapsed >= wait_seconds:
            return [
                CheckResult(
                    "hardware_wait",
                    passed,
                    f"{polls} poll(s), {elapsed:.1f} second(s)",
                    {
                        "polls": polls,
                        "elapsed_seconds": round(elapsed, 1),
                        "wait_seconds": wait_seconds,
                        "poll_seconds": poll_seconds,
                    },
                ),
                *results,
            ]
        sleeper(poll_seconds)


def _run_hardware_poll(
    *,
    expect_device_name: str,
    expect_address: str,
    expect_com_port: str,
    device_loader: DeviceLoader,
    port_loader: PortLoader,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    devices: list[BluetoothDevice] = []
    ports: list[ComPortInfo] = []

    try:
        devices = device_loader()
    except Exception as exc:
        results.append(CheckResult("hardware_bluetooth_scan", False, str(exc)))
    else:
        results.append(
            CheckResult(
                "hardware_bluetooth_scan",
                True,
                f"{len(devices)} device(s)",
                [asdict(device) for device in devices],
            )
        )

    try:
        ports = port_loader()
    except Exception as exc:
        results.append(CheckResult("hardware_com_ports", False, str(exc)))
    else:
        results.append(
            CheckResult(
                "hardware_com_ports",
                True,
                f"{len(ports)} port(s)",
                [asdict(port) for port in ports],
            )
        )

    if devices:
        results.append(
            CheckResult(
                "hardware_com_candidates",
                True,
                f"{len(devices)} candidate(s)",
                [_candidate_data(device, ports) for device in devices],
            )
        )

    if expect_device_name:
        matched_devices = _devices_matching_name(devices, expect_device_name)
        results.append(
            CheckResult(
                "expect_device_name",
                bool(matched_devices),
                f"{len(matched_devices)} match(es) for {expect_device_name!r}",
                {
                    "expected": expect_device_name,
                    "matches": [asdict(device) for device in matched_devices],
                },
            )
        )

    if expect_address:
        try:
            normalized = normalize_address(expect_address)
        except ValueError as exc:
            results.append(CheckResult("expect_device_address", False, str(exc), {"expected": expect_address}))
        else:
            matched_devices = [device for device in devices if device.address == normalized]
            results.append(
                CheckResult(
                    "expect_device_address",
                    bool(matched_devices),
                    f"{len(matched_devices)} match(es) for {normalized}",
                    {
                        "expected": normalized,
                        "matches": [asdict(device) for device in matched_devices],
                    },
                )
            )

    if expect_com_port:
        expected = expect_com_port.upper()
        matched_ports = [port for port in ports if port.device.upper() == expected or port.name.upper() == expected]
        results.append(
            CheckResult(
                "expect_com_port",
                bool(matched_ports),
                f"{len(matched_ports)} match(es) for {expected}",
                {
                    "expected": expected,
                    "matches": [asdict(port) for port in matched_ports],
                },
            )
        )

    return results


def _load_windows_devices() -> list[BluetoothDevice]:
    return WindowsBluetoothBackend().list_devices(issue_inquiry=True)


def _devices_matching_name(devices: list[BluetoothDevice], expected_name: str) -> list[BluetoothDevice]:
    expected = expected_name.casefold()
    matches: list[BluetoothDevice] = []
    for device in devices:
        names = [device.name, *device.raw_names]
        if any(expected in (name or "").casefold() for name in names):
            matches.append(device)
    return matches


def _candidate_data(device: BluetoothDevice, ports: list[ComPortInfo]) -> dict[str, Any]:
    assessment = assess_com_candidate(device, ports)
    return {
        "address": device.address,
        "name": device.name,
        "label": assessment.label,
        "score": assessment.score,
        "reasons": assessment.reasons,
    }


def run_hardware_pairing_test(
    *,
    target_address: str = "",
    target_name: str = "",
    com_wait_seconds: float = 45.0,
    poll_seconds: float = 3.0,
    max_attempts: int = 1,
    backend: WindowsBluetoothBackend | None = None,
    sleeper: Sleeper = time.sleep,
) -> list[CheckResult]:
    if not target_address and not target_name:
        return [
            CheckResult(
                "hardware_pairing_guard",
                False,
                "Specify --target-address or --target-name for hardware pairing test.",
            )
        ]

    backend = backend or WindowsBluetoothBackend()
    results: list[CheckResult] = []

    try:
        devices_before = backend.list_devices(issue_inquiry=True)
    except Exception as exc:
        return [CheckResult("hardware_pairing_scan_before", False, str(exc))]

    results.append(
        CheckResult(
            "hardware_pairing_scan_before",
            True,
            f"{len(devices_before)} device(s)",
            [asdict(device) for device in devices_before],
        )
    )

    resolved = _resolve_target_device(devices_before, target_address=target_address, target_name=target_name)
    results.append(resolved)
    if not resolved.ok:
        return results

    address = str(resolved.data["address"])
    results.append(CheckResult("hardware_pairing_target", True, address, resolved.data))

    outcome = PairingRetrier(backend, sleeper=sleeper).run(
        address,
        RetryConfig(
            max_attempts=max(1, int(max_attempts)),
            com_wait_seconds=max(0.0, float(com_wait_seconds)),
            poll_interval_seconds=max(0.5, float(poll_seconds)),
            settle_seconds=2.0,
            unpair_before_each_attempt=True,
            enable_serial_service=True,
        ),
        on_event=lambda event: _append_pairing_event(results, event.stage, event.message, event.attempt, event.ports),
    )
    results.append(
        CheckResult(
            "hardware_pairing_outcome",
            outcome.success,
            outcome.message,
            {
                "success": outcome.success,
                "stopped": outcome.stopped,
                "attempts": outcome.attempts,
                "ports": [asdict(port) for port in outcome.ports],
            },
        )
    )

    try:
        devices_after = backend.list_devices(issue_inquiry=False)
    except Exception as exc:
        results.append(CheckResult("hardware_pairing_scan_after", False, str(exc)))
    else:
        matched_after = [device for device in devices_after if device.address == address]
        registered = bool(matched_after and (matched_after[0].remembered or matched_after[0].authenticated))
        results.append(
            CheckResult(
                "hardware_pairing_windows_registered",
                registered,
                "registered" if registered else "not registered",
                {
                    "target_address": address,
                    "matches": [asdict(device) for device in matched_after],
                    "devices": [asdict(device) for device in devices_after],
                },
            )
        )

    try:
        ports_after = backend.list_com_ports()
    except Exception as exc:
        results.append(CheckResult("hardware_pairing_com_after", False, str(exc)))
    else:
        matched_ports = find_matching_ports(address, ports_after)
        results.append(
            CheckResult(
                "hardware_pairing_com_after",
                bool(matched_ports),
                f"{len(matched_ports)} matching COM port(s)",
                {
                    "target_address": address,
                    "matching_ports": [asdict(port) for port in matched_ports],
                    "all_ports": [asdict(port) for port in ports_after],
                },
            )
        )

    return results


def _append_pairing_event(
    results: list[CheckResult],
    stage: str,
    message: str,
    attempt: int,
    ports: list[ComPortInfo],
) -> None:
    index = sum(1 for item in results if item.name.startswith("hardware_pairing_event_")) + 1
    results.append(
        CheckResult(
            f"hardware_pairing_event_{index}",
            True,
            message,
            {"stage": stage, "attempt": attempt, "ports": [asdict(port) for port in ports]},
        )
    )


def _resolve_target_device(
    devices: list[BluetoothDevice],
    *,
    target_address: str,
    target_name: str,
) -> CheckResult:
    if target_address:
        try:
            normalized = normalize_address(target_address)
        except ValueError as exc:
            return CheckResult("hardware_pairing_resolve_target", False, str(exc), {"target_address": target_address})
        matches = [device for device in devices if device.address == normalized]
        if not matches:
            return CheckResult(
                "hardware_pairing_resolve_target",
                False,
                f"Target address was not found: {normalized}",
                {"target_address": normalized, "devices": [asdict(device) for device in devices]},
            )
        return CheckResult(
            "hardware_pairing_resolve_target",
            True,
            normalized,
            {"address": normalized, "device": asdict(matches[0])},
        )

    matches = _devices_matching_name(devices, target_name)
    if len(matches) != 1:
        return CheckResult(
            "hardware_pairing_resolve_target",
            False,
            f"Expected exactly one device matching {target_name!r}, found {len(matches)}.",
            {"target_name": target_name, "matches": [asdict(device) for device in matches]},
        )
    return CheckResult(
        "hardware_pairing_resolve_target",
        True,
        matches[0].address,
        {"address": matches[0].address, "device": asdict(matches[0])},
    )


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
    parser.add_argument(
        "--esp32-check",
        action="store_true",
        help="Run read-only ESP32 SPP checks. Defaults to expecting device name BT-COM-MOCK.",
    )
    parser.add_argument("--expect-device-name", default="", help="Expected Bluetooth device name substring.")
    parser.add_argument("--expect-address", default="", help="Expected Bluetooth MAC address.")
    parser.add_argument("--expect-com-port", default="", help="Expected COM port, for example COM12.")
    parser.add_argument("--wait-seconds", type=float, default=0.0, help="Wait this many seconds for expectations.")
    parser.add_argument("--poll-seconds", type=float, default=3.0, help="Polling interval for expectation checks.")
    parser.add_argument(
        "--hardware-pairing-test",
        action="store_true",
        help="Actively unpair/pair a target device and wait for a matching COM port.",
    )
    parser.add_argument("--target-address", default="", help="Target MAC for --hardware-pairing-test.")
    parser.add_argument("--target-name", default="", help="Unique target name substring for --hardware-pairing-test.")
    parser.add_argument("--com-wait-seconds", type=float, default=45.0, help="COM wait for hardware pairing test.")
    parser.add_argument("--pair-attempts", type=int, default=1, help="Pair attempts for hardware pairing test.")
    args = parser.parse_args(argv)

    hardware_requested = args.esp32_check or any(
        [args.expect_device_name, args.expect_address, args.expect_com_port]
    )
    results = run_safe_diagnostics(
        scan_bluetooth=args.scan_bluetooth and not hardware_requested and not args.hardware_pairing_test
    )
    if args.mock_retry:
        results.extend(
            run_mock_retry(
                target_address=args.mock_target_address,
                target_com_port=args.mock_com_port,
                appear_after_pair_count=args.mock_appear_after,
            )
        )
    if hardware_requested:
        results.extend(
            run_hardware_expectations(
                expect_device_name=args.expect_device_name or ("BT-COM-MOCK" if args.esp32_check else ""),
                expect_address=args.expect_address,
                expect_com_port=args.expect_com_port,
                wait_seconds=args.wait_seconds,
                poll_seconds=args.poll_seconds,
            )
        )
    if args.hardware_pairing_test:
        results.extend(
            run_hardware_pairing_test(
                target_address=args.target_address,
                target_name=args.target_name,
                com_wait_seconds=args.com_wait_seconds,
                poll_seconds=args.poll_seconds,
                max_attempts=args.pair_attempts,
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
