import re
import unittest
from pathlib import Path

from bluetooth_assistant import __version__


class VersionTests(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        match = re.search(r'^version = "([^"]+)"$', pyproject.read_text(encoding="utf-8"), re.MULTILINE)

        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)


if __name__ == "__main__":
    unittest.main()
