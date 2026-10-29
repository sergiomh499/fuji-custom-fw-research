"""Central registry of supported camera models."""

from .xt10 import XT10_MODEL
from .x10 import X10_MODEL
from .xt20 import XT20_MODEL
from .xt30 import XT30_MODEL

ALL_MODELS = [XT10_MODEL, X10_MODEL, XT20_MODEL, XT30_MODEL]


def get_model_by_id(model_id: str):
    for model in ALL_MODELS:
        if model.id == model_id:
            return model
    return None


def resolve_model_from_code(model_code: str):
    for model in ALL_MODELS:
        if model_code.startswith(model.model_code_prefix):
            return model
    return None
