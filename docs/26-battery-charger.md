# 26 — Battery, charger, RTC, modules (2026-11-22)

## Fuel gauge: works (read-only)
- TI **BQ28Z610** at 0x55 on **i2c16** (`i2c@888000`; same as the OnePlus 8T). It is on i2c16, NOT i2c15 (i2c15 holds fsa4480, 2x tfa987x audio amps, SMB1390 charge pump, FM radio).
  DT node in `sm8250-realme-bitra.dts` (`&i2c16 { fuel-gauge@55 { compatible = "ti,bq28z610"; } }`), driver `bq27xxx_battery_i2c` (already built in).
- `/sys/class/power_supply/bq28z610-0`: status, capacity, voltage_now, current_now, temp, charge_full(_design), cycle_count, health.
  First reading on this phone: Charging, 62 %, **8.37 V (2S pack)**, +331 mA from the Mac's USB port, 37 C, cycle_count **1695**, charge_full 1480 mAh vs design 2465 mAh (~60 % health).
- Reads before the move to i2c16 failed with ENXIO: nothing on i2c15 answers at 0x55/0x10/0x64 (those chips live elsewhere or are unpowered).
- A DTB change needs `make dtbs` as well as `Image.gz` (the DTB shim embeds the built .dtb).

## Charger: NOT driven (deliberately)
- Charging works on its own (hardware default): the gauge shows Charging with a rising level over USB, no driver involved.
- The stock tree charges through an **MP2650** (i2c5 @0x5c) + Oplus charge pump (0x68) + RK826 VOOC MCU (i2c16 @0x0a) + SMB1390 (i2c15) and the pm8150b `qpnp-smb5`; none has a mainline driver
  except the pm8150b charger (`qcom_pm8150b_charger.c` in this fork: it writes USBIN current limit, charge enable and **float voltage**). With the wrong battery data (this pack is a 2S high-voltage
  Oplus cell, stock says `oplus_batt_4400mv`) that could overcharge a lithium cell, so it stays disabled until limits are checked against the stock values.
- To do: read the PMIC FG (`pm8150b_fg`, read-only ADC) as a cross-check; datasheet of MP2650 for its watchdog/default current; decide on USB input current limits (USB-C PD/`tcpm` is present: `tcpm-source-psy-*`).

## Power key and buttons: work
`pm8941_pwrkey` (event0), `pm8941_resin` = volume down (event1), "Volume keys" gpio-keys = volume up (event4), haptics, touchscreen. 33 thermal zones report (TSENS module loaded).

## Production kernel config
- `configs/bitra_defconfig` is a normal (non-debug) config; this round: `RTC_DRV_PM8XXX=y`, `kasan_multi_shot` removed from the default bootargs.
- **548 options are modules** (the base config is from postmarketOS): TSENS (thermal!), SPMI ADC/temp-alarm, PM8008 regulators, SPI GENI... A rootfs without `/lib/modules/<release>` silently loses them.
  `scripts/build_alpine_rootfs.py` now runs `modules_install` (stripped, 14 MB) into the image, and `hwdrivers` (sysinit) loads by modalias (36 modules load on this phone).
  The release string includes the git hash (`7.2.0-g<hash>[-dirty]`): modules must match the running kernel, so rebuild/push them together (live: tar to /lib/modules, `depmod` is done by modules_install).

## RTC and clock
The PMIC RTC (`rtc0`) counts but is **not settable** (stock DT has no `allow-set-time` either; Android keeps an offset in userspace). `bitra-time` stores `offset = real - rtc` in `/var/lib/bitra-rtc-offset`
(updated after every NTP sync and on shutdown) and restores `rtc + offset` at boot, with or without network.
Gotchas found on the way:
- `/run` must be a fresh tmpfs: after `switch_root` it was a directory on the disk, so OpenRC's "started" state survived reboots and services (bitra-time, sysctl, bootmisc, hostname, modules) were silently skipped.
  The initramfs now mounts tmpfs on `/newroot/run`.
