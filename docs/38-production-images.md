# 38 - Production (release) images and housekeeping (2026-11-27)

## What was flashed (clean flash, all from the repo)
- **Partition table (LUN 0 / sda)**: the `darwin` partition (sda12, 64 GiB, the HakiOS iOS volume) was removed at the owner's request and `userdata` (sda11) grown over it and the free space after it: 64 GiB -> 225.4 GiB (same start, type A03A, GUID and name). Backup of the old table: `android/backups/lun0-gpt-20261127/` (`sgdisk --backup` + raw first 6 sectors, README with the restore command). The HakiOS loader reads the iOS volume by the partition name `darwin`, so HakiOS boots need a recreated `darwin` partition (iOS volume rebuilt from the restore ipsw, docs/34); the loader/Mu images themselves are unchanged.
- **`userdata`**: `releases/alpine-rootfs-release.ext4` (`--release`, 1800 MiB apparent, sha256 `713f154597d83a07d4b77feba3bccd1a24cf049926dac6323ddb2ac53ffa662d`), written by `tools/flash-userdata.sh` from the RAM-boot flashing environment `a-32` (gzip over the USB link, `gunzip | dd`, readback hash identical, `FLASH OK`). The first boot grew the filesystem to 222 GiB (`bitra-growfs`).
- **`boot`**: `releases/mainline-boot-10.img` (`--release`, sha256 `c2eb1aebc2cccfd3f4fdc2acd849b7f6b23c610f66b5b972de91055438d23f38`), flashed with `tools/flash-boot.sh` after confirming the partition held `mainline-boot-9`; readback identical. Rollback: `releases/mainline-boot-9.img` (fastboot with the keys: `fastboot flash boot`).
- Verified after the reboot: kernel `7.2.0-bitra`, cmdline has `quiet loglevel=0 logo.nologo vt.global_cursor_default=0` and none of `earlycon=efifb`/`keep_bootcon`/`console=tty0`; services up (`bitra-net`, `bitra-telnetd`, `bitra-wifi-mac`, `bitra-bt-addr`, `bluetooth`, `hexagonrpcd-sdsp`, `bitra-sensors`, `networkmanager`, `sshd`); no getty; no saved Wi-Fi connections (NetworkManager lists only `lo`), no Bluetooth bonds, no `wpa_supplicant.conf`. Screen behaviour (blank until Phosh) is for the owner to confirm by eye.

## Incident: Phosh "stuck" after the clean flash (2026-11-27), fixed
- Symptom: black panel, `tinydm` failed ("respawned too many times"): the autologin session started and ended within a second, over and over (each pass leaked a D-Bus daemon).
- Cause: `/usr/bin/gnome-session` (a wrapper script) re-executes itself through `bash -c "exec -l $SHELL -c 'exec gnome-session -l ...'"`. The builder wrote a one-line `/bin/bash` stand-in (`exec /bin/busybox ash`, for the bitra-agent's shell wrapper) AFTER installing packages, replacing the real `bash`; the stand-in ignores `-c`, so `gnome-session` exited 0 without starting anything. The previous live system never showed it because its real bash had been installed by hand earlier.
- Found by tracing the session (`sh -x /usr/bin/tinydm-run-session`, `~/.phoshdebug` to wrap `gnome-session`, `sh -x /usr/bin/gnome-session`). A getty on tty1 and the kernel command line were ruled out.
- Fix on the phone: the real bash 5.3.9 (taken from the Alpine package on the host) copied over `/bin/bash` (the stand-in is saved as `/root/bash-shim.bak`); Phosh then ran (`phoc`, `gnome-session-binary`, `phosh`, `squeekboard`). Fix in the builder: `bash` is an explicit package, the stand-in is only created when no real bash exists, and the build asserts that `/bin/bash` is an ELF. Rebuilt `releases/alpine-rootfs-release.ext4` sha256 `f7ec53a091a03d3f59f5ba7856340c1111c57065c6f2cbca87910079ccada5a8` (the flashed one was `713f1545...`); the phone now equals it except for being repaired live, no reflash needed.
- Lesson: boot the production image to the Phosh home screen before calling it done (the check list should include `pidof phosh`).

## The release profile
- `scripts/build_mainline_boot.py NAME --release`: kernel command line without the framebuffer console (`bitra.root=userdata panic=0 consoleblank=0 quiet loglevel=0 logo.nologo vt.global_cursor_default=0`; the stock command line keeps `console=ttyMSM0`, which is not visible).
- `scripts/build_alpine_rootfs.py --release`: no getty on tty1 (no login prompt on the panel), root password locked.
- Both builders (every profile): the dev telnet shell (root, no password, for the bitra-agent) is bound to the USB link address `192.168.2.15:23` only (it used to listen on every interface, i.e. on Wi-Fi too, also in the initramfs); sshd is key-only (`PermitRootLogin prohibit-password`, `PasswordAuthentication no`; the build host's `~/.ssh/*.pub` go to root's `authorized_keys`).
- The flashing environment is a normal boot image built without `bitra.root` (`--cmdline-extra "panic=0 consoleblank=0 earlycon=efifb keep_bootcon console=tty0 loglevel=4"`, name `a-32`): it stays in the initramfs shell with nothing from UFS mounted.

## Repo housekeeping done
Personal Wi-Fi network names removed from docs and tools (scripts now take the connection names from the environment); kernel-module build products (`tools/xnulog/*.o/.ko/.cmd`, with absolute home paths) untracked and ignored. Git history still contains the old versions of those files.

## Still to do for production
1. **Login/lock-screen password**: the user `bitra` still has the dev password `bitra` (Phosh's lock screen needs a real password): ask for one at first boot, no default.
2. **Remove the build host's public keys** from the image (or make them opt-in); decide how developers get in (ssh transport for `bitra-agent`, which still talks telnet).
3. **Drop the dev tooling from release rootfs**: busybox-extras telnetd/udhcpd services, `bitra-diag`, python tools, test binaries in `/usr/local/bin`.
4. **Kernel**: production config (docs/27 "Production kernel config": still the pmOS-derived superset, 548 modules), `printk` rate limit, drop debugfs; strip the stock Android cmdline leftovers (`androidboot.*`, `kasan_multi_shot`).
5. **Updates and signing**: image naming/versioning, hashes recorded with every release, an update path for `boot`/`userdata`, secure boot is off (bootloader unlocked).
6. **Services review**: `hexagonrpcd` and sensor config pruning in the release (docs/32), time handling (`bitra-time`, RTC), logging to RAM vs flash.
7. **Privacy**: SoC-serial derived MAC/BD addresses are stable per phone (docs/35, 36): consider per-network randomisation for Wi-Fi; the sensor registry is device-specific calibration from the owner's `persist` backup (never publish).
8. The systemd migration (docs/37) will redo the rootfs; keep this list in the new recipes.
