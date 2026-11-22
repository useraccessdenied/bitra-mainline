#!/usr/bin/env python3
"""Build an Alpine (aarch64) root filesystem image for the bitra mainline port. Stdlib only, no sudo, no containers.

  python3 scripts/build_alpine_rootfs.py [--branch v3.24] [--size-mb 2048] [--out releases/alpine-rootfs.ext4]

How: re-executes itself under `unshare --map-root-user --map-auto` (user namespace with the /etc/subuid range: uid 0 inside, other ids mapped),
downloads the sha256-verified alpine-minirootfs, runs the x86_64 apk-tools-static against it (package signatures are
checked by apk with the keys that ship in the minirootfs; post-install scripts run through the host's qemu-user binfmt),
adds the bitra bits (USB-NCM network + telnetd for the bitra-agent, firmware, helper tools, services) and packs it with
`mke2fs -d`. The firmware and helper binaries are the same ones the RAM-boot initramfs carries.
Build dir: build/alpine (gitignored). Not verified: apk-tools-static itself (TLS only; it only runs in the build namespace).
"""
import argparse, hashlib, lzma, os, re, shutil, subprocess, sys, tarfile, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BITRA = Path(os.environ.get("BITRA_REPO", ROOT.parent / "bitra"))
BUILD = ROOT / "build/alpine"
MIRROR = "https://dl-cdn.alpinelinux.org/alpine"
CLANG = BITRA / "roms/lineageos/a16/prebuilts/clang/host/linux-x86/clang-r563880c/bin/clang"
LINUX = Path(os.environ.get("MAINLINE_SRC", BITRA / "roms/mainline/linux"))
OUT = Path(os.environ.get("MAINLINE_OUT", BITRA / "roms/mainline/out"))
FW_ROOT = Path(os.environ.get("FIRMWARE_DIR", "/usr/lib/firmware"))
FW_FILES = ["regulatory.db", "regulatory.db.p7s", "ath11k/QCA6390/hw2.0/amss.bin", "ath11k/QCA6390/hw2.0/m3.bin",
            "ath11k/QCA6390/hw2.0/board-2.bin", "qca/htbtfw20.tlv", "qca/htnv20.bin"]
PACKAGES = ["alpine-base", "busybox-extras", "openssh", "iw", "wpa_supplicant", "e2fsprogs", "e2fsprogs-extra", "bluez", "dbus",
            "wireless-regdb", "nano", "htop", "util-linux", "kbd"]
TOOLS = [("bitra-reboot", False), ("bitra-failnth", False), ("bitra-drm", True), ("bitra-evtest", True)]


def get(url):
    with urllib.request.urlopen(url, timeout=180) as r:
        return r.read()


def cached(url, name, sha256=None):
    BUILD.mkdir(parents=True, exist_ok=True)
    p = BUILD / name
    if not p.exists():
        p.write_bytes(get(url))
    if sha256 and hashlib.sha256(p.read_bytes()).hexdigest() != sha256:
        p.unlink()
        sys.exit(f"sha256 mismatch for {name}")
    return p


def minirootfs(branch):
    yaml = get(f"{MIRROR}/{branch}/releases/aarch64/latest-releases.yaml").decode()
    m = re.search(r"file: (alpine-minirootfs-[\d.]+-aarch64\.tar\.gz)\n(?:.*\n){4}\s+sha256: ([0-9a-f]{64})", yaml)
    if not m:
        sys.exit("cannot find minirootfs in latest-releases.yaml")
    return cached(f"{MIRROR}/{branch}/releases/aarch64/{m.group(1)}", m.group(1), m.group(2))


def apk_static(branch):
    idx = subprocess.run(["tar", "-xzO", "APKINDEX"], input=get(f"{MIRROR}/{branch}/main/x86_64/APKINDEX.tar.gz"),
                         capture_output=True, check=True).stdout.decode()
    m = re.search(r"^P:apk-tools-static\nV:(\S+)\n", idx, re.M)
    pkg = cached(f"{MIRROR}/{branch}/main/x86_64/apk-tools-static-{m.group(1)}.apk", f"apk-tools-static-{m.group(1)}.apk")
    d = BUILD / "apk-static"
    d.mkdir(exist_ok=True)
    subprocess.run(["tar", "-xzf", str(pkg), "-C", str(d), "sbin/apk.static"], stderr=subprocess.DEVNULL)
    exe = d / "sbin/apk.static"
    if not exe.exists():
        sys.exit("apk.static not found in the package")
    return exe


