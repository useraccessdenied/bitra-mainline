#!/usr/bin/env python3
"""Fetch aarch64 Alpine packages (+ dependency closure) for the phone's initramfs. Stdlib only.

  python3 scripts/fetch_alpine_pkgs.py iw wpa_supplicant [--branch latest-stable] [--out third_party/alpine]

Resolves dependencies from APKINDEX, downloads the .apk files, verifies each package's control-segment checksum
(`C:` field = Q1 + base64(sha1)) against the index, and extracts the data segment into OUT/root/.
NOT verified: the APKINDEX signature itself (Alpine's public key is not shipped here) - treat as untrusted data;
the files only run in the phone's RAM-only initramfs. Output dir is gitignored.
"""
import argparse, base64, hashlib, io, re, sys, tarfile, urllib.request, zlib
from pathlib import Path

BASE = "https://dl-cdn.alpinelinux.org/alpine/{branch}/{repo}/aarch64/"


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def parse_index(raw):
    tf = tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz")
    text = tf.extractfile("APKINDEX").read().decode()
    pkgs = []
    for stanza in text.strip().split("\n\n"):
        d = {}
        for line in stanza.splitlines():
            if len(line) > 2 and line[1] == ":":
                d[line[0]] = line[2:]
        if "P" in d:
            pkgs.append(d)
    return pkgs


def split_members(data):
    """Split concatenated gzip members; returns list of raw gzip member bytes."""
    out, pos = [], 0
    while pos < len(data):
        d = zlib.decompressobj(wbits=31)
        d.decompress(data[pos:])
        used = len(data) - pos - len(d.unused_data)
        out.append(data[pos:pos + used])
        pos += used
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--branch", default="latest-stable")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "third_party/alpine"))
    a = ap.parse_args()
    out = Path(a.out); (out / "apk").mkdir(parents=True, exist_ok=True)
    pkgs = []
    for repo in ("main", "community"):
        try:
            pkgs += parse_index(get(BASE.format(branch=a.branch, repo=repo) + "APKINDEX.tar.gz"))
        except Exception as e:
            print(f"warning: no {repo} index: {e}", file=sys.stderr)
    by_name, provides = {}, {}
    for p in pkgs:
        by_name.setdefault(p["P"], p)
        provides.setdefault(p["P"], p)
        for tok in p.get("p", "").split():
            provides.setdefault(re.split(r"[=<>~]", tok)[0], p)
    need, order, seen = list(a.roots), [], set()
    while need:
        n = need.pop(0)
        n = re.split(r"[=<>~]", n)[0]
        if n.startswith("!") or n in seen:
            continue
        p = provides.get(n)
        if not p:
            print(f"warning: unresolved dependency {n}", file=sys.stderr); seen.add(n); continue
        if p["P"] in seen:
            seen.add(n); continue
        seen.add(n); seen.add(p["P"]); order.append(p)
        need += p.get("D", "").split()
    root = out / "root"; root.mkdir(exist_ok=True)
    for p in order:
        fn = f"{p['P']}-{p['V']}.apk"
        repo = "main" if p in pkgs[:0] else None
        url = None
        for r in ("main", "community"):
            try:
                data = get(BASE.format(branch=a.branch, repo=r) + fn); url = r; break
            except Exception:
                continue
        if url is None:
            sys.exit(f"cannot download {fn}")
        members = split_members(data)
        ctrl = members[1] if len(members) > 2 else members[0]   # [signature, control, data]
        got = "Q1" + base64.b64encode(hashlib.sha1(ctrl).digest()).decode()
        if got != p["C"]:
            sys.exit(f"checksum mismatch for {fn}: {got} != {p['C']}")
        (out / "apk" / fn).write_bytes(data)
        tf = tarfile.open(fileobj=io.BytesIO(zlib.decompress(members[-1], 31)))
        for m in tf.getmembers():
            if m.name.startswith(".") or "/man/" in m.name or "/doc/" in m.name or m.name.startswith("usr/share/"):
                continue
            try:
                tf.extract(m, root, filter="tar")
            except (tarfile.FilterError, OSError) as e:	# e.g. absolute symlinks (bin/sh -> /usr/bin/busybox): not needed
                print(f"  skipped {m.name}: {type(e).__name__}", file=sys.stderr)
        print(f"ok {fn} ({url}) checksum verified")
    print("extracted to", root)


if __name__ == "__main__":
    main()
