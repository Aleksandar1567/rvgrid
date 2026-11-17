#!/usr/bin/env bash
# Download the pinned EDA + RISC-V toolchains into $RVGRID_TOOLS (no sudo).
#
#   OSS CAD Suite : yosys, verilator 5, iverilog, nextpnr, gtkwave
#   xPack GCC     : riscv-none-elf-gcc (bare-metal RV32/RV64, multilib)
#
# Usage:  scripts/setup-tools.sh            # install into ~/tools
#         RVGRID_TOOLS=/opt/eda scripts/setup-tools.sh
# Then:   source env.sh
set -euo pipefail

OSS_CAD_DATE="${OSS_CAD_DATE:-2026-11-01}"
XPACK_GCC_VER="${XPACK_GCC_VER:-15.2.0-1}"
TOOLS="${RVGRID_TOOLS:-$HOME/tools}"

mkdir -p "$TOOLS"
cd "$TOOLS"

fetch() {  # url dest
    if [ ! -f "$2" ]; then
        echo ">> downloading $(basename "$2")"
        curl -fL --retry 3 --progress-bar -o "$2.part" "$1"
        mv "$2.part" "$2"
    fi
}

# --- OSS CAD Suite -----------------------------------------------------------
oss_tgz="oss-cad-suite-linux-x64-${OSS_CAD_DATE//-/}.tgz"
if [ ! -x "$TOOLS/oss-cad-suite/bin/verilator" ]; then
    fetch "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_CAD_DATE}/${oss_tgz}" "$oss_tgz"
    echo ">> unpacking OSS CAD Suite"
    tar xzf "$oss_tgz"
    echo "$OSS_CAD_DATE" > oss-cad-suite/RVGRID_VERSION
    rm -f "$oss_tgz"
fi

# --- xPack RISC-V GCC --------------------------------------------------------
gcc_dir="xpack-riscv-none-elf-gcc-${XPACK_GCC_VER}"
gcc_tgz="${gcc_dir}-linux-x64.tar.gz"
if [ ! -x "$TOOLS/$gcc_dir/bin/riscv-none-elf-gcc" ]; then
    fetch "https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/download/v${XPACK_GCC_VER}/${gcc_tgz}" "$gcc_tgz"
    echo ">> unpacking xPack RISC-V GCC"
    tar xzf "$gcc_tgz"
    rm -f "$gcc_tgz"
fi
ln -sfn "$gcc_dir" riscv-gcc

echo
echo "Tools installed in $TOOLS"
echo "  verilator : $("$TOOLS/oss-cad-suite/bin/verilator" --version)"
echo "  yosys     : $("$TOOLS/oss-cad-suite/bin/yosys" -V)"
echo "  gcc       : $("$TOOLS/riscv-gcc/bin/riscv-none-elf-gcc" --version | head -1)"
echo
echo "Next: source env.sh"
