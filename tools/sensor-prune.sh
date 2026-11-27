#!/bin/sh
# sensor-prune.sh: serve only the sensor configs this phone needs (bind-mounted over the served config directory; a reboot undoes it).
# Dropped: other platforms (sxr2130_*), chips that are not in the stock bitra device tree (other IMUs, SAR, barometer, heart rate, hall, wigig, other ALS/prox chips).
C=/usr/share/qcom/sm8250/realme/bitra/sensors/config
P=/run/sensor-config-pruned
mountpoint -q $C && umount $C
rm -rf $P; mkdir -p $P
DROP='^(sxr2130_.*|wigig_sensing_0|pah_813x_0_reg|kona_bu52053nvx_0|bmi160|kona_qrd_bmi160|bmi26x_0|kona_qrd_bmi26x_0|kona_qrd_lsm6dsm|kona_qrd_lsm6dso|kona_sx932x_0|sx932x_0|kona_qrd_sx933x_0|kona_qrd_lps22hh_0|lps22hh_0|kona_qrd_tmd2725_0|stk3x5x_0|tcs3701|sns_heart_rate|sns_wrist_pedo|kona_qrd_cct|kona_qrd_cct_rear|kona_qrd_tcs3408_rear|tcs3408|kona_hdk_ak991x_0|kona_qrd_ak991x_0)\.json$'
for f in $C/*.json; do b=$(basename $f); echo "$b" | grep -Eq "$DROP" || cp $f $P/; done
echo "kept $(ls $P | wc -l) of $(ls $C | wc -l)"
mount --bind $P $C
