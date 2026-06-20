from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .models import BluetoothDevice, ComPortInfo, OperationResult, normalize_address


@dataclass(slots=True)
class MockDeviceScenario:
    address: str
    name: str
    com_port: str
    appear_after_pair_count: int | None = 2
    fail_pair_attempts: set[int] = field(default_factory=set)
    duplicate_devices: bool = False
    service_result: OperationResult = field(
        default_factory=lambda: OperationResult(True, "テスト用: COM作成依頼を成功扱いにしました")
    )
    remembered: bool = True
    class_of_device: int = 0x001F00

    def __post_init__(self) -> None:
        self.address = normalize_address(self.address)
        self.fail_pair_attempts = set(self.fail_pair_attempts)


class MockBluetoothBackend:
    def __init__(
        self,
        target_address: str = "AA:BB:CC:DD:EE:FF",
        appear_after_pair_count: int | None = 2,
        fail_pair_attempts: set[int] | None = None,
        duplicate_devices: bool = True,
        service_result: OperationResult | None = None,
        target_com_port: str = "COM12",
        scenarios: Iterable[MockDeviceScenario] | None = None,
    ) -> None:
        self.target_address = normalize_address(target_address)
        self.scan_count = 0
        self.history: list[tuple[str, str, int]] = []
        self._pair_counts: dict[str, int] = {}
        self._unpair_counts: dict[str, int] = {}
        self._service_counts: dict[str, int] = {}
        self._paired: dict[str, bool] = {}
        self._scenarios: dict[str, MockDeviceScenario] = {}

        if scenarios is None:
            service_result = service_result or OperationResult(True, "テスト用: COM作成依頼を成功扱いにしました")
            scenarios = self._default_scenarios(
                self.target_address,
                appear_after_pair_count,
                fail_pair_attempts or set(),
                duplicate_devices,
                service_result,
                target_com_port,
            )

        for scenario in scenarios:
            self._scenarios[scenario.address] = scenario

    @property
    def pair_count(self) -> int:
        return self.pair_count_for(self.target_address)

    @property
    def unpair_count(self) -> int:
        return self.unpair_count_for(self.target_address)

    @property
    def service_count(self) -> int:
        return self.service_count_for(self.target_address)

    def pair_count_for(self, address: str) -> int:
        return self._pair_counts.get(normalize_address(address), 0)

    def unpair_count_for(self, address: str) -> int:
        return self._unpair_counts.get(normalize_address(address), 0)

    def service_count_for(self, address: str) -> int:
        return self._service_counts.get(normalize_address(address), 0)

    def list_devices(self, *, issue_inquiry: bool = True, timeout_multiplier: int = 8) -> list[BluetoothDevice]:
        self.scan_count += 1
        devices: list[BluetoothDevice] = []
        for scenario in self._scenarios.values():
            address = scenario.address
            paired = self._paired.get(address, False)
            devices.append(
                BluetoothDevice(
                    address,
                    name=scenario.name,
                    class_of_device=scenario.class_of_device,
                    connected=paired,
                    remembered=scenario.remembered or paired,
                    authenticated=paired,
                    last_seen=f"テストスキャン {self.scan_count}",
                )
            )
            if scenario.duplicate_devices:
                devices.append(
                    BluetoothDevice(
                        address.replace(":", ""),
                        name=f"{scenario.name}（同じMAC）",
                        class_of_device=scenario.class_of_device,
                        remembered=True,
                        last_seen=f"テスト重複 {self.scan_count}",
                    )
                )
        return sorted(devices, key=lambda item: (item.address, item.name.lower(), item.last_seen))

    def pair(self, address: str, pin: str = "") -> OperationResult:
        _ = pin
        scenario = self._scenario_for(address, create=True)
        count = self.pair_count_for(scenario.address) + 1
        self._pair_counts[scenario.address] = count
        self.history.append(("pair", scenario.address, count))

        if count in scenario.fail_pair_attempts:
            self._paired[scenario.address] = False
            return OperationResult(False, f"テスト用: ペアリング失敗（{count}回目）", 1)

        self._paired[scenario.address] = True
        return OperationResult(True, f"テスト用: ペアリング成功（{count}回目）")

    def unpair(self, address: str) -> OperationResult:
        scenario = self._scenario_for(address, create=True)
        count = self.unpair_count_for(scenario.address) + 1
        self._unpair_counts[scenario.address] = count
        self._paired[scenario.address] = False
        self.history.append(("unpair", scenario.address, count))
        return OperationResult(True, f"テスト用: 登録解除（{count}回目）")

    def enable_serial_service(self, address: str) -> OperationResult:
        scenario = self._scenario_for(address, create=True)
        count = self.service_count_for(scenario.address) + 1
        self._service_counts[scenario.address] = count
        self.history.append(("service", scenario.address, count))
        return scenario.service_result

    def list_com_ports(self) -> list[ComPortInfo]:
        ports: list[ComPortInfo] = []
        for scenario in self._scenarios.values():
            threshold = scenario.appear_after_pair_count
            if threshold is None:
                continue
            has_existing_port = threshold <= 0
            has_new_port = (
                self._paired.get(scenario.address, False)
                and self.pair_count_for(scenario.address) >= threshold
            )
            if has_existing_port or has_new_port:
                ports.append(self._com_port_for(scenario))
        return ports

    def _scenario_for(self, address: str, *, create: bool) -> MockDeviceScenario:
        normalized = normalize_address(address)
        scenario = self._scenarios.get(normalized)
        if scenario is not None:
            return scenario
        if not create:
            raise KeyError(normalized)

        com_number = 20 + len(self._scenarios)
        scenario = MockDeviceScenario(
            normalized,
            name="手入力テスト機器",
            com_port=f"COM{com_number}",
            appear_after_pair_count=2,
            duplicate_devices=False,
        )
        self._scenarios[scenario.address] = scenario
        return scenario

    @staticmethod
    def _default_scenarios(
        target_address: str,
        appear_after_pair_count: int | None,
        fail_pair_attempts: set[int],
        duplicate_devices: bool,
        service_result: OperationResult,
        target_com_port: str,
    ) -> list[MockDeviceScenario]:
        return [
            MockDeviceScenario(
                target_address,
                name="テスト用 COM 機器",
                com_port=target_com_port,
                appear_after_pair_count=appear_after_pair_count,
                fail_pair_attempts=fail_pair_attempts,
                duplicate_devices=duplicate_devices,
                service_result=service_result,
            ),
            MockDeviceScenario(
                "11:22:33:44:55:66",
                name="テスト用 COM遅延機器",
                com_port="COM13",
                appear_after_pair_count=3,
                duplicate_devices=True,
            ),
            MockDeviceScenario(
                "22:33:44:55:66:77",
                name="テスト用 COMなし機器",
                com_port="",
                appear_after_pair_count=None,
            ),
        ]

    @staticmethod
    def _com_port_for(scenario: MockDeviceScenario) -> ComPortInfo:
        compact = normalize_address(scenario.address).replace(":", "")
        return ComPortInfo(
            scenario.com_port,
            name=scenario.com_port,
            description=f"Standard Serial over Bluetooth link ({scenario.name})",
            hwid=rf"BTHENUM\{{00001101-0000-1000-8000-00805F9B34FB}}\7&MOCK&0&{compact}_C00000003",
            source="mock",
        )
