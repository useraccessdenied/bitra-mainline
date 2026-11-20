#!/usr/bin/env python3
"""Build a minimal debug initramfs + boot.img for bitra (stdlib only, host-native).

The initramfs contains a static aarch64 busybox and an /init that brings up a USB gadget
(CDC-NCM, which macOS supports natively) and starts a network shell, so a RAM-only
`fastboot boot` on the test Mac proves: kernel boots -> userspace runs -> USB gadget works.

  python3 scripts/build_debug_initramfs.py [--kernel Image] [--dtb dtb] [--out releases/droidian-debug]

Boot image parameters come from the STOCK Android 13 boot.img (header v2, see docs/11).
Nothing here touches the device.
"""
import argparse, gzip, hashlib, io, os, stat, struct, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# the Android build repo (bitra-lineageos) supplies busybox, mkbootimg and the Droidian DTB carrier; override with BITRA_REPO
BITRA = Path(os.environ.get("BITRA_REPO", ROOT.parent / "bitra"))
BUSYBOX = BITRA / "roms/lineageos/a17/kernel/realme/sm8250/KernelSU/userspace/ksud/bin/aarch64/busybox"
MKBOOTIMG = BITRA / "roms/lineageos/a16/system/tools/mkbootimg/mkbootimg.py"
KERNEL_DEFAULT = BITRA / "roms/droidian/kernel-out/arch/arm64/boot/Image"
DTB_DEFAULT = BITRA / "releases/droidian-kernel/dtb"

# stock cmdline (firmware/stock-a13/boot-unpacked) + debug extras
CMDLINE = ("console=ttyMSM0,115200n8 earlycon=msm_geni_serial,0xa90000 androidboot.hardware=qcom "
           "androidboot.console=ttyMSM0 androidboot.memcg=1 lpm_levels.sleep_disabled=1 "
           "video=vfb:640x400,bpp=32,memsize=3072000 msm_rtb.filter=0x237 service_locator.enable=1 "
           "androidboot.usbcontroller=a600000.dwc3 swiotlb=2048 loop.max_part=7 "
           "cgroup.memory=nokmem,nosocket reboot=panic_warm kpti=off buildvariant=user "
           "printk.devkmsg=on loglevel=7")

INIT = r"""#!/bin/busybox sh
# bitra debug initramfs: USB NCM gadget + network shell
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
/bin/busybox --install -s /bin 2>/dev/null
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null
mkdir -p /dev/pts /config /pstore /tmp
mount -t devpts devpts /dev/pts
mount -t configfs none /config
mount -t pstore pstore /pstore 2>/dev/null
log() { echo "bitra-debug: $*" > /dev/kmsg; echo "bitra-debug: $*"; }
log "init started, kernel $(uname -r)"

G=/config/usb_gadget/g1
mkdir -p $G && cd $G
echo 0x1d6b > idVendor
echo 0x0104 > idProduct
mkdir -p strings/0x409
echo "bitra-debug" > strings/0x409/manufacturer
echo "halium-debug" > strings/0x409/product
echo "bitra0001" > strings/0x409/serialnumber
mkdir -p configs/c.1/strings/0x409
echo "NCM" > configs/c.1/strings/0x409/configuration
mkdir -p functions/ncm.usb0
ln -s $G/functions/ncm.usb0 configs/c.1/ncm.usb0

# wait for a UDC (dwc3 may probe late)
i=0
while [ -z "$(ls /sys/class/udc 2>/dev/null)" ] && [ $i -lt 30 ]; do sleep 1; i=$((i+1)); done
UDC=$(ls /sys/class/udc | head -n1)
log "UDC='$UDC' after ${i}s"
echo "$UDC" > $G/UDC || log "binding UDC failed"
sleep 2
IF=$(ls /sys/class/net | grep -v '^lo$' | grep -E '^(usb|ncm)' | head -n1)
log "usb net interface: '$IF'"
if [ -n "$IF" ]; then
  ifconfig "$IF" 192.168.2.15 netmask 255.255.255.0 up
  log "ip 192.168.2.15 on $IF"
  nc -ll -p 23 -e /bin/sh &
  telnetd -p 2323 -l /bin/sh &
fi
cd /
# keep alive; heartbeat helps when watching pstore/dmesg
while true; do log "alive $(cat /proc/uptime | cut -d' ' -f1)s"; sleep 10; done
"""


