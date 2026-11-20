# 21 — UFS storage on mainline (read-only probe, 2026-11-21)

Status: **works** (RAM boot, nothing mounted writable). Kernel 7.2.0, image `t-u1`. Details also summarised in docs/18.

## Hardware
- Controller: Qualcomm UFS HC `1d84000.ufshc` (+ QMP UFS PHY), driver `ufshcd-qcom` (built in: SCSI_UFSHCD_PLATFORM, SCSI_UFS_QCOM, BLK_DEV_SD, PHY_QCOM_QMP_UFS).
- Device: **SAMSUNG KLUEG8UHDB-C2D1** (UFS 3.1, 256 GB; this phone is SM8250 = UFS 3.1, not UFS 4.0). Six LUNs `sda`..`sdf` (+ 3 well-known LUNs).
- Device-tree wiring (kebab/common values were verified against the stock tree before enabling): `vcc` = pm8150_l17 (3.0 V) = `vreg_l17a_3p0`,
  `vccq` = pm8150_l6 (1.2 V) = `vreg_l6a_1p2`, `vccq2` = pm8150_s4 (1.8 V) = `vreg_s4a_1p8`; PHY `vdda-phy` = `vreg_l5a_0p88`, `vdda-pll` = `vreg_l9a_1p2`. Stock lanes = 2, `dev-ref-clk-freq` = 19.2 MHz.
- Harmless boot notices: `freq-table-hz property not specified`, `Unable to find vdd-hba-supply regulator, assuming enabled`.

## LUN / partition map (matches Android's /dev/block/sd*; from backups/*/info/by-name.txt)
- sda (253 GB): 11 partitions incl. `persist` (sda2, ext4), `cache`, `metadata`, `super` (sda10), `userdata` (sda11, ext4 in Droidian layout).
- sdb: xbl (sdb1), xbl_config (sdb2). sdc: (xbl backup LUN). sdd: devinfo-ish/ALIGN partitions. sde (2.1 GB): firmware + modem/dsp/bluetooth images: aop sde1, hyp sde3, modem sde4, bluetooth sde5, abl sde8, dsp sde9, keymaster sde10, cmnlib64 sde13, devcfg sde14, qupfw sde15, multiimgoem sde21, featenabler sde24, imagefv sde25. sdf: oplus/opporeserve and misc.
- Never write: xbl*, abl, aop, hyp, devcfg, keymaster, imagefv, multiimgoem, modemst1/2, mdm1* , persist, oplusreserve*.

## Safety procedure used (reuse it)
1. RAM boot only (`ssh mac to-fastboot; ssh mac ramboot IMG`); the initramfs mounts nothing from UFS.
2. Immediately `blockdev --setro` on every /dev/sd? and partition.
3. Compare against the 2026-11-16 backup (67 partition images + GPT dumps `info/gpt-sd?.bin`).
4. Mount only with `-o ro,noload,nodev,nosuid,noexec` (ext4 journal not replayed).
Caveat (unverified, unavoidable): ufshcd performs standard device queries at init, some of which can write device attributes/flags (e.g. bActiveICCLevel, fDeviceInit, bRefClkFreq if different).

## Verification results
- GPT: sdb..sdf first MiB identical to the backup byte for byte. sda: partition entries identical (11 entries, same GUIDs/ranges, same disk GUID); the first-MiB hash differs only in 28 blocks starting at `persist` (live ext4, expected drift).
- Read integrity: sha256 of 15 firmware partitions read through mainline UFS = backup hashes, 15/15 (abl, aop, devcfg, hyp, keymaster, xbl, xbl_config, imagefv, multiimgoem, qupfw, dsp 64 MiB, modem 195 MiB, bluetooth, cmnlib64, featenabler).
- `persist` mounted read-only: contents listed in docs/18 (bdwlan.elf = OEM Wi-Fi board data, regdb.bin, wlan/*.ini, camera/fingerprint/sensor calibration; no plain Wi-Fi MAC / BT address file).

## Open
- Real Wi-Fi MAC / BT address (stock: `use-nv-mac`, modem NV) — read from Droidian or pick a persistent random address.
- Convert `persist/bdwlan.elf` (+ regdb.bin) into an ath11k board-2.bin entry.
- Write path untested on purpose: no filesystem is mounted rw from mainline yet; a mainline rootfs needs a deliberate plan (which partition, backups, never touching the firmware LUNs).
- Throughput/latency, suspend (UFS link hibern8), write booster, RPMB, inline crypto (ICE) not exercised.
