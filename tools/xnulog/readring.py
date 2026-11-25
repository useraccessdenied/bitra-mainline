#!/usr/bin/env python3
"""readring.py DUMP [DUMP...]: the text in a post-mortem ring dumped from /proc/xnulog (tools/xnulog).
Layout: 8 bytes magic ("XNUPMLOG" kernel, "XNULDLOG" loader), u32 bytes written in all at +8, u32 ring size at +12 (the kernel's ring wraps and
keeps the newest size-64 bytes; the loader's has 0 there and never wraps), text from +64."""
import sys
for path in sys.argv[1:]:
    d = open(path, "rb").read()
    magic = d[:8]
    total = int.from_bytes(d[8:12], "little")
    size = int.from_bytes(d[12:16], "little")
    if magic not in (b"XNUPMLOG", b"XNULDLOG"):
        print("%s: no ring (magic %r)" % (path, magic), file=sys.stderr)
        continue
    cap = (size - 64) if size else (len(d) - 64)
    cap = min(cap, len(d) - 64)
    if total <= cap:
        text = d[64:64 + total]
    else:
        start = total % cap
        text = d[64 + start:64 + cap] + d[64:64 + start]
        sys.stderr.write("%s: %d bytes written, the newest %d are kept\n" % (path, total, cap))
    sys.stdout.write(text.decode("latin1"))
