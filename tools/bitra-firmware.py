#!/usr/bin/env python3
"""bitra-firmware.py: get the firmware files the realme GT Neo 2 (bitra) needs, WITHOUT redistributing anything.
Stdlib + `7z` (only for the vendor extraction). Nothing is ever written to the phone, the zip or the backup.

The files fall in two groups (see firmware/manifest.json, which records names, sizes and sha256 only):
  vendor        ADSP, CDSP, SLPI remoteproc sets (name.mdt + name.b00..bNN): taken from the phone's own `modem` partition image,
                which you supply as a vendor firmware zip, a raw modem.img, a partition backup, or by reading it from the running phone.
  linux-firmware  GPU (Adreno 650 sqe/gmu), Wi-Fi (ath11k QCA6390) and Bluetooth (qca htbtfw20/htnv20): copied from a linux-firmware
                checkout or an installed copy (--linux-firmware DIR), or downloaded from git.kernel.org (--download).

  python3 tools/bitra-firmware.py extract --from-zip Firmware_F.20_EX01_IN.zip      # vendor zip with firmware-update/modem.img
  python3 tools/bitra-firmware.py extract --from-modem-img modem.img                # raw FAT image of the modem partition
  python3 tools/bitra-firmware.py extract --from-adb                                # phone in Android with USB debugging (most users)
  python3 tools/bitra-firmware.py extract --from-phone                              # reads the partition through `ssh mac bitra-agent` (read only)
  python3 tools/bitra-firmware.py open [--linux-firmware /usr/lib/firmware | --download]
  python3 tools/bitra-firmware.py all --from-zip ZIP [--linux-firmware DIR]
  python3 tools/bitra-firmware.py verify [--out DIR]                                # compare what is installed with the manifest
  python3 tools/bitra-firmware.py manifest --out DIR                                # maintainers: (re)write the manifest from a known-good tree

Output (default third_party/firmware, gitignored) uses the /lib/firmware layout: copy or symlink it to /lib/firmware on the target.
Vendor files from a different firmware release than the manifest's are installed with a warning (the hashes differ per release); the MDT/segment
consistency check always runs. Whether you may share these files is a licence question: do not publish them (docs/FIRMWARE.md).
"""
import argparse, hashlib, json, lzma, os, shutil, struct, subprocess, sys, tempfile, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "firmware" / "manifest.json"
DEFAULT_OUT = ROOT / "third_party" / "firmware"
VENDOR_DIR = "qcom/sm8250/realme/bitra"
DSPS = ("adsp", "cdsp", "slpi")
LF_URL = "https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/{}"
OPEN_FILES = [  # (path in linux-firmware, what)
    ("qcom/a650_sqe.fw", "Adreno 650 command processor"),
    ("qcom/a650_gmu.bin", "Adreno 650 GMU"),
    ("ath11k/QCA6390/hw2.0/amss.bin", "Wi-Fi QCA6390 firmware"),
    ("ath11k/QCA6390/hw2.0/m3.bin", "Wi-Fi QCA6390 M3"),
    ("ath11k/QCA6390/hw2.0/board-2.bin", "Wi-Fi QCA6390 board data"),
    ("qca/htbtfw20.tlv", "Bluetooth QCA6390 firmware"),
    ("qca/htnv20.bin", "Bluetooth QCA6390 NVM"),
]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_manifest():
    return json.loads(MANIFEST.read_text())


def check_set(d, name):
    """Check an MDT against its segment files; return (program headers, bad files, link lo, link hi)."""
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


def sevenzip():
    for n in ("7z", "7zz", "7za"):
        if shutil.which(n):
            return n
    sys.exit("7z not found (needed to read the FAT modem image): install p7zip / 7zip")


def vendor_from_image(img, out, dsps):
    z = sevenzip()
    man = {e["path"]: e for e in load_manifest()["files"] if e["group"] == "vendor"}
    out_dir = Path(out) / VENDOR_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    differ = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name in dsps:
            # 7z reports a harmless "Unexpected end of archive" for this image, so the check below is what counts
            subprocess.run([z, "x", "-y", f"-o{tmp}", str(img), f"image/{name}.*"], capture_output=True)
            src = Path(tmp) / "image"
            if not (src / f"{name}.mdt").exists():
                sys.exit(f"{name}: not found in {img} (is this the modem partition image?)")
            phnum, bad, lo, hi = check_set(src, name)
            print(f"{name}: {phnum} program headers, mismatching segment files {bad}, link range 0x{lo:08x}..0x{hi:08x} ({(hi-lo)/1048576:.1f} MiB)")
            if bad:
                sys.exit(f"{name}: inconsistent set, not installing")
            for f in sorted(src.glob(f"{name}.*")):
                shutil.copy2(f, out_dir / f.name)
                e = man.get(f"{VENDOR_DIR}/{f.name}")
                if e is None or e["sha256"] != sha256(f):
                    differ += 1
    print(f"vendor files installed into {out_dir}")
    if differ:
        print(f"note: {differ} file(s) differ from the manifest (another firmware release than the one the kernel was tested with); "
              f"the sets are internally consistent, so they should load, but test before relying on them")


