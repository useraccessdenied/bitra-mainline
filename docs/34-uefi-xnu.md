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

## HakiOS loader.efi runs on bitra (2026-11-23)
`loader.efi` built from the HakiOS tree (`arch/arm64/boot/build.sh`, clang + lld-link, 76 KB, placeholder identity), embedded in the UEFI firmware volume (`FILE APPLICATION` GUID
7A6E1A52-0C5D-4E3B-9B1F-4C1D2A0B7E01 in `bitraPkg/Include/RAW.inc`) and registered as a Boot Manager entry "HackiOS" in `PlatformBootOptions.c`. With `PcdFrameBufferDelay` back at 10 ms the boot is fast again.
Owner photo of the screen: the HackiOS banner (the text says "POCO X5 Pro", hard-coded) and
`XNULOADER v3 | UEFI recovery`, `CurrentEL=1 MIDR=51df805e CNTFRQ=19200000 image=a1000000`, `display 1080 x 2400 at 9c000000`, `platform qemu-virt` (no bitra board package, so it falls back),
`no payload at f0000000 (magic 0)`, `usb: start failed 800000000000000e` (EFI_NOT_FOUND: no UEFI USB-gadget protocol, as expected), `USB recovery unavailable; holding in loader`.
So: UEFI -> boot manager -> HakiOS loader -> framebuffer text works; what is missing is a payload (kernel + userland) and a bitra board package.

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

## XNU kernel built for bitra (2026-11-23, host only, nothing run on the phone yet)
Plan: HakiOS "garnet" tree (Darwin userland 16.5 / xnu-8796.121.2, no pointer authentication; the main HakiOS tree's Darwin 26/27 needs a team tree that is not public).
Owner-supplied IPSW: `iPhone10,3,iPhone10,6_16.5_20F66_Restore.ipsw` (6.17 GB, BuildManifest checked: 16.5 / 20F66; kept outside the repo, not unpacked yet).
- `tools/hakios-device.py new bitra --soc sm8250 ... --fdt <stock kona v2.1 dtb>` made `devices/bitra` (copy in `uefi/hakios-bitra/device-package/`). 12 of 16 SoC values came from the tree; missing: soc_cmd_db, soc_mpss_mem, modem_ipa_fw_at, soc_pas_mpss (all modem related). All 23 phone drivers are left out to begin with.
- Build prerequisites on this immutable host without root: autoconf 2.72, automake 1.17 (Perl `threads` disabled in its installed Config.pm; missing core Perl modules File::Compare/Copy/Find taken from the perl 5.44 source), libBlocksRuntime + libdispatch (tpoechtrager/apple-libdispatch; block.cpp removed and one stub symbol because it does not compile against libstdc++ 16), cctools-port (ld64, nm, otool ...) and the iPhoneOS 16.5 SDK (theos/sdks), the uuid header shim from the Mu-Silicium build. Script: `uefi/hakios-bitra/toolchain2.sh`, environment `xnu-env-host.sh`.
- `xnu-deps/setup.sh` then `./xnu-build.sh -j16 -k BUILD_DSYM=0` (dsymutil is not in the AOSP clang; the dSYM is optional). The build ends with the documented `check_all_exports` error; the kernel is linked.
- Config: `devices/bitra/configs/bitra.config` leaves every phone driver out; `CONFIG_HAKIOS_ADRENO710=y` is built in only because HakiosGPU (always built) needs symbols from an Adreno driver (inert without `adreno=N`). Built in: adreno710 + virtio drivers; boot arg `ufs=2`.
- Result: `hakios-kernel-bitra`, Mach-O arm64, 14.9 MB, `Darwin Kernel Version 22.5.0 ... xnu-8796.121.2`, sha256 `355dd2de...f907d5`. Untested: no payload image, no loader board entry for bitra, nothing booted.

## First XNU boot on bitra (2026-11-24)

The HakiOS loader (patched with a `bitra` platform: GICv3 0x17a00000/0x17a60000, selected by the framebuffer at 0x9c000000) starts the
iOS 16.5 XNU kernel (xnu-8796.121.2) on the phone from `fastboot boot` + the Mu-Silicium boot menu entry "HackiOS" (press Vol-up at the Mu logo).
Photographed on the panel: loader banner, `platform bitra`, `display 1080 x 2400 at 9c000000`, kernel mapped and entered (`jumping to fb41d4a8`),
then the kernel's own verbose log (iBoot version, IONVRAM, `Security policy loaded: ... Seatbelt sandbox`). The kernel's text and UEFI's debug
console draw over each other, so the screen is garbled. Not yet: root image (`hello`) result, anything past policy init, a clean log.

Payload delivery: a 15 MB copy by the boot shim with the MMU off never finished (phone stuck on the fastboot logo; tests with 80 B, 15 MB zero,
different destinations isolated it). The shim (`uefi/hakios-bitra/BootShim-payload.S`) now only leaves a mailbox at 0x9FEFF000 (FD tail) and the loader
copies the payload with caches on (`loader-bitra.patch`). Also fixed: a literal pool after the `_Payload` label shifted the FD copy.
Build: `uefi/hakios-bitra/mkbitraimg.py --payload payload.bin -o img` (payload from `xnuloader/mkpayload.py kernel=... ramdisk=...`).
