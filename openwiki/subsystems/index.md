# Files

- [DSP Film Simulation & Color Pipeline](color_pipeline.md) - Reverse-engineered architecture of Fujifilm DSP color transformation matrices, Q12/Q15 fixed-point arithmetic, 1D tone curves, and 3D-LUT compilation.
- [X-Mount Electronic Lens Protocol & Snap Focus](lens_and_focus.md) - Reverse-engineered Fujifilm X-mount electronic lens SPI protocol, packet framing, motor stepping commands, and standalone ARMv7-A Snap Focus payload.
- [OSD Framebuffer & Live Telemetry](osd_telemetry.md) - Architecture of the Fujifilm X-T10 On-Screen Display (OSD) framebuffer, liveview overlay injection, and volatile USB PTP memory telemetry.
- [Recipe Persistence (C1-C7) & SD Card Exchange](recipe_persistence.md) - Serialization of Fujifilm custom film simulation recipes (C1-C7) in EEPROM binary structs and human-readable SD card exchange format.
- [KASAGO TCP/IP Stack & Wi-Fi Crash Remediation](wifi_networking.md) - Root-cause analysis of the KASAGO TCP/IP buffer depletion crash when connecting modern smartphones to Fujifilm X-T10, and defensive patching implementation.
