"""Film simulation token registry (compatibility shim)."""

from core.film_simulation import (
    FilmSimulationExtractor,
    FilmSimulationPatcher,
    TOKENS,
)

# Backwards-compatible registry used by older callers/tests.
class FilmSimulationRegistry:
    TOKENS = {k: v for k, v in TOKENS.items()}
    tokens = TOKENS
    FILM_SIM_TOKENS = TOKENS

    @classmethod
    def parse_tokens(cls, data, search_range=(0x0024FB10, 0x0024FB80)):
        return FilmSimulationExtractor.parse_tokens(data, search_range)


__all__ = ["FilmSimulationRegistry", "FilmSimulationExtractor", "FilmSimulationPatcher"]
