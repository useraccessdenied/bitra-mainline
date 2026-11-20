# Known issues / to do later (mainline bring-up)

Logged 2026-11-21. Display = Samsung AMS662ZS01 via msm DPU/DSI, kernel 7.2.0 (see docs/18).

## Display (marked for later by the owner)
1. **DSI PHY warnings at boot** — `DSI PLL(0) lock failed, status=0x0`, `dsi0_phy_pll_out_dsiclk already disabled/unprepared`
   (WARN in clk_core_disable/unprepare via `of_clk_add_hw_provider` -> `clk_core_reparent_orphans` in `dsi_phy_driver_probe`).
   Harmless so far; likely the PHY PLL being (un)prepared while ABL left it running (we boot with `clk_ignore_unused`).
2. **fbcon text rendering** — `fb0: sys_imageblit: framebuffer is not in virtual address space` on the msmdrmfb fbdev; console text
   is not verified to render on the panel (kernel log is read through the agent instead).
3. **Panel suspend/resume** — never exercised (display off/on, runtime PM, backlight, TE/PLL re-lock).
4. **ESD and TE behaviour over longer runs** — vendor DT enables ESD register polling (`0x9f 0x00 0x01 0x80`) and an ESD error GPIO;
   mainline driver has none. Only seconds-long animation runs were done; check long-run stability, TE misses, flicker.

## Other open items
- UFS (read-only probe first, explicit go-ahead needed), touch (Synaptics S3908 TouchComm driver), Wi-Fi/BT (QCA6390), USB-C PD,
  audio, modem (external SDX55M over PCIe/MHI), sensors, camera. See docs/20 (in this repo) for the order.
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
