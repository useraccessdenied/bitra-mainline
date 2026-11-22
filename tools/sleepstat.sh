#!/bin/sh
# snapshot of the system-sleep evidence: qcom_stats counters, cluster idle stats, interconnect nodes with non-zero votes
out=/root/sleepstat-$1.txt
{
 echo "== $(date) $1"
 for n in aosd cxsd ddr; do printf "%s " $n; grep Count /sys/kernel/debug/qcom_stats/$n; done
 echo "-- ddr freq (count)"; grep "DDR Freq" /sys/kernel/debug/qcom_stats/ddr_stats | awk '{print $3, $4, $5, $6}' | head -14
 echo "-- cluster idle"; cat /sys/kernel/debug/pm_genpd/power-domain-cpu-cluster0/idle_states
 echo "-- genpd cx/mx/mmcx (perf level)"; grep -E "^(cx|mx|mmcx) " /sys/kernel/debug/pm_genpd/pm_genpd_summary | cut -c1-90
 echo "-- interconnect nodes with avg or peak > 0 (parents only)"; awk '/^[a-zA-Z]/ && ($(NF-1)>0 || $NF>0) {print}' /sys/kernel/debug/interconnect/interconnect_summary | cut -c1-110
 echo "-- cpuidle cpu0"; for s in /sys/devices/system/cpu/cpu0/cpuidle/state*; do echo $(cat $s/name) usage=$(cat $s/usage) time=$(cat $s/time); done
} > $out 2>&1
