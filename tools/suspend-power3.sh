#!/bin/sh
# Cumulative-unbind standby power bisect (about 14 min incl. the unplug wait). Runs detached on the phone on battery.
#   setsid sh suspend-power3.sh LABEL [SUSPEND_S=100] &    (UNPLUG USB when the panel says so; replug at "ALL DONE", then REBOOT the phone: it is left unbound)
# Stages are cumulative: B0 baseline, B1 Wi-Fi+BT+PMU rails, B2 audio codec/amps/usb-c mux, B3 haptics+NFC, B4 display pipeline, B5 USB gadget.
# Each stage: unbind, suspend SUSPEND_S, read the gauge average current right after wake (see suspend-power2.sh). Enabled regulators per stage: /root/reg-LABEL-Bn.txt
LABEL=${1:-run}; S=${2:-100}
PS=/sys/class/power_supply/bq28z610-0; RTC=/sys/class/rtc/rtc0
LOG=/root/spower3-$LABEL.log
BL=$(ls -d /sys/class/backlight/* | head -n1)
g() { cat $PS/$1 2>/dev/null; }
say() { echo "$*" >> $LOG; printf '\n*** spower3 %s: %s\n' "$LABEL" "$*" > /dev/tty1 2>/dev/null; }
sample() { echo "$1 rtc=$(cat $RTC/since_epoch) st=$(g status) v=$(g voltage_now) i=$(g current_now) q=$(g charge_now) cap=$(g capacity) T=$(g temp)" >> $LOG; }
unb() { # $1 = path of the driver's unbind file, $2 = device name
    if [ -e "$1" ]; then echo "$2" > "$1" 2>>$LOG && echo "  unbound $2" >> $LOG || echo "  FAILED to unbind $2" >> $LOG; else echo "  skip $2 (no $1)" >> $LOG; fi
    sleep 1
}
regs() { awk 'NR>2 && $2>0' /sys/kernel/debug/regulator/regulator_summary > /root/reg-$LABEL-$1.txt 2>/dev/null; echo "  regulators with use>0: $(wc -l < /root/reg-$LABEL-$1.txt)" >> $LOG; }
stage() { # $1 name
    regs $1
    echo 0 > $RTC/wakealarm; echo $(( $(cat $RTC/since_epoch) + S )) > $RTC/wakealarm
    sample "$1 before"; sync; echo freeze > /sys/power/state
    sample "$1 after+0s"; sleep 2; sample "$1 after+2s"
}
echo "== $(date) spower3 $LABEL kernel $(uname -r)" > $LOG
say "WAITING for UNPLUG of USB (up to 15 min). ~14 min run (cumulative unbind + 100 s suspends). DO NOT TOUCH."
n=0; while [ "$(g status)" != "Discharging" ] && [ $n -lt 450 ]; do sleep 2; n=$((n+1)); done
sample unplugged; say "unplug detected, settling 30 s"; sleep 30
B=$(cat $BL/brightness); echo 0 > $BL/brightness
rc-service bitra-wifi stop >/dev/null 2>&1; killall wpa_supplicant udhcpc 2>/dev/null; sleep 2
say "B0: baseline, nothing unbound, suspend ${S}s"; stage B0
say "B1: unbind Wi-Fi (ath11k), Bluetooth, WCN power sequencer"
unb /sys/bus/pci/drivers/ath11k_pci/unbind 0000:01:00.0
unb /sys/bus/serial/drivers/hci_uart_qca/unbind serial0-0
unb /sys/bus/platform/drivers/pci-pwrctrl-pwrseq/unbind 1c00000.pcie:pcie@0:wifi@0
unb /sys/bus/platform/drivers/pwrseq-qcom_wcn/unbind qca6390-pmu
say "B1: suspend ${S}s"; stage B1
say "B2: unbind audio codec, TFA987x amps, FSA4480"
unb /sys/bus/platform/drivers/wcd938x_codec/unbind audio-codec
unb /sys/bus/i2c/drivers/tfa987x/unbind 15-0034
unb /sys/bus/i2c/drivers/tfa987x/unbind 15-0035
unb /sys/bus/i2c/drivers/fsa4480/unbind 15-0042
say "B2: suspend ${S}s"; stage B2
say "B3: unbind haptics and NFC"
unb /sys/bus/i2c/drivers/aw8695-haptics/unbind 11-005a
unb /sys/bus/i2c/drivers/nxp-nci_i2c/unbind 1-0028
say "B3: suspend ${S}s"; stage B3
say "B4: unbind the display pipeline (msm DPU, panel supplies, mdss domain)"
unb /sys/bus/platform/drivers/msm_dpu/unbind ae01000.display-controller
sleep 2
say "B4: suspend ${S}s"; stage B4
say "B5: release the USB gadget"
for c in /config/usb_gadget/g1/UDC /sys/kernel/config/usb_gadget/g1/UDC; do [ -e $c ] && echo "" > $c 2>>$LOG; done; sleep 1
say "B5: suspend ${S}s"; stage B5
echo $B > $BL/brightness
{ printf "RESULT %s (uA, gauge average right after a %s s suspend, cumulative unbinds):" $LABEL $S
  for s in B0 B1 B2 B3 B4 B5; do printf " %s=%s" $s "$(grep "^$s after+0s" $LOG | sed 's/.* i=\([-0-9]*\) .*/\1/')"; done; echo; } >> $LOG
say "ALL DONE - replug USB, then REBOOT the phone (devices are left unbound)"; echo "== done" >> $LOG
