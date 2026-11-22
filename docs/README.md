# bitra-mainline docs

Numbering continues the `bitra` workspace docs (00–17 cover LineageOS and Droidian there). Start with **27** for the current state.

| Doc | What it is |
|---|---|
| [31-audio.md](31-audio.md) | ADSP firmware, sound card (model/routing/DP link), speaker playback and bottom microphone (UCM, PulseAudio), top-mic search, open items |
| [32-sensors.md](32-sensors.md) | SLPI remoteproc, hexagonrpcd (FastRPC) and the Sensor Core; why no sensor is enumerated yet |
| [30-phosh.md](30-phosh.md) | Phosh session (tinydm/elogind/NetworkManager/UPower), the cgroup cmdline fix, open items |
| [29-graphics-gpu.md](29-graphics-gpu.md) | Sway on the panel (touch, keys, 120 Hz) and Adreno 650 acceleration (freedreno/turnip), firmware pitfalls |
| [28-suspend-resume.md](28-suspend-resume.md) | s2idle suspend/resume: staged test, wake sources verified, gaps |
| [27-hardware-status.md](27-hardware-status.md) | **Hardware status tracker**: working / partial / not working / untested per block, with evidence and next steps. Keep it current. |
| [known-issues.md](known-issues.md) | Detailed open items, deferred owner items, parked fault-injection sweep state |
| [25-alpine-rootfs.md](25-alpine-rootfs.md) | Alpine 3.24 on `userdata`: image builder, switch_root hook, how it was flashed, gotchas |
| [26-battery-charger.md](26-battery-charger.md) | Fuel gauge, charger (deliberately not driven), power keys, modules, RTC/clock |
| [24-upstream-candidates.md](24-upstream-candidates.md) | Kernel fixes found by fault injection/KASAN, with commits and status (send order) |
| [23-display-soak.md](23-display-soak.md) | KASAN/lockdep debug-kernel soak of the display driver, deterministic fail-nth harness and results |
| [22-touchscreen.md](22-touchscreen.md) | Synaptics S3908 TouchComm research and bring-up |
| [21-ufs.md](21-ufs.md) | UFS storage: read-only probe, LUN/partition map, safety procedure |
| [20-mainline-research-firmware-rust-connectivity.md](20-mainline-research-firmware-rust-connectivity.md) | Research: firmware, Rust vs C, connectivity (SDX55M modem), order of work |
| [19-bitra-hardware-map.md](19-bitra-hardware-map.md) | Hardware map from the stock merged device tree |
| [18-mainline-bringup.md](18-mainline-bringup.md) | Historical stage-1 bring-up log (RAM boot, ABL DTB shim, panel, Wi-Fi, BT, UFS) |

Conventions: results are dated; "verified" means seen on the phone; every kernel change is committed in the fork (branch `bitra`) and exported to `patches/series/`
(`python3 scripts/export_patches.py`); upstream-worthy fixes get a row in docs/24; hardware changes update docs/27 in the same commit.
