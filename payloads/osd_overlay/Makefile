CC = arm-none-eabi-gcc
OBJCOPY ?= arm-none-eabi-objcopy

CFLAGS = -marm -march=armv7-a -fPIC -fno-builtin -nostdlib -Wl,-T,Linker.ld

SRCS = osd_overlay.c

all: osd_overlay.bin

help:
	@echo "OSD Overlay ARMv7-A Payload Build Targets:"
	@echo "  make           - Build osd_overlay.bin"
	@echo "  make check     - Check if arm-none-eabi-gcc toolchain is available"
	@echo "  make clean     - Remove build artifacts"

check:
	@if command -v $(CC) >/dev/null 2>&1; then \
		echo "[OK] $(CC) found: $$($(CC) --version | head -n1)"; \
	else \
		echo "[INFO] $(CC) not installed (install via pacman -S arm-none-eabi-gcc)"; \
	fi

osd_overlay.bin: $(SRCS) Linker.ld
	@if ! command -v $(CC) >/dev/null 2>&1; then \
		echo "error: $(CC) not found."; \
		exit 1; \
	fi
	$(CC) $(CFLAGS) $(SRCS) -o osd_overlay.elf
	$(OBJCOPY) -O binary osd_overlay.elf osd_overlay.bin

clean:
	rm -f osd_overlay.elf osd_overlay.bin
