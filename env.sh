# Put the project's tools on PATH:  source env.sh
#
# Order matters: the venv's python first, then the RISC-V GCC, then the
# OSS CAD Suite binaries (appended so its bundled python never shadows ours).

_rvgrid_root="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_rvgrid_tools="${RVGRID_TOOLS:-$HOME/tools}"

if [ -d "$_rvgrid_root/.venv" ]; then
    # shellcheck disable=SC1091
    . "$_rvgrid_root/.venv/bin/activate"
fi
[ -d "$_rvgrid_tools/riscv-gcc/bin" ] && export PATH="$_rvgrid_tools/riscv-gcc/bin:$PATH"
[ -d "$_rvgrid_tools/oss-cad-suite/bin" ] && export PATH="$PATH:$_rvgrid_tools/oss-cad-suite/bin"

unset _rvgrid_root _rvgrid_tools
