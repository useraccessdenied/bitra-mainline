# bitra-mainline

Mainline-Linux bring-up of the **realme GT Neo 2** (bitra, Snapdragon 870 / SM8250-AC): tooling, notes and patch exports.
Companion repos:
- kernel: https://github.com/useraccessdenied/linux-sm8250-realme-bitra (branch `bitra`)
- Android/Droidian build repo: https://github.com/useraccessdenied/bitra-lineageos

Status: mainline 7.2.0 RAM-boots and runs **Alpine 3.24 from UFS (`userdata`)** with panel console, USB NCM + Wi-Fi shells. See `docs/18-mainline-bringup.md`, `docs/25-alpine-rootfs.md`.

- `scripts/build_mainline_boot.py NAME` — build a `fastboot boot` image (needs the kernel build dir, `BITRA_REPO`, `MAINLINE_OUT`).
- `docs/` — bring-up log, hardware map, research. `patches/` — kernel patch exports.
- Boot via `ssh mac to-fastboot` from the running OS (a key-combo fastboot makes the OPLUS ABL refuse images).

Everything is experimental and AI-assisted (see AI_DISCLOSURE.md). RAM boots only; never flash from here without a backup.

- `docs/21-ufs.md` — UFS storage on mainline; `docs/22-touchscreen.md` — touchscreen research and effort estimate; `docs/known-issues.md` — open items.
- `scripts/build_alpine_rootfs.py` — Alpine rootfs image (no sudo); `docs/25-alpine-rootfs.md` — how it boots and was flashed.
