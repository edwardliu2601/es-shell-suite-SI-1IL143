"""Unit tests for conflict-resolution agenda."""

from grupo_05_forward.agenda import select_next, sort_by_priority
from grupo_05_forward.models import Conclusion, Condition, Rule


def _rule(rule_id: str, priority: int) -> Rule:
    return Rule(
        id=rule_id,
        description=rule_id,
        priority=priority,
        conditions=(
            Condition(attribute_id="x", operator="==", value=1),
        ),
        conclusion=Conclusion(attribute_id="y", value=True),
    )


def test_sort_by_priority_descending():
    rules = [_rule("low", 1), _rule("high", 50), _rule("mid", 10)]
    ordered = sort_by_priority(rules)
    assert [r.id for r in ordered] == ["high", "mid", "low"]


def test_tie_break_by_id():
    rules = [_rule("b", 10), _rule("a", 10)]
    ordered = sort_by_priority(rules)
    assert [r.id for r in ordered] == ["a", "b"]


def test_select_next_empty():
    assert select_next([]) is None


def test_select_next_picks_highest():
    rules = [_rule("low", 1), _rule("high", 99)]
    assert select_next(rules).id == "high"
