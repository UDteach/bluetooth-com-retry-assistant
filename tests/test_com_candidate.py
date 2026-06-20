import unittest

from bluetooth_assistant.com_candidate import assess_com_candidate
from bluetooth_assistant.models import BluetoothDevice, ComPortInfo


class ComCandidateTests(unittest.TestCase):
    def test_existing_matching_port_is_com_available(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="Unknown")
        ports = [
            ComPortInfo(
                "COM12",
                hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}\\7&MOCK&0&AABBCCDDEEFF",
            )
        ]

        assessment = assess_com_candidate(device, ports)

        self.assertEqual(assessment.label, "COMあり")
        self.assertEqual(assessment.icon, "✓")
        self.assertEqual(assessment.display_label, "✓ COMあり")
        self.assertGreaterEqual(assessment.score, 100)

    def test_spp_name_is_high_candidate(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-COM-MOCK")

        assessment = assess_com_candidate(device, [])

        self.assertEqual(assessment.label, "COM候補 高")
        self.assertEqual(assessment.icon, "▲")
        self.assertIn("名前にSPP/Serial/COM系のヒントがあります", assessment.reasons)

    def test_no_com_name_is_low_candidate(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-NO-COM-MOCK")

        assessment = assess_com_candidate(device, [])

        self.assertEqual(assessment.label, "COM候補 低")
        self.assertEqual(assessment.icon, "×")
        self.assertIn("名前にCOMが出にくいヒントがあります", assessment.reasons)

    def test_dfu_no_com_name_stays_low_com_candidate(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-DFU-NO-COM-MOCK")

        assessment = assess_com_candidate(device, [])

        self.assertLess(assessment.score, 10)

    def test_same_address_count_adds_duplicate_reason(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="Unknown")

        assessment = assess_com_candidate(device, [], same_address_count=2)

        self.assertIn("同じMACが2件見えています", assessment.reasons)


if __name__ == "__main__":
    unittest.main()
