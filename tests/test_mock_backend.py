import unittest

from bluetooth_assistant.mock_backend import MockBluetoothBackend, MockDeviceScenario
from bluetooth_assistant.models import find_matching_ports


class MockBackendTests(unittest.TestCase):
    def test_scenario_counts_are_isolated_by_address(self):
        backend = MockBluetoothBackend(
            scenarios=[
                MockDeviceScenario("AA:BB:CC:DD:EE:FF", "Mock A", "COM10", appear_after_pair_count=1),
                MockDeviceScenario("11:22:33:44:55:66", "Mock B", "COM11", appear_after_pair_count=1),
            ]
        )

        backend.pair("AA:BB:CC:DD:EE:FF")
        backend.unpair("11:22:33:44:55:66")
        backend.enable_serial_service("11:22:33:44:55:66")

        self.assertEqual(backend.pair_count_for("AA:BB:CC:DD:EE:FF"), 1)
        self.assertEqual(backend.pair_count_for("11:22:33:44:55:66"), 0)
        self.assertEqual(backend.unpair_count_for("AA:BB:CC:DD:EE:FF"), 0)
        self.assertEqual(backend.unpair_count_for("11:22:33:44:55:66"), 1)
        self.assertEqual(backend.service_count_for("AA:BB:CC:DD:EE:FF"), 0)
        self.assertEqual(backend.service_count_for("11:22:33:44:55:66"), 1)

        ports = backend.list_com_ports()
        self.assertEqual([port.device for port in find_matching_ports("AA:BB:CC:DD:EE:FF", ports)], ["COM10"])
        self.assertEqual(find_matching_ports("11:22:33:44:55:66", ports), [])

    def test_unknown_mac_scenario_does_not_change_existing_target(self):
        backend = MockBluetoothBackend(appear_after_pair_count=1)

        backend.pair("33:44:55:66:77:88")
        backend.enable_serial_service("33:44:55:66:77:88")

        self.assertEqual(backend.pair_count, 0)
        self.assertEqual(backend.service_count, 0)
        self.assertEqual(backend.pair_count_for("33:44:55:66:77:88"), 1)
        self.assertEqual(backend.service_count_for("33:44:55:66:77:88"), 1)

        ports = backend.list_com_ports()
        self.assertEqual(find_matching_ports("AA:BB:CC:DD:EE:FF", ports), [])
        self.assertEqual([port.device for port in find_matching_ports("33:44:55:66:77:88", ports)], [])

    def test_duplicate_mock_devices_are_merged_by_mac(self):
        backend = MockBluetoothBackend()

        devices = backend.list_devices()
        target = next(device for device in devices if device.address == "AA:BB:CC:DD:EE:FF")
        slow = next(device for device in devices if device.address == "11:22:33:44:55:66")

        self.assertEqual(target.raw_count, 2)
        self.assertEqual(slow.raw_count, 2)
        self.assertEqual(len({device.address for device in devices}), len(devices))


if __name__ == "__main__":
    unittest.main()
