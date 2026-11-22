# 29 — Graphics: Sway on the panel and Adreno 650 GPU acceleration (2026-11-22)

Status: **works**. Display (msm DPU/DSI) + Sway (Wayland) with touch and hardware keys, and the GPU accelerated through Mesa (freedreno OpenGL ES, turnip Vulkan).
Test kernel `7.2.0-bitra` with the GPU enabled in the DT (kernel fork commit `bead68980`), RAM-booted as `a-13`; the flashed `boot` image (`mainline-boot-2`) does NOT have the GPU enabled yet (see "Not done").

## What was set up on the phone (Alpine 3.24)
- Packages: `sway seatd foot grim wlr-randr swaybg mesa-dri-gallium mesa-egl mesa-gles mesa-gbm mesa-vulkan-freedreno vulkan-tools libinput-tools eudev udev-init-scripts(-openrc) font-dejavu weston-clients mesa-demos wev linux-firmware-qcom`.
- **udev instead of mdev** (libinput needs udev's input tags): `udev`, `udev-trigger` (sysinit), `udev-postmount`, `seatd` (default); `mdev` removed from sysinit. Verified: touchscreen = `ID_INPUT_TOUCHSCREEN`, keys tagged.
- User `bitra` (dev password `bitra`) in `video input render seat audio`; `render` group created. Session launcher `rootfs-overlay/usr/local/bin/bitra-sway-start`
  (`openvt -c 2 -s -f -- bitra-sway-start`, `WLR_RENDERER=pixman|gles2`), config `rootfs-overlay/home/bitra/.config/sway/config`:
  scale 2, touch mapped to `DSI-1`, **Volume Up = new terminal, Volume Down = screenshot**, bar with a clock. A sway config block must be multi-line (`input type:touch {` newline ...): a one-line block was the "Error(s) loading config".
- Wayland output: `DSI-1`, 1080x2400 at **120 Hz** (also 60 Hz).

## Proof 1: software rendering (pixman), no GPU
Sway on the `msm` KMS driver with `WLR_RENDERER=pixman`: owner confirmed on the physical panel: Sway shows, Volume Up opens a second terminal, touch works. Screenshot: `docs/data/sway-software-screenshot-2026-11-22.png`.

## Proof 2: GPU acceleration
- DT: removed `&gpu`/`&gmu` `status = "disabled"`, added `&gpu_zap_shader { firmware-name = "qcom/sm8250/realme/bitra/a650_zap.mdt"; }`.
- Firmware: the **signed ZAP shader is device specific**: taken from this phone's stock vendor firmware (`firmware/stock-a13/v-extract/vendor/firmware/a650_zap.{mdt,b00,b01,b02}`) into `/lib/firmware/qcom/sm8250/realme/bitra/`.
  **`a650_sqe.fw` and `a650_gmu.bin` must come from linux-firmware (Alpine `linux-firmware-qcom`, zstd-compressed, the kernel reads them)**: the stock Android SQE is version 93 and the driver refuses it ("a650 SQE ucode is too old. Have version 93 need at least 95").
  The driver caches the first firmware it loads, so replacing a file needs a reboot. GMU firmware loads as v2.1.8.
- Results: `vulkaninfo`: `Turnip Adreno (TM) 650`, Mesa 26.1.6, Vulkan 1.3.354; `eglinfo`: OpenGL / ES renderer **FD650** (software was `llvmpipe`).
  Sway with `WLR_RENDERER=gles2` (compositor on the GPU) + `weston-simple-egl`: **605 frames / 5 s = ~121 fps (the panel's 120 Hz)**; screenshot `docs/data/gpu-egl-screenshot-2026-11-22.png`.
  GPU devfreq 305 -> **670 MHz** (the Snapdragon 870 bin) and back to idle; no GPU errors in dmesg; **GPU survives s2idle suspend/resume** (20 s suspend with the demo running, demo kept running).

## Not done / open
- **GPU cooling device**: `msm_devfreq_init: Couldn't register GPU cooling device` (error from `of_devfreq_cooling_register`, although the gpu node has `#cooling-cells` and the `gpu-top/bottom-thermal` zones reference it):
  no kernel GPU throttling path. Fix before the GPU is part of the default boot / heavy use (thermal zones read 36-37 C at idle).
- **GPU firmware is not in the initramfs**: the first firmware request happens before the root is mounted (`Direct firmware load for qcom/a650_sqe.fw failed with error -2` at ~25 s); the later retry after `switch_root` works (~85 s on first GPU use). Add `a650_sqe.fw.zst`, `a650_gmu.bin.zst` and the ZAP files to the initramfs.
- `sync_state() pending due to 3d6a000.gmu` for gcc/gpucc until the GPU initialises (check that it completes; it did not matter for function).
- The flashed boot image has the GPU disabled; flash an image built from the new DT after the two items above (use `tools/flash-boot.sh`).
- No Xwayland (not installed), no on-screen keyboard, no screen lock/idle, no brightness/rotation handling, no auto-start (sway is started by hand), no D-Bus session. The base for a real shell is Phosh (docs/27 next steps).
- The image builder (`scripts/build_alpine_rootfs.py`) now includes all of the above (packages, udev, user, overlay, ZAP firmware); the default size is 1280 MB (a 1 GiB+ image does not fit a single agent `put`: keep using the live system or split transfers).