def compile_tool(name, needs_headers):
    out = BUILD / "tools" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(CLANG), "--target=aarch64-linux-gnu", "-static", "-nostdlib", "-ffreestanding", "-fno-stack-protector",
           "-O2", "-fuse-ld=lld"]
    if needs_headers:
        cmd += ["-D__linux__", "-D__user=", "-Wno-#warnings", f"-I{LINUX}/include/uapi", f"-I{LINUX}/arch/arm64/include/uapi",
                f"-I{OUT}/arch/arm64/include/generated/uapi"]
    subprocess.run(cmd + ["-o", str(out), str(ROOT / "tools" / (name + ".c"))], check=True)
    return out


SYSTEMCTL_SHIM = """#!/bin/sh
# the bitra-agent calls systemctl for reboot / state; Alpine has no systemd
case "$*" in
  *reboot-argument=bootloader*) exec /usr/local/bin/bitra-reboot bootloader ;;
  *reboot-argument=recovery*) exec /usr/local/bin/bitra-reboot recovery ;;
  reboot*|*" reboot"*) exec /usr/local/bin/bitra-reboot ;;
  *is-system-running*) echo running ;;
esac
exit 0
"""

BITRA_NET = """#!/sbin/openrc-run
description="USB NCM link to the host: 192.168.2.15, DHCP pool .20-.30, telnetd for the bitra-agent"
depend() { before sshd; need localmount; }
start() {
    IF=
    for i in $(seq 1 30); do
        IF=$(ls /sys/class/net | grep -E '^(usb|ncm)' | head -n1)
        [ -n "$IF" ] && break
        sleep 1
    done
    [ -n "$IF" ] || { eerror "no USB net interface"; return 1; }
    ip addr flush dev "$IF"; ip addr add 192.168.2.15/24 dev "$IF"; ip link set "$IF" up
    killall telnetd udhcpd 2>/dev/null   # leftovers of the initramfs; bitra-telnetd/bitra-udhcpd are supervised
    return 0
}
stop() { return 0; }
"""

BITRA_TELNETD = """#!/sbin/openrc-run
description="telnetd on :23 for the bitra-agent, respawned if it dies"
depend() { need bitra-net; }
start() {
    start-stop-daemon -S -b -m -p /run/bitra-telnetd.pid -x /bin/sh -- -c 'while :; do /usr/sbin/telnetd -F -b 0.0.0.0:23 -l /bin/sh; sleep 1; done'
}
stop() { start-stop-daemon -K -p /run/bitra-telnetd.pid; killall telnetd 2>/dev/null; return 0; }
"""

BITRA_UDHCPD = """#!/sbin/openrc-run
description="DHCP pool .20-.30 for the host side of the USB link, respawned if it dies"
depend() { need bitra-net; }
start() {
    start-stop-daemon -S -b -m -p /run/bitra-udhcpd.pid -x /bin/sh -- -c 'while :; do /usr/sbin/udhcpd -f /etc/bitra-udhcpd.conf; sleep 1; done'
}
stop() { start-stop-daemon -K -p /run/bitra-udhcpd.pid; killall udhcpd 2>/dev/null; return 0; }
"""
UDHCPD_CONF = "start 192.168.2.20\\nend 192.168.2.30\\ninterface usb0\\nlease_file /run/udhcpd.leases\\noption subnet 255.255.255.0\\n".replace("\\n", "\n")

BITRA_GROWFS = """#!/sbin/openrc-run
description="grow the root ext4 to fill its partition (no-op when already full)"
depend() { need root; before bitra-net; }
start() {
    dev=$(awk '$2=="/" && $1 ~ /^\\/dev\\// {print $1}' /proc/mounts | tail -n1)
    [ -b "$dev" ] || return 0
    resize2fs "$dev" >/dev/null 2>&1
    return 0
}
"""

BITRA_DIAG = """#!/sbin/openrc-run
description="print network/service state into /etc/issue so it shows above the console login prompt"
depend() { after *; }
start() {
    {
        echo "--- bitra-diag ---"
        ifconfig usb0 2>&1 | head -4
        route -n 2>&1 | head -4
        cat /proc/net/arp
        cat /proc/sys/net/ipv4/conf/usb0/rp_filter /proc/sys/net/ipv4/conf/all/rp_filter
        netstat -ltn 2>&1 | head -5
        echo "pids: telnetd=$(pidof telnetd) udhcpd=$(pidof udhcpd) sshd=$(pidof sshd)"
        rc-status -a 2>&1 | grep -E "bitra|crashed" | head -6
        dmesg | grep -i -E "usb|ncm|gadget|dwc3" | tail -4
        echo "------------------"
    } >> /etc/issue
    return 0
}
"""

