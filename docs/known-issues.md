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