def cpio_newc(entries):
    """entries: list of (path, mode, data_bytes|None, rdev(major,minor)|None). Returns bytes."""
    out = io.BytesIO()
    ino = 1

    def pad(n):
        out.write(b"\0" * ((4 - n % 4) % 4))

    for path, mode, data, rdev in entries + [("TRAILER!!!", 0, b"", None)]:
        name = path.encode() + b"\0"
        data = data or b""
        major, minor = rdev or (0, 0)
        nlink = 2 if stat.S_ISDIR(mode) else 1
        hdr = "070701" + "".join(f"{v:08X}" for v in (
            ino, mode, 0, 0, nlink, 0, len(data), 0, 0, major, minor, len(name), 0))
        out.write(hdr.encode()); out.write(name); pad(110 + len(name))
        out.write(data); pad(len(data))
        ino += 1
    return out.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kernel", default=str(KERNEL_DEFAULT))
    ap.add_argument("--dtb", default=str(DTB_DEFAULT))
    ap.add_argument("--out", default=str(ROOT / "releases/debug"))
    ap.add_argument("--pad-mb", type=int, default=0, help="add incompressible padding to the ramdisk (size experiment)")
    ap.add_argument("--ramdisk-offset", default="0x1000000")
    ap.add_argument("--boot-name", default="debug-boot.img")
    ap.add_argument("--cmdline-extra", default="", help="appended to the kernel cmdline (bisect experiments)")
    a = ap.parse_args()
    for p in (BUSYBOX, MKBOOTIMG, Path(a.kernel), Path(a.dtb)):
        if not Path(p).exists():
            sys.exit(f"missing: {p}")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    bb = BUSYBOX.read_bytes()
    D, F, X = stat.S_IFDIR | 0o755, stat.S_IFREG | 0o644, stat.S_IFREG | 0o755
    entries = [(d, D, None, None) for d in ("bin", "sbin", "dev", "proc", "sys", "tmp", "config", "pstore", "etc", "dev/pts")]
    entries += [("bin/busybox", X, bb, None), ("init", X, INIT.encode(), None),
                ("etc/passwd", F, b"root::0:0:root:/:/bin/sh\n", None),
                ("dev/console", stat.S_IFCHR | 0o600, None, (5, 1)), ("dev/null", stat.S_IFCHR | 0o666, None, (1, 3))]
    if a.pad_mb:
        entries.append(("pad.bin", F, os.urandom(a.pad_mb << 20), None))
    ramdisk = out / ("ramdisk-" + a.boot_name.replace(".img", "") + ".cpio.gz")
    with gzip.GzipFile(ramdisk, "wb", mtime=0) as g:
        g.write(cpio_newc(entries))

    boot = out / a.boot_name
    cmd = [sys.executable, str(MKBOOTIMG), "--header_version", "2", "--kernel", a.kernel, "--ramdisk", str(ramdisk),
           "--dtb", a.dtb, "--base", "0x0", "--kernel_offset", "0x8000", "--ramdisk_offset", a.ramdisk_offset,
           "--dtb_offset", "0x1f00000", "--tags_offset", "0x100", "--pagesize", "4096",
           "--os_version", "13.0.0", "--os_patch_level", "2024-10", "--cmdline", (CMDLINE + " " + a.cmdline_extra).strip(), "-o", str(boot)]
    subprocess.run(cmd, check=True)
    (out / "init").write_text(INIT)
    sums = (out / "SHA256SUMS").read_text() if (out / "SHA256SUMS").exists() else ""
    sums = "".join(l for l in sums.splitlines(True) if boot.name not in l and ramdisk.name not in l)
    for f in (boot, ramdisk):
        sums += f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}\n"
    sums += f"{hashlib.sha256(bb).hexdigest()}  (busybox source: {BUSYBOX.name}, from the KernelSU repo, topjohnwu build)\n"
    (out / "SHA256SUMS").write_text(sums)
    print(sums)
    print(f"boot image: {boot} ({boot.stat().st_size >> 20} MiB)")


if __name__ == "__main__":
    main()
