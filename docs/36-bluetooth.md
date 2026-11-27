# 36 - Bluetooth (QCA6390 over UART6, BlueZ 5.86) (2026-11-27)

## State
- Controller `hci0` (ROME/QCA6390, firmware `qca/htbtfw20.tlv` + `qca/htnv20.bin`) is up; **`bluetoothd` was simply not running** (the OpenRC `bluetooth` service from `bluez-openrc` was installed but not in a runlevel, which is also why Phosh logged `org.bluez ... Launch helper exited`). It is now in the default runlevel (`scripts/build_alpine_rootfs.py`, also enabled live).
- Verified 2026-11-27 with `bluetoothctl`: classic inquiry finds devices and **LE scanning works** (`scan le`: ~6 random-address devices in 10 s; a named Galaxy Fit3 seen in classic inquiry). Pairing and audio (A2DP through `pulseaudio-bluez`, already installed) not tested yet.

## Address
- The DT `local-bd-address` (`02:b1:7a:05:5a:ad`) is one fixed placeholder for every phone. The service `bitra-bt-addr` (rootfs-overlay, runs before `bluetooth`) sets a stable locally administered address derived from the SoC serial (`02:` + first 5 bytes of sha256(`bitra-bt:<serial>`)) with `btmgmt public-addr` (power off, set; the kernel then removes and re-adds the controller index and the firmware is downloaded again, ~2 s). This phone: `02:46:42:53:05:10`. Verified on a cold boot (controller comes up with the placeholder, then the service changes it; `bluetoothctl show` reports the new address, powered).
- `btmgmt` needs a terminal (it prints nothing without a pty): the service runs it through `script -qc`. Package `bluez-btmgmt` (added to the builder's package list; installed live with `apk add`).
- The real stock address was not found (same as Wi-Fi, docs/35).

## Name and class (2026-11-27)
- Phosh's "device name" setting talks to `systemd-hostnamed` (D-Bus `org.freedesktop.hostname1`), which does not exist on this OpenRC system, so it changes nothing (the hostname stays `bitra`) and BlueZ never sees it. BlueZ takes its name from `/etc/bluetooth/main.conf` (`Name`, default `BlueZ 5.86`) and, with no device class configured, advertises class `0x000c0000` (audio service bits, no device type), so other devices showed a headset.
- `rootfs-overlay/etc/bluetooth/main.conf` (the stock file with two lines set): `Name = realme GT Neo 2`, `Class = 0x5a020c` (BlueZ only uses the major/minor bits: Phone / Smartphone, reported as `0x000c020c`). Runtime change without a restart: `bluetoothctl system-alias NAME`. Other devices cache the old name/icon: unpair/rescan there.
- Option if the Phosh setting should work: a small provider of `org.freedesktop.hostname1` (set-hostname + pretty hostname) that also writes the BlueZ name.

## Open
- Pairing, A2DP/audio routing, headset profile (HFP needs a modem/ofono path), Phosh Bluetooth panel check, range, coexistence with 2.4 GHz Wi-Fi, suspend/wake.
