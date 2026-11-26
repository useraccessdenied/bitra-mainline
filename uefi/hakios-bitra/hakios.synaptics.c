/*
 * The touch screen of the realme GT Neo 2 (bitra, SM8250-AC): a Synaptics S3908, TouchComm generation 1, at
 * address 0x4b of the I2C bus of the SoC's serial engine at 0x00a94000 (QUP2 SE5, "qup13": GPIO 36 data, 37 clock),
 * with its reset on GPIO 38 and its interrupt line (low while a message waits) on GPIO 39. As a source of touches for
 * /dev/hakios-touch (sys/hakios.input.h). Only with boot-arg touchscreen=1: every number below belongs to this phone.
 *
 * What is written here comes from the phone itself and from what a Linux driver for the same chip does on it (the
 * device tree of the vendor kernel, and the running mainline kernel: pins and address from its pinmux and I2C
 * bus, the chip's own answers "TouchComm v1, mode 0x01, part s3908PR0-15.0, 8640 x 19200, 10 touch objects"):
 *
 *   power     NOT done here. The chip's two supplies are PM8150C regulators (3.0 V and 1.8 V, through RPMh); whether the
 *             boot loader left them on is what the first run says (the log line "touch: ... answers" or "no answer").
 *   pins      GPIO 36 and 37 are taken from the serial engine and used as plain pins: I2C by hand (as hakios.speaker.c
 *             does it): a pin is pulled low or let go, the bus's pull-ups raise it. GPIO 38 is the chip's reset (low:
 *             reset), GPIO 39 its interrupt line (an input; no interrupt is used: a thread looks at it).
 *   protocol  a command is one write [cmd, length (2 bytes, little endian), payload]; a message, a command's response or
 *             a report, is one read of 64 bytes: [0xa5, code, length (2), payload, 0x5a], a longer payload arriving in
 *             further reads that repeat the marker with code 0x03. Codes up to 0x0f (and 0xff) are statuses, from 0x10 on
 *             report ids (0x10 identify, 0x11 touch).
 *   start     identify (0x02), get application info (0x20: the panel's largest coordinates and the number of touch objects),
 *             get the touch report configuration (0x25: a list of (field, bits) that says how a touch report is laid out
 *             in bits), enable the touch report (0x05, 0x11).
 *   reports   the configuration is a small program: FOREACH_ACTIVE_OBJECT ... FOREACH_END around the fields of one object
 *             (index, classification, x, y, ...), each with its width in bits, the report being a bit stream, least
 *             significant bit first. An object whose classification is not 0 is a finger on the glass.
 *
 * The samples go to hakios_touch_post() as a fraction of the panel (0..65535), and the display shim scales the iPhone's
 * picture to the whole panel, so no offset or crop applies. Boot-arg touch_flip=N: 1 mirrors x, 2 mirrors y, 4 swaps x and y.
 * Boot-arg touch_poll_us=N: look at the interrupt line every N microseconds (default 2000). Boot-arg touch_i2c_us=N: the half
 * period of the I2C clock (default 2, about 200 kHz; the chip takes 400 kHz).
 */
#include <kern/clock.h>
#include <kern/locks.h>
#include <kern/thread.h>
#include <libkern/libkern.h>
#include <mach/mach_types.h>
#include <pexpert/pexpert.h>
#include <sys/hakios.input.h>
#include <sys/systm.h>

#include <sys/errno.h>

extern void loader_log_putc(char c);
extern vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);
extern kern_return_t thread_terminate(thread_t thread);

#define TLMM_PHYS               0x0f100000UL    /* SM8250's pin controller */
#define TLMM_SIZE               0x100000UL
#define GPIO_CFG(n)             (tlmm + 0x1000UL * (n))         /* [1:0] pull, [5:2] function, [8:6] drive, [9] output */
#define GPIO_IO(n)              (tlmm + 0x1000UL * (n) + 4)     /* bit 0 in, bit 1 out */
#define CFG_PULL_UP             3
#define CFG_OUTPUT              (1u << 9)

#define PIN_SDA                 36
#define PIN_SCL                 37
#define PIN_RESET               38
#define PIN_INT                 39
#define I2C_ADDRESS             0x4b

static uint32_t i2c_khz = 400;          /* touch_i2c_khz */
static uint32_t poll_us = 2000;         /* touch_poll_us */
static uint32_t flip;                   /* touch_flip */

static int say(const char *format, ...) __printflike(1, 2);

static int
say(const char *format, ...)
{
	__attribute__((uninitialized)) char line[300];
	va_list list;
	int length;

	va_start(list, format);
	length = vsnprintf(line, sizeof(line), format, list);
	va_end(list);
	for (const char *c = line; *c != 0; c++) {
		loader_log_putc(*c);
	}
	printf("%s", line);
	return length;
}

static inline uint32_t
rd(vm_offset_t address)
{
	return *(volatile uint32_t *)address;
}

static inline void
wr(vm_offset_t address, uint32_t value)
{
	*(volatile uint32_t *)address = value;
}

static void
sleep_ms(uint32_t ms)
{
	delay_for_interval(ms, NSEC_PER_MSEC);
}

/* ---- the supplies (RPMh), the clocks (GCC) and the I2C bus (the serial engine "GENI" at 0xa94000, FIFO mode, polled) ------------- */

/* Image AW: Mu's TLMM protocol writes the pins (raw writes to the pin controller reset the phone); the loader does that before this
 * kernel starts (boot-arg touch_pins=1): GPIO 36/37 to the serial engine's function, GPIO 38 (reset) high, GPIO 39 (interrupt) an input. */
extern lck_mtx_t hakios_rsc_lock;
extern vm_offset_t ml_io_map_wcomb(vm_offset_t phys_addr, vm_size_t size);

#define GCC_PHYS                0x00100000UL
#define GCC_SIZE                0x60000UL
#define SE_PHYS                 0x00a94000UL
#define SE_SIZE                 0x4000UL

