# Makefile for timewarrior-tools

PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
EXTDIR ?= $(HOME)/.config/timewarrior/extensions

# Files to install
EXTENSIONS = summarize.py
BINARIES = timew-change-tag timew-short.sh timew-start-afk

.PHONY: all install install-dev uninstall help

all: help

help:
	@echo "timewarrior-tools installation"
	@echo ""
	@echo "Targets:"
	@echo "  install      Install files (copy)"
	@echo "  install-dev  Install files (symlinks for development)"
	@echo "  uninstall    Remove installed files"
	@echo ""
	@echo "Directories:"
	@echo "  BINDIR = $(BINDIR)"
	@echo "  EXTDIR = $(EXTDIR)"

install: $(BINDIR) $(EXTDIR)
	@for f in $(EXTENSIONS); do \
		echo "Installing $$f -> $(EXTDIR)/"; \
		cp "$$f" "$(EXTDIR)/"; \
		chmod +x "$(EXTDIR)/$$f"; \
	done
	@for f in $(BINARIES); do \
		echo "Installing $$f -> $(BINDIR)/"; \
		cp "$$f" "$(BINDIR)/"; \
		chmod +x "$(BINDIR)/$$f"; \
	done

install-dev: $(BINDIR) $(EXTDIR)
	@for f in $(EXTENSIONS); do \
		echo "Linking $$f -> $(EXTDIR)/"; \
		ln -sf "$(CURDIR)/$$f" "$(EXTDIR)/$$f"; \
	done
	@for f in $(BINARIES); do \
		echo "Linking $$f -> $(BINDIR)/"; \
		ln -sf "$(CURDIR)/$$f" "$(BINDIR)/$$f"; \
	done

uninstall:
	@for f in $(EXTENSIONS); do \
		echo "Removing $(EXTDIR)/$$f"; \
		rm -f "$(EXTDIR)/$$f"; \
	done
	@for f in $(BINARIES); do \
		echo "Removing $(BINDIR)/$$f"; \
		rm -f "$(BINDIR)/$$f"; \
	done

$(BINDIR):
	mkdir -p $(BINDIR)

$(EXTDIR):
	mkdir -p $(EXTDIR)
