/* rvgrid board support: console, timer, traps and the bits of libc we use. */
#include "rvgrid.h"

/* ---- Console ------------------------------------------------------------- */

void uart_putc(char c)
{
    while (UART_STATUS & 1u)
        ;
    UART_TXDATA = (uint8_t)c;
}

void uart_puts(const char *s)
{
    while (*s)
        uart_putc(*s++);
}

static void put_uint(uint32_t v, unsigned base, int width, char pad)
{
    char buf[12];
    int n = 0;
    do {
        unsigned d = v % base;
        buf[n++] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
        v /= base;
    } while (v);
    while (n < width--)
        uart_putc(pad);
    while (n)
        uart_putc(buf[--n]);
}

/* Supports %c %s %d %u %x %p %% with an optional zero-pad width (%08x). */
int printf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    for (; *fmt; fmt++) {
        if (*fmt != '%') {
            uart_putc(*fmt);
            continue;
        }
        fmt++;
        char pad = ' ';
        int width = 0;
        if (*fmt == '0') {
            pad = '0';
            fmt++;
        }
        while (*fmt >= '0' && *fmt <= '9')
            width = width * 10 + (*fmt++ - '0');
        while (*fmt == 'l')
            fmt++;
        switch (*fmt) {
        case 'c': uart_putc((char)va_arg(ap, int)); break;
        case 's': uart_puts(va_arg(ap, const char *)); break;
        case 'u': put_uint(va_arg(ap, uint32_t), 10, width, pad); break;
        case 'x': put_uint(va_arg(ap, uint32_t), 16, width, pad); break;
        case 'p': uart_puts("0x"); put_uint((uint32_t)va_arg(ap, void *), 16, 8, '0'); break;
        case 'd': {
            int32_t v = va_arg(ap, int32_t);
            if (v < 0) {
                uart_putc('-');
                width--;
            }
            put_uint(v < 0 ? -(uint32_t)v : (uint32_t)v, 10, width, pad);
            break;
        }
        case '%': uart_putc('%'); break;
        default:  uart_putc('?'); break;
        }
    }
    va_end(ap);
    return 0;
}

/* ---- Timer --------------------------------------------------------------- */

uint64_t timer_now(void)
{
    uint32_t hi, lo;
    do {                            /* hi-lo-hi: retry if lo wrapped meanwhile */
        hi = TIMER_MTIME_HI;
        lo = TIMER_MTIME_LO;
    } while (hi != TIMER_MTIME_HI);
    return ((uint64_t)hi << 32) | lo;
}

void timer_set_cmp(uint64_t when)
{
    TIMER_MTIMECMP_HI = 0xFFFFFFFFu;   /* no spurious irq while half-written */
    TIMER_MTIMECMP_LO = (uint32_t)when;
    TIMER_MTIMECMP_HI = (uint32_t)(when >> 32);
}

/* ---- Simulation ---------------------------------------------------------- */

void sim_exit(int code)
{
    SIMCTRL_EXIT = (uint32_t)code;
    for (;;)
        ;
}

/* ---- Traps --------------------------------------------------------------- */

__attribute__((weak)) void irq_handler(uint32_t cause)
{
    printf("\n*** unexpected interrupt %u\n", cause);
    sim_exit(0x200 + (int)cause);
}

__attribute__((weak)) uint32_t trap_handler(uint32_t mcause, uint32_t mepc, uint32_t mtval)
{
    if (mcause & MCAUSE_IRQ) {
        irq_handler(mcause & ~MCAUSE_IRQ);
        return mepc;
    }
    printf("\n*** trap: mcause=%u mepc=0x%08x mtval=0x%08x\n", mcause, mepc, mtval);
    sim_exit(0x100 + (int)mcause);
}

/* ---- libc ---------------------------------------------------------------- */

void *memset(void *dst, int c, size_t n)
{
    uint8_t *d = dst;
    while (n--)
        *d++ = (uint8_t)c;
    return dst;
}

void *memcpy(void *dst, const void *src, size_t n)
{
    uint8_t *d = dst;
    const uint8_t *s = src;
    while (n--)
        *d++ = *s++;
    return dst;
}
