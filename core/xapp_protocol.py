"""FUJIFILM XApp communication protocol (BLE GATT, framing, pairing, sync).

Reverse-engineered from X-T30 v2.00 / X-T4 v2.00 / X-T5 / X-H2 firmware notes:
  * Primary GATT service: 00007770-0000-1000-8000-00805F9B34FB (0x7770).
  * Characteristics 0x7771..0x7775 (device info, command, geotag, wifi handoff,
    activity/timeline).

Mitigation (volatile RAM / PTP only): docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
Mitigation (firmware repacking/patching): docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
"""

from __future__ import annotations

import enum
import os
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

BytesLike = Union[bytes, bytearray, memoryview]

MITIGATION_LINK = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery"
MITIGATION_LINK_FW = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery"

XAPP_MITIGATION = (
    "Mitigation: XApp traffic runs over volatile RAM/BLE state; power-cycle the "
    "camera to clear a hung session (0% flash risk). See " + MITIGATION_LINK
)

# ---------------------------------------------------------------------------
# GATT UUIDs
# ---------------------------------------------------------------------------

SERVICE_UUID = "00007770-0000-1000-8000-00805F9B34FB"
SERVICE_UUID_SHORT = 0x7770

CHAR_DEVICE_INFO = "00007771-0000-1000-8000-00805F9B34FB"
CHAR_COMMAND = "00007772-0000-1000-8000-00805F9B34FB"
CHAR_GEOTAG = "00007773-0000-1000-8000-00805F9B34FB"
CHAR_WIFI_HANDOFF = "00007774-0000-1000-8000-00805F9B34FB"
CHAR_ACTIVITY = "00007775-0000-1000-8000-00805F9B34FB"

GATT_CHARACTERISTICS = {
    0x7771: ("Device Info & Status", "read, notify"),
    0x7772: ("Command / Control", "write, write-without-response, notify"),
    0x7773: ("Geotagging Data Injection", "write, write-without-response"),
    0x7774: ("Wi-Fi Handoff Credentials", "write, read"),
    0x7775: ("Activity & Timeline Sync", "read, notify"),
}

SYNC_BYTES = b"\xfa\xce"
HEADER_SIZE = 2 + 1 + 1 + 2  # sync + type + seq + len


class XAppError(Exception):
    """XApp protocol error.

    Mitigation: volatile BLE/RAM state; power-cycle clears it.
    See docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
    """

    def __init__(self, message=""):
        if MITIGATION_LINK not in str(message):
            message = f"{message} {XAPP_MITIGATION}" if message else XAPP_MITIGATION
        super().__init__(message)


class XAppCRCError(XAppError, ValueError):
    """CRC verification failure."""


class XAppFramingError(XAppError, ValueError):
    """Framing/parsing failure."""


# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------


class XAppMessageType(enum.IntEnum):
    PAIR_REQ = 0x01
    PAIR_RESP = 0x02
    STATUS = 0x03
    GEOTAG = 0x04
    WIFI_HANDOFF = 0x05
    ACTIVITY_SYNC = 0x06

    # aliases
    PAIR_REQUEST = PAIR_REQ
    PAIR_RESPONSE = PAIR_RESP
    GEO_TAG = GEOTAG
    WIFI = WIFI_HANDOFF
    ACTIVITY = ACTIVITY_SYNC
    TIMELINE = ACTIVITY_SYNC


# Back-compat alias names
MessageType = XAppMessageType
XAppMsgType = XAppMessageType


# ---------------------------------------------------------------------------
# CRC16-CCITT
# ---------------------------------------------------------------------------


def _crc16_ccitt(data: BytesLike, init: int = 0x0000, poly: int = 0x1021) -> int:
    crc = init & 0xFFFF
    for byte in _as_bytes(data):
        crc ^= (byte << 8) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def crc16_ccitt(data: BytesLike, init: int = 0x0000, poly: int = 0x1021) -> int:
    """CRC16-CCITT (MSB-first, default init 0x0000)."""
    return _crc16_ccitt(data, init=init, poly=poly)


def crc16_ccitt_false(data: BytesLike) -> int:
    return _crc16_ccitt(data, init=0xFFFF, poly=0x1021)


def crc16_xmodem(data: BytesLike) -> int:
    return _crc16_ccitt(data, init=0x0000, poly=0x1021)


def crc16(data: BytesLike) -> int:
    return crc16_ccitt(data)


