# 28 — Suspend / resume (s2idle) (2026-11-22)

Kernel `7.2.0-g2cecd2883092` + `CONFIG_PM_DEBUG`, `PM_SLEEP_DEBUG`, `PM_ADVANCED_DEBUG`, `PM_TEST_SUSPEND` (in `configs/bitra_defconfig`: cheap, gives `/sys/power/pm_test`,
`pm_wakeup_irq`, `suspend_stats`), boot image `a-8`, Alpine on `userdata`, Wi-Fi connected, touch/UFS/display active.

## Result: s2idle suspend and resume work
- Only `s2idle` (`freeze`) is offered (`/sys/power/mem_sleep` = `[s2idle]`); no deep `mem` suspend (PSCI suspend not enabled in this tree).
- Staged `pm_test` walk (`tools/suspend-test.sh stages`): `freezer`, `devices`, `platform` all return 0 with no failed device. `processors`/`core` fail with EAGAIN by design:
  the kernel says "Unsupported test mode for suspend to idle, please choose none/freezer/devices/platform".
- Real suspend (`tools/suspend-test.sh real SECS`, RTC alarm): slept 20 s and 3 x 120 s, `PM: suspend devices took ~0.43 s`, `resume devices took ~0.58 s`, `suspend_stats`: 0 failed steps, no failed device.
- State after resume: Wi-Fi still associated (same IP, ping works), backlight back (1174), wall clock correct (the RTC offset survives), touchscreen delivers events (3562 EV_ABS in a 30 s drag test).

## Wake sources (verified with `/sys/power/pm_wakeup_irq`)
| Source | Verified | IRQ |
|---|---|---|
| RTC alarm (`rtc0/wakealarm`, absolute RTC time) | yes, wakes on time (20 s test: alarm 1441564, woke 1441566) | pmic_arb (rtc@6000) |
| Power key | yes (woke ~23 s before the alarm) | `pm8941_pwrkey` (pmic_arb 524301), irq 129 |
| Volume up | yes | spmi-gpio 5 "Volume Up", irq 177 |
| Touchscreen: **double tap** | yes (owner: a double tap wakes the screen, a single tap does not) | `synaptics-tcm` (msmgpio 39, level), irq 171 |
| Volume down, USB/Type-C plug, Wi-Fi (WoWLAN), modem (mhi) | not tested | |

Note: the touch controller wakes the system on a **double tap only** (owner's observation: single taps do nothing). That means the S3908 firmware does its own double-tap gesture detection while the system sleeps and raises the interrupt only for it. The driver has no gesture code (docs/22), so this works with the controller's default behaviour; whether it can be configured (other gestures, enable/disable from userspace) is untested.
The per-source `event_count` in `/sys/class/wakeup` does not reflect IRQ wakes of the PMIC key/gpio IRQs (counters stay 0); use `pm_wakeup_irq` + `/proc/interrupts` to identify the waker.

## Noise / gaps
- `mhi mhi0: Failed to send DISABLE / SECONDARY BOOTLOADER / MISSION MODE uevent` during suspend (the QCA6390 Wi-Fi's MHI layer sends uevents while userspace is frozen). Harmless.
- Not measured: power draw while suspended (the phone is on USB power, which charges the battery; needs an unplugged run and the gauge `current_now`), cpuidle depth in s2idle (PSCI idle states),
  wake from `mhi`/Wi-Fi, repeated cycles (hundreds), suspend with a UI (screen blank, brightness restore), long sleeps (hours), suspend while charging vs on battery.
- The USB-NCM shell drops while devices are suspended and returns after resume: run tests detached (`setsid`) and read `/root/suspend.log` afterwards.

## Power draw on battery (measured 2026-11-22, `tools/suspend-power.sh`, raw log `docs/data/suspend-power-2026-11-22.log`)
USB unplugged, battery 81 % (aged pack: 1480 mAh full vs 2465 design), 8.3-8.4 V (2S), Wi-Fi associated, USB-NCM gadget idle. Source: BQ28Z610 gauge
(`current_now` is a smoothed average with ~30 s time constant, `charge_now` has 1 mAh steps, so averages come from dQ/dt over long stages).

| Stage | Result |
|---|---|
| A idle, screen on (brightness 1174) | ~129 mA, 1.09 W |
| B idle, backlight off (no suspend) | ~123 mA, 1.03 W |
| C suspend 2 min, Wi-Fi up | 88 mA by dQ (3 mAh), gauge average 70 mA at wake |
| D suspend 2 min, Wi-Fi down | 59 mA by dQ (2 mAh), 69 mA at wake |
| E suspend 15 min, Wi-Fi down | **160 mA** by dQ (40 mAh) — outlier, see below |
| F suspend 15 min, Wi-Fi up | 80 mA by dQ (20 mAh), 71 mA at wake |

Reading: **suspended draw is about 60-90 mA (0.5-0.75 W): only ~40 % below an idle phone with the screen black.** A healthy phone sleeps at a few tens of mW (10-20 mA at 3.8 V).
At ~70 mA this pack (1480 mAh) lasts ~21 h in suspend, ~12 h idle with the screen off.
- E is probably a gauge artefact: 11 suspends = 11 stages (no wake-up loops), the Wi-Fi chip is powered off in suspend either way (mhi power-off/on in the log), C/D/F and the gauge's own average all say ~70 mA,
  and a BQ28Z610 corrects `RemainingCapacity` from the open-circuit voltage after a long rest. To confirm, repeat E and F back to back.
- CPU idle is not the problem: cpu0 uses `cpu-sleep-0-0` (140k entries, 1352 s) and the cluster domain enters `cluster-sleep-0` (67k entries, 785 s).
- Suspects for the missing ~60 mA (not yet measured one by one): `clk_ignore_unused` and `pd_ignore_unused` on the command line (unused clocks/PLLs and power domains stay on; `mx`/`mmcx` have many children),
  regulators left on by the bootloader (camera/sensor/audio rails nobody owns), the display pipeline (`mdss_gdsc` on), the Bluetooth half of the QCA6390 (hci0 up), the audio amplifiers,
  PCIe0 link state, and the fast-charge MCU / charge pump idle current on the battery side.
- Wake-ups from timers are not the cause (one suspend per stage; `suspend_stats` clean).

Next experiments (each needs the phone unplugged for a few minutes; the gauge average settles in ~1 min): boot without `clk_ignore_unused pd_ignore_unused`, bring `hci0` down, turn `mdss` off in suspend, list powered regulators
(`/sys/kernel/debug/regulator/regulator_summary`), and read `/sys/kernel/debug/clk/clk_summary` for enabled unused clocks.
