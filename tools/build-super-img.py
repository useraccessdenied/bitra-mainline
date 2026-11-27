#!/usr/bin/env python3
"""Build super.img: the proprietary vendor files the mainline kernel needs, as a plain read-only ext4 image for the `super` partition.

  python3 tools/build-super-img.py --rom-zip RMX3370export_...zip [--firmware-zip Firmware_F.20_EX01_IN.zip] -o releases/super.img [--sparse]

--rom-zip       the realme full package (IMAGES/vendor.img + IMAGES/odm.img + RADIO/modem.img)
--firmware-zip  optional realme firmware zip (firmware-update/modem.img); its DSP set is used instead of the one in the ROM package
Layout (docs/38; mounted read-only by the initramfs, then bound by the rootfs):
  firmware/qcom/sm8250/realme/bitra/   adsp, cdsp, slpi sets (from modem.img) + a650_zap (GPU, from vendor)
  sensors/config/*.json                all sensor config JSONs (vendor + odm), not pruned
  sensors/sns_reg_config               default registry template
  VERSION  MANIFEST.sha256  PROPRIETARY.txt
Calibration (the sensor registry, Wi-Fi board data) is per unit, lives in the user's own persist partition and is never part of this image.
Needs: simg2img, fsck.erofs (erofs-utils), mke2fs, 7z (modem.img), optional img2simg. Stdlib Python."""
import argparse, hashlib, importlib.util, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FWDIR = "firmware/qcom/sm8250/realme/bitra"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 22), b""):
            h.update(c)
    return h.hexdigest()


def need(tool):
    if not shutil.which(tool):
        sys.exit(f"missing tool: {tool}")


def from_zip(zp, member, dst):
    with zipfile.ZipFile(zp) as z, z.open(member) as s, open(dst, "wb") as d:
        shutil.copyfileobj(s, d, 1 << 22)


def erofs_extract(sparse_img, outdir, tmp, name):
    raw = Path(tmp) / (name + ".raw")
    subprocess.run(["simg2img", str(sparse_img), str(raw)], check=True)
    outdir.mkdir()
    subprocess.run(["fsck.erofs", f"--extract={outdir}", "--no-preserve", str(raw)], check=True, stdout=subprocess.DEVNULL)
    raw.unlink()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom-zip", required=True)
    ap.add_argument("--firmware-zip")
    ap.add_argument("-o", "--out", default=str(ROOT / "releases/super.img"))
    ap.add_argument("--sparse", action="store_true", help="also write OUT.sparse (Android sparse, for fastboot)")
    a = ap.parse_args()
    for t in ("simg2img", "fsck.erofs", "mke2fs", "7z"):
        need(t)
    spec = importlib.util.spec_from_file_location("bitra_firmware", ROOT / "tools/bitra-firmware.py")
    bf = importlib.util.module_from_spec(spec); spec.loader.exec_module(bf)
    with tempfile.TemporaryDirectory(dir=ROOT / "releases") as tmp:
        tmp = Path(tmp); tree = tmp / "tree"; (tree / FWDIR).mkdir(parents=True); (tree / "sensors/config").mkdir(parents=True)
        # DSP sets from the modem partition image
        if a.firmware_zip:
            modem = bf.modem_img_from_zip(a.firmware_zip, tmp); src = a.firmware_zip
        else:
            modem = tmp / "modem.img"; from_zip(a.rom_zip, "RADIO/modem.img", modem); src = a.rom_zip
        stage = tmp / "dsp"
        bf.vendor_from_image(modem, stage, ["adsp", "cdsp", "slpi"])
        for f in (stage / bf.VENDOR_DIR).iterdir():
            shutil.copy2(f, tree / FWDIR / f.name)
        # vendor + odm (erofs, Android sparse)
        for part in ("vendor", "odm"):
            img = tmp / f"{part}.img"; from_zip(a.rom_zip, f"IMAGES/{part}.img", img)
            erofs_extract(img, tmp / f"{part}-x", tmp, part); img.unlink()
        v, o = tmp / "vendor-x", tmp / "odm-x"
        for d in (v / "etc/sensors/config", o / "etc/sensor/config"):
            for f in sorted(d.iterdir()):
                if f.is_file():
                    shutil.copy2(f, tree / "sensors/config" / f.name)
        shutil.copy2(v / "etc/sensors/sns_reg_config", tree / "sensors/sns_reg_config")
        for n in sorted((v / "firmware").glob("a650_zap.*")):
            if n.suffix != ".elf":
                shutil.copy2(n, tree / FWDIR / n.name)
        files = sorted(p for p in tree.rglob("*") if p.is_file())
        (tree / "PROPRIETARY.txt").write_text(
            "Proprietary firmware and configuration files (Qualcomm / realme / OPPO), extracted unmodified from realme RMX3370 stock firmware.\n"
            "Included for the use of this phone only; not covered by the licence of the rest of the project.\n")
        (tree / "VERSION").write_text(f"source: {Path(a.rom_zip).name}\nfirmware: {Path(src).name}\n")
        files = sorted(p for p in tree.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
        (tree / "MANIFEST.sha256").write_text("".join(f"{sha256(p)}  {p.relative_to(tree)}\n" for p in files))
        size = sum(p.stat().st_size for p in tree.rglob("*") if p.is_file())
        mb = int(size * 1.25 / 1048576) + 16
        out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
        out.unlink(missing_ok=True)
        subprocess.run(["mke2fs", "-q", "-t", "ext4", "-b", "4096", "-O", "^has_journal", "-L", "bitra-vendor", "-d", str(tree), str(out), f"{mb}M"], check=True)
        subprocess.run(["e2fsck", "-fn", str(out)], check=True, stdout=subprocess.DEVNULL)
        print(f"{out}  {mb} MiB  {len(files)} files  sha256 {sha256(out)}")
        if a.sparse:
            sp = Path(str(out) + ".sparse"); subprocess.run(["img2simg", str(out), str(sp)], check=True)
            print(f"{sp}  sha256 {sha256(sp)}")


main()
