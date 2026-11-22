# 32 — Sensors: SLPI remoteproc, FastRPC server, Sensor Core (2026-11-22)

Status: **partial.** The sensor DSP (SLPI) boots from this phone's own firmware, the FastRPC server `hexagonrpcd` attaches and serves the sensor configuration, and the Sensor Core (SSC) framework answers on QRTR (`'registry' sensor available`). **No physical sensor is enumerated yet** (`ssccli`: "No 'accel' sensor available", same for proximity, light, gyroscope, magnetometer), so iio-sensor-proxy has nothing to report.

## What works
- **SLPI remoteproc**: DT `&slpi { firmware-name = "qcom/sm8250/realme/bitra/slpi.mdt"; status = "okay"; }` (reserved region `slpi_mem` 0x90600000, 21 MiB, from the OnePlus common DT, matches stock). Firmware = `slpi.mdt` + `slpi.b00..b21` from the stock `modem` partition (`tools/extract-dsp-firmware.py`). `remoteproc0 slpi running`, FastRPC `fastrpc-sdsp` registered with compute-cb nodes, ADSP unaffected.
- **Userspace**: Alpine packages `hexagonrpcd` (+`-openrc`, `-udev`: without the udev rule `/dev/fastrpc-sdsp` is root-only while the service runs as `fastrpc`), `libssc` (`ssccli`), `iio-sensor-proxy`. Service `hexagonrpcd-sdsp` (`hexagonrpcd -f /dev/fastrpc-sdsp -d sdsp -s -R DIR`).
- **Served directory** (`/usr/share/qcom/sm8250/realme/bitra/`, set with `hexagonrpcd_fw_dir` in `/etc/conf.d/hexagonrpcd-sdsp`): `sensors/config/*.json` (stock vendor `/vendor/etc/sensors/config` + odm `/odm/etc/sensor/config`), `sensors/sns_reg.conf` (stock `sns_reg_config`), `sensors/registry/registry/` (writable by `fastrpc`; the DSP writes `registry/../temp.json`). Two path details found with the daemon in the foreground: the registry needs the extra `registry/registry/` subdirectory, and the DSP opens **`/odm/etc/sensor/config` literally** (symlink it to the served `sensors/config`).
- The image builder (`scripts/build_alpine_rootfs.py`) installs all of this (packages, SLPI firmware, config tree from the stock extracts in the `bitra` workspace, symlink, conf.d, service in the default runlevel).

## Stock sensor set (odm configs)
BMI26x and ICM4x6xx / LSM6DSO IMUs (`kona_qrd_bmi26x_0`, `kona_qrd_icm4x6xx`, `kona_qrd_lsm6dso`), SX933x (SAR/grip), CCT (color/ambient light, front and rear), BU52053NVX (hall switch). The vendor set adds alsps/mmc5603nj (magnetometer)/lps22hh (pressure) configs.

## Open: why no sensor is enumerated
- The registry directory stays empty (the DSP has written nothing).
- Likely causes to check: the SSC sensors sit on buses/regulators owned by the SLPI (a dedicated SSC QUP I2C/I3C/SPI, plus rails the AP might switch off in `regulator_late_cleanup` or protect through xPU), missing registry/calibration (the stock one lives in `persist`: `sensors/registry`), or SSC needing more served files (`/socinfo/`, `/acdb/`). The kernel log shows nothing from the SLPI.
- Next steps: compare with a working SM8250 phone (pmOS) for SLPI-related DT (`qupv3` for SSC, regulators), inspect the stock DT for the SSC QUP and sensor rails, SSC diag logging, try serving the stock registry from the `persist` backup.
