import io
import json
import unittest
from contextlib import redirect_stdout

from bluetooth_assistant.diagnostics import (
    main,
    run_hardware_expectations,
    run_hardware_pairing_test,
    run_mock_retry,
    run_safe_diagnostics,
)
from bluetooth_assistant.mock_backend import MockBluetoothBackend, MockDeviceScenario
from bluetooth_assistant.models import BluetoothDevice, ComPortInfo


class DiagnosticsTests(unittest.TestCase):
    def test_safe_diagnostics_runs_without_pairing_or_unpairing(self):
        results = run_safe_diagnostics(scan_bluetooth=False)
        names = [result.name for result in results]

        self.assertIn("python", names)
        self.assertIn("tkinter_import", names)
        self.assertIn("com_ports", names)
        self.assertIn("windows_bluetooth_backend", names)

    def test_mock_retry_diagnostic_succeeds(self):
        results = run_mock_retry()

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok)
        self.assertEqual(results[0].data["pair_count"], 2)
        self.assertEqual(results[0].data["unpair_count"], 2)
        self.assertEqual(results[0].data["slow_device_pair_count"], 0)
        self.assertEqual(
            [entry[0] for entry in results[0].data["history"]],
            ["unpair", "pair", "service", "unpair", "pair", "service"],
        )

    def test_mock_retry_diagnostic_accepts_custom_com_port(self):
        results = run_mock_retry(target_com_port="COM98", appear_after_pair_count=1)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok)
        self.assertEqual(results[0].data["target_com_port"], "COM98")
        self.assertEqual(results[0].data["ports"][0]["device"], "COM98")

    def test_json_main_exit_code_for_mock_retry(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(["--json", "--mock-retry"])

        self.assertIn(code, (0, 1))
        payload = json.loads(stream.getvalue())
        self.assertTrue(any(result["name"] == "mock_retry" for result in payload))

    def test_hardware_expectations_match_device_and_com_port(self):
        results = run_hardware_expectations(
            expect_device_name="BT-COM",
            expect_address="AA:BB:CC:DD:EE:FF",
            expect_com_port="COM7",
            device_loader=lambda: [BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-COM-MOCK")],
            port_loader=lambda: [ComPortInfo("COM7", name="COM7", hwid="BTHENUM\\MOCK\\AABBCCDDEEFF")],
        )
        by_name = {result.name: result for result in results}

        self.assertTrue(by_name["hardware_wait"].ok)
        self.assertTrue(by_name["expect_device_name"].ok)
        self.assertTrue(by_name["expect_device_address"].ok)
        self.assertTrue(by_name["expect_com_port"].ok)
        self.assertTrue(by_name["hardware_com_candidates"].ok)
        self.assertEqual(by_name["hardware_com_candidates"].data[0]["label"], "COMあり")

    def test_hardware_expectations_report_missing_device(self):
        results = run_hardware_expectations(
            expect_device_name="BT-COM-MOCK",
            device_loader=lambda: [BluetoothDevice("AA:BB:CC:DD:EE:FF", name="Other")],
            port_loader=lambda: [],
        )
        by_name = {result.name: result for result in results}

        self.assertFalse(by_name["hardware_wait"].ok)
        self.assertFalse(by_name["expect_device_name"].ok)

    def test_hardware_expectations_can_wait_until_device_appears(self):
        calls = {"count": 0}

        def device_loader():
            calls["count"] += 1
            if calls["count"] == 1:
                return []
            return [BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-COM-MOCK")]

        sleeps = []
        results = run_hardware_expectations(
            expect_device_name="BT-COM-MOCK",
            wait_seconds=5,
            poll_seconds=0.5,
            device_loader=device_loader,
            port_loader=lambda: [],
            sleeper=sleeps.append,
        )
        by_name = {result.name: result for result in results}

        self.assertTrue(by_name["hardware_wait"].ok)
        self.assertEqual(calls["count"], 2)
        self.assertEqual(sleeps, [0.5])

    def test_hardware_pairing_test_requires_target(self):
        results = run_hardware_pairing_test(backend=MockBluetoothBackend(), sleeper=lambda _seconds: None)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].name, "hardware_pairing_guard")

    def test_hardware_pairing_test_pairs_and_finds_com(self):
        backend = MockBluetoothBackend(
            scenarios=[
                MockDeviceScenario(
                    "AA:BB:CC:DD:EE:FF",
                    "BT-COM-MOCK",
                    "COM12",
                    appear_after_pair_count=1,
                )
            ]
        )

        results = run_hardware_pairing_test(
            target_name="BT-COM-MOCK",
            com_wait_seconds=0,
            poll_seconds=0.5,
            backend=backend,
            sleeper=lambda _seconds: None,
        )
        by_name = {result.name: result for result in results}

        self.assertTrue(by_name["hardware_pairing_resolve_target"].ok)
        self.assertTrue(by_name["hardware_pairing_outcome"].ok)
        self.assertTrue(by_name["hardware_pairing_windows_registered"].ok)
        self.assertTrue(by_name["hardware_pairing_com_after"].ok)
        self.assertEqual(by_name["hardware_pairing_com_after"].data["matching_ports"][0]["device"], "COM12")

    def test_hardware_pairing_test_rejects_ambiguous_name(self):
        backend = MockBluetoothBackend(
            scenarios=[
                MockDeviceScenario("AA:BB:CC:DD:EE:FF", "BT-COM-MOCK", "COM12"),
                MockDeviceScenario("11:22:33:44:55:66", "BT-COM-MOCK 2", "COM13"),
            ]
        )

        results = run_hardware_pairing_test(
            target_name="BT-COM-MOCK",
            backend=backend,
            sleeper=lambda _seconds: None,
        )
        by_name = {result.name: result for result in results}

        self.assertFalse(by_name["hardware_pairing_resolve_target"].ok)
        self.assertNotIn("hardware_pairing_outcome", by_name)
