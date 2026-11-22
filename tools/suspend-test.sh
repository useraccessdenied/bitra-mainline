#!/bin/sh
# Staged s2idle test (needs CONFIG_PM_DEBUG for /sys/power/pm_test). Runs on the phone, logs to /root/suspend.log.
#   suspend-test.sh stages        walk pm_test levels freezer, devices, platform, processors, core (each resumes by itself after ~5 s)
#   suspend-test.sh real [SECS]   real s2idle, RTC alarm wake after SECS (default 20)
# The USB-NCM shell drops while devices are suspended: start it detached (setsid sh suspend-test.sh ... &) and read the log afterwards.
LOG=/root/suspend.log
stats() { for f in success fail failed_freeze failed_prepare failed_suspend failed_suspend_late failed_suspend_noirq failed_resume failed_resume_early failed_resume_noirq last_failed_dev last_failed_errno last_failed_step; do
            printf '%s=%s ' $f "$(cat /sys/power/suspend_stats/$f 2>/dev/null)"; done; echo; }
echo "== $(date) $1 ($(uname -r))" >> $LOG
case "$1" in
stages)
    for lvl in freezer devices platform processors core; do
        echo $lvl > /sys/power/pm_test
        echo "-- level $lvl: suspending" >> $LOG; sync
        echo freeze > /sys/power/state 2>>$LOG; echo "-- level $lvl: returned $?" >> $LOG
        stats >> $LOG
        dmesg | tail -40 > /root/dmesg-$lvl.txt
        sleep 3
    done
    echo none > /sys/power/pm_test ;;
real)
    S=${2:-20}
    echo none > /sys/power/pm_test
    echo 0 > /sys/class/rtc/rtc0/wakealarm
    echo $(( $(cat /sys/class/rtc/rtc0/since_epoch) + S )) > /sys/class/rtc/rtc0/wakealarm
    echo "-- real suspend, alarm in $S s (rtc $(cat /sys/class/rtc/rtc0/since_epoch), alarm $(cat /sys/class/rtc/rtc0/wakealarm))" >> $LOG; sync
    echo freeze > /sys/power/state 2>>$LOG; echo "-- real: returned $?" >> $LOG
    echo "-- resumed: rtc $(cat /sys/class/rtc/rtc0/since_epoch), date $(date)" >> $LOG
    stats >> $LOG
    dmesg | tail -80 > /root/dmesg-real.txt ;;
*) echo "usage: $0 stages | real [SECS]"; exit 2 ;;
esac
echo "== done" >> $LOG
