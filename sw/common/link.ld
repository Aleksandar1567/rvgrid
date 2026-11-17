/*
 * One memory, one image: code, read-only data, data, bss and stack all live
 * in the tile's L1. The binary is loaded at L1_BASE as-is (by the host, or
 * baked into the SRAM), so .data needs no copy at boot; only .bss is zeroed.
 *
 *   L1_BASE  +--------------------+
 *            | .text  (_start 1st)|
 *            | .rodata            |
 *            | .data / .sdata     |   <- end of the .bin file
 *            | .bss  / .sbss      |   zeroed by start.S
 *            |   ... free ...     |
 *            | stack (grows down) |
 *   L1 end   +--------------------+   __stack_top
 */
OUTPUT_ARCH("riscv")
ENTRY(_start)

INCLUDE memory.ld           /* generated from rvgrid/config.py */

STACK_SIZE = 4K;

SECTIONS
{
    .text : {
        KEEP(*(.text.start))
        *(.text .text.*)
    } > L1

    .rodata : ALIGN(4) {
        *(.rodata .rodata.* .srodata .srodata.*)
    } > L1

    .data : ALIGN(4) {
        *(.data .data.*)
        __global_pointer$ = . + 0x800;
        *(.sdata .sdata.*)
        . = ALIGN(4);
    } > L1

    .bss (NOLOAD) : ALIGN(4) {
        __bss_start = .;
        *(.sbss .sbss.* .bss .bss.* COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > L1

    __stack_top = ORIGIN(L1) + LENGTH(L1);
    ASSERT(__bss_end + STACK_SIZE <= __stack_top, "program does not fit in L1 with its stack")

    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
