import json
import subprocess
import unittest
from unittest.mock import patch

from bluetooth_assistant.com_ports import (
    _dedupe_ports,
    _extract_com_name,
    _list_pnp_com_ports,
    _list_wmi_serial_ports,
    list_com_ports,
)
from bluetooth_assistant.models import ComPortInfo


class Completed:
    def __init__(self, stdout):
        self.stdout = stdout


class ComPortTests(unittest.TestCase):
    def test_dedupe_merges_pyserial_and_wmi_sources(self):
        ports = _dedupe_ports(
            [
                ComPortInfo("COM7", name="COM7", hwid=r"BTHENUM\AABBCCDDEEFF", source="pyserial"),
                ComPortInfo(
                    "COM7",
                    description="Standard Serial over Bluetooth link",
                    hwid=r"BTHENUM\AABBCCDDEEFF",
                    source="wmi",
                ),
            ]
        )

        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0].source, "pyserial+wmi")
        self.assertEqual(ports[0].description, "Standard Serial over Bluetooth link")

    def test_wmi_parser_accepts_single_object_json(self):
        payload = json.dumps(
            {
                "DeviceID": "COM9",
                "Name": "COM9",
                "Description": "Bluetooth Serial",
                "PNPDeviceID": r"BTHENUM\AABBCCDDEEFF",
            }
        )

        with patch("bluetooth_assistant.com_ports.os.name", "nt"), patch(
            "bluetooth_assistant.com_ports.subprocess.run",
            return_value=Completed(payload),
        ):
            ports = _list_wmi_serial_ports()

        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0].device, "COM9")
        self.assertEqual(ports[0].source, "wmi")

    def test_wmi_parser_accepts_array_json(self):
        payload = json.dumps(
            [
                {"DeviceID": "COM3", "Name": "COM3", "Description": "A", "PNPDeviceID": "ID1"},
                {"DeviceID": "COM4", "Name": "COM4", "Description": "B", "PNPDeviceID": "ID2"},
            ]
        )

        with patch("bluetooth_assistant.com_ports.os.name", "nt"), patch(
            "bluetooth_assistant.com_ports.subprocess.run",
            return_value=Completed(payload),
        ):
            ports = _list_wmi_serial_ports()

        self.assertEqual([port.device for port in ports], ["COM3", "COM4"])

    def test_wmi_parser_handles_invalid_json(self):
        with patch("bluetooth_assistant.com_ports.os.name", "nt"), patch(
            "bluetooth_assistant.com_ports.subprocess.run",
            return_value=Completed("not json"),
        ):
            self.assertEqual(_list_wmi_serial_ports(), [])

    def test_wmi_parser_handles_timeout(self):
        with patch("bluetooth_assistant.com_ports.os.name", "nt"), patch(
            "bluetooth_assistant.com_ports.subprocess.run",
            side_effect=subprocess.TimeoutExpired("powershell", 12),
        ):
            self.assertEqual(_list_wmi_serial_ports(), [])

    def test_extract_com_name_from_friendly_name(self):
        self.assertEqual(_extract_com_name("Standard Serial over Bluetooth link (COM12)"), "COM12")
        self.assertEqual(_extract_com_name("No port"), "")

    def test_pnp_parser_extracts_com_port_from_name(self):
        payload = json.dumps(
            {
                "Name": "Standard Serial over Bluetooth link (COM12)",
                "Caption": "Standard Serial over Bluetooth link (COM12)",
                "Description": "Bluetooth Serial",
                "PNPDeviceID": r"BTHENUM\AABBCCDDEEFF",
                "PNPClass": "Ports",
            }
        )

        with patch("bluetooth_assistant.com_ports.os.name", "nt"), patch(
            "bluetooth_assistant.com_ports.subprocess.run",
            return_value=Completed(payload),
        ):
            ports = _list_pnp_com_ports()

        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0].device, "COM12")
        self.assertEqual(ports[0].source, "pnp")

    def test_windows_list_com_ports_uses_windows_sources_before_pyserial(self):
        with patch("bluetooth_assistant.com_ports.os.name", "nt"), patch(
            "bluetooth_assistant.com_ports._list_wmi_serial_ports",
            return_value=[ComPortInfo("COM7", hwid="ID", source="wmi")],
        ), patch(
            "bluetooth_assistant.com_ports._list_pnp_com_ports",
            return_value=[],
        ), patch("bluetooth_assistant.com_ports._list_pyserial_ports") as pyserial_ports:
            ports = list_com_ports()

        self.assertEqual([port.device for port in ports], ["COM7"])
        pyserial_ports.assert_not_called()
