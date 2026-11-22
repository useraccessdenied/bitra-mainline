#!/bin/sh
# Find which unbind makes s2idle hang. Runs detached on the phone, PLUGGED IN (USB shell alive while awake). Short 20 s suspends.
#   setsid sh suspend-unbind-test.sh LABEL [SKIP...] &      e.g. SKIP: pwrctrl pmu   (stages to leave out, after a hang found them)
# Cumulative stages: base bt wifi pciremove rootport pcie pwrctrl pmu codec amps haptic nfc display. The log is synced to disk BEFORE each suspend,
# so after a hang (watchdog reset, the phone reboots into Alpine) the last line names the culprit; /var/lib/pstore (bitra-pstore service) has the console trace.
LABEL=${1:-t}; shift; SKIP=" $* "
RTC=/sys/class/rtc/rtc0; LOG=/root/unbind-$LABEL.log
echo 1 > /sys/power/pm_debug_messages; echo 1 > /sys/power/pm_print_times
log() { echo "$(date +%T) $*" >> $LOG; sync; }
unb() { if [ -e "$1" ]; then echo "$2" > "$1" 2>>$LOG && log "  unbound $2" || log "  FAILED unbind $2"; else log "  skip $2 (no $1)"; fi; sleep 1; }
sus() { # $1 stage name
    echo 0 > $RTC/wakealarm; echo $(( $(cat $RTC/since_epoch) + 20 )) > $RTC/wakealarm
    log "stage $1: SUSPENDING (alarm in 20 s)"
    echo freeze > /sys/power/state; log "stage $1: resumed OK (suspend_stats fail=$(cat /sys/power/suspend_stats/fail))"
}
want() { case "$SKIP" in *" $1 "*) log "stage $1: SKIPPED"; return 1;; esac; return 0; }
echo "== $(date) unbind test $LABEL kernel $(uname -r) skip:$SKIP" > $LOG; sync
rc-service bitra-wifi stop >/dev/null 2>&1; killall wpa_supplicant udhcpc 2>/dev/null; sleep 1
sus base
want bt       && { unb /sys/bus/serial/drivers/hci_uart_qca/unbind serial0-0; sus bt; }
want wifi     && { unb /sys/bus/pci/drivers/ath11k_pci/unbind 0000:01:00.0; sus wifi; }
# the endpoint must leave the PCI core BEFORE its power goes away (a suspend over a powered-off but registered device hung the phone, 2026-11-22)
want pciremove && { [ -e /sys/bus/pci/devices/0000:01:00.0/remove ] && { echo 1 > /sys/bus/pci/devices/0000:01:00.0/remove; log "  removed PCI device 0000:01:00.0"; }; sleep 1; sus pciremove; }
# take the whole PCIe host away before its slot power: root port removed, controller unbound (no PCIe suspend callbacks against a dead link)
want rootport && { [ -e /sys/bus/pci/devices/0000:00:00.0/remove ] && { echo 1 > /sys/bus/pci/devices/0000:00:00.0/remove; log "  removed PCI root port 0000:00:00.0"; }; sleep 1; sus rootport; }
want pcie     && { unb /sys/bus/platform/drivers/qcom-pcie/unbind 1c00000.pcie; sus pcie; }
want pwrctrl  && { unb /sys/bus/platform/drivers/pci-pwrctrl-pwrseq/unbind 1c00000.pcie:pcie@0:wifi@0; sus pwrctrl; }
want pmu      && { unb /sys/bus/platform/drivers/pwrseq-qcom_wcn/unbind qca6390-pmu; sus pmu; }
want codec    && { unb /sys/bus/platform/drivers/wcd938x_codec/unbind audio-codec; sus codec; }
want amps     && { unb /sys/bus/i2c/drivers/tfa987x/unbind 15-0034; unb /sys/bus/i2c/drivers/tfa987x/unbind 15-0035; unb /sys/bus/i2c/drivers/fsa4480/unbind 15-0042; sus amps; }
want haptic   && { unb /sys/bus/i2c/drivers/aw8695-haptics/unbind 11-005a; sus haptic; }
want nfc      && { unb /sys/bus/i2c/drivers/nxp-nci_i2c/unbind 1-0028; sus nfc; }
want display  && { unb /sys/bus/platform/drivers/msm_dpu/unbind ae01000.display-controller; sleep 2; sus display; }
log "== done, all stages passed"
