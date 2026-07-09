"""Risk policy decision helpers."""

from __future__ import annotations


def should_block_by_risk(decision: str, *, block_on_restrict: bool) -> bool:
    """Return whether a risk decision should block processing."""
    return decision == "block" or (decision == "restrict" and block_on_restrict)
