"""Checksum helpers for Fujifilm firmware containers."""


def calculate_delta(orig_sum: int, new_sum: int, orig_checksum: int) -> int:
    """Return the adjusted checksum after a payload sum change."""
    return (orig_checksum - (new_sum - orig_sum)) & 0xFFFFFFFF
