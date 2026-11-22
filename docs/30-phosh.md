# 30 — Phosh on the phone (2026-11-22)

Status: **works.** Phosh 0.55 (phoc compositor on the Adreno GPU, squeekboard on-screen keyboard) starts automatically at boot on Alpine 3.24 / mainline 7.2.0; owner-verified on the panel: unlock, home screen, apps, keyboard, Wi-Fi/battery indicators, brightness, power key.
Flashed image: `mainline-boot-4.img` (docs/25). Lock-screen / user password: `bitra` (dev), user `bitra`.

## How it is wired
- **Session**: `tinydm` (OpenRC service, autologin of uid 1000) reads `/var/lib/tinydm/default-session.desktop` -> `/usr/share/wayland-sessions/phosh.desktop` -> `phosh-session` -> `dbus-run-session phoc ... gnome-session --session=phosh`. Log: `~bitra/.local/state/tinydm.log`.
- **Seat**: `elogind` (not seatd) + `polkit-elogind`; libseat in phoc picks logind. The DRM device must carry udev's `seat`/`master-of-seat` tags: after installing elogind the udev rules need a `udevadm control --reload; udevadm trigger` (a reboot does it), otherwise phoc fails with "Could not take device: No such device".
- **Network**: NetworkManager now owns Wi-Fi (Phosh's Wi-Fi panel talks to it); `bitra-wifi` and `seatd` are no longer enabled. `/etc/NetworkManager/conf.d/bitra.conf` marks `usb0` unmanaged (the USB-NCM shell link keeps its static 192.168.2.15).
  `tools/nm-wifi-from-wpa.py` creates the NM connections from `/etc/wpa_supplicant/wpa_supplicant.conf` on the phone (never printing secrets; hex PSKs work). `networkmanager-cli` is a separate package (`nmcli`).
- **Battery**: UPower reads the BQ28Z610 gauge (94 %, 12.7 Wh full vs 21.2 Wh design = ~60 % health, matches docs/26), the charging icon works.
- **GPU**: phoc renders through wlroots GLES on freedreno (docs/29). Phosh picks **display scale 3** from the panel size; Wayland clients must use buffer sizes divisible by 3 (vkmark's default 800x600 fails with "Buffer size is not divisible by scale (3)": use `--size 1080x2400`).

## Problems found and fixed on the way
- **Kernel WARN `mm/shrinker.c:212 set_shrinker_bit`** (phoc taking a transparent-huge-page fault): caused by the Android leftover `cgroup.memory=nokmem,nosocket` in the boot image's base cmdline (OpenRC cgroups + a 7.x kernel). Removed in `scripts/build_mainline_boot.py`; verified no warning after a reboot (`mainline-boot-4`).
- **`upower-openrc` does not exist** in Alpine 3.24 (upowerd is D-Bus activated); `phosh-openrc` / `phoc-openrc` do not exist either (tinydm is the session starter).
- Brightness via Phosh/gsd-power works through elogind's `SetBrightness`; idle blanking/locking defaults are on (5 min): they were switched off only during the GPU benchmark and restored afterwards.

## Open
- Display: `[drm:dpu_crtc_get_vblank_counter] / dpu_crtc_get_scanout_position *ERROR* no encoder found for crtc 0` log lines (18 during a 6 min GPU run): vblank queries while the CRTC has no encoder; harmless so far.
- `typec_displayport port0-partner.1: probe ... failed with error -71` when a USB partner attaches.
- No modem/calls (ModemManager has nothing to manage), no camera, no audio (docs/27), no auto-rotation test (iio-sensor-proxy is installed, no sensors without SLPI), no feedback/haptics profile test, Bluetooth pairing UI untested, no swipe-to-suspend test.
- tinydm autologin means the session starts without a login prompt; the lock screen asks for the dev password.
