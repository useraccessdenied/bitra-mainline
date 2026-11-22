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

## Update 2026-11-22 (battery/RTC round)
- /run is now a tmpfs (initramfs), modules are in the image, bitra-time uses the RTC offset: see docs/26.
- Boot image now `a-7.img` (cmdline `bitra.root=userdata ...`), kernel `7.2.0-g593dc521516f-dirty` + DT with the gauge; the flashed rootfs got modules and the new services live (not reflashed).

## Boot image flashed to `boot` (2026-11-22)
After a hang during the standby-power experiments reset the phone into the Droidian initrd (no Droidian rootfs any more: bootloop-like, shell windows only a few seconds), the mainline boot image was flashed permanently:
1. Backup of the partition first: `dd if=/dev/sde11 of=/root/boot-droidian-backup.img` (96 MiB, sha256 `95a645cb12d3625492d97eefa6bf40db3be0c6d41598b1749d8a191b15c40ae4`), copied to `bitra/backups/boot-before-mainline-20261122/` and re-hashed on the host.
2. Image: `releases/mainline-boot-1.img` (= the tested `a-10`: normal-config kernel `7.2.0-bitra`, cmdline `bitra.root=userdata panic=0 consoleblank=0 earlycon=efifb keep_bootcon console=tty0 loglevel=4`), sha256 `22dc32fbd4ef235956e01c00f56ed35aea7b13084b36d740eb3cfdd0c373cf2d`, 24,166,400 bytes.
3. Flash from the running phone with `tools/flash-boot.sh IMAGE SHA256` (checks the single `boot` partition, size, not mounted, image hash; dd; readback hash).
4. `reboot` (no fastboot): the phone booted Alpine on its own (`androidboot.mode=normal`, root `sda11`).
Recovery if a flashed image ever fails to boot: enter fastboot with the keys (the screen stays on the bootloader), `fastboot flash boot boot-droidian-backup.img` or flash any other known-good boot image; `fastboot boot IMG` also works from the keys-entered fastboot.
Development flow now: build a test image, RAM-boot it (`ssh mac to-fastboot` from Alpine, `ramboot`), and flash it with `flash-boot.sh` only when it is good. The modules in the rootfs must match the kernel release (`7.2.0-bitra`).
