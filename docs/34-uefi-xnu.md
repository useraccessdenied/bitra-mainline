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
Sources are kept outside the repo (`~/projects/bitra/mu-silicium`): `git clone --recursive --depth 1 https://github.com/Project-Silicium/Mu-Silicium`, a Python venv with `pip-requirements.txt`,
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

### Userland runs (2026-11-24, later)
Kernel log pages (loader shows its own log and the kernel's log in 20 s pages after the run, `show_log_pages` in `loader-bitra.patch`, since the
kernel's console and UEFI's overdraw each other) show a complete boot: `Added memory device md0/rmd0`, `BSD root: md0`, `bsd_init: done`,
`load_init_program: attempting to load /sbin/launchd`, then `pid 1 exited (exit 0)` and the panic `initproc failed to start` - which is what the
test program `hello` (the root image) does by design. So the iOS 16.5 kernel runs on the SM8250 and executes a Darwin process.
Two bugs found on the way: (1) RAM keeps the previous run's payload across the warm reset and the loader reused it (its magic was still there),
so images sent later seemed to change nothing: the loader now takes the shim's mailbox first; (2) the kernel only gets its root image and
boot-args when `rd=md0` / ramdisk entries are present (`mkbitrapayload.py` puts small entries first and pads the end).
Not working / open: display is the loader's text only (XNU draws 1125x2436 on the 1080x2400 panel), `cpus=1`, no storage/touch, no Darwin userland
image yet (the 2.5 GB system image from the IPSW must come from somewhere other than the boot image: UFS or the Alpine partition).

