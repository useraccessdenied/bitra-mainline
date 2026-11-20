# 23 — Display soak test on a KASAN/lockdep debug kernel (2026-11-21)

Goal: find latent memory/locking bugs in the display path (msm DPU + DSI + our panel driver) without waiting for a "static noise" screen in daily use.
Everything automated through the agent; RAM boots only. Harness: `tools/soak.sh` (baked into the initramfs as /bin/soak.sh), debug kernel built in a separate output dir.

## Debug kernel
Same source/config as the normal build + KASAN (generic, inline, vmalloc), UBSAN (bounds, shift, unreachable), PROVE_LOCKING (lockdep), DEBUG_ATOMIC_SLEEP, DEBUG_LIST/SG/NOTIFIERS/MUTEXES/SPINLOCK,
SLUB_DEBUG_ON, PAGE_POISONING, DEBUG_KMEMLEAK, DEBUG_OBJECTS (timers/work/free), DEBUG_SHIRQ, soft-lockup + hung-task detectors, WQ_WATCHDOG, FAULT_INJECTION (+failslab, fail_page_alloc).
30 MB Image.gz (13 MB normally), 38 MiB boot image (still accepted by `fastboot boot`). Userspace is reached at ~20 s, inside the ~35 s bootloader watchdog window
(a watchdog patch was added so the kernel itself pets an already-armed qcom watchdog: `drivers/watchdog/qcom-wdt.c`).
Build: `make O=../out-debug ...`; image: `MAINLINE_OUT=.../out-debug python3 scripts/build_mainline_boot.py NAME --cmdline-extra "... kasan_multi_shot"`.

## Phases and results (first debug kernel, 7.2.0-g4dbb0bd0e9f0)
| Phase | What | Result |
|---|---|---|
| boot | whole boot log | known DSI PLL WARNs (2), kmemleak start msgs, **1 UBSAN: typec** (below) |
| modes x40 | 80 full modesets 120<->60 Hz | clean |
| blank x60 | panel off/on through fbdev blank (panel unprepare/prepare) | no sanitizer hits; **60/60 cycles log `[drm:dpu_encoder_helper_wait_for_irq] *ERROR* encoder is disabled ... dpu_encoder_phys_cmd_ctl_start_irq`** (functional, upstream DPU) |
| backlight x8 + anim 40 s | sweeps 0..2047, full-height animation | clean; 114 fps measured on the heavy debug kernel |
| mix 180 s | modes + blank + backlight + animation in parallel + 4 CPU hogs (load 5.8) | clean |
| rebind x10 | unbind/bind the panel driver (DRM device torn down and rebuilt) | survived; **20 WARN `msm_gem.c:170`**, **kmemleak 2 real leaks per rebind** |
| fault x40 @25% | probe the panel driver with 25% of its slab allocations failing | 40/40 probes failed as injected and unwound; every time a clean rebind worked; **no KASAN/UBSAN/lockdep; no leak from the panel driver** |
Totals over the session: KASAN 0, lockdep 0, hung task/soft lockup 0, Oops 0. 

## Findings
1. **UBSAN invalid-load in `typec_register_altmode()`** (`drivers/usb/typec/class.c:658`): "load of value 128 is not a valid value for type 'bool'". Cause: `struct typec_altmode_desc desc;` in `typec_port_register_altmodes()`
   is never zeroed; only svid/vdo/mode are set, then `mode_selection` and `roles` are read from stack garbage. Generic upstream bug (every Type-C port via that path). Fixed: `= { }` (commit ee1805433). Upstream candidate.
2. **Real leak in the DPU: `drm_self_refresh_helper_init()` without cleanup** (`dpu_crtc_init()`): 512 bytes per CRTC (2) per DRM bring-up never freed. kmemleak after 50 bring-ups: 100 objects, all one allocation site; plus 2 benign
   `build_sched_domains` leaks (scheduler topology, known false positives). Fixed with a drmm action (commit fba17282e). Upstream candidate.
3. **`msm_gem.c:170` WARN (`GEM_WARN_ON(msm_obj->pin_count)`)** on every fbdev teardown (panel unbind): `msm_fbdev_fb_destroy -> drm_framebuffer_remove -> msm_gem_free_object -> put_pages -> update_lru_locked`;
   the fbdev GEM object is freed while still pinned. Upstream msm GEM lifetime issue; only on DRM device teardown (rebind), not in normal use. NOT fixed; tracked.
4. **`encoder is disabled` error on every panel off/on** (fbdev blank): command-mode kickoff waits for the ctl_start IRQ after the encoder was disabled (race in `dpu_encoder_phys_cmd`). Functional/log noise so far; the panel recovers and works. NOT fixed; tracked.
5. Panel driver itself: no sanitizer/lockdep findings, no leak in 40 injected-failure probes. Earlier hardening (PPS-failure power-down, connector pointer cleared on remove) is exercised by the rebind/fault phases.
6. Known/benign: DSI PHY PLL WARNs at boot (see known-issues).

## Verification of the fixes
See the section below (second debug kernel run).
