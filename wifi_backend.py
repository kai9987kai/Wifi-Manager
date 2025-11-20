import subprocess
import re
import time

class WiFiBackend:
    def __init__(self):
        pass

    def _run_command(self, command):
        try:
            # Run command and capture output, ensuring text is decoded
            result = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                shell=True,
                encoding='utf-8', 
                errors='ignore' # Handle potential encoding issues gracefully
            )
            return result.stdout
        except Exception as e:
            print(f"Error running command '{command}': {e}")
            return ""

    def scan_networks(self):
        """
        Scans for available WiFi networks using netsh.
        Returns a list of dictionaries containing SSID, Signal, and Authentication.
        """
        # Trigger a scan first (optional, but good for freshness)
        # self._run_command("netsh wlan show networks mode=bssid") 
        # Note: 'show networks' is faster but less detailed than 'show networks mode=bssid'
        
        output = self._run_command("netsh wlan show networks mode=bssid")
        
        networks = []
        current_network = {}
        
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith("SSID"):
                # If we have a previous network collected, add it
                if current_network and 'ssid' in current_network:
                    networks.append(current_network)
                
                # Start new network
                parts = line.split(":", 1)
                if len(parts) > 1:
                    ssid_val = parts[1].strip()
                    current_network = {'ssid': ssid_val, 'signal': 0, 'auth': 'Open'}
            
            elif line.startswith("Signal"):
                parts = line.split(":", 1)
                if len(parts) > 1 and current_network:
                    try:
                        current_network['signal'] = int(parts[1].strip().replace("%", ""))
                    except ValueError:
                        current_network['signal'] = 0
            
            elif line.startswith("Authentication"):
                parts = line.split(":", 1)
                if len(parts) > 1 and current_network:
                    current_network['auth'] = parts[1].strip()
        
        # Add the last one
        if current_network and 'ssid' in current_network:
            networks.append(current_network)
            
        # Deduplicate by SSID, keeping the strongest signal
        unique_networks = {}
        for net in networks:
            ssid = net['ssid']
            if not ssid: # Skip hidden networks or empty SSIDs
                continue
            
            if ssid not in unique_networks:
                unique_networks[ssid] = net
            else:
                if net['signal'] > unique_networks[ssid]['signal']:
                    unique_networks[ssid] = net
                    
        return list(unique_networks.values())

    def get_current_connection(self):
        """Returns the SSID of the currently connected network, or None."""
        output = self._run_command("netsh wlan show interfaces")
        match = re.search(r"^\s*SSID\s*:\s*(.*)$", output, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def connect_to_profile(self, ssid):
        """Connects to a saved network profile."""
        cmd = f'netsh wlan connect name="{ssid}"'
        return self._run_command(cmd)

    def connect_with_password(self, ssid, password):
        """
        Creates a profile XML and connects to a new network.
        Note: This is a bit complex as it requires generating an XML profile.
        For simplicity in this v1, we might focus on connecting to existing profiles 
        or open networks, but let's try to implement a basic WPA2 profile generator.
        """
        profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
	<name>{ssid}</name>
	<SSIDConfig>
		<SSID>
			<name>{ssid}</name>
		</SSID>
	</SSIDConfig>
	<connectionType>ESS</connectionType>
	<connectionMode>auto</connectionMode>
	<MSM>
		<security>
			<authEncryption>
				<authentication>WPA2PSK</authentication>
				<encryption>AES</encryption>
				<useOneX>false</useOneX>
			</authEncryption>
			<sharedKey>
				<keyType>passPhrase</keyType>
				<protected>false</protected>
				<keyMaterial>{password}</keyMaterial>
			</sharedKey>
		</security>
	</MSM>
</WLANProfile>"""
        
        # Save XML to a temp file
        filename = f"temp_profile_{ssid}.xml"
        with open(filename, "w") as f:
            f.write(profile_xml)
            
        # Add profile
        add_output = self._run_command(f'netsh wlan add profile filename="{filename}"')
        
        # Connect
        connect_output = self._run_command(f'netsh wlan connect name="{ssid}"')
        
        # Cleanup
        import os
        try:
            os.remove(filename)
        except:
            pass
            
        return connect_output

    def get_saved_profiles(self):
        """Returns a list of saved profile names (SSIDs)."""
        output = self._run_command("netsh wlan show profiles")
        profiles = []
        for line in output.split('\n'):
            # Line format: "    All User Profile     : SSID_NAME"
            if "All User Profile" in line:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    profiles.append(parts[1].strip())
        return profiles

    def get_profile_password(self, ssid):
        """Retrieves the cleartext password for a saved profile."""
        cmd = f'netsh wlan show profile name="{ssid}" key=clear'
        output = self._run_command(cmd)
        
        # Look for "Key Content            : PASSWORD"
        match = re.search(r"Key Content\s*:\s*(.*)$", output, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def disconnect(self):
        return self._run_command("netsh wlan disconnect")

if __name__ == "__main__":
    # Simple test
    backend = WiFiBackend()
    print("Scanning...")
    nets = backend.scan_networks()
    for n in nets:
        print(n)
    
    curr = backend.get_current_connection()
    print(f"Current: {curr}")
    
    print("Saved Profiles:")
    profiles = backend.get_saved_profiles()
    print(profiles)
    if profiles:
        print(f"Password for {profiles[0]}: {backend.get_profile_password(profiles[0])}")
