"""On-Screen Display (OSD) framebuffer helpers for the Fujifilm X-T10.

Reverse-engineered X-T10 v1.31 display facts:
  * OSD debug routine: ``0x007f9c1c`` (``OSD DEBUG MODE SCREEN SELECT``).
  * Display buffer descriptor pointer: ``0x01b59bd4``.
  * Resolution: 640x480, RGB565 / YUV422 packed, 307200 bytes per buffer.

Failure mitigation (buffer corruption is volatile RAM only, never flash):
  * Do NOT write these helpers into early-boot or flash paths. Keep them behind
    the secondary cold-hook trampoline so a fault only resets RAM.
  * Mitigation: docs/BRICK_ANALYSIS_AND_RECOVERY.md#cold-hooking
  * Volatile/PTP RAM recovery (pull battery, 0% flash risk):
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery
  * Firmware repacking/patching recovery (DISP/BACK forced update):
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery
  * Hardware flashing recovery (SPI Pomona 5250 + CH341A flashrom):
    docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence, Tuple, Union

BytesLike = Union[bytes, bytearray, memoryview]

WIDTH = 640
HEIGHT = 480
BUFFER_SIZE = 307200  # 640 * 480

OSD_DEBUG_ROUTINE = 0x007F9C1C
DISPLAY_BUFFER_PTR = 0x01B59BD4

GUIDE_THIRDS = "thirds"
GUIDE_16_9 = "16:9"
GUIDE_ANAMORPHIC = "2.39:1"
GUIDE_XPAN = "65:24"
GUIDE_SQUARE = "1:1"

def rgb565(r: int, g: int, b: int) -> int:
    """Encode an 8-bit RGB triple as a 16-bit RGB565 value."""
    r = max(0, min(255, int(r))) >> 3
    g = max(0, min(255, int(g))) >> 2
    b = max(0, min(255, int(b))) >> 3
    return (r << 11) | (g << 5) | b


def yuv422(y: int, u: int, v: int) -> int:
    """Pack a YUV422 sample into a 16-bit word (Y high, UV low)."""
    y = max(0, min(255, int(y)))
    u = max(0, min(255, int(u)))
    v = max(0, min(255, int(v)))
    return (y << 8) | ((u + v) // 2 & 0xFF)


def zebra_stripe(x: int, y: int, luma: int, threshold: int = 235,
                 stripe: int = 4) -> bool:
    """Return True if pixel (x,y) with luminance ``luma`` should be striped.

    Classic diagonal zebra: only overexposed pixels (luma >= threshold) and only
    on alternating diagonal bands so the stripe pattern is visible.
    """
    if luma < threshold:
        return False
    band = (x + y) // stripe
    return (band % 2) != 0


def peaking_highlight(gradient: int, threshold: int = 40) -> bool:
    """Return True if an edge with magnitude ``gradient`` should be highlighted."""
    return int(gradient) >= int(threshold)


def _false_color_rgb565(luma: int) -> int:
    """Map a luminance value (0-255) to a false-color RGB565 value."""
    l = max(0, min(255, int(luma)))
    if l < 5:
        return rgb565(128, 0, 128)   # clipped blacks (purple)
    if l <= 25:
        return rgb565(0, 0, 255)     # shadows (blue)
    if 95 <= l <= 110:
        return rgb565(0, 255, 0)     # 18% gray (green)
    if 130 <= l <= 150:
        return rgb565(255, 128, 192) # skin tones (pink)
    if 165 <= l <= 191:
        return rgb565(192, 192, 192) # highlights (light gray)
    if l > 250:
        return rgb565(255, 0, 0)     # clipped whites (red)
    return rgb565(l, l, l)


def draw_false_color(luma_buffer: "BytesLike", width: int = 640,
                    height: int = 480) -> list:
    """Map a luminance buffer into false-color RGB565 values.

    Returns a list of ``width * height`` RGB565 ints.
    """
    n = width * height
    out = [0] * n
    for i in range(n):
        lum = 0
        if i < len(luma_buffer):
            lum = luma_buffer[i]
        out[i] = _false_color_rgb565(lum)
    return out


def _bresenham(fb: "OSDFramebuffer", x0: int, y0: int, x1: int, y1: int,
               value: int) -> None:
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        fb.set_pixel(x0, y0, value)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


@dataclass
class OSDFramebuffer:
    """Mutable view over a 640x480 OSD display buffer (307200 bytes).

    Mitigation for buffer corruption: docs/BRICK_ANALYSIS_AND_RECOVERY.md#cold-hooking
    (volatile RAM only; pull battery to recover, 0% flash risk).
    """

    width: int = WIDTH
    height: int = HEIGHT
    fmt: str = "rgb565"
    buffer: bytearray = field(default=None)

    def __post_init__(self) -> None:
        if self.buffer is None:
            self.buffer = bytearray(self.width * self.height)
        if len(self.buffer) != self.width * self.height:
            raise ValueError(
                f"buffer size {len(self.buffer)} != {self.width * self.height}"
            )
        self._ensure_size()

    def _ensure_size(self) -> None:
        if len(self.buffer) != self.width * self.height:
            raise ValueError("invalid framebuffer size")

    def clear(self, value: int = 0) -> None:
        for i in range(len(self.buffer)):
            self.buffer[i] = value & 0xFF

    def _idx(self, x: int, y: int) -> int:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return -1
        return y * self.width + x

    def set_pixel(self, x: int, y: int, value: int = 0xFF) -> bool:
        idx = self._idx(x, y)
        if idx < 0:
            return False
        self.buffer[idx] = int(value) & 0xFF
        return True

    def get_pixel(self, x: int, y: int) -> int:
        idx = self._idx(x, y)
        if idx < 0:
            return 0
        return self.buffer[idx]

    def draw_hline(self, y: int, x0: int = 0, x1: int | None = None,
                   value: int = 0xFF) -> None:
        if x1 is None:
            x1 = self.width - 1
        for x in range(max(0, x0), min(self.width, x1 + 1)):
            self.set_pixel(x, y, value)

    def draw_vline(self, x: int, y0: int = 0, y1: int | None = None,
                   value: int = 0xFF) -> None:
        if y1 is None:
            y1 = self.height - 1
        for y in range(max(0, y0), min(self.height, y1 + 1)):
            self.set_pixel(x, y, value)

    def draw_rect(self, x0: int, y0: int, x1: int, y1: int,
                  value: int = 0xFF) -> None:
        self.draw_hline(y0, x0, x1, value)
        self.draw_hline(y1, x0, x1, value)
        self.draw_vline(x0, y0, y1, value)
        self.draw_vline(x1, y0, y1, value)

    def draw_framing_guides(self, guide: str = GUIDE_THIRDS) -> None:
        """Draw framing guide overlays.

        Supported guides: ``thirds``, ``16:9``, ``2.39:1`` (anamorphic), ``65:24`` (XPan), ``1:1`` (square).
        """
        if guide == GUIDE_THIRDS or guide == "all":
            for frac in (1 / 3, 2 / 3):
                self.draw_vline(int(self.width * frac), 0, self.height - 1)
                self.draw_hline(int(self.height * frac), 0, self.width - 1)
        if guide == GUIDE_16_9 or guide == "all":
            # 16:9 letterbox bars for a 4:3 LCD.
            target_h = int(self.width * 9 / 16)
            bar = (self.height - target_h) // 2
            for y in range(0, bar):
                self.draw_hline(y, 0, self.width - 1)
            for y in range(self.height - bar, self.height):
                self.draw_hline(y, 0, self.width - 1)
        if guide == GUIDE_ANAMORPHIC or guide == "all":
            target_h = int(self.width / 2.39)
            bar = (self.height - target_h) // 2
            for y in range(0, bar):
                self.draw_hline(y, 0, self.width - 1)
            for y in range(self.height - bar, self.height):
                self.draw_hline(y, 0, self.width - 1)
        if guide == GUIDE_XPAN or guide == "all":
            # Hasselblad XPan panoramic aspect ratio 65:24
            target_h = int(self.width * 24 / 65)
            bar = (self.height - target_h) // 2
            for y in range(0, bar):
                self.draw_hline(y, 0, self.width - 1)
            for y in range(self.height - bar, self.height):
                self.draw_hline(y, 0, self.width - 1)
        if guide == GUIDE_SQUARE or guide == "all":
            # 1:1 Square crop (pillarbox on 4:3 LCD)
            target_w = self.height
            pillar = (self.width - target_w) // 2
            for x in range(0, pillar):
                self.draw_vline(x, 0, self.height - 1)
            for x in range(self.width - pillar, self.width):
                self.draw_vline(x, 0, self.height - 1)
    # aliases
    draw_grid = draw_framing_guides
    draw_guides = draw_framing_guides

    def draw_zebra(self, threshold: int = 235, stripe: int = 4,
                   luma: int | None = None) -> None:
        """Draw diagonal zebra stripes across overexposed regions.

        If ``luma`` is provided it is treated as a uniform luminance for the
        whole frame (useful for synthetic tests); otherwise the existing buffer
        values are used as luminance.
        """
        for y in range(self.height):
            for x in range(self.width):
                lum = luma if luma is not None else self.get_pixel(x, y)
                if zebra_stripe(x, y, lum, threshold, stripe):
                    self.set_pixel(x, y, 0xFF)

    draw_zebra_stripes = draw_zebra

    def draw_peaking(self, threshold: int = 40,
                     gradients: Sequence[int] | None = None) -> None:
        """Draw peaking edge highlights.

        ``gradients`` may be a flat sequence of length width*height; pixels whose
        gradient >= threshold are highlighted.
        """
        if gradients is None:
            # Highlight a default centre crosshair as a stand-in edge.
            cx, cy = self.width // 2, self.height // 2
            for d in range(-2, 3):
                self.set_pixel(cx + d, cy, 0xFF)
                self.set_pixel(cx, cy + d, 0xFF)
            return
        for i, g in enumerate(gradients):
            if i >= len(self.buffer):
                break
            if peaking_highlight(g, threshold):
                self.buffer[i] = 0xFF

    draw_peaking_mask = draw_peaking

    def draw_artificial_horizon(self, pitch_deg: float, roll_deg: float,
                               tolerance: float = 0.5, color: int = 0xFF) -> None:
        """Draw a 2-axis artificial horizon (roll + pitch) centered on the frame.

        Level (|roll|, |pitch| <= tolerance) renders in green (0x07E0).
        """
        import math
        level = abs(roll_deg) <= tolerance and abs(pitch_deg) <= tolerance
        col = 0x07E0 if level else (color & 0xFF)
        # color may be rgb565; store low byte for byte framebuffer
        if isinstance(col, int) and col > 0xFF:
            col = col & 0xFF
        cx, cy0 = self.width // 2, self.height // 2
        pitch_shift = int(pitch_deg * 4.0)
        cy = cy0 + pitch_shift
        half = max(self.width, self.height)
        ang = math.radians(roll_deg)
        dx = int(math.cos(ang) * half)
        dy = int(math.sin(ang) * half)
        _bresenham(self, cx - dx, cy - dy, cx + dx, cy + dy, col)
        # pitch ladder: a few parallel lines
        for off in (-60, -30, 30, 60):
            px = int(-math.sin(ang) * off)
            py = int(math.cos(ang) * off)
            _bresenham(self, cx - dx + px, cy - dy + py,
                       cx + dx + px, cy + dy + py, col)
        # reference roll tick at centre
        _bresenham(self, cx - 10, cy, cx + 10, cy, col)

    def draw_false_color(self, luma_buffer, width: int | None = None,
                         height: int | None = None):
        if width is None:
            width = self.width
        if height is None:
            height = self.height
        out = draw_false_color(luma_buffer, width, height)
        for i, v in enumerate(out):
            if i < len(self.buffer):
                self.buffer[i] = int(v) & 0xFF
        return out

    def draw_status_bar(self, battery_voltage: float | None = None,
                        sensor_temp: float | None = None,
                        text: str | None = None) -> None:
        """Render a custom text status bar along the top of the OSD buffer."""
        if text is None:
            parts = []
            if battery_voltage is not None:
                parts.append(f"BAT {battery_voltage:.2f}V")
            if sensor_temp is not None:
                parts.append(f"TEMP {sensor_temp:.1f}C")
            text = "  ".join(parts)
        text = text or ""
        # Simple 1-byte-per-column marker: write code points into top row region.
        for i, ch in enumerate(text[: self.width]):
            self.set_pixel(i, 0, ord(ch) & 0xFF)
        # Draw a separator line under the status bar.
        self.draw_hline(8, 0, self.width - 1, 0xFF)


# Backwards/alias friendly module-level names.
OSD_DEBUG_OFFSET = OSD_DEBUG_ROUTINE
DISPLAY_BUFFER_OFFSET = DISPLAY_BUFFER_PTR
MITIGATION_LINK = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#cold-hooking"
PTP_RAM_RECOVERY_LINK = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#ptp-ram-recovery"
FIRMWARE_LEVEL_RECOVERY_LINK = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#firmware-level-recovery"
HARD_BRICK_RECOVERY_LINK = "docs/BRICK_ANALYSIS_AND_RECOVERY.md#level-3-hard-brick--recovery"