BITRA_WATCH = """#!/sbin/openrc-run
description="debug: print ARP, TCP connections and usb0 counters to the panel every 15 s"
depend() { after bitra-diag; }
start() {
    start-stop-daemon -S -b -m -p /run/bitra-watch.pid -x /bin/sh -- -c 'while :; do { echo "== $(date +%T) arp:"; tail -n +2 /proc/net/arp; echo "tcp:"; netstat -tn | tail -n +3; ifconfig usb0 | grep -E "RX packets|TX packets"; } > /dev/tty1 2>&1; sleep 15; done'
}
stop() { start-stop-daemon -K -p /run/bitra-watch.pid; }
"""

BITRA_WIFI = """#!/sbin/openrc-run
description="Wi-Fi: wpa_supplicant + DHCP on wlan0 when /etc/wpa_supplicant/wpa_supplicant.conf exists (the config is pushed after flashing, not baked in)"
depend() { after bitra-net; }
start() {
    [ -f /etc/wpa_supplicant/wpa_supplicant.conf ] || return 0
    ip link set wlan0 up
    wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf -P /run/wpa_supplicant.pid
    udhcpc -b -i wlan0 -p /run/udhcpc-wlan0.pid
    return 0
}
stop() {
    [ -f /run/udhcpc-wlan0.pid ] && kill $(cat /run/udhcpc-wlan0.pid) 2>/dev/null
    [ -f /run/wpa_supplicant.pid ] && kill $(cat /run/wpa_supplicant.pid) 2>/dev/null
    return 0
}
"""

BITRA_TIME = """#!/sbin/openrc-run
description="no RTC on this phone: restore the last known time (TLS needs a sane clock), then sync with NTP when a network is up"
depend() { need localmount; before bitra-wifi sshd; }
start() {
    now=$(date +%s)
    saved=$(cat /var/lib/bitra-time 2>/dev/null || echo 0)
    built=$(cat /etc/bitra-build-time 2>/dev/null || echo 0)
    best=$saved; [ "$built" -gt "$best" ] && best=$built
    [ "$now" -lt "$best" ] && date -s "@$best" >/dev/null
    # plain background job (not start-stop-daemon): it exits when the time is synced, which openrc would report as 'crashed'
    setsid sh -c 'until ntpd -q -n -p pool.ntp.org -p time.cloudflare.com >/dev/null 2>&1; do sleep 10; done; mkdir -p /var/lib; date +%s > /var/lib/bitra-time' >/dev/null 2>&1 &
    return 0
}
stop() {
    mkdir -p /var/lib; date +%s > /var/lib/bitra-time
    return 0
}
"""

FSTAB = "# <fs> <mountpoint> <type> <opts> <dump> <pass>\nLABEL=bitra-root / ext4 rw,noatime 0 1\n"
INITTAB = """::sysinit:/sbin/openrc sysinit
::sysinit:/sbin/openrc boot
::wait:/sbin/openrc default
tty1::respawn:/sbin/getty 38400 tty1
::ctrlaltdel:/sbin/reboot
::shutdown:/sbin/openrc shutdown
"""
SSHD_CONF = "PermitRootLogin yes\nPasswordAuthentication yes\n"


def sh(*cmd, **kw):
    return subprocess.run(list(map(str, cmd)), check=True, **kw)


