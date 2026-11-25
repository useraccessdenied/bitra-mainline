// SPDX-License-Identifier: GPL-2.0
/*
 * xnulog: read back the log the HakiOS (XNU) kernel leaves in RAM before a reset.
 * insmod xnulog.ko [pa=0xf0000000] [size=0x100000]; `cat /proc/xnulog > log.bin` reads, `echo > /proc/xnulog` clears.
 * Maps the range with memremap(); read only. Debug tool for bitra-mainline docs/34.
 */
#include <linux/module.h>
#include <linux/io.h>
#include <linux/proc_fs.h>
#include <linux/uaccess.h>

static unsigned long long pa = 0xf0000000ULL;
module_param(pa, ullong, 0444);
static unsigned long size = 0x800000;
module_param(size, ulong, 0444);
static void *map;
static struct proc_dir_entry *ent;

static ssize_t xl_read(struct file *f, char __user *buf, size_t n, loff_t *pos)
{
	if (*pos >= size)
		return 0;
	if (n > size - *pos)
		n = size - *pos;
	if (copy_to_user(buf, map + *pos, n))
		return -EFAULT;
	*pos += n;
	return n;
}

/* any write clears the whole ring: done before each HakiOS run, so that what is read after it can only be that run's */
static ssize_t xl_write(struct file *f, const char __user *buf, size_t n, loff_t *pos)
{
	memset(map, 0, size);
	return n;
}

static const struct proc_ops xl_ops = { .proc_read = xl_read, .proc_write = xl_write, .proc_lseek = default_llseek };

static int __init xl_init(void)
{
	map = memremap(pa, size, MEMREMAP_WB);
	if (!map)
		return -ENOMEM;
	ent = proc_create("xnulog", 0600, NULL, &xl_ops);
	if (!ent) {
		memunmap(map);
		return -ENOMEM;
	}
	return 0;
}

static void __exit xl_exit(void)
{
	proc_remove(ent);
	memunmap(map);
}

module_init(xl_init);
module_exit(xl_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("read the XNU post-mortem log ring from RAM");