static vm_offset_t gcc, se, rsc, cmd_db;

static void
sleep_us(uint32_t us)
{
	delay_for_interval(us, NSEC_PER_USEC);
}

#define CMD_DB_PHYS             0x80860000UL
#define CMD_DB_SIZE             0x20000UL
#define RSC_PHYS                0x18220000UL    /* the application processor's "DRV 2" */
#define RSC_SIZE                0x10000UL
#define TCS(reg)                (rsc + 0xd00 + (reg))           /* command slot set 0, an "active" one */
#define TCS_IRQ_ENABLE          0x00
#define TCS_IRQ_STATUS          0x04
#define TCS_IRQ_CLEAR           0x08
#define TCS_WAIT_FOR_COMPLETION 0x10
#define TCS_CONTROL             0x14
#define TCS_CONTROL_ENABLE      (1u << 16)
#define TCS_CONTROL_TRIGGER     (1u << 24)
#define TCS_STATUS              0x18            /* 0 while busy */
#define TCS_CMD_ENABLE          0x1c
#define TCS_CMD_MSGID(n)        (0x30 + 20 * (n))
#define TCS_CMD_ADDR(n)         (0x34 + 20 * (n))
#define TCS_CMD_DATA(n)         (0x38 + 20 * (n))
#define MSGID_WRITE_4_BYTES     0x10008
#define MSGID_RESPONSE          0x100

#define VRM_VOLTAGE             0               /* a regulator's registers, from its address: millivolts */
#define VRM_ENABLE              4
#define VRM_MODE                8
#define VRM_MODE_LDO_HPM        7

struct cmd_db_slave {
	uint16_t id, header_offset, data_offset, count, version, reserved[3];
};
struct cmd_db_header {
	uint32_t version;
	uint8_t magic[4];
	struct cmd_db_slave slave[8];
	uint32_t checksum, reserved;
	uint8_t data[];
};
struct cmd_db_entry {
	char id[8];
	uint32_t priority[2];
	uint32_t address;
	uint16_t length, offset;
};

/* The RPMh address of a resource by its name in the command database the boot loader left; 0 = none. */
static uint32_t
rpmh_address(const char *name)
{
	const struct cmd_db_header *db = (const struct cmd_db_header *)cmd_db;
	char id[8] = { 0 };

	if (db->magic[0] != 0xdb || db->magic[1] != 0x30 || db->magic[2] != 0x03 || db->magic[3] != 0x0c) {
		printf("touch: no command database (magic %02x %02x %02x %02x)\n", db->magic[0], db->magic[1], db->magic[2],
		    db->magic[3]);
		return 0;
	}
	strlcpy(id, name, sizeof(id));
	for (unsigned s = 0; s < 8; s++) {
		const struct cmd_db_slave *slave = &db->slave[s];
		const struct cmd_db_entry *entry = (const struct cmd_db_entry *)(db->data + slave->header_offset);

		if (slave->id == 0 || slave->header_offset >= CMD_DB_SIZE - 0x1000 || slave->count > 512) {
			continue;
		}
		for (unsigned i = 0; i < slave->count; i++) {
			if (memcmp(entry[i].id, id, sizeof(id)) == 0) {
				return entry[i].address;
			}
		}
	}
	return 0;
}

static bool
rpmh_wait(uint32_t reg, uint32_t mask, uint32_t value, const char *what)
{
	for (int i = 0; i < 2000; i++) {
		if ((rd(TCS(reg)) & mask) == value) {
			return true;
		}
		sleep_us(100);
	}
	printf("touch: RPMh: timeout waiting for %s (register %#x = %#x)\n", what, reg, rd(TCS(reg)));
	return false;
}

/* Send up to three register writes to RPMh and wait until they are done. */
static bool
rpmh_write(const uint32_t *address, const uint32_t *data, unsigned count)
{
	uint32_t irq_enable;
	bool done;

	/* the other drivers that write this slot set take the same lock, so that two requests never mix their address and data words */
	lck_mtx_lock(&hakios_rsc_lock);
	irq_enable = rd(TCS(TCS_IRQ_ENABLE));
	/* the slot set must be idle, and switched off the way the hardware wants it: trigger, then enable */
	for (int i = 0; rd(TCS(TCS_STATUS)) == 0; i++) {
		if (i > 2000) {
			printf("touch: RPMh: the command slots stay busy\n");
			lck_mtx_unlock(&hakios_rsc_lock);
			return false;
		}
		sleep_us(100);
	}
	wr(TCS(TCS_CONTROL), rd(TCS(TCS_CONTROL)) & ~TCS_CONTROL_TRIGGER);
	wr(TCS(TCS_CONTROL), rd(TCS(TCS_CONTROL)) & ~TCS_CONTROL_ENABLE);
	wr(TCS(TCS_IRQ_CLEAR), 1);
	for (unsigned i = 0; i < count; i++) {
		wr(TCS(TCS_CMD_MSGID(i)), MSGID_WRITE_4_BYTES | MSGID_RESPONSE);
		wr(TCS(TCS_CMD_ADDR(i)), address[i]);
		wr(TCS(TCS_CMD_DATA(i)), data[i]);
	}
	wr(TCS(TCS_WAIT_FOR_COMPLETION), (1u << count) - 1);
	wr(TCS(TCS_CMD_ENABLE), (1u << count) - 1);
	wr(TCS(TCS_IRQ_ENABLE), irq_enable | 1);        /* the status bit follows the enable; the interrupt itself stays masked */
	wr(TCS(TCS_CONTROL), TCS_CONTROL_ENABLE);
	wr(TCS(TCS_CONTROL), TCS_CONTROL_ENABLE | TCS_CONTROL_TRIGGER);

	done = rpmh_wait(TCS_IRQ_STATUS, 1, 1, "the request");
	wr(TCS(TCS_CONTROL), rd(TCS(TCS_CONTROL)) & ~TCS_CONTROL_TRIGGER);
	wr(TCS(TCS_CONTROL), rd(TCS(TCS_CONTROL)) & ~TCS_CONTROL_ENABLE);
	wr(TCS(TCS_CMD_ENABLE), 0);
	wr(TCS(TCS_WAIT_FOR_COMPLETION), 0);
	wr(TCS(TCS_IRQ_CLEAR), 1);
	wr(TCS(TCS_IRQ_ENABLE), irq_enable);
	lck_mtx_unlock(&hakios_rsc_lock);
	return done;
}


