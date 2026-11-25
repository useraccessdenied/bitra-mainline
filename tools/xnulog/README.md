# xnulog: read the HakiOS kernel's log after a reset

The HakiOS kernel mirrors every console character into a 1 MiB ring of RAM at physical 0xf0000000 (loader: `allocate_pages`, kernel:
`hakios_pm_map` / `pm_put` in `osfmk/console/video_console.c`; header "XNUPMLOG", u32 bytes written at +8, u32 size at +12, text from +64).
RAM survives the reset; after the phone is back in Alpine:

    ssh mac "stage --sha256 $(sha256sum xnulog.ko | cut -d' ' -f1) xnulog.ko" < xnulog.ko
    ssh mac "put xnulog.ko /tmp/xnulog.ko"
    ssh mac "sh 'insmod /tmp/xnulog.ko; cat /proc/xnulog > /tmp/xnu.log'"
    ssh mac "get /tmp/xnu.log" > xnu.log ; python3 -c "d=open('xnu.log','rb').read(); n=int.from_bytes(d[8:12],'little'); print(d[64:64+n].decode('latin1'))"

Build: `make -C $MAINLINE_OUT ARCH=arm64 LLVM=1 M=$PWD LOCALVERSION= modules` (module for the running 7.2.0-bitra kernel).
