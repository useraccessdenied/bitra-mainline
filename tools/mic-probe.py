#!/usr/bin/env python3
"""Run on the phone: record 3 s from each VA-macro DMIC input and print the peak level.
Tap/talk at the phone during each step. Usage: mic-probe.py [dmic-number ...]  (default 0-5)
       mic-probe.py adc   -> also probe the WCD938x analog inputs (TX_CODEC_DMA_TX_3 path)"""
import array, subprocess, sys, time

def amixer(*a):
    subprocess.run(["amixer", "-q", "-c", "0", *a], check=True)

def level(path):
    d = open(path, "rb").read()[44:]
    s = array.array("h"); s.frombytes(d[: len(d) // 2 * 2])
    if not s: return 0, 0
    return max(abs(x) for x in s), int((sum(x * x for x in s) / len(s)) ** 0.5)

adc = "adc" in sys.argv[1:]
nums = [int(a) for a in sys.argv[1:] if a.isdigit()] or ([] if adc else range(6))

def rec(label):
    print(f"{label}: make noise now", flush=True)
    time.sleep(1)
    r = subprocess.run(["arecord", "-q", "-D", "hw:0,1", "-f", "S16_LE", "-r", "48000", "-c", "1", "-d", "3", "/tmp/mic.wav"],
                       capture_output=True, text=True)
    if r.returncode:
        print("  arecord failed:", r.stderr.strip()); return
    print("  peak %d rms %d" % level("/tmp/mic.wav"), flush=True)

if adc:
    amixer("cset", "name=MultiMedia2 Mixer TX_CODEC_DMA_TX_3", "1")
    amixer("cset", "name=TX_AIF1_CAP Mixer DEC0", "1")
    amixer("cset", "name=TX DEC0 MUX", "SWR_MIC")
    amixer("cset", "name=TX0 MODE", "ADC_NORMAL"); amixer("cset", "name=TX1 MODE", "ADC_NORMAL")
    amixer("cset", "name=TX2 MODE", "ADC_NORMAL"); amixer("cset", "name=TX3 MODE", "ADC_NORMAL")
    for n, mux in ((1, None), (2, "INP2"), (2, "INP3"), (3, "INP4"), (3, "INP6"), (4, "INP5"), (4, "INP7")):
        for k in range(1, 5):
            amixer("cset", f"name=ADC{k} Switch", "0"); amixer("cset", f"name=ADC{k}_MIXER Switch", "0")
        if mux: amixer("cset", f"name=ADC{n} MUX", mux)
        amixer("cset", f"name=ADC{n}_MIXER Switch", "1"); amixer("cset", f"name=ADC{n} Switch", "1")
        amixer("cset", "name=TX SMIC MUX0", f"ADC{n-1}")
        rec(f"ADC{n} {mux or 'IN1'}")
    sys.exit(0)
amixer("cset", "name=MultiMedia2 Mixer VA_CODEC_DMA_TX_0", "1")
amixer("cset", "name=VA DEC0 MUX", "VA_DMIC")
amixer("cset", "name=VA_AIF1_CAP Mixer DEC0", "1")
amixer("cset", "name=VA_DEC0 Volume", "100")
for n in nums:
    amixer("cset", "name=VA DMIC MUX0", f"DMIC{n}")
    print(f"DMIC{n}: make noise now", flush=True)
    time.sleep(1)
    r = subprocess.run(["arecord", "-q", "-D", "hw:0,1", "-f", "S16_LE", "-r", "48000", "-c", "1", "-d", "3", "/tmp/mic.wav"],
                       capture_output=True, text=True)
    if r.returncode:
        print("  arecord failed:", r.stderr.strip()); continue
    print("  peak %d rms %d" % level("/tmp/mic.wav"), flush=True)
