#!/bin/sh
# Standby power bisect with the SAFE unbind order (about 9 min incl. the unplug wait). Runs detached on the phone on battery.
#   setsid sh suspend-power4.sh LABEL [SUSPEND_S=75] &   (UNPLUG USB when the panel says so; replug at "ALL DONE", then REBOOT: devices are left unbound)
# Cumulative stages, riskiest last: M0 baseline | M1 haptics + NFC | M2 + display pipeline (msm DPU) | M3 + TFA987x amps | M4 + FSA4480.
# (Radios were measured by suspend-power4.sh: no effect. Unbinding qca6390-pmu, TFA987x or FSA4480 can hang the next suspend, see docs/known-issues.md.)
# Measurement: gauge average current right after wake from a SUSPEND_S suspend (time constant ~30 s), see suspend-power2.sh.
LABEL=${1:-run}; S=${2:-75}
PS=/sys/class/power_supply/bq28z610-0; RTC=/sys/class/rtc/rtc0
LOG=/root/spower5-$LABEL.log
BL=$(ls -d /sys/class/backlight/* | head -n1)
g() { cat $PS/$1 2>/dev/null; }
say() { echo "$*" >> $LOG; printf '\n*** spower5 %s: %s\n' "$LABEL" "$*" > /dev/tty1 2>/dev/null; sync; }
sample() { echo "$1 rtc=$(cat $RTC/since_epoch) st=$(g status) v=$(g voltage_now) i=$(g current_now) q=$(g charge_now) cap=$(g capacity) T=$(g temp)" >> $LOG; }
unb() { if [ -e "$1" ]; then echo "$2" > "$1" 2>>$LOG && echo "  unbound $2" >> $LOG || echo "  FAILED unbind $2" >> $LOG; else echo "  skip $2" >> $LOG; fi; sleep 1; }
rm_pci() { [ -e /sys/bus/pci/devices/$1/remove ] && { echo 1 > /sys/bus/pci/devices/$1/remove; echo "  removed PCI $1" >> $LOG; }; sleep 1; }
stage() {
    awk 'NR>2 && $2>0' /sys/kernel/debug/regulator/regulator_summary > /root/reg5-$LABEL-$1.txt 2>/dev/null; echo "  regulators with use>0: $(wc -l < /root/reg5-$LABEL-$1.txt)" >> $LOG
    echo 0 > $RTC/wakealarm; echo $(( $(cat $RTC/since_epoch) + S )) > $RTC/wakealarm
    sample "$1 before"; sync; echo freeze > /sys/power/state
    sample "$1 after+0s"; sleep 2; sample "$1 after+2s"
}
echo "== $(date) spower5 $LABEL kernel $(uname -r)" > $LOG
say "WAITING for UNPLUG of USB (up to 15 min). ~8 min run (4 cumulative stages, ${S} s suspends). DO NOT TOUCH."
n=0; while [ "$(g status)" != "Discharging" ] && [ $n -lt 450 ]; do sleep 2; n=$((n+1)); done
sample unplugged; say "unplug detected, settling 30 s"; sleep 30
B=$(cat $BL/brightness); echo 0 > $BL/brightness
rc-service bitra-wifi stop >/dev/null 2>&1; killall wpa_supplicant udhcpc 2>/dev/null; sleep 2
say "M0: baseline (nothing unbound), suspend ${S}s"; stage M0
say "M1: haptics + NFC unbound"
unb /sys/bus/i2c/drivers/aw8695-haptics/unbind 11-005a; unb /sys/bus/i2c/drivers/nxp-nci_i2c/unbind 1-0028
say "M1: suspend ${S}s"; stage M1
say "M2: + display pipeline unbound (panel supplies, mdss domain)"
unb /sys/bus/platform/drivers/msm_dpu/unbind ae01000.display-controller; sleep 2
say "M2: suspend ${S}s"; stage M2
say "M3: + speaker amps (TFA987x) unbound  [may hang]"
unb /sys/bus/i2c/drivers/tfa987x/unbind 15-0034; unb /sys/bus/i2c/drivers/tfa987x/unbind 15-0035
say "M3: suspend ${S}s"; stage M3
say "M4: + USB-C audio switch (FSA4480) unbound  [may hang]"
unb /sys/bus/i2c/drivers/fsa4480/unbind 15-0042
say "M4: suspend ${S}s"; stage M4
echo $B > $BL/brightness
{ printf "RESULT %s (uA, gauge average right after a %s s suspend, cumulative):" $LABEL $S
  for s in M0 M1 M2 M3 M4; do printf " %s=%s" $s "$(grep "^$s after+0s" $LOG | sed 's/.* i=\([-0-9]*\) .*/\1/')"; done; echo; } >> $LOG
say "ALL DONE - replug USB, then REBOOT the phone"; echo "== done" >> $LOG; sync
