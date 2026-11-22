# Upstream candidates (fixes to send to mainline)

Single list of everything in the kernel fork (`useraccessdenied/linux`-style fork, branch `bitra`, base b56ee7a86 = Linux 7.2.0-rc)
that is a generic bug fix, not a bitra bring-up hack. Update this file whenever one is added, changed, sent or merged.
Keep each fix as its own small commit so `git format-patch` gives a clean series. Commits carry `Co-Authored-By: Claude`;
upstream submission needs the human sender's Signed-off-by and the kernel's AI-assistance disclosure.

Status values: `local` (only in the fork), `sent` (link), `merged`.

| # | Commit | Subsystem | Bug | Found by | Status |
|---|---|---|---|---|---|
| 1 | ee1805433 | usb: typec | descriptor read uninitialised `bool` from stack (UBSAN "value 128"); zero the struct | UBSAN soak | local |
| 2 | fba17282e | drm/msm/dpu | `drm_self_refresh_helper_init()` never cleaned up: 512 B leaked per CRTC per bring-up (drmm action) | kmemleak, 50 rebinds | local; cleanup moved/complemented by #6 |
| 3 | 50c10c1c4 | watchdog: qcom | bootloader-armed watchdog not marked running at probe, nothing pets it before userspace (`WDOG_HW_RUNNING`) | slow debug-kernel boot resets | local |
| 4 | 54f0bd481 | input: synaptics TouchComm (imported driver) | hardening of the out-of-tree driver being proposed upstream (not a mainline bug) | review | local, part of the touch driver work |
| 5 | 6e291167c | pinctrl: pinconf-generic | `parse_fw_cfg()` uses unchecked `bitmap_zalloc()` -> NULL deref in `test_and_set_bit()` during probe | fail-nth, N=33 | local |
| 6 | 584df0429 | drm/msm | (a) self-refresh entry work takes a drm_dev ref when it runs; must be cancelled in `msm_drm_kms_uninit()`, not from a drmm action: "refcount_t addition on 0"/underflow; (b) `kms->event_thread[].worker` not cleared after destroy while `struct msm_kms` survives unbind/bind: UAF | fail-nth N=5/22, N=99+ | local |
| 7 | 7d8925a6c | drm/msm/dpu | `dpu_kms_global_obj_fini()` runs twice / before init: KASAN double-free in `dpu_kms_global_destroy_state` | fail-nth N=99+ | local |
| 8 | 136edf150 | drm/msm | `kms->wq` freed but not cleared in `msm_kms_destroy()`, flushed by the next failed bring-up's `msm_drm_kms_uninit()`: null-ptr-deref in `touch_wq_lockdep_map` | fail-nth N=752 | local; N=1..400 clean on t-dbg6, end region verified by the next run |
| 9 | 6e08a12ed | drm/msm | `msm_atomic_destroy_pending_timer()` and `msm_disp_snapshot_{init,destroy}` leave stale (or ERR_PTR) kthread workers in the surviving `struct msm_kms`: slab-use-after-free in `kthread_destroy_worker`, null-ptr-deref in `msm_disp_snapshot_destroy` | fail-nth N=733..739 on t-dbg6 | local; end region N=700..745 and stride 401..699 clean on t-dbg7/t-dbg10 |
| 10 | (not written) | drm/msm | `msm_disp_snapshot` devcoredump holds duplicated atomic state (fb/gem/drm_dev refs) for 5 min: pins the drm_device (DRM minors exhausted after ~64 fast rebinds, bind fails -ENOSPC) and its late free oopses in `msm_gem_free_object` (dev_private NULL) | fail-nth N=47, soak | **open, no fix yet** |
| 11 | (not written) | drm/msm | `msm_gem.c:170 GEM_WARN_ON` in `update_lru_locked` on every panel unbind (fb object freed while still pinned) | KASAN soak | **open** |
| 12 | (not written) | drm/msm/dpu | "encoder is disabled" DPU error logged on every panel blank/unblank (kickoff vs disable race) | soak | **open** |
| 13 | 4527ced2e | drm/msm | `msm_irq_install()` frees the irq when `msm_irq_postinstall()` fails but leaves `kms->irq_requested` set; `msm_irq_uninstall()` never clears it either -> second `free_irq()` ("Trying to free already-free IRQ" WARN) | fail-nth N=750..800 (t-dbg7) | local, verified N=770..790 on t-dbg10 |
| 14 | 593dc5215 | drm/msm/dpu | `dpu_kms_destroy()` leaves `rpm_enabled` set after `pm_runtime_disable()`; a later bind failing before `dpu_kms_init()` disables runtime PM again -> "Unbalanced pm_runtime_enable!" on the next good bind (and a lockdep splat via the printk) | fail-nth N=778 (t-dbg8) | local, verified N=770..790 on t-dbg10 |

Notes for sending:
- #1, #3, #5 are tiny and independent: send first (typec, watchdog, pinctrl lists).
- #6/#7/#8/#9 form one msm "teardown/error-path lifetime" series (+ #2); the common cause is `struct msm_kms`/`dpu_kms` surviving
  unbind/bind while the per-bind state is destroyed. Check each against drm-misc-next before sending; the DRM tree renamed
  `drm_atomic_state` -> `drm_atomic_commit` in this base, so patches may need a rebase.
- Evidence for each: docs/23-display-soak.md (stacks, N values), tools/soak.sh `failnth`, tools/bitra-failnth.c.
