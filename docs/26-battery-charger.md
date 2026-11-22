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
