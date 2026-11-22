# Mu-Silicium UEFI on bitra, and the XNU / HakiOS idea (2026-11-23)

Goal: try the Darwin kernel (XNU) through the HakiOS project, at least to a framebuffer boot (and a USB NCM shell if it exists).

## HakiOS review (source read, nothing of it built or run)
- HakiOS ([oosexgang/hakios-xnu-kernel](https://github.com/oosexgang/hakios-xnu-kernel), POCO X6 fork [JosephMontfort/hakios-xnu-kernel-garnet](https://github.com/JosephMontfort/hakios-xnu-kernel-garnet)) is an XNU port that
  runs **as a UEFI application** (`loader.efi`, built without EDK2) on top of a Mu-Silicium UEFI that is started with `fastboot boot`. Payload (kernel + images + boot args)
  follows the UEFI image and is copied to reserved RAM by a BootShim.
- No SM8250 device package exists (only SM7325 / SM7435 phones). Porting is data (`board.dts` + `soc.dtsi` from the phone's live DT, framebuffer address from the loader log).
- **No USB NCM / gadget driver.** The loader has a small fastboot-protocol server on top of the UEFI USB-gadget protocol (needs UEFI USB device mode); debugging is
  the framebuffer plus loader logs. A network shell would be a new XNU driver.
- Writes: only to a partition named `darwin` (GUID/LBA-checked) and `logdump`; bitra has neither, so by default nothing is written. No network code found in the loader.
  The prebuilt binaries in the garnet fork were NOT used; Darwin user space needs an Apple IPSW the user supplies (identity.h, placeholder otherwise).

## Mu-Silicium for bitra
Project-Silicium/Mu-Silicium has `Platforms/Realme/bitraPkg` (SM8250-AC, status table "Inactive"). Built from source, RAM-booted with `fastboot boot` (nothing flashed):

| Step | Result |
|---|---|
| Release build, RAM boot | blank screen, phone resets to Alpine after ~1 min (release logs nothing) |
| DEBUG build | log is drawn on the framebuffer (FrameBufferSerialPortLib): works, too fast to read -> `PcdFrameBufferDelay` per newline |
| UEFI stops in `UFSDxe.efi`: `ufs_error_log: 28b`, `ASSERT_EFI_ERROR (Device Error)` `UFS.c +1029` | fixed by `EnableUfsIOC` = 1 (bitra had 0, the working sibling alioth has 1) in `ConfigurationMapLib.c` |
| Next stop: `pil-abl Failed to read from partition / Failed to load ELF file / uefipil.cfg auto processing failed, target panic` | `[AUTO] ABL` in `Binaries/bitra/RawFiles/uefipil.cfg` makes PIL load the `abl` partition (LUN 4, type GUID matches the real GPT) and that read fails; emptied the `[AUTO]` list |
| Result | **UEFI reaches BDS**: DXE drivers (UFS, SDCC, PMIC x5, SPMI, RPMh, clocks, USB init, SMBIOS, ACPI) load, the Silicium logo shows, `[Bds] Booting USB Storage`, `USB boot desired, but no USB devices found`, then it resets into Alpine (nothing to boot) |

Minor errors in that log, not fatal: `CPU Vectors region not present in cfg file` (ArmCpuDxe), `Rpmh Sleep callback registration failed (0x...03)`, `PlatformUpdateSmBiosType17: Failed to get DDR Speeds`.
The `abl` read failure itself was not diagnosed (probably the UFS driver does not expose LUN 4 to PIL, or the ABL image check); it is skipped, not solved.

## What it means for XNU
- **Framebuffer boot of the UEFI: reached.** The HakiOS loader could draw on the same framebuffer (0x9C000000, 1080x2400x32).
- **USB NCM shell: not possible in this stack.** Mu-Silicium lists USB device mode as not working on bitra (there is no USB device after the UEFI starts), and HakiOS has no network gadget anyway.
- Remaining work before a Darwin kernel runs: get `loader.efi` into the firmware volume (or a USB/ESP) as the boot option, hand the payload over (boot-image ramdisk), write the bitra `board.dts`/`soc.dtsi`, and
  provide Apple's `identity.h` from an IPSW. None of this is done.

## Reproduce
Sources are kept outside the repo (`~/projects/mu-silicium-src`): `git clone --recursive --depth 1 https://github.com/Project-Silicium/Mu-Silicium`, a Python venv with `pip-requirements.txt`,
the AOSP clang (has lld-link), a shim directory with an empty `uuid/uuid.h` plus a `libuuid.so` symlink (no sudo, host has only the runtime library), and
`sed -i 's/"scope": "edk2-build"/"scope": "unused-x86-nasm"/' Mu_Basecore/BaseTools/Bin/nasm_ext_dep.yaml` (the x86 nasm NuGet package needs Mono and is not used for AArch64).
`uefi/mu-silicium-bitra/` holds the changes as patches (`mu-silicium-bitra.patch`: `EnableUfsIOC`, `PcdFrameBufferDelay`; `mu-silicium-binaries-bitra.patch`: the `[AUTO]` list) and `build.sh`.
Build `python3 build_uefi.py -d bitra [-r DEBUG]`, then `ssh mac "stage --sha256 H x.img"`, `to-fastboot`, `ramboot x.img`. If the UEFI hangs, hold power ~15 s and power on normally (a keys-entered fastboot also works for `ramboot` here).
