import unittest

from bluetooth_assistant.app import timeout_multiplier_from_seconds


class AppHelperTests(unittest.TestCase):
    def test_timeout_multiplier_from_seconds_clamps_minimum(self):
        self.assertEqual(timeout_multiplier_from_seconds(0), 1)
        self.assertEqual(timeout_multiplier_from_seconds(1), 1)

    def test_timeout_multiplier_from_seconds_uses_inquiry_units(self):
        self.assertEqual(timeout_multiplier_from_seconds(2), 2)
        self.assertEqual(timeout_multiplier_from_seconds(10), 8)

    def test_timeout_multiplier_from_seconds_clamps_maximum(self):
        self.assertEqual(timeout_multiplier_from_seconds(999), 48)
