#!/usr/bin/env python3
"""Make the boot logo as a gzip-compressed raw framebuffer (XRGB8888, little endian) for the release initramfs.

The initramfs writes it straight to /dev/fb0 (`gunzip -c /logo.raw.gz > /dev/fb0`), so the geometry must match the panel's fbdev:
1080x2400 visible, stride 4352 bytes (measured on the phone: /sys/class/graphics/fb0/{virtual_size,stride}).
A flat image compresses to a few KB. Use --png FILE to show your own picture instead (8-bit RGB/RGBA, not interlaced; it is centred, not scaled).
  python3 tools/make-boot-logo.py OUT.raw.gz [--png logo.png]
"""
import argparse, gzip, math, struct, sys, zlib

W, H, STRIDE = 1080, 2400, 4352
FG = bytes((0xE6, 0xE6, 0xE6, 0))   # B G R X
FONT = {
    "b": ["X....", "X....", "XXXX.", "X...X", "X...X", "X...X", "XXXX."],
    "i": ["..X..", ".....", ".XX..", "..X..", "..X..", "..X..", ".XXX."],
    "t": [".X...", ".X...", "XXXX.", ".X...", ".X...", ".X..X", "..XX."],
    "r": [".....", ".....", "X.XX.", "XX..X", "X....", "X....", "X...."],
    "a": [".....", ".....", ".XXX.", "....X", ".XXXX", "X...X", ".XXXX"],
}


def fill(fb, x0, x1, y, px=FG):
    if 0 <= y < H and x1 > x0:
        fb[y * STRIDE + x0 * 4: y * STRIDE + x1 * 4] = px * (x1 - x0)


def default_logo(fb):
    cx, cy, ro, ri = W // 2, 900, 230, 190
    for y in range(cy - ro, cy + ro + 1):
        dy = y - cy
        xo = int(math.sqrt(max(ro * ro - dy * dy, 0)))
        if abs(dy) >= ri:
            fill(fb, cx - xo, cx + xo + 1, y)
        else:
            xi = int(math.sqrt(ri * ri - dy * dy))
            fill(fb, cx - xo, cx - xi, y); fill(fb, cx + xi + 1, cx + xo + 1, y)
    s = 22                                   # pixel size of the 5x7 font
    word = "bitra"; tw = len(word) * 6 * s - s
    x = (W - tw) // 2; y0 = 1300
    for ch in word:
        for r, row in enumerate(FONT[ch]):
            for c, v in enumerate(row):
                if v == "X":
                    for yy in range(s):
                        fill(fb, x + c * s, x + c * s + s, y0 + r * s + yy)
        x += 6 * s


def png_logo(fb, path):
    d = open(path, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit("not a PNG")
    pos, idat, ihdr = 8, b"", None
    while pos < len(d):
        n, t = struct.unpack(">I4s", d[pos:pos + 8]); body = d[pos + 8:pos + 8 + n]; pos += 12 + n
        if t == b"IHDR": ihdr = struct.unpack(">IIBBBBB", body)
        elif t == b"IDAT": idat += body
    w, h, depth, ctype, _, _, il = ihdr
    if depth != 8 or ctype not in (2, 6) or il:
        sys.exit("PNG must be 8-bit RGB or RGBA, not interlaced")
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat); prev = bytearray(w * bpp); ox, oy = (W - w) // 2, (H - h) // 2
    for y in range(h):
        f = raw[y * (w * bpp + 1)]; line = bytearray(raw[y * (w * bpp + 1) + 1:(y + 1) * (w * bpp + 1)])
        for i in range(len(line)):
            a = line[i - bpp] if i >= bpp else 0; b = prev[i]; c = prev[i - bpp] if i >= bpp else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if 0 <= oy + y < H:
            for x in range(w):
                if 0 <= ox + x < W:
                    r, g, bl = line[x * bpp:x * bpp + 3]
                    o = (oy + y) * STRIDE + (ox + x) * 4; fb[o:o + 3] = bytes((bl, g, r))


def make(png=None):
    fb = bytearray(STRIDE * H)
    png_logo(fb, png) if png else default_logo(fb)
    return gzip.compress(bytes(fb), 9, mtime=0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out"); ap.add_argument("--png")
    a = ap.parse_args()
    data = make(a.png); open(a.out, "wb").write(data); print(a.out, len(data), "bytes")
