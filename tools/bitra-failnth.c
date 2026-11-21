/* Freestanding aarch64 helper for the deterministic fail-nth sweep (docs/23).
 * usage: bitra-failnth FILE DATA N
 * Opens FILE and the fault-injection files FIRST (so the shell's and the VFS open path's allocations are not counted),
 * arms fail-nth=N for this task only, performs ONE write(FILE, DATA), then prints "ret=<write result> left=<fail-nth>".
 * left=0 means the Nth slab allocation of that write was really hit and failed; left>0 means the write made fewer than N
 * allocations (sweep finished). Needs failslab with task-filter=Y and probability=0 (set by soak.sh). */
static long sc3(long n, long a, long b, long c)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	__asm__ volatile("svc 0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2) : "memory");
	return x0;
}
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
static long slen(const char *s) { long n = 0; while (s[n]) n++; return n; }
static char *itoa(long v, char *end)
{
	int neg = v < 0;
	unsigned long u = neg ? -v : v;
	*--end = 0;
	do { *--end = '0' + u % 10; u /= 10; } while (u);
	if (neg) *--end = '-';
	return end;
}
static void out(const char *s) { sc3(64, 1, (long)s, slen(s)); }

void bitra_main(long *sp)
{
	long argc = sp[0];
	char **argv = (char **)(sp + 1);
	char nb[24], buf[32], *p;
	long fd, fn, mf, ret, n = 0, i, left;

	if (argc < 4) { out("usage: bitra-failnth FILE DATA N\n"); sc3(93, 2, 0, 0); }
	for (i = 0; argv[3][i]; i++) n = n * 10 + argv[3][i] - '0';
	fd = sc4(56, -100, (long)argv[1], 1 /* O_WRONLY */, 0);
	fn = sc4(56, -100, (long)"/proc/self/fail-nth", 2 /* O_RDWR */, 0);
	mf = sc4(56, -100, (long)"/proc/self/make-it-fail", 1, 0);
	if (fd < 0 || fn < 0 || mf < 0) { out("open failed\n"); sc3(93, 3, 0, 0); }
	sc3(64, mf, (long)"1", 1);
	p = itoa(n, nb + sizeof(nb));
	sc3(64, fn, (long)p, slen(p));
	ret = sc3(64, fd, (long)argv[2], slen(argv[2]));
	sc4(67, fn, (long)buf, 31, 0);	/* pread64(fn, buf, 31, 0): remaining count */
	for (i = 0; i < 31 && buf[i] >= '0' && buf[i] <= '9'; i++) ;
	buf[i] = 0;
	left = 0;
	out("ret="); p = itoa(ret, nb + sizeof(nb)); out(p);
	out(" left="); out(buf); out("\n");
	(void)left;
	sc3(93, 0, 0, 0);
}
__asm__(".global _start\n_start:\n\tmov x0, sp\n\tbl bitra_main\n");
