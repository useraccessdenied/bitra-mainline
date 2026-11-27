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

### Update 2026-11-22 (later): `mainline-boot-2.img` flashed
Same kernel (`7.2.0-bitra`) and cmdline as `mainline-boot-1`, plus an initramfs change: right after mounting the root, `/pstore` is copied to `/var/lib/pstore/early-<uptime>/` (the previous boot's ramoops console/dmesg survive even if the next boot dies before userspace).
sha256 `8ecc47d16a773eb0980e7a16586071674d0674cc382413877da0071a459ae643`, flashed with `tools/flash-boot.sh` after confirming the partition held `mainline-boot-1` (hash `22dc32fb...`); readback OK; normal reboot came up in Alpine on its own and the early copy ran.
Rollback images: `releases/mainline-boot-1.img` (previous), `bitra/backups/boot-before-mainline-20261122/` (Droidian).

### Update 2026-11-22 (GPU): `mainline-boot-3.img` flashed
GPU enabled in the DT, `CONFIG_DEVFREQ_THERMAL=y`, GPU firmware in the initramfs; sha256 `507beb960a6415f01a3f8efb084ccc1308fa1e8419e9b0e0b5099d8131c6b87b`; flashed over `mainline-boot-2` with `tools/flash-boot.sh` (readback OK, standalone boot verified). See docs/29.

### Update 2026-11-22 (audio): `mainline-boot-5.img` flashed
ADSP enabled + sound card model/routing + q6afe vote handling; sha256 `14afccb86766f670c026402e22f3681f507e50e514ddbc1c3d2a78e9db9daaec`; flashed over `mainline-boot-4` (readback OK, standalone boot verified, ADSP running, card registered, tone played). The ADSP firmware lives in the rootfs (`/lib/firmware/qcom/sm8250/realme/bitra/adsp.*`, installed live; the builder copies it from `third_party/firmware/` after `tools/extract-dsp-firmware.py`). See docs/31.

### Update 2026-11-22 (microphone): `mainline-boot-6.img` flashed
`releases/mainline-boot-6.img`, sha256 `11ce98f2e774260e842d95f705ab0757498d35c1b5b7581523cbfadf9940d016`, 24,215,552 bytes: the committed kernel (fork head `f04411f42`) with the stock-matching DT changes for the microphone (AMIC1/3/4/5 -> MIC BIAS routes, third DMIC pin pair, stock VA DMIC bias routes; `qcom,tx-port-mapping` unchanged). Before flashing, `boot` was read back and matched `mainline-boot-5` (`14afccb8...`); flashed with `tools/flash-boot.sh` (pushed to a phone tmpfs, `/mnt/ram`, with the image; hash checked on the phone), readback hash identical. Cold boot afterwards: sound card up, PulseAudio auto-started with `bitra_mic` as default source (rms ~185 ambient, both channels identical), no kernel faults. Rollback: `releases/mainline-boot-5.img` (`14afccb8...`) with the same script, or the Droidian backup via keys fastboot.

### Update 2026-11-27 (sensors): `mainline-boot-8.img` flashed
`releases/mainline-boot-8.img`, sha256 `209c0b48b0b133885b5c33eae7e14f2f6f3e06a0fc4e0a543af27c0bd58b717d`, 24,223,744 bytes: kernel fork head `1136f1896` with `CONFIG_QCOM_OPLUS_SENSOR_DEVINFO=y` (the SMEM sensor inventory is written at 1.9 s, before the SLPI powers up at 6.5 s; docs/32), cmdline as before. Same DT as the RAM-boot test `a-30`, which includes the committed USB dual-role change (docs/33: the earlier flashed images forced peripheral mode; in `a-30` and this image the role stayed `device`/sink with the Mac attached; host mode and charger-attach behaviour are still untested).
- Backup first: the partition held `mainline-boot-7` (hash `42d55ea8...` over its 24,215,552 bytes); the full 96 MiB dump is `android/backups/boot-before-sensors-20261127/boot-backup.img` (sha256 `d4e22ad4efd930892896087ecb5157937bc89418c2e8c78ed72513387a3409dd`, copied off the phone and compared). Restore: `fastboot flash boot boot-backup.img` from the keys-entered fastboot.
- Flashed with `tools/flash-boot.sh` (partition `/dev/sde11`, 196608 sectors, readback hash identical, `FLASH OK`); the normal reboot came up in Alpine on its own (kernel `7.2.0-bitra`, driver log line at 1.877 s, `slpi is now up` at 6.77 s). The rootfs was not rebuilt (same kernel release, modules unchanged).
- Checked on the next cold boot: proximity, light, magnetometer, compass and accelerometer all answer (`ssccli`) about 2 minutes after boot with no manual step; `iio-sensor-proxy` tested earlier with `a-30` lists accelerometer, light, proximity, compass.

### Update 2026-11-27 (Wi-Fi): `mainline-boot-9.img` flashed
`releases/mainline-boot-9.img`, sha256 `a03e0b736b4b829041904ef245b56f54e52982b185e76349b1ef1f2334d6d877`, 24,231,936 bytes: `mainline-boot-8` plus the Wi-Fi calibration variant in the DT (kernel fork `eb7a65263`) and the generated `board-2.bin` (OEM bdwlan.elf, docs/35) in the initramfs. Before flashing, the partition was confirmed to hold exactly `mainline-boot-8` (hash `209c0b48...`; restore image = `releases/mainline-boot-8.img`). Flashed with `tools/flash-boot.sh` (readback identical, `FLASH OK`); the reboot came up in Alpine: variant `realme_GT_Neo_2` in the live DT, `bitra-wifi-mac` set `02:4e:83:93:af:e1`, Wi-Fi associated with internet (25-60 ms), SMEM sensor inventory written at 2.0 s.

### Update 2026-11-27: rootfs image rebuilt from the repo
`releases/alpine-rootfs.ext4` (1800 MiB apparent, sha256 `8cdc6fc634abc9696ef90853a00e5e29de1c5f46484c36ef694ce8e436027a0d`, `--size-mb 1800`: the tree is now 1.2 GB, 900 MiB no longer fits) now reproduces what had been changed live on the phone: the SMEM-sensor setup (45 pruned sensor configs, `bitra-sensors`), the OEM Wi-Fi `board-2.bin` (`f5f3244b...`) with `bitra-wifi-mac` and its NetworkManager config, `bluetooth` in the default runlevel, `bitra-bt-addr`, `bluez-btmgmt`, BlueZ `main.conf` (name and phone class) and the iio-sensor-proxy udev rule. Checked by reading the image with `debugfs`. **Not flashed** (flashing it wipes `userdata`); the boot image `mainline-boot-9` is unchanged and current.

