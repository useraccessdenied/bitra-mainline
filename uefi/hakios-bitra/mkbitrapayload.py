#!/usr/bin/env python3
"""XNUP payload for bitra, small entries first and the kernel last, then 1 MiB of padding.
(The bytes at the very end of a big boot image did not arrive in RAM in the tests of 2026-11-24, so what matters must not be last.)
usage: mkbitrapayload.py -o payload.bin --kernel K [--ramdisk R] [--resident R] [--cmdline "..."] [--kver "..."]"""
import argparse, struct
ap = argparse.ArgumentParser()
ap.add_argument('-o', required=True); ap.add_argument('--kernel', required=True)
ap.add_argument('--ramdisk'); ap.add_argument('--resident'); ap.add_argument('--cmdline', default='-v'); ap.add_argument('--kver', default='')
a = ap.parse_args()
body = b''
def add(n, d):
    global body
    body += struct.pack('<16sII', n.encode(), len(d), 0) + d + b'\0' * (-len(d) % 16)
add('cmdline', a.cmdline.encode() + b'\0')
if a.kver: add('kernel.ver', a.kver.encode() + b'\0')
if a.ramdisk: add('ramdisk', open(a.ramdisk, 'rb').read())
if a.resident: add('resident', open(a.resident, 'rb').read())   # becomes /dev/md0 (rd=md0); the ramdisk is the second disk
add('kernel', open(a.kernel, 'rb').read())
body += b'\0' * 16                      # end marker (an entry with an empty name)
open(a.o, 'wb').write(b'XNUP' + struct.pack('<I', len(body)) + body + b'\0' * 0x100000)
