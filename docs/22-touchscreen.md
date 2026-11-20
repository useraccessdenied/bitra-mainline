# 22 — Touchscreen: research and effort estimate (2026-11-21)

## The hardware (stock device tree, 4.19 vendor kernel)
Synaptics **S3908** (Realme/Oplus "synaptics-s3908", TouchComm/TCM "oncell"), I2C bus `0xa94000`, address **0x4b**, project 0x5473 (21619, also 2169A/2169B/2161A),
IRQ = **TLMM 39** (level-low), reset = **TLMM 38**, 16x35 channels, panel coordinates 8640x19200 over display 1080x2400 (factor 8), up to 10 touches, curved-screen "prevention" tuning.
Supplies (resolved from the stock tree): `vdd` = pm8150a_l11 (2.9-3.3 V) = mainline `vreg_l11c_3p0`; `vcc` (I/O) = pm8150a_l1 (1.8 V) = mainline `vreg_l1c_1p8`.
Note the swap vs the OnePlus 8T: on this phone the *touch* uses l11c and the *panel VCI* uses l13a_ts_3p0 (see docs/18, panel driver).

## What exists already
1. **In our mainline tree (pmOS SM8250 fork, 7.2.0): `drivers/input/touchscreen/synaptics_s3908.c` (567 lines) + binding `syna,s3908.yaml`** ("Synaptics TCM Oncell Touchscreens",
   Frieder Hannenheim / Casey Connolly). The OnePlus 8T (`sm8250-oneplus-kebab.dts`) already uses it: `touchscreen@4b`, `syna,s3908`, IRQ tlmm 39 level-low, reset tlmm 38, vdd `vreg_l13a_ts_3p0`, vcc `vreg_l1c_1p8`,
   pinctrl `ts_int_default` (gpio38/39, pull-up) — **the same address and GPIOs as this phone**. The driver identifies the chip, reads max X/Y from the application info, parses touch reports (input MT, protocol B), no firmware update, no gestures, no suspend handling.
   Our config has it as a module (`CONFIG_TOUCHSCREEN_SYNAPTICS_S3908=m`, `INPUT_EVDEV=m`): both must be built in (no module loader in the initramfs).
2. Upstream history: posted to linux-input in March 2024 (v1) and June 2024 (v2, series "qcom: initial support for the OnePlus 8T", patch 7/8 + binding). The author notes the same touchscreen is used in the Realme GT2 Pro and OnePlus 9 Pro; the cover letter says it only supports the 8T's S3908,
   and the 8T firmware appears not to support the touch-report-configuration command. A merge into Linus's tree was not confirmed by search (it is carried in the pmOS tree).
3. **New upstream effort (2026-09-10, linux-input, LWN 1093606): "Input: add Synaptics TouchComm I2C touchscreen driver and bindings" by Vsevolod Nevorotov** — `synaptics_tcm_i2c.c` (1033 lines) for **TouchComm generation-1 over I2C, naming the S3908 (OnePlus 9RT)**:
   Protocol-B multitouch, dynamic touch-report layouts and coordinate/pressure decoding, standard touchscreen properties (swap/invert), low-power wake gestures (double-tap to wake), system suspend/resume with deep-sleep transition, regulator + reset GPIO lifecycle.
   Same binding file name (`syna,s3908.yaml`, 69 lines) — it competes with / would supersede the 2024 driver. Not merged as far as known.
