#!/bin/sh
# Short suspend power measurement (about 9 min incl. the wait for the unplug). Runs detached on the phone on battery.
#   setsid sh suspend-power2.sh LABEL [SUSPEND_S=150] &     (then UNPLUG USB when the panel says so; replug at "ALL DONE")
# Uses the gauge's smoothed average current (time constant ~30 s) read right after wake, which after a 150 s suspend is dominated by the
# suspended draw (the 15 min runs agreed with it within ~10 mA). Log: /root/spower-LABEL.log, interconnect votes: /root/icc-LABEL.txt
LABEL=${1:-run}; S=${2:-150}
PS=/sys/class/power_supply/bq28z610-0; RTC=/sys/class/rtc/rtc0
LOG=/root/spower-$LABEL.log
BL=$(ls -d /sys/class/backlight/* | head -n1)
g() { cat $PS/$1 2>/dev/null; }
say() { echo "$*" >> $LOG; printf '\n*** spower %s: %s\n' "$LABEL" "$*" > /dev/tty1 2>/dev/null; }
sample() { echo "$1 rtc=$(cat $RTC/since_epoch) st=$(g status) v=$(g voltage_now) i=$(g current_now) q=$(g charge_now) cap=$(g capacity) T=$(g temp)" >> $LOG; }
cur() { g current_now; }
suspend_for() {
    echo 0 > $RTC/wakealarm; echo $(( $(cat $RTC/since_epoch) + $2 )) > $RTC/wakealarm
    sample "$1 before"; sync; echo freeze > /sys/power/state
    sample "$1 after+0s"; sleep 1; sample "$1 after+1s"; sleep 2; sample "$1 after+3s"
}
echo "== $(date) spower $LABEL kernel $(uname -r) cmdline: $(cat /proc/cmdline | tr ' ' '\n' | grep -E 'ignore_unused' | tr '\n' ' ')" > $LOG
dmesg | grep "sync_state() pending" >> $LOG; echo "sync_state pending count: $(dmesg | grep -c 'sync_state() pending')" >> $LOG
cat /sys/kernel/debug/interconnect/interconnect_summary > /root/icc-$LABEL.txt 2>&1
say "WAITING for UNPLUG of USB (up to 15 min). ~9 min run: idle 90 s (backlight off), suspend ${S} s, suspend ${S} s radios off. DO NOT TOUCH."
n=0; while [ "$(g status)" != "Discharging" ] && [ $n -lt 450 ]; do sleep 2; n=$((n+1)); done
sample unplugged; say "unplug detected, settling 30 s"; sleep 30
B=$(cat $BL/brightness); echo 0 > $BL/brightness
say "I: idle, backlight OFF (90 s)"; for i in 1 2 3 4 5 6 7 8 9; do sleep 10; sample "I t=$((i*10))"; done
say "S1: SUSPEND ${S}s, Wi-Fi + Bluetooth up (screen dark, do not touch)"; suspend_for S1 $S
say "radios off"; rc-service bitra-wifi stop >/dev/null 2>&1; killall wpa_supplicant udhcpc 2>/dev/null; rfkill block wifi; rfkill block bluetooth; sleep 20
say "S2: SUSPEND ${S}s, radios OFF (screen dark, do not touch)"; suspend_for S2 $S
rfkill unblock all; rc-service bitra-wifi restart >/dev/null 2>&1; echo $B > $BL/brightness
echo "RESULT $LABEL: idle(bl off) $(grep '^I t=90' $LOG | sed 's/.* i=\([-0-9]*\) .*/\1/') uA | suspend radios-up $(grep '^S1 after+0s' $LOG | sed 's/.* i=\([-0-9]*\) .*/\1/') uA | suspend radios-off $(grep '^S2 after+0s' $LOG | sed 's/.* i=\([-0-9]*\) .*/\1/') uA" >> $LOG
say "ALL DONE - replug USB now"; echo "== done" >> $LOG
