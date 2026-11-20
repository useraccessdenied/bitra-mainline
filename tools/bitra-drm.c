/* bitra-drm: freestanding aarch64 DRM test tool (raw syscalls, kernel uapi headers; no libc).
 *   bitra-drm modes                 list the first connector's modes
 *   bitra-drm anim MODE_INDEX SECS [ROWS]  set the mode, animate with page flips, print the measured flip rate
 *                                   ROWS: bar height in rows (default full height); 1 = nearly no drawing
 * Built by scripts/build_mainline_boot.py with the AOSP clang. */
#include <linux/types.h>
#include <drm/drm.h>
#include <drm/drm_mode.h>
#include <drm/drm_fourcc.h>

typedef unsigned long size_t_;
static long sc6(long n, long a, long b, long c, long d, long e, long f)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	register long x3 __asm__("x3") = d;
	register long x4 __asm__("x4") = e;
	register long x5 __asm__("x5") = f;
	__asm__ volatile("svc 0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5) : "memory");
	return x0;
}
#define sys3(n, a, b, c) sc6(n, (long)(a), (long)(b), (long)(c), 0, 0, 0)
static long ioc(int fd, unsigned long req, void *arg) { return sys3(29, fd, req, arg); }
static void wr(const char *s) { long n = 0; while (s[n]) n++; sys3(64, 1, s, n); }
static void wnum(long v)
{
	char b[24]; int i = 23; b[i] = 0;
	if (v < 0) { wr("-"); v = -v; }
	do { b[--i] = '0' + v % 10; v /= 10; } while (v);
	wr(&b[i]);
}
static long atoi_(const char *s) { long v = 0; while (*s >= '0' && *s <= '9') v = v * 10 + *s++ - '0'; return v; }
static void *memset_(void *d, int c, unsigned long n) { unsigned char *p = d; while (n--) *p++ = c; return d; }

static __u32 res_conn[8], res_enc[8], res_crtc[8], res_fb[8];
static struct drm_mode_modeinfo modes[16];
static __u32 conn_enc[8], conn_props[32]; static __u64 conn_propv[32];

struct buf { __u32 handle, fb, pitch; __u64 size; __u32 *map; int lastx; };

static int open_card(void)
{
	long fd = sys3(56, -100, "/dev/dri/card0", 2 /* O_RDWR */);
	return (int)fd;
}

static int get_conn(int fd, struct drm_mode_get_connector *c, struct drm_mode_card_res *r)
{
	memset_(r, 0, sizeof(*r));
	r->connector_id_ptr = (__u64)res_conn; r->count_connectors = 8;
	r->crtc_id_ptr = (__u64)res_crtc; r->count_crtcs = 8;
	r->encoder_id_ptr = (__u64)res_enc; r->count_encoders = 8;
	r->fb_id_ptr = (__u64)res_fb; r->count_fbs = 0;
	if (ioc(fd, DRM_IOCTL_MODE_GETRESOURCES, r) < 0) return -1;
	memset_(c, 0, sizeof(*c));
	c->connector_id = res_conn[0];
	c->modes_ptr = (__u64)modes; c->count_modes = 16;
	c->encoders_ptr = (__u64)conn_enc; c->count_encoders = 8;
	c->props_ptr = (__u64)conn_props; c->prop_values_ptr = (__u64)conn_propv; c->count_props = 32;
	if (ioc(fd, DRM_IOCTL_MODE_GETCONNECTOR, c) < 0) return -2;
	return 0;
}

static int make_buf(int fd, struct buf *b, int w, int h)
{
	struct drm_mode_create_dumb cd = { .width = w, .height = h, .bpp = 32 };
	struct drm_mode_map_dumb md = {};
	struct drm_mode_fb_cmd2 f = {};
	if (ioc(fd, DRM_IOCTL_MODE_CREATE_DUMB, &cd) < 0) return -1;
	b->handle = cd.handle; b->pitch = cd.pitch; b->size = cd.size;
	f.width = w; f.height = h; f.pixel_format = DRM_FORMAT_XRGB8888;
	f.handles[0] = cd.handle; f.pitches[0] = cd.pitch;
	if (ioc(fd, DRM_IOCTL_MODE_ADDFB2, &f) < 0) return -2;
	b->fb = f.fb_id;
	md.handle = cd.handle;
	if (ioc(fd, DRM_IOCTL_MODE_MAP_DUMB, &md) < 0) return -3;
	long m = sc6(222, 0, cd.size, 3 /* RW */, 1 /* SHARED */, fd, md.offset);
	if (m < 0 && m > -4096) return -4;
	b->map = (__u32 *)m; b->lastx = -1;
	return 0;
}

static void paint_bg(struct buf *b, int w, int h)
{
	/* vertical colour bands + a thin white frame line so geometry is visible */
	for (int y = 0; y < h; y++) {
		__u32 *row = (__u32 *)((char *)b->map + (unsigned long)y * b->pitch);
		__u32 c = (y < h / 3) ? 0x00200000 : (y < 2 * h / 3) ? 0x00002000 : 0x00000020;
		for (int x = 0; x < w; x++) row[x] = c;
	}
}

static int bar_rows = 0;
static void bar(struct buf *b, int w, int h, int x, __u32 col)
{
	for (int y = 0; y < (bar_rows ? bar_rows : h); y++) {
		__u32 *row = (__u32 *)((char *)b->map + (unsigned long)y * b->pitch);
		__u32 c = col ? col : ((y < h / 3) ? 0x00200000 : (y < 2 * h / 3) ? 0x00002000 : 0x00000020);
		for (int i = 0; i < 48 && x + i < w; i++) row[x + i] = c;
	}
}

