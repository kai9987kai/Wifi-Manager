# WiFi Manager

A lightweight **Windows Wi-Fi manager GUI** built with **Python + CustomTkinter**, backed by the native `netsh wlan` command set.

It’s split into:
- `wifi_backend.py` — a small backend wrapper around `netsh` (scan, connect, disconnect, saved profiles, password extraction)
- `main.py` — a CustomTkinter desktop UI that calls the backend in background threads to keep the interface responsive

---

## Features

### GUI (CustomTkinter)
- **Scan & list nearby networks** with:
  - SSID
  - Signal strength (%)
  - Authentication/security label
- **Show current connection** in the sidebar
- **Connect / Disconnect** with one click
- **Saved profile helpers**
  - Marks networks as **(Saved)**
  - A **Key** button appears for saved profiles to display the saved Wi-Fi password (when available)

### Backend (netsh-based)
- Scan networks using:
  - `netsh wlan show networks mode=bssid`
  - Parses SSID / Signal / Authentication
  - Deduplicates by SSID (keeps strongest signal)
- Current SSID detection:
  - `netsh wlan show interfaces`
- Connect flows:
  - Connect to an **existing saved profile**:
    - `netsh wlan connect name="SSID"`
  - Connect to a **new WPA2-Personal network** (basic v1 approach):
    - Generates a WLAN profile XML (`WPA2PSK` + `AES`)
    - `netsh wlan add profile filename="temp_profile_<SSID>.xml"`
    - `netsh wlan connect name="SSID"`
    - Cleans up the temporary XML file afterwards
- Saved profiles:
  - `netsh wlan show profiles`
- Saved password extraction (cleartext):
  - `netsh wlan show profile name="SSID" key=clear`
  - Parses `Key Content`

---

## Platform Support

✅ **Windows 10/11** (intended)  
⚠️ Not currently implemented for Linux/macOS (would require `nmcli`, `networksetup`, etc.)

---

## Requirements

- **Python 3.x**
- **Windows** with Wi-Fi and `netsh` available
- `customtkinter` (UI)

> `tkinter` ships with standard Python on Windows in most installs, but some minimal Python distributions may omit it.

---

## Install

### 1) Clone the repo
```bash
git clone https://github.com/kai9987kai/Wifi-Manager.git
cd Wifi-Manager
