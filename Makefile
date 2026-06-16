PREFIX ?= $(HOME)/.local
BIN_DIR := $(PREFIX)/bin
PYTHON ?= python3

.PHONY: install-local install-skill uninstall test help

install-local:
	./install.sh --no-skill

install-skill:
	./install.sh

uninstall:
	./uninstall.sh

test:
	$(PYTHON) -m unittest discover -s tests

help:
	$(PYTHON) apple_triage/main.py --help
