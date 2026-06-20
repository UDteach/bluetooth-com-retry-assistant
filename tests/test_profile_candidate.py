import unittest

from bluetooth_assistant.models import BluetoothDevice, ComPortInfo
from bluetooth_assistant.profile_candidate import (
    NORDIC_SECURE_DFU_SERVICE_UUID,
    SPP_SERVICE_UUID,
    assess_profile_candidate,
)


class ProfileCandidateTests(unittest.TestCase):
    def test_matching_com_port_marks_spp_com(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="Unknown")
        ports = [
            ComPortInfo(
                "COM12",
                hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}\\7&MOCK&0&AABBCCDDEEFF",
            )
        ]

        assessment = assess_profile_candidate(device, ports)

        self.assertEqual(assessment.label, "SPP/COM")
        self.assertEqual(assessment.icon, "✓")
        self.assertEqual(assessment.profile, "SPP/RFCOMM")
        self.assertFalse(assessment.firmware_candidate)

    def test_spp_service_uuid_marks_spp_candidate(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="Sensor", service_uuids=(SPP_SERVICE_UUID,))

        assessment = assess_profile_candidate(device, [])

        self.assertEqual(assessment.label, "SPP/COM候補")
        self.assertGreaterEqual(assessment.score, 60)
        self.assertIn("Serial Port ProfileのUUID 0x1101 が見えています", assessment.reasons)

    def test_com_name_without_negative_hint_marks_spp_candidate(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-COM-METER")

        assessment = assess_profile_candidate(device, [])

        self.assertEqual(assessment.label, "SPP/COM候補")
        self.assertIn("名前にCOM系のヒントがあります", assessment.reasons)

    def test_dfu_service_uuid_marks_firmware_candidate(self):
        device = BluetoothDevice(
            "AA:BB:CC:DD:EE:FF",
            name="Smart Meter",
            service_uuids=(NORDIC_SECURE_DFU_SERVICE_UUID,),
        )

        assessment = assess_profile_candidate(device, [])

        self.assertEqual(assessment.label, "FW/DFU候補")
        self.assertEqual(assessment.profile, "BLE GATT/DFU")
        self.assertTrue(assessment.firmware_candidate)
        self.assertIn("Nordic Secure DFUのUUID 0xFE59 が見えています", assessment.reasons)

    def test_firmware_name_with_spp_marks_fw_com_candidate(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="METER-SPP-FW-UPDATE")

        assessment = assess_profile_candidate(device, [])

        self.assertEqual(assessment.label, "FW/COM候補")
        self.assertEqual(assessment.profile, "SPP/RFCOMM")
        self.assertTrue(assessment.firmware_candidate)

    def test_ble_name_marks_gatt_candidate_without_com(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="SmartMeter BLE")

        assessment = assess_profile_candidate(device, [])

        self.assertEqual(assessment.label, "BLE GATT候補")
        self.assertEqual(assessment.icon, "◇")

    def test_no_com_name_does_not_become_spp_from_com_word(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-NO-COM-MOCK")

        assessment = assess_profile_candidate(device, [])

        self.assertEqual(assessment.label, "不明")
        self.assertIn("名前にCOMが出にくいヒントがあります", assessment.reasons)


if __name__ == "__main__":
    unittest.main()
