CC = arm-none-eabi-gcc
OBJCOPY ?= arm-none-eabi-objcopy

CFLAGS = -marm -march=armv7-a -fPIC -fno-builtin -nostdlib -Wl,-T,Linker.ld

X10_CFLAGS = -marm -march=armv5te -fPIC -fno-builtin -nostdlib -Wl,-T,Linker.ld

SRCS = src/entry.S src/hook_instax.c


help:
	@echo "Fujifilm ARM32 Payload Build Targets:"
	@echo "  make payload.bin   - Build payload for X-T10 (ARMv7-A)"
	@echo "  make x10           - Build payload for X10 (ARMv5TE)"
	@echo "  make check         - Check if arm-none-eabi-gcc toolchain is available"
	@echo "  make clean         - Remove build artifacts"

check:
	@if command -v $(CC) >/dev/null 2>&1; then \
		echo "[OK] $(CC) found: $$($(CC) --version | head -n1)"; \
	else \
		echo "[INFO] $(CC) not installed (install via pacman -S arm-none-eabi-gcc)"; \
	fi

all: payload.bin

payload.bin: $(SRCS) Linker.ld
	@if ! command -v $(CC) >/dev/null 2>&1; then \
		echo "error: $(CC) not found."; \
		echo "Install the ARM GNU toolchain (arm-none-eabi-gcc), e.g.:"; \
		echo "  Debian/Ubuntu: sudo apt install gcc-arm-none-eabi"; \
		echo "  Arch Linux:    sudo pacman -S arm-none-eabi-gcc"; \
		exit 1; \
	fi
	$(CC) $(CFLAGS) $(SRCS) -o payload.elf
	$(OBJCOPY) -O binary payload.elf payload.bin

x10: $(SRCS) Linker.ld
	@if ! command -v $(CC) >/dev/null 2>&1; then \
		echo "error: $(CC) not found."; \
		echo "Install the ARM GNU toolchain (arm-none-eabi-gcc), e.g.:"; \
		echo "  Debian/Ubuntu: sudo apt install gcc-arm-none-eabi"; \
		echo "  Arch Linux:    sudo pacman -S arm-none-eabi-gcc"; \
		exit 1; \
	fi
	$(CC) $(X10_CFLAGS) $(SRCS) -o payload_x10.elf
	$(OBJCOPY) -O binary payload_x10.elf payload_x10.bin

clean:
	rm -f payload.elf payload.bin payload_x10.elf payload_x10.bin
