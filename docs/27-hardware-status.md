# 27 — Hardware status tracker (mainline 7.2.0 on realme GT Neo 2 / bitra)

Single place to see what works. **Keep this file updated** whenever hardware is found, tested or fixed (date + evidence).
Last full review: **2026-11-22** (quick tests of keys, haptics, NFC, suspend the same day), kernel `7.2.0-g593dc521516f-dirty` + DT `dac11722c`, boot image `a-7.img`, Alpine 3.24 on `userdata`.

Status: **Working** = verified on the phone | **Partial** = works with gaps (listed) | **Not working** = understood, not done | **Untested** = driver/device present, function not verified | **Not tried** = no work yet | **Skip** = decided not to support.
"Verified" below means seen on the real phone in a session; details live in the doc named in the last column. Open upstream-side kernel bugs are in docs/24, deferred owner items in docs/known-issues.md.

## Platform / boot
| Item | Status | Evidence / gaps | Next step | Doc |
|---|---|---|---|---|
| Boot path | **Partial** | RAM boot only: Droidian initrd -> `to-fastboot` -> `ramboot`. ABL refuses mainline DTBs, so the Droidian base DTB is passed and `BITRA_DTB_SHIM` swaps in ours. Nothing flashed to `boot`. | standalone boot (flash a mainline boot image, keep a recovery path) | 18 |
| Reboot / `reboot bootloader` | **Working** | PMIC PON reboot-mode; `to-fastboot` works from initramfs and from Alpine. | | 18 |
| Power-off | **Untested** | | test `poweroff`/long-press behaviour | |
| CPU / SMP / cpufreq | **Working** | 8 CPUs, schedutil, cpu7 seen at 1.86 GHz. cpuidle states, big-core max frequency under load: unverified | measure idle states, boost | |
| Memory / ramoops (pstore) | **Working** | Layout identical to stock; pstore holds the console after a crash | | 18 |
| Watchdog | **Working** | `qcom-wdt` patch (upstream candidate #3); userspace pet loop in the initramfs survives switch_root. Alpine has no own pet service yet | add a watchdog service in the rootfs | 24 |
| Thermal sensing (TSENS) | **Working** | 33 thermal zones report temperatures (needs modules). Trip points / throttling under load: unverified | stress test, verify throttling | 26 |
| Suspend / resume (s2idle) | **Partial** | Verified 2026-11-22: `pm_test` freezer/devices/platform pass; real s2idle resumes (Wi-Fi stays associated, backlight, touch, clock all fine). Wake from RTC alarm, power key, volume up and touch verified. Only s2idle (no deep `mem` suspend). Not measured: suspend power draw, cpuidle depth, volume-down/USB/Wi-Fi wake, long/repeated cycles, UI screen-blank flow | measure draw on battery, enable PSCI deep idle, WoWLAN | 28 |
| PMIC RTC | **Partial** | `rtc0` counts but is read-only (as on Android); `bitra-time` keeps an offset in `/var/lib`, restores it at boot with no network, NTP corrects. | alarm/wake support | 26 |
| Kernel modules | **Working** | 548 options are modules; stripped modules (14 MB) are in the rootfs, `hwdrivers` loads them by modalias (36 loaded). Release string includes the git hash: keep kernel and modules in step | production config trim, `depmod` at install | 26 |
| Hardware RNG / crypto | **Untested** | `/dev/hwrng` and 561 crypto algorithms present | check ICE for UFS inline crypto (not needed yet) | |

## Display / GPU / input
| Item | Status | Evidence / gaps | Next step | Doc |
|---|---|---|---|---|
| Panel Samsung AMS662ZS01 (DSI cmd mode, DSC, 1080x2400) | **Working** | msm DPU/DSI, new panel driver, backlight 0..2047, fbdev `msmdrmfb`; **fbcon text renders on the panel** (Alpine login on tty1) | | 18, 25 |
| Panel gaps | **Partial** | DSI PHY PLL warnings at boot; panel suspend/resume never exercised; 120/90 Hz modes and ESD/TE over long runs unverified; no ESD polling like stock | see docs/known-issues.md (deferred) | 23 |
| Pixelworks Iris5 co-processor | **Skip** | Bypassed ("soft" mode: DSI goes straight to the panel) | | 18 |
| GPU Adreno 650 | **Not working** | `gpu`/`gmu` disabled in DT, no firmware; `/dev/dri/card0` + `renderD128` are KMS only (software rendering) | enable with `a650` firmware, test | |
| DisplayPort / USB-C alt mode | **Not working** | `mdss_dp` disabled; FSA4480 mux probed on i2c15 | after USB-C role switch work | |
| Touchscreen Synaptics S3908 (TouchComm) | **Partial** | Works (driver ported, docs/22). Suspend wake by touch and touch after resume verified 2026-11-22 (any touch wakes; no double-tap gesture mode). Open: double-tap-only wake, axis orientation in a real UI, no pressure | wake + orientation tests | 22 |
| Power key / volume keys | **Working** | Verified 2026-11-22 with `evtest`: power key = `KEY_POWER` (pm8941_pwrkey, event0); volume up and down = `KEY_VOLUMEUP`/`KEY_VOLUMEDOWN` on the "Volume keys" gpio-keys device (event4), with autorepeat. `pm8941_resin` (event1) gets no events: volume-down arrives via gpio-keys, so it is an unused duplicate | maybe drop the resin node from the DT; test long-press power behaviour (PMIC resets after a long hold) | 26 |
| Haptics AW8697 (driver `aw8695-haptics`) | **Working** (basic) | Verified 2026-11-22: FF_RUMBLE effect upload + play via `tools/bitra-haptic.py`, owner felt 3 x 600 ms and 3 x 800 ms pulses. Untested: effect strength/waveform variety (FF_PERIODIC), f0 calibration quality, use from a UI | vibration profiles for a UI (feedbackd) | 19 |
| Notification LED / flash | **Not tried** | No LEDs in `/sys/class/leds`; `pm8150l_flash` disabled in DT | check stock for an LED node | |
| Ambient light / proximity / accelerometer / gyro / magnetometer | **Not working** | SLPI remoteproc not running (see Remoteprocs); IIO shows only PMIC ADCs | enable SLPI + sensor drivers | 20 |
| Fingerprint (Jiiov, under display) | **Not tried** | Calibration data is in `persist`; no mainline driver known | research | 18 |

## Storage / USB / power
| Item | Status | Evidence / gaps | Next step | Doc |
|---|---|---|---|---|
| UFS 3.1 (Samsung KLUEG8UHDB, 256 GB) | **Working** | Alpine root on `sda11` (ext4), 600 MB written at ~750 MB/s, readback hash identical, grown to 222 GiB. Untested: suspend/hibernate, write booster, ICE, RPMB | | 21, 25 |
| USB device mode (gadget NCM) | **Working** | USB-NCM shell for the agent, DHCP pool, survives switch_root | | 18 |
| USB host / OTG | **Not working** | `dr_mode = "peripheral"` forced, no role switch | typec role switching | |
| USB Type-C (PMIC `typec`, tcpm) | **Partial** | `typec/port0` + partner present, `tcpm-source-psy` registered; PD negotiation, orientation, role swap untested | | |
| Fuel gauge BQ28Z610 | **Working** (read-only) | i2c16 @0x55: capacity, voltage 8.4 V (2S), current, temp, cycle_count 1695, charge_full 1480/2465 mAh | monitored-battery data, `charge_full` calibration | 26 |
| Charging | **Partial** | Charges by itself over USB (gauge: Charging, +331 mA at 5 V from a Mac). No driver controls it: MP2650 (i2c5), Oplus charge pump (0x68), RK826 VOOC MCU, SMB1390, pm8150b smb5 — **fast charging not working**, input current limit unknown | read PMIC FG as cross-check, MP2650 datasheet, then a safe driver (float voltage is the risk) | 26 |
| Battery health | **Info** | ~60 % of design capacity, 1695 cycles | | 26 |

## Connectivity
| Item | Status | Evidence / gaps | Next step | Doc |
|---|---|---|---|---|
| Wi-Fi QCA6390 (ath11k, PCIe0) | **Partial** | WPA2/WPA3 connect, DHCP, internet, boot-time `bitra-wifi`. Gaps: placeholder MAC (`use-nv-mac` not read), generic firmware board data (no OEM BDF from `persist/bdwlan.elf`), scan stuck ("Resource busy") after `select_network`, power-save/suspend, regulatory (self-managed US), roaming | convert bdwlan.elf to board-2.bin, real MAC | 18, known-issues |
| Bluetooth QCA6390 (hci0, uart6) | **Partial** | Controller + firmware load, classic inquiry works. LE scan unverified, BD address is a placeholder, no bluez daemon in use, no pairing/A2DP | run `bluetoothd` + `bluetoothctl`, real address | 18, known-issues |
| NFC NQ-NCI (nxp-nci, i2c1 @0x28) | **Partial** | Verified 2026-11-22 with `tools/bitra-nfc.py` (kernel NFC netlink, no neard): controller powers up, polls and **detects an ISO14443-A target** (ATQA 0400, SAK 20 = ISO-DEP, random 4-byte UID). Untested: reading NDEF/tag data, other protocols (B, F, 15693), card emulation / host-card-emulation, p2p, antenna range, power use; neard is not in Alpine 3.24 | NDEF read (libnfc is not usable: it does not speak the kernel NCI subsystem), HCE | 19 |
| Cellular modem (Qualcomm X55, external SDX55M over PCIe2/MHI + IPA) | **Not working** | `pcie2` disabled, MPSS not running, no modem nodes; SIM/IMS/calls/SMS/data none; must keep IMEI/modem NV safe (rmtfs) | docs/20 plan, rmtfs, MHI | 20 |
| GNSS / GPS | **Not tried** | via modem/SLPI | after modem | |
| FM radio (rtc6226) | **Skip** | | | 19 |

## Audio / camera / remoteprocs
| Item | Status | Evidence / gaps | Next step | Doc |
|---|---|---|---|---|
| Remoteprocs ADSP / CDSP / SLPI / MPSS | **Not working** | `/sys/class/remoteproc` is empty: none enabled/started. Blocks audio, sensors, modem, camera, some charging/PD features | firmware paths + `qcom_q6v5_pas`, test one at a time | 20 |
| Audio (Q6 / WCD938x / WSA / macros) | **Not working** | No sound card. `snd-sm8250` deferred ("MultiMedia1: error getting cpu dai name"); LPASS pinctrl `33c0000` and macros wait for suppliers. | needs ADSP; fix LPASS pinctrl/macro deferrals | |
| Speaker amplifiers 2x TFA987x | **Partial** | Both amps probe on i2c15 (0x34/0x35, chip revision 0x0c74); no audio path yet | after ADSP | 19 |
| USB-C audio mux FSA4480 | **Untested** | Probes on i2c15 @0x42 (i2cget works) | | |
| Microphones / earpiece / headset | **Not tried** | | | |
| Cameras (CAMSS) | **Not working** | No `/dev/video*`; `camss` and `venus` exist as modules but no sensor nodes, PM8008 camera regulators | sensor DT from stock, `persist/camera` calibration | 19 |
| Video codec (Venus) | **Not tried** | | | |

## Userspace / OS (Alpine on userdata)
| Item | Status | Evidence / gaps | Next step |
|---|---|---|---|
| Alpine 3.24 root on UFS | **Working** | boots in ~25 s after the kernel; OpenRC; apk works (clock fixed); persistence verified across reboots | |
| Console on the panel | **Working** | tty1 login, diagnostics block in `/etc/issue` | |
| Network shells (USB-NCM telnet/ssh, Wi-Fi ssh) | **Working** | agent shell, sshd, Wi-Fi at boot | harden (telnet is root, no password, on 0.0.0.0 by owner choice) |
| Graphical session (sway/Phosh) + touch | **Not tried** | needs GPU decision (software rendering OK first) | |
| Standalone boot (no Mac) | **Not working** | see Boot path | |
| Production kernel config | **Partial** | non-debug, modules shipped; still the pmOS-derived superset (548 modules) | trim, `LOCALVERSION`, signed/reproducible build |
| Hardware keys in UI, rotation, brightness UI | **Not tried** | | |
| Power management daemon, battery UI | **Not tried** | gauge data exists | |

## How to update this file
1. After testing something, change its row (status, evidence with date, next step) in the same commit as the code/doc change.
2. New hardware found (e.g. via `/sys`, stock FDT in `docs/19`): add a row, status `Not tried`.
3. Keep the "Last full review" line current; re-run the read-only snapshot (remoteprocs, sound, video, iio, thermal, input, power_supply) when reviewing.
