# WiFi Manager

A focused Windows Wi-Fi desktop app built with Python, CustomTkinter, and the
native `netsh wlan` command set.

## Highlights

- Scans nearby networks without freezing the interface
- Sorts networks by strongest signal and shows available bands
- Shows live signal, channel, radio type, and receive/transmit link rates
- Searches networks and filters by saved or open networks
- Manages every saved profile, including networks that are currently out of range
- Connects directly to saved profiles without asking for the password again
- Forgets unwanted profiles with an explicit confirmation step
- Supports new open, WPA-Personal, WPA2-Personal, and WPA3-Personal profiles
- Provides an opt-in 15-second auto-refresh mode
- Shows clear progress and actionable Windows command errors
- Uses argument-based command execution instead of shell command strings
- Generates escaped profile XML in a securely named temporary file
- Clears copied Wi-Fi keys from the clipboard after 30 seconds
- Supports light, dark, and system appearance modes

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer
- A Wi-Fi adapter managed by Windows WLAN AutoConfig

## Install and run

```powershell
git clone https://github.com/kai9987kai/Wifi-Manager.git
cd Wifi-Manager
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Press `F5` to refresh networks or `Ctrl+F` to focus search. Switch to
**Saved profiles** to connect to, inspect, or forget any Windows Wi-Fi profile,
including profiles that are not currently nearby.

## Security notes

WiFi Manager can ask Windows to reveal the key stored in a saved Wi-Fi
profile. The app requires confirmation before displaying it. Windows may
require administrator access and may decline to return the key.

New personal-network passwords are written only to a temporary WLAN profile
file, imported for the current Windows user, and then deleted. Windows stores
the resulting profile using its normal profile protection.

Enterprise networks that require certificates, usernames, or organization
policy must be configured through Windows before WiFi Manager can connect to
their saved profile.

## Development

Run the backend test suite with:

```powershell
python -m unittest discover -s tests -v
```

The project is split into:

- `wifi_backend.py`: safe `netsh` execution, parsing, profiles, and connection checks
- `main.py`: CustomTkinter interface and background task coordination
- `tests/`: backend regression tests

`netsh` output labels are localized by Windows. The parser currently targets
English Windows installations.
