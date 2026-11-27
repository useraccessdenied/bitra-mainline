#!/bin/sh
# sensor-timeline.sh: restart the SLPI + hexagonrpcd and log (a) every file access in the served directory and /mnt/vendor/persist, (b) the first time each
# sensor answers. Output: /tmp/sensor-timeline.log. Run detached: setsid sh /tmp/sensor-timeline.sh >/dev/null 2>&1 &
L=/tmp/sensor-timeline.log; : > $L
D=/usr/share/qcom/sm8250/realme/bitra
T0=$(cut -d' ' -f1 /proc/uptime)
now() { awk -v a=$(cut -d' ' -f1 /proc/uptime) -v b=$T0 'BEGIN{printf "%6.1f", a-b}'; }
rc-service hexagonrpcd-sdsp stop >/dev/null 2>&1
echo stop > /sys/class/remoteproc/remoteproc0/state; sleep 2
cat > /tmp/ino-prog.sh <<'EP'
#!/bin/sh
echo "$(awk -v a=$(cut -d' ' -f1 /proc/uptime) -v b=$(cat /tmp/sensor-timeline.t0) 'BEGIN{printf "%6.1f", a-b}') FILE $1 $2/$3" >> /tmp/sensor-timeline.log
EP
chmod +x /tmp/ino-prog.sh; echo $T0 > /tmp/sensor-timeline.t0
inotifyd /tmp/ino-prog.sh $D:rwcdm $D/sensors:rwcdm $D/sensors/registry:rwcdm $D/sensors/registry/registry:rwcdm $D/sensors/config:r $D/socinfo:r 2>/dev/null &
echo start > /sys/class/remoteproc/remoteproc0/state; echo "$(now) slpi start" >> $L; sleep 3
rc-service hexagonrpcd-sdsp start >/dev/null 2>&1; echo "$(now) daemon started" >> $L
got=""
for i in $(seq 1 60); do
  for s in accelerometer proximity light magnetometer; do
    case " $got " in *" $s "*) continue;; esac
    if timeout 6 ssccli --sensor $s --timeout 2 2>&1 | grep -q measurement; then got="$got $s"; echo "$(now) READY $s" >> $L; fi
  done
  [ $(echo $got | wc -w) -ge 4 ] && break
  sleep 3
done
echo "$(now) done: $got" >> $L
killall inotifyd 2>/dev/null
