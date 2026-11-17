/*
 * memtest: exercise L1 through every load/store width.
 *
 * Byte and half-word stores reach the SRAM as a 32-bit write with SEL byte
 * enables; loads come back as a full word that the core shifts and sign- or
 * zero-extends. A wrong SEL or lane shows up here as a corrupted neighbour.
 */
#include "rvgrid.h"

#define WORDS 1024
static volatile uint32_t buf[WORDS];
static unsigned errors;

static void check(const char *what, unsigned i, uint32_t got, uint32_t want)
{
    if (got != want) {
        if (errors < 8)
            printf("  %s[%u]: got 0x%08x want 0x%08x\n", what, i, got, want);
        errors++;
    }
}

int main(void)
{
    printf("memtest: %u bytes at %p\n", (unsigned)sizeof(buf), (void *)buf);

    /* 1. Address-in-address, full words. */
    for (unsigned i = 0; i < WORDS; i++)
        buf[i] = (uint32_t)&buf[i] ^ 0xA5A5A5A5u;
    for (unsigned i = 0; i < WORDS; i++)
        check("word", i, buf[i], (uint32_t)&buf[i] ^ 0xA5A5A5A5u);

    /* 2. Walking ones on one word. */
    for (unsigned b = 0; b < 32; b++) {
        buf[0] = 1u << b;
        check("walk", b, buf[0], 1u << b);
    }

    /* 3. Byte stores must not touch the other three bytes. */
    volatile uint8_t *bytes = (volatile uint8_t *)buf;
    for (unsigned i = 0; i < 64; i++)
        buf[i] = 0;
    for (unsigned i = 0; i < 256; i++)
        bytes[i] = (uint8_t)(i * 7 + 1);
    for (unsigned i = 0; i < 256; i++)
        check("byte", i, bytes[i], (uint8_t)(i * 7 + 1));
    check("bytelanes", 0, buf[0], 0x160F0801u);   /* bytes 1, 8, 15, 22 */

    /* 4. Half-word stores, and sign extension on loads. */
    volatile uint16_t *halves = (volatile uint16_t *)buf;
    volatile int16_t *shalves = (volatile int16_t *)buf;
    volatile int8_t *sbytes = (volatile int8_t *)buf;
    halves[0] = 0x8001;
    halves[1] = 0x7FFE;
    check("half", 0, buf[0], 0x7FFE8001u);
    check("lh", 0, (uint32_t)shalves[0], 0xFFFF8001u);
    check("lhu", 0, halves[0], 0x00008001u);
    check("lb", 0, (uint32_t)sbytes[1], 0xFFFFFF80u);
    check("lbu", 0, bytes[1], 0x00000080u);

    printf("memtest: %s (%u errors)\n", errors ? "FAIL" : "PASS", errors);
    return (int)errors;
}
