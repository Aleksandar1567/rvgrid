/*
 * timer_irq: periodic machine-timer interrupts.
 *
 * TIMER raises the core's timerInterrupt while mtime >= mtimecmp. The
 * handler acknowledges by moving mtimecmp one period ahead, so the period
 * stays exact no matter how long the handler takes.
 */
#include "rvgrid.h"

#define PERIOD  2000u   /* cycles */
#define TICKS   5u

static volatile uint32_t ticks;
static uint64_t next;

void irq_handler(uint32_t cause)
{
    if (cause != IRQ_M_TIMER)
        sim_exit(0x200 + (int)cause);
    ticks++;
    LEDS_OUT = ticks;
    next += PERIOD;
    timer_set_cmp(next);
}

int main(void)
{
    next = timer_now() + PERIOD;
    timer_set_cmp(next);
    csr_set(mie, MIE_MTIE);
    csr_set(mstatus, MSTATUS_MIE);

    uint32_t spins = 0;
    while (ticks < TICKS)
        spins++;                        /* main keeps running between ticks */

    csr_clear(mstatus, MSTATUS_MIE);
    printf("timer_irq: %u ticks, main loop ran %u times\n", ticks, spins);
    return (ticks == TICKS && spins > 0) ? 0 : 1;
}