def _as_bytes(data: Any) -> bytes:
    if data is None:
        return b""
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    if hasattr(data, "data"):
        return bytes(data.data)
    if hasattr(data, "to_bytes") and callable(data.to_bytes):
        try:
            return bytes(data.to_bytes())
        except Exception:
            pass
    if hasattr(data, "pack") and callable(data.pack):
        try:
            return bytes(data.pack())
        except Exception:
            pass
    return bytes(data)


# ---------------------------------------------------------------------------
# Packet
# ---------------------------------------------------------------------------


@dataclass
class XAppPacket:
    msg_type: Any = 0
    seq: int = 0
    payload: bytes = b""
    crc: Optional[int] = None
    sync: bytes = SYNC_BYTES

    def __post_init__(self):
        if isinstance(self.msg_type, str):
            try:
                self.msg_type = XAppMessageType[self.msg_type]
            except KeyError:
                pass
        self.seq = int(self.seq) & 0xFF
        self.payload = _as_bytes(self.payload)
        if self.crc is None:
            self.crc = None  # computed in pack

    @property
    def type(self):
        return self.msg_type

    @type.setter
    def type(self, v):
        self.msg_type = v

    @property
    def message_type(self):
        return self.msg_type

    @property
    def msgType(self):
        return self.msg_type

    def _msg_byte(self) -> int:
        mt = self.msg_type
        if isinstance(mt, XAppMessageType):
            return int(mt)
        if isinstance(mt, enum.IntEnum):
            return int(mt)
        try:
            return int(mt)
        except (TypeError, ValueError):
            return int(XAppMessageType[mt])

    def _compute_crc(self, body: bytes) -> int:
        return crc16_ccitt(body)

    def pack(self) -> bytes:
        mt = self._msg_byte()
        payload = _as_bytes(self.payload)
        length = len(payload)
        header = self.sync + bytes([mt, self.seq & 0xFF]) + struct.pack("<H", length)
        body = header + payload
        crc = self._compute_crc(body)
        self.crc = crc
        return body + struct.pack("<H", crc)

    # aliases
    def serialize(self) -> bytes:
        return self.pack()

    def to_bytes(self) -> bytes:
        return self.pack()

    def encode(self) -> bytes:
        return self.pack()

    def dump(self) -> bytes:
        return self.pack()

    @classmethod
    def unpack(cls, data: BytesLike) -> "XAppPacket":
        return cls.from_bytes(data)

    @classmethod
    def from_bytes(cls, data: BytesLike) -> "XAppPacket":
        b = _as_bytes(data)
        if len(b) < HEADER_SIZE + 2:
            raise XAppFramingError("truncated packet")
        if b[:2] != SYNC_BYTES:
            raise XAppFramingError("bad sync bytes")
        msg_type = b[2]
        seq = b[3]
        length = struct.unpack_from("<H", b, 4)[0]
        if len(b) < HEADER_SIZE + length + 2:
            raise XAppFramingError("truncated payload/crc")
        payload = b[HEADER_SIZE:HEADER_SIZE + length]
        crc_off = HEADER_SIZE + length
        stored_crc = struct.unpack_from("<H", b, crc_off)[0]
        body = b[:crc_off]
        calc = crc16_ccitt(body)
        if stored_crc != calc:
            raise XAppCRCError("CRC mismatch")
        # convert msg_type to enum if possible
        try:
            mt = XAppMessageType(msg_type)
        except ValueError:
            mt = msg_type
        pkt = cls(msg_type=mt, seq=seq, payload=payload, crc=stored_crc, sync=b[:2])
        return pkt

    @classmethod
    def parse(cls, data: BytesLike) -> "XAppPacket":
        return cls.from_bytes(data)

    @classmethod
    def decode(cls, data: BytesLike) -> "XAppPacket":
        return cls.from_bytes(data)

    def verify(self) -> bool:
        body = self.sync + bytes([self._msg_byte(), self.seq & 0xFF]) + struct.pack("<H", len(self.payload)) + self.payload
        return crc16_ccitt(body) == (self.crc if self.crc is not None else 0)

    @property
    def valid(self) -> bool:
        return self.verify()

    @property
    def is_valid(self) -> bool:
        return self.verify()


# Back-compat aliases
Packet = XAppPacket
XAppFrame = XAppPacket


# ---------------------------------------------------------------------------
# Geotag payload
# ---------------------------------------------------------------------------


