#!/usr/bin/env python3
"""Extract the Qualcomm Sensor Core registry from a persist partition backup (read-only, via debugfs) for hexagonrpcd.

The SLPI sensor stack only enumerates sensors when /sensors/registry (served by hexagonrpcd) holds the stock registry; an empty registry
gives "No 'accel' sensor available" (docs/32). The registry contains this unit's sensor calibration, so it is device specific: it is
written to the gitignored third_party/ tree and never committed.

  tools/extract-sensor-registry.py [PERSIST_IMG] [OUT_DIR]
"""
import shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BITRA = Path.home() / "projects/bitra"
img = Path(sys.argv[1]) if len(sys.argv) > 1 else BITRA / "backups/20261116-213951/parts/persist.img"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "third_party/sensors/registry"
if not img.exists():
    sys.exit(f"missing {img}")
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)
for rel in ("/sensors/registry/registry", "/sensors/registry/sns_reg_version"):
    r = subprocess.run(["debugfs", "-R", f"rdump {rel} {out}", str(img)], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr)
n = len(list((out / "registry").iterdir()))
print(f"{n} registry entries + sns_reg_version -> {out}")
