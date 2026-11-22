#!/bin/sh
# Flash a boot image to the `boot` partition from a running phone (mainline/Alpine shell), verify by readback. Runs on the phone.
#   flash-boot.sh IMAGE SHA256        IMAGE must already be on the phone (use a tmpfs: mount -t tmpfs tmpfs /mnt/ram), SHA256 = hash of the host copy.
# Checks: exactly one partition named boot, 196608 sectors (96 MiB), not mounted, image hash and size. BACK UP the partition first:
#   dd if=/dev/sde11 of=/root/boot-backup.img bs=4M; sha256sum ...; copy it off the phone.
# Restore from a keys-entered fastboot: fastboot flash boot boot-backup.img
set -e
IMG=$1; WANT=$2
[ -f "$IMG" ] && [ -n "$WANT" ] || { echo "usage: $0 IMAGE SHA256"; exit 2; }
N=0; DEV=
for d in /sys/class/block/sd*; do grep -qx "PARTNAME=boot" $d/uevent && { DEV=/dev/$(basename $d); N=$((N+1)); }; done
[ "$N" = 1 ] || { echo "expected exactly one partition named boot, found $N"; exit 1; }
SECT=$(cat /sys/class/block/$(basename $DEV)/size)
echo "target $DEV sectors=$SECT"
[ "$SECT" = 196608 ] || { echo "unexpected partition size"; exit 1; }
grep -q "^$DEV " /proc/mounts && { echo "mounted!"; exit 1; }
SZ=$(stat -c %s "$IMG")
[ "$(sha256sum "$IMG" | cut -d' ' -f1)" = "$WANT" ] || { echo "image hash mismatch"; exit 1; }
[ "$SZ" -le 100663296 ] || { echo "image too big"; exit 1; }
blockdev --setrw $DEV 2>/dev/null || true
dd if="$IMG" of=$DEV bs=4M conv=fsync 2>&1 | tail -1
sync; echo 3 > /proc/sys/vm/drop_caches
GOT=$(dd if=$DEV bs=4M 2>/dev/null | head -c $SZ | sha256sum | cut -d' ' -f1)
echo "readback: $GOT"
[ "$GOT" = "$WANT" ] && echo "FLASH OK" || { echo "READBACK MISMATCH"; exit 1; }
