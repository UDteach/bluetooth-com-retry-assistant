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
        self.assertGreaterEqual(assessment.score, 100)

    def test_spp_name_is_high_candidate(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-COM-MOCK")

        assessment = assess_com_candidate(device, [])

        self.assertEqual(assessment.label, "COM候補 高")
        self.assertIn("名前にSPP/Serial/COM系のヒントがあります", assessment.reasons)

    def test_no_com_name_is_low_candidate(self):
        device = BluetoothDevice("AA:BB:CC:DD:EE:FF", name="BT-NO-COM-MOCK")

        assessment = assess_com_candidate(device, [])

        self.assertEqual(assessment.label, "COM候補 低")
        self.assertIn("名前にCOMが出にくいヒントがあります", assessment.reasons)


if __name__ == "__main__":
    unittest.main()
