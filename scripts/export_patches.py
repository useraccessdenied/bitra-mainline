#!/usr/bin/env python3
"""Export the bitra kernel commits as a patch series. Stdlib only.

  python3 scripts/export_patches.py [--src ../bitra/roms/mainline/linux] [--base b56ee7a86]

Writes patches/series/NNNN-*.patch (git format-patch, oldest first), patches/series/series (order) and patches/BASE
(the upstream commit of github.com/omnipha/linux-qualcomm-sm8250 the series applies to). Apply with `git am patches/series/*.patch`.
The kernel fork (branch `bitra`) is the source of truth; this export only exists so the changes can be read and reviewed in this repo.
"""
import argparse, os, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = Path(os.environ.get("MAINLINE_SRC", ROOT.parent / "android/roms/mainline/linux"))
DEFAULT_BASE = "b56ee7a86"  # omnipha: "sm8250: enable OnePlus focus and built-in panel"


def git(src, *a):
    return subprocess.run(["git", "-C", str(src), *a], check=True, capture_output=True, text=True).stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--base", default=DEFAULT_BASE)
    a = ap.parse_args()
    out = ROOT / "patches/series"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    git(a.src, "format-patch", "-q", "--no-signature", "-o", str(out), f"{a.base}..HEAD")
    names = sorted(p.name for p in out.glob("*.patch"))
    (out / "series").write_text("\n".join(names) + "\n")
    head = git(a.src, "rev-parse", "HEAD").strip()
    (ROOT / "patches/BASE").write_text(f"{git(a.src, 'rev-parse', a.base).strip()}\n# series head at export: {head}\n")
    old = ROOT / "patches/bitra-all.patch"
    if old.exists():
        old.unlink()
    print(f"{len(names)} patches, base {a.base}, head {head[:9]}")


if __name__ == "__main__":
    main()