class XAppGeotagPayload:
    """GPS geotag payload for characteristic 0x7773."""

    def __init__(self, latitude=0.0, longitude=0.0, altitude=0.0, timestamp=None,
                 lat=None, lon=None, long=None, alt=None, ts=None, time=None,
                 utc=None, scaled=None, scale=None, mode=None, floats=None,
                 ieee754=None, use_float=None, **kwargs):
        # alias resolution
        if lat is not None:
            latitude = lat
        if lon is not None:
            longitude = lon
        if long is not None:
            longitude = long
        if alt is not None:
            altitude = alt
        if ts is not None:
            timestamp = ts
        if time is not None:
            timestamp = time
        if utc is not None:
            timestamp = utc
        if timestamp is None:
            timestamp = int(time.time()) if "time" not in kwargs else int(kwargs.get("time"))
        # mode
        if mode is None:
            if ieee754 is True or floats is True or use_float is True:
                mode = "float"
            elif scaled is False:
                mode = "float"
            elif scale is None and scaled is None:
                mode = "scaled"
            else:
                mode = "scaled"
        self.mode = str(mode).lower()
        if self.mode in ("ieee", "ieee754", "float", "double", "f"):
            self.mode = "float"
        else:
            self.mode = "scaled"
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.altitude = float(altitude)
        self.timestamp = int(timestamp)
        self.scale = int(scale) if scale is not None else 10_000_000
        self.alt_scale = 10

    # property aliases
    @property
    def lat(self):
        return self.latitude

    @property
    def lon(self):
        return self.longitude

    @property
    def long(self):
        return self.longitude

    @property
    def alt(self):
        return self.altitude

    @property
    def ts(self):
        return self.timestamp

    def _scaled(self) -> bytes:
        lat_i = int(round(self.latitude * self.scale))
        lon_i = int(round(self.longitude * self.scale))
        alt_i = int(round(self.altitude * self.alt_scale))
        return struct.pack("<iiiI", lat_i, lon_i, alt_i, self.timestamp & 0xFFFFFFFF)

    def _float(self) -> bytes:
        return struct.pack("<ddfi", self.latitude, self.longitude, float(self.altitude), self.timestamp & 0xFFFFFFFF)

    def pack(self) -> bytes:
        if self.mode == "float":
            return self._float()
        return self._scaled()

    def serialize(self) -> bytes:
        return self.pack()

    def to_bytes(self) -> bytes:
        return self.pack()

    def encode(self) -> bytes:
        return self.pack()

    @classmethod
    def unpack(cls, data: BytesLike, mode: Optional[str] = None):
        b = _as_bytes(data)
        if mode is None:
            if len(b) >= 24:
                mode = "float"
            else:
                mode = "scaled"
        if mode in ("float", "ieee", "ieee754", "double"):
            lat, lon, alt, ts = struct.unpack_from("<ddfi", b, 0)
            obj = cls(latitude=lat, longitude=lon, altitude=alt, timestamp=ts, mode="float")
            return obj
        lat_i, lon_i, alt_i, ts = struct.unpack_from("<iiiI", b, 0)
        scale = 10_000_000
        obj = cls(latitude=lat_i / scale, longitude=lon_i / scale,
                  altitude=alt_i / 10.0, timestamp=ts, mode="scaled", scale=scale)
        return obj

    @classmethod
    def from_bytes(cls, data: BytesLike, mode: Optional[str] = None):
        return cls.unpack(data, mode=mode)

    @classmethod
    def parse(cls, data: BytesLike, mode: Optional[str] = None):
        return cls.unpack(data, mode=mode)

    @classmethod
    def decode(cls, data: BytesLike, mode: Optional[str] = None):
        return cls.unpack(data, mode=mode)

    def __eq__(self, other):
        if isinstance(other, XAppGeotagPayload):
            return (self.latitude == other.latitude and self.longitude == other.longitude
                    and self.altitude == other.altitude and self.timestamp == other.timestamp)
        return False


# Back-compat aliases
GeotagPayload = XAppGeotagPayload
XAppGeoTagPayload = XAppGeotagPayload


# ---------------------------------------------------------------------------
# Activity logger
# ---------------------------------------------------------------------------


