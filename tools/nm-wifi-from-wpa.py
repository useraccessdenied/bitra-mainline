#!/usr/bin/env python3
# migrate Wi-Fi from the bitra-wifi service (wpa_supplicant.conf) to a NetworkManager connection; secrets are never printed
import re, subprocess, sys
conf = open("/etc/wpa_supplicant/wpa_supplicant.conf").read()
blocks = re.findall(r"network=\{(.*?)\}", conf, re.S)
made = 0
for b in blocks:
    ssid = re.search(r'ssid="([^"]+)"', b)
    psk = re.search(r'psk=(?:"([^"]+)"|([0-9a-fA-F]{64}))', b)
    if not ssid or not psk:
        continue
    secret = psk.group(1) or psk.group(2)
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
