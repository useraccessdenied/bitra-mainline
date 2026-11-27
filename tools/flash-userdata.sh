#!/bin/sh
# Flash a gzip-compressed ext4 root image to the `userdata` partition from a RAM-booted shell (nothing from UFS mounted), verify by readback. Runs on the phone.
#   flash-userdata.sh IMAGE.gz GZ_SHA256 RAW_SHA256 RAW_BYTES
# IMAGE.gz must already be on the phone in a tmpfs (mount -t tmpfs -o size=1500m tmpfs /mnt/ram). WIPES userdata. Checks: exactly one partition named userdata,
# at least RAW_BYTES large, not mounted, the gzip hash, then writes, syncs, reads back RAW_BYTES and compares with RAW_SHA256.
set -e
GZ=$1; GZSHA=$2; RAWSHA=$3; RAWB=$4
[ -f "$GZ" ] && [ -n "$RAWB" ] || { echo "usage: $0 IMAGE.gz GZ_SHA256 RAW_SHA256 RAW_BYTES"; exit 2; }
N=0; DEV=
for d in /sys/class/block/sd*; do grep -qx "PARTNAME=userdata" $d/uevent && { DEV=/dev/$(basename $d); N=$((N+1)); }; done
[ "$N" = 1 ] || { echo "expected exactly one partition named userdata, found $N"; exit 1; }
SECT=$(cat /sys/class/block/$(basename $DEV)/size)      # 512-byte units
echo "target $DEV, $((SECT*512/1048576)) MiB"
[ $((SECT*512)) -ge "$RAWB" ] || { echo "partition smaller than the image"; exit 1; }
grep -q "^$DEV" /proc/mounts && { echo "mounted!"; exit 1; }
[ "$(sha256sum "$GZ" | cut -d' ' -f1)" = "$GZSHA" ] || { echo "gzip hash mismatch"; exit 1; }
blockdev --setrw $DEV 2>/dev/null || true
gunzip -c "$GZ" | dd of=$DEV bs=4M conv=fsync 2>&1 | tail -1
sync; echo 3 > /proc/sys/vm/drop_caches
GOT=$(dd if=$DEV bs=4M 2>/dev/null | head -c $RAWB | sha256sum | cut -d' ' -f1)
echo "readback: $GOT"
[ "$GOT" = "$RAWSHA" ] && echo "FLASH OK" || { echo "READBACK MISMATCH"; exit 1; }
