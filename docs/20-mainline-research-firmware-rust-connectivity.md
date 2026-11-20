# 20 — Mainline research: firmware, Rust, connectivity (2026-11-21)

Method: 3 research subagents + local inspection of the phone's backed-up partitions. Confidence is marked. Caveat: postmarketOS is now
**Nura** (nura.eco, gitlab.nura.eco); wiki.nura.eco does not resolve and nura.eco is IPv6-only, so several Nura/pmOS pages could not be
read (incl. https://nura.eco/blog/2026/05/08/q6voice-project). Items below sourced only from search snippets are marked (snippet).

## 1. Firmware: is any of it open source?
No. Every Qualcomm block here needs binary firmware; no open replacement exists for Adreno GMU/SQE, ath11k WLAN, QCA BT, DSPs or the modem
(only reverse-engineering/fuzzing projects, none usable). "Redistributable" binaries in linux-firmware (WHENCE, LICENSE.qcom — the licence text itself was not read), not OSS.

| Block | linux-firmware (WHENCE) | What we must supply from the phone |
|---|---|---|
| Adreno 650 | qcom/a650_gmu.bin, a650_sqe.fw (generic) | zap shader: upstream only has the reference-board qcom/sm8250/a650_zap.mbn; retail OEM zap is signed/per-platform — use the phone's own (unverified cross-OEM loading) |
| Venus | qcom/vpu-1.0/venus.mbn | generic ok |
| ADSP/CDSP | qcom/sm8250/{adsp,cdsp}.mbn (reference build) | the phone's own from modem.img / dsp.img (signed per OEM; test before assuming other OEM blobs load) |
| SLPI | RB5-only build | phone's own |
| QCA6390 Wi-Fi | ath11k/QCA6390/hw2.0/{board-2.bin,amss.bin,m3.bin} | OEM board data (bdwlan) merged with ath11k-bdencoder, as done for Xiaomi elish |
| QCA6390 BT | qca/htbtfw20.tlv, htnv20.bin | also in bluetooth.img (htbtfw10/20, htnv10/20 present) |
| SDX55M modem | none | modem.img image/sdx55m/ (sbl1, apps, mdmddr, devcfg, aop, ...) + modem_pr/mcfg |
| IPA | none for sm8250 | ipa_fws from the phone |

Tooling (Nura/pmOS): pil-squasher (.mdt+.bNN -> .mbn), droid-juicer, fw-xtractor. Local check: backups/*/parts/modem.img is FAT with image/{adsp,cdsp,...}.mdt/.bNN and image/sdx55m/;
dsp.img is ext4 with adsp/cdsp/sdsp user-PD libs; bluetooth.img has the QCA BT files. Never touch: xbl, hyp, aop, devcfg, keymaster, imagefv, multiimgoem, abl.

## 2. Rust vs C for the new drivers (verdict: C)
Merged in mainline (7.x): platform/of, I2C (6.19), clk, regulator (version unverified), devres, irq, DRM core (Nova, Tyr).
Only posted: GPIO consumer (Sept 2026 v1), regmap (partial), drm_panel (stalled; DRM wants bridges), LED classdev. Absent/not found: input + force feedback, backlight, mipi_dsi.
Toolchain: Rust builds with LLVM=1 + bindgen (libclang); arm64 maintained; Fedora rust/bindgen packages are supported. DRM maintainers signalled Rust may become required for new DRM drivers "in about a year" (unconfirmed wording).
- AMS662ZS01 DSI panel: C (no mipi_dsi/drm_panel Rust). Touch (Synaptics TouchComm): C (no input). AW8697 haptics: C (no FF, no regmap).
- Only plausible Rust candidate: a small raw-transfer I2C chip driver, as a learning exercise. Revisit when GPIO + panel/bridge bindings land.
Honest note: memory safety is real, but missing abstractions would force hand-written unsafe bindings — where the bugs would be.

## 3. Connectivity facts specific to this phone
- **Modem is a discrete Qualcomm SDX55M on PCIe (pcie@1c10000, MHI), booted by the AP** (stock DT: `qcom,mdm0` = `qcom,ext-sdx55m`,
  `mhi_rmnet`, "voice-mhi" audio; modem.img carries sdx55m/ images; partitions mdm1m9kefs1-3/c, mdm1oemnvbktmp, mdmddr, modemst1/2).
  Not an integrated MPSS: mainline needs mhi_pci_generic-style flashless boot (sbl1/edl) + power/reset GPIO sequencing (no esoc upstream) + QRTR; MPSS/IPA nodes absent upstream for SM8250 anyway.
- Wi-Fi/BT: QCA6390 (cnss in stock DT, PCIe0 + qca6390-pmu): upstream via the qca6390-pmu node (RB5/OnePlus 8T tested; Xiaomi elish pattern). Low-medium effort.
- No upstream/Nura port exists for the GT Neo 2 (nearest: realme GT 2 porsche, GT Neo 3T draft MR). No SM8250 phone with a confirmed working modem was found; OnePlus 8 wiki lists calls/SMS/data broken (snippet, undated).
- VoLTE/IMS: pieces only (imsd, 81voltd, OpenIMSd; q6voice project (snippet: msm8916 only, unread)).
- Not researched in depth / not found: NFC (NQ-NCI -> nxp-nci?), GNSS, sensors (SLPI+hexagonrpcd), camera, USB-C PD/DP (upstream since 6.7), fingerprint (TEE: infeasible).

## 4. Recommended order
1) agent shell + hardware survey (done) -> 2) display panel (C) for a real console -> 3) Wi-Fi (QCA6390 + OEM BDF) -> 4) Bluetooth -> 5) USB-C/PD ->
6) UFS read-only (explicit go-ahead) -> 7) touch -> 8) audio (Q6 + TFA98xx) -> 9) back up modem partitions, then the SDX55M/MHI path ->
10) sensors/NFC -> 11) VoLTE -> camera. Skip fingerprint.
