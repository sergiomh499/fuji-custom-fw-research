---
type: concept
title: KASAGO TCP/IP Stack & Wi-Fi Crash Remediation
description: Root-cause analysis of the KASAGO TCP/IP buffer depletion crash when connecting modern smartphones to Fujifilm X-T10, and defensive patching implementation.
tags: [wifi, networking, kasago, crash, bugfix, dhcp, android17, ios18]
verified:
  - by: openwiki/0.7.1
    at: 2026-10-28T21:29:05.191Z
sources:
  - id: openwiki-source-86ca433cc7062c5458b60463
    resource: repo://core/wifi_patch.py
  - id: openwiki-source-31ab0089bbea1301f0f1542d
    resource: repo://docs/WIFI_STACK_CRASH_ANALYSIS.md
generated: { by: "omp", at: "2026-10-28T21:29:05.191Z" }
---

# KASAGO TCP/IP Stack & Wi-Fi Crash Remediation

Owners of earlier Fujifilm X-series cameras (such as the Fujifilm X-T10, X-T1, X-E2) experience an instant freeze or complete shutdown whenever modern smartphones (Android 14+, Android 17, or iOS 17/18) attempt to connect via Wi-Fi for photo transfer or remote control. Fujifilm acknowledged the failure across several models, patching newer units (e.g. X-T20 v2.11) while abandoning the X-T10 citing "hardware limitations".

## The Embedded KASAGO Network Stack

Reverse engineering of the X-T10 v1.31 firmware binary (`FWUP0007.DAT`) reveals that the networking subsystem is built on **KASAGO TCP/IP** (developed by Elmic Systems / Kyoto Software Research), an embedded IPv4/v6 dual stack:
- **Initialization:** `lanInit:efTcpIpInit` at physical offset `0x00B4D474`.
- **DHCP Daemon:** `tfDhcpdStart` at physical offset `0x00B4DE4C`.
- **Discovery Sockets:** UDP listeners on ports 51541 and 51542, plus an embedded HTTP server handling `IMPORT /guest` and `DISCOVER` requests at `0x00B93180 - 0x00B93300`.

## Root Cause: Buffer Exhaustion & Unhandled State Machine Halt

When an Android 14+ or iOS 18 device associates with the camera's SoftAP, two distinct protocol anomalies occur:

1. **DHCP Option 61 (Client Identifier) Length Overflow:**
   Modern operating systems use MAC randomization and append extended DUID identifiers (19+ bytes). In KASAGO's DHCP server, options exceeding standard static lease structures trigger internal memory pool exhaustion.
2. **Oversized Discovery / SSDP Packets:**
   Modern devices broadcast UPnP/mDNS announcement frames and user-agent headers exceeding 1 KB. The camera's static receive buffers quickly run out of descriptors, emitting the debug assertion `recv Memory Depletiion Err.` at `0x00B4DD9C`.
3. **RTOS State Machine Panic:**
   Rather than dropping malformed or oversized packets, the KASAGO state machine hits an unhandled branch: `STM AP_SOC Halt.` at `0x00B4DF3C`. This triggers an immediate hardware shutdown or watch-dog lockup.

## Defensive Binary Patch

The `core/wifi_patch.py` module and `fujitool patch wifi` CLI command remediate this vulnerability without source code recompilation:
- **Detection:** `WiFiPatcher.detect()` verifies the presence of KASAGO initialization symbols and crash sites in the target firmware.
- **Defensive Hooks:**
  - Clamps DHCP Option 61 length processing to prevent static buffer overruns.
  - Replaces the terminal `STM AP_SOC Halt.` branch with a safe graceful drop and return (`ARM_BX_LR`, `0x1e 0xff 0x2f 0xe1` or `ARM_NOP`).
  - Preserves legitimate photo transfer and PTP-IP communications while discarding oversized broadcast bursts.

```bash
# Apply defensive Wi-Fi patch to official firmware DAT
fujitool patch wifi FWUP0007.DAT FWUP0007_PATCHED.DAT --increment-version
```
If any unexpected connection failure occurs with the patched firmware, holding `DISP/BACK` on camera startup allows rolling back to official stock firmware from the SD card.

## Verification via Official X-T20 v2.11 Firmware Diff

Fujifilm officially resolved this freeze in the X-T20 Ver.2.11 release (`FWUP0013.DAT`). Reverse engineering by `core/xt20_extractor.py` confirms that the KASAGO stack (`lanInit`, `efTcpIpInit`, `tfDhcpdStart`) remains at `0x00F5F1B0 - 0x00F5FB38`, but the socket descriptor allocation path guards against oversized option fields, mirroring our defensive clamp strategy and proving the root cause analysis.
