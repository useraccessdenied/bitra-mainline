#!/usr/bin/env python3
"""Raw image -> Android sparse image with ONLY RAW chunks (no DONT_CARE, no FILL). Stdlib.

img2simg turns zero blocks into DONT_CARE chunks, which a flasher skips: flashed over an un-erased partition the old contents stay in those blocks
(an ext4 made with lazy_itable_init has zero inode tables, so the new filesystem then reads the old partition's garbage). This writes every block.
  python3 tools/mksparse.py IN.raw OUT.img [--chunk-mb 64]"""
import argparse, os, struct

BLK = 4096


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inp"); ap.add_argument("out"); ap.add_argument("--chunk-mb", type=int, default=64)
    a = ap.parse_args()
    size = os.path.getsize(a.inp)
    if size % BLK:
        raise SystemExit("input size must be a multiple of 4096")
    blocks = size // BLK; per = a.chunk_mb * 1048576 // BLK
    nchunks = (blocks + per - 1) // per
    with open(a.inp, "rb") as i, open(a.out, "wb") as o:
        o.write(struct.pack("<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, BLK, blocks, nchunks, 0))
        left = blocks
        while left:
            n = min(per, left); left -= n
            o.write(struct.pack("<HHII", 0xCAC1, 0, n, 12 + n * BLK))
            rem = n * BLK
            while rem:
                b = i.read(min(rem, 1 << 22)); o.write(b); rem -= len(b)
    print(f"{a.out}: {nchunks} RAW chunks, {blocks} blocks")


main()
