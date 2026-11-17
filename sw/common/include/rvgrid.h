/*
 * rvgrid board support: everything a program needs besides soc.h.
 *
 * soc.h (generated from rvgrid/config.py) has the addresses and registers;
 * this file adds the few functions that make them pleasant to use.
 */
#pragma once

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>

#include "soc.h"

/* ---- CSR access ---------------------------------------------------------- */
#define csr_read(csr)        ({ uint32_t __v; __asm__ volatile("csrr %0, " #csr : "=r"(__v)); __v; })
#define csr_write(csr, val)  __asm__ volatile("csrw " #csr ", %0" :: "rK"(val))
#define csr_set(csr, bits)   __asm__ volatile("csrs " #csr ", %0" :: "rK"(bits))
#define csr_clear(csr, bits) __asm__ volatile("csrc " #csr ", %0" :: "rK"(bits))

#define MSTATUS_MIE   (1u << 3)
#define MIE_MTIE      (1u << 7)
#define MCAUSE_IRQ    (1u << 31)
#define IRQ_M_TIMER   7u

/* Exception codes (mcause with bit 31 clear). */
#define EXC_ILLEGAL_INSTRUCTION  2u
#define EXC_BREAKPOINT           3u
#define EXC_ECALL_M             11u

/* ---- Console (UART) ------------------------------------------------------ */
void uart_putc(char c);
void uart_puts(const char *s);
/* printf: %c %s %d %u %x %p %% and zero-pad widths (%08x). Every integer is
 * 32 bits on RV32, so uint32_t, int and long all print with %u/%d/%x
 * (an 'l' modifier is accepted and ignored). Not type-checked by GCC, because
 * newlib's uint32_t is 'long unsigned int' and %u would warn everywhere. */
int  printf(const char *fmt, ...);

/* ---- Time (TIMER) -------------------------------------------------------- */
uint64_t timer_now(void);              /* cycles since reset */
void     timer_set_cmp(uint64_t when); /* timer irq while now >= when */

/* ---- Tile ---------------------------------------------------------------- */
static inline uint32_t tile_id(void) { return TILECTRL_TILE_ID; }

/* ---- Simulation ---------------------------------------------------------- */
/* Stop the testbench with an exit code (0 = pass). Never returns. */
__attribute__((noreturn)) void sim_exit(int code);

/* ---- Traps --------------------------------------------------------------- */
/*
 * Called from start.S for every trap; returns the address to resume at.
 * The default version dispatches interrupts to irq_handler() and ends the
 * simulation on any exception. Both are weak: define your own to override.
 */
uint32_t trap_handler(uint32_t mcause, uint32_t mepc, uint32_t mtval);
void     irq_handler(uint32_t cause);

/* ---- Minimal libc (no libc is linked) ------------------------------------ */
void *memset(void *dst, int c, size_t n);
void *memcpy(void *dst, const void *src, size_t n);
