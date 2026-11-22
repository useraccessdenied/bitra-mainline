#!/bin/sh
# Autonomous USB/Type-C logger for the OTG host test: runs detached, appends to /root/otg-test.log
LOG=/root/otg-test.log
echo "=== otg-log start $(date) uptime $(cut -d. -f1 /proc/uptime)" >> $LOG
LASTN=0
END=$(( $(date +%s) + ${1:-1200} ))
while [ $(date +%s) -lt $END ]; do
  {
    echo "--- $(date +%H:%M:%S) up=$(cut -d. -f1 /proc/uptime)"
    echo "typec: data=$(cat /sys/class/typec/port0/data_role 2>&1 | tr '\n' ' ') power=$(cat /sys/class/typec/port0/power_role 2>&1 | tr '\n' ' ') partner=$(ls /sys/class/typec 2>&1 | tr '\n' ' ') mode=$(cat /sys/class/typec/port0/power_operation_mode 2>&1) orient=$(cat /sys/class/typec/port0/orientation 2>&1)"
    echo "usb_role=$(cat /sys/class/usb_role/*/role 2>&1 | tr '\n' ' ') udc=$(cat /sys/class/udc/*/state 2>&1 | tr '\n' ' ')"
    for r in /sys/class/regulator/regulator.*; do n=$(cat $r/name 2>/dev/null); case "$n" in usb_otg_vbus|usb_vbus) echo "reg $n state=$(cat $r/state) uV=$(cat $r/microvolts 2>/dev/null)";; esac; done
    echo "usb devices: $(ls /sys/bus/usb/devices 2>&1 | tr '\n' ' ')"
    lsusb 2>&1 | head -8
    echo "psy: $(for d in /sys/class/power_supply/*; do echo -n "$(basename $d):on=$(cat $d/online 2>/dev/null),st=$(cat $d/status 2>/dev/null),I=$(cat $d/current_now 2>/dev/null) "; done)"
  } >> $LOG 2>&1
  N=$(dmesg | wc -l)
  [ "$N" -gt "$LASTN" ] && dmesg | sed -n "$((LASTN+1)),\$p" | grep -i -E "usb|typec|tcpm|xhci|dwc3|vbus|otg|hid|sd[a-z]: " | grep -v "dependency cycle" | cut -c1-170 >> $LOG
  LASTN=$N
  sleep 3
done
echo "=== otg-log end $(date)" >> $LOG
