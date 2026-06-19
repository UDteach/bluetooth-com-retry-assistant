from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Callable, Protocol

from .models import BluetoothDevice, ComPortInfo, OperationResult, find_matching_ports, normalize_address


class BluetoothBackend(Protocol):
    def list_devices(self, *, issue_inquiry: bool = True, timeout_multiplier: int = 8) -> list[BluetoothDevice]:
        ...

    def pair(self, address: str) -> OperationResult:
        ...

    def unpair(self, address: str) -> OperationResult:
        ...

    def enable_serial_service(self, address: str) -> OperationResult:
        ...

    def list_com_ports(self) -> list[ComPortInfo]:
        ...


@dataclass(slots=True)
class RetryConfig:
    max_attempts: int = 5
    inquiry_timeout_multiplier: int = 8
    com_wait_seconds: float = 20.0
    poll_interval_seconds: float = 1.5
    settle_seconds: float = 2.0
    clean_before_first_attempt: bool = False
    unpair_between_attempts: bool = True
    enable_serial_service: bool = True


@dataclass(slots=True)
class RetryEvent:
    stage: str
    message: str
    attempt: int = 0
    ports: list[ComPortInfo] = field(default_factory=list)


@dataclass(slots=True)
class RetryOutcome:
    success: bool
    stopped: bool
    attempts: int
    ports: list[ComPortInfo] = field(default_factory=list)
    message: str = ""


EventCallback = Callable[[RetryEvent], None]


class PairingRetrier:
    def __init__(self, backend: BluetoothBackend, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.backend = backend
        self._sleep = sleeper

    def run(
        self,
        address: str,
        config: RetryConfig,
        on_event: EventCallback | None = None,
        stop_event: threading.Event | None = None,
    ) -> RetryOutcome:
        target_address = normalize_address(address)
        stop_event = stop_event or threading.Event()
        emit = on_event or (lambda event: None)

        initial_ports = find_matching_ports(target_address, self.backend.list_com_ports())
        if initial_ports:
            message = f"既存の COM ポートを検出しました: {_format_ports(initial_ports)}"
            emit(RetryEvent("success", message, ports=initial_ports))
            return RetryOutcome(True, False, 0, initial_ports, message)

        attempts = max(1, int(config.max_attempts))
        for attempt in range(1, attempts + 1):
            if stop_event.is_set():
                return RetryOutcome(False, True, attempt - 1, message="停止しました")

            emit(RetryEvent("scan", "Bluetooth 一覧を更新しています", attempt))
            try:
                self.backend.list_devices(
                    issue_inquiry=True,
                    timeout_multiplier=config.inquiry_timeout_multiplier,
                )
            except Exception as exc:  # pragma: no cover - UI/logging boundary
                emit(RetryEvent("warning", f"一覧更新に失敗しました: {exc}", attempt))

            should_clean = config.clean_before_first_attempt or attempt > 1
            if should_clean:
                emit(RetryEvent("unpair", "既存のペアリングを解除しています", attempt))
                unpair_result = self.backend.unpair(target_address)
                emit(RetryEvent("unpair", unpair_result.message or "解除を実行しました", attempt))
                if config.settle_seconds > 0:
                    self._sleep(config.settle_seconds)

            emit(RetryEvent("pair", "ペアリングを開始します", attempt))
            pair_result = self.backend.pair(target_address)
            emit(RetryEvent("pair", pair_result.message or "ペアリング処理が戻りました", attempt))
            if not pair_result.ok:
                if attempt < attempts and config.unpair_between_attempts:
                    self._cleanup_after_failed_attempt(target_address, attempt, emit, config)
                continue

            if config.enable_serial_service:
                emit(RetryEvent("service", "Serial Port サービスの有効化を試みます", attempt))
                service_result = self.backend.enable_serial_service(target_address)
                emit(RetryEvent("service", service_result.message or "サービス有効化処理が戻りました", attempt))

            ports = self._wait_for_ports(target_address, attempt, config, emit, stop_event)
            if ports:
                message = f"COM ポートを検出しました: {_format_ports(ports)}"
                emit(RetryEvent("success", message, attempt, ports))
                return RetryOutcome(True, False, attempt, ports, message)

            if stop_event.is_set():
                return RetryOutcome(False, True, attempt, message="停止しました")

            emit(RetryEvent("retry", "COM ポート未検出のため次の試行へ進みます", attempt))
            if attempt < attempts and config.unpair_between_attempts:
                self._cleanup_after_failed_attempt(target_address, attempt, emit, config)

        message = "最大試行回数まで実行しましたが、対象 MAC の COM ポートは見つかりませんでした"
        emit(RetryEvent("failed", message, attempts))
        return RetryOutcome(False, False, attempts, message=message)

    def _wait_for_ports(
        self,
        address: str,
        attempt: int,
        config: RetryConfig,
        emit: EventCallback,
        stop_event: threading.Event,
    ) -> list[ComPortInfo]:
        deadline = time.monotonic() + max(0.0, config.com_wait_seconds)
        while True:
            ports = find_matching_ports(address, self.backend.list_com_ports())
            if ports:
                return ports
            if stop_event.is_set() or time.monotonic() >= deadline:
                return []
            emit(RetryEvent("wait", "COM ポートを待っています", attempt))
            self._sleep(max(0.1, config.poll_interval_seconds))

    def _cleanup_after_failed_attempt(
        self,
        address: str,
        attempt: int,
        emit: EventCallback,
        config: RetryConfig,
    ) -> None:
        emit(RetryEvent("unpair", "次の試行のため解除します", attempt))
        result = self.backend.unpair(address)
        emit(RetryEvent("unpair", result.message or "解除を実行しました", attempt))
        if config.settle_seconds > 0:
            self._sleep(config.settle_seconds)


def _format_ports(ports: list[ComPortInfo]) -> str:
    return ", ".join(port.device for port in ports if port.device) or "unknown"
