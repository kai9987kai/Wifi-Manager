import locale
import os
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable


class WiFiBackendError(RuntimeError):
    """Raised when Windows cannot complete a Wi-Fi operation."""


class WiFiBackend:
    COMMAND_TIMEOUT_SECONDS = 20
    PROFILE_NAMESPACE = "http://www.microsoft.com/networking/WLAN/profile/v1"

    def __init__(self, runner: Callable = subprocess.run):
        self._runner = runner

    def _run_command(self, *arguments: str) -> str:
        command = ["netsh", "wlan", *arguments]
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            result = self._runner(
                command,
                capture_output=True,
                text=True,
                shell=False,
                encoding=locale.getpreferredencoding(False),
                errors="replace",
                timeout=self.COMMAND_TIMEOUT_SECONDS,
                check=False,
                startupinfo=startupinfo,
            )
        except FileNotFoundError as exc:
            raise WiFiBackendError("Windows netsh was not found.") from exc
        except subprocess.TimeoutExpired as exc:
            raise WiFiBackendError("The Wi-Fi command timed out.") from exc
        except OSError as exc:
            raise WiFiBackendError(f"Could not run the Wi-Fi command: {exc}") from exc

        output = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part and part.strip()
        )
        if result.returncode != 0:
            detail = output or f"netsh exited with code {result.returncode}"
            raise WiFiBackendError(detail)
        return output

    def scan_networks(self) -> list[dict]:
        """Return visible networks, strongest first, with duplicate SSIDs merged."""
        output = self._run_command("show", "networks", "mode=bssid")
        networks = []
        current = None

        for raw_line in output.splitlines():
            line = raw_line.strip()
            ssid_match = re.match(r"^SSID\s+\d+\s*:\s*(.*)$", line, re.IGNORECASE)
            if ssid_match:
                if current and current["ssid"]:
                    networks.append(current)
                current = {
                    "ssid": ssid_match.group(1).strip(),
                    "signal": 0,
                    "auth": "Unknown",
                    "encryption": "Unknown",
                    "bands": [],
                }
                continue

            if not current:
                continue

            value = self._line_value(line)
            label = line.split(":", 1)[0].strip().lower()
            if label == "signal" and value:
                try:
                    signal = int(value.replace("%", "").strip())
                    current["signal"] = max(current["signal"], signal)
                except ValueError:
                    pass
            elif label == "authentication" and value:
                current["auth"] = value
            elif label == "encryption" and value:
                current["encryption"] = value
            elif label == "band" and value and value not in current["bands"]:
                current["bands"].append(value)

        if current and current["ssid"]:
            networks.append(current)

        unique_networks = {}
        for network in networks:
            existing = unique_networks.get(network["ssid"])
            if existing is None or network["signal"] > existing["signal"]:
                unique_networks[network["ssid"]] = network

        return sorted(
            unique_networks.values(),
            key=lambda network: (-network["signal"], network["ssid"].casefold()),
        )

    def get_current_connection(self) -> str | None:
        """Return the SSID connected on any Wi-Fi interface."""
        output = self._run_command("show", "interfaces")
        interface = None

        for raw_line in output.splitlines():
            line = raw_line.strip()
            label, value = self._split_line(line)
            normalized_label = label.lower()

            if normalized_label == "name":
                interface = {"state": "", "ssid": None}
            elif interface is not None and normalized_label == "state":
                interface["state"] = value.lower()
            elif interface is not None and normalized_label == "ssid":
                interface["ssid"] = value

            if (
                interface
                and interface["state"] == "connected"
                and interface["ssid"]
            ):
                return interface["ssid"]

        return None

    def connect_to_profile(self, ssid: str) -> str:
        """Connect to an existing saved network profile."""
        self._validate_ssid(ssid)
        return self._run_command("connect", f"name={ssid}", f"ssid={ssid}")

    def connect_new_network(self, ssid: str, authentication: str, password: str = "") -> str:
        """Create a current-user profile and connect to an open or personal network."""
        self._validate_ssid(ssid)
        auth_value, needs_password = self._profile_authentication(authentication)

        if needs_password and not self.is_valid_passphrase(password):
            raise WiFiBackendError(
                "The password must be 8-63 characters, or a 64-digit hexadecimal key."
            )
        if not needs_password:
            password = ""

        profile_xml = self._build_profile_xml(ssid, auth_value, password)
        profile_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".xml", prefix="wifi-manager-", delete=False
            ) as profile_file:
                profile_file.write(profile_xml)
                profile_path = Path(profile_file.name)

            self._run_command(
                "add",
                "profile",
                f"filename={profile_path}",
                "user=current",
            )
            return self.connect_to_profile(ssid)
        finally:
            if profile_path:
                profile_path.unlink(missing_ok=True)

    def connect_with_password(self, ssid: str, password: str) -> str:
        """Backward-compatible helper for WPA2-Personal networks."""
        return self.connect_new_network(ssid, "WPA2-Personal", password)

    def get_saved_profiles(self) -> list[str]:
        """Return saved Wi-Fi profile names."""
        output = self._run_command("show", "profiles")
        profiles = []
        for line in output.splitlines():
            match = re.match(r"^\s*All User Profile\s*:\s*(.+)$", line, re.IGNORECASE)
            if match:
                profiles.append(match.group(1).strip())
        return profiles

    def get_profile_password(self, ssid: str) -> str | None:
        """Return the cleartext password for a saved profile when Windows permits it."""
        self._validate_ssid(ssid)
        output = self._run_command("show", "profile", f"name={ssid}", "key=clear")
        match = re.search(r"^\s*Key Content\s*:\s*(.*)$", output, re.MULTILINE | re.IGNORECASE)
        return match.group(1).strip() if match else None

    def disconnect(self) -> str:
        return self._run_command("disconnect")

    def wait_for_connection(self, ssid: str, timeout: float = 12) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.get_current_connection() == ssid:
                return True
            time.sleep(0.5)
        return False

    def wait_for_disconnection(self, timeout: float = 6) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.get_current_connection() is None:
                return True
            time.sleep(0.25)
        return False

    @classmethod
    def is_open_network(cls, authentication: str) -> bool:
        normalized = authentication.strip().lower()
        return normalized in {"open", "none"} or normalized.startswith("open ")

    @classmethod
    def supports_password_profile(cls, authentication: str) -> bool:
        normalized = authentication.strip().lower()
        return "personal" in normalized or normalized in {
            "wpapsk",
            "wpa2psk",
            "wpa3sae",
        }

    @staticmethod
    def is_valid_passphrase(password: str) -> bool:
        if 8 <= len(password) <= 63:
            return True
        return len(password) == 64 and all(char in "0123456789abcdefABCDEF" for char in password)

    @classmethod
    def _build_profile_xml(cls, ssid: str, auth_value: str, password: str) -> bytes:
        namespace = cls.PROFILE_NAMESPACE
        ET.register_namespace("", namespace)

        def element(parent, name, text=None):
            child = ET.SubElement(parent, f"{{{namespace}}}{name}")
            if text is not None:
                child.text = text
            return child

        profile = ET.Element(f"{{{namespace}}}WLANProfile")
        element(profile, "name", ssid)
        ssid_config = element(profile, "SSIDConfig")
        ssid_node = element(ssid_config, "SSID")
        element(ssid_node, "name", ssid)
        element(profile, "connectionType", "ESS")
        element(profile, "connectionMode", "auto")
        msm = element(profile, "MSM")
        security = element(msm, "security")
        auth_encryption = element(security, "authEncryption")
        element(auth_encryption, "authentication", auth_value)
        element(auth_encryption, "encryption", "none" if auth_value == "open" else "AES")
        element(auth_encryption, "useOneX", "false")

        if password:
            shared_key = element(security, "sharedKey")
            element(shared_key, "keyType", "passPhrase")
            element(shared_key, "protected", "false")
            element(shared_key, "keyMaterial", password)

        return ET.tostring(profile, encoding="utf-8", xml_declaration=True)

    @classmethod
    def _profile_authentication(cls, authentication: str) -> tuple[str, bool]:
        normalized = authentication.strip().lower()
        if cls.is_open_network(authentication):
            return "open", False
        if "wpa3" in normalized or normalized == "wpa3sae":
            return "WPA3SAE", True
        if "wpa2" in normalized or normalized == "wpa2psk":
            return "WPA2PSK", True
        if normalized.startswith("wpa") or normalized == "wpapsk":
            return "WPAPSK", True
        raise WiFiBackendError(
            f"{authentication or 'This security type'} requires a profile configured by Windows."
        )

    @staticmethod
    def _validate_ssid(ssid: str) -> None:
        if not ssid or "\0" in ssid or "\r" in ssid or "\n" in ssid:
            raise WiFiBackendError("The network name is invalid.")

    @staticmethod
    def _line_value(line: str) -> str:
        return line.split(":", 1)[1].strip() if ":" in line else ""

    @staticmethod
    def _split_line(line: str) -> tuple[str, str]:
        if ":" not in line:
            return line, ""
        label, value = line.split(":", 1)
        return label.strip(), value.strip()
