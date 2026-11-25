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

static vm_offset_t tlmm;
static uint32_t half_us = 2;            /* touch_i2c_us */
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
spin_us(uint32_t us)
{
	uint64_t until;

	nanoseconds_to_absolutetime((uint64_t)us * NSEC_PER_USEC, &until);
	until += mach_absolute_time();
	while (mach_absolute_time() < until) {
	}
}

static void
sleep_ms(uint32_t ms)
{
	delay_for_interval(ms, NSEC_PER_MSEC);
}

/* ---- pins and I2C by hand ---------------------------------------------------------------------------- */

/* A line is pulled low (the pin drives 0) or let go (an input, and the pull-up raises it). */
static void
line(unsigned pin, bool high)
{
	wr(GPIO_IO(pin), 0);
	wr(GPIO_CFG(pin), CFG_PULL_UP | (high ? 0 : CFG_OUTPUT));
}

static bool
level(unsigned pin)
{
	return rd(GPIO_IO(pin)) & 1;
}

/* A push-pull output (the reset pin). */
static void
drive(unsigned pin, bool high)
{
	wr(GPIO_IO(pin), high ? 2 : 0);
	wr(GPIO_CFG(pin), CFG_OUTPUT);
}

static void
half_bit(void)
{
	spin_us(half_us);
}

static void
i2c_start(void)
{
	line(PIN_SDA, true);
	line(PIN_SCL, true);
	half_bit();
	line(PIN_SDA, false);
	half_bit();
	line(PIN_SCL, false);
	half_bit();
}

static void
i2c_stop(void)
{
	line(PIN_SDA, false);
	half_bit();
	line(PIN_SCL, true);
	half_bit();
	line(PIN_SDA, true);
	half_bit();
}

/* One bit out (and the other side's bit in, if we let the data line go): the clock goes up and down once. */
static bool
i2c_bit(bool out)
{
	bool in;

	line(PIN_SDA, out);
	half_bit();
	line(PIN_SCL, true);
	for (unsigned stretched = 0; !level(PIN_SCL) && stretched < 1000; stretched++) {
		half_bit();             /* the chip may hold the clock low until it is ready */
	}
	half_bit();
	in = level(PIN_SDA);
	line(PIN_SCL, false);
	return in;
}

/* True if the byte was acknowledged. */
static bool
i2c_write_byte(uint8_t byte)
{
	for (int bit = 7; bit >= 0; bit--) {
		i2c_bit((byte >> bit) & 1);
	}
	return !i2c_bit(true);
}

static uint8_t
i2c_read_byte(bool more)
{
	uint8_t byte = 0;

	for (int bit = 7; bit >= 0; bit--) {
		byte = (uint8_t)(byte << 1 | i2c_bit(true));
	}
	i2c_bit(!more);                 /* acknowledge all but the last byte */
	return byte;
}

/* A write of `length' bytes to the chip. False if nobody acknowledged. */
static bool
i2c_write(const uint8_t *data, uint32_t length)
{
	bool ok;

	i2c_start();
	ok = i2c_write_byte(I2C_ADDRESS << 1);
	for (uint32_t i = 0; ok && i < length; i++) {
		ok = i2c_write_byte(data[i]);
	}
	i2c_stop();
	return ok;
}

/* A read of `length' bytes from the chip. False if nobody acknowledged the address. */
static bool
i2c_read(uint8_t *data, uint32_t length)
{
	bool ok;

	i2c_start();
	ok = i2c_write_byte(I2C_ADDRESS << 1 | 1);
	for (uint32_t i = 0; ok && i < length; i++) {
		data[i] = i2c_read_byte(i + 1 < length);
	}
	i2c_stop();
	return ok;
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
		say("touch: no answer to identify (error %d; SDA reads %u, SCL %u, INT %u)\n", e, level(PIN_SDA), level(PIN_SCL),
		    level(PIN_INT));
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
	/*
	 * Every step is said before it is made: a pin that the secure side protects resets the phone at the access (image AM: no
	 * line at all reached the log), and the last line in the RAM ring then says which one.
	 */
	say("touch: mapping the pin controller at %lx\n", (unsigned long)TLMM_PHYS);
	tlmm = ml_io_map(TLMM_PHYS, TLMM_SIZE);
	say("touch: mapped; reading the four pins' configuration (read only)\n");
	for (unsigned pin = 36; pin <= 39; pin++) {
		say("touch: gpio%u: reading CFG\n", pin);
		uint32_t cfg = rd(GPIO_CFG(pin));

		say("touch: gpio%u: reading IO\n", pin);
		uint32_t io = rd(GPIO_IO(pin));

		say("touch: gpio%u: function %u, pull %u, %s, reads %u\n", pin, (cfg >> 2) & 15, cfg & 3, (cfg & CFG_OUTPUT) ? "output" : "input", io & 1);
	}
	/*
	 * Image AN: writing the registers of gpio39 (the interrupt line) resets the phone, so nothing is written to it or to the reset line
	 * (gpio38) unless the chip does not answer: the chip drives its interrupt line itself, and the level is read the same.
	 */
	say("touch: gpio%u (the interrupt line) and gpio%u (reset) are not written; reading only\n", PIN_INT, PIN_RESET);
	say("touch: the bus lines: gpio%u IO, then CFG\n", PIN_SDA);
	wr(GPIO_IO(PIN_SDA), 0);
	say("touch: gpio%u IO written\n", PIN_SDA);
	wr(GPIO_CFG(PIN_SDA), CFG_PULL_UP);
	say("touch: gpio%u CFG written; gpio%u IO, then CFG\n", PIN_SDA, PIN_SCL);
	wr(GPIO_IO(PIN_SCL), 0);
	say("touch: gpio%u IO written\n", PIN_SCL);
	wr(GPIO_CFG(PIN_SCL), CFG_PULL_UP);
	say("touch: gpio%u CFG written: the bus is let go\n", PIN_SCL);
	spin_us(50);
	say("touch: SDA reads %u, SCL %u, INT %u; probing the chip at I2C address %02x\n", level(PIN_SDA), level(PIN_SCL),
	    level(PIN_INT), I2C_ADDRESS);
	if (!chip_setup()) {
		/* once more after a reset of the chip, as the Linux driver starts it: reset low 10 ms, then 1 s to come up */
		say("touch: resetting the chip: gpio%u IO low, then CFG\n", PIN_RESET);
		wr(GPIO_IO(PIN_RESET), 0);
		say("touch: gpio%u IO written\n", PIN_RESET);
		wr(GPIO_CFG(PIN_RESET), CFG_OUTPUT);
		say("touch: gpio%u CFG written: reset asserted\n", PIN_RESET);
		sleep_ms(10);
		wr(GPIO_IO(PIN_RESET), 2);
		say("touch: reset released\n");
		sleep_ms(1000);
		if (!chip_setup()) {
			say("touch: no touch screen (are the chip's supplies on?)\n");
			thread_terminate(current_thread());
			return;
		}
	}
	say("touch: running; the samples go to /dev/hakios-touch\n");
	for (;;) {
		if (!level(PIN_INT)) {
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
				delay_for_interval(poll_us, NSEC_PER_USEC);     /* (not a hot loop on a line that stays low) */
			}
		} else {
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
	PE_parse_boot_argn("touch_i2c_us", &half_us, sizeof(half_us));
	if (kernel_thread_start(synaptics_thread, NULL, &thread) == KERN_SUCCESS) {
		thread_deallocate(thread);
	}
}