/* Switch on a regulator of the PM8150C (RPMh: voltage in millivolts, enable, high power mode). */
static bool
supply_on(const char *name, uint32_t millivolts)
{
	uint32_t base = rpmh_address(name);
	uint32_t address[3] = { base + VRM_VOLTAGE, base + VRM_ENABLE, base + VRM_MODE };
	uint32_t data[3] = { millivolts, 1, VRM_MODE_LDO_HPM };

	if (base == 0 || (base >> 16 & 0xf) != 4) {
		say("touch: RPMh: no regulator \"%s\" (address %#x)\n", name, base);
		return false;
	}
	say("touch: RPMh: %s is at %#x; slot status %#x, control %#x\n", name, base, rd(TCS(TCS_STATUS)), rd(TCS(TCS_CONTROL)));
	if (!rpmh_write(address, data, 3)) {
		return false;
	}
	say("touch: %s on (%u mV)\n", name, millivolts);
	return true;
}

/* ---- clocks (GCC) -------------------------------------------------------------------------------- */

#define GCC_PHYS                0x00100000UL
#define GCC_SIZE                0x60000UL
#define GCC_VOTE                (gcc + 0x52008)         /* the application processor's votes */
#define VOTE_QUP1_CORE_2X       (1u << 18)
#define VOTE_QUP1_CORE          (1u << 19)
#define VOTE_QUP1_M_AHB         (1u << 20)
#define VOTE_QUP1_S_AHB         (1u << 21)
#define VOTE_QUP1_SE5           (1u << 27)             /* serial engine 13 is the 6th of the second group */
#define GCC_QUP1_M_AHB_CBCR     (gcc + 0x18004)         /* bit 31: the clock is off */
#define GCC_QUP1_S_AHB_CBCR     (gcc + 0x18008)
#define GCC_QUP1_SE5_CBCR       (gcc + 0x185fc)
#define GCC_QUP1_SE5_CMD        (gcc + 0x18600)         /* bit 0: take the new configuration */
#define GCC_QUP1_SE5_CFG        (gcc + 0x18604)         /* [4:0] 2*divider-1, [10:8] source, [13:12] mode */
#define GCC_QUP1_SE5_DFSR       (gcc + 0x18614)         /* bit 0: the engine chooses among preset rates itself */
#define GCC_QUP1_SE5_PERF_CFG(l) (gcc + 0x1861c + 4 * (l))
#define GCC_QUP1_SE5_PERF_M(l)  (gcc + 0x1865c + 4 * (l))
#define GCC_QUP1_SE5_PERF_N(l)  (gcc + 0x1869c + 4 * (l))
#define CLOCK_OFF               (1u << 31)
#define XO_HZ                   19200000

static uint32_t se_source_hz, se_clock_select;

static uint32_t
rcg_rate(uint32_t cfg, uint32_t m, uint32_t not_n_minus_m)
{
	static const uint32_t parent[8] = { XO_HZ, 600000000, 0, 0, 0, 0, 300000000, 0 };
	uint64_t hz = parent[cfg >> 8 & 7];
	uint32_t divider = cfg & 0x1f, mode = cfg >> 12 & 3;

	if (divider) {
		hz = hz * 2 / (divider + 1);
	}
	if (mode) {
		uint32_t n = (~not_n_minus_m & 0xffff) + (m & 0xffff);

		if (n) {
			hz = hz * (m & 0xffff) / n;
		}
	}
	return (uint32_t)hz;
}

static bool
clocks_on(void)
{
	wr(GCC_VOTE, rd(GCC_VOTE) | VOTE_QUP1_CORE_2X | VOTE_QUP1_CORE | VOTE_QUP1_M_AHB | VOTE_QUP1_S_AHB);
	if (rd(GCC_QUP1_SE5_DFSR) & 1) {
		/* preset rates: the lowest that is at least 4 MHz */
		for (uint32_t level = 0; level < 8; level++) {
			uint32_t hz = rcg_rate(rd(GCC_QUP1_SE5_PERF_CFG(level)), rd(GCC_QUP1_SE5_PERF_M(level)),
			    rd(GCC_QUP1_SE5_PERF_N(level)));

			if (hz >= 4000000 && (se_source_hz == 0 || hz < se_source_hz)) {
				se_source_hz = hz;
				se_clock_select = level;
			}
		}
		if (se_source_hz == 0) {
			printf("touch: no usable preset clock rate\n");
			return false;
		}
	} else {
		/* the crystal, undivided: nothing else has to be running */
		wr(GCC_QUP1_SE5_CFG, (rd(GCC_QUP1_SE5_CFG) & ~0x371fu) | 1);
		wr(GCC_QUP1_SE5_CMD, rd(GCC_QUP1_SE5_CMD) | 1);
		for (int i = 0; i < 500 && (rd(GCC_QUP1_SE5_CMD) & 1); i++) {
			sleep_us(10);
		}
		if (rd(GCC_QUP1_SE5_CMD) & 1) {
			printf("touch: the serial engine's clock does not take its configuration (%#x)\n", rd(GCC_QUP1_SE5_CMD));
			return false;
		}
		se_source_hz = XO_HZ;
		se_clock_select = 0;
	}
	wr(GCC_VOTE, rd(GCC_VOTE) | VOTE_QUP1_SE5);
	/* the clocks are "voted": like Linux, only the engine's own clock is checked (the AHB gates of the wrapper read "off" until used) */
	for (int i = 0; i < 1000; i++) {
		if (!(rd(GCC_QUP1_SE5_CBCR) & CLOCK_OFF)) {
			say("touch: clocks: M_AHB %#x, S_AHB %#x, SE5 %#x\n", rd(GCC_QUP1_M_AHB_CBCR), rd(GCC_QUP1_S_AHB_CBCR),
			    rd(GCC_QUP1_SE5_CBCR));
			return true;
		}
		sleep_us(10);
	}
	say("touch: the engine's clock stays off: %#x %#x %#x\n", rd(GCC_QUP1_M_AHB_CBCR), rd(GCC_QUP1_S_AHB_CBCR),
	    rd(GCC_QUP1_SE5_CBCR));
	return false;
}