- Alpine's `hwclock` service (hctosys from the RTC) is pulled in by other services; `bitra-time` has `need hwclock` so it always runs after it.

## Quick hardware tests (2026-11-22)
- Keys: `evtest` on event0/1/4 while the owner pressed them: power, volume up, volume down all arrive; the PON `resin` device stays silent (volume-down is a gpio-key). See docs/27.
- Haptics: `tools/bitra-haptic.py` (FF_RUMBLE through `EVIOCSFF`) — owner felt every pulse.
- NFC: `tools/bitra-nfc.py` talks to the kernel NFC generic-netlink family directly (DEV_UP, START_POLL, GET_TARGET); detected an ISO14443-A target (ATQA 0400, SAK 20, UID 08a5b523).
  Pitfall found: a netlink request with NLM_F_ACK leaves an ACK in the socket; read replies in a loop (the first datagram may just be the ack).
- The image builder now also installs curl, i2c-tools, evtest and python3 and copies `tools/*.py` to `/usr/local/bin`, so a rebuilt image matches the live system.

## Charger state read from the MP2650 (2026-11-22, read-only)
`i2c5` (qupv3 se5, 400 kHz) is now enabled in the DT (no driver binds the MP2650 @0x5c; `tools/mp2650-status.py` reads it with `i2cget`, nothing is written). The register layout comes from the Oplus driver in the workspace vendor kernel (`roms/droidian/kernel/drivers/power/oplus/charger_ic/oplus_mp2650.[ch]`); the stock charging parameters of **this** phone are in `roms/droidian/kernel/arch/arm64/boot/dts/vendor/oplus/bitra/kona-mtp.dtsi` (`&pm8150b_charger`, `mp2650-charger@5c`).

What the bootloader left programmed (and Linux inherits, since nothing touches the chip):

| Setting | Value on the phone now | Stock (bitra vendor DT / driver) |
|---|---|---|
| Input current limit (reg00) | `0x1e` = **1500 mA** | USB SDP 500 mA, CDP 1500 mA, standard/PD/QC charger **2000 mA** |
| Input voltage limit VINDPM (reg01) | 4.5 V | default |
| **Charge current** (reg02) | `0x06` = **300 mA** | normal temp window **1100 mA** (PD/QC 2000 mA), cool/little cold 1100 mA, cold 300 mA, warm lower |
| Termination / precharge (reg03) | 200 mA / 600 mA | iterm 135 mA |
| **Float voltage per cell** (reg04) | `0x68` -> **4362.5 mV** (2S pack: 8.725 V) | **4435 mV** (cold 3980 mV); stock `oplus_batt_4400mv` |
| Charging enabled / OTG boost / battery FET (reg08) | on / **off** / on | |
| Watchdog (reg09) | **disabled** (settings persist); 12 h fast-charge timer on, termination on | |
| 2-cell battery select, precharge threshold (reg07) | 2 cells, 6.8 V | |

Reading it: the inherited state is conservative on **voltage** (below the stock float voltage, which is also kind to this worn pack: 1695 cycles, 1480 of 2465 mAh = 60 % health) but slow on **current**: 300 mA into the pack is roughly 5 hours for the remaining capacity, against ~1.1-2 A in the stock normal-charge path. The watchdog being disabled means the bootloader's values stay until power is lost, and also that any value written would persist (no automatic fall back); the 12 h charge timer is the only built-in backstop. The PM8150B `smb5` is not bound (no power-supply device from it), so charger-type detection (SDP/CDP/DCP/PD) is not visible to Linux either; the USB psy (`tcpm-source-psy`) only reports the PD contract (5 V / 3 A with the Mac).

Fast charging proper (SuperVOOC, 65 W) is a proprietary handshake with the RK826 MCU (i2c16 @0x0a) and the adapter: not reproducible. A standard-charger improvement would be raising the MP2650 charge current within the stock limits; this needs a policy (temperature windows, input limit per charger type, termination) and is **not done**: nothing writes the charger.

Battery snapshot at the time: 97 % (8.617 V, 0 mA, "Not charging" = full), 35 C.

