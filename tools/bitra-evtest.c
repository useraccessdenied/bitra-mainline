/* bitra-evtest: freestanding aarch64 input event dumper (raw syscalls, kernel uapi headers; no libc).
 *   bitra-evtest /dev/input/eventN [SECONDS]   prints the device name, abs ranges and events (type code value)
 * Built by scripts/build_mainline_boot.py with the AOSP clang. */
#include <linux/types.h>
#include <asm-generic/ioctl.h>

/* linux/input.h drags in libc headers; the few definitions needed are repeated here */
struct input_event { long tv_sec, tv_usec; __u16 type, code; __s32 value; };
struct input_absinfo { __s32 value, minimum, maximum, fuzz, flat, resolution; };
#define EV_SYN 0
#define SYN_REPORT 0
#define ABS_MT_SLOT 0x2f
#define ABS_MT_TOUCH_MAJOR 0x30
#define ABS_MT_POSITION_X 0x35
#define ABS_MT_POSITION_Y 0x36
#define ABS_MT_TRACKING_ID 0x39
#define ABS_MT_PRESSURE 0x3a
#define EVIOCGNAME(len) _IOC(_IOC_READ, 'E', 0x06, len)
#define EVIOCGABS(abs) _IOR('E', 0x40 + (abs), struct input_absinfo)

static long sc4(long n, long a, long b, long c, long d)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	register long x3 __asm__("x3") = d;
	__asm__ volatile("svc 0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3) : "memory");
	return x0;
}
static void wr(const char *s) { long n = 0; while (s[n]) n++; sc4(64, 1, (long)s, n, 0); }
static void wnum(long v)
{
	char b[24]; int i = 23; b[i] = 0;
	if (v < 0) { wr("-"); v = -v; }
	do { b[--i] = '0' + v % 10; v /= 10; } while (v);
	wr(&b[i]);
}
static long atoi_(const char *s) { long v = 0; while (*s >= '0' && *s <= '9') v = v * 10 + *s++ - '0'; return v; }

void bitra_main(long *sp)
{
	int argc = (int)sp[0]; char **argv = (char **)(sp + 1);
	if (argc < 2) { wr("usage: bitra-evtest /dev/input/eventN [secs]\n"); sc4(94, 1, 0, 0, 0); }
	long secs = argc > 2 ? atoi_(argv[2]) : 10;
	long fd = sc4(56, -100, (long)argv[1], 0 /* O_RDONLY */, 0);
	if (fd < 0) { wr("open failed\n"); sc4(94, 1, 0, 0, 0); }
	char name[80] = {0};
	sc4(29, fd, EVIOCGNAME(sizeof(name)), (long)name, 0);
	wr("device: "); wr(name); wr("\n");
	static const struct { int code; const char *n; } axes[] = {
		{ ABS_MT_POSITION_X, "X" }, { ABS_MT_POSITION_Y, "Y" }, { ABS_MT_PRESSURE, "PRESSURE" },
		{ ABS_MT_TOUCH_MAJOR, "MAJOR" }, { ABS_MT_SLOT, "SLOT" }, { ABS_MT_TRACKING_ID, "TRACKING_ID" } };
	for (unsigned i = 0; i < sizeof(axes) / sizeof(axes[0]); i++) {
		struct input_absinfo ai = {};
		if (sc4(29, fd, EVIOCGABS(axes[i].code), (long)&ai, 0) == 0) {
			wr(" abs "); wr(axes[i].n); wr(": min "); wnum(ai.minimum); wr(" max "); wnum(ai.maximum); wr("\n");
		}
	}
	wr("touch the screen now; events (type code value):\n");
	long ts[2]; sc4(113, 1, (long)ts, 0, 0);
	long end = ts[0] + secs, nev = 0;
	struct { int fd; short events, revents; } pfd = { (int)fd, 1, 0 };	/* struct pollfd */
	for (;;) {
		long t[2]; sc4(113, 1, (long)t, 0, 0);
		if (t[0] >= end) break;
		long ptimeout[2] = { 1, 0 };
		pfd.revents = 0;
		long r = sc4(73, (long)&pfd, 1, (long)ptimeout, 0);	/* ppoll */
		if (r <= 0) continue;
		struct input_event ev[16];
		long n = sc4(63, fd, (long)ev, sizeof(ev), 0);
		for (long i = 0; i < n / (long)sizeof(ev[0]); i++) {
			if (ev[i].type == EV_SYN && ev[i].code == SYN_REPORT) { wr("--- sync\n"); continue; }
			wnum(ev[i].type); wr(" "); wnum(ev[i].code); wr(" "); wnum(ev[i].value); wr("\n"); nev++;
		}
	}
	wr("events: "); wnum(nev); wr("\n");
	sc4(94, 0, 0, 0, 0);
}
__asm__(".global _start\n_start:\n\tmov x0, sp\n\tbl bitra_main\n");
