import re
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from bluetooth_assistant import __version__
from bluetooth_assistant.app import main


class VersionTests(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        match = re.search(r'^version = "([^"]+)"$', pyproject.read_text(encoding="utf-8"), re.MULTILINE)

        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)

    def test_app_version_argument_prints_package_version(self):
        output = StringIO()

        with redirect_stdout(output), self.assertRaises(SystemExit) as caught:
            main(["--version"])

        self.assertEqual(caught.exception.code, 0)
        self.assertIn(__version__, output.getvalue())


if __name__ == "__main__":
    unittest.main()
