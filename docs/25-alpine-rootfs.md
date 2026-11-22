# 25 — Alpine rootfs on UFS (`userdata`) with mainline 7.2.0 (2026-11-22)

Status: **works.** Alpine 3.24 (aarch64) boots from the `userdata` partition (sda11, ext4, grown to the whole 222 GiB on first boot),
console on the panel (fbcon text renders; login on tty1), USB-NCM + telnet for the bitra-agent, sshd, Wi-Fi (wpa_supplicant + DHCP) at boot.
Still RAM-booted: every boot is `to-fastboot` + `ramboot a-N.img`; the flash (`boot` partition) still holds the Droidian boot image.
The Droidian install on `userdata` was wiped (owner's decision); the Droidian initrd in `boot` is the way back to fastboot after a power cycle.

## Pieces
- `scripts/build_alpine_rootfs.py` — builds the image with no sudo/containers: `unshare --map-root-user --map-auto`, sha256-checked minirootfs, x86_64
  apk-tools-static (`--root`, `--arch aarch64`; package signatures verified by apk), post-install scripts via host qemu-user binfmt, `mke2fs -d`.
  Adds: firmware (same files as the initramfs), helper tools (`bitra-reboot` etc.), OpenRC services `bitra-net` (192.168.2.15 on usb0), `bitra-telnetd`
  (:23, respawning), `bitra-udhcpd` (pool .20-.30), `bitra-wifi`, `bitra-growfs` (resize2fs to the partition), `bitra-diag` (prints net/service state above the console login).
  The agent needs `systemctl` and `bash` shims, both installed. Root password `bitra` (dev), your `~/.ssh/*.pub` go to root's authorized_keys.
- `scripts/build_mainline_boot.py` — PID-1 loop in the initramfs: `bitra.root=<GPT partname>` on the kernel command line, or `bitra-switchroot part NAME|loop FILE`
  from the shell, mounts the root and `switch_root`s. The initramfs telnetd/udhcpd/watchdog-pet loop survive the switch (Alpine kills/replaces the first two).
- Image is 600 MiB; the first boot grows it online (ext4 reserves 1024x growth, enough for 225 GiB).
- Wi-Fi credentials are NOT in the image: `ssh mac "put wpa.conf /etc/wpa_supplicant/wpa_supplicant.conf"` after flashing; `bitra-wifi` starts it when present.

## Flashing userdata (what was done, from a RAM-booted mainline shell)
1. `mount -t tmpfs -o size=3g tmpfs /mnt/ram`; `put` the image there (NOT `/tmp` of an Alpine loop root: it ran out of space).
2. `sha256sum` on the phone = host hash; then `dd bs=4M conv=fsync` to the partition found by `PARTNAME=userdata` (size and unmounted state re-checked first).
3. Read back and compare the sha256 (UFS write path: 600 MB at ~750 MB/s, readback hash identical).

## Lessons (gotchas)
- Alpine's busybox has no `telnetd`/`udhcpd`: they are in `busybox-extras`. Alpine's `ip` is busybox: no `-br`. busybox `losetup -f` fails: use `/dev/loopN`.
- `supervise-daemon` did not work for busybox applets here; the services use `start-stop-daemon -b` + a respawn loop.
- The Android boot image cuts the kernel command line (512 + 1024 bytes): put important parameters (`bitra.root=`) FIRST in `--cmdline-extra`.
- `bitra-agent put` of a 2 GiB file failed (EINVAL); keep transfers < ~1 GiB. `stage` of 2 GiB works.
- Debugging without a shell: the panel console works, so print diagnostics into `/etc/issue` (bitra-diag) and photograph the screen.

## apk / TLS needs a clock (2026-11-22)
The phone has no RTC (`/sys/class/rtc` is empty), so it boots at 1970-01-01 and `apk update` fails with `TLS: server certificate not trusted`
(and curl/https the same). `bitra-time` (boot runlevel) restores max(`/var/lib/bitra-time`, `/etc/bitra-build-time`) before the network comes up,
then loops `ntpd -q` in the background until a server answers and saves the time (also saved on shutdown). Installed live on the flashed system
with `put` + `rc-update add bitra-time boot`; the builder bakes it into new images. A real fix is the PMIC RTC (pm8150 rtc is not enabled in our DT).
Note: `example.com` does not resolve on the owner's LAN (router DNS); other hosts work. Not a phone issue.
