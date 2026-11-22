#!/usr/bin/env python3
"""Extract the DSP firmware sets (ADSP, CDSP, SLPI) from a backup of the phone's `modem` partition (FAT image). Stdlib + 7z.

  python3 tools/extract-dsp-firmware.py [--modem-img PATH] [--out third_party/firmware/qcom/sm8250/realme/bitra] [--dsp adsp,cdsp,slpi]
Each set is name.mdt + name.b00..bNN. The script checks every set against its MDT header (every segment file present with the declared size)
and reports the link address range. The images are relocatable (MDT_RELOCATABLE): the kernel loads them into the reserved region of the device tree
(ADSP 37 MiB at 0x91b00000 on this phone), so the region must be at least the declared span (ADSP 37.0 MiB, CDSP 20.0 MiB, SLPI 21.0 MiB).
Never writes to the backup; 7z reports a harmless "Unexpected end of archive" for this image.
"""
import argparse, os, shutil, struct, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BITRA = Path(os.environ.get("BITRA_REPO", ROOT.parent / "bitra"))
DEFAULT_IMG = BITRA / "backups/20261116-213951/parts/modem.img"


def check(d, name):
    m = (d / f"{name}.mdt").read_bytes()
    phoff = struct.unpack_from("<I", m, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", m, 42)
    bad, lo, hi = 0, None, 0
    for i in range(phnum):
        t, off, va, pa, fsz, msz, fl, al = struct.unpack_from("<8I", m, phoff + i * phentsize)
        f = d / f"{name}.b{i:02d}"
        if fsz and (not f.exists() or f.stat().st_size != fsz):
            bad += 1
        if t == 1 and msz:
            lo = pa if lo is None else min(lo, pa)
            hi = max(hi, pa + msz)
    return phnum, bad, lo, hi


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modem-img", default=str(DEFAULT_IMG))
    ap.add_argument("--out", default=str(ROOT / "third_party/firmware/qcom/sm8250/realme/bitra"))
    ap.add_argument("--dsp", default="adsp,cdsp,slpi")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name in a.dsp.split(","):
            subprocess.run(["7z", "x", "-y", f"-o{tmp}", a.modem_img, f"image/{name}.*"], capture_output=True)
            src = Path(tmp) / "image"
            phnum, bad, lo, hi = check(src, name)
            print(f"{name}: {phnum} program headers, mismatching segment files: {bad}, link range 0x{lo:08x}..0x{hi:08x} ({(hi-lo)/1048576:.1f} MiB)")
            if bad:
                raise SystemExit(f"{name}: inconsistent set, not installing")
            for f in sorted(src.glob(f"{name}.*")):
                shutil.copy2(f, out / f.name)
    print("installed into", out)


if __name__ == "__main__":
    main()
