#!/usr/bin/env python3
"""make-ath11k-board.py: add this phone's OEM Wi-Fi board data to an ath11k board-2.bin. Stdlib only; reads inputs, writes a new file.

  python3 tools/make-ath11k-board.py --bdwlan bdwlan.elf --board-2 /usr/lib/firmware/ath11k/QCA6390/hw2.0/board-2.bin \
          --variant realme_GT_Neo_2 -o board-2.bin [--qmi-board-id 255]

bdwlan.elf is /mnt/vendor/persist/bdwlan.elf from the stock ROM (device specific: TX power / calibration limits of this unit family). ath11k board-2.bin
entries are the whole bdwlan.elf file (57,908 bytes for the QCA6390 entries shipped in linux-firmware). The new entry is named
  bus=pci,qmi-chip-id=0,qmi-board-id=<id>,variant=<variant>
and is found when the DT node of the Wi-Fi device has `qcom,calibration-variant = "<variant>"` (without it ath11k falls back to the generic entry).
Layout (drivers/net/wireless/ath/ath11k/core.c): magic "QCA-ATH11K-BOARD\\0" padded to 4, then TLV ies (u32 type, u32 len, data padded to 4):
type 0 = BOARD containing sub-ies type 0 = name, type 1 = data. Existing entries are kept (the same name is replaced)."""
import argparse, hashlib, struct, sys

MAGIC = b"QCA-ATH11K-BOARD\0"


def pad4(n):
    return (n + 3) & ~3


def parse(buf):
    off = pad4(len(MAGIC))
    if not buf.startswith(MAGIC):
        sys.exit("not an ath11k board-2.bin")
    entries = []
    while off + 8 <= len(buf):
        t, l = struct.unpack_from("<II", buf, off)
        v = buf[off + 8:off + 8 + l]
        off += 8 + pad4(l)
        name = data = None
        so = 0
        while so + 8 <= len(v):
            t2, l2 = struct.unpack_from("<II", v, so)
            if t2 == 0:
                name = v[so + 8:so + 8 + l2].decode()
            elif t2 == 1:
                data = v[so + 8:so + 8 + l2]
            so += 8 + pad4(l2)
        entries.append((t, name, data))
    return entries


def ie(t, payload):
    return struct.pack("<II", t, len(payload)) + payload + b"\0" * (pad4(len(payload)) - len(payload))


def build(entries):
    out = MAGIC + b"\0" * (pad4(len(MAGIC)) - len(MAGIC))
    for t, name, data in entries:
        out += ie(t, ie(0, name.encode()) + ie(1, data))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bdwlan", required=True)
    ap.add_argument("--board-2", required=True)
    ap.add_argument("--variant", default="realme_GT_Neo_2")
    ap.add_argument("--qmi-board-id", type=int, default=255)
    ap.add_argument("-o", required=True)
    a = ap.parse_args()
    bd = open(a.bdwlan, "rb").read()
    if bd[:4] != b"\x7fELF":
        sys.exit("bdwlan.elf is not an ELF file")
    entries = parse(open(a.board_2, "rb").read())
    name = f"bus=pci,qmi-chip-id=0,qmi-board-id={a.qmi_board_id},variant={a.variant}"
    entries = [e for e in entries if e[1] != name] + [(0, name, bd)]
    out = build(entries)
    assert [(e[1], e[2]) for e in parse(out)] == [(e[1], e[2]) for e in entries]
    open(a.o, "wb").write(out)
    print(f"{len(entries)} entries, {len(out)} bytes, sha256 {hashlib.sha256(out).hexdigest()}")
    for t, n, d in entries:
        print(f"  {n}  ({len(d)} bytes)")


if __name__ == "__main__":
    main()
