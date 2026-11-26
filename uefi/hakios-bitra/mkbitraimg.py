#!/usr/bin/env python3
"""Pack Mu-Silicium's bitra UEFI (with the HakiOS loader in its FV) and a HakiOS XNUP payload into a
`fastboot boot` image: kernel = gzip(shim + FD + payload) + DTB, like Mu's own image (header v1).
usage: mkbitraimg.py --payload payload.bin -o out.img   (env MU = Mu-Silicium tree, CLANG = clang bin dir)"""
import argparse, gzip, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MU = os.environ.get('MU', '/var/home/kapil/projects/mu-silicium-src/mu')
CLANG = os.environ.get('CLANG', '/var/home/kapil/projects/bitra/android/roms/lineageos/a16/prebuilts/clang/host/linux-x86/clang-r563880c/bin')
FD_BASE, FD_SIZE = 0x9FC00000, 0x300000
PAYLOAD_BASE = int(os.environ.get('PAYLOAD_BASE', '0xF4000000'), 16)   # must equal PAYLOAD_BASE of the loader (xnuloader/build.sh)
PAYLOAD_MAX = 0x03F00000

ap = argparse.ArgumentParser()
ap.add_argument('--payload', required=True)
ap.add_argument('--mode', default='DEBUG')
ap.add_argument('-o', '--output', required=True)
ap.add_argument('--gz', action='store_true', help='carry the payload gzip-compressed (the loader inflates it): the firmware delivers only ~12.5 MiB of the decompressed boot image intact')
a = ap.parse_args()

fd = open(f'{MU}/Build/bitraPkg/{a.mode}_CLANGPDB/FV/SILICIUM_UEFI.fd', 'rb').read()
assert len(fd) == FD_SIZE
pay = open(a.payload, 'rb').read()
assert pay[:4] == b'XNUP' and len(pay) <= PAYLOAD_MAX
if a.gz:
    import gzip as _gz
    pay = _gz.compress(pay, 9, mtime=0)
pay += b'\0' * (-len(pay) % 16)
with tempfile.TemporaryDirectory() as t:
    env = dict(os.environ, PATH=CLANG + ':' + os.environ['PATH'])
    subprocess.check_call(['clang', '--target=aarch64-linux-gnu', '-c', os.path.join(HERE, 'BootShim-payload.S'),
                           '-o', t + '/s.o', f'-DFD_BASE={FD_BASE:#x}', f'-DFD_SIZE={FD_SIZE:#x}',
                           f'-DPAYLOAD_BASE={PAYLOAD_BASE:#x}', f'-DIMAGE_SIZE={(0x1000 + FD_SIZE + len(pay) + 0xFFF) & ~0xFFF:#x}', f'-DMAILBOX_MAGIC=0x2143525350554e58', f'-DPAYLOAD_SIZE={len(pay):#x}'], env=env)
    subprocess.check_call(['llvm-objcopy', '-O', 'binary', t + '/s.o', t + '/shim.bin'], env=env)
    blob = open(t + '/shim.bin', 'rb').read() + fd + pay
    dtb = open(f'{MU}/Resources/DTBs/bitra.dtb', 'rb').read()
    open(t + '/k', 'wb').write(gzip.compress(blob, 6) + dtb)
    subprocess.check_call([sys.executable, f'{MU}/Resources/Scripts/mkbootimg.py', '--kernel', t + '/k',
                           '--ramdisk', f'{MU}/Resources/ramdisk', '--header_version', '1',
                           # ABL puts the ramdisk at kernel + (ramdisk_addr - kernel_addr); the default 16 MiB gap lands inside a big
                           # payload (it destroyed everything past 12.5 MiB of it), so put the ramdisk 64 MiB above the kernel
                           '--ramdisk_offset', '0x4000000', '-o', a.output])
print(a.output, os.path.getsize(a.output), 'bytes; payload', len(pay))
