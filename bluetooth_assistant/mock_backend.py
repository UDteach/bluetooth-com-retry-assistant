from __future__ import annotations

from dataclasses import dataclass, field

from .models import BluetoothDevice, ComPortInfo, OperationResult, merge_duplicate_devices, normalize_address


@dataclass(slots=True)
class MockBluetoothBackend:
    target_address: str = "AA:BB:CC:DD:EE:FF"
    appear_after_pair_count: int = 2
    fail_pair_attempts: set[int] = field(default_factory=set)
    duplicate_devices: bool = True
    service_result: OperationResult = field(default_factory=lambda: OperationResult(True, "mock service enabled"))
    pair_count: int = 0
    unpair_count: int = 0
    service_count: int = 0
    scan_count: int = 0

    def list_devices(self, *, issue_inquiry: bool = True, timeout_multiplier: int = 8) -> list[BluetoothDevice]:
        self.scan_count += 1
        devices = [
            BluetoothDevice(self.target_address, name="Mock SPP Device", authenticated=self.pair_count > 0),
        ]
        if self.duplicate_devices:
            devices.append(
                BluetoothDevice(
                    self.target_address.replace(":", ""),
                    name="Mock SPP Device Duplicate",
                    remembered=True,
                )
            )
        return merge_duplicate_devices(devices)

    def pair(self, address: str) -> OperationResult:
        normalize_address(address)
        self.pair_count += 1
        if self.pair_count in self.fail_pair_attempts:
            return OperationResult(False, f"mock pair failed at attempt {self.pair_count}", 1)
        return OperationResult(True, f"mock pair succeeded at attempt {self.pair_count}")

    def unpair(self, address: str) -> OperationResult:
        normalize_address(address)
        self.unpair_count += 1
        return OperationResult(True, f"mock unpair {self.unpair_count}")

    def enable_serial_service(self, address: str) -> OperationResult:
        normalize_address(address)
        self.service_count += 1
        return self.service_result

    def list_com_ports(self) -> list[ComPortInfo]:
        if self.pair_count >= self.appear_after_pair_count:
            compact = normalize_address(self.target_address).replace(":", "")
            return [
                ComPortInfo(
                    "COM12",
                    name="COM12",
                    description="Standard Serial over Bluetooth link",
                    hwid=rf"BTHENUM\{{00001101-0000-1000-8000-00805F9B34FB}}\7&MOCK&0&{compact}_C00000003",
                    source="mock",
                )
            ]
        return []