#define GENI_FORCE_DEFAULT      (se + 0x020)
#define GENI_OUTPUT_CTRL        (se + 0x024)
#define GENI_CGC_CTRL           (se + 0x028)
#define GENI_STATUS             (se + 0x040)    /* bit 0: a command is running */
#define GENI_SER_M_CLK_CFG      (se + 0x048)    /* bit 0 enable, [15:4] divider */
#define GENI_IF_DISABLE_RO      (se + 0x064)    /* bit 0: no FIFO interface */
#define GENI_FW_REVISION_RO     (se + 0x068)    /* [15:8] protocol: 1 = SPI */
#define GENI_CLK_SEL            (se + 0x07c)
#define SPI_CPHA                (se + 0x224)
#define SPI_LOOPBACK            (se + 0x22c)
#define SPI_CPOL                (se + 0x230)
#define SPI_DEMUX_OUTPUT_INV    (se + 0x24c)
#define SPI_DEMUX_SEL           (se + 0x250)
#define GENI_BYTE_GRAN          (se + 0x254)
#define GENI_DMA_MODE_EN        (se + 0x258)
#define SPI_TRANS_CFG           (se + 0x25c)
#define GENI_TX_PACKING_CFG0    (se + 0x260)
#define GENI_TX_PACKING_CFG1    (se + 0x264)
#define SPI_WORD_LEN            (se + 0x268)
#define SPI_TX_TRANS_LEN        (se + 0x26c)
#define SPI_RX_TRANS_LEN        (se + 0x270)
#define SPI_DELAY_COUNTERS      (se + 0x278)
#define GENI_RX_PACKING_CFG0    (se + 0x284)
#define GENI_RX_PACKING_CFG1    (se + 0x288)
#define GENI_M_CMD0             (se + 0x600)    /* [31:27] operation */
#define GENI_M_CMD_CTRL         (se + 0x604)    /* bit 2 cancel, bit 1 abort */
#define GENI_M_IRQ_STATUS       (se + 0x610)
#define GENI_M_IRQ_EN           (se + 0x614)
#define GENI_M_IRQ_CLEAR        (se + 0x618)
#define GENI_S_IRQ_CLEAR        (se + 0x648)
#define GENI_TX_FIFO            (se + 0x700)
#define GENI_RX_FIFO            (se + 0x780)
#define GENI_TX_FIFO_STATUS     (se + 0x800)    /* [27:0] words */
#define GENI_RX_FIFO_STATUS     (se + 0x804)    /* bit 31 last, [30:28] bytes of the last word, [24:0] words */
#define GENI_TX_WATERMARK       (se + 0x80c)
#define GENI_RX_WATERMARK       (se + 0x810)
#define GENI_RX_RFR_WATERMARK   (se + 0x814)
#define SE_DMA_TX_IRQ_CLR       (se + 0xc44)
#define SE_DMA_RX_IRQ_CLR       (se + 0xd44)
#define SE_GSI_EVENT_EN         (se + 0xe18)
#define SE_IRQ_EN               (se + 0xe1c)
#define SE_HW_PARAM_0           (se + 0xe24)    /* [21:16] FIFO depth in words */
#define SE_DMA_GENERAL_CFG      (se + 0xe30)

#define M_CMD_DONE              (1u << 0)
#define M_CMD_CANCEL            (1u << 4)
#define M_CMD_ABORT             (1u << 5)
#define M_ERRORS                ((1u << 1) | (1u << 2) | (1u << 3) | (1u << 24) | (1u << 25) | (1u << 28) | (1u << 29))
#define SPI_FULL_DUPLEX         (3u << 27)


#define I2C_TX_TRANS_LEN        (se + 0x26c)
#define I2C_RX_TRANS_LEN        (se + 0x270)
#define I2C_SCL_COUNTERS        (se + 0x278)
#define GENI_I2C_WRITE          1u
#define GENI_I2C_READ           2u
#define M_I2C_NACK              (1u << 10)      /* GP IRQ 1 of the I2C protocol (geni-se.h: GP IRQ n is bit 9+n) */
#define M_I2C_ERRORS            ((1u << 1) | (1u << 2) | (1u << 3) | (1u << 10) | (1u << 12) | (1u << 13) | (1u << 24) | (1u << 25) | (1u << 28) | (1u << 29))

static uint32_t fifo_depth;
static uint32_t i2c_errors;

static void
geni_drain(uint8_t *rx, uint32_t length, uint32_t *received)
{
	uint32_t status = rd(GENI_RX_FIFO_STATUS), words = status & 0x01ffffff, bytes = words * 4;

	if (status & 0x80000000u) {
		uint32_t valid = status >> 28 & 7;

		if (valid && valid < 4) {
			bytes -= 4 - valid;
		}
	}
	for (uint32_t i = 0; i < words; i++) {
		uint32_t word = rd(GENI_RX_FIFO);

		for (int j = 0; j < 4 && bytes; j++, bytes--) {
			if (*received < length) {
				if (rx) {
					rx[*received] = (uint8_t)(word >> (8 * j));
				}
				(*received)++;
			}
		}
	}
}

