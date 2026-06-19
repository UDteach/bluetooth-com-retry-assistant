import threading
import unittest

from bluetooth_assistant.mock_backend import MockBluetoothBackend
from bluetooth_assistant.models import OperationResult, find_matching_ports
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
        self.assertEqual(backend.unpair_count, 2)
        self.assertIn("success", [event.stage for event in events])

    def test_unpair_happens_before_each_pair_attempt(self):
        backend = MockBluetoothBackend(appear_after_pair_count=3)

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=3, com_wait_seconds=0, settle_seconds=0),
        )

        self.assertTrue(outcome.success)
        self.assertEqual(
            [entry[0] for entry in backend.history if entry[0] in {"unpair", "pair"}],
            ["unpair", "pair", "unpair", "pair", "unpair", "pair"],
        )

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
        self.assertEqual(backend.unpair_count, 0)

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
        self.assertEqual(backend.unpair_count, 2)

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

    def test_multiple_mock_devices_are_matched_by_target_mac(self):
        backend = MockBluetoothBackend()

        first = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "11:22:33:44:55:66",
            RetryConfig(max_attempts=3, com_wait_seconds=0, settle_seconds=0),
        )

        self.assertTrue(first.success)
        self.assertEqual(first.ports[0].device, "COM13")
        self.assertEqual(backend.pair_count_for("11:22:33:44:55:66"), 3)
        self.assertEqual(backend.pair_count, 0)
        self.assertFalse(find_matching_ports("AA:BB:CC:DD:EE:FF", first.ports))

    def test_manual_unknown_mac_can_be_mocked(self):
        backend = MockBluetoothBackend()

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "33:44:55:66:77:88",
            RetryConfig(max_attempts=2, com_wait_seconds=0, settle_seconds=0),
        )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.ports[0].device, "COM23")
        self.assertEqual(backend.pair_count_for("33:44:55:66:77:88"), 2)

    def test_mock_target_com_port_can_be_configured(self):
        backend = MockBluetoothBackend(target_com_port="COM98", appear_after_pair_count=1)

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=1, com_wait_seconds=0, settle_seconds=0),
        )

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.ports[0].device, "COM98")


class ScanFailingBackend(MockBluetoothBackend):
    def list_devices(self, *, issue_inquiry=True, timeout_multiplier=8):
        raise RuntimeError("scan failed")


class NoPortBackend(MockBluetoothBackend):
    def list_com_ports(self):
        return []


class UnpairRaisingBackend(MockBluetoothBackend):
    def unpair(self, address):
        raise RuntimeError("unpair exploded")


class PairRaisingBackend(MockBluetoothBackend):
    def pair(self, address):
        raise RuntimeError("pair exploded")


class ServiceRaisingBackend(MockBluetoothBackend):
    def enable_serial_service(self, address):
        raise RuntimeError("service exploded")


class PortRaisingOnceBackend(MockBluetoothBackend):
    def __init__(self):
        super().__init__(appear_after_pair_count=1)
        self._raised = False

    def list_com_ports(self):
        if not self._raised:
            self._raised = True
            raise RuntimeError("ports exploded")
        return super().list_com_ports()


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

    def test_unpair_exception_is_logged_and_pairing_continues(self):
        backend = UnpairRaisingBackend(appear_after_pair_count=1)
        events = []

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=1, com_wait_seconds=0, settle_seconds=0),
            events.append,
        )

        self.assertTrue(outcome.success)
        self.assertIn("warning", [event.stage for event in events])
        self.assertEqual(backend.pair_count, 1)

    def test_pair_exception_is_logged_and_retried_until_failed(self):
        backend = PairRaisingBackend(appear_after_pair_count=1)
        events = []

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=2, com_wait_seconds=0, settle_seconds=0),
            events.append,
        )

        self.assertFalse(outcome.success)
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual([entry[0] for entry in backend.history], ["unpair", "unpair"])
        self.assertIn("warning", [event.stage for event in events])

    def test_service_exception_does_not_stop_com_polling(self):
        backend = ServiceRaisingBackend(appear_after_pair_count=1)
        events = []

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=1, com_wait_seconds=0, settle_seconds=0),
            events.append,
        )

        self.assertTrue(outcome.success)
        self.assertIn("warning", [event.stage for event in events])

    def test_com_port_exception_is_logged_and_retried(self):
        backend = PortRaisingOnceBackend()
        events = []

        outcome = PairingRetrier(backend, sleeper=lambda _seconds: None).run(
            "AA:BB:CC:DD:EE:FF",
            RetryConfig(max_attempts=1, com_wait_seconds=0, settle_seconds=0),
            events.append,
        )

        self.assertTrue(outcome.success)
        self.assertIn("warning", [event.stage for event in events])


if __name__ == "__main__":
    unittest.main()
