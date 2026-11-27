#!/bin/sh
# usbwatch.sh: log the USB gadget / Type-C / usb0 state every 2 s to /var/log/usbwatch.log (persistent), plus new kernel messages.
# Run on the phone: setsid sh /tmp/usbwatch.sh >/dev/null 2>&1 &   Read it after the next boot when the Mac link has dropped.
L=/var/log/usbwatch.log
prev=""
while :; do
  s="udc=$(cat /sys/class/udc/*/state 2>/dev/null) role=$(cat /sys/class/typec/port0/data_role 2>/dev/null) pwr=$(cat /sys/class/typec/port0/power_role 2>/dev/null) partner=$([ -e /sys/class/typec/port0-partner ] && echo yes || echo no) usb0=$(cat /sys/class/net/usb0/operstate 2>/dev/null) carrier=$(cat /sys/class/net/usb0/carrier 2>/dev/null) rx=$(cat /sys/class/net/usb0/statistics/rx_packets 2>/dev/null) tx=$(cat /sys/class/net/usb0/statistics/tx_packets 2>/dev/null) up=$(cut -d' ' -f1 /proc/uptime)"
  k=$(dmesg | grep -i -E "usb|dwc3|typec|tcpm|udc|gadget|ncm|vbus|role" | tail -3 | md5sum)
  [ "$s" != "$prev" ] && echo "$(date +%T) $s" >> $L
  if [ "$k" != "$kprev" ]; then echo "$(date +%T) KMSG $(dmesg | grep -i -E 'usb|dwc3|typec|tcpm|udc|gadget|ncm|vbus|role' | tail -2 | tr '\n' '|')" >> $L; kprev=$k; fi
  prev="$s"; sync; sleep 2
done
