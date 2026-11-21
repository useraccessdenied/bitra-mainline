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


## Long run (first debug kernel)
`bitra-drm anim 0 600 1 v`: 72,351 vblanks in 600 s = **120.5 Hz, no drift**; no DPU errors, no sanitizer/lockdep/hung-task findings; a further 120 s animation held ~115 fps on the heavy debug kernel.

## Second debug kernel (7.2.0-g50c10c1c4741 = bitra + the 3 fixes) — verification
- **Type-C UBSAN**: gone from the boot log (UBSAN: 0). Fixed by commit ee1805433.
- **Self-refresh leak**: after the same 10 panel rebinds, kmemleak shows **0** `drm_self_refresh_helper_init` objects (was 2 per rebind); only the 2 benign `build_sched_domains` objects remain. Fixed by fba17282e.
- **Watchdog**: userspace was reached at ~25-30 s uptime on the debug kernel and the phone stayed up (qcom-wdt patch 50c10c1c4).
- **msm_gem.c:170 WARN** (19 in 10 rebinds) unchanged — not fixed, see finding 3.
- Second fault-injection run (40 probes @25% failslab): all 40 probes failed as injected and unwound, 0 leaks from the panel driver, 0 self-refresh leaks, **but this time the run also produced**
  - `refcount_t: underflow; use-after-free` in `drm_dev_put()` from `__drm_atomic_commit_free()` called by **`drm_self_refresh_helper_entry_work`** while a failed display bring-up was being unwound;
  - `KASAN: null-ptr-deref` in `update_lru_locked` <- `put_pages` <- `msm_gem_free_object` <- `msm_gem_kernel_put` <- `msm_dsi_tx_buf_free` <- `dsi_unbind` <- `component_unbind_all` <- `msm_drm_uninit` <- `msm_drm_unbind` <- ... <- `ams662zs01_remove` (unbind).
    `update_lru_locked()` dereferences `obj->dev->dev_private`; it is NULL, i.e. the DSI tx-buffer GEM object belongs to a DRM device whose `msm_drm_init()` error path already ran `ddev->dev_private = NULL; drm_dev_put(ddev)` (msm_drv.c) while the DSI component still owned the buffer.
  Both are in upstream msm/DRM error-unwinding (not in the panel driver). The first run (random 25%) did not hit them, the second did: different injection points. They need the deterministic sweep below to attribute precisely (is the refcount imbalance caused by the new drmm self-refresh cleanup, or pre-existing? the splat shows the *worker* doing the put, and the imbalance exists before my cleanup runs, but this is NOT proven).

