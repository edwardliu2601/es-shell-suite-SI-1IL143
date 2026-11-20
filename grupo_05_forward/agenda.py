"""Conflict resolution for activatable rules."""

from __future__ import annotations

from .models import Rule


def sort_by_priority(rules: list[Rule]) -> list[Rule]:
    """Sort candidates: higher priority first; ties broken by rule id."""
    return sorted(rules, key=lambda rule: (-rule.priority, rule.id))


def select_next(rules: list[Rule]) -> Rule | None:
    """Pick the next rule to fire under the engine policy."""
    if not rules:
        return None
    return sort_by_priority(rules)[0]