4. Vendor reference (our 4.19 trees): `drivers/input/touchscreen/synaptics_tcm` ≈ 14.3k lines and the Oplus wrapper `oplus_touchscreen` ≈ 50.7k lines (gestures, glove/palm/edge/"prevention", firmware update, factory tests, debugfs). The mainline driver deliberately ignores almost all of it.
5. Other mainline touch drivers in the tree (not applicable to the S3908's protocol): rmi4 (RMI over I2C/SPI, OnePlus 6/6T), focaltech edt-ft5x06 (FT3658U, as on the GT Neo 3T), goodix_berlin, himax_hx83112b, elan, ilitek, novatek, melfas_mip4, s6sy761, stmfts, zinitix, cyttsp5, hid-over-i2c. None speaks TouchComm.

## Effort estimate
| Path | Work | Time | Risk |
|---|---|---|---|
| **A. Use the existing `synaptics_s3908`** | DT node (copy of kebab, our supplies), 2 config switches, one test boot, read events | **~1-2 h** | Firmware report-format / command differences between this phone and the 8T; coordinates come in chip units (8640x19200) so userspace must scale (libinput does from the absinfo range) |
| A+. Fix report parsing if it misbehaves | I2C trace + compare with the vendor driver's report parsing (14k lines) | +0.5-1 day | medium |
| **B. Try the 2026 TouchComm gen-1 driver** (apply the series from linux-input) | Fetch the 2 patches, port to 7.2, test; gives wake gestures, suspend/resume, dynamic report layout | **~0.5-1 day** | new, unmerged, written for the 9RT; check it against this firmware |
| C. Write one from scratch in C | Only if A and B both fail on this firmware | 1-2 weeks | needs the vendor protocol details |
| D. Write one from scratch in Rust | Needs Rust input-device and GPIO bindings that are not merged (see docs/20); I2C/regulator/IRQ exist | 3-6+ weeks (mostly unsafe bindings) | high; **not recommended** |
Rust evaluation: not needed — a working C driver already exists and the missing Rust abstractions (input device/multitouch, GPIO consumer, regmap) would have to be written first as unsafe FFI, which is where memory bugs would actually live. Revisit when Rust input bindings land.

## Plan
1. A first (cheapest, and it tells us whether the firmware matches): enable the driver built-in, add `touchscreen@4b` on the right I2C bus with this phone's supplies, boot, read `/dev/input/event*`.
2. If events are wrong or missing, switch to B; fall back to A+ / C only with evidence.
3. Later (not part of this driver): wake gestures, palm/glove/edge rejection, suspend/resume, calibration.


## RESULT (2026-11-21): touchscreen works on mainline with the 2026 TouchComm driver (path B)
**Path A (existing `synaptics_s3908`, built in, node copied from the 8T): detected the chip but unusable.** Probe OK ("Synaptics TCM Oncell Touchscreen", i2c-13/13-004b, max 8639x19199),
IRQ fires, but every report is rejected: `invalid touch report length`. Cause: the driver hardcodes ONE touch-report layout (its own comment says other report configs would need
dynamic parsing); this phone's firmware (`s3908PR0-15.0`, TouchComm v1) uses another layout.
**Path B (`synaptics_tcm_i2c`, Vsevolod Nevorotov's 2026-09-10 series, imported from lore `20260910070723.347768-1-sevanevorotov29@gmail.com`): works.**
`TouchComm v1, mode 0x01, part s3908PR0-15.0`, `8640x19200, 10 touch objects`, input device "Synaptics TouchComm Touchscreen" (event3). Measured with tools/bitra-evtest: ~3100-4600 frames per 30-45 s capture,
all 10 MT slots used, X 0..8639 and Y 162/377..19199 (edge to edge), tracking ids start/release in balance, smooth coordinate streams, no kernel warnings from the driver. Pressure stays 0 (this report layout carries no Z).
Upstream review state: Tested-by: Frieder Hannenheim (OnePlus 8T, S3908, "wake from suspend works"; no wake when the screen is off but the device is not suspended — he points to David Heidelberg's ft5x06 double-tap series).
Our tree: branch `bitra` carries the import (unmodified commit 83e846480) + a hardening commit (below) + the DTS node. The old driver stays in the tree but is disabled in our config (both bind `syna,s3908`).
### DT differences vs the old driver / the 8T
- New binding (`syna,s3908`): `vdd-supply` (3.0 V) and **`avdd-supply` (1.8 V)**, optional `wakeup-source`; the old binding used `vdd` + `vcc`. With `vcc` the new driver warns `supply avdd not found, using dummy regulator` and the chip never answers (`failed to write command 0x02: -110`).
- This phone: vdd = `vreg_l11c_3p0` (pm8150a_l11), avdd = `vreg_l1c_1p8` (pm8150a_l1), irq tlmm 39 level-low, reset tlmm 38 active-low, `clock-frequency = <400000>` on `&i2c13`, pinctrl `ts_int_default`/`ts_rst_suspend`.
### Review of the automated review (sashiko) of the posting — checked against the code and the vendor reference
1. "continued read skips the final chunk when payload_len == 60": **not a bug** — the vendor driver counts the padding byte inside the message and also skips the read when only the padding byte remains.
2. "non-last chunks read 63 instead of 64 bytes": **undetermined** (vendor reads rd_chunk_size = 64 per chunk, i.e. 62 payload bytes; this driver reads 63). Never hit by ordinary touch reports (< 60 bytes). Left unchanged; verify with a long report (e.g. gesture/diagnostic) if it ever matters.
3. "unbounded active-object count / 32-bit overflow in syna_get_bits": **real in principle** (needs a misbehaving controller). Fixed: 64-bit bounds check; `active` clamped to max_objects. (Object *index* was already range-checked.)
4. "unbalanced regulator disable if recovery power-up fails": **real**. Fixed with a `powered` flag. (Commit 54f0bd481; compile-clean at W=1, checkpatch clean; retested on the phone after the change.)
Worth upstreaming these fixes to the author.
### Tool bug worth remembering
`bitra-evtest` first showed 0 events even while the driver decoded touches: my `pollfd` had a 64-bit fd, so `ppoll` never saw the requested events. Fixed (struct { int fd; short events, revents; }).
### Not done / open
Suspend/resume and wake gestures (double-tap) untested; `wakeup-source` is set in the DT. Palm/edge rejection, glove mode, curved-screen grip handling from the vendor driver are not implemented (userspace/libinput does basic palm handling).
Pressure/size: `TOUCH_MAJOR` max is 4095 here; width fields only. Coordinate range is in chip units (libinput scales from the absinfo range). Check the axis orientation against the panel (swap/invert) when a UI runs.
