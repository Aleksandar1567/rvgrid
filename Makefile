# Thin wrapper; everything real lives in Python (python -m rvgrid ...) or sw/Makefile.
#
#   make setup            venv + Python deps + EDA tools (1.2 GB download, 4 GB in ~/tools)
#   make test             unit tests (pure Python) + system tests (Verilator)
#   make test-unit        just the fast ones, no external tools needed
#   make sim APP=hello    boot one program, print its console
#   make waves APP=hello  same, plus a VCD waveform (open with gtkwave/surfer)
#   make diagrams         regenerate docs/generated + README block + schematics
#   make synth            Yosys/nextpnr resource + Fmax estimate (ECP5)

SHELL  := /bin/bash
VENV   := .venv
PY     := $(VENV)/bin/python
ENV    := source env.sh &&
APP    ?= hello

.PHONY: setup venv tools gen sw test test-unit sim waves diagrams synth clean

setup: venv tools

venv: $(PY)
$(PY): pyproject.toml
	python3 -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e '.[dev]'
	@touch $(PY)

tools:
	scripts/setup-tools.sh

gen: venv
	$(ENV) python -m rvgrid gen

sw: venv
	$(ENV) $(MAKE) -C sw

test: venv
	$(ENV) python -m pytest

test-unit: venv
	$(ENV) python -m pytest tests/unit

sim: venv
	$(ENV) python -m rvgrid sim $(APP)

waves: venv
	$(ENV) python -m rvgrid sim $(APP) --waves

diagrams: venv
	$(ENV) python -m rvgrid diagram

synth: venv sw
	$(ENV) python -m rvgrid synth

clean:
	rm -rf build
