#!/usr/bin/env python3
"""Write an image to the phone's `darwin` partition (sda12), chunked, hash-verified, then read back.
Chunks go host -> Mac stage -> phone /tmp (sha256 checked by the agent) -> dd into the partition.
Only ever writes the partition passed as --dev (default /dev/sda12); never a firmware LUN.
Usage: write_darwin_part.py IMAGE [--dev /dev/sda12] [--start-chunk N]"""
import argparse, hashlib, json, subprocess, sys, time

CH = 64 << 20

def ssh(cmd, stdin=None, timeout=900):
    r = subprocess.run(["ssh", "mac", cmd], stdin=stdin, capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr

def phone(cmd):
    return ssh('sh "%s"' % cmd)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("--dev", default="/dev/sda12"); ap.add_argument("--start-chunk", type=int, default=0)
    a = ap.parse_args()
    if a.dev != "/dev/sda12":
        sys.exit("refusing: only /dev/sda12 (darwin) is allowed")
    data = open(a.image, "rb")
    data.seek(0, 2); size = data.tell()
    whole = hashlib.sha256()
    data.seek(0)
    for b in iter(lambda: data.read(1 << 20), b""):
        whole.update(b)
    print("image", size, whole.hexdigest(), flush=True)
    n = (size + CH - 1) // CH
    for i in range(a.start_chunk, n):
        data.seek(i * CH); blob = data.read(CH)
        h = hashlib.sha256(blob).hexdigest()
        path = "/tmp/claude-chunk.bin"
        open(path, "wb").write(blob)
        for attempt in range(3):
            o = ssh("stage --sha256 %s chunk.bin" % h, stdin=open(path, "rb"))
            if '"verified": true' not in o: continue
            o = ssh("put chunk.bin /tmp/chunk.bin")
            if h in o and "remote_sha_output" in o and o.count(h) >= 2: break
        else:
            sys.exit("chunk %d transfer failed: %s" % (i, o))
        o = phone("dd if=/tmp/chunk.bin of=%s bs=1M seek=%d conv=fsync 2>&1 | tail -1; sync" % (a.dev, i * 64))
        print("chunk %d/%d ok %s" % (i + 1, n, o.strip().replace("\n", " ")), flush=True)
    o = phone("head -c %d %s | sha256sum" % (size, a.dev))
    print("readback", o.strip())
    if whole.hexdigest() in o:
        print("VERIFIED")
    else:
        print("MISMATCH"); sys.exit(1)

main()