def modem_img_from_zip(zp, tmp):
    with zipfile.ZipFile(zp) as z:
        names = [n for n in z.namelist() if n.endswith("modem.img")]
        if not names:
            sys.exit(f"{zp}: no modem.img inside (expected firmware-update/modem.img)")
        dst = Path(tmp) / "modem.img"
        with z.open(names[0]) as s, open(dst, "wb") as d:
            shutil.copyfileobj(s, d)
    return dst


def modem_img_from_phone(tmp):
    dst = Path(tmp) / "modem.img"
    cmd = "dd if=/dev/disk/by-partlabel/modem bs=1M 2>/dev/null"
    print("reading the modem partition from the phone (read only)...")
    with open(dst, "wb") as f:
        r = subprocess.run(["ssh", os.environ.get("BITRA_TESTHOST", "mac"), f"bitra-agent sh '{cmd}'"], stdout=f)
    if r.returncode or dst.stat().st_size < (1 << 20):
        sys.exit("could not read the partition through bitra-agent (use --from-zip or --from-modem-img instead)")
    return dst


ADB_DIRS = ("/vendor/firmware_mnt/image", "/firmware/image", "/vendor/firmware_mnt")


def adb(args, **kw):
    cmd = ["adb"] + (["-s", os.environ["ANDROID_SERIAL"]] if "ANDROID_SERIAL" in os.environ else []) + args
    return subprocess.run(cmd, **kw)


def vendor_from_adb(out, dsps):
    """Stock Android mounts the modem partition read only (usually /vendor/firmware_mnt); pull the DSP sets from it,
    or, with root, read the partition. Nothing is written to the phone."""
    if not shutil.which("adb"):
        sys.exit("adb not found: install Android platform-tools")
    out_dir = Path(out) / VENDOR_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "image"
        stage.mkdir()
        got = False
        for d in ADB_DIRS:
            r = adb(["shell", f"ls {d}/adsp.mdt"], capture_output=True, text=True)
            if r.returncode == 0 and "adsp.mdt" in r.stdout and "No such" not in r.stdout:
                ok = True
                for name in dsps:
                    for f in adb(["shell", f"ls {d}/{name}.*"], capture_output=True, text=True).stdout.split():
                        ok &= adb(["pull", f, str(stage / Path(f).name)], capture_output=True).returncode == 0
                got = ok
                if got:
                    print(f"pulled the DSP sets from {d}")
                    break
        if not got:
            print("no readable firmware mount; trying to read the modem partition as root (adb root or su)...")
            img = Path(tmp) / "modem.img"
            for sh in ("dd if=/dev/block/by-name/modem bs=1M", "su -c 'dd if=/dev/block/by-name/modem bs=1M'"):
                with open(img, "wb") as f:
                    r = adb(["exec-out", sh], stdout=f, stderr=subprocess.DEVNULL)
                if r.returncode == 0 and img.stat().st_size > (1 << 20):
                    return vendor_from_image(img, out, dsps)
            sys.exit("could not read the firmware over adb (not mounted readable, no root); use --from-zip with the vendor firmware zip")
        # same install + checks as the image path
        for name in dsps:
            if not (stage / f"{name}.mdt").exists():
                sys.exit(f"{name}: not found on the phone")
            phnum, bad, lo, hi = check_set(stage, name)
            print(f"{name}: {phnum} program headers, mismatching segment files {bad}, link range 0x{lo:08x}..0x{hi:08x} ({(hi-lo)/1048576:.1f} MiB)")
            if bad:
                sys.exit(f"{name}: inconsistent set, not installing")
            for f in sorted(stage.glob(f"{name}.*")):
                shutil.copy2(f, out_dir / f.name)
        print(f"vendor files installed into {out_dir}; run `verify` to compare with the manifest")


def cmd_extract(a):
    dsps = a.dsp.split(",")
    with tempfile.TemporaryDirectory() as tmp:
        if a.from_adb:
            return vendor_from_adb(a.out, dsps)
        if a.from_zip:
            img = modem_img_from_zip(a.from_zip, tmp)
        elif a.from_modem_img:
            img = Path(a.from_modem_img)
        elif a.from_phone:
            img = modem_img_from_phone(tmp)
        else:
            sys.exit("give one of --from-adb, --from-zip, --from-modem-img, --from-phone")
        vendor_from_image(img, a.out, dsps)


