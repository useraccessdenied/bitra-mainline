#!/usr/bin/env python3
# migrate Wi-Fi from the bitra-wifi service (wpa_supplicant.conf) to a NetworkManager connection; secrets are never printed
import re, subprocess, sys
conf = open("/etc/wpa_supplicant/wpa_supplicant.conf").read()
blocks = re.findall(r"network=\{(.*?)\}", conf, re.S)
made = 0
for b in blocks:
    ssid = re.search(r'ssid="([^"]+)"', b)
    psk = re.search(r'psk=(?:"([^"]+)"|([0-9a-fA-F]{64}))', b)
    plain = re.search(r'^\s*#psk="([^"]+)"', b, re.M)   # wpa_passphrase leaves the passphrase in a comment next to the hashed key
    if not ssid or not (psk or plain):
        continue
    # A raw 64-hex key only works for WPA2-PSK: WPA3 (SAE-only) access points need the passphrase, otherwise wpa_supplicant scans forever and NetworkManager
    # reports "ssid-not-found" / "The Wi-Fi network could not be found" (docs/35). Prefer the passphrase.
    secret = plain.group(1) if plain else (psk.group(1) or psk.group(2))
    if not plain and not psk.group(1):
        print("WARNING:", ssid.group(1), "has only a raw 64-hex key: fine for WPA2, will NOT connect to a WPA3/SAE-only network; add the passphrase")
    prio = re.search(r"priority=(\d+)", b)
    name = "bitra-" + ssid.group(1)
    subprocess.run(["nmcli", "connection", "delete", name], capture_output=True)
    cmd = ["nmcli", "connection", "add", "type", "wifi", "ifname", "wlan0", "con-name", name, "ssid", ssid.group(1),
           "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", secret, "connection.autoconnect", "yes",
           "connection.autoconnect-priority", prio.group(1) if prio else "0"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print("added connection for", ssid.group(1), "rc", r.returncode, r.stderr.strip()[:100])
    made += 1
print("connections created:", made)
