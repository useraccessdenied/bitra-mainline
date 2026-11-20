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
    '( exec 3>/dev/watchdog0 2>/dev/null || exec 3>/dev/watchdog; while :; do echo . >&3; sleep 4; done ) &  # fd held open: no per-pet close warning\n', 1)
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
# the agent's shell wrapper does `exec bash ... || exec sh`; a failed exec kills busybox ash, so give it a bash,
# and its file transfer uses /usr/local/sbin/busybox-bitra nc
b.INIT = b.INIT.replace('mount -t devtmpfs devtmpfs /dev 2>/dev/null\n',
    'mount -t devtmpfs devtmpfs /dev 2>/dev/null\n'
    "printf '#!/bin/busybox sh\\nexec /bin/busybox ash\\n' > /bin/bash; chmod +x /bin/bash\n"
    'mkdir -p /usr/local/sbin; ln -sf /bin/busybox /usr/local/sbin/busybox-bitra\n', 1)
# reboot-to-bootloader support: tiny static helper + a systemctl shim, so the agent's to-fastboot/reboot/state work here
import subprocess, tempfile
CLANG = BITRA / "roms/lineageos/a16/prebuilts/clang/host/linux-x86/clang-r563880c/bin/clang"
def build_reboot_helper():
    out = Path(tempfile.mkdtemp()) / "bitra-reboot"
    subprocess.run([str(CLANG), "--target=aarch64-linux-gnu", "-static", "-nostdlib", "-ffreestanding", "-fno-stack-protector",
                    "-O2", "-fuse-ld=lld", "-o", str(out), str(ROOT / "tools/bitra-reboot.c")], check=True)
    return out.read_bytes()
SYSTEMCTL_SHIM = b'''#!/bin/busybox sh
case "$*" in
  *reboot-argument=bootloader*) exec /bin/bitra-reboot bootloader ;;
  *reboot-argument=recovery*) exec /bin/bitra-reboot recovery ;;
  reboot*|*" reboot"*) exec /bin/bitra-reboot ;;
  *is-system-running*) echo running ;;
esac
exit 0
'''
LINUX = Path(os.environ.get("MAINLINE_SRC", BITRA / "roms/mainline/linux"))
OUT = Path(os.environ.get("MAINLINE_OUT", BITRA / "roms/mainline/out"))
def build_drm_tool():
    out = Path(tempfile.mkdtemp()) / "bitra-drm"
    subprocess.run([str(CLANG), "--target=aarch64-linux-gnu", "-static", "-nostdlib", "-ffreestanding", "-fno-stack-protector",
                    "-O2", "-fuse-ld=lld", "-D__linux__", "-D__user=", "-Wno-#warnings",
                    f"-I{LINUX}/include/uapi", f"-I{LINUX}/arch/arm64/include/uapi", f"-I{OUT}/arch/arm64/include/generated/uapi",
                    "-o", str(out), str(ROOT / "tools/bitra-drm.c")], check=True)
    return out.read_bytes()
import lzma
FW_ROOT = Path(os.environ.get("FIRMWARE_DIR", "/usr/lib/firmware"))
FW_FILES = ["regulatory.db", "regulatory.db.p7s", "ath11k/QCA6390/hw2.0/amss.bin", "ath11k/QCA6390/hw2.0/m3.bin", "ath11k/QCA6390/hw2.0/board-2.bin",
            "qca/htbtfw20.tlv", "qca/htnv20.bin"]
def firmware_entries():
    import stat as _st
    D, F = _st.S_IFDIR | 0o755, _st.S_IFREG | 0o644
    ents, dirs = [], set()
    for rel in FW_FILES:
        src = FW_ROOT / (rel + ".xz")
        data = lzma.open(src).read() if src.exists() else (FW_ROOT / rel).read_bytes()
        parts = ("lib/firmware/" + rel).split("/")
        for i in range(1, len(parts)):
            d = "/".join(parts[:i])
            if d not in dirs:
                dirs.add(d); ents.append((d, D, None, None))
        ents.append(("lib/firmware/" + rel, F, data, None))
    return ents
ALPINE_ROOT = Path(os.environ.get("ALPINE_ROOT", ROOT / "third_party/alpine/root"))
ALPINE_LIBS = ("libc.musl", "libnl-", "libssl", "libcrypto", "libdbus", "libpcsclite", "libudev")
ALPINE_KEEP = ("lib/", "usr/lib/lib", "sbin/wpa_supplicant", "sbin/wpa_cli", "usr/sbin/iw", "usr/bin/hci", "usr/bin/rfcomm", "usr/bin/sdptool")
def alpine_entries():
    """musl + iw + wpa_supplicant (+libs) from scripts/fetch_alpine_pkgs.py; empty if not fetched."""
    import stat as _st
    if not ALPINE_ROOT.exists():
        return []
    D = _st.S_IFDIR | 0o755
    ents, dirs = [], set()
    for f in sorted(ALPINE_ROOT.rglob("*")):
        rel = str(f.relative_to(ALPINE_ROOT))
        if not f.is_symlink() and not f.is_file():
            continue
        if not rel.startswith(ALPINE_KEEP) or "engines-3" in rel or "ossl-modules" in rel:
            continue
        base = rel.rsplit("/", 1)[-1]
        if "/lib" in "/" + rel and base.startswith("lib") and not base.startswith(ALPINE_LIBS):
            continue	# glib/gio/util-linux etc. come in as dependency noise; the bluez tools are static
        parts = rel.split("/")
        for i in range(1, len(parts)):
            d = "/".join(parts[:i])
            if d not in dirs and d not in ("lib", "usr", "sbin"):
                dirs.add(d); ents.append((d, D, None, None))
            elif d in ("lib", "usr", "sbin") and d not in dirs:
                dirs.add(d); ents.append((d, D, None, None))
        if f.is_symlink():
            ents.append((rel, _st.S_IFLNK | 0o777, os.readlink(f).encode(), None))
        else:
            ents.append((rel, _st.S_IFREG | (0o755 if f.stat().st_mode & 0o111 else 0o644), f.read_bytes(), None))
    return ents
def build_evtest_tool():
    out = Path(tempfile.mkdtemp()) / "bitra-evtest"
    subprocess.run([str(CLANG), "--target=aarch64-linux-gnu", "-static", "-nostdlib", "-ffreestanding", "-fno-stack-protector",
                    "-O2", "-fuse-ld=lld", "-D__linux__", "-D__user=", "-Wno-#warnings",
                    f"-I{LINUX}/include/uapi", f"-I{LINUX}/arch/arm64/include/uapi", f"-I{OUT}/arch/arm64/include/generated/uapi",
                    "-o", str(out), str(ROOT / "tools/bitra-evtest.c")], check=True)
    return out.read_bytes()
_helper = build_reboot_helper()
_drm = build_drm_tool()
_evtest = build_evtest_tool()
_orig_cpio = b.cpio_newc
def _cpio(entries):
    import stat as _st
    X = _st.S_IFREG | 0o755
    return _orig_cpio(entries + firmware_entries() + alpine_entries() + [("bin/bitra-reboot", X, _helper, None), ("bin/bitra-drm", X, _drm, None), ("bin/bitra-evtest", X, _evtest, None), ("bin/systemctl", X, SYSTEMCTL_SHIM, None)])
b.cpio_newc = _cpio
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
