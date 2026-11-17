/* hello: the first program. Console, a bit of compute, LEDs, exit code. */
#include "rvgrid.h"

static uint32_t fib(uint32_t n)
{
    return n < 2 ? n : fib(n - 1) + fib(n - 2);
}

int main(void)
{
    printf("Hello from RISC-V! tile=%u\n", tile_id());

    uint64_t t0 = timer_now();
    uint32_t f = fib(12);
    uint32_t cycles = (uint32_t)(timer_now() - t0);
    printf("fib(12) = %u in %u cycles\n", f, cycles);

    for (unsigned i = 0; i < 8; i++)
        LEDS_OUT = 1u << i;

    return f == 144 ? 0 : 1;
}