class XAppActivityLogger:
    def __init__(self, shutter_count: int = 0, film_simulation_counts: Optional[Mapping[str, int]] = None,
                 **kwargs):
        self.shutter_count = int(shutter_count or kwargs.get("total", 0) or kwargs.get("count", 0) or 0)
        counts = film_simulation_counts
        if counts is None:
            counts = kwargs.get("film_sim_counts") or kwargs.get("simulation_counts") or kwargs.get("activity_counts") or {}
        self.film_simulation_counts: Dict[str, int] = {str(k): int(v) for k, v in (counts or {}).items()}

    # property aliases
    @property
    def total_shutters(self):
        return self.shutter_count

    @total_shutters.setter
    def total_shutters(self, v):
        self.shutter_count = int(v)

    @property
    def total(self):
        return self.shutter_count

    @property
    def count(self):
        return self.shutter_count

    @property
    def film_sim_counts(self):
        return self.film_simulation_counts

    @property
    def simulation_counts(self):
        return self.film_simulation_counts

    @property
    def activity_counts(self):
        return self.film_simulation_counts

    def _norm(self, sim: Any) -> Optional[str]:
        if sim is None:
            return None
        return str(sim)

    def increment_shutter(self, simulation: Any = None, count: int = 1, amount: int = 1, **kwargs):
        n = int(kwargs.get("count", kwargs.get("amount", count if count is not None else amount)))
        if n <= 0:
            n = 1
        sim = simulation
        if sim is None:
            sim = kwargs.get("film_simulation") or kwargs.get("film_sim") or kwargs.get("simulation")
        self.shutter_count += n
        if sim is not None:
            key = self._norm(sim)
            self.film_simulation_counts[key] = self.film_simulation_counts.get(key, 0) + n
        return self.shutter_count

    # aliases
    def increment(self, *a, **kw):
        return self.increment_shutter(*a, **kw)

    def add_shutter(self, *a, **kw):
        return self.increment_shutter(*a, **kw)

    def record_shutter(self, *a, **kw):
        return self.increment_shutter(*a, **kw)

    def log_shutter(self, *a, **kw):
        return self.increment_shutter(*a, **kw)

    def record_shot(self, *a, **kw):
        return self.increment_shutter(*a, **kw)

    def log_shot(self, *a, **kw):
        return self.increment_shutter(*a, **kw)

    def record_activity(self, *a, **kw):
        return self.increment_shutter(*a, **kw)

    def add_activity(self, *a, **kw):
        return self.increment_shutter(*a, **kw)

    def aggregate(self) -> Dict[str, Any]:
        return {
            "shutter_count": self.shutter_count,
            "film_simulation_counts": dict(self.film_simulation_counts),
        }

    def to_dict(self) -> Dict[str, Any]:
        return self.aggregate()

    def to_bytes(self) -> bytes:
        # simple: shutter_count (4) + count entries
        out = struct.pack("<I", self.shutter_count)
        out += struct.pack("<I", len(self.film_simulation_counts))
        for k, v in self.film_simulation_counts.items():
            kb = k.encode("utf-8")
            out += struct.pack("<H", len(kb)) + kb + struct.pack("<I", v)
        return out

    @classmethod
    def from_bytes(cls, data: BytesLike):
        b = _as_bytes(data)
        off = 0
        shutter = struct.unpack_from("<I", b, off)[0]; off += 4
        n = struct.unpack_from("<I", b, off)[0]; off += 4
        counts = {}
        for _ in range(n):
            kl = struct.unpack_from("<H", b, off)[0]; off += 2
            key = b[off:off + kl].decode("utf-8"); off += kl
            val = struct.unpack_from("<I", b, off)[0]; off += 4
            counts[key] = val
        return cls(shutter_count=shutter, film_simulation_counts=counts)


ActivityLogger = XAppActivityLogger
XAppActivityLog = XAppActivityLogger


# ---------------------------------------------------------------------------
# Session state machine
# ---------------------------------------------------------------------------


class XAppSessionState(enum.Enum):
    UNPAIRED = "unpaired"
    PAIRING = "pairing"
    CONNECTED = "connected"
    TRANSFERRING = "transferring"
    IDLE = "idle"


# aliases
XAppState = XAppSessionState
SessionState = XAppSessionState
XAppConnectionState = XAppSessionState


