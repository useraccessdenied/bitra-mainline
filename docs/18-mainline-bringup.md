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

## Update: agent control + panel driver (2026-11-21)
- The initramfs now serves DHCP (192.168.2.20-30) so the Mac needs no sudo, runs telnetd on :23, provides a `bash` shim (the agent's
  `exec bash || exec sh` kills busybox ash), `/usr/local/sbin/busybox-bitra` (agent file transfer), and a `systemctl` shim +
  `bitra-reboot` helper (tools/bitra-reboot.c, freestanding; reboot(2) with an argument) so the agent's `to-fastboot`/`reboot`/`state`
  work. `reboot bootloader` relies on the PMIC PON reboot-mode (`&pon { mode-bootloader = <0x2>; }`, CONFIG_POWER_RESET_QCOM_PON=y).
- New panel driver `drivers/gpu/drm/panel/panel-samsung-ams662zs01.c` (derived from the sibling OnePlus 8T AMB655X driver): stock DCS init
  sequence decoded from the vendor DT (script: parse `qcom,mdss-dsi-on-command` blobs: [dtype,last,vc,ack,wait,len16,payload...]),
  same DSC PPS (slice 540x30, 8 bpp), modes 120 Hz (hfp 50) and 60 Hz (hfp 540), supplies vddio=l14a 1.8 V, vdd=l13a 3.0 V (VCI),
  vddr=l2c 1.2 V, reset GPIO 75 (active-low in DT), AVDD gpio via pinctrl (gpio8 'panel_vout'), TE GPIO 66, backlight DCS 0..2047.
  Pixelworks Iris5 runs in "soft" mode (`pxlw,soft-iris-enable`): DSI goes straight to the panel (to be confirmed on hardware).

## RESULT: display works on mainline (2026-11-21, t-d1)
Booting with the panel driver and the display pipeline enabled: msm drm 1.13 initialises (DPU rev 0x60000000), the DSI panel binds
(`ae94000.dsi.0` backlight 0..2047), connector `DSI-1` connected/enabled with 1080x2400, fbdev `msmdrmfb` (stride **4352**, 32 bpp).
Verified on the panel with solid white and R/G/B bars written to /dev/fb0 (colour order correct for XRGB8888 bytes B,G,R,X;
rows must be 4352 bytes apart). Backlight sysfs brightness works. Known noise: WARNs from the DSI PHY probe
(`DSI PLL(0) lock failed`, `dsi0_phy_pll_out_dsiclk already disabled`) during `of_clk_add_hw_provider` reparenting — harmless so far, to be cleaned up.
Not yet checked: 60 Hz mode switch, ESD/TE behaviour, fbcon text rendering (`sys_imageblit: framebuffer is not in virtual address space`
warning from fbcon on msmdrmfb), suspend/resume of the panel.

## Refresh rates measured (t-d4, tools/bitra-drm.c)
`bitra-drm modes | anim MODE SECS [ROWS] [v]` — raw-syscall DRM tool baked into the initramfs (/bin/bitra-drm): lists modes, sets one,
page-flips an animation and reports the real rate from flip-complete events (`v` = pure WAIT_VBLANK rate).
- First attempt: 120 Hz mode ran at only ~72 fps and the vblank rate was ~120 Hz in BOTH modes. Two causes: (1) the driver always sent the
  panel its 120 Hz command (`60 08 00`), so the panel's TE stayed at 120 Hz even in the 60 Hz mode; (2) in DSC command mode msm derives the
  DSI clock from the mode's pixel clock (pclk x compressed-htotal/htotal x 24/32 lanes) = ~805 Mbit/s/lane at 120 Hz → ~6.4 ms per frame of an
  8.33 ms period, so ~40% of frames missed a TE tick.
- Fix: panel selects 0x60 data from the committed adjusted_mode (connector remembered in get_modes); the 120 Hz mode carries 1216 extra
  vertical porch lines (clock 344→516 MHz, ~1.2 Gbit/s/lane, same trick as the OnePlus 8T driver).
- Result: 120 Hz mode 120.5 fps (vblank 120.5), 60 Hz mode 60.3 fps (vblank 60.3); 8 rapid 120<->60 switches clean, no new kernel errors.
- Initramfs holds /dev/watchdog0 open: the per-pet "watchdog did not stop!" messages are gone. `to-fastboot` works from a mainline session
  (PMIC PON reboot-mode + tools/bitra-reboot.c), so the dev loop needs no key presses.

## RESULT: Wi-Fi works (QCA6390 / ath11k) — scan finds the home APs (2026-11-21, t-w4)
`wlan0` appears, firmware 0x10121492 (2021-11-04, generic linux-firmware amss/m3/board-2, no OEM BDF needed so far), `iw dev wlan0 scan`
returned 15 BSS incl. the owner's 2.4 GHz (ch 10, -46 dBm) and 5 GHz (ch 52, -63 dBm) APs. Not yet: association/WPA, throughput, suspend, MAC (`use-nv-mac`:
the default 00:03:7f:12:42:42 placeholder is used), Bluetooth.
Gotchas found on the way (each was a hard stop):
1. `qca6390-pmu` waited on `regulators-2/smps2`: "could not find RPMh address for resource smpf2" — the OnePlus tree takes the PMU's 0.95 V
   rails from PM8009 smpf2, which has no RPMh address on this phone. Stock cnss uses pm8150_s6 (aon 0.95 V), s4 (1.8 V io), s5 (1.9 V), pm8150a_s8 (1.3 V):
   the bitra DTS points `vddpmu`/`vddrfa0p95` at `vreg_s6a_0p95`.
2. `pwrseq-qcom_wcn`: "cannot find GPIO chip gpiolib_shared.proxy.N" — GPIO 21 (bt-enable) is referenced by the PMU and the BT node, so gpiolib-shared
   makes a proxy device; it needs `CONFIG_GPIO_SHARED_PROXY=y` (it was =m, no module loader in the initramfs).
3. ath11k/cfg80211/mac80211 must be built in (CONFIG_RFKILL=y so CFG80211 can be y); firmware is put into the initramfs by scripts/build_mainline_boot.py
   (decompressed from the host's linux-firmware; generic board-2.bin worked).
4. Wireless userspace: scripts/fetch_alpine_pkgs.py downloads iw + wpa_supplicant (+musl, libnl3, openssl, dbus-libs, pcsc-lite-libs) from Alpine with checksum
   verification into third_party/alpine (gitignored); the initramfs build adds them. (APKINDEX signature itself is not verified.)
Kernel config snapshot: configs/bitra_defconfig (savedefconfig of the working build; apply on top of the omnipha defconfig via `make bitra_defconfig` after copying to arch/arm64/configs/).
