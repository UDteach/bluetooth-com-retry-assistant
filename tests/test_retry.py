import threading
import unittest

from bluetooth_assistant.models import BluetoothDevice, ComPortInfo, OperationResult
from bluetooth_assistant.retry import PairingRetrier, RetryConfig


class FakeBluetoothBackend:
    def __init__(self, appear_after_pair_count=1):
        self.appear_after_pair_count = appear_after_pair_count
        self.pair_count = 0
        self.unpair_count = 0
        self.devices = [
            BluetoothDevice("AA:BB:CC:DD:EE:FF", name="Device"),
            BluetoothDevice("aabbccddeeff", name="Device Duplicate"),
        ]

    def list_devices(self, *, issue_inquiry=True, timeout_multiplier=8):
        return self.devices

    def pair(self, address):
        self.pair_count += 1
        return OperationResult(True, f"pair {self.pair_count}")

    def unpair(self, address):
        self.unpair_count += 1
        return OperationResult(True, f"unpair {self.unpair_count}")

    def enable_serial_service(self, address):
        return OperationResult(True, "service enabled")

    def list_com_ports(self):
        if self.pair_count >= self.appear_after_pair_count:
            return [ComPortInfo("COM12", hwid=r"BTHENUM\AABBCCDDEEFF_C00000003")]
        return []


class RetryTests(unittest.TestCase):
    def test_retry_until_mock_com_port_appears(self):
        backend = FakeBluetoothBackend(appear_after_pair_count=2)
        events = []
        retrier = PairingRetrier(backend, sleeper=lambda _seconds: None)

        outcome = retrier.run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=3, com_wait_seconds=0, settle_seconds=0),
            events.append,
        )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(outcome.ports[0].device, "COM12")
        self.assertEqual(backend.pair_count, 2)
        self.assertGreaterEqual(backend.unpair_count, 1)
        self.assertIn("success", [event.stage for event in events])

    def test_existing_mock_com_port_short_circuits(self):
        backend = FakeBluetoothBackend(appear_after_pair_count=0)
        retrier = PairingRetrier(backend, sleeper=lambda _seconds: None)

        outcome = retrier.run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=3),
        )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.attempts, 0)
        self.assertEqual(backend.pair_count, 0)

    def test_stop_event_exits_before_pairing(self):
        backend = FakeBluetoothBackend(appear_after_pair_count=10)
        stop_event = threading.Event()
        stop_event.set()

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=3),
            stop_event=stop_event,
        )

        self.assertFalse(outcome.success)
        self.assertTrue(outcome.stopped)
        self.assertEqual(backend.pair_count, 0)


if __name__ == "__main__":
    unittest.main()
