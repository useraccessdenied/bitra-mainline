#!/usr/bin/env python3
"""Read-only status of the MPS MP2650 main charger (i2c bus 5, addr 0x5c) plus the battery gauge. Runs on the phone (needs i2c-tools and i2c5 enabled in the DT).

Register layout from the Oplus driver (roms/droidian/kernel/drivers/power/oplus/charger_ic/oplus_mp2650.h). Nothing is written.
  mp2650-status.py [BUS] [ADDR]
"""
import subprocess, sys
from pathlib import Path

BUS = sys.argv[1] if len(sys.argv) > 1 else "5"
ADDR = sys.argv[2] if len(sys.argv) > 2 else "0x5c"


def reg(n):
    r = subprocess.run(["i2cget", "-y", BUS, ADDR, f"0x{n:02x}", "b"], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"i2cget reg 0x{n:02x} failed: {r.stderr.strip()}")
    return int(r.stdout.strip(), 16)


r = {n: reg(n) for n in range(0x0A + 1)}
print("raw:", " ".join(f"{n:02x}={v:02x}" for n, v in r.items()))
print(f"input current limit     : {r[0x00] & 0x7f} x 50 mA = {(r[0x00] & 0x7f) * 50} mA")
print(f"input voltage (VINDPM)  : {r[0x01] * 100} mV")
print(f"charge current          : {r[0x02]} x 50 mA = {r[0x02] * 50} mA")
print(f"termination current     : {(r[0x03] & 0xf) * 100} mA, precharge {(r[0x03] >> 4) * 60} mA")
print(f"float voltage per cell  : {3712.5 + ((r[0x04] >> 1) & 0x3f) * 12.5:.1f} mV (recharge threshold {100 + 100 * (r[0x04] & 1)} mV)")
print(f"charging enabled        : {bool(r[0x08] & 0x10)}   OTG boost enabled: {bool(r[0x08] & 0x20)}   battery FET: {bool(r[0x08] & 0x02)}")
print(f"watchdog timer          : {'disabled' if ((r[0x09] >> 4) & 3) == 0 else 'enabled (%d)' % ((r[0x09] >> 4) & 3)}   charge timer enabled: {bool(r[0x09] & 0x08)}   termination enabled: {bool(r[0x09] & 0x40)}")
B = Path("/sys/class/power_supply/bq28z610-0")
if B.exists():
    g = lambda n: (B / n).read_text().strip() if (B / n).exists() else "?"
    print(f"battery gauge           : {g('status')}, {g('capacity')} %, {int(g('voltage_now')) / 1e6:.3f} V, {int(g('current_now')) / 1000:.0f} mA, {int(g('temp')) / 10:.1f} C, "
          f"full {int(g('charge_full')) / 1000:.0f} / design {int(g('charge_full_design')) / 1000:.0f} mAh, {g('cycle_count')} cycles")
