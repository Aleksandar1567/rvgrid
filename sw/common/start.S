/*
 * Reset entry and trap entry for every rvgrid program.
 *
 * The core starts at the reset vector (L1_BASE) in machine mode with
 * interrupts off and every register undefined. Before C can run we need:
 *   x1..x31 - zeroed. The register file has no reset, so its power-up
 *         garbage would otherwise end up on the stack the first time a
 *         function saves a callee-saved register. Harmless for the program,
 *         but it makes two runs (or two lockstep cores) differ in memory.
 *   gp  - global pointer, so the linker can relax small-data accesses
 *   sp  - a stack (top of L1, see link.ld)
 *   bss - zeroed, because C promises zero-initialised globals
 *   mtvec - where traps (exceptions and interrupts) jump to
 */
    .section .text.start, "ax"
    .globl _start
_start:
    li      x1, 0
    li      x2, 0
    li      x3, 0
    li      x4, 0
    li      x5, 0
    li      x6, 0
    li      x7, 0
    li      x8, 0
    li      x9, 0
    li      x10, 0
    li      x11, 0
    li      x12, 0
    li      x13, 0
    li      x14, 0
    li      x15, 0
    li      x16, 0
    li      x17, 0
    li      x18, 0
    li      x19, 0
    li      x20, 0
    li      x21, 0
    li      x22, 0
    li      x23, 0
    li      x24, 0
    li      x25, 0
    li      x26, 0
    li      x27, 0
    li      x28, 0
    li      x29, 0
    li      x30, 0
    li      x31, 0

    .option push
    .option norelax
    la      gp, __global_pointer$
    .option pop
    la      sp, __stack_top

    la      t0, __bss_start
    la      t1, __bss_end
1:  bgeu    t0, t1, 2f
    sw      zero, 0(t0)
    addi    t0, t0, 4
    j       1b
2:
    la      t0, trap_entry
    csrw    mtvec, t0

    call    main
    tail    sim_exit            /* a0 = main's return value */

/*
 * Trap entry (mtvec, direct mode). Saves the caller-saved registers, calls
 *     uint32_t trap_handler(uint32_t mcause, uint32_t mepc, uint32_t mtval)
 * and resumes at the address it returns (mepc to retry/return, mepc+4 to
 * skip the faulting instruction).
 */
    .text
    .align  2
    .globl  trap_entry
trap_entry:
    addi    sp, sp, -64
    sw      ra,  0(sp)
    sw      t0,  4(sp)
    sw      t1,  8(sp)
    sw      t2, 12(sp)
    sw      a0, 16(sp)
    sw      a1, 20(sp)
    sw      a2, 24(sp)
    sw      a3, 28(sp)
    sw      a4, 32(sp)
    sw      a5, 36(sp)
    sw      a6, 40(sp)
    sw      a7, 44(sp)
    sw      t3, 48(sp)
    sw      t4, 52(sp)
    sw      t5, 56(sp)
    sw      t6, 60(sp)

    csrr    a0, mcause
    csrr    a1, mepc
    csrr    a2, mtval
    call    trap_handler
    csrw    mepc, a0

    lw      ra,  0(sp)
    lw      t0,  4(sp)
    lw      t1,  8(sp)
    lw      t2, 12(sp)
    lw      a0, 16(sp)
    lw      a1, 20(sp)
    lw      a2, 24(sp)
    lw      a3, 28(sp)
    lw      a4, 32(sp)
    lw      a5, 36(sp)
    lw      a6, 40(sp)
    lw      a7, 44(sp)
    lw      t3, 48(sp)
    lw      t4, 52(sp)
    lw      t5, 56(sp)
    lw      t6, 60(sp)
    addi    sp, sp, 64
    mret
