# bitra-port

Mainline Linux on the **realme GT Neo 2** (RMX3370, codename `bitra`, Snapdragon 870 / SM8250-AC): tooling, notes and patch exports.

> **AI-assisted, experimental.** See [AI_DISCLOSURE.md](AI_DISCLOSURE.md) and [ATTRIBUTION.md](ATTRIBUTION.md). Not affiliated with Realme/Oplus,
> postmarketOS/Nura or any kernel maintainer. Use at your own risk: this repo writes to the phone's `userdata` partition and never to the firmware LUNs.

Companion repos
- kernel: <https://github.com/useraccessdenied/linux-mainline-bitra> (branch `bitra`, based on `omnipha/linux-qualcomm-sm8250` 7.2.0)
- Android / Droidian build repo: <https://github.com/useraccessdenied/bitra-android>

## Status (2026-11-22)
Mainline **7.2.0 boots the phone into Alpine Linux 3.24 from UFS (`userdata`)**: console on the panel (fbcon), touchscreen, Wi-Fi, USB-NCM + SSH shells,
battery gauge, thermal sensing, input devices for the hardware keys, and a **Phosh phone UI on the accelerated Adreno 650 GPU** (docs/29, 30; Sway also works), and **audio on both speakers** (ADSP firmware loads, docs/31). It boots standalone from the flashed `boot` partition (kernel + initramfs);
the mainline boot image is **flashed to `boot`** (2026-11-22), so the phone boots Alpine by itself; test kernels are still RAM-booted with `fastboot boot`.

Per-hardware status (working / partial / not working / untested) is tracked in **[docs/27-hardware-status.md](docs/27-hardware-status.md)** — keep it current.
Biggest gaps: cellular modem, camera and sensors (CDSP/SLPI firmware is extracted, not enabled), audio beyond the speakers (microphones, earpiece, headset), charging control (fast charge), suspend, standalone boot.

## Repository layout
| Path | What |
|---|---|
| `docs/` | Bring-up log, hardware map, research, per-feature results (index: [docs/README.md](docs/README.md)) |
| `scripts/build_mainline_boot.py` | Builds the `fastboot boot` image (kernel + initramfs with USB-NCM shell, switch_root hook) |
| `scripts/build_alpine_rootfs.py` | Builds the Alpine rootfs image (no sudo, no containers; user namespace + qemu-user) |
| `scripts/build_debug_initramfs.py` | Base initramfs / boot image builder reused by the above (busybox + NCM gadget) |
| `scripts/fetch_alpine_pkgs.py` | Fetches a few Alpine packages for the initramfs (iw, wpa_supplicant, ...) |
| `scripts/export_patches.py` | Exports the kernel commits to `patches/series/` |
| `configs/bitra_defconfig` | `savedefconfig` of the working kernel build |
| `patches/` | The kernel changes as a `git am` series (`patches/series/`, base in `patches/BASE`) |
| `tools/` | `flash-boot.sh` (hash-checked flash of the `boot` partition from the phone), small freestanding aarch64 helpers (`bitra-reboot`, `bitra-drm`, `bitra-evtest`, `bitra-failnth`), Python hardware tests that run on the phone (`bitra-haptic.py`, `bitra-nfc.py`, `gpu-hang-test.py`, `nm-wifi-from-wpa.py`, `tone.py`, `extract-dsp-firmware.py`) and `gpu-stress.sh` and `soak.sh` (display soak / fault-injection harness) |
| `third_party/` | Fetched/vendored inputs (Alpine packages, touch driver series); mostly gitignored |
| `releases/`, `build/` | Build outputs (gitignored) |

## How to build and boot
Needs: a Linux build host with an aarch64-capable clang (the AOSP `clang-r563880c` of the `bitra` workspace is used by default), `qemu-user` binfmt for aarch64,
`unshare` with a subuid/subgid range, `mke2fs`, and the phone reachable through the `bitra-agent` (`ssh mac ...`, see docs/18). Environment variables: `BITRA_REPO` (workspace checkout),
`MAINLINE_SRC` (kernel tree), `MAINLINE_OUT` (kernel build dir), `FIRMWARE_DIR` (linux-firmware, default `/usr/lib/firmware`).

1. **Kernel** (in the kernel fork, branch `bitra`): `cp configs/bitra_defconfig arch/arm64/configs/`, then `make O=../out ARCH=arm64 LLVM=1 bitra_defconfig` and
   `make O=../out ARCH=arm64 LLVM=1 LOCALVERSION= -j$(nproc) Image.gz modules dtbs` (a DT change needs `dtbs` as well as `Image.gz`; `LOCALVERSION=` keeps the release `7.2.0-bitra` so modules match across builds).
2. **Rootfs**: `python3 scripts/build_alpine_rootfs.py --size-mb 600` -> `releases/alpine-rootfs.ext4` (+ `.sha256`). Installs the kernel modules of `MAINLINE_OUT`.
3. **Boot image**: `python3 scripts/build_mainline_boot.py a-N --cmdline-extra "bitra.root=userdata panic=0 consoleblank=0 earlycon=efifb keep_bootcon console=tty0 loglevel=4"`
   (put important parameters first: the boot image truncates the kernel command line).
4. **Boot**: `ssh mac "stage --sha256 H a-N.img" < releases/a-N.img`, `ssh mac to-fastboot`, `ssh mac "ramboot a-N.img"`. (A fastboot entered with the hardware keys makes the OPLUS ABL refuse images; `to-fastboot` from a running OS works, also from Alpine.)
5. **Install the rootfs** (first time only; wipes `userdata`): see [docs/25-alpine-rootfs.md](docs/25-alpine-rootfs.md) (tmpfs in RAM, `put`, `sha256sum`, `dd`, read back and compare).
6. **Wi-Fi credentials** are never baked into images: `ssh mac "put wpa.conf /etc/wpa_supplicant/wpa_supplicant.conf"`.

## Safety rules used here
- Never write the firmware LUNs (xbl, abl, aop, hyp, modem, persist, ...); only `userdata` is written. Backups of the original partitions live in the `bitra` workspace.
- The `boot` partition holds the mainline image since 2026-11-22; the old Droidian image is backed up (`bitra/backups/boot-before-mainline-20261122/`, restore with `fastboot flash boot`). The recovery path is the key-combo fastboot (vol-down + power); `fastboot boot` of a test image works from it.
- Verify every transfer by hash (`stage --sha256`, `sha256sum` on the phone) and every flash by readback.
- Do not enable charger drivers that write float voltage / current limits until checked against the stock values (docs/26).

## Kernel work worth upstreaming
Bugs found by fault injection / KASAN soak and fixed in the fork are listed in [docs/24-upstream-candidates.md](docs/24-upstream-candidates.md)
(14 candidates: typec, qcom-wdt, pinctrl, a drm/msm lifetime series, ...). The deterministic fail-nth sweep is parked; state and resume steps are in docs/known-issues.md and docs/23.