### System image built (2026-11-24)
`sysimage/unpack.sh` on the owner's iPhone10,3/10,6 16.5 20F66 IPSW (Apple files stay in `hakios-src/garnet/sysimage`, outside the repos), then
`PREBUILT=1 REST=1 SYSTEM=1 userland/build.sh`: `userland/system.apfs`, 2,475,704,320 bytes, sha256 a70a25e6f589913ded1a39111687a0c55d526cc725de1d846f2dd11dadd6677d
(not published: it holds Apple's files). It cannot travel in the fastboot boot image (2.4 GB); HakiOS sends it over USB (`xl ramdisk`), which bitra lacks.
Plan: put it in unused space of `userdata` (past the Alpine ext4; only `userdata`/`boot` may be written) and read it through the UFS driver (`ufs=2`).
Logs: the loader dumps the whole kernel log at once; `pages=N` among the payload's arguments shows it in N-second pages. Mu's `PcdFrameBufferDelay` is 0 again.

## `darwin` partition created, system image written (2026-11-24)
- Owner approved a GPT edit on the UFS LUN that also holds the firmware partitions (safeguards below) to give HakiOS a dedicated partition.
- Before: `userdata` = sda11, 59,094,515 x 4 KiB sectors (ext4 filled all of it, 1.85 GB used). Backups in `backups/gpt-20261124/`
  (primary and backup GPT sectors, `sfdisk -d`, original LBA 0; the rootfs tarball, sha256 2c4b4b18..., stayed on the build host).
- Steps: RAM-booted the initramfs without `bitra.root` (image `d-1`), copied e2fsck/resize2fs/sfdisk plus musl libs from the rootfs into RAM, `e2fsck -f`,
  `resize2fs /dev/sda11 16777216` (64 GiB), then `sfdisk --no-reread` with a script that changes only sda11's size and adds
  `sda12 : start=19460616 size=16777216 name="darwin"` (type Linux data). sfdisk also rewrote the protective MBR (LBA 0); the original sector was restored with dd.
- Verified: entries 1-10 and the unchanged header fields byte-identical to the backup; only the two header CRCs, entry 11 and the new entry 12 differ.
  About 113 GiB at the end of the LUN is left unallocated.
- `scripts/write_darwin_part.py` writes an image to sda12 in 64 MiB chunks (stage, put, sha256 on the phone, dd), then reads the whole range back.
  A single `put` of the 2.4 GB file timed out (0 bytes arrived); 64 MiB chunks take about 4 s each.
- `system.apfs` (2,475,704,320 bytes, sha256 a70a25e6f589913ded1a39111687a0c55d526cc725de1d846f2dd11dadd6677d) is on sda12; readback hash matches, also after a reboot.
  Alpine boots from the shrunk `userdata` (63 GB, 2.5 GB used).
- Next: boot HakiOS with `ufs=2`/darwin root; the HakiOS UFS driver on the SM8250 controller is untested.

## Boot-image payload limit, gzip payload, storage blocker (2026-11-24, night)
- **Only about 12.5 MiB of the decompressed boot image reach RAM intact.** Per-MiB checksums printed by the loader (payload at 0xA03800A0)
  matched the host for MiB 0-11, MiB 12 was partly wrong and MiB 13-18 read as zeros (the loader is loaded at 0xA1000000, 12.5 MiB into
  the image; moving the ramdisk with `--ramdisk_offset 0x4000000` changed nothing). The earlier "15 MB payload copy hangs", the loop
  "kernel resets right after `jumping to`" and the failures of the 20-24 MB flash-root images all come from this: the tail of the kernel file was missing.
  The 16 MB image of the first working boot only lost the unused end of the kernel file.
- **Fix:** `mkbitraimg.py --gz` carries the payload gzip-compressed (20.2 MB -> 5.5 MB); the loader (`gunzip()` in `loader.c`, a small
  freestanding inflate) inflates it into the payload region and checks CRC-32 and size (`bitra: inflated ... CRC ok`). Verified: the flash-root
  payload (real `flashboot.apfs` boot volume, `stage0` as launchd) runs and the kernel halts at the end, then the phone returns to Alpine.
- **APSS watchdog:** read at start (`en=0 sts=0 bark=7ffff bite=fffff`): the bootloaders leave it disabled, so it was not the cause of the resets.
- **No UFS block device in Mu's UEFI:** `ufs: connect: 157 handles, 3 connected`, no BlockIo, no PartitionInfo. `UFSDxe` (Qualcomm binary from
  the phone's firmware) is in the DXE list but exposes nothing, so the loader cannot serve `darwin` (`ufs=2` needs it). Next: read why from Mu's
  in-RAM debug log (`fwlog:` lines, loader scans 0x9FFF7000), then either fix the UEFI side or use the kernel's own UFS host controller driver (`ufs_native=`).
- **`darwin` partition now holds Apple's layout** (`rootfs.apfs` + both cryptexes back to back, 8,365,539,328 bytes, sha256 9efb156f...; the piece hashes match
  the HakiOS documentation 9f430a58 / 2279bf44 / 6b9d1f09). Its type GUID is still the Linux data type (a write path would need APFS container type 7C3457EF-0000-11AA-AA11-00306543ECAC;
  reads do not check it). The RAM side: `flashboot.apfs` (4 MB boot volume, `CRYPTEXES=flash FLASHBOOT=1 PREBUILT=1`) as `resident`, `root.apfs` as `ramdisk`.
- Test images are kept in `releases/` (gitignored): `xnu-bitra-H.img` has 10 s pauses in the loader (after the firmware-log lines and before the jump).

## Image H result: the firmware UFS driver runs, but exposes no block device (2026-11-25)

Photos of image H (loader pauses 10 s). Mu's own log (RAM log buffer at 0x9FFF7000, read by the loader) says:

    Boot Device : UFS.
    UFS INQUIRY ID: SAMSUNG KLUEG8UHDB-C2D1 1903.
    UFS Boot LUN: 1.
    restore_to_ufs_from_buf: Backup region is corrupted either..
    boot_dev_ufs: 0x1
    BOOT: You are calling UFSFirmwareOps function now..
    ERROR: ufs fw head magic error!.   (twice)

So UFSDxe initialised the controller and talked to the disk (inquiry, boot LUN), and then only the firmware-update
path (UFSFirmwareOps) complained. Nothing in the log says why no BlockIo/PartitionInfo appears. The gzip payload
(5.5 MB -> 20.2 MB, CRC ok) and the kernel run are fine; this image (flashboot as md0, no root_apfs) mounts the
1-file boot volume, finds no launchd and halts, as expected.