def cmd_open(a):
    man = {e["path"]: e for e in load_manifest()["files"] if e["group"] == "linux-firmware"}
    out = Path(a.out)
    for path, what in OPEN_FILES:
        e = man.get(path)
        dst = out / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = None
        if a.linux_firmware:
            base = Path(a.linux_firmware)
            for cand in (base / path, base / (path + ".zst"), base / (path + ".xz")):
                if cand.exists():
                    src = cand
                    break
        if src is not None and src.suffix == ".zst":
            with tempfile.NamedTemporaryFile(delete=False) as t:
                r = subprocess.run(["zstd", "-dc", str(src)], stdout=t)
            if r.returncode:
                sys.exit(f"zstd failed on {src}")
            shutil.move(t.name, dst)
        elif src is not None and src.suffix == ".xz":
            with lzma.open(src) as s_, open(dst, "wb") as d_:
                shutil.copyfileobj(s_, d_)
        elif src is not None:
            shutil.copy2(src, dst)
        elif a.download:
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(LF_URL.format(path), timeout=120) as r, open(dst, "wb") as f:
                        shutil.copyfileobj(r, f)
                    break
                except OSError as ex:
                    if shutil.which("curl") and subprocess.run(["curl", "-fsSL", "--retry", "3", "-m", "180", "-o", str(dst), LF_URL.format(path)]).returncode == 0:
                        break
                    if attempt == 2:
                        sys.exit(f"{path}: download failed ({ex}); retry, or pass --linux-firmware DIR")
        else:
            sys.exit(f"{path}: not found; pass --linux-firmware DIR or --download")
        got = sha256(dst)
        state = "ok" if e and e["sha256"] == got else "DIFFERS from the manifest (another linux-firmware release)"
        print(f"{path}: {what}: {state}")


def cmd_verify(a):
    out = Path(a.out)
    bad = missing = 0
    for e in load_manifest()["files"]:
        p = out / e["path"]
        if not p.exists():
            missing += 1
            print("missing", e["path"])
        elif sha256(p) != e["sha256"]:
            bad += 1
            print("differs", e["path"])
    n = len(load_manifest()["files"])
    print(f"{n} files in the manifest, {missing} missing, {bad} differ")
    for name in DSPS:
        d = out / VENDOR_DIR
        if (d / f"{name}.mdt").exists():
            phnum, badseg, lo, hi = check_set(d, name)
            print(f"{name}: segment check {'ok' if not badseg else str(badseg) + ' bad'}")
    sys.exit(1 if (missing or bad) else 0)


def cmd_manifest(a):
    out = Path(a.out)
    files = []
    for p in sorted(out.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(out).as_posix()
        if rel.startswith(VENDOR_DIR + "/"):
            group = "vendor"
        elif any(rel == o[0] for o in OPEN_FILES):
            group = "linux-firmware"
        else:
            continue
        files.append({"path": rel, "size": p.stat().st_size, "sha256": sha256(p), "group": group})
    MANIFEST.parent.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "note": "names, sizes and sha256 only; vendor = from the phone's modem partition, linux-firmware = from linux-firmware (uncompressed)",
        "vendor_release": "realme RMX3370 stock firmware as read from the phone (modem backup 20261116-213951)",
        "linux_firmware_release": "Alpine linux-firmware 20260519",
        "files": files}, indent=1) + "\n")
    print(f"{len(files)} files written to {MANIFEST}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("extract", "open", "all", "verify", "manifest"):
        p = sub.add_parser(name)
        p.add_argument("--out", default=str(DEFAULT_OUT))
        if name in ("extract", "all"):
            p.add_argument("--from-zip")
            p.add_argument("--from-modem-img")
            p.add_argument("--from-phone", action="store_true")
            p.add_argument("--from-adb", action="store_true")
            p.add_argument("--dsp", default=",".join(DSPS))
        if name in ("open", "all"):
            p.add_argument("--linux-firmware")
            p.add_argument("--download", action="store_true")
    a = ap.parse_args()
    if a.cmd == "extract":
        cmd_extract(a)
    elif a.cmd == "open":
        cmd_open(a)
    elif a.cmd == "all":
        cmd_extract(a)
        cmd_open(a)
    elif a.cmd == "verify":
        cmd_verify(a)
    else:
        cmd_manifest(a)


if __name__ == "__main__":
    main()
