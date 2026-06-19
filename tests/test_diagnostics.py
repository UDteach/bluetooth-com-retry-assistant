import io
import json
import unittest
from contextlib import redirect_stdout

from bluetooth_assistant.diagnostics import main, run_mock_retry, run_safe_diagnostics


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

    def test_json_main_exit_code_for_mock_retry(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(["--json", "--mock-retry"])

        self.assertIn(code, (0, 1))
        payload = json.loads(stream.getvalue())
        self.assertTrue(any(result["name"] == "mock_retry" for result in payload))
