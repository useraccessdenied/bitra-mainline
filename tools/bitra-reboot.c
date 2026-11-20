/* Freestanding aarch64 helper: reboot(2) with an optional argument ("bootloader", "recovery").
 * busybox reboot cannot pass one. Built by scripts/build_mainline_boot.py with the AOSP clang. */
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

void bitra_main(long *sp)
{
	const char *arg = sp[0] > 1 ? ((char **)(sp + 1))[1] : 0;

	sc4(81, 0, 0, 0, 0);	/* sync */
	if (arg)
		sc4(142, 0xfee1dead, 672274793, 0xA1B2C3D4 /* RESTART2 */, (long)arg);
	else
		sc4(142, 0xfee1dead, 672274793, 0x01234567 /* RESTART */, 0);
	for (;;)
		;
}

__asm__(".global _start\n_start:\n\tmov x0, sp\n\tbl bitra_main\n");
