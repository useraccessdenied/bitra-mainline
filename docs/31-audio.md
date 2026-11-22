# 31 — Audio: ADSP firmware, sound card, speakers (2026-11-22)

Status: **partial, speakers work.** The ADSP boots from this phone's own firmware, the whole Q6/LPASS/SoundWire/WCD938x chain probes, the sound card `sm8250 - realme GT Neo 2` registers (8 MultiMedia PCMs, Headset Jack, USB Offload Jack)
and a test tone plays **clean on both speakers** (owner-verified: top and bottom, a quiet and a louder tone). Flashed in `mainline-boot-5.img`. A UCM profile (speaker only) lets PulseAudio create a sink, and a tone through it was heard clearly (owner-verified). Not done: microphones, earpiece, headset/USB-C audio, Phosh volume keys/OSD unconfirmed.

## What was needed
1. **ADSP firmware** (`tools/extract-dsp-firmware.py`): the stock `modem` partition (FAT image from the 2026-11-16 backup) holds `image/adsp.mdt` + `adsp.b00-b18` (also `cdsp.*`, `slpi.*`). Each set is checked against its MDT header (every segment file present with the declared size).
   All three are **relocatable** (`MDT_RELOCATABLE`), link ranges ADSP 0x89500000..0x8ba00000 (37 MiB), CDSP 20 MiB, SLPI 21 MiB: the kernel's MDT loader places them in the DT's reserved region, which must be at least that big.
   Installed under `/lib/firmware/qcom/sm8250/realme/bitra/` (the remoteproc driver `qcom_q6v5_pas` is a module; the rootfs is mounted by then, no initramfs copy needed).
2. **Reserved-memory map**: checked against the stock DT before enabling anything. The stock layout (205 MiB protected block at 0x80b00000, every carve-out shifted up by 0x7a00000, ADSP at 0x91b00000 / 37 MiB, CDSP 0x8f200000, SLPI 0x90600000, GPU zap 0x8e21a000)
   differs from mainline's generic SM8250 map (ADSP 0x8a100000 / 29 MiB: too small for this firmware), but the **running device tree already carries the stock layout** (the bootloader patches the reserved-memory nodes, our DTB shim keeps them): `/proc/device-tree/.../memory-region` of the remoteproc nodes resolves to the stock regions. No change needed (`ours.dts` decompiled from the built DTB shows mainline's map; the live tree does not).
3. **DT** (`sm8250-realme-bitra.dts`): `&adsp { firmware-name = ".../adsp.mdt"; status = "okay"; }`; `&sound` gets `model = "realme GT Neo 2"` and the **8T's `audio-routing`** (same WCD938x; this phone's real mic wiring is unverified) and drops `displayport-dai-link`.
   Without a `model`, ASoC refuses the card with a **silent `-EINVAL`** (`snd-sm8250 sound: probe ... failed with error -22`, no other message); the DisplayPort link waited forever for `mdss_dp` (disabled): "DisplayPort Playback: codec dai not found".
