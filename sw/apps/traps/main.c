/*
 * traps: what happens when software does something wrong.
 *
 *  1. illegal instruction -> exception, handler skips it
 *  2. ecall               -> exception, handler returns a value
 *  3. bad address         -> the decoder answers ERR. VexRiscv_Min can't take
 *                            an access fault, so the load returns 0 and
 *                            TILECTRL records the address.
 */
#include "rvgrid.h"

static volatile uint32_t last_cause;

uint32_t trap_handler(uint32_t mcause, uint32_t mepc, uint32_t mtval)
{
    (void)mtval;
    last_cause = mcause;
    return mepc + 4;                    /* skip the trapping instruction */
}

int main(void)
{
    int fails = 0;

    __asm__ volatile(".word 0x00000000");          /* all-zero = illegal */
    printf("illegal instruction -> mcause %u\n", last_cause);
    fails += last_cause != EXC_ILLEGAL_INSTRUCTION;

    last_cause = 0;
    __asm__ volatile("ecall");
    printf("ecall               -> mcause %u\n", last_cause);
    fails += last_cause != EXC_ECALL_M;

    TILECTRL_BUSERR_COUNT = 0;
    volatile uint32_t *hole = (volatile uint32_t *)0x40000000u;
    uint32_t v = *hole;
    *hole = 0x1234;
    uint32_t count = TILECTRL_BUSERR_COUNT, addr = TILECTRL_BUSERR_ADDR;
    printf("bad address         -> read 0x%08x, %u bus errors, first at 0x%08x\n", v, count, addr);
    fails += !(v == 0 && count == 2 && addr == 0x40000000u);

    printf("traps: %s\n", fails ? "FAIL" : "PASS");
    return fails;
}
