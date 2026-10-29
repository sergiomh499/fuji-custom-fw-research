"""Declarative camera model definitions."""

from .base import CameraModel
from .xt10 import XT10Model, XT10_MODEL
from .x10 import X10Model, X10_MODEL
from .xt20 import XT20Model, XT20_MODEL
from .xt30 import XT30Model, XT30_MODEL
from .registry import ALL_MODELS, get_model_by_id, resolve_model_from_code

__all__ = [
    "CameraModel",
    "XT10Model",
    "XT10_MODEL",
    "X10Model",
    "X10_MODEL",
    "XT20Model",
    "XT20_MODEL",
    "XT30Model",
    "XT30_MODEL",
    "ALL_MODELS",
    "get_model_by_id",
    "resolve_model_from_code",
]
