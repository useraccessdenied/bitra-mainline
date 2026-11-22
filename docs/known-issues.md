# Known issues / to do later (mainline bring-up)

> Per-hardware status of everything found so far lives in **docs/27-hardware-status.md**; this file holds the detailed open items.

Logged 2026-11-21, reviewed 2026-11-22. Display = Samsung AMS662ZS01 via msm DPU/DSI, kernel 7.2.0 (see docs/18).

## Display (marked for later by the owner)
1. **DSI PHY warnings at boot** — `DSI PLL(0) lock failed, status=0x0`, `dsi0_phy_pll_out_dsiclk already disabled/unprepared`
   (WARN in clk_core_disable/unprepare via `of_clk_add_hw_provider` -> `clk_core_reparent_orphans` in `dsi_phy_driver_probe`).
   Harmless so far; likely the PHY PLL being (un)prepared while ABL left it running (we boot with `clk_ignore_unused`).
2. ~~fbcon text rendering~~ — **resolved 2026-11-22**: the Alpine login prompt and boot text render on the panel (tty1). The `sys_imageblit` message was not a blocker.
3. **Panel suspend/resume** — exercised 2026-11-22 as part of s2idle (devices suspend/resume OK, backlight restored, touch fine; docs/28). Still to check by eye: image intact after every wake, TE/PLL re-lock over many cycles.
4. **ESD and TE behaviour over longer runs** — vendor DT enables ESD register polling (`0x9f 0x00 0x01 0x80`) and an ESD error GPIO;
   mainline driver has none. Only seconds-long animation runs were done; check long-run stability, TE misses, flicker.

## Other open items
Done since the first list: UFS (read/write, rootfs on `userdata`), touch, Wi-Fi/BT bring-up, battery gauge, thermal sensing, Alpine userspace (docs/21, 22, 25, 26).
Still open (see docs/27-hardware-status.md for the full table): USB-C PD/role switching, audio, modem (external SDX55M over PCIe/MHI), sensors, camera, GPU,
charging control, suspend/resume, standalone boot. See docs/20 for the order.
- ABL only accepts Droidian's DTB carrier + kernel-side DTB shim (CONFIG_BITRA_DTB_SHIM); a U-Boot stage would remove it.
- `fastboot` entered with hardware keys makes ABL refuse images ("Load Error"); use `to-fastboot` from the running OS.

## Connectivity (2026-11-21)
- Wi-Fi: scan stuck ("Resource busy") after switching networks with `wpa_cli select_network`; recover with `ip link set wlan0 down/up`. Investigate (ath11k scan abort after roam/disconnect).
- Wi-Fi: real MAC (use-nv-mac) and Bluetooth BD address are not read from vendor storage; both use placeholders/temporary values.
- Wi-Fi: no OEM board data (BDF) used yet; generic board-2.bin worked. Check power/suspend, regulatory (self-managed US), roaming, coex with Bluetooth.
- Bluetooth: LE scanning unverified; pairing/A2DP/audio not tried; needs bluetoothd (dbus) or a tty-capable btmgmt in the initramfs.
- Alpine package index signature is not verified by scripts/fetch_alpine_pkgs.py (checksums only).

## Touchscreen (2026-11-21)
- Works (docs/22). Open: suspend/resume + double-tap wake untested; no wake while the screen is off but the system is not suspended (same as upstream review note); axis orientation vs the panel not yet verified in a UI; no pressure value in this report layout.
- The unmerged `synaptics_tcm_i2c` driver (and my hardening commit) should go back to the author / linux-input; the old `synaptics_s3908` stays disabled in our config (same compatible).
- ABL-agnostic tool note: tools/bitra-evtest.c had a pollfd layout bug (fixed).

## Deferred by the owner (2026-11-21) — do later
- Touchscreen: **suspend/resume and double-tap wake** (untested; upstream reviewer reports wake from suspend working on an 8T), and **orientation/axes vs the panel in a real UI**.
- Display (earlier list): DSI PHY PLL warnings, fbcon text rendering, panel suspend/resume, ESD/TE over long runs.
- Wi-Fi: convert `persist/bdwlan.elf` + regdb.bin to an ath11k board-2.bin entry; real MAC; BT real address; BT LE scan test/pairing/A2DP.
- Audio, modem (external SDX55M), sensors, camera: see docs/20.