static void
geni_recover(void)
{
	wr(GENI_M_CMD_CTRL, 1u << 2);
	for (int i = 0; i < 2000 && !(rd(GENI_M_IRQ_STATUS) & M_CMD_CANCEL); i++) {
		sleep_us(100);
	}
	if (!(rd(GENI_M_IRQ_STATUS) & M_CMD_CANCEL)) {
		wr(GENI_M_CMD_CTRL, 1u << 1);
		for (int i = 0; i < 2000 && !(rd(GENI_M_IRQ_STATUS) & M_CMD_ABORT); i++) {
			sleep_us(100);
		}
	}
	for (int i = 0; i < 64 && (rd(GENI_RX_FIFO_STATUS) & 0x01ffffff); i++) {
		(void)rd(GENI_RX_FIFO);
	}
	wr(GENI_M_IRQ_CLEAR, 0xffffffff);
}


/* 0 = ready; otherwise why the engine cannot be used. The clock (400 kHz: source 19.2 MHz, divider 2, 24 source clocks per bit) as the Linux i2c-qcom-geni table. */
static const char *
geni_i2c_init(uint32_t khz)
{
	uint32_t proto = rd(GENI_FW_REVISION_RO) >> 8 & 0xff, divider, t_high, t_low, t_cycle;

	say("touch: the engine: firmware revision %#x (protocol %u), FIFO interface %s\n", rd(GENI_FW_REVISION_RO), proto,
	    (rd(GENI_IF_DISABLE_RO) & 1) ? "disabled" : "enabled");
	if (proto != 3) {
		return "the serial engine has no I2C firmware";
	}
	if (rd(GENI_IF_DISABLE_RO) & 1) {
		return "the serial engine's FIFO interface is disabled";
	}
	fifo_depth = rd(SE_HW_PARAM_0) >> 16 & 0x3f;
	if (fifo_depth < 4) {
		return "the serial engine reports no FIFO";
	}
	wr(SE_GSI_EVENT_EN, 0);
	wr(GENI_M_IRQ_CLEAR, 0xffffffff);
	wr(GENI_S_IRQ_CLEAR, 0xffffffff);
	wr(SE_DMA_TX_IRQ_CLR, 0xffffffff);
	wr(SE_DMA_RX_IRQ_CLR, 0xffffffff);
	wr(GENI_CGC_CTRL, rd(GENI_CGC_CTRL) | 0x7f);
	wr(SE_DMA_GENERAL_CFG, rd(SE_DMA_GENERAL_CFG) | 0xf);
	wr(GENI_OUTPUT_CTRL, 0x7f);
	wr(GENI_FORCE_DEFAULT, 1);
	wr(GENI_DMA_MODE_EN, rd(GENI_DMA_MODE_EN) & ~1u);
	wr(GENI_RX_WATERMARK, fifo_depth - 3);
	wr(GENI_RX_RFR_WATERMARK, fifo_depth - 2);
	wr(GENI_TX_WATERMARK, 0);
	wr(SE_IRQ_EN, rd(SE_IRQ_EN) | 0xf);
	wr(GENI_M_IRQ_EN, rd(GENI_M_IRQ_EN) | 0x7fc0007f);
	wr(GENI_TX_PACKING_CFG0, 0x0007f8fe);
	wr(GENI_TX_PACKING_CFG1, 0x000ffefe);
	wr(GENI_RX_PACKING_CFG0, 0x0007f8fe);
	wr(GENI_RX_PACKING_CFG1, 0x000ffefe);
	wr(GENI_BYTE_GRAN, 0);
	if (khz >= 1000) {
		divider = 1; t_high = 3; t_low = 9; t_cycle = 18;
	} else if (khz >= 400) {
		divider = 2; t_high = 5; t_low = 12; t_cycle = 24;
	} else {
		divider = 7; t_high = 10; t_low = 11; t_cycle = 26;
	}
	say("touch: the bus clock: source %u Hz, divider %u -> %u Hz\n", se_source_hz, divider, se_source_hz / divider / t_cycle);
	wr(GENI_CLK_SEL, se_clock_select & 7);
	wr(GENI_SER_M_CLK_CFG, divider << 4 | 1);
	wr(I2C_SCL_COUNTERS, t_high << 20 | t_low << 10 | t_cycle);
	return NULL;
}

/* One transfer on the bus: a write of `length' bytes (data) or a read of `length' bytes (data). False if nobody acknowledged or the engine failed. */
static bool
i2c_xfer(bool read, uint8_t *data, uint32_t length)
{
	uint32_t done = 0, status = 0, words;
	uint64_t deadline;

	for (int i = 0; rd(GENI_STATUS) & 1; i++) {
		if (i > 1000) {
			geni_recover();
			break;
		}
		sleep_us(10);
	}
	wr(GENI_M_IRQ_CLEAR, 0xffffffff);
	if (read) {
		wr(I2C_RX_TRANS_LEN, length);
	} else {
		wr(I2C_TX_TRANS_LEN, length);
	}
	wr(GENI_M_CMD0, (read ? GENI_I2C_READ : GENI_I2C_WRITE) << 27 | (uint32_t)I2C_ADDRESS << 9);
	deadline = mach_absolute_time();
	{
		uint64_t span;

		nanoseconds_to_absolutetime(100ULL * NSEC_PER_MSEC, &span);
		deadline += span;
	}
	words = (length + 3) / 4;
	if (!read) {
		/* the engine takes four bytes to a word, least significant first; the FIFO is as deep as fifo_depth words */
		uint32_t sent = 0;

		while (sent < words) {
			if (rd(GENI_M_IRQ_STATUS) & M_I2C_ERRORS) {
				break;
			}
			if ((rd(GENI_TX_FIFO_STATUS) & 0x0fffffff) < fifo_depth) {
				uint32_t w = 0;

				for (uint32_t j = 0; j < 4 && sent * 4 + j < length; j++) {
					w |= (uint32_t)data[sent * 4 + j] << (8 * j);
				}
				wr(GENI_TX_FIFO, w);
				sent++;
			} else if (mach_absolute_time() > deadline) {
				break;
			}
		}
	}
	for (;;) {
		status = rd(GENI_M_IRQ_STATUS);
		if (read) {
			geni_drain(data, length, &done);
		}
		if (status & (M_CMD_DONE | M_I2C_ERRORS)) {
			break;
		}
		if (mach_absolute_time() > deadline) {
			break;
		}
	}
	if (read) {
		geni_drain(data, length, &done);
	}
	if (!(status & M_CMD_DONE) || (status & M_I2C_ERRORS) || (read && done < length)) {
		if (i2c_errors++ < 12) {
			say("touch: i2c %s of %u bytes failed: status %#x%s, %u bytes in\n", read ? "read" : "write", length, status,
			    (status & M_I2C_NACK) ? " (no acknowledge)" : "", done);
		}
		geni_recover();
		return false;
	}
	wr(GENI_M_IRQ_CLEAR, status);
	return true;
}

