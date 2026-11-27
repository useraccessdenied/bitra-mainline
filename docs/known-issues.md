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
- Wi-Fi: the old "scan stuck (Resource busy)" report was a WPA3-only network with a raw-key profile, not ath11k (docs/35, 2026-11-27).
- Wi-Fi/Bluetooth addresses: the stock addresses were not found; both are now stable per-phone addresses derived from the SoC serial (docs/35, docs/36).
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

## Parked by the owner (2026-11-22): system sleep (AOSD/CXSD/DDR)
Standby is ~55-65 mA (about 1 day on the worn 1480 mAh pack) and `qcom_stats` aosd/cxsd/ddr stay 0; stock Android had similar battery life, so this is not a regression. Findings, sources and the cheap experiments left are in docs/28. Resume with `tools/sleepstat.sh` around a suspend.

## Phosh / GPU round (2026-11-22, docs/29, 30)
- Display: `dpu_crtc_get_vblank_counter` / `dpu_crtc_get_scanout_position` log "no encoder found for crtc 0" while the CRTC is disabled (upstream-side display driver noise).
- `typec_displayport ... probe failed with error -71` when a USB-C partner attaches (DP alt mode, USB-C/PD work is open).
- Wi-Fi is now managed by NetworkManager; `bitra-wifi`/`wpa_supplicant.conf` remain only as the source for `tools/nm-wifi-from-wpa.py`. A Wi-Fi password is still never baked into images.
- Phosh needs display buffers divisible by its scale 3 (client issue only).

## Deferred by the owner (2026-11-22): hours-long GPU testing
To do later (not now): a multi-hour GPU soak. Include: sustained mixed Vulkan/GLES load for hours with the sampler (`tools/gpu-stress.sh`, longer `LOAD_S`) logging freq/temps/throttle state/battery;
GPU load combined with repeated suspend/resume cycles; other GPU fault types (iommu/page faults, repeated deliberate hangs with `tools/gpu-hang-test.py hang`, hang while Phosh animates); GPU power draw on battery;
check that the cooling device actually throttles when the thermal trips are reached (force a hot run or lower a trip), memory leaks across hours (`/proc/meminfo`, dmesg), and the `sync_state` wait on the GMU. Baseline for comparison: docs/29 'GPU tests' (5 min, peak 60 C, no throttling needed).

## Audio round (2026-11-22, docs/31)
- One unexplained reset during the first playback attempt (PulseAudio was also probing the card); not reproduced with PulseAudio stopped, nor with PulseAudio playing through the UCM sink. Keep watching.
- UCM profile covers the speaker and the bottom microphone (docs/31). Top microphone not found (all analog/digital inputs tried), no earpiece/headset entries yet. The mic needs the `bitra_mic` PulseAudio remap source because the second PCM channel is silent.
- AFE commands right after the ADSP boot are rejected (status 0x16: LPASS vote, first clock SET_PARAM); they work minutes later. The vote reply is handled (fails fast), the first clock set is retried by deferred probing.
- Older record in pstore (`dmesg-ramoops-0`, 971 s uptime): `fsa4480_switch_set` taking a corrupted mutex from `tcpm_snk_attach` -> `typec_set_orientation`, i.e. the USB-C stack using an FSA4480 that had been **unbound** by the standby-power bisect scripts (stale switch pointer after unbind). Not a regression of the normal configuration, but unbinding `fsa4480` while a typec switch references it is unsafe.
- `cpu cpu7: Voltage update failed freq=3187200` / `failed to update OPP` at boot (the 3.19 GHz OPP of the SM8250-AC/870 does not get its voltage).

## USB-NCM shell link drops a few minutes after boot (2026-11-27)
The agent loses the phone about 4-7 minutes after every boot (it appears in the first minutes, then `state` says `absent`; the Mac shows a renamed interface with a DHCP address but nothing answers on 192.168.2.15:23). Seen with the flashed images and the RAM-boot `a-30`, so not caused by the DT change. `tools/usbwatch.sh` (run on the phone, log in `/var/log/usbwatch.log`) showed the phone side healthy during a drop: UDC `configured`, role device, `usb0` up with carrier, no kernel message, but the `usb0` rx/tx counters froze (no traffic) from ~400 s on. Not found yet: whether the Mac, the NCM function or the phone's shell service stops first. Next: log from the phone side with `ip -s`/`tcpdump` on usb0, check the Mac interface (macOS NCM driver), try ECM instead of NCM.
Update: the 'drop' is not permanent. Right after one drop `net` reported the Mac's `en33` with no address (the agent then fails because the Mac has no passwordless sudo for `ifconfig`, `doctor` shows `sudo_nopasswd: false`), and a minute later the same interface had a DHCP lease again (192.168.2.21) and the shell answered. The phone's udhcpd (pool .20-.30, default lease) and `usb0` (192.168.2.15) were fine. The Mac's interface number and lease change after each drop (en9 -> en33, hosts .30/.21/.28/.24/.23), so the Mac re-creates the NCM interface and takes time to configure it. Suggested: add the `/etc/sudoers.d/bitra` entry from the bitra-agent README on the Mac so the agent can set a static address itself.

## SKIPPED (owner, 2026-11-27): iio-sensor-proxy should wait for the SSC instead of exiting
Decision: not fixed on Alpine; the systemd distros (D-Bus activated iio-sensor-proxy, `Restart=`) should make it go away, so the `bitra-sensors` Phosh restart workaround stays until then (docs/37). Original note:
Problem: the SLPI sensors answer ~55 s after boot (docs/32), `iio-sensor-proxy` (3.9, ssc drivers via libssc) finds no sensor at start and exits, and Phosh only claims the proxy when its session starts, so `bitra-sensors` restarts the whole Phosh session once (~55 s after boot). Restarting the proxy behind a running session leaves Phosh without sensors until the session restarts.
Goal: no session restart. The proxy stays on D-Bus from boot (`net.hadess.SensorProxy`), keeps probing the ssc-accel/ssc-light/ssc-compass/ssc-proximity drivers (retry with back-off while the SSC is not ready), and when a sensor appears it flips `HasAccelerometer`/`HasAmbientLight`/... and emits PropertiesChanged; check that Phosh (0.55) then enables auto-rotate without a restart (Phosh claims on session start, so also check ClaimAccelerometer from a client that connected earlier).
Pointers: Alpine package `iio-sensor-proxy` 3.9; the udev rule is `rootfs-overlay/etc/udev/rules.d/81-bitra-iio-sensor-proxy.rules` (IIO_SENSOR_PROXY_TYPE, ACCEL_MOUNT_MATRIX); the service to retire is `rootfs-overlay/etc/init.d/bitra-sensors`; tools: `tools/sensor-timeline.sh` (startup timing), `tools/sensor-prune*.sh`. Build without containers (rootfs chroot via user namespace + qemu-user as in scripts/build_alpine_rootfs.py, or clang cross build). Test: cold boot, watch `monitor-sensor`, rotate in Phosh with no session restart. Upstream candidate: log in docs/24 when done.