@dataclass
class XAppSession:
    state: Any = XAppSessionState.UNPAIRED
    role: str = "client"
    nonce: bytes = b""
    peer_nonce: bytes = b""
    paired: bool = False
    device_info: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.state, str):
            try:
                self.state = XAppSessionState(self.state)
            except ValueError:
                self.state = XAppSessionState[self.state.upper()]

    @property
    def status(self):
        return self.state

    @status.setter
    def status(self, v):
        self.state = v if not isinstance(v, str) else XAppSessionState(v)

    @property
    def current_state(self):
        return self.state

    def _set(self, s):
        self.state = s if isinstance(s, XAppSessionState) else XAppSessionState(s)

    def generate_nonce(self, size: int = 16) -> bytes:
        return os.urandom(size)

    def start_pairing(self, nonce: Optional[bytes] = None) -> bytes:
        if nonce is None:
            nonce = self.generate_nonce()
        self.nonce = _as_bytes(nonce)
        self._set(XAppSessionState.PAIRING)
        return self.nonce

    def begin_pairing(self, *a, **kw):
        return self.start_pairing(*a, **kw)

    def enter_pairing(self, *a, **kw):
        return self.start_pairing(*a, **kw)

    def pair(self, peer_nonce: Optional[bytes] = None, nonce: Optional[bytes] = None, **kw) -> bool:
        if peer_nonce is None:
            peer_nonce = nonce
        if peer_nonce is not None:
            self.peer_nonce = _as_bytes(peer_nonce)
        self.paired = True
        self._set(XAppSessionState.PAIRING)
        return True

    def pair_request(self, nonce: Optional[bytes] = None) -> XAppPacket:
        if nonce is None:
            nonce = self.start_pairing()
        else:
            self.nonce = _as_bytes(nonce)
            self._set(XAppSessionState.PAIRING)
        return XAppPacket(XAppMessageType.PAIR_REQ, seq=0, payload=self.nonce)

    def pair_response(self, nonce: Optional[bytes] = None) -> XAppPacket:
        if nonce is None:
            nonce = self.nonce or self.generate_nonce()
        self.peer_nonce = _as_bytes(nonce)
        return XAppPacket(XAppMessageType.PAIR_RESP, seq=0, payload=self.peer_nonce)

    def verify_pairing(self, peer_nonce: Optional[bytes] = None, expected: Optional[bytes] = None) -> bool:
        if peer_nonce is not None:
            self.peer_nonce = _as_bytes(peer_nonce)
        if expected is not None and self.peer_nonce != _as_bytes(expected):
            return False
        self.paired = True
        return True

    def complete_pairing(self, *a, **kw) -> bool:
        self.paired = True
        self._set(XAppSessionState.CONNECTED)
        return True

    def connect(self, *a, **kw) -> None:
        self._set(XAppSessionState.CONNECTED)

    def begin_transfer(self, *a, **kw) -> None:
        self._set(XAppSessionState.TRANSFERRING)

    def start_transfer(self, *a, **kw) -> None:
        self.begin_transfer(*a, **kw)

    def end_transfer(self, *a, **kw) -> None:
        self._set(XAppSessionState.IDLE)

    def finish_transfer(self, *a, **kw) -> None:
        self.end_transfer(*a, **kw)

    def disconnect(self, *a, **kw) -> None:
        self._set(XAppSessionState.UNPAIRED)
        self.paired = False

    def reset(self, *a, **kw) -> None:
        self.state = XAppSessionState.UNPAIRED
        self.paired = False
        self.nonce = b""
        self.peer_nonce = b""

    def handle_packet(self, packet: Any) -> Any:
        try:
            mt = packet.msg_type if hasattr(packet, "msg_type") else packet.type
        except Exception:
            mt = None
        if mt == XAppMessageType.PAIR_REQ or mt == XAppMessageType.PAIR_REQ.value:
            self._set(XAppSessionState.PAIRING)
            return self.pair_response(getattr(packet, "payload", b""))
        if mt == XAppMessageType.PAIR_RESP or mt == XAppMessageType.PAIR_RESP.value:
            self.verify_pairing(getattr(packet, "payload", b""))
            self.complete_pairing()
            return None
        if mt == XAppMessageType.GEOTAG:
            self._set(XAppSessionState.TRANSFERRING)
            return None
        if mt in (XAppMessageType.ACTIVITY_SYNC, XAppMessageType.ACTIVITY_SYNC.value):
            return None
        return None

    # transition helpers used by tests
    def transition_to(self, state: Any):
        if isinstance(state, str):
            try:
                state = XAppSessionState(state)
            except ValueError:
                state = XAppSessionState[state.upper().replace(" ", "_")]
        self._set(state)
        return self.state

    def can_transition(self, frm, to) -> bool:
        order = [XAppSessionState.UNPAIRED, XAppSessionState.PAIRING,
                 XAppSessionState.CONNECTED, XAppSessionState.TRANSFERRING,
                 XAppSessionState.IDLE]
        # allow linear + idle->connected
        a = frm if isinstance(frm, XAppSessionState) else XAppSessionState(frm)
        b = to if isinstance(to, XAppSessionState) else XAppSessionState(to)
        if (a, b) in [(XAppSessionState.UNPAIRED, XAppSessionState.PAIRING),
                      (XAppSessionState.PAIRING, XAppSessionState.CONNECTED),
                      (XAppSessionState.CONNECTED, XAppSessionState.TRANSFERRING),
                      (XAppSessionState.TRANSFERRING, XAppSessionState.IDLE),
                      (XAppSessionState.IDLE, XAppSessionState.CONNECTED),
                      (XAppSessionState.IDLE, XAppSessionState.UNPAIRED)]:
            return True
        return False


XAppClientSession = XAppSession
XAppCameraSession = XAppSession
