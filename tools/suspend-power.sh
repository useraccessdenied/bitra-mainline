#!/bin/sh
# Suspend power-draw measurement from the battery gauge. Runs detached on the phone, logs to /root/suspend-power.log.
#   setsid sh suspend-power.sh [SHORT_S=120] [LONG_S=900] &   then UNPLUG USB when the log says "waiting for unplug"; replug at the end.
# Stages: A idle screen on, B idle backlight off, C suspend SHORT (Wi-Fi up), D suspend SHORT (Wi-Fi down), E suspend LONG (Wi-Fi down), F suspend LONG (Wi-Fi up).
# Needs the BQ28Z610 gauge (charge_now has 1 mAh steps, so LONG stages give the average draw: dQ/dt). current_now/power_avg are the gauge's own averages.
PS=/sys/class/power_supply/bq28z610-0
RTC=/sys/class/rtc/rtc0
LOG=/root/suspend-power.log
SHORT=${1:-120}; LONG=${2:-900}
BL=$(ls -d /sys/class/backlight/* | head -n1)
g() { cat $PS/$1 2>/dev/null; }
say() { echo "$*" >> $LOG; printf '\n*** suspend-power: %s\n' "$*" > /dev/tty1 2>/dev/null; }   # also on the panel console
sample() { echo "$1 rtc=$(cat $RTC/since_epoch) st=$(g status) v=$(g voltage_now) i=$(g current_now) p=$(g power_avg) q=$(g charge_now) cap=$(g capacity) T=$(g temp)" >> $LOG; }
wifi_down() { rc-service bitra-wifi stop >/dev/null 2>&1; killall wpa_supplicant udhcpc 2>/dev/null; ip link set wlan0 down 2>/dev/null; }
wifi_up()   { rc-service bitra-wifi restart >/dev/null 2>&1; }
suspend_for() { # $1 label $2 seconds
    echo 0 > $RTC/wakealarm
    echo $(( $(cat $RTC/since_epoch) + $2 )) > $RTC/wakealarm
    sample "$1 before-suspend"; sync
    echo freeze > /sys/power/state
    for d in 0 1 2 4 8 15; do [ $d -gt 0 ] && sleep $(( d - last )); last=$d; sample "$1 after-resume+${d}s"; done; last=0
}
echo "== $(date) suspend-power SHORT=$SHORT LONG=$LONG kernel $(uname -r)" > $LOG
say "WAITING for you to UNPLUG USB (up to 15 min). After that: ~4 min idle stages (screen stays on), then suspend stages (screen goes dark), ~40 min total. DO NOT TOUCH the phone."
n=0; while [ "$(g status)" != "Discharging" ] && [ $n -lt 450 ]; do sleep 2; n=$((n+1)); done
sample "unplugged"; say "unplug detected, settling 20 s. Stages A,B (idle, ~3 min) first - screen stays on for A, backlight off for B"; sleep 20
say "A: idle, screen ON (90 s)"
for i in $(seq 1 18); do sample "A t=$((i*5))"; sleep 5; done
say "B: idle, backlight OFF (90 s)"; B=$(cat $BL/brightness); echo 0 > $BL/brightness
for i in $(seq 1 18); do sample "B t=$((i*5))"; sleep 5; done
say "C: SUSPEND ${SHORT}s with Wi-Fi up (screen dark, do not touch)"; suspend_for C $SHORT
say "D: SUSPEND ${SHORT}s with Wi-Fi down"; wifi_down; suspend_for D $SHORT
say "E: SUSPEND ${LONG}s with Wi-Fi down (long stage)"; suspend_for E $LONG
say "F: SUSPEND ${LONG}s with Wi-Fi up (long stage)"; wifi_up; sleep 20; suspend_for F $LONG
echo $B > $BL/brightness
echo "-- summary (dQ over the long stages, mAh*1000 -> mA)" >> $LOG
for s in E F; do
    a=$(grep "^$s before-suspend" $LOG | sed 's/.* q=\([0-9]*\) .*/\1/'); b=$(grep "^$s after-resume+15s" $LOG | sed 's/.* q=\([0-9]*\) .*/\1/')
    ta=$(grep "^$s before-suspend" $LOG | sed 's/.* rtc=\([0-9]*\) .*/\1/'); tb=$(grep "^$s after-resume+15s" $LOG | sed 's/.* rtc=\([0-9]*\) .*/\1/')
    echo "$s: q $a -> $b uAh over $((tb-ta)) s => $(( (a-b)*3600/(tb-ta)/1000 )) mA average (incl. the 15 s awake tail)" >> $LOG
done
say "ALL DONE - you can replug USB now"; echo "== done (replug USB)" >> $LOG