static long now_us(void)
{
	long ts[2];
	sys3(113, 1 /* CLOCK_MONOTONIC */, ts, 0);
	return ts[0] * 1000000L + ts[1] / 1000;
}

void bitra_main(long *sp)
{
	int argc = (int)sp[0]; char **argv = (char **)(sp + 1);
	struct drm_mode_card_res r; struct drm_mode_get_connector c;
	int fd = open_card();
	if (fd < 0) { wr("open /dev/dri/card0 failed\n"); sys3(94, 1, 0, 0); }
	if (get_conn(fd, &c, &r) < 0) { wr("getconnector failed\n"); sys3(94, 1, 0, 0); }
	if (argc < 2 || argv[1][0] == 'm') {
		for (unsigned i = 0; i < c.count_modes; i++) {
			wnum(i); wr(": "); wnum(modes[i].hdisplay); wr("x"); wnum(modes[i].vdisplay); wr(" @");
			wnum(modes[i].vrefresh); wr(" clock="); wnum(modes[i].clock); wr(" htotal="); wnum(modes[i].htotal);
			wr(" vtotal="); wnum(modes[i].vtotal); wr(modes[i].type & 8 ? " [preferred]" : ""); wr("\n");
		}
		sys3(94, 0, 0, 0);
	}
	bar_rows = argc > 4 ? (int)atoi_(argv[4]) : 0;
	int mi = argc > 2 ? (int)atoi_(argv[2]) : 0; long secs = argc > 3 ? atoi_(argv[3]) : 5;
	if (mi >= (int)c.count_modes) { wr("bad mode index\n"); sys3(94, 1, 0, 0); }
	struct drm_mode_get_encoder e = { .encoder_id = c.encoder_id ? c.encoder_id : conn_enc[0] };
	ioc(fd, DRM_IOCTL_MODE_GETENCODER, &e);
	__u32 crtc = e.crtc_id ? e.crtc_id : res_crtc[0];
	int w = modes[mi].hdisplay, h = modes[mi].vdisplay;
	struct buf bufs[2];
	ioc(fd, DRM_IOCTL_SET_MASTER, 0);
	for (int i = 0; i < 2; i++) {
		int rc = make_buf(fd, &bufs[i], w, h);
		if (rc < 0) { wr("make_buf failed rc="); wnum(rc); wr("\n"); sys3(94, 1, 0, 0); }
		paint_bg(&bufs[i], w, h);
	}
	struct drm_mode_crtc sc = { .crtc_id = crtc, .fb_id = bufs[0].fb, .set_connectors_ptr = (__u64)&c.connector_id,
				    .count_connectors = 1, .mode_valid = 1, .mode = modes[mi] };
	if (ioc(fd, DRM_IOCTL_MODE_SETCRTC, &sc) < 0) { wr("SETCRTC failed (master?)\n"); sys3(94, 1, 0, 0); }
	wr("mode "); wnum(mi); wr(" set: "); wnum(modes[mi].hdisplay); wr("x"); wnum(modes[mi].vdisplay); wr(" @");
	wnum(modes[mi].vrefresh); wr(" Hz, animating "); wnum(secs); wr(" s\n");

	if (argc > 5 && argv[5][0] == 'v') {	/* vblank-rate probe: bitra-drm anim MODE SECS ROWS v */
		long tv0 = now_us(), tvend = tv0 + secs * 1000000L, nv = 0, first = 0, last = 0;
		while (now_us() < tvend) {
			union drm_wait_vblank vbl = {};
			vbl.request.type = _DRM_VBLANK_RELATIVE;
			vbl.request.sequence = 1;
			if (ioc(fd, DRM_IOCTL_WAIT_VBLANK, &vbl) < 0) { wr("WAIT_VBLANK failed\n"); break; }
			long t = (long)vbl.reply.tval_sec * 1000000L + vbl.reply.tval_usec;
			if (!first) first = t; last = t; nv++;
		}
		wr("vblanks="); wnum(nv);
		if (nv > 1 && last > first) { wr(" vblank_fps_x10="); wnum((nv - 1) * 10000000L / (last - first)); }
		wr("\n");
		sys3(94, 0, 0, 0);
	}
	long t0 = now_us(), tend = t0 + secs * 1000000L, first_ev = 0, last_ev = 0; long flips = 0; int cur = 1; int x = 0;
	char evbuf[256];
	while (now_us() < tend) {
		struct buf *b = &bufs[cur];
		if (b->lastx >= 0) bar(b, w, h, b->lastx, 0);
		bar(b, w, h, x, 0x00ffffff); b->lastx = x; x = (x + 14) % (w - 48);
		struct drm_mode_crtc_page_flip pf = { .crtc_id = crtc, .fb_id = b->fb, .flags = DRM_MODE_PAGE_FLIP_EVENT };
		if (ioc(fd, DRM_IOCTL_MODE_PAGE_FLIP, &pf) < 0) { wr("PAGE_FLIP failed\n"); break; }
		long n = sys3(63, fd, evbuf, sizeof(evbuf));	/* wait for the flip-complete event */
		if (n >= (long)sizeof(struct drm_event_vblank)) {
			struct drm_event_vblank *ev = (void *)evbuf;
			long t = (long)ev->tv_sec * 1000000L + ev->tv_usec;
			if (!first_ev) first_ev = t; last_ev = t; flips++;
		}
		cur ^= 1;
	}
	wr("flips="); wnum(flips);
	if (flips > 1 && last_ev > first_ev) { wr(" measured_fps_x10="); wnum((flips - 1) * 10000000L / (last_ev - first_ev)); }
	wr("\ndone\n");
	sys3(94, 0, 0, 0);
}
__asm__(".global _start\n_start:\n\tmov x0, sp\n\tbl bitra_main\n");