## Deterministic sweep (`soak.sh failnth FROM TO`) and an unresolved hang
`/proc/self/fail-nth` fails exactly the Nth slab allocation of the task that writes `bind`, so N = 1, 2, ... walks every allocation point of the panel probe + DRM bring-up.
The first attempt (`failnth 1 6`) never returned: the agent command timed out after 120 s and **the phone then stayed unreachable for 20+ minutes** (agent state `absent`; the Mac showed a fresh USB network interface with a DHCP lease from the phone, but nothing answered on 192.168.2.15:23, so the phone was alive in some early boot stage).
Not diagnosed: it may be (a) a real kernel hang/deadlock in the unbind/bind path at a small N (small N also hits the shell's own VFS/sysfs allocations), (b) a hard hang followed by a watchdog reset into the *flashed* Droidian that then stuck in its initrd, or (c) something unrelated. Needs a physical power cycle (hold Power ~15 s) before any further tests.
Lessons for the harness: run the sweep from a start N above the shell/VFS allocations, in small chunks, with each chunk's result written to a file the next call can `get`; consider a tiny helper binary that does the fail-nth write + bind itself, so the injected failures only hit the driver path; and make sure a hung phone can reach fastboot without a key combo (it cannot today: `to-fastboot` needs the shell).

## Round 3: deterministic fail-nth (2026-11-21)

**Why the first sweep hung the phone:** `soak.sh failnth` set failslab `probability=100` *without* `task-filter`, so every
allocation on the whole system failed, not just the Nth one of the probe. Rewritten: failslab `task-filter=Y`, `probability=0`,
and a freestanding helper `tools/bitra-failnth.c` that opens the bind file and `/proc/self/fail-nth` first, arms N, does ONE
`write()` to `bind`, and prints `ret=… left=…` (`left=0` = the Nth allocation really failed). Only that write's allocations can fail.

**First real result (N=33, debug kernel t-dbg2):** a generic pinctrl bug, nothing to do with msm/DPU or the panel driver:
`parse_fw_cfg()` (drivers/pinctrl/pinconf-generic.c) passes an unchecked `bitmap_zalloc()` to `test_and_set_bit()` ->
`KASAN: null-ptr-deref in parse_fw_cfg` via `pinctrl_bind_pins()` during really_probe, followed by a NULL oops and a slab
use-after-free in the same task, and the shell/`reboot` then hung on the held device lock (the phone had to be force-restarted).
Fix committed in the kernel fork (6e291167c, upstream candidate, 3 lines). N=30..32 were clean (the injected failure was
handled, `probe=ok`).

**Consequence for the earlier msm findings:** the refcount-underflow / `msm_drm_uninit` NULL deref seen under 25% random fault
injection are still unattributed; a sweep after the pinctrl fix (t-dbg3) is needed, because any splat after N=33 on t-dbg2 was
polluted by the oops.

## Round 3 results (kernels t-dbg3..t-dbg5, 2026-11-21)

Sweep: `soak.sh failnth FROM TO OUTFILE [STEP]` (fail exactly the Nth slab allocation of one `write()` to the panel driver's
`bind`, then rebind if the probe failed, grep dmesg for KASAN/UBSAN/refcount/BUG/lockdep). The probe makes well over 400
allocations (N up to 400 still hit one with `left=0`), so the sweep continues with a stride.

Findings, each reproduced deterministically and fixed in the kernel fork (all upstream candidates):

| N (t-dbg3/4) | splat | cause | fix |
|---|---|---|---|
| 33 | KASAN null-ptr-deref `parse_fw_cfg` (pinctrl core), then oops + UAF + hung unbind | unchecked `bitmap_zalloc()` | 6e291167c pinctrl: check the allocation |
| 5, 22 | `refcount_t: addition on 0` / underflow in `drm_self_refresh_helper_entry_work` -> `drm_dev_put` | the delayed work takes a drm_dev ref when it runs; cancelling it from my drmm action (fba17282e) is too late, the device is already being released. The work is pre-existing upstream, my action did not create the race (without it the work would also outlive the device, and leak) | cancel/free the helper data in `msm_drm_kms_uninit()` while the device is still referenced |
| 99+ (after a failed init) | KASAN slab-use-after-free in `kthread_destroy_worker` | `struct msm_kms` outlives the DRM device across unbind/bind; `msm_drm_kms_uninit` destroyed `event_thread[].worker` without clearing it, so a later failed bring-up destroyed the stale workers again | clear the pointers |
| 752 (the last allocation point; the probe makes ~750 slab allocations) | KASAN null-ptr-deref in `touch_wq_lockdep_map` via `msm_drm_kms_uninit` -> `flush_workqueue(kms->wq)` | same lifetime class: `msm_kms_destroy()` freed `kms->wq` without clearing it; a failed next bring-up (before/inside `msm_kms_init`) flushes a stale/NULL queue. The oops killed the helper while it held the device lock, so unbind/reboot then hung (power cycle needed) | clear the pointer, guard the flush (t-dbg6, built and committed, not yet swept) |
| 99+ | KASAN double-free in `dpu_kms_global_destroy_state` | `dpu_kms_destroy()` finalises the global private object even if `hw_init` failed before initialising it / it was already finalised | guard + zero after fini |

After these (t-dbg5): N=1..400 = zero splats except N=47, which is the devcoredump issue below. The failed-probe range unwinds
cleanly (`probe=failed` on injected -ENOMEM, immediately rebindable).

**Open, upstream-side: display error snapshots pin the DRM device.** `msm_disp_snapshot_*` stores a duplicated atomic state
(`disp_state->atomic_state`, holds framebuffer/gem + drm_dev references) in a devcoredump that lives for 5 minutes. (a) With
fast unbind/bind cycles each snapshot keeps its drm_device alive: after ~64 bring-ups drm_minor_alloc returns ENOSPC and every
bind fails with -28 (this made the first t-dbg4/5 sweeps meaningless from N~110 on; the harness now purges
`/sys/class/devcoredump/devcd*/data` every iteration). (b) If the coredump is freed after teardown, `msm_disp_state_free` ->
`drm_atomic_commit_put` -> `msm_gem_free_object` dereferences `dev_private` (NULL after `msm_drm_uninit`): oops in
`devcd_del` (N=47). Possible fix: snapshot should format its atomic state to text or drop the references when the DRM device
is torn down; not done.

Recovery notes: after a KASAN oops in a driver unbind the shell can still answer; `to-fastboot` works but may take a minute.
`echo b > /proc/sysrq-trigger` over the agent timed out and left ABL in a state where the next RAM boot never enumerated
(needed a power cycle) - use `to-fastboot`.

Coverage: N=1..400 every allocation, N=401..752 every 9th, then the sweep reached the end of the probe (left>0 at 752 on
t-dbg5). Result tables of the raw sweeps are kept in the scratchpad only; the table above is the summary. Still to do: sweep
t-dbg6 over the end region (N=700..760) and the stride range once more, and a clean N=1..400 on t-dbg6.
