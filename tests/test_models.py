import unittest

from bluetooth_assistant.models import (
    BluetoothDevice,
    ComPortInfo,
    address_in_text,
    find_matching_ports,
    merge_duplicate_devices,
    normalize_address,
)


class ModelTests(unittest.TestCase):
    def test_normalize_address_accepts_common_forms(self):
        self.assertEqual(normalize_address("aabbccddeeff"), "AA:BB:CC:DD:EE:FF")
        self.assertEqual(normalize_address("AA-BB-CC-DD-EE-FF"), "AA:BB:CC:DD:EE:FF")

    def test_merge_duplicate_devices_by_mac(self):
        devices = merge_duplicate_devices(
            [
                BluetoothDevice(
                    "AA:BB:CC:DD:EE:FF",
                    name="Sensor",
                    authenticated=False,
                    service_uuids=("0000180A-0000-1000-8000-00805F9B34FB",),
                ),
                BluetoothDevice(
                    "aabbccddeeff",
                    name="Sensor SPP",
                    authenticated=True,
                    connected=True,
                    service_uuids=("00001101-0000-1000-8000-00805F9B34FB",),
                ),
            ]
        )
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].address, "AA:BB:CC:DD:EE:FF")
        self.assertTrue(devices[0].authenticated)
        self.assertTrue(devices[0].connected)
        self.assertEqual(devices[0].raw_count, 2)
        self.assertIn("同一MAC 2件", devices[0].status_text)
        self.assertEqual(
            devices[0].service_uuids,
            (
                "0000180A-0000-1000-8000-00805F9B34FB",
                "00001101-0000-1000-8000-00805F9B34FB",
            ),
        )

    def test_address_matching_handles_pnp_device_id(self):
        text = r"BTHENUM\{00001101-0000-1000-8000-00805F9B34FB}\7&1D80ECD3&0&AABBCCDDEEFF_C00000003"
        self.assertTrue(address_in_text("AA:BB:CC:DD:EE:FF", text))

    def test_address_matching_handles_reversed_byte_order(self):
        text = r"BTHENUM\{00001101-0000-1000-8000-00805F9B34FB}\7&1D80ECD3&0&FFEEDDCCBBAA_C00000003"
        self.assertTrue(address_in_text("AA:BB:CC:DD:EE:FF", text))

    def test_address_matching_rejects_other_mac(self):
        text = r"BTHENUM\{00001101-0000-1000-8000-00805F9B34FB}\7&1D80ECD3&0&112233445566_C00000003"
        self.assertFalse(address_in_text("AA:BB:CC:DD:EE:FF", text))

    def test_invalid_address_raises(self):
        with self.assertRaises(ValueError):
            normalize_address("AA:BB")

    def test_find_matching_ports_filters_by_mac(self):
        ports = [
            ComPortInfo("COM4", description="Standard Serial over Bluetooth link", hwid="BTHENUM\\AABBCCDDEEFF"),
            ComPortInfo("COM5", description="Other", hwid="USB VID:PID=1234:5678"),
        ]
        self.assertEqual([port.device for port in find_matching_ports("AA:BB:CC:DD:EE:FF", ports)], ["COM4"])


if __name__ == "__main__":
    unittest.main()
