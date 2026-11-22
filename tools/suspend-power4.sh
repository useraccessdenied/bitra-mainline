#!/bin/sh
# Standby power bisect with the SAFE unbind order (about 9 min incl. the unplug wait). Runs detached on the phone on battery.
#   setsid sh suspend-power4.sh LABEL [SUSPEND_S=75] &   (UNPLUG USB when the panel says so; replug at "ALL DONE", then REBOOT: devices are left unbound)
# Cumulative stages: M0 baseline | M1 Bluetooth + ath11k off, PCI endpoint and root port removed | M2 + pci-pwrctrl unbound | M3 + audio codec, TFA987x amps, FSA4480
#                    | M4 + haptics, NFC | M5 + display pipeline (msm DPU).  NOT included: unbinding qca6390-pmu (hangs the next suspend, see docs/known-issues.md).
# Measurement: gauge average current right after wake from a SUSPEND_S suspend (time constant ~30 s), see suspend-power2.sh.
LABEL=${1:-run}; S=${2:-75}
PS=/sys/class/power_supply/bq28z610-0; RTC=/sys/class/rtc/rtc0
LOG=/root/spower4-$LABEL.log
BL=$(ls -d /sys/class/backlight/* | head -n1)
g() { cat $PS/$1 2>/dev/null; }
say() { echo "$*" >> $LOG; printf '\n*** spower4 %s: %s\n' "$LABEL" "$*" > /dev/tty1 2>/dev/null; sync; }
sample() { echo "$1 rtc=$(cat $RTC/since_epoch) st=$(g status) v=$(g voltage_now) i=$(g current_now) q=$(g charge_now) cap=$(g capacity) T=$(g temp)" >> $LOG; }
unb() { if [ -e "$1" ]; then echo "$2" > "$1" 2>>$LOG && echo "  unbound $2" >> $LOG || echo "  FAILED unbind $2" >> $LOG; else echo "  skip $2" >> $LOG; fi; sleep 1; }
rm_pci() { [ -e /sys/bus/pci/devices/$1/remove ] && { echo 1 > /sys/bus/pci/devices/$1/remove; echo "  removed PCI $1" >> $LOG; }; sleep 1; }
stage() {
    awk 'NR>2 && $2>0' /sys/kernel/debug/regulator/regulator_summary > /root/reg4-$LABEL-$1.txt 2>/dev/null; echo "  regulators with use>0: $(wc -l < /root/reg4-$LABEL-$1.txt)" >> $LOG
    echo 0 > $RTC/wakealarm; echo $(( $(cat $RTC/since_epoch) + S )) > $RTC/wakealarm
    sample "$1 before"; sync; echo freeze > /sys/power/state
    sample "$1 after+0s"; sleep 2; sample "$1 after+2s"
}
echo "== $(date) spower4 $LABEL kernel $(uname -r)" > $LOG
say "WAITING for UNPLUG of USB (up to 15 min). ~9 min run (5 cumulative stages, ${S} s suspends). DO NOT TOUCH."
n=0; while [ "$(g status)" != "Discharging" ] && [ $n -lt 450 ]; do sleep 2; n=$((n+1)); done
sample unplugged; say "unplug detected, settling 30 s"; sleep 30
B=$(cat $BL/brightness); echo 0 > $BL/brightness
rc-service bitra-wifi stop >/dev/null 2>&1; killall wpa_supplicant udhcpc 2>/dev/null; sleep 2
say "M0: baseline (nothing unbound), suspend ${S}s"; stage M0
say "M1: Bluetooth + Wi-Fi drivers off, PCI endpoint + root port removed"
unb /sys/bus/serial/drivers/hci_uart_qca/unbind serial0-0
unb /sys/bus/pci/drivers/ath11k_pci/unbind 0000:01:00.0
rm_pci 0000:01:00.0; rm_pci 0000:00:00.0
say "M1: suspend ${S}s"; stage M1
say "M2: + pci-pwrctrl (Wi-Fi slot power control) unbound"
unb /sys/bus/platform/drivers/pci-pwrctrl-pwrseq/unbind 1c00000.pcie:pcie@0:wifi@0
say "M2: suspend ${S}s"; stage M2
say "M3: + audio codec, speaker amps, USB-C audio switch unbound"
unb /sys/bus/platform/drivers/wcd938x_codec/unbind audio-codec
unb /sys/bus/i2c/drivers/tfa987x/unbind 15-0034; unb /sys/bus/i2c/drivers/tfa987x/unbind 15-0035; unb /sys/bus/i2c/drivers/fsa4480/unbind 15-0042
say "M3: suspend ${S}s"; stage M3
say "M4: + haptics and NFC unbound"
unb /sys/bus/i2c/drivers/aw8695-haptics/unbind 11-005a; unb /sys/bus/i2c/drivers/nxp-nci_i2c/unbind 1-0028
say "M4: suspend ${S}s"; stage M4
say "M5: + display pipeline unbound (panel supplies, mdss domain)"
unb /sys/bus/platform/drivers/msm_dpu/unbind ae01000.display-controller; sleep 2
say "M5: suspend ${S}s"; stage M5
echo $B > $BL/brightness
{ printf "RESULT %s (uA, gauge average right after a %s s suspend, cumulative):" $LABEL $S
  for s in M0 M1 M2 M3 M4 M5; do printf " %s=%s" $s "$(grep "^$s after+0s" $LOG | sed 's/.* i=\([-0-9]*\) .*/\1/')"; done; echo; } >> $LOG
say "ALL DONE - replug USB, then REBOOT the phone"; echo "== done" >> $LOG; sync