Consequence: `ufs=2` cannot serve `darwin` (the loader needs BlockIo). The controller is live at 0x1d84000 (same
address as SM8250's `ufshc`), so the way forward is `ufs_native=1`, but the kernel's unit map (`ufs_native_map`,
`ufs_shared_pa` page) is built from the loader's BlockIo survey. For bitra the loader must instead publish a
synthetic unit list (LUN 0, 4096-byte blocks, 61,777,920 blocks) or the kernel must probe LUNs itself.
Also unknown: whether the controller's DMA (SMMU config) lets it reach the loader's `hc_area`.

## Images I and J: the kernel's own UFS driver on bitra (2026-11-25, built, not yet run)
- Kernel rebuilt with `CONFIG_HAKIOS_UFS=y` (`devices/bitra/configs/bitra.config`; the first bitra kernel had no UFS code at all).
- Loader (bitra, `ufs=2 ufs_native=1`, no PartitionInfo): publishes its own table, unit0 (LUN 0, 61,777,920 blocks of 4096) and
  `darwin` (start 19,460,616, 16,777,216 blocks, from `backups/gpt-20261124/gpt-after.sfdisk`), flagged `BLOCK_PART_SYNTH`, and offers
  the controller (0x1d84000) with its `hc_area`. UEFI's transfer list is kept and put back as before. Read only (`ufs_write` off).
- Kernel (`hakios.ufs.c`): for synthetic units the native map has no loader read to compare with, so it reads LBA 1 of the unit with
  its own driver and requires `EFI PART`.
- I = `root_apfs=ufs_darwin ufs=2 ufs_native=1 bootcpu=7 cpus=1`; J = the same without `bootcpu=7` (in case core 7 does not start).
  Both gzip payloads (5.7 MB). Unknown until run: whether the controller's DMA (SMMU) can reach `hc_area`.
- Patches: `loader-bitra.patch`, `kernel-ufs-bitra.patch`.

## Images I/J results and image K (2026-11-25)
- I (`bootcpu=7`): resets right after `jumping to`, no kernel output. J (core 0): the kernel boots with the UFS driver built in, finds the
  controller (CAP 1587031f, VER 300, HCE 1) and UEFI's list (9a12d000), whitelist self-test passes, and prints
  `native: transfer list switched from UEFI's 9a12d000 to this kernel's a3455000`; then the phone resets (nothing more on screen).
  After the switch the kernel rings a TEST UNIT READY (no data) as proof, so the controller's fetch of the list/UCD from the loader's
  image memory (a3455000) is what resets the phone (XPU/SMMU), not a data buffer.
- K = J with the list area in UEFI pages (`allocate_pages` BootServicesData; Qualcomm's UFSDxe keeps its list in its own pool).
  Still open if K also resets: the kernel's data buffers (`kmem_alloc_contig`, high RAM) and the core-7 start (I).

## Post-mortem log in RAM, and where the reset is (2026-11-25, images L/M)
- Photos were slow, so the kernel now mirrors its console into a 1 MiB ring at PA 0xf0000000 (loader reserves it with `allocate_pages`;
  `pm_put`/`hakios_pm_map` in `osfmk/console/video_console.c`). After a reset Alpine reads it (`tools/xnulog`: `insmod xnulog.ko`,
  `cat /proc/xnulog`; `echo > /proc/xnulog` zeroes it). Zero it and check it is all zeros before each run: then whatever is in it after
  can only be from that run (an empty ring = the run never reached the kernel's console).
- L (K + ring): log ends at `transfer list switched ... to this kernel's 99b26000` (list in UEFI pages): same reset as J/K.
- M (`ufs_native=3`, dry run: switch in/out/in, no command): no reset; the kernel runs to init and the user-space tests
  (19 of 23 checks pass; failing: the darwin mount [native reads off in this mode], the /private/var memory fs, a symlink, launchd.darwin).
  So the controller restart with a different list is harmless; the reset comes with the first command (the proof's TEST UNIT READY
  doorbell, i.e. the controller's first DMA fetch of this kernel's UTRD/UCD). Next: breadcrumbs around the doorbell (image N).
- Image N (breadcrumbs): the log ends at `proof: ringing slot 0 now (list 99b26000 run 1 HCS 10f IS 400)`; the `rung` line never prints, so the
  phone resets when the doorbell is written, i.e. at the controller's first DMA fetch of this kernel's UTRD/UCD (UTRD `10000000 0 f 0 99b27000 0
  800080 01000000`, sane). Image O (Mu with the stock `EnableUfsIOC = 0`): Mu does not boot at all (ABL goes to recovery); the patch's `EnableUfsIOC = 1` is
  needed on this phone. Remaining suspect: which memory the controller's DMA may reach (SMMU). Next: send the TEST UNIT READY through UEFI's own list
  and descriptor memory (no switch) to see whether DMA to UEFI's own pages works.
- Image P (`ufs_native=4`, TEST UNIT READY through UEFI's own list and its own UCD, kernel, no switch): resets at the doorbell too
  (`uefi-tur 1 ... ringing UEFI's slot 0 ... now` is the last line). Image Q (the same test from the loader at UEFI time, loader ring at
  0xf0100000 read with `insmod xnulog.ko pa=0xf0100000`): also resets (last line `uefi-tur: ringing UEFI's slot 0 now (HCS 10f IS 400 doorbell 0 run 1)`).
  So a doorbell from anything but UEFI's driver resets the phone (`androidboot.startupmode=hard_reset` in Alpine's cmdline afterwards),
  from the loader too, with UEFI's own memory and format. Not the kernel's mappings, not our memory, not our command.
- Linux has the UFS controller (SIDs 0xe0, 0x4e0) in a translated IOMMU domain (apps SMMU 15000000, SMMUv2, 87 stream groups, 74 context banks;
  `iommu_groups/8: DMA 1d84000.ufshc`). Theory: UEFI's driver maps its buffers in the SMMU around each command; an unmapped DMA is an SMMU fault
  that the secure side turns into a hard reset. Image R: the loader dumps the SMMU stream matching entries (`smmu_dump=1`) and sets the entries
  matching the UFS stream IDs to bypass (`smmu_bypass=1`) before the TEST UNIT READY.

## The UFS reset is the SMMU (2026-11-25, image S) 
Loader ring of S (apps SMMU 0x15000000, read at UEFI time; reading is safe): `sCR0 2d0406` (USFCFG=1: a transaction of a stream that no
group matches is a fault), `IDR0 4c017e57` (87 stream groups), only 5 valid SMR: ids 0x4a0, 0xc0, 0x0, 0x20 and 0x820 (mask 0x402); none matches the UFS stream IDs 0xe0 / 0x4e0
(DT `iommus`). UEFI's UFSDxe maps the controller only around its own commands; a doorbell from anyone else is a DMA of an unmatched stream: SMMU
fault, hard reset (`androidboot.startupmode=hard_reset`). This explains J..R (kernel and loader alike, UEFI's memory or ours).
Fix under test (image T): make a free stream group for each of 0xe0 and 0x4e0, S2CR type bypass first, SMR valid last, then retry the
TEST UNIT READY. The kernel's own driver will have to do the same (map 0x15000000, same two groups) before it takes the controller.
- Image T: the two new groups (0xe0, 0x4e0, SMR valid, S2CR type 1 = bypass) were written, but the S2CR reads back `20000` (type 2 = fault): this SMMU
  does not accept plain bypass from the non-secure side (idle groups are `...200ff`, also fault). Then the loader's TEST UNIT READY died in a loader
  exception: UEFI's list address (UTRLBA 9a135000) now held code (UEFI frees its list memory after use and reuses it; the list in UTRLBA is stale, so it
  cannot be used for commands, and the loader-side TUR test was dropped). Image U: a stage 1 context bank (free CB, `CBAR` type 1, 64-bit, TCR 39-bit 4 KB WB,
  MAIR0 0xff) with one identity table of 16 x 1 GB blocks (`0x741`), `SCTLR.M`, and the two groups translate (S2CR type 0, that bank); the kernel's
  own driver then does its proof and reads (`ufs_native=1 smmu_bypass=1`).
- Linux's view (Alpine, `/dev/mem` mmap of 0x15000000, read-only): UFS streams 0x4e0 (group 2) and 0xe0 (group 3) -> S2CR type 0, context bank 6;
  bank 6 `CBAR 0001f300` (stage 1, stage 2 bypass, MemAttr f, BPSHCFG 3). **Reading the registers of an enabled context bank hangs the bus** (reading bank 6's SCTLR
  from Linux did; so did my own read-back after `SCTLR <- 1` of bank 69 in image X, which is why the loader ring stopped there, not at the write). Context banks
  64-69 read fine while unused (CBAR 0, SCTLR e0); the SCTLR read of bank 63 hangs (it is enabled). Next (image Y): same, without reading banks back after enabling, CBAR 0001f300.

## The kernel's own UFS driver reaches the storage (2026-11-25, image Z)
Images X/Y: enabling a translated context bank (writing `SCTLR` with `M`) hangs the bus on this SMMU, and so does reading any enabled bank, so no page table.
Image Z does what Linux's Qualcomm SMMU code does for streams that should bypass (the hypervisor refuses S2CR bypass; Linux reserves the **last
context bank (73) as a bypass bank**: `CBAR` type 1 `0x10000`, `SCTLR.M` left 0, and bypass groups get S2CR type 0 with that bank): the loader writes
`CBAR(73) = 0x10000`, makes free groups 4 and 5 for the stream IDs 0xe0 and 0x4e0 with S2CR 73, and invalidates (`smmu_bypass=1`).
Result: no reset. The kernel's own transfer list is fetched, the proof TEST UNIT READY of LUN 0 runs (`OCS 0, response 21`) and the drive answers
`status 02, sense 2/04/02` (not ready, initializing command required: the unit has to be started, as Linux's sd driver does). The driver took that for
a failed proof and fell back to the loader (the loader has no Block I/O here), so the darwin mount failed with EIO.
Next (image AA): the driver treats a CHECK CONDITION to TEST UNIT READY as an answer, and on 2/04/02 sends one **START STOP UNIT, plain start** to the unit and asks again.
That is one new opcode in the driver's whitelist (`hc_refusal`): `0x1b` only with CDB4 = 0x01 (start, no LOEJ, power condition 0), not immediate, no data, only to
a unit reads may go to; stop, LOEJ, every power condition and the well-known units stay refused (self-test cases added). It writes no data.
- Image AA/AB: a TEST UNIT READY, and a READ of LUN 0, answer `2/04/02` (not ready, initializing command required); a plain START STOP UNIT to LUN 0 is refused by the drive
  (`5/24/00`). So the unit takes no I/O: the device is likely in a low power mode. The proof now counts a controller-run command with a valid response as proven.
  Image AC: the driver's one non-read command changes to what Linux's ufshcd sends to wake a UFS device: START STOP UNIT of the **device well-known unit
  (0xD0), power condition ACTIVE (CDB4 = 0x10)**, not immediate, no data. Every other START STOP UNIT (a normal unit, other power conditions, start/stop/eject
  bits) and every other use of a well-known unit stays refused (self-test cases). It writes no data.
- Image AC: the device-unit ACTIVE wake works (`START STOP UNIT` of 0xD0, power condition ACTIVE: response 00 status 00) and the TEST UNIT READY then passes. The first block-1 read
  completed without an error line but the bytes were not `EFI PART` (image AD dumps blocks 0-2 on that failure). Image AD: the run did not get that far: the kernel refused to start
  (`UEFI's command descriptor is not where it was`): UEFI's list memory (UTRLBA 9a136000) held code again. Mu's UFSDxe frees that memory after use and it is reused, so the driver's
  check that UEFI's slot 0 holds a read is only said now, not required (image AE); UEFI's list is put back by the address in the registers.
- Image AE/AF: with the stale-list check informational, the run reaches the proof (wake OK, TEST UNIT READY OK) and a READ of LUN 0: the controller says success (`OCS 0`, response `status 0`,
  residual 0, PRD target 1_02acc000, 4096 bytes, a correct READ(10) of LBA 1), but the whole 256 KB buffer stays zero. So the data DMA does not arrive where the CPU looks. Suspects:
  the buffer is above 4 GB and cached. Image AG: the data buffers are in the loader's UEFI area (below 4 GB, mapped uncached, behind the lists).

## iOS 16.5 root volume boots from the phone's UFS `darwin` partition (2026-11-25, image AG)
Image AG (`root_apfs=ufs_darwin ufs=2 ufs_native=1 smmu_bypass=1 cpus=1`, kernel with `CONFIG_HAKIOS_UFS`, loader with the SMMU bypass bank and the DMA buffers in its UEFI area):
`unit0 is LUN 0: its GPT header read natively`, then the kernel's own driver serves `/dev/ufs_darwin`: `apfs: volume 0 "SydneyF20F66.D22D221OS" ... 142299 files, 136413 directories`
mounts read only as the iOS volume, the root is switched onto it, the System Cryptex (container 1 at 5368 MB) and the App Cryptex (container 2 at 7968 MB) mount, `=== 45 checks, 0 failed ===`.
Then `exec /sbin/launchd.darwin: No such file or directory` and the kernel halts (cleanly: the phone returns to Alpine). Nothing was written to the phone (`ufs_write` off).
What it took, in order: (1) gzip payload; (2) Mu's UFSDxe exposes no Block I/O, so the kernel's own UFS driver (`ufs_native`) with a table from the loader; (3) a post-mortem log in RAM (kernel `0xf0000000`,
loader `0xf0100000`; `tools/xnulog`) since the failures were hard resets; (4) the resets were the apps SMMU (`0x15000000`): `sCR0.USFCFG=1` and no stream group for the UFS stream IDs 0xe0/0x4e0, so
the controller's first DMA faulted; plain S2CR bypass is refused, enabling a translated context bank hangs the bus; Linux's own trick works (the last context bank, 73, with `CBAR` type 1 and `SCTLR.M` 0,
bypass groups with S2CR type 0 -> that bank); (5) the unit answered `2/04/02` until the **UFS device was woken** (START STOP UNIT to well-known unit 0xD0, ACTIVE; one new opcode in the driver's
whitelist, narrow, self-tested); (6) UEFI's list memory is stale (freed and reused), so its content is only said; (7) read data never arrived in kernel memory above 4 GB (cached): buffers are in the loader's UEFI pages (below 4 GB, uncached).
Open: why (7) (address above 4 GB or the cache attributes) is not known; throughput not measured (uncached 256 KB slots); `bootcpu=7` still resets; `launchd.darwin`; the SMMU bank and groups are set by the loader (`smmu_bypass=1`), not the kernel.

## Apple's launchd runs (2026-11-26, image AH)
`launchd.darwin` is not a file on the iOS volume: it is the name of the launchd that only the RAM-root recipe's `system.apfs` has. On the flash recipe the root is Apple's own volume
and its launchd is `/sbin/launchd` (525,088 bytes, decmpfs). The prebuilt `init` I used (`PREBUILT=1`, no ld64 for the Darwin tools) predates the source's mapping of the name for `flash_root_mode`,
so the image needs an rc that execs `/sbin/launchd` itself: `uefi/hakios-bitra/rc.launchd.flash` (`RC=rc.launchd.flash PREBUILT=1 FLASHBOOT=1 CRYPTEXES=flash ./build.sh` in `userland/`).
Image AH: the root pivots onto the iOS volume, `exec /sbin/launchd`: `Darwin Bootstrapper Version 7.0.0 ... launchd/RELEASE_ARM64`, its boot tasks, and ~21 services spawned from our `/redwood` LaunchDaemons:
backboardd, SpringBoard, containermanagerd, cfprefsd, notifyd, logd(+helper), lsd, powerd, runningboardd, usermanagerd, wifid, distnoted, fseventsd, datamigrator, iconservicesagent, MobileGestaltHelper, ACCHWComponentAuthService, var_store...
backboardd creates 1125x2436 BGRA surfaces and swaps them to the (mini) framebuffer (several IOMobileFramebuffer selectors not implemented). Noise: `lsd` "denied attempt to escape CPU monitor (missing required
entitlement)" 583 times and `minisandbox: privilege 1015 refused to lsd` (the AMFI/Sandbox stand-ins), `map_with_linking_np: region 0, not code signed` for our test binaries. The 90 s `loader_return_after`
brought the kernel back at ~140 s of kernel time (log 246 KB in the loader), the phone went to Alpine by itself.
Faster logs: the screen is the slow part (each console line is drawn and the framebuffer scrolled; launchd's volume throttles the whole boot). Image AI: `vcquiet=1` feeds the RAM ring but skips drawing, the kernel ring is 8 MiB and
WRAPS (keeps the newest 8 MiB; `tools/xnulog/readring.py` unrolls a dump), the loader ring moved to 0xf0800000 (`insmod xnulog.ko pa=0xf0800000 size=0x100000`; the kernel ring is `pa=0xf0000000 size=0x800000`, the module defaults).
- `loader_quiet=1` (image AJ): the loader skips its photograph pauses, writes the kernel's log into its own ring (now 4 MiB at 0xf0800000, `insmod xnulog.ko pa=0xf0800000 size=0x400000`) instead of drawing it, one summary line. The firmware's own on-screen logging
  is `DebugLib` through `FrameBufferSerialPortLib`; a DEBUG build prints (`PcdDebugPrintErrorLevel 0x8007EE0F`), a RELEASE build does not (level 0): image AK = AJ's payload with the RELEASE Mu (`EXTRA="-r RELEASE" sh uefi/mu-silicium-bitra/build.sh`,
  `mkbitraimg.py --mode RELEASE`); not yet run on the phone.
- Image AK (RELEASE Mu, `loader_quiet=1`, `vcquiet=1`; 2026-11-26): runs like the DEBUG images (23 services spawned, `kernel log: 280092 bytes, in the loader ring at f0800000`, phone back in Alpine by itself). Mu prints nothing; the `fwlog:` lines in the loader ring are
  Mu's log buffer text left from earlier boots (it keeps text across resets).

## All 8 cores, and the iOS UI (2026-11-26, image AL)
Image AL = AK with `cpus=8` (kernel on core 0, no `bootcpu`): the kernel registers cores 0-7 (MPIDR 0x000..0x700), starts the big cores 4-7 first and the small 1-3 later with PSCI CPU_ON over SMC (the same conduit Linux uses here: `PSCIv1.1`, `SMC Calling Convention v1.1`),
`GenericARMPE: the slower cores started too: 8 processors running`, 45 checks 0 failed, 27 launchd services, and **the owner saw the iOS UI come up: SpringBoard home screen with the dialer and apps** (touch is not wired yet; the display geometry is the UEFI framebuffer 1080x2400
under 1125x2436 surfaces). Kernel time to launchd dropped from ~50 s to ~30 s. At `loader_return_after` PSCI stops the other cores (`psci: cpu 6 ends the system`) and the boot processor returns to the loader.
Log: 430 KB in the loader ring; the unimplemented-service noise is SpringBoard asking launchd for services the image does not have (sleepd, chronod, commcenter, biome, mobileactivationd ...).

## Touch: the Synaptics S3908 driver (2026-11-26, images AM-AO)
`drivers/input/hakios.synaptics.c` (copy in `uefi/hakios-bitra/`): I2C by hand on GPIO 36 (SDA) / 37 (SCL), address 0x4b, interrupt GPIO 39 (read as a level), reset GPIO 38; TouchComm v1 from the phone's own answers
and the working Linux driver; samples go to `/dev/hakios-touch` as a fraction of the panel. Image AM (`touchscreen=1`) reset the phone ~2 s after launchd started with no `touch:` line; AN (a line before every access)
stopped at `the interrupt line (gpio39) to an input with a pull-up`: **writing GPIO 39's registers resets the phone** (reading all of GPIOs 36-39 is fine: bootloader state is plain GPIO, no pull). The chip drives its interrupt line, so AO writes
only the I2C pins, and GPIO 38 (reset) only if the chip does not answer, every register write logged first. Power of the chip's two PM8150C supplies is not switched by this driver (whatever the boot loader left).
- **Why runs sometimes went to recovery (fixed, image AR):** the Mu patch had Mass Storage as boot option 0 (hidden) and HackiOS as option 1; without a Vol-up press in time Mu tried the empty mass storage first, failed, and the phone reset into recovery.
  `PlatformBootOptions.c` now has HackiOS first (no key needed).
- **Pin controller writes are blocked before the OS handoff (images AP, AR):** from the loader (UEFI up) a no-op write of a pin's CFG back to itself resets the phone, for gpio36 and for gpio0; reads are fine
  (the scan of gpio0..179 shows 47 pins configured by the firmware, e.g. gpio133-145 `CFG 1`, gpio146-179 `CFG 801`). Image AS (`tlmm_test=2`): exit boot services first, then the same writes, then PSCI SYSTEM_RESET.

## Touch screen works (images AT..BB, 2026-11-26)
- **Raw TLMM (pin controller) writes reset the phone from every state tried**: UEFI up (AQ/AR), after ExitBootServices (AS), any pin (gpio0/36/50), via SCM IO_WRITE (AU: returns -2, no effect). Not the mapping (AT: the page is Device-nGnRnE, MAIR byte 0). Reads work, but the raw read view is not trustworthy (gpio38 CFG read 0 after a successful protocol ConfigGpio).
- **Mu's own protocols write fine** (AV found the GUIDs by listing every protocol of every handle and matching them to the Qualcomm driver binaries; layouts from Qualcomm's QcomPkg/Include/Protocol): TLMM `ad9aec18-7bf0-4809-9e96-3012309f3df7` (ConfigGpio/GpioIn/GpioOut, EFI_GPIO_CFG macro), I2C `b27ae8b1-3e10-4d07-ab5c-eb9a6dc6fa8f`, PMIC VREG `22d38d3d-e8b6-4f8f-9c26-bceb07d6cb68`. PMIC device 2 = PM8150C (LDO1 = l1c 1.8 V, LDO11 = l11c 3.1 V); `VregControl` hangs forever from the loader (AX, AY), the I2C protocol only registers the buses Mu uses (instances 2, 6, 12 (= SE3, the haptics bus at 0xa8c000, an AW8697 answers at 0x5a), 16, 17), not the touch engine (SE5).
- **What works (AZ/BA/BB)**: the loader (`touch_pins=1`) sets the pins through the TLMM protocol (gpio36/37 function 1 "qup13" with pull-up, gpio38 reset high, gpio39 input); the kernel's touch driver powers the chip through RPMh (raw RSC writes are NOT blocked: `ldoc1` 1.8 V, `ldoc11` 3.0 V from the command database), votes the QUP1 clocks (SM8250 GCC offsets match), and drives the serial engine at 0xa94000 as an I2C master (GENI firmware protocol 3, FIFO mode, 400 kHz: divider 2, 24 source clocks per bit). GENI status bits: GP IRQ n is bit 9+n (NACK = bit 10), bit 7 is RX data ready (not an error; image BA took it for one). The S3908 answers "TouchComm v1, mode 01, part s3908PR0-15.0, 8640 x 19200, 10 touch objects"; ~1700 reports, 0 bad; strokes: first move after ~45 ms, moves never more than 3 ms apart.
- DWC3 (USB, 0xa600000) probe (AX): clocked and readable after Mu's fastboot, core ID 0x33313130 (DWC_usb31), GCTL in host mode (PRTCAPDIR 1), no event buffers, DEVTEN 0: idle; a gadget driver would start from scratch (PHY, device mode, events, EP0, bulk).
- The three `smc` calls inside Mu's TLMMDxe are TZ feature probes (SCM info service, IS_CALL_AVAILABLE), not an unlock.
- Next: UI speed (5-19 frames a second; apps render on the CPU): the cpufreq driver (EPSS 0x18591000, three groups: the SM8250 layout) enabled for bitra, image BC.
- **cpufreq result (BC, 2026-11-26):** raw EPSS writes (0x18591000) and the RPMh BCM DDR vote (16383 on MC0/SH0) are allowed and do not reset the phone. Groups: cores 0-3 (A55) row 13 -> 16 = 1804 MHz, cores 4-6 row 0 -> 17 = 2419 MHz, core 7 row 0 -> 20 = 3187 MHz. A loop on core 0 ran 379 -> 451 (+19%). UI still 10-20 fps while scrolling (driver cost 2-6 ms/frame, so the time is in the CPU-side software rendering by SpringBoard/backboardd, no GPU); touch 3346 reports, 0 bad. No thermal guard yet.
- **2026-11-27: the `darwin` partition (sda12) was removed** at the owner's request (its 64 GiB went to `userdata`, docs/38). HakiOS/iOS boots need it recreated and the iOS volume rebuilt from the restore ipsw (`ref/`); the old partition table is in `android/backups/lun0-gpt-20261127/`.

