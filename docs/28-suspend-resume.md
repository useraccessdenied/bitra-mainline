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
| Touchscreen (tap) | yes | `synaptics-tcm` (msmgpio 39, level), irq 171 |
| Volume down, USB/Type-C plug, Wi-Fi (WoWLAN), modem (mhi) | not tested | |

Note: the touch controller wakes the system on **any** touch (not just a double-tap): there is no double-tap gesture mode in this driver (docs/22).
The per-source `event_count` in `/sys/class/wakeup` does not reflect IRQ wakes of the PMIC key/gpio IRQs (counters stay 0); use `pm_wakeup_irq` + `/proc/interrupts` to identify the waker.

## Noise / gaps
- `mhi mhi0: Failed to send DISABLE / SECONDARY BOOTLOADER / MISSION MODE uevent` during suspend (the QCA6390 Wi-Fi's MHI layer sends uevents while userspace is frozen). Harmless.
- Not measured: power draw while suspended (the phone is on USB power, which charges the battery; needs an unplugged run and the gauge `current_now`), cpuidle depth in s2idle (PSCI idle states),
  wake from `mhi`/Wi-Fi, repeated cycles (hundreds), suspend with a UI (screen blank, brightness restore), long sleeps (hours), suspend while charging vs on battery.
- The USB-NCM shell drops while devices are suspended and returns after resume: run tests detached (`setsid`) and read `/root/suspend.log` afterwards.
