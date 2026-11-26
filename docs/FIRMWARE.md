# Firmware files for bitra

The kernel needs a few firmware files at runtime. **They are not in this repo and should not be published**: they are Qualcomm/Realme/third-party
property and most licences forbid redistribution. `firmware/manifest.json` lists every file by path, size and sha256 only, and
`tools/bitra-firmware.py` gets them from sources the user already has.

| Group | Files | What for | Where they come from |
|---|---|---|---|
| vendor | `qcom/sm8250/realme/bitra/{adsp,cdsp,slpi}.mdt + .b00..bNN` (54 files) | audio / sensor hub / compute DSP (remoteproc) | the phone's own `modem` partition (stock firmware) |
| linux-firmware | `qcom/a650_sqe.fw`, `qcom/a650_gmu.bin` | Adreno 650 GPU | linux-firmware (installed copy or git.kernel.org) |
| linux-firmware | `ath11k/QCA6390/hw2.0/{amss,m3,board-2}.bin` | Wi-Fi | linux-firmware |
| linux-firmware | `qca/htbtfw20.tlv`, `qca/htnv20.bin` | Bluetooth | linux-firmware |

CDSP is extracted but not enabled yet. No GPU zap shader is loaded on this phone. Modem (SDX55M, external) is not set up.

## Getting them
Needs Python 3 and `7z` (for the vendor files from an image). Output defaults to `third_party/firmware/` (gitignored), laid out like `/lib/firmware`.

```
# vendor DSP sets: pick the source you have
python3 tools/bitra-firmware.py extract --from-adb                    # phone running Android, USB debugging on (most users)
python3 tools/bitra-firmware.py extract --from-zip Firmware_F.20_EX01_IN.zip   # realme firmware zip (firmware-update/modem.img inside)
python3 tools/bitra-firmware.py extract --from-modem-img modem.img    # raw dump of the modem partition
python3 tools/bitra-firmware.py extract --from-phone                  # phone running our Alpine, through bitra-agent

# GPU, Wi-Fi, Bluetooth
python3 tools/bitra-firmware.py open --linux-firmware /usr/lib/firmware   # an installed linux-firmware (.zst/.xz ok)
python3 tools/bitra-firmware.py open --download                           # or fetch from git.kernel.org

python3 tools/bitra-firmware.py verify     # compare with the manifest
```
`all` runs both steps. With ADB, the tool first tries to pull `/vendor/firmware_mnt/image` (stock Android mounts the modem partition read only and
`adb pull` needs no root there); if that is not readable it tries to read the partition as root. Nothing is written to the phone.

## Releases
The manifest is from the stock firmware read from this phone (the Indian F.20 zip gives identical files; the EU F.18 zip differs in 37 of the 54 vendor files,
all three sets still pass the segment checks) and linux-firmware 20260519. Other releases install with a warning: test before relying on them.
The DSP images are relocatable; the device tree's reserved regions must be at least ADSP 37 MiB, CDSP 20 MiB, SLPI 21 MiB.

## Sharing
Do not put the extracted files in a public repository. Share the tool, the manifest and the extraction recipe instead.
