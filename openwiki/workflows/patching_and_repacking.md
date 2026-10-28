---
type: workflow
title: Binary Patching, Ghidra Analysis & Build Toolchains
description: Developer guide for ARM relative branch calculation, trampoline payload injection, headless Ghidra automation, and bare-metal compilation.
tags: [patching, ghidra, toolchain, arm, trampoline, injection]
verified:
  - by: openwiki/0.7.1
    at: 2026-10-28T21:29:05.191Z
sources:
  - id: openwiki-source-9e823c83f26b10d85c917097
    resource: repo://core/patcher.py
  - id: openwiki-source-72b0a7843d97c1664cb7976b
    resource: repo://tools/ghidra_headless.py
generated: { by: "omp", at: "2026-10-28T21:29:05.191Z" }
---

# Binary Patching, Ghidra Analysis & Build Toolchains

Reverse engineering and modifying Fujifilm firmware requires coordinate precision: disassembled code must be mapped to runtime memory layouts, custom ARM machine code must be cross-compiled with strict position independence, and branch trampolines must be calculated relative to ARM pipeline program counters.

## ARM32 Relative Branch Calculation

ARM32 `B` (Branch) and `BL` (Branch with Link) instructions use a 24-bit signed word offset relative to the Program Counter ($PC + 8$ bytes due to instruction pipelining):

$$\text{offset} = \frac{\text{destination} - (\text{source} + 8)}{4}$$

$$\text{instruction} = \text{base\_opcode} \ | \ (\text{offset} \ \& \ \text{0x00FFFFFF})$$

Where `base_opcode` is `0xEA000000` for unconditional branch (`B`) and `0xEB000000` for branch with link (`BL`).

The `core/patcher.py` module implements this logic via `encode_arm_branch()` and handles payload injection:
```bash
# Calculate relative branch instruction from hook to payload
python3 tools/fuji_patch.py branch 0x00485258 0x01cf0000 --link

# Inject payload binary into target at 0x01cf0000 and hook at 0x00485258
python3 tools/fuji_patch.py inject xt10_v131.bin payloads/payload.bin 0x00485258 0x01cf0000 xt10_v131_mod.bin
```

## Bare-Metal ARM Cross-Compilation

Payloads in `payloads/` are written in freestanding C and assembly, designed to run without OS loaders or dynamic linkers:
- **Compiler:** `arm-none-eabi-gcc`.
- **Target Architectures:**
  - Fujifilm X-T10: `-march=armv7-a -marm` (Cortex-A/R profile).
  - FinePix X10: `-march=armv5te -marm` (ARM9/ARM11 profile).
- **Compiler Flags:** `-fPIC -fno-builtin -nostdlib` with custom `Linker.ld` script.

```bash
# Verify compiler installation
make -C payloads check

# Compile payloads for X-T10 and X10
make -C payloads payload.bin
make -C payloads x10
```

## Automated Headless Ghidra Analysis

Analyzing a 53 MB unpacked firmware binary manually is error-prone. The `tools/ghidra_headless.py` wrapper invokes Ghidra's headless analyzer (`analyzeHeadless`) with automated labeling scripts:

- **Target Architecture Specification:** `ARM:LE:32:v7` for X-T10, `ARM:LE:32:v5t` for X10.
- **Java Labeling Script:** `ghidra_scripts/LabelFujifilmStructures.java` labels:
  - SQLite database schemas (`create table pt`, `create table fnf`).
  - UI State Machine menu dispatch tables (507 entries: `FSIMMENU`, `AFMENU`, `CUSTOMMENU`).
  - Film simulation DSP token buffers (`PROV`, `VELV`, `CHROME`, `_ASTIA`).
  - Lens communication and KASAGO network entrypoints.

```bash
# Run headless analysis and structure labeling
python3 tools/ghidra_headless.py \
  --target xt10 \
  --bin /tmp/xt10_v131.bin \
  --project-dir ./ghidra_project \
  --script ghidra_scripts/LabelFujifilmStructures.java
```