## Found by the debug-kernel soak (docs/23) — upstream-side display bugs, not fixed
- `msm_gem.c:170` `GEM_WARN_ON(msm_obj->pin_count)` on every fbdev teardown (panel unbind): the fbdev GEM object is freed while pinned.
- `dpu_encoder_helper_wait_for_irq: encoder is disabled ... ctl_start_irq` on every panel off/on (blank): command-mode kickoff vs disable race.
- Under fault injection: `refcount_t underflow` in `drm_dev_put()` from `drm_self_refresh_helper_entry_work` and a KASAN null-ptr-deref in `msm_drm_uninit -> dsi_unbind -> msm_dsi_tx_buf_free -> update_lru_locked` (dev_private already NULL after a failed `msm_drm_init`). Needs the fail-nth sweep to attribute.
- **Phone unreachable after `soak.sh failnth 1 6`** (see docs/23): needs a manual power cycle; cause unknown.
- Fixed in our tree (upstream candidates): typec altmode descriptor not zeroed (UBSAN), DPU self-refresh helper leak (512 B x 2 per DRM bring-up), qcom-wdt not marking an armed watchdog as running.

## Parked by the owner (2026-11-22) — fault-injection sweep, resume after the bootable-OS milestone
State: kernel fork `bitra` at 593dc5215 (candidates #1-#14 in docs/24); image `releases/t-dbg10.img` = debug kernel with all fixes.
- fail-nth clean so far: N=1..400 (t-dbg6), 401..699 stride 7, 770..790 (all t-dbg10), 850..3000 stride 50.
- To do: understand why `left` stays 0 up to N=3000 (real end of the bind's allocations not found; check the semantics of `left` for large N); re-run N=1..400 and a full 746..900 on t-dbg10; then other drivers (UFS, ath11k, panel) with the same helper.
- Open upstream-side items: devcoredump pinning drm_device (#10), msm_gem.c:170 (#11), "encoder is disabled" (#12), rpmh.c:386 WARN from sugov (new, unexamined).
- Resume with: `ssh mac "sh 'soak.sh failnth FROM TO OUT [STEP]'"` on a t-dbgN RAM boot (docs/23).

## System items found 2026-11-22 (Alpine round, docs/25, 26)
- The bitra-agent shell is telnet as root on 0.0.0.0:23 (owner's choice for development); sshd uses the dev password `bitra`. Harden before the phone leaves the desk.
- No watchdog service in Alpine: the initramfs' pet loop keeps running after switch_root; replace it with an OpenRC service.
- Alpine's `hwclock` is pulled in by other services and does hctosys from the read-only RTC; `bitra-time` has `need hwclock` to run after it (docs/26).
- Kernel and modules must match (release string contains the git hash, `-dirty` if the tree is dirty): rebuild/push them together.
- `bitra-agent put` fails for single files around 2 GiB (EINVAL); keep transfers under about 1 GiB.
- `rpmh.c:386` WARN from `sugov` (cpufreq) seen once on a debug kernel; unexamined.
- Boot-time `clk_core_disable/unprepare` WARNs (~19 s, kworker) — DSI PHY related (item 1 above).
- Charger: MP2650 / Oplus charge pump / RK826 VOOC MCU / SMB1390 are not driven; charging works by hardware default, fast charging does not (docs/26).

## Standby power bisect: suspend hang after unbinding the Wi-Fi/BT power chain (2026-11-22)
`tools/suspend-power3.sh` (cumulative unbind run): stage B0 (baseline, nothing unbound) measured 65 mA suspended. Stage B1 unbound `ath11k_pci` (0000:01:00.0), `hci_uart_qca` (serial0-0), `pci-pwrctrl-pwrseq`
(1c00000.pcie:pcie@0:wifi@0) and `pwrseq-qcom_wcn` (qca6390-pmu) -- all four reported unbound, regulators in use dropped 53 -> 47 -- and then the s2idle suspend never returned: the phone was reset (watchdog) and booted into the old Droidian initrd.
(Update: reproduced and narrowed down, see docs/28 'Hangs found while bisecting': a removed-PCIe/pwrseq combination, not the radios being off.) Unknown whether it hung entering suspend (PCIe root port 0000:00:00.0 left without its endpoint/power sequencer, `1c00000.pcie` runtime state) or in resume. Not caused by the radios being "off" (rfkill suspends fine).
Next: redo the bisect on the flashed kernel (a hang now reboots into Alpine), unbind in smaller steps (BT alone, then ath11k alone, then pwrseq), keep a console log (`no_console_suspend`, ramoops `console-ramoops` after the reset).
Also: the boot partition used to hold Droidian; it now holds the mainline image (docs/25).