def inner(a):
    root = BUILD / "rootfs"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    sh("tar", "-xzf", minirootfs(a.branch), "-C", root)
    apk = apk_static(a.branch)
    repos = f"{MIRROR}/{a.branch}/main\n{MIRROR}/{a.branch}/community\n"
    (root / "etc/apk/repositories").write_text(repos)
    sh(apk, "--root", root, "--arch", "aarch64", "--keys-dir", root / "etc/apk/keys", "--no-cache", "--no-interactive",
       "-X", f"{MIRROR}/{a.branch}/main", "-X", f"{MIRROR}/{a.branch}/community", "add", *PACKAGES)

    def put(rel, data, mode=0o644):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data) if isinstance(data, str) else p.write_bytes(data)
        p.chmod(mode)

    put("etc/hostname", "bitra\n")
    put("etc/fstab", FSTAB)
    put("etc/inittab", INITTAB)
    put("etc/ssh/sshd_config.d/bitra.conf", SSHD_CONF)
    put("etc/init.d/bitra-net", BITRA_NET, 0o755)
    put("etc/init.d/bitra-growfs", BITRA_GROWFS, 0o755)
    put("etc/init.d/bitra-diag", BITRA_DIAG, 0o755)
    put("etc/init.d/bitra-time", BITRA_TIME, 0o755)
    put("etc/bitra-build-time", str(int(__import__("time").time())) + "\n")
    put("etc/init.d/bitra-wifi", BITRA_WIFI, 0o755)
    put("etc/init.d/bitra-watch", BITRA_WATCH, 0o755)
    put("etc/init.d/bitra-telnetd", BITRA_TELNETD, 0o755)
    put("etc/init.d/bitra-udhcpd", BITRA_UDHCPD, 0o755)
    put("etc/bitra-udhcpd.conf", UDHCPD_CONF)
    put("etc/motd", "bitra (realme GT Neo 2) - Alpine on mainline Linux\n")
    put("usr/bin/systemctl", SYSTEMCTL_SHIM, 0o755)
    put("bin/bash", "#!/bin/busybox sh\nexec /bin/busybox ash\n", 0o755)   # the agent's shell wrapper wants a bash
    (root / "usr/local/sbin").mkdir(parents=True, exist_ok=True)
    (root / "usr/local/sbin/busybox-bitra").symlink_to("/bin/busybox")
    for name, hdr in TOOLS:
        t = compile_tool(name, hdr)
        put(f"usr/local/bin/{name}", t.read_bytes(), 0o755)
    soak = ROOT / "tools/soak.sh"
    if soak.exists():
        put("usr/local/bin/soak.sh", soak.read_bytes(), 0o755)
    for rel in FW_FILES:
        xz = FW_ROOT / (rel + ".xz")
        put("lib/firmware/" + rel, lzma.open(xz).read() if xz.exists() else (FW_ROOT / rel).read_bytes())
    keys = [p.read_text() for p in sorted(Path.home().glob(".ssh/*.pub"))]
    if keys:
        put("root/.ssh/authorized_keys", "".join(keys), 0o600)
        (root / "root/.ssh").chmod(0o700)

    # runlevels + root password, run inside the image through qemu-user binfmt
    def chroot(*cmd, inp=None):
        return subprocess.run(["chroot", str(root), *cmd], check=True, input=inp)

    for svc, lvl in [("devfs", "sysinit"), ("dmesg", "sysinit"), ("mdev", "sysinit"),
                     ("hostname", "boot"), ("bitra-time", "boot"), ("sysctl", "boot"), ("bootmisc", "boot"), ("syslog", "boot"),
                     ("bitra-growfs", "boot"), ("bitra-net", "default"), ("bitra-telnetd", "default"), ("bitra-udhcpd", "default"), ("bitra-wifi", "default"), ("bitra-diag", "default"), ("sshd", "default"), ("dbus", "default"),
                     ("mount-ro", "shutdown"), ("killprocs", "shutdown"), ("savecache", "shutdown")]:
        if (root / "etc/init.d" / svc).exists():
            chroot("/sbin/rc-update", "add", svc, lvl)
    chroot("/usr/sbin/chpasswd", inp=b"root:bitra\n")

    img = Path(a.out)
    img.parent.mkdir(parents=True, exist_ok=True)
    if img.exists():
        img.unlink()
    sh("mke2fs", "-q", "-t", "ext4", "-L", "bitra-root", "-d", root, "-E", "lazy_itable_init=1", img, f"{a.size_mb}M")
    sh("e2fsck", "-fn", img)
    h = hashlib.sha256()
    with open(img, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    Path(str(img) + ".sha256").write_text(f"{h.hexdigest()}  {img.name}\n")
    print(f"image: {img} ({img.stat().st_size >> 20} MiB apparent)  sha256 {h.hexdigest()}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--branch", default="v3.24")
    ap.add_argument("--size-mb", type=int, default=2048)
    ap.add_argument("--out", default=str(ROOT / "releases/alpine-rootfs.ext4"))
    a = ap.parse_args()
    if os.geteuid() != 0:
        os.execvp("unshare", ["unshare", "--map-root-user", "--map-auto", sys.executable, *sys.argv])
    inner(a)


if __name__ == "__main__":
    main()
