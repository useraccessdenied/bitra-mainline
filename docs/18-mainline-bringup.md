# 18 — Mainline Linux bring-up (stage 1: RAM boot + USB NCM shell) — 2026-11-21

Goal: boot a mainline kernel on the GT Neo 2 (bitra, SM8250-AC) with the same USB-NCM debug link as the Droidian work.
Base: postmarketOS SM8250 mainline fork as carried by github.com/omnipha/linux-qualcomm-sm8250 (branch `omnipha`, 7.2.0).
Our changes: `patches/mainline/0001-bitra-stage1-bringup.patch` (branch `bitra` in roms/mainline/linux, untracked).
Build: host-native, AOSP clang (`roms/mainline/env.sh`), `make O=../out omnipha_sm8250_defconfig`; boot image:
`python3 scripts/build_mainline_boot.py NAME` (reuses scripts/build_debug_initramfs.py: busybox + NCM gadget initramfs).

## Result
Mainline 7.2.0 runs on the phone from a `fastboot boot` RAM image: 8 CPUs up, dwc3 UDC `a600000.usb`, NCM gadget, shell
(uptime > 200 s observed). Nothing is flashed; a plain reboot returns to Droidian.

## What was learned (the non-obvious parts)
1. **ABL (OPLUS) refuses mainline DTBs** ("Failed to load/authenticate boot image: Load Error"). ABL (strings of
   backups abl.img, LZMA FV) picks the DTB by msm-id/board-id/`oplus,dtsi_no`, then merges the vendor `dtbo` overlay with
   libufdt (needs the downstream `__symbols__`/paths) — a mainline tree cannot satisfy that. Even the stock merged
   `/sys/firmware/fdt` was refused as appended DTB here.
   Workaround (bring-up only): pass Droidian's base kona DTBs (`releases/droidian-kernel/dtb`) to ABL and let the kernel
   swap in an embedded mainline DTB, keeping ABL's `/chosen` (bootargs, initrd range, seeds):
   `CONFIG_BITRA_DTB_SHIM` (arch/arm64/kernel/bitra-dtb-shim.c). Long-term: a U-Boot stage (as HakiOS does) or the real fix.
2. **ABL state**: a fastboot entered with the hardware keys makes ABL answer `Load Error` for every image. Always use
   `ssh mac to-fastboot` from the running OS (or `reboot` then `to-fastboot`). The phone is not A/B; no slot is changed.
3. **No visible console**: no UART, pstore does not survive resets on this device (even a deliberate 4.19 panic leaves
   nothing). The panel is the console: ABL leaves a 1080x2400 a8r8g8b8 framebuffer at 0x9c000000 (stride 4320). The shim
   describes it to the EFI-framebuffer earlycon (`earlycon=efifb`) and the efifb writer is also registered as a normal
   console (drivers/firmware/efi/earlycon.c, gated) so it survives late init. simpledrm/fbcon must stay OFF: they turn the
   panel into noise. Debug by filming the screen; frames/stills read well (`pyav` venv for HEVC).
4. **The console is slow** (uncached full-screen scroll per line): with `ignore_loglevel` the panel lagged 3x behind real
   time. Use `loglevel=4`; initramfs status lines are written at KERN_CRIT (`<2>`) so they show.
5. **Watchdog**: ABL arms the apps watchdog; the stock-like reset (PMIC hard reset, "Droidian came back") happens ~35 s
   after boot unless `/dev/watchdog0` is petted — the initramfs pets it from its first line.
6. **USB**: do not enable `USB_G_SERIAL` (legacy gadget claims the UDC); configfs NCM with `USB_CONFIGFS=y`.
   macOS only gets an `enN` interface; give it `sudo ifconfig enN inet 192.168.2.2 netmask 255.255.255.0 alias`
   (the agent has no passwordless sudo there). Shell: busybox telnetd on :23 (agent) — `nc -e` closes on the agent's IAC.
7. DTS reuses the OnePlus 8T common description (same ABL memory map incl. framebuffer_mem 0x9c000000 and
   ramoops 0xb0000000); memory node must be named `/memory` for ABL; UFS/display/GPU/PCIe disabled in stage 1.

## Open / next
UFS (read-only first; pmOS warns UFS bring-up with non-vendor kernels erased a Sony), display panel (Samsung
AMS662ZS01 DSC cmd-mode) so a real console exists, touch, regulators/PMIC, remoteprocs, Wi-Fi, modem (IMEI-safe rmtfs).
Debug images: releases/mainline-debug/ (untracked). The stock FDT (`roms/mainline/stock/`) contains the device serial: never commit.
