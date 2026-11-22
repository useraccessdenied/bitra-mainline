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

## Standby power: experiments (2026-11-22, `tools/suspend-power2.sh`, logs `docs/data/spower-x*.log`)
Short method: 90 s idle with the backlight off, then 150 s suspends; the gauge's average current (time constant ~30 s) read right after wake is dominated by the suspended draw (it matched the 15 min dQ/dt runs within ~10 mA).

| Run | Kernel/cmdline | Idle (backlight off) | Suspend, radios up | Suspend, radios rfkill-blocked |
|---|---|---|---|---|
| baseline (earlier, 120 s/15 min stages) | `7.2.0-g2cecd2883092`, ignore flags on | 123 mA | ~70 mA | ~60-69 mA |
| x1 | + DT: no framebuffer-0 clocks/pd, crypto disabled (`sync_state` pending count 4 -> 0) | **104 mA** | 66 mA | 63 mA |
| x2 | x1 without `clk_ignore_unused pd_ignore_unused` | 103 mA | 66 mA | 64 mA |

Findings:
- **The `sync_state` fix is worth ~19 mA when awake** (the bootloader's interconnect/clock votes were never released: `gcc`/`dispcc` waited for `chosen:framebuffer-0`, `qnoc` for `crypto@1dfa000`, neither of which has a driver). It barely changes suspend (-4 mA).
- **`clk_ignore_unused` / `pd_ignore_unused` are not needed any more and cost nothing to drop**: the phone boots and runs normally without them (display, Wi-Fi, USB shell, modules), and the power is unchanged. They stay off in the recommended command line (docs/25: `a-10`).
- Radios (Wi-Fi/BT blocked with rfkill) change ~2 mA only. Note rfkill does not power the QCA6390 down: its PMU rails stay on while `pwrseq-qcom_wcn`/ath11k are bound.
- UFS is already in its deepest suspend state (`spm_lvl` 3: device SLEEP, link HIBERN8). CPU and cluster reach `cpu-sleep-0-0` / `cluster-sleep-0`.
- **The suspend floor is still ~65 mA at 8.35 V (0.55 W).** Not explained by unused clocks/PDs, UFS, CPUs or the radios' rfkill state. Remaining candidates, to be bisected by unbinding in a cumulative run:
  QCA6390 PMU rails (unbind pwrseq + ath11k + BT), the audio codec/amps (WCD938x rails `audio-codec-vdd-*` are held by a deferred codec, TFA987x x2, FSA4480), panel supplies in suspend (`ae94000.dsi.0-vdd/vddr/vddio`),
  the display subsystem (`mdss_gdsc` on), NFC/haptics chips, the PMIC regulators `vreg_bob` (6 users) and `vreg_s*`, DDR/`cx`/`mx` levels in the RPMh sleep set (needs `aoss`/`rpmh` debugging), and battery-side parts (charge pump / VOOC MCU quiescent).
- Kernel release is pinned to `7.2.0-bitra` (`CONFIG_LOCALVERSION="-bitra"`, no `LOCALVERSION_AUTO`, and `export LOCALVERSION=` in the build environment so the build script does not append `+`): DT-only rebuilds keep matching modules.

## Standby power bisect results (2026-11-22; logs in `docs/data/`, scripts `tools/suspend-power{3,4,5}.sh`, `tools/suspend-unbind-test.sh`)
Cumulative unbinds, gauge average right after a 75 s suspend (noise about +-10 mA; the first minutes after boot read ~10 mA higher):

| Run | M0 baseline | radios off (BT+ath11k, PCI endpoint+root port removed) | + pci-pwrctrl | haptics+NFC | + display pipeline | + TFA987x amps | + FSA4480 |
|---|---|---|---|---|---|---|---|
| p4 (phone up 6 min) | 56 mA | 57 | 56 | (hang in the next stage) | | | |
| p5 (phone up 1 min) | 66 mA | | | 67 | 56 | 56 | 55 |

**No peripheral unbind lowers suspend draw beyond the noise: the floor of ~55-65 mA (0.5 W at 8.4 V) is not in a driver-controlled device.**
Evidence for where it is: `/sys/kernel/debug/qcom_stats` after several suspends in the same boot: **`aosd` count 0, `cxsd` count 0, `ddr` LPM counts 0**; the DDR frequency table shows memory
idling at 768 MHz (the lowest ~547 MHz barely used), never in self-refresh. The SoC never enters its always-on / clock-shutdown / DDR-sleep states in s2idle.
Only one cluster idle state exists in the DT (`cluster-sleep-0` = `0x4100c244`, "cluster llcc off": used 67k times) and nothing describes a system-level state; upstream has a history of trouble
with exactly this (SM8250 cpuidle states were added, then [reverted](https://lkml.iu.edu/2210.2/01396.html) / [disabled](https://lore.kernel.org/lkml/CAMi1Hd2Qh-AO8JjwzwqYaQF3kyfC6R3K2t6jy3r2sSApTmwGGw@mail.gmail.com/T/)
pending synchronisation between the RPMh RSC and the cluster PM domain; the original [review thread](https://lkml.iu.edu/hypermail/linux/kernel/2201.1/06321.html) describes the PSCI value; the OSI approach is discussed in the [sdm845 series](https://lore.kernel.org/all/20220630101403.1888541-1-abel.vesa@linaro.org/T/)).
Reaching AOSD/CXSD on SM8250 needs RPMh sleep/wake sets flushed at the right moment, all votes (CX/MX/DDR/XO) dropped and the firmware (TZ/PSCI) agreeing; this is an upstream-wide gap, not a bitra bug. Next (own task): check `rpmh` flush
in suspend, the `apps_rsc` power-domain wiring, the PSCI state ids the stock kernel uses (`lpm-levels` in the stock DT), and whether PSCI `SYSTEM_SUSPEND` is available.

### Hangs found while bisecting (all reproduce with the phone plugged in; use `tools/suspend-unbind-test.sh`)
- Unbinding `pci-pwrctrl-pwrseq` (`1c00000.pcie:pcie@0:wifi@0`) while the PCIe root port (`0000:00:00.0`) is still registered hangs the next s2idle suspend (watchdog reset). Removing the PCI endpoint is not enough; removing the root port first fixes it.
- With the root port removed, unbinding `qca6390-pmu` (pwrseq-qcom_wcn) hangs the next suspend.
- In p4, unbinding TFA987x x2 + FSA4480 on top of the removed PCIe host hung the next suspend, but the same unbinds alone (p5) are fine: the hangs are combinations of removed PCIe/pwrseq state, not single drivers.
- After a hang the phone may reset a second time before userspace is up (the first reset's pstore log was lost). The initramfs now copies `/pstore` to `/var/lib/pstore/early-N` right after mounting the root (a-12; not yet in the flashed image), and the `bitra-pstore` service saves it at boot.
- Open question: the saved `console-ramoops` of a hung boot ended at ~35 s of uptime in two cases (no suspend messages): the ramoops console may stop recording after `switch_root` or the reset loses the tail. Test with a marker + `echo c > /proc/sysrq-trigger`.

## System sleep (AOSD/CXSD/DDR): research and parked work (2026-11-22)
**Parked by the owner:** stock Android gave about the same battery life on this phone, so the ~1 day standby on the worn pack (1480 of 2465 mAh) is not a regression; revisit later (battery life of a replaced/new pack would double).
What was established (research by a delegated agent plus local reads; items marked [S] came from search summaries and were not opened):
- **Local ground truth, verified:** the stock vendor DT (`stock.dts`, node `qcom,lpm-levels`) has only cluster levels `l3-wfi` (psci-mode 0x1) and `llcc-off` (psci-mode 0xc24, 3263/6562/9987 us, `qcom,is-reset`, `qcom,notify-rpm`), CPU levels `wfi` (1) and `rail-pc` (4); no separate system/CXO level.
  Mainline's `cluster-sleep-0` = `0x4100c244` is exactly that (0xc24<<4 | 4, plus PSCI powerdown type/level bits). So **we already use the vendor's deepest kernel-visible state**; going on to AOSD/CXSD/DDR self-refresh is left to the firmware (TZ/hyp + AOSS) once the cluster is down and no votes remain.
- **Our state:** PSCI v1.1, `OSI mode supported`; the cluster domain enters `cluster-sleep-0` (7.6k times in ~90 s awake, some rejected/above); `aosd`/`cxsd`/`ddr` counts stay 0 after suspends; `cx`/`mx` sit at LOW_SVS (48) awake; DDR idles at 768 MHz; interconnect votes while awake include display (qxm_mdp ~1.1 GB/s each), USB (1 GB/s) and ebi 3.3 GB/s.
- **Upstream history [S]:** SM8250 cpuidle states added, reverted (Oct 2022, RB5 instability), cluster state disabled then re-enabled for v6.2 after the rpmh-rsc/cluster-PD genpd work (Ulf Hansson, Nov 2022); sdm845 PC->OSI (Abel Vesa, 2022); 2026: Dmitry Baryshkov's C630 "lower PSCI cluster idle" (cluster state unstable if display not probed early; open) and Maulik Shah's rpmh-rsc debug series. No public report found of a mainline SM8250/8150/8350 device with non-zero cxsd/aosd counts.
- **Code, verified:** `cpuidle-psci-domain.c` powers the cluster domain only in OSI mode (else ALWAYS_ON); `rpmh-rsc.c` flushes the sleep/wake sets on the cluster PD's PRE_OFF notifier (skipped with the HW solver); `s2idle` does not use PSCI SYSTEM_SUSPEND.
Sources: <https://lore.kernel.org/r/20220630101403.1888541-1-abel.vesa@linaro.org>, <https://lkml.iu.edu/2210.2/01396.html>, <https://lore.kernel.org/all/20221122123713.65631-1-ulf.hansson@linaro.org/T/>, <https://lkml.iu.edu/hypermail/linux/kernel/2303.3/05913.html>, <https://lkml.iu.edu/hypermail/linux/kernel/2604.3/08525.html>, <https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2606.1/10780.html>, <https://docs.qualcomm.com/doc/80-70020-30/topic/qcs6490-soc-power-saving-state.html> (cxsd/aosd debugfs on QCS6490).

Cheap experiments left, in order (all read-only or low risk): (1) `tools/sleepstat.sh` before/after a 30-60 s suspend and see whether the cluster's `S2idle` count and `aosd/cxsd` move; (2) find what holds votes after suspend (`interconnect_summary`, `clk_summary`, `regulator_summary`, `pm_genpd_summary`: cx/mx corner, any rpmhpd consumer left active); (3) `cpuidle` governor/`s2idle` depth; (4) `CONFIG_PSCI_CHECKER` once (boot hang risk); (5) `mem_sleep=deep` (PSCI SYSTEM_SUSPEND) if `psci_features` allows it (hang risk).
