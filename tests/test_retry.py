import threading
import unittest

from bluetooth_assistant.mock_backend import MockBluetoothBackend
from bluetooth_assistant.models import OperationResult
from bluetooth_assistant.retry import PairingRetrier, RetryConfig


class RetryTests(unittest.TestCase):
    def test_retry_until_mock_com_port_appears(self):
        backend = MockBluetoothBackend(appear_after_pair_count=2)
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
        backend = MockBluetoothBackend(appear_after_pair_count=0)
        retrier = PairingRetrier(backend, sleeper=lambda _seconds: None)

        outcome = retrier.run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=3),
        )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.attempts, 0)
        self.assertEqual(backend.pair_count, 0)

    def test_stop_event_exits_before_pairing(self):
        backend = MockBluetoothBackend(appear_after_pair_count=10)
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

    def test_pair_failures_are_retried_and_cleaned(self):
        backend = MockBluetoothBackend(appear_after_pair_count=2, fail_pair_attempts={1})

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=3, com_wait_seconds=0, settle_seconds=0),
        )

        self.assertTrue(outcome.success)
        self.assertEqual(backend.pair_count, 2)
        self.assertEqual(backend.unpair_count, 1)

    def test_service_can_be_disabled(self):
        backend = MockBluetoothBackend(appear_after_pair_count=1)

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=1, com_wait_seconds=0, enable_serial_service=False),
        )

        self.assertTrue(outcome.success)
        self.assertEqual(backend.service_count, 0)

    def test_service_failure_does_not_stop_com_polling(self):
        backend = MockBluetoothBackend(
            appear_after_pair_count=1,
            service_result=OperationResult(False, "mock service missing", 1060),
        )

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=1, com_wait_seconds=0),
        )

        self.assertTrue(outcome.success)
        self.assertEqual(backend.service_count, 1)

    def test_stop_event_exits_during_com_wait(self):
        backend = MockBluetoothBackend(appear_after_pair_count=99)
        stop_event = threading.Event()

        def stop_on_sleep(_seconds):
            stop_event.set()

        outcome = PairingRetrier(backend, sleeper=stop_on_sleep).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=3, com_wait_seconds=30, poll_interval_seconds=0.1, settle_seconds=0),
            stop_event=stop_event,
        )

        self.assertFalse(outcome.success)
        self.assertTrue(outcome.stopped)


class ScanFailingBackend(MockBluetoothBackend):
    def list_devices(self, *, issue_inquiry=True, timeout_multiplier=8):
        raise RuntimeError("scan failed")


class NoPortBackend(MockBluetoothBackend):
    def list_com_ports(self):
        return []


class RetryFailureTests(unittest.TestCase):
    def test_scan_failure_is_logged_but_pairing_continues(self):
        backend = ScanFailingBackend(appear_after_pair_count=1)
        events = []

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=1, com_wait_seconds=0),
            events.append,
        )

        self.assertTrue(outcome.success)
        self.assertIn("warning", [event.stage for event in events])

    def test_failure_after_max_attempts(self):
        backend = NoPortBackend(appear_after_pair_count=99)

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=2, com_wait_seconds=0, settle_seconds=0),
        )

        self.assertFalse(outcome.success)
        self.assertFalse(outcome.stopped)
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(backend.pair_count, 2)


if __name__ == "__main__":
    unittest.main()
