#!/bin/sh
# Sustained GPU load with a state sampler. Runs on the phone inside the Phosh/Wayland session (user bitra, wayland-0).
#   setsid sh gpu-stress.sh LABEL [LOAD_S=300] &      -> /root/gpustress-LABEL.csv, /root/gpustress-LABEL.log (summary at the end)
# Load: vkmark (Turnip, mailbox present mode, 1080x2400 = divisible by Phosh's display scale 3) looping heavy scenes. Samples every 5 s:
# GPU devfreq freq/max, the GPU cooling device state, thermal zones, battery temp/current/status; baseline 20 s before, cooldown 60 s after.
LABEL=${1:-run}; LOAD=${2:-300}
CSV=/root/gpustress-$LABEL.csv; LOG=/root/gpustress-$LABEL.log
GPU=/sys/class/devfreq/3d00000.gpu; PS=/sys/class/power_supply/bq28z610-0
COOL=$(for c in /sys/class/thermal/cooling_device*; do [ "$(cat $c/type)" = "devfreq-3d00000.gpu" ] && echo $c; done)
zone() { for z in /sys/class/thermal/thermal_zone*; do [ "$(cat $z/type)" = "$1" ] && { cat $z/temp; return; }; done; echo -1; }
E0=$(dmesg | grep -c -i -E "adreno|gpu fault|gpu hang|\[drm:.*ERROR")
echo "t_s,phase,gpu_hz,gpu_max_hz,cool_state,gpu_top_mC,gpu_bot_mC,cpu7_mC,pm8150_mC,batt_dC,batt_uA,batt_status" > $CSV
T0=$(date +%s)
sample() { echo "$(( $(date +%s) - T0 )),$1,$(cat $GPU/cur_freq),$(cat $GPU/max_freq),$(cat $COOL/cur_state),$(zone gpu-top-thermal),$(zone gpu-bottom-thermal),$(zone cpu7-top-thermal),$(zone pm8150-thermal),$(cat $PS/temp),$(cat $PS/current_now),$(cat $PS/status)" >> $CSV; }
echo "== $(date) gpu-stress $LABEL load ${LOAD}s kernel $(uname -r), cooling=$COOL" > $LOG
i=0; while [ $i -lt 4 ]; do sample baseline; sleep 5; i=$((i+1)); done
cat > /tmp/gpu-load.sh <<'L'
#!/bin/sh
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0
while :; do
  vkmark --size 1080x2400 --present-mode mailbox -b vertex:duration=15 -b shading:duration=15 -b texture:duration=15 -b cube:duration=15 2>&1
done
L
chmod 755 /tmp/gpu-load.sh
su bitra -c "/tmp/gpu-load.sh > /tmp/gpu-load.log 2>&1" &
LP=$!
end=$(( $(date +%s) + LOAD ))
while [ $(date +%s) -lt $end ]; do sample load; sleep 5; done
pkill -f gpu-load.sh; pkill vkmark; sleep 2
i=0; while [ $i -lt 12 ]; do sample cooldown; sleep 5; i=$((i+1)); done
E1=$(dmesg | grep -c -i -E "adreno|gpu fault|gpu hang|\[drm:.*ERROR")
{
  echo "-- vkmark scores per pass:"; grep -E "vkmark Score|FPS" /tmp/gpu-load.log | cut -c1-90
  echo "-- kernel GPU/drm error lines before/after: $E0 / $E1"
  awk -F, 'NR>1 && $2=="load" {n++; f+=$3; if($3>mf)mf=$3; if($3<lf||lf=="")lf=$3; if($6>mt)mt=$6; if($7>mb)mb=$7; if($8>mc)mc=$8; if($5>ms)ms=$5; if($4<mm||mm=="")mm=$4}
       END {printf "-- load: %d samples, GPU freq min/avg/max = %d/%d/%d MHz, lowest max_freq %d MHz, max cooling state %d, max temps: gpu-top %.1f C, gpu-bottom %.1f C, cpu7 %.1f C\n", n, lf/1e6, f/n/1e6, mf/1e6, mm/1e6, ms, mt/1000, mb/1000, mc/1000}' $CSV
  awk -F, 'NR>1 && $2=="baseline" {t+=$6; n++} END {printf "-- baseline gpu-top %.1f C (avg of %d)\n", t/n/1000, n}' $CSV
  awk -F, '$2=="cooldown" {t=$6} END {printf "-- end of cooldown gpu-top %.1f C\n", t/1000}' $CSV
} >> $LOG
echo "== done" >> $LOG
