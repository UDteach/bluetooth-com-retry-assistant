import unittest
from pathlib import Path

from bluetooth_assistant.profile_candidate import NORDIC_SECURE_DFU_SERVICE_UUID, SPP_SERVICE_UUID

ROOT = Path(__file__).resolve().parents[1]


def read_sketch(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class HardwareSketchTests(unittest.TestCase):
    def test_spp_mock_exposes_classic_spp_identity(self):
        sketch = read_sketch("hardware/esp32_spp_mock/esp32_spp_mock.ino")

        self.assertIn("BluetoothSerial", sketch)
        self.assertIn("CONFIG_BT_SPP_ENABLED", sketch)
        self.assertIn("BT-COM-MOCK", sketch)

    def test_no_com_mock_does_not_start_spp(self):
        sketch = read_sketch("hardware/esp32_no_com_mock/esp32_no_com_mock.ino")

        self.assertIn("BT-NO-COM-MOCK", sketch)
        self.assertNotIn("BluetoothSerial", sketch)
        self.assertNotIn(SPP_SERVICE_UUID, sketch)

    def test_classic_dfu_hint_mock_is_visible_but_not_spp(self):
        sketch = read_sketch("hardware/esp32_classic_dfu_hint_mock/esp32_classic_dfu_hint_mock.ino")

        self.assertIn("BT-DFU-NO-COM-MOCK", sketch)
        self.assertIn("esp_bt_gap_set_scan_mode", sketch)
        self.assertNotIn("BluetoothSerial", sketch)
        self.assertNotIn(SPP_SERVICE_UUID, sketch)

    def test_ble_dfu_mock_advertises_secure_dfu_without_spp(self):
        sketch = read_sketch("hardware/esp32_ble_dfu_mock/esp32_ble_dfu_mock.ino")

        self.assertIn("BT-BLE-DFU-MOCK", sketch)
        self.assertIn(NORDIC_SECURE_DFU_SERVICE_UUID, sketch)
        self.assertIn("8EC90001-F315-4F60-9FB8-838830DAEA50", sketch)
        self.assertIn("8EC90002-F315-4F60-9FB8-838830DAEA50", sketch)
        self.assertIn("8EC90003-F315-4F60-9FB8-838830DAEA50", sketch)
        self.assertIn("BLEDevice::startAdvertising", sketch)
        self.assertNotIn("BluetoothSerial", sketch)
        self.assertNotIn("CONFIG_BT_SPP_ENABLED", sketch)


if __name__ == "__main__":
    unittest.main()