static bool
i2c_write(const uint8_t *data, uint32_t length)
{
	return i2c_xfer(false, (uint8_t *)(uintptr_t)data, length);
}

static bool
i2c_read(uint8_t *data, uint32_t length)
{
	return i2c_xfer(true, data, length);
}

/* ---- TouchComm ----------------------------------------------------------------------------------------- */

#define MARKER                  0xa5
#define PADDING                 0x5a
#define HEADER                  4
#define CHUNK                   64              /* one read is at most this long, header included */

#define CMD_IDENTIFY            0x02
#define CMD_ENABLE_REPORT       0x05
#define CMD_GET_APP_INFO        0x20
#define CMD_GET_TOUCH_CONFIG    0x25
#define CMD_SET_TOUCH_CONFIG    0x26

#define STATUS_IDLE             0x00
#define STATUS_OK               0x01
#define STATUS_BUSY             0x02
#define STATUS_CONTINUED        0x03
#define REPORT_IDENTIFY         0x10
#define REPORT_TOUCH            0x11

/* the opcodes of the touch report configuration: the ones that have no width, and the ones that do */
#define T_END                   0
#define T_FOREACH_ACTIVE        1
#define T_FOREACH               2
#define T_FOREACH_END           3
#define T_PAD_TO_BYTE           4
#define T_TIMESTAMP             5
#define T_INDEX                 6
#define T_CLASSIFICATION        7
#define T_X                     8
#define T_Y                     9
#define T_Z                     10
#define T_NUM_ACTIVE            24

#define MAX_OBJECTS             16
#define MAX_MESSAGE             1024
#define MAX_CONFIG              128

static uint8_t rx[CHUNK];
static uint8_t payload[MAX_MESSAGE];
static uint32_t payload_len;
static uint8_t code;
static uint8_t config[MAX_CONFIG];
static uint32_t config_len;
static uint32_t max_x, max_y, max_objects;

struct object {
	uint32_t status, x, y;
};
static struct object objects[MAX_OBJECTS];

/*
 * One whole message: 0 and `code', `payload_len', `payload' set; EPROTO if what came is not a message (the chip is not
 * talking yet); EIO if nobody answered; EMSGSIZE.
 */
static int
recv_message(void)
{
	uint32_t total, copied, remaining;

	if (!i2c_read(rx, CHUNK)) {
		return EIO;
	}
	if (rx[0] != MARKER) {
		return EPROTO;
	}
	code = rx[1];
	payload_len = rx[2] | (uint32_t)rx[3] << 8;
	if (code == STATUS_IDLE || code == STATUS_BUSY || code == STATUS_CONTINUED) {
		payload_len = 0;                /* an idle or busy chip answers with a header and nothing behind it */
		return 0;
	}
	if (payload_len > sizeof(payload)) {
		return EMSGSIZE;
	}
	total = HEADER + payload_len + 1;       /* header, payload, the trailing 0x5a */
	copied = payload_len < CHUNK - HEADER ? payload_len : CHUNK - HEADER;
	memcpy(payload, rx + HEADER, copied);
	if (total <= CHUNK) {
		return rx[total - 1] == PADDING ? 0 : EPROTO;
	}
	/* a continued read: the rest comes in chunks that repeat the marker and carry code 3 */
	remaining = payload_len - copied;
	while (remaining > 0) {
		bool last = remaining <= CHUNK - 3;
		uint32_t chunk = last ? remaining : (remaining - 1 < CHUNK - 3 ? remaining - 1 : CHUNK - 3);
		uint32_t read_len = chunk + 2 + (last ? 1 : 0);

		if (!i2c_read(rx, read_len)) {
			return EIO;
		}
		if (rx[0] != MARKER || rx[1] != STATUS_CONTINUED) {
			return EPROTO;
		}
		memcpy(payload + copied, rx + 2, chunk);
		copied += chunk;
		remaining -= chunk;
		if (last && rx[2 + chunk] != PADDING) {
			return EPROTO;
		}
	}
	return 0;
}

/* A command and its response (in `payload'). 0, or an errno. Reports that arrive meanwhile are dropped. */
static int
exec_command(uint8_t cmd, const uint8_t *data, uint32_t length)
{
	uint8_t buf[MAX_CONFIG + 3];

	if (length + 3 > sizeof(buf)) {
		return EINVAL;
	}
	buf[0] = cmd;
	buf[1] = (uint8_t)length;
	buf[2] = (uint8_t)(length >> 8);
	if (length > 0) {
		memcpy(buf + 3, data, length);
	}
	if (!i2c_write(buf, length + 3)) {
		return EIO;
	}
	for (int tries = 0; tries < 30; tries++) {              /* about 500 ms */
		int e;

		sleep_ms(16);
		e = recv_message();
		if (e == EPROTO) {
			continue;
		}
		if (e != 0) {
			return e;
		}
		if (code == REPORT_IDENTIFY && cmd == CMD_IDENTIFY) {
			return 0;
		}
		if (code >= REPORT_IDENTIFY) {
			continue;                               /* a report, not our response */
		}
		if (code == STATUS_OK) {
			return 0;
		}
		if (code == STATUS_IDLE || code == STATUS_BUSY) {
			continue;
		}
		say("touch: command %02x failed with status %02x\n", cmd, code);
		return EIO;
	}
	return ETIMEDOUT;
}

