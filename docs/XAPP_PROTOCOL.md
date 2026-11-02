# FUJIFILM XApp Communication Protocol

## 1. BLE GATT Architecture

Primary service: `00007770-0000-1000-8000-00805F9B34FB` (short `0x7770`).

| UUID (short) | Full UUID | Name | Permissions |
|---|---|---|---|
| 0x7770 | 00007770-0000-1000-8000-00805F9B34FB | Camera Service | primary service |
| 0x7771 | 00007771-0000-1000-8000-00805F9B34FB | Device Info & Status | read, notify |
| 0x7772 | 00007772-0000-1000-8000-00805F9B34FB | Command / Control | write, write-without-response, notify |
| 0x7773 | 00007773-0000-1000-8000-00805F9B34FB | Geotagging Data Injection | write, write-without-response |
| 0x7774 | 00007774-0000-1000-8000-00805F9B34FB | Wi-Fi Handoff Credentials | write, read |
| 0x7775 | 00007775-0000-1000-8000-00805F9B34FB | Activity & Timeline Sync | read, notify |

## 2. Packet Framing

```
+------+------+------+------+----------+--------+
| SYNC | TYPE | SEQ  | LEN  | PAYLOAD  | CRC16 |
| 2 B  | 1 B  | 1 B  | 2 B  | LEN B    | 2 B   |
+------+------+------+------+----------+--------+
```

- `SYNC` = `0xFA 0xCE`.
- `LEN` = payload length, little-endian.
- `CRC16` = CRC16-CCITT over all preceding bytes (SYNC..PAYLOAD), little-endian.

Message types: `PAIR_REQ (0x01)`, `PAIR_RESP (0x02)`, `STATUS (0x03)`,
`GEOTAG (0x04)`, `WIFI_HANDOFF (0x05)`, `ACTIVITY_SYNC (0x06)`.

## 3. Pairing Handshake

Initiated by holding `DISP/BACK` on camera to enter "Bluetooth Pairing Registration".

```
Client                          Camera
  |  -- PAIR_REQ (nonce C) ---->  |
  |  <-- PAIR_RESP (nonce K) --   |
  |  verify nonces                |
  |  -- STATUS (connected) ---->  |
```

State machine: `unpaired -> pairing -> connected -> transferring -> idle`.

## 4. Geotagging Payload (0x7773)

Scaled-integer form (16 bytes):

```
int32 latitude  (deg * 1e7)
int32 longitude (deg * 1e7)
int32 altitude  (m * 10)
uint32 utc_timestamp (unix seconds)
```

IEEE-754 form (24 bytes): `double lat, double lon, float alt, uint32 ts`.

## 5. Activity Log (0x7775)

```
uint32 shutter_count
uint32 n_entries
repeat:
  uint16 key_len
  bytes  key (film simulation name)
  uint32 count
```

Cumulative shutter count plus per-film-simulation usage counters for the
XApp "Activity" / "Timeline" views.

## 6. Failure Mitigation

- Volatile/PTP RAM recovery: docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
- Firmware repacking/patching: docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