4. **Kernel** (`q6afe.c`): the ADSP answers `AFE_CMD_REMOTE_LPASS_CORE_HW_VOTE_REQUEST` with an error result (status 0x16) instead of the 0x100f5 response; the driver had no case for it, so every vote timed out after 3 s ("Unknown cmd 0x100f4", "AFE failed to vote (3)", LPASS pinctrl/macro clock enable -110).
   The callback now completes the waiter, so the vote fails fast. (A different, upstream fix for the vote reply layout exists: Val Packett's [q6afe vote series](https://lkml.iu.edu/2605.0/08569.html); ours is a different failure mode.) The audio works with the vote rejected.

## The readiness race (understood, not fixed)
Right after the ADSP boots, the AFE service accepts no commands (vote and the first clock `SET_PARAM` rejected with 0x16, ~35 ms after boot); the same commands work minutes later (a manual re-probe of the VA macro succeeded, and then macros, SoundWire and WCD938x bound).
`q6core_is_adsp_ready()` exists in the tree but nothing calls it, and calling it before the first AFE command did not change the early rejections (it probably reports ready at once), so that patch was dropped. In practice the sequence settles because the macros defer/retry.

## UCM profile (speaker, 2026-11-22)
Files in `rootfs-overlay/` (installed by `scripts/build_alpine_rootfs.py`, which now copies the whole overlay tree and adds `alsa-ucm-conf` + `pulseaudio-utils`):
- `usr/share/alsa/ucm2/conf.d/sm8250/realme GT Neo 2.conf`: the file name is the card long name; it just selects the `HiFi` use case.
- `usr/share/alsa/ucm2/Qualcomm/sm8250/realme-bitra/HiFi.conf`: verb with one `Speaker` device on `hw:${CardId},0`.
- **Lesson:** the back-end route `TERT_MI2S_RX Audio Mixer MultiMedia1` must be in the *verb* Enable/DisableSequence. With the route in the device sequence PulseAudio probes the PCM first and fails with `Error opening PCM device _ucm0001.hw:r2,0: Invalid argument` / `Failed to find a working profile`.
- Result: card `alsa_card.platform-sound`, default sink `alsa_output.platform-sound.HiFi__Speaker__sink`; `pactl set-sink-volume @DEFAULT_SINK@ 40%` then `paplay tone.wav` plays with no kernel errors or reset (this also did not reproduce the earlier unexplained reset). `alsaucm` state does not persist across invocations, so check enable/disable within one invocation.
- Not in the profile: microphones, earpiece, headset/USB-C (wiring unverified).

## Microphones (2026-11-22): investigated, not working yet
- **Stock wiring** (from the stock odm `mixer_paths.xml` and the stock dtbo audio-routing): the handset mics are **analog on the WCD938x**, not DMICs: `ADC1` (IN1, `TX SMIC MUX ADC0`) and `ADC4` (INP5, `TX SMIC MUX ADC3`), read as a stereo pair over `TX_CODEC_DMA_TX_3` (`handset-dmic-endfire`: DEC0<-ADC0, DEC1<-ADC3, `ADC1/ADC4 Volume` 6-8, `TX_DEC0/1 Volume` 84). Headset mic: ADC2 INP2 (`TX_CDC_DMA_TX_4`). The `dmic*` stock paths are for another codec (SLIM) and do not apply.
- Stock bias routing: AMIC1->MIC BIAS1, AMIC2->BIAS2, AMIC3 and AMIC4->BIAS3, AMIC5->BIAS4. Our DT had only AMIC2; the missing routes are added in the bitra DT (booted as a-24, card still registers).
- VA-macro DMIC0-3 (`VA_CODEC_DMA_TX_0`): DAPM path fully powered (DMIC2, MIC BIAS1, DEC0, codec DMA all On, pins muxed) but the data is exact zero: no digital mic on those lines.
- Analog probe (`tools/mic-probe.py adc`, then the stock-style stereo setup): the path delivers data, but nothing yet responds to speech. Every capture starts with the same deterministic ~0.3 s start-up burst (peak 1774, identical across runs; do not mistake it for sound; skip the first 0.5 s). Stock-style stereo: ch0 rms ~5600 both quiet and during speech, ch1 ~2. ADC1 alone: rms 42 quiet vs 47 talking.
- Next: confirm the test was done with someone talking at the mic holes, then check the capture-side supplies/clocks (MIC BIAS regulator voltage, the `vdd-mic-bias`/BOB supply, `ADC` HW mode, `TX0 MODE` vs stock) and whether the stock firmware needs a different SoundWire TX port setup.

## Test procedure (manual, without PulseAudio)
`apk add alsa-utils`; stop PulseAudio (`pkill pulseaudio`: it grabs the card and fails with "Failed to find a working profile"); route and play:
`amixer -c 0 cset name="TERT_MI2S_RX Audio Mixer MultiMedia1" 1; aplay -D hw:0,0 tone.wav` (`tools/tone.py AMP` writes a 2 s 440 Hz stereo tone; start at amplitude 3000). The speaker amps (2x TFA9874 at 0x34/0x35 on i2c15, "top_spkr/bottom_spkr", Tertiary MI2S RX) have no mixer controls.

## Open / next
- **One unexplained reset**: during the very first playback attempt the phone reset (a `reboot ... 'bootloader'` line at 147 s, then it came back on the same test image) while PulseAudio was also grabbing the card; two later runs with PulseAudio stopped played fine. Suspects: PulseAudio probing the PCMs concurrently; not reproduced. Test with PulseAudio/PipeWire playing in Phosh before relying on it.
- UCM covers the speaker only; add capture paths (WCD/VA DMIC), earpiece and headset once the wiring is verified. Confirm Phosh volume keys/OSD with the new sink.
- Untested: microphones (WCD/VA DMIC/AMIC wiring unverified), earpiece, headset jack events, USB-C audio (FSA4480 + the USB offload jack), volume and speaker protection (TFA amps have no kernel volume; start quiet), Bluetooth audio, calls (modem).
- Kernel log noise: `qcom-soundwire ...: din-ports/dout-ports mismatch with controller`, `rx_macro: Unsorted reg_defaults`, `AFE failed to vote`, `cpu cpu7: Voltage update failed freq=3187200` (not audio).
- CDSP and SLPI firmware sets are extracted and verified (CDSP/SLPI regions match) but not enabled; enable one at a time (docs/27).
