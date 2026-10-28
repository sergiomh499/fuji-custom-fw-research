# Fujifilm X-T10 Wi-Fi Stack Crash Analysis

## Scope

Target firmware: Fujifilm X-T10 `FWUP0007.DAT`, v1.31, unpacked to
`/tmp/xt10_v131.bin` (53,084,624 bytes, ARM32 little-endian).

The camera's TCP/IP implementation is the KASAGO stack.  Relevant markers are
located in two physical file regions:

| Region | File offset range | Contents |
|---|---:|---|
| Network init / DHCP / TCP-IP | `0x00B4D400 - 0x00B4F000` | `lanInit`, `efTcpIpInit`, `tfDhcpdStart`, `recv Memory Depletiion Err.`, `STM AP_SOC Halt.` |
| HTTP / discovery listener | `0x00B93180 - 0x00B93300` | `IMPORT /guest`, `DISCOVER`, UDP ports `51541` / `51542` |

Key marker offsets:

| Marker | File offset |
|---|---:|
| `lanInit` | `0x00B4D414` |
| `efTcpIpInit` | `0x00B4D47C` |
| `tfDhcpdStart` | `0x00B4DE59` |
| `recv Memory Depletiion Err.` | `0x00B4DD9C` |
| `STM AP_SOC Halt.` | `0x00B4DF3C` |
| `IMPORT /guest` | `0x00B9319C` |
| `DISCOVER` (network region) | `0x00B4DF7C` |
| `DISCOVER` (discovery region) | `0x00B932A0` |
| UDP port `51541` | `0x00B93251` |
| UDP port `51542` | `0x00B932B1` |

## Root cause

Modern phones send three classes of traffic that exceed the assumptions of the
unpatched KASAGO build in X-T10:

1. **DHCP client identifier overflow**
   - X-T10's `tfDhcpdStart` path uses a fixed-size DHCP lease/client record.
   - Modern Android 14+ uses randomized MAC addresses and long DHCP client
     identifiers / DUIDs (19+ bytes).
   - The older parser copies the option into a small static lease struct without
     an effective length clamp, overwriting adjacent KASAGO heap/control data.
   - Result: immediate freeze or `STM AP_SOC Halt.`.

2. **Oversized HTTP / discovery packets**
   - The discovery listener handles `IMPORT /guest`, `DISCOVER`, and UDP
     broadcasts on ports `51541` / `51542`.
   - Modern iOS 18 / Android stacks send large User-Agent, SSDP, or mDNS-style
     payloads.
   - The receive path logs `recv Memory Depletiion Err.` when the fixed receive
     buffer is exhausted; the error path is not defensive and stalls the AP SoC.

3. **Management-frame negotiation mismatch**
   - Modern clients negotiate protected management frames (802.11w / PMF).
   - The older X-T10 Wi-Fi firmware rejects or mishandles this negotiation and
     reaches an unhandled STM halt (`STM AP_SOC Halt.`).

## Observed assembly/data flow

The region `0x00B4D400 - 0x00B4F000` contains the KASAGO initialization and
error strings in this order:

- `lanInit` / `efTcpIpInit`: stack bring-up.
- `tfDhcpdStart`: DHCP server start.
- `recv Memory Depletiion Err.`: receive-buffer exhaustion.
- `STM AP_SOC Halt.`: fatal SoC halt.

The region `0x00B93180 - 0x00B93300` contains the discovery protocol strings:

- `IMPORT /guest`
- `DISCOVER`
- `51541` / `51542`

This indicates a single receive path feeds both DHCP and HTTP/discovery
handling, with fixed buffers and no early rejection of oversized or malformed
packets.

## Difference from patched Fujifilm models

Fujifilm patched newer models (for example X-T20 v2.11 and X-T2 v4.41) but
left X-T10 v1.31 unchanged, citing hardware limitations.  The newer firmware
retains the same KASAGO architecture but adds defensive handling:

- DHCP option lengths are clamped before copying into lease records.
- Oversized discovery/HTTP packets are dropped before receive-buffer depletion.
- Management-frame negotiation failures are converted into a recoverable error
  instead of `STM AP_SOC Halt.`.

X-T10 lacks these guards in v1.31.

## Proposed binary patch strategy

1. **DHCP option clamp**
   - Hook the `tfDhcpdStart` / DHCPREQUEST option parser.
   - Clamp client identifier and DUID lengths to the static lease struct bound.
   - Reject or truncate options longer than the bound instead of copying them.

2. **Discovery packet guard**
   - Hook the UDP/TCP receive path before `recv Memory Depletiion Err.`.
   - If an HTTP/discovery packet exceeds the configured receive buffer, drop it
     and return success without allocating or depleting memory.

3. **STM halt recovery**
   - Replace the fatal `STM AP_SOC Halt.` path with a recoverable error return
     (`bx lr` or error code) for management-frame negotiation failures.

4. **Injection**
   - Use `core.patcher.encode_arm_branch` / `inject_payload` to redirect the
     vulnerable handler to a defensive payload.
   - Keep all changes in the documented regions so they are auditable.

## Runtime impact

The patch is intentionally conservative: it does not attempt to modernize the
whole KASAGO stack.  It only prevents the specific oversized/malformed inputs
that crash X-T10, preserving normal camera Wi-Fi behavior.