/* `bits' bits of the report's bit stream from bit `offset' on, least significant bit first */
static uint32_t
get_bits(const uint8_t *buf, uint32_t buf_len, uint32_t offset, uint32_t bits)
{
	uint32_t byte = offset / 8, bit = offset % 8, done = 0, out = 0;

	if (bits == 0 || bits > 32 || (uint64_t)offset + bits > (uint64_t)buf_len * 8) {
		return 0;
	}
	while (done < bits) {
		uint32_t take = 8 - bit < bits - done ? 8 - bit : bits - done;
		uint8_t value = (uint8_t)((buf[byte] >> bit) & (0xffu >> (8 - take)));

		out |= (uint32_t)value << done;
		done += take;
		bit = 0;
		byte++;
	}
	return out;
}

/* Walk the report configuration and unpack the touch report accordingly. 0, or an errno. */
static int
parse_touch_report(void)
{
	uint32_t idx = 0, loop_start = 0, loop_bits = 0, offset = 0, obj = 0, seen = 0, active = 0;
	bool active_only = false, have_active = false, done = false;

	memset(objects, 0, sizeof(objects));
	while (idx < config_len && !done) {
		uint8_t op = config[idx++];
		uint32_t bits, data, i;

		switch (op) {
		case T_END:
			done = true;
			continue;
		case T_FOREACH_ACTIVE:
		case T_FOREACH:
			active_only = op == T_FOREACH_ACTIVE;
			loop_start = idx;
			obj = 0;
			seen = 0;
			loop_bits = 0;
			for (i = idx; i < config_len; i++) {
				if (config[i] == T_FOREACH_END || config[i] == T_END) {
					break;
				}
				if (config[i] == T_PAD_TO_BYTE) {
					continue;
				}
				if (++i < config_len) {
					loop_bits += config[i];
				}
			}
			if (active_only && !have_active && offset + loop_bits > payload_len * 8) {
				/* not enough payload for even one object */
				idx = (i < config_len && config[i] == T_FOREACH_END) ? i + 1 : i;
			}
			continue;
		case T_FOREACH_END:
			if (!active_only) {
				if (++obj < max_objects) {
					idx = loop_start;
				}
			} else if (have_active) {
				if (++seen < active) {
					idx = loop_start;
				}
			} else if (++seen < max_objects && offset + loop_bits <= payload_len * 8) {
				idx = loop_start;
			}
			continue;
		case T_PAD_TO_BYTE:
			offset = (offset + 7) & ~7u;
			continue;
		}
		/* everything else is (opcode, width in bits) */
		if (idx >= config_len) {
			break;
		}
		bits = config[idx++];
		data = get_bits(payload, payload_len, offset, bits);
		offset += bits;
		switch (op) {
		case T_INDEX:
			if (data >= max_objects || data >= MAX_OBJECTS) {
				return ERANGE;
			}
			obj = data;
			break;
		case T_NUM_ACTIVE:
			active = data < max_objects ? data : max_objects;       /* from the chip: never loop more often than there are objects */
			have_active = true;
			if (active == 0) {
				done = true;
			}
			break;
		case T_CLASSIFICATION:
			objects[obj].status = data;
			break;
		case T_X:
			objects[obj].x = data;
			break;
		case T_Y:
			objects[obj].y = data;
			break;
		default:
			break;                          /* time stamps, pressure, widths, gestures: not used */
		}
	}
	return 0;
}

/* a config that gives x and y of each object */
static bool
config_has_coordinates(void)
{
	bool x = false, y = false;

	for (uint32_t i = 0; i < config_len; i++) {
		switch (config[i]) {
		case T_END:
			return x && y;
		case T_FOREACH_ACTIVE:
		case T_FOREACH:
		case T_FOREACH_END:
		case T_PAD_TO_BYTE:
			break;
		default:
			x |= config[i] == T_X;
			y |= config[i] == T_Y;
			i++;                            /* the width */
			break;
		}
	}
	return x && y;
}

static const uint8_t default_config[] = {
	T_FOREACH_ACTIVE,
	T_INDEX, 4, T_CLASSIFICATION, 4, T_X, 16, T_Y, 16, T_Z, 8, 11, 12, 12, 12,
	T_FOREACH_END,
	T_END,
};

static bool
read_touch_config(void)
{
	if (exec_command(CMD_GET_TOUCH_CONFIG, NULL, 0) != 0 || payload_len == 0 || payload_len > sizeof(config)) {
		return false;
	}
	config_len = payload_len;
	memcpy(config, payload, config_len);
	return true;
}

