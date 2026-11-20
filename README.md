# bitra-mainline

Mainline-Linux bring-up of the **realme GT Neo 2** (bitra, Snapdragon 870 / SM8250-AC): tooling, notes and patch exports.
Companion repos:
- kernel: https://github.com/useraccessdenied/linux-sm8250-realme-bitra (branch `bitra`)
- Android/Droidian build repo: https://github.com/useraccessdenied/bitra-lineageos

Status: mainline 7.2.0 RAM-boots with USB NCM shell (stage 1). See `docs/18-mainline-bringup.md`.

- `scripts/build_mainline_boot.py NAME` — build a `fastboot boot` image (needs the kernel build dir, `BITRA_REPO`, `MAINLINE_OUT`).
- `docs/` — bring-up log, hardware map, research. `patches/` — kernel patch exports.
- Boot via `ssh mac to-fastboot` from the running OS (a key-combo fastboot makes the OPLUS ABL refuse images).

Everything is experimental and AI-assisted (see AI_DISCLOSURE.md). RAM boots only; never flash from here without a backup.
