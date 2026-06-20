import unittest
from types import MethodType, SimpleNamespace

from bluetooth_assistant.app import (
    BluetoothAssistantApp,
    build_com_port_display_rows,
    build_device_display_rows,
    devices_with_manual_devices,
    format_com_port_summary,
    format_status_text,
    manual_device_from_address,
    retry_config_from_values,
    scan_progress_signature,
    timeout_multiplier_from_seconds,
    window_title_for_mode,
)
from bluetooth_assistant.models import BluetoothDevice, ComPortInfo


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

    def test_retry_config_from_values_uses_bounded_ui_values(self):
        config = retry_config_from_values(4, 1, 2, True)

        self.assertEqual(config.max_attempts, 4)
        self.assertEqual(config.inquiry_timeout_multiplier, 2)
        self.assertEqual(config.com_wait_seconds, 3)
        self.assertTrue(config.unpair_before_each_attempt)
        self.assertTrue(config.enable_serial_service)

    def test_retry_config_from_values_single_attempt_for_manual_connect(self):
        config = retry_config_from_values(20, 10, 45, False, single_attempt=True)

        self.assertEqual(config.max_attempts, 1)
        self.assertEqual(config.inquiry_timeout_multiplier, 8)
        self.assertEqual(config.com_wait_seconds, 45)
        self.assertFalse(config.enable_serial_service)

    def test_retry_config_from_values_falls_back_for_invalid_values(self):
        config = retry_config_from_values("invalid", "invalid", "invalid", True)

        self.assertEqual(config.max_attempts, 5)
        self.assertEqual(config.inquiry_timeout_multiplier, 8)
        self.assertEqual(config.com_wait_seconds, 20)

    def test_manual_device_from_address_normalizes_mac(self):
        device = manual_device_from_address("aabb.ccdd-eeff")

        self.assertEqual(device.address, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(device.name, "手入力")
        self.assertTrue(device.remembered)

    def test_manual_device_from_address_rejects_invalid_mac(self):
        with self.assertRaises(ValueError):
            manual_device_from_address("not-a-mac")

    def test_devices_with_manual_devices_keeps_manual_after_scan(self):
        manual = manual_device_from_address("AA:BB:CC:DD:EE:FF")
        scanned = [BluetoothDevice("11:22:33:44:55:66", name="Scanned")]

        merged = devices_with_manual_devices(scanned, {manual.address: manual})

        self.assertEqual(
            {device.address for device in merged},
            {"AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"},
        )

    def test_devices_with_manual_devices_keeps_same_mac_rows(self):
        manual = manual_device_from_address("AA:BB:CC:DD:EE:FF")
        scanned = [BluetoothDevice("AA:BB:CC:DD:EE:FF", name="Scanned Name", authenticated=True)]

        merged = devices_with_manual_devices(scanned, {manual.address: manual})

        self.assertEqual(len(merged), 2)
        self.assertEqual([device.address for device in merged], ["AA:BB:CC:DD:EE:FF", "AA:BB:CC:DD:EE:FF"])
        self.assertEqual({device.name for device in merged}, {"Scanned Name", "手入力"})

    def test_build_device_display_rows_scores_and_numbers_duplicate_mac_rows(self):
        devices = [
            BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-NO-COM"),
            BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-COM-SPP"),
        ]
        ports = [
            ComPortInfo(
                "COM12",
                hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}\\7&MOCK&0&AABBCCDDEEFF",
            )
        ]

        rows = build_device_display_rows(devices, ports)

        self.assertEqual(len(rows), 2)
        self.assertEqual({row.same_address_count for row in rows}, {2})
        self.assertEqual({row.row_id for row in rows}, {"AA:BB:CC:DD:EE:FF#1", "AA:BB:CC:DD:EE:FF#2"})
        self.assertEqual(rows[0].device.name, "BT-COM-SPP")

    def test_build_com_port_display_rows_sorts_com_numbers(self):
        ports = [
            ComPortInfo("COM10", description="ten", source="pnp"),
            ComPortInfo("COM3", description="three", source="wmi"),
            ComPortInfo("COM7", description="seven", source="wmi+pnp"),
        ]

        rows = build_com_port_display_rows(ports)

        self.assertEqual([row[0] for row in rows], ["COM3", "COM7", "COM10"])
        self.assertEqual(rows[0], ("COM3", "three", "wmi"))

    def test_format_com_port_summary_lists_current_ports(self):
        ports = [
            ComPortInfo("COM4", description="USB"),
            ComPortInfo("COM7", description="Bluetooth"),
        ]

        self.assertEqual(format_com_port_summary([]), "現在のCOM: 0件")
        self.assertEqual(format_com_port_summary(ports), "現在のCOM: 2件（COM4, COM7）")

    def test_scan_progress_signature_counts_duplicate_candidates(self):
        devices = [
            BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-COM"),
            BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-COM"),
            BluetoothDevice("11:22:33:44:55:66", name="BT-NO-COM", class_of_device=0x001F00),
        ]

        signature = scan_progress_signature(devices)

        self.assertEqual(
            signature,
            (
                ("11:22:33:44:55:66", "BT-NO-COM", 0x001F00, 1),
                ("AA:BB:CC:DD:EE:FF", "BT-COM", 0, 2),
            ),
        )

    def test_clear_scan_results_for_new_scan_removes_previous_rows(self):
        class FakeTree:
            def __init__(self) -> None:
                self.children = ["AA:BB:CC:DD:EE:FF#1"]
                self.selected = ["AA:BB:CC:DD:EE:FF#1"]
                self.removed_selection: tuple[str, ...] = ()
                self.deleted_rows: tuple[str, ...] = ()

            def selection(self) -> tuple[str, ...]:
                return tuple(self.selected)

            def selection_remove(self, *items: str) -> None:
                self.removed_selection = items
                self.selected = [item for item in self.selected if item not in items]

            def delete(self, *items: str) -> None:
                self.deleted_rows = items
                self.children = [item for item in self.children if item not in items]

            def get_children(self) -> tuple[str, ...]:
                return tuple(self.children)

        class FakeVar:
            def __init__(self) -> None:
                self.value = ""

            def set(self, value: str) -> None:
                self.value = value

        fake_app = SimpleNamespace(
            _devices={"AA:BB:CC:DD:EE:FF#1": BluetoothDevice("AA:BB:CC:DD:EE:FF")},
            _same_address_count_by_row={"AA:BB:CC:DD:EE:FF#1": 1},
            _last_scanned_devices=[BluetoothDevice("AA:BB:CC:DD:EE:FF")],
            _checked_rows={"AA:BB:CC:DD:EE:FF#1"},
            _run_status_by_address={"AA:BB:CC:DD:EE:FF": "成功"},
            tree=FakeTree(),
            detail_var=FakeVar(),
        )
        fake_app._selected_device = MethodType(BluetoothAssistantApp._selected_device, fake_app)
        fake_app._update_selection_detail = MethodType(BluetoothAssistantApp._update_selection_detail, fake_app)

        BluetoothAssistantApp._clear_scan_results_for_new_scan(fake_app)

        self.assertEqual(fake_app._devices, {})
        self.assertEqual(fake_app._same_address_count_by_row, {})
        self.assertEqual(fake_app._last_scanned_devices, [])
        self.assertEqual(fake_app._checked_rows, set())
        self.assertEqual(fake_app._run_status_by_address, {})
        self.assertEqual(fake_app.tree.removed_selection, ("AA:BB:CC:DD:EE:FF#1",))
        self.assertEqual(fake_app.tree.deleted_rows, ("AA:BB:CC:DD:EE:FF#1",))
        self.assertEqual(fake_app.tree.get_children(), ())
        self.assertIn("COM候補の点数", fake_app.detail_var.value)
