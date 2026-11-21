#!/bin/sh
# Display soak harness for the debug kernel (run on the phone; busybox ash).
#   soak.sh start                 write a marker into the kernel log (reports are split at it)
#   soak.sh modes [N]             N times: 120 Hz mode, 60 Hz mode (full modesets)
#   soak.sh blank [N]             N times: panel off/on through fbdev blank (unprepare/prepare)
#   soak.sh backlight [N]         N backlight sweeps 0..2047
#   soak.sh anim [SECS]           full-height animation at 120 Hz (heavy writes into the scanout buffer)
#   soak.sh mix SECS              all of the above in parallel plus CPU load for SECS seconds
#   soak.sh rebind [N]            N times: unbind + bind the panel driver (teardown/probe paths)
#   soak.sh fault [N] [PCT]       N probes of the panel driver with PCT% of this task's slab allocations failing
#   soak.sh failnth FROM TO [OUTFILE]   deterministic sweep: fail exactly the Nth slab allocation of a write to the panel bind file (helper bitra-failnth); reports splats per N
#   soak.sh leak                  kmemleak scan + print
#   soak.sh report [boot|soak]    count/print sanitizer, lockdep, WARN, BUG findings
P=/sys/bus/mipi-dsi/drivers/panel-ams662zs01
D=ae94000.dsi.0
BL=/sys/class/backlight/$D/brightness
FB=/sys/class/graphics/fb0/blank
mark() { echo "soak: $*" > /dev/kmsg; }
loop() { n=${2:-10}; i=0; while [ $i -lt $n ]; do "$1" $i; i=$((i+1)); done; }
step_modes() { bitra-drm anim 0 1 1 > /dev/null 2>&1; bitra-drm anim 1 1 1 > /dev/null 2>&1; }
step_blank() { echo 4 > $FB; sleep 1; echo 0 > $FB; sleep 1; }
step_bl() { for v in 1 200 700 1200 2047 1174; do echo $v > $BL; sleep 1; done; }
step_rebind() { echo $D > $P/unbind; sleep 1; echo $D > $P/bind; sleep 3; }
FS=/sys/kernel/debug/failslab
step_fault() {
  echo $D > $P/unbind 2>/dev/null; sleep 1
  ( echo 1 > /proc/self/make-it-fail; echo $D > $P/bind ) 2>/dev/null
  echo 0 > $FS/probability
  [ -e $P/$D ] || { echo $D > $P/bind 2>/dev/null; echo "attempt $1: probe failed (injected), rebound clean"; }
  echo ${FAULT_PCT:-25} > $FS/probability
  sleep 2
}
case "$1" in
  start)     mark "start"; echo marked ;;
  modes)     mark "modes x${2:-50}"; loop step_modes ${2:-50}; mark "modes done" ;;
  blank)     mark "blank x${2:-100}"; loop step_blank ${2:-100}; mark "blank done" ;;
  backlight) mark "backlight x${2:-20}"; loop step_bl ${2:-20}; mark "backlight done" ;;
  anim)      mark "anim ${2:-60}s"; bitra-drm anim 0 ${2:-60}; mark "anim done" ;;
  rebind)    mark "rebind x${2:-20}"; loop step_rebind ${2:-20}; mark "rebind done" ;;
  mix)
    S=${2:-120}; mark "mix ${S}s"
    ( while :; do step_modes; done ) & A=$!
    ( while :; do step_blank; done ) & B=$!
    ( while :; do step_bl; done ) & C=$!
    ( while :; do bitra-drm anim 0 5; done ) > /dev/null 2>&1 & E=$!
    for c in 1 2 3 4; do ( while :; do :; done ) & eval "H$c=\$!"; done
    sleep $S
    kill $A $B $C $E $H1 $H2 $H3 $H4 2>/dev/null; sleep 2; killall bitra-drm 2>/dev/null
    echo 0 > $FB; mark "mix done" ;;
  fault)
    FAULT_PCT=${3:-25}; mark "fault x${2:-40} ${FAULT_PCT}%"
    echo Y > $FS/task-filter; echo N > $FS/ignore-gfp-wait; echo 1 > $FS/interval; echo -1 > $FS/times 2>/dev/null || echo 100000 > $FS/times
    echo 0 > $FS/space; echo 1 > $FS/verbose 2>/dev/null; echo $FAULT_PCT > $FS/probability
    loop step_fault ${2:-40}
    echo 0 > $FS/probability; echo N > $FS/task-filter
    [ -e $P/$D ] || echo $D > $P/bind; mark "fault done" ;;
  failnth)
    # Only ONE allocation of ONE write() fails: failslab is task-filtered with probability 0 (so nothing else is affected;
    # the earlier probability=100 without task-filter failed every allocation system-wide and hung the phone), and
    # bitra-failnth opens everything first, arms fail-nth=N and does a single write to the driver's bind file.
    A=${2:-1}; Z=${3:-100}; OUTF=${4:-/tmp/failnth.txt}; mark "failnth $A..$Z"
    echo Y > $FS/task-filter; echo N > $FS/ignore-gfp-wait; echo 0 > $FS/probability; echo 1 > $FS/interval
    echo 100000 > $FS/times; echo 0 > $FS/space
    PATF='KASAN|Unable to handle|refcount_t|BUG:|possible circular|inconsistent lock|UBSAN|use-after-free|Oops'
    n=$A
    while [ $n -le $Z ]; do
      base=$(dmesg | grep -c -E "$PATF")
      echo $D > $P/unbind 2>/dev/null; sleep 1
      res=$(bitra-failnth $P/bind $D $n 2>&1)
      sleep 1
      st=ok; [ -e $P/$D ] || { echo $D > $P/bind 2>/dev/null; st=failed; sleep 1; }
      sleep 2
      new=$(dmesg | grep -c -E "$PATF")
      if [ "$new" -gt "$base" ]; then r="SPLAT(+$((new-base)))"; else r=clean; fi
      echo "N=$n $res probe=$st $r" | tee -a $OUTF
      case "$res" in *"left=0"*) ;; *) echo "N=$n past the last allocation point: sweep complete" | tee -a $OUTF; break;; esac
      n=$((n+1))
    done
    echo 0 > $FS/probability; echo N > $FS/task-filter; mark "failnth done" ;;
  leak)
    mark "kmemleak scan"; echo scan > /sys/kernel/debug/kmemleak; sleep 6; echo scan > /sys/kernel/debug/kmemleak
    cat /sys/kernel/debug/kmemleak | head -60 ;;
  report)
    case "$2" in
      boot) dmesg | sed '/soak: start/,$d' > /tmp/rep.txt ;;
      *)    dmesg | sed -n '/soak: start/,$p' > /tmp/rep.txt ;;
    esac
    PAT='BUG:|KASAN|UBSAN|WARNING:|possible (circular|recursive|irq)|inconsistent lock|suspicious RCU|Oops|Unable to handle|refcount_t|use-after|double-free|invalid-free|Poison|corrupt|kmemleak:|hung task|soft lockup|rcu.*stall|underflow|DSI.*(fail|error|timeout)|msm_dpu.*(error|fail)'
    echo "lines=$(wc -l < /tmp/rep.txt)"
    for k in KASAN UBSAN "BUG:" "WARNING:" lockdep "possible circular" kmemleak "hung task" "soft lockup" "Oops|Unable to handle" "underflow"; do
      echo "$k: $(grep -c -E "$k" /tmp/rep.txt)"
    done
    echo "--- first matches"; grep -E "$PAT" /tmp/rep.txt | head -${3:-40} ;;
  *) echo "usage: soak.sh start|modes|blank|backlight|anim|mix|rebind|leak|report" ;;
esac
