"""Declarative base model for Fujifilm cameras."""

from dataclasses import dataclass, field


@dataclass
class CameraModel:
    """A declarative description of a supported camera model."""

    id: str
    name: str
    model_code_prefix: str
    processor: str
    sensor: str
    latest_fw: str
    fw_filename: str
    dl_url: str
    virtual_delta: int = 0
    known_offsets: dict = field(default_factory=dict)