/* The chip identified, asked for its geometry and its report layout, and set to send touch reports. */
static bool
chip_setup(void)
{
	uint8_t report = REPORT_TOUCH;
	int e = exec_command(CMD_IDENTIFY, NULL, 0);

	if (e != 0) {
		say("touch: no answer to identify (error %d)\n", e);
		return false;
	}
	if (payload_len < 18) {
		say("touch: the identify answer is %u bytes\n", payload_len);
		return false;
	}
	say("touch: answers: TouchComm v%u, mode %02x, part %.16s\n", payload[0], payload[1], (const char *)&payload[2]);
	if (payload[1] != 0x01) {
		say("touch: the chip is not in application mode (it would need firmware: not done here)\n");
		return false;
	}
	if (exec_command(CMD_GET_APP_INFO, NULL, 0) != 0 || payload_len < 38) {
		say("touch: no application info\n");
		return false;
	}
	/* the info: 8 x u16 (version, status, sizes ...) = 16 bytes, the 16-byte customer config id, then max x, max y, max objects ... */
	max_x = payload[32] | (uint32_t)payload[33] << 8;
	max_y = payload[34] | (uint32_t)payload[35] << 8;
	max_objects = payload[36] | (uint32_t)payload[37] << 8;
	if (max_objects == 0) {
		max_objects = 10;
	}
	if (max_objects > MAX_OBJECTS) {
		max_objects = MAX_OBJECTS;
	}
	if (max_x == 0 || max_y == 0) {
		say("touch: the chip does not say how large the panel is\n");
		return false;
	}
	say("touch: %u x %u, %u touch objects\n", max_x + 1, max_y + 1, max_objects);
	if (!read_touch_config()) {
		say("touch: no touch report configuration\n");
		return false;
	}
	if (!config_has_coordinates()) {
		say("touch: the report has no coordinates: installing ours\n");
		if (exec_command(CMD_SET_TOUCH_CONFIG, default_config, sizeof(default_config)) != 0 || !read_touch_config() ||
		    !config_has_coordinates()) {
			say("touch: the chip keeps a report layout this driver cannot read\n");
			return false;
		}
	}
	if (exec_command(CMD_ENABLE_REPORT, &report, 1) != 0) {
		say("touch: the touch report could not be enabled\n");
		return false;
	}
	say("touch: report layout (%u bytes):", config_len);
	for (uint32_t i = 0; i < config_len; i++) {
		say(" %u", config[i]);
	}
	say("\n");
	return true;
}

/* ---- the samples --------------------------------------------------------------------------------------- */

static struct {
	bool down;
	uint32_t x, y;
} contact[MAX_OBJECTS];

static void
scale(uint32_t x, uint32_t y, uint32_t *ox, uint32_t *oy)
{
	uint32_t px, py;

	if (flip & 4) {
		uint32_t t = x;

		x = y;
		y = t;
	}
	px = (uint32_t)(((uint64_t)(x > max_x ? max_x : x) * 65535) / max_x);
	py = (uint32_t)(((uint64_t)(y > max_y ? max_y : y) * 65535) / max_y);
	if (flip & 1) {
		px = 65535 - px;
	}
	if (flip & 2) {
		py = 65535 - py;
	}
	*ox = px;
	*oy = py;
}

static void
post_touches(void)
{
	for (uint32_t i = 0; i < max_objects; i++) {
		bool down = objects[i].status != 0;
		uint32_t x, y;

		scale(objects[i].x, objects[i].y, &x, &y);
		if (down && !contact[i].down) {
			hakios_touch_post(HAKIOS_TOUCH_DOWN, i, x, y);
		} else if (down && (x != contact[i].x || y != contact[i].y)) {
			hakios_touch_post(HAKIOS_TOUCH_MOVE, i, x, y);
		} else if (!down && contact[i].down) {
			hakios_touch_post(HAKIOS_TOUCH_UP, i, contact[i].x, contact[i].y);
		}
		if (down) {
			contact[i].x = x;
			contact[i].y = y;
		}
		contact[i].down = down;
	}
}

static void
synaptics_thread(__unused void *argument, __unused wait_result_t wait)
{
	uint64_t reports = 0, bad = 0, last_say = mach_absolute_time(), now;
	uint64_t every;

	nanoseconds_to_absolutetime(10ULL * NSEC_PER_SEC, &every);
	sleep_ms(3000);                         /* the rest of the boot first */
	/* every step is said before it is made: the RAM ring then shows how far a run got */
	say("touch: mapping the serial engine, clocks, RPMh and the command database\n");
	gcc = ml_io_map(GCC_PHYS, GCC_SIZE);
	se = ml_io_map(SE_PHYS, SE_SIZE);
	rsc = ml_io_map(RSC_PHYS, RSC_SIZE);
	cmd_db = ml_io_map_wcomb(CMD_DB_PHYS, CMD_DB_SIZE);
	say("touch: switching on the chip's supplies (RPMh)\n");
	supply_on("ldoc1", 1800);
	supply_on("ldoc11", 3000);
	sleep_ms(50);
	say("touch: the serial engine's clocks\n");
	if (!clocks_on()) {
		say("touch: no clock for the serial engine\n");
		thread_terminate(current_thread());
		return;
	}
	say("touch: initialising the serial engine for I2C\n");
	{
		const char *why = geni_i2c_init(i2c_khz);

		if (why != NULL) {
			say("touch: %s\n", why);
			thread_terminate(current_thread());
			return;
		}
	}
	say("touch: probing the chip at I2C address %02x\n", I2C_ADDRESS);
	sleep_ms(300);                          /* the chip boots after its supplies come up */
	if (!chip_setup()) {
		say("touch: no answer; waiting 1 s and trying once more\n");
		sleep_ms(1000);
		if (!chip_setup()) {
			say("touch: no touch screen (the loader's pin set-up: touch_pins=1?)\n");
			thread_terminate(current_thread());
			return;
		}
	}
	say("touch: running; the samples go to /dev/hakios-touch\n");
	for (;;) {
		{
			int e = recv_message();

			if (e == 0 && code == REPORT_TOUCH) {
				if (parse_touch_report() == 0) {
					post_touches();
					reports++;
				} else {
					bad++;
				}
			} else if (e != 0) {
				bad++;
			}
			delay_for_interval(poll_us, NSEC_PER_USEC);
		}
		now = mach_absolute_time();
		if (now - last_say > every) {
			last_say = now;
			say("touch: %llu reports, %llu bad\n", reports, bad);
		}
	}
}

void
hakios_synaptics_init(void)
{
	uint32_t enabled = 0;
	thread_t thread;

	if (!PE_parse_boot_argn("touchscreen", &enabled, sizeof(enabled)) || !enabled) {
		return;
	}
	PE_parse_boot_argn("touch_flip", &flip, sizeof(flip));
	PE_parse_boot_argn("touch_poll_us", &poll_us, sizeof(poll_us));
	PE_parse_boot_argn("touch_i2c_khz", &i2c_khz, sizeof(i2c_khz));
	if (kernel_thread_start(synaptics_thread, NULL, &thread) == KERN_SUCCESS) {
		thread_deallocate(thread);
	}
}
