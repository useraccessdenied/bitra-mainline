#!/usr/bin/env python3
"""Build the three release images and their SHA-256 hashes (docs/38). Stdlib Python.

  python3 tools/release.py VERSION --rom-zip ROM.zip [--firmware-zip FW.zip] [--skip-rootfs] [--skip-boot]
Output: releases/VERSION/{boot.img, userdata.img (Android sparse), super.img (raw ext4, flashed as is), SHA256SUMS}
  fastboot flash boot boot.img ; fastboot flash userdata userdata.img ; fastboot flash super super.img
userdata.img is small and grows to the partition on first boot (bitra-growfs); super.img carries the proprietary vendor files."""
import argparse, hashlib, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 22), b""):
            h.update(c)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version"); ap.add_argument("--rom-zip", required=True); ap.add_argument("--firmware-zip")
    ap.add_argument("--rootfs-size-mb", type=int, default=1800)
    ap.add_argument("--skip-rootfs", action="store_true"); ap.add_argument("--skip-boot", action="store_true")
    a = ap.parse_args()
    out = ROOT / "releases" / a.version; out.mkdir(parents=True, exist_ok=True)
    rel = ROOT / "releases"
    if not a.skip_boot:
        subprocess.run([PY, str(ROOT / "scripts/build_mainline_boot.py"), f"release-{a.version}", "--release"], check=True)
        shutil.copy2(rel / f"release-{a.version}.img", out / "boot.img")
    if not a.skip_rootfs:
        raw = rel / f"userdata-{a.version}.raw"
        subprocess.run([PY, str(ROOT / "scripts/build_alpine_rootfs.py"), "--release", "--size-mb", str(a.rootfs_size_mb), "--out", str(raw)], check=True)
        subprocess.run(["img2simg", str(raw), str(out / "userdata.img")], check=True)
    cmd = [PY, str(ROOT / "tools/build-super-img.py"), "--rom-zip", a.rom_zip, "-o", str(out / "super.img")]
    if a.firmware_zip:
        cmd += ["--firmware-zip", a.firmware_zip]
    subprocess.run(cmd, check=True)
    names = [n for n in ("boot.img", "userdata.img", "super.img") if (out / n).exists()]
    (out / "SHA256SUMS").write_text("".join(f"{sha(out / n)}  {n}\n" for n in names))
    print((out / "SHA256SUMS").read_text())


main()
