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

## Fixed after the first proof (2026-11-22, same day)
- **GPU cooling device**: the cause was `# CONFIG_DEVFREQ_THERMAL is not set`: without it `of_devfreq_cooling_register()` is a header stub that returns `-EINVAL`, and the msm message hid the code (now printed with `%pe`, kernel `cbd6be89f`).
  Enabled `CONFIG_DEVFREQ_THERMAL=y` (in `configs/bitra_defconfig`). Verified: `cooling_device3` = `devfreq-3d00000.gpu` (7 states) bound as `cdev0` to `gpu-top-thermal` and `gpu-bottom-thermal`;
  forcing `cur_state` 6 caps the devfreq `max_freq` at 305 MHz, state 0 restores 670 MHz (the demo keeps its ~121 fps). Modules had to be rebuilt/reinstalled together with the kernel.
  (A debugging detour: I patched `devfreq_cooling.c` with traces that never ran because that file was not even compiled; check `CONFIG_*` before instrumenting.)
- **GPU firmware in the initramfs**: `a650_sqe.fw.zst`, `a650_gmu.bin.zst` (linux-firmware, copied from Alpine's `linux-firmware-qcom` into `third_party/firmware/qcom/`) and the device-specific ZAP files are now in the boot image
  (`EXTRA_FW` in `scripts/build_mainline_boot.py`); the GPU loads its firmware at ~25 s with no failed first attempt.
- **Flashed**: `releases/mainline-boot-3.img` (= `a-17`: kernel `7.2.0-bitra` + GPU enabled + DEVFREQ_THERMAL + GPU firmware in the initramfs + early pstore copy), sha256 `507beb960a6415f01a3f8efb084ccc1308fa1e8419e9b0e0b5099d8131c6b87b`, written with `tools/flash-boot.sh` after confirming the partition held `mainline-boot-2`;
  readback OK; a normal reboot came up on its own with Turnip Adreno 650, EGL FD650, cooling and firmware all working. Rollback images: `mainline-boot-2`, `mainline-boot-1`, and the Droidian backup.

## Still open
- `sync_state() pending due to 3d6a000.gmu` (gcc/gpucc) persists (the GMU device has no bound driver of its own); functionally harmless so far.
- No long-run GPU stress or GPU-hang recovery test; no GPU load vs thermals measurement.
- No Xwayland, on-screen keyboard, screen lock/idle, brightness/rotation handling, auto-start of sway, D-Bus session. A real shell (Phosh) is the next step.
- The image builder (`scripts/build_alpine_rootfs.py`) includes the graphics stack, user, overlay and ZAP firmware; a full image is ~1.3 GB (does not fit one agent `put`; the live system is the source of truth).
