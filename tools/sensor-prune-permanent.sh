#!/bin/sh
# Make the pruned sensor config permanent on a running phone: move the dropped config files out of the served directory (kept in config-unused/).
C=/usr/share/qcom/sm8250/realme/bitra/sensors/config
U=/usr/share/qcom/sm8250/realme/bitra/sensors/config-unused
mountpoint -q $C && umount $C
mkdir -p $U
DROP='^(sxr2130_.*|wigig_sensing_0|pah_813x_0_reg|kona_bu52053nvx_0|bmi160|kona_qrd_bmi160|bmi26x_0|kona_qrd_bmi26x_0|kona_qrd_lsm6dsm|kona_qrd_lsm6dso|kona_sx932x_0|sx932x_0|kona_qrd_sx933x_0|kona_qrd_lps22hh_0|lps22hh_0|kona_qrd_tmd2725_0|stk3x5x_0|tcs3701|sns_heart_rate|sns_wrist_pedo|kona_qrd_cct|kona_qrd_cct_rear|kona_qrd_tcs3408_rear|tcs3408|kona_hdk_ak991x_0|kona_qrd_ak991x_0)\.json$'
for f in $C/*.json; do b=$(basename $f); echo "$b" | grep -Eq "$DROP" && mv $f $U/; done
echo "served: $(ls $C | wc -l) files, moved aside: $(ls $U | wc -l)"
