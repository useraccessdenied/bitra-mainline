#!/usr/bin/env python3
"""NFC poll test through the kernel NFC netlink interface (stdlib only; runs on the phone; no neard needed).

  bitra-nfc.py [SECONDS]      (default 40)
Lists the NFC devices, powers the first one up, starts polling for all protocols and prints every target found
(SENS_RES / SEL_RES / NFCID1 = the tag's identity). Hold a tag or contactless card against the back of the phone.
"""
import os, socket, struct, sys, time

NETLINK_GENERIC, GENL_ID_CTRL, CTRL_CMD_GETFAMILY = 16, 0x10, 3
NLM_F_REQUEST, NLM_F_ACK, NLM_F_DUMP = 1, 4, 0x300
NFC_CMD_GET_DEVICE, NFC_CMD_DEV_UP, NFC_CMD_DEV_DOWN, NFC_CMD_START_POLL, NFC_CMD_STOP_POLL, NFC_CMD_GET_TARGET = 1, 2, 3, 6, 7, 8
NFC_EVENT_TARGETS_FOUND, NFC_EVENT_TARGET_LOST = 9, 12
A_DEV_INDEX, A_DEV_NAME, A_PROTOCOLS, A_TGT_INDEX, A_SENS_RES, A_SEL_RES, A_NFCID1 = 1, 2, 3, 4, 5, 6, 7
ALL_PROTOCOLS = 0xFE   # jewel, mifare, felica, iso14443, nfc-dep, iso14443-b, iso15693


def attr(t, data):
    n = 4 + len(data)
    return struct.pack("HH", n, t) + data + b"\0" * ((4 - n % 4) % 4)


def parse_attrs(buf):
    out, off = {}, 0
    while off + 4 <= len(buf):
        n, t = struct.unpack_from("HH", buf, off)
        if n < 4:
            break
        out[t & 0x7FFF] = buf[off + 4:off + n]
        off += (n + 3) & ~3
    return out


class Genl:
    def __init__(self):
        self.s = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_GENERIC)
        self.s.bind((0, 0))
        self.seq = 1

    def send(self, fam, cmd, attrs=b"", flags=NLM_F_REQUEST | NLM_F_ACK):
        body = struct.pack("BBH", cmd, 1, 0) + attrs
        self.seq += 1
        self.s.send(struct.pack("IHHII", 16 + len(body), fam, flags, self.seq, os.getpid()) + body)

    def recv(self, timeout):
        """all messages that arrive within `timeout` s (replies may span several datagrams; ACKs/errors are dropped)"""
        msgs, end = [], time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                break
            self.s.settimeout(left)
            try:
                data = self.s.recv(65536)
            except socket.timeout:
                break
            off = 0
            while off + 16 <= len(data):
                n, typ, fl, seq, pid = struct.unpack_from("IHHII", data, off)
                if typ == 2:            # NLMSG_ERROR: error 0 is just an ack
                    err = struct.unpack_from("i", data, off + 16)[0]
                    if err:
                        print(f"netlink error {err} ({os.strerror(-err)})", flush=True)
                elif typ != 3:          # NLMSG_DONE
                    msgs.append((typ, data[off + 16:off + n]))
                off += (n + 3) & ~3
            if msgs and timeout > 0.5:
                end = min(end, time.time() + 0.4)
        return msgs

    def family(self, name):
        self.send(GENL_ID_CTRL, CTRL_CMD_GETFAMILY, attr(2, name.encode() + b"\0"), NLM_F_REQUEST)
        for typ, body in self.recv(2):
            if typ == GENL_ID_CTRL:
                a = parse_attrs(body[4:])
                fid = struct.unpack("H", a[1][:2])[0]
                groups = {}
                for g in parse_attrs(a.get(7, b"")).values():
                    ga = parse_attrs(g)
                    groups[ga[1].rstrip(b"\0").decode()] = struct.unpack("I", ga[2][:4])[0]
                return fid, groups
        sys.exit(f"genl family {name} not found (no NFC support in the kernel?)")


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    g = Genl()
    fid, groups = g.family("nfc")
    g.s.setsockopt(270, 1, groups["events"])   # SOL_NETLINK, NETLINK_ADD_MEMBERSHIP
    g.send(fid, NFC_CMD_GET_DEVICE, flags=NLM_F_REQUEST | NLM_F_DUMP)
    devs = []
    for typ, body in g.recv(2):
        if typ == fid:
            a = parse_attrs(body[4:])
            devs.append((struct.unpack("I", a[A_DEV_INDEX][:4])[0], a[A_DEV_NAME].rstrip(b"\0").decode()))
    print("devices:", devs, flush=True)
    if not devs:
        sys.exit("no NFC device")
    idx = devs[0][0]
    ia = attr(A_DEV_INDEX, struct.pack("I", idx))
    g.send(fid, NFC_CMD_DEV_UP, ia, NLM_F_REQUEST)
    g.recv(1)
    print("DEV_UP sent", flush=True)
    g.send(fid, NFC_CMD_START_POLL, ia + attr(A_PROTOCOLS, struct.pack("I", ALL_PROTOCOLS)), NLM_F_REQUEST)
    print(f"polling for {secs} s: hold a tag/card against the back of the phone ...", flush=True)
    end = time.time() + secs
    found = 0
    while time.time() < end:
        for typ, body in g.recv(1):
            if typ != fid:
                continue
            cmd = body[0]
            if cmd == NFC_EVENT_TARGETS_FOUND:
                g.send(fid, NFC_CMD_GET_TARGET, ia, NLM_F_REQUEST | NLM_F_DUMP)
                for t2, b2 in g.recv(2):
                    if t2 == fid:
                        a = parse_attrs(b2[4:])
                        f = lambda k: a[k].hex() if k in a else "-"
                        print(f"TARGET FOUND: sens_res={f(A_SENS_RES)} sel_res={f(A_SEL_RES)} nfcid1={f(A_NFCID1)}", flush=True)
                        found += 1
            elif cmd == NFC_EVENT_TARGET_LOST:
                print("target lost", flush=True)
    g.send(fid, NFC_CMD_STOP_POLL, ia, NLM_F_REQUEST)
    g.recv(1)
    g.send(fid, NFC_CMD_DEV_DOWN, ia, NLM_F_REQUEST)
    g.recv(1)
    print("done, targets found:", found)


if __name__ == "__main__":
    main()
