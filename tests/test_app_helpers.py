import unittest

from bluetooth_assistant.app import (
    format_status_text,
    manual_device_from_address,
    merge_with_manual_devices,
    timeout_multiplier_from_seconds,
    window_title_for_mode,
)
from bluetooth_assistant.models import BluetoothDevice


class AppHelperTests(unittest.TestCase):
    def test_timeout_multiplier_from_seconds_clamps_minimum(self):
        self.assertEqual(timeout_multiplier_from_seconds(0), 1)
        self.assertEqual(timeout_multiplier_from_seconds(1), 1)

    def test_timeout_multiplier_from_seconds_uses_inquiry_units(self):
        self.assertEqual(timeout_multiplier_from_seconds(2), 2)
        self.assertEqual(timeout_multiplier_from_seconds(10), 8)

    def test_timeout_multiplier_from_seconds_clamps_maximum(self):
        self.assertEqual(timeout_multiplier_from_seconds(999), 48)

    def test_window_title_shows_test_mode_only_for_mock(self):
        self.assertEqual(window_title_for_mode(False), "BluetoothAssistant")
        self.assertEqual(window_title_for_mode(True), "BluetoothAssistant - テストモード")

    def test_status_text_shows_test_mode_only_for_mock(self):
        self.assertEqual(format_status_text("待機中"), "状態: 待機中")
        self.assertEqual(
            format_status_text("待機中", mock_mode=True),
            "状態: テストモード / 待機中",
        )

    def test_manual_device_from_address_normalizes_mac(self):
        device = manual_device_from_address("aabb.ccdd-eeff")

        self.assertEqual(device.address, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(device.name, "手入力")
        self.assertTrue(device.remembered)

    def test_manual_device_from_address_rejects_invalid_mac(self):
        with self.assertRaises(ValueError):
            manual_device_from_address("not-a-mac")

    def test_merge_with_manual_devices_keeps_manual_after_scan(self):
        manual = manual_device_from_address("AA:BB:CC:DD:EE:FF")
        scanned = [BluetoothDevice("11:22:33:44:55:66", name="Scanned")]

        merged = merge_with_manual_devices(scanned, {manual.address: manual})

        self.assertEqual(
            {device.address for device in merged},
            {"AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"},
        )

    def test_merge_with_manual_devices_merges_same_mac_names(self):
        manual = manual_device_from_address("AA:BB:CC:DD:EE:FF")
        scanned = [BluetoothDevice("AA:BB:CC:DD:EE:FF", name="Scanned Name", authenticated=True)]

        merged = merge_with_manual_devices(scanned, {manual.address: manual})

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].address, "AA:BB:CC:DD:EE:FF")
        self.assertTrue(merged[0].authenticated)
        self.assertIn("Scanned Name", merged[0].raw_names)
        self.assertIn("手入力", merged[0].raw_names)
