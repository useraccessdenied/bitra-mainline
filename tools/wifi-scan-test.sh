#!/bin/sh
# wifi-scan-test.sh [CYCLES]: switch between two saved Wi-Fi connections and scan after every switch, log failures ("Resource busy"), nl80211 events and
# new kernel messages. Output /tmp/wifi-scan-test.log. Run detached: setsid sh /tmp/wifi-scan-test.sh 10 >/dev/null 2>&1 &
N=${1:-10}; L=/tmp/wifi-scan-test.log; : > $L
A=${CONN_A:-bitra-Kapil2.4G}; B=${CONN_B:-bitra-Kapil-5G}
ts() { awk '{printf "%6.1f", $1}' /proc/uptime; }
iw event -t > /tmp/wifi-scan-events.log 2>&1 &
EV=$!
dmesg | wc -l > /tmp/wifi-scan-dmesg.n
for i in $(seq 1 $N); do
  for c in $A $B; do
    echo "$(ts) cycle $i: nmcli con up $c" >> $L
    nmcli con up "$c" >> $L 2>&1
    sleep 4
    for k in 1 2 3; do
      out=$(iw dev wlan0 scan trigger 2>&1); rc=$?
      echo "$(ts)   scan trigger #$k rc=$rc $out" >> $L
      [ $rc -ne 0 ] && echo "$(ts)   FAIL: $(iw dev wlan0 link | head -1)" >> $L
      sleep 3
    done
  done
done
kill $EV 2>/dev/null
echo "$(ts) done" >> $L
dmesg | tail -n +$(( $(cat /tmp/wifi-scan-dmesg.n) + 1 )) | grep -i -E "ath11k|wlan|wmi|firmware|scan" >> $L
