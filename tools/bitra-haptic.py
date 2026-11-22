#!/usr/bin/env python3
"""Vibrate the phone through the input force-feedback interface (stdlib only; runs on the phone).

  bitra-haptic.py [EVENT_DEV] [PULSES] [MS] [STRENGTH 0-65535]
Defaults: the first input device named like *haptics*, 3 pulses of 500 ms at full strength, 500 ms apart.
Uploads an FF_RUMBLE effect (EVIOCSFF) and plays it with an EV_FF write, like fftest does.
"""
import fcntl, glob, os, struct, sys, time

EVIOCSFF = 0x40304580      # _IOW('E', 0x80, struct ff_effect) on 64-bit (48 bytes)
EVIOCRMFF = 0x40044581     # _IOW('E', 0x81, int)
FF_RUMBLE, EV_FF = 0x50, 0x15


def find_dev():
    for n in sorted(glob.glob("/sys/class/input/event*/device/name")):
        if "haptic" in open(n).read().lower():
            return "/dev/input/" + n.split("/")[4]
    sys.exit("no haptics input device")


def main():
    dev = sys.argv[1] if len(sys.argv) > 1 else find_dev()
    pulses = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    ms = int(sys.argv[3]) if len(sys.argv) > 3 else 500
    strength = int(sys.argv[4]) if len(sys.argv) > 4 else 65535
    fd = os.open(dev, os.O_RDWR)
    # struct ff_effect: type, id, direction, trigger{button,interval}, replay{length,delay}, pad, union{rumble: strong,weak}
    eff = bytearray(struct.pack("HhHHHHHH", FF_RUMBLE, -1, 0, 0, 0, ms, 0, 0) + struct.pack("HH", strength, strength) + b"\0" * 28)
    fcntl.ioctl(fd, EVIOCSFF, eff, True)
    eid = struct.unpack_from("h", eff, 2)[0]
    print(f"{dev}: effect id {eid}, {pulses} x {ms} ms, strength {strength}", flush=True)
    for i in range(pulses):
        os.write(fd, struct.pack("llHHi", 0, 0, EV_FF, eid, 1))
        print(f"pulse {i + 1}", flush=True)
        time.sleep(ms / 1000 + 0.5)
    fcntl.ioctl(fd, EVIOCRMFF, eid)
    os.close(fd)


if __name__ == "__main__":
    main()
