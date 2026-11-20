#!/usr/bin/env python3
"""Build a RAM-boot image for the mainline (roms/mainline) kernel on bitra. Stdlib only.

Reuses scripts/build_debug_initramfs.py (busybox + NCM gadget initramfs, header v2 mkbootimg) but:
  * the DTB passed to ABL is Droidian's base kona tree (releases/droidian-kernel/dtb): ABL only accepts
    trees it can merge the vendor dtbo into; the kernel swaps in its embedded tree (BITRA_DTB_SHIM).
  * the heartbeat is quiet so the on-screen early console (earlycon=efifb) is not scrolled away.

  python3 scripts/build_mainline_boot.py NAME [--cmdline-extra STR]
Output: releases/NAME.img (gitignored)
Always boot via `ssh mac to-fastboot` (a manually entered fastboot makes ABL refuse images: 'Load Error').
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_debug_initramfs as b

ROOT = b.ROOT
BITRA = b.BITRA
b.INIT = b.INIT.replace(
    'while true; do log "alive $(cat /proc/uptime | cut -d\' \' -f1)s"; sleep 10; done',
    'while true; do sleep 600; log "alive $(cat /proc/uptime | cut -d\' \' -f1)s"; done')
# quiet kernel log + status lines at KERN_CRIT so they show on the (very slow) panel console;
# pet the ABL-armed watchdog from the first instruction of init; report USB bring-up state
b.INIT = b.INIT.replace('log() { echo "bitra-debug: $*" > /dev/kmsg; echo "bitra-debug: $*"; }',
    'log() { echo "<2>bitra-debug: $*" > /dev/kmsg; }')
b.INIT = b.INIT.replace('/bin/busybox --install -s /bin 2>/dev/null',
    '/bin/busybox --install -s /bin 2>/dev/null\n'
    'mount -t devtmpfs devtmpfs /dev 2>/dev/null\n'
    '( while :; do echo . > /dev/watchdog0 2>/dev/null || echo . > /dev/watchdog 2>/dev/null; sleep 4; done ) &', 1)
b.INIT = b.INIT.replace('UDC=$(ls /sys/class/udc | head -n1)',
    'mount -t debugfs none /sys/kernel/debug 2>/dev/null\n'
    'log "wdt: $(ls /dev/watchdog* 2>&1 | tr "\\n" " ")"\n'
    'log "udc: $(ls /sys/class/udc 2>&1)"\n'
    'for l in $(cat /sys/kernel/debug/devices_deferred 2>/dev/null | tr "\\t" "~" | head -12); do log "deferred: $l"; done\n'
    'UDC=$(ls /sys/class/udc | head -n1)', 1)
# the agent speaks telnet (IAC) on :23, like the Droidian initrd's busybox telnetd; plain `nc -e` closes on it
b.INIT = b.INIT.replace("nc -ll -p 23 -e /bin/sh &", "telnetd -b 0.0.0.0:23 -l /bin/sh")
# DHCP for the Mac side (no sudo needed there): same pool as the Droidian initrd (192.168.2.20-30)
b.INIT = b.INIT.replace('  telnetd -b 0.0.0.0:23 -l /bin/sh',
    "  printf 'start 192.168.2.20\\nend 192.168.2.30\\ninterface %s\\nlease_file /tmp/udhcpd.leases\\noption subnet 255.255.255.0\\n' \"$IF\" > /tmp/udhcpd.conf\n"
    '  udhcpd /tmp/udhcpd.conf &\n'
    '  telnetd -b 0.0.0.0:23 -l /bin/sh',1)
MAIN = Path(os.environ.get("MAINLINE_OUT", BITRA / "roms/mainline/out")) / "arch/arm64/boot"
name = sys.argv[1]
extra = "clk_ignore_unused pd_ignore_unused panic=0 consoleblank=0 earlycon=efifb keep_bootcon fw_devlink.sync_state=strict loglevel=4"
rest = sys.argv[2:]
if rest[:1] == ["--cmdline-extra"]:
    extra = rest[1]
sys.argv = ["x", "--kernel", str(MAIN / "Image.gz"), "--dtb", str(BITRA / "releases/droidian-kernel/dtb"),
            "--out", str(ROOT / "releases"), "--boot-name", name + ".img",
            "--cmdline-extra", extra]
b.main()
