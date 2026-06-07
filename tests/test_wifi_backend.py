import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from wifi_backend import WiFiBackend, WiFiBackendError


SCAN_OUTPUT = """
Interface name : WiFi
There are 2 networks currently visible.

SSID 1 : Coffee & Code
    Network type            : Infrastructure
    Authentication          : WPA3-Personal
    Encryption              : CCMP
    BSSID 1                 : 00:11:22:33:44:55
         Signal             : 42%
         Band               : 2.4 GHz
    BSSID 2                 : 00:11:22:33:44:66
         Signal             : 88%
         Band               : 5 GHz

SSID 2 : Guest
    Network type            : Infrastructure
    Authentication          : Open
    Encryption              : None
    BSSID 1                 : aa:bb:cc:dd:ee:ff
         Signal             : 65%
         Band               : 5 GHz
"""


class OutputBackend(WiFiBackend):
    def __init__(self, output):
        self.output = output
        self.calls = []

    def _run_command(self, *arguments):
        self.calls.append(arguments)
        return self.output


class RecordingBackend(WiFiBackend):
    def __init__(self):
        self.calls = []
        self.profile_xml = None
        self.profile_path = None

    def _run_command(self, *arguments):
        self.calls.append(arguments)
        if arguments[:2] == ("add", "profile"):
            self.profile_path = Path(arguments[2].removeprefix("filename="))
            self.profile_xml = self.profile_path.read_bytes()
        return "Command completed successfully."


class WiFiBackendTests(unittest.TestCase):
    def test_scan_keeps_strongest_signal_and_sorts_networks(self):
        networks = OutputBackend(SCAN_OUTPUT).scan_networks()

        self.assertEqual(["Coffee & Code", "Guest"], [item["ssid"] for item in networks])
        self.assertEqual(88, networks[0]["signal"])
        self.assertEqual(["2.4 GHz", "5 GHz"], networks[0]["bands"])
        self.assertEqual("CCMP", networks[0]["encryption"])

    def test_current_connection_ignores_disconnected_interface(self):
        output = """
            Name                   : WiFi 2
            State                  : disconnected

            Name                   : WiFi
            State                  : connected
            SSID                   : Office Network
            AP BSSID               : 00:11:22:33:44:55
        """

        self.assertEqual(
            "Office Network",
            OutputBackend(output).get_current_connection(),
        )

    def test_run_command_does_not_use_a_shell(self):
        captured = {}

        def runner(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return SimpleNamespace(stdout="ok", stderr="", returncode=0)

        backend = WiFiBackend(runner=runner)
        backend.connect_to_profile('Cafe & echo "unsafe"')

        self.assertEqual("netsh", captured["command"][0])
        self.assertIn('name=Cafe & echo "unsafe"', captured["command"])
        self.assertFalse(captured["kwargs"]["shell"])

    def test_profile_xml_escapes_values_and_temp_file_is_removed(self):
        backend = RecordingBackend()
        backend.connect_new_network(
            'Cafe & "Friends"',
            "WPA3-Personal",
            "password<&",
        )

        root = ET.fromstring(backend.profile_xml)
        namespace = {"w": WiFiBackend.PROFILE_NAMESPACE}
        self.assertEqual(
            'Cafe & "Friends"',
            root.findtext("w:name", namespaces=namespace),
        )
        self.assertEqual(
            "WPA3SAE",
            root.findtext(".//w:authentication", namespaces=namespace),
        )
        self.assertEqual(
            "password<&",
            root.findtext(".//w:keyMaterial", namespaces=namespace),
        )
        self.assertFalse(backend.profile_path.exists())

    def test_open_profile_has_no_shared_key(self):
        xml = WiFiBackend._build_profile_xml("Guest", "open", "")
        root = ET.fromstring(xml)
        namespace = {"w": WiFiBackend.PROFILE_NAMESPACE}

        self.assertEqual(
            "none",
            root.findtext(".//w:encryption", namespaces=namespace),
        )
        self.assertIsNone(root.find(".//w:sharedKey", namespaces=namespace))

    def test_invalid_personal_password_is_rejected_before_file_creation(self):
        backend = RecordingBackend()

        with self.assertRaises(WiFiBackendError):
            backend.connect_new_network("Home", "WPA2-Personal", "short")

        self.assertEqual([], backend.calls)

    def test_command_error_is_reported(self):
        def runner(_command, **_kwargs):
            return SimpleNamespace(stdout="", stderr="Access is denied.", returncode=1)

        with self.assertRaisesRegex(WiFiBackendError, "Access is denied"):
            WiFiBackend(runner=runner).disconnect()


if __name__ == "__main__":
    unittest.main()
