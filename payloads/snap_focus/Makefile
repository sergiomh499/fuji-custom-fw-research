CC = arm-none-eabi-gcc
OBJCOPY ?= arm-none-eabi-objcopy

CFLAGS = -marm -march=armv7-a -fPIC -fno-builtin -nostdlib -Wl,-T,Linker.ld

SRCS = snap_focus.c

all: snap_focus.bin

help:
	@echo "Snap Focus ARMv7-A Payload Build Targets:"
	@echo "  make           - Build snap_focus.bin"
	@echo "  make check     - Check if arm-none-eabi-gcc toolchain is available"
	@echo "  make clean     - Remove build artifacts"

check:
	@if command -v $(CC) >/dev/null 2>&1; then \
		echo "[OK] $(CC) found: $$($(CC) --version | head -n1)"; \
	else \
		echo "[INFO] $(CC) not installed (install via pacman -S arm-none-eabi-gcc)"; \
	fi

snap_focus.bin: $(SRCS) Linker.ld
	@if ! command -v $(CC) >/dev/null 2>&1; then \
		echo "error: $(CC) not found."; \
		exit 1; \
	fi
	$(CC) $(CFLAGS) $(SRCS) -o snap_focus.elf
	$(OBJCOPY) -O binary snap_focus.elf snap_focus.bin

clean:
	rm -f snap_focus.elf snap_focus.bin
