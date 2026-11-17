# VexRiscv (vendored, pre-generated Verilog)

`VexRiscv_Min.v` is used unmodified. At build time rvgrid copies it and renames
its modules (`VexRiscv` → `VexRiscv_Min`, …) so several variants can live in
one design later.

| | |
|---|---|
| Source | https://github.com/litex-hub/pythondata-cpu-vexriscv, `pythondata_cpu_vexriscv/verilog/VexRiscv_Min.v` |
| Commit | `642ecfed1c84460555d6d803d660cc60cfc1ecb6` (2026-06-02) |
| VexRiscv | `b6118e5cc2a33323425df6455697139021d50c72` (SpinalHDL 1.9.4) |
| License | MIT, see `LICENSE` |

Generated with:

```
sbt "runMain vexriscv.GenCoreDefault --iCacheSize 0 --dCacheSize 0 --mulDiv false \
     --singleCycleShift false --singleCycleMulDiv false --bypass false \
     --prediction none --outputFile VexRiscv_Min"
```

What that means:

- RV32I + Zicsr (machine mode only). No M extension: `*` and `/` come from libgcc.
- No caches, no branch prediction, no bypass network: simple and cycle-predictable.
- CSRs: `mstatus mie mip mtvec mepc mcause mtval`. No `mcycle`/`mhartid`
  (use the tile's TIMER and TILECTRL.TILE_ID instead).
- Traps: illegal instruction, `ecall`, machine timer/software/external interrupts.
  Wishbone `ERR` is ignored, and so are misaligned accesses.

## Other cores

To try another configuration, generate it from the VexRiscv repo (needs Java +
sbt) or copy another file from the source repo above, drop it next to this one
and add a variant to `rvgrid/cpu/vexriscv.py`. Non-VexRiscv cores (PicoRV32,
SERV, …) get their own wrapper in `rvgrid/cpu/`.
