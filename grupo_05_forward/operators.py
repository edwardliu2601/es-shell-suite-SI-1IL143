"""Condition operator evaluation."""

from __future__ import annotations

from typing import Any, Callable

from .exceptions import ConditionEvaluationError

OperatorFn = Callable[[Any, Any], bool]


def _compare_ordered(left: Any, right: Any, op: str) -> bool:
    try:
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
    except TypeError as exc:
        raise ConditionEvaluationError(
            f"Cannot compare {left!r} and {right!r} with '{op}'"
        ) from exc
    raise ConditionEvaluationError(f"Unknown ordered operator: {op}")


def eval_eq(left: Any, right: Any) -> bool:
    return left == right


def eval_ne(left: Any, right: Any) -> bool:
    return left != right


def eval_gt(left: Any, right: Any) -> bool:
    return _compare_ordered(left, right, ">")


def eval_lt(left: Any, right: Any) -> bool:
    return _compare_ordered(left, right, "<")


def eval_ge(left: Any, right: Any) -> bool:
    return _compare_ordered(left, right, ">=")


def eval_le(left: Any, right: Any) -> bool:
    return _compare_ordered(left, right, "<=")


def eval_in(left: Any, right: Any) -> bool:
    if not isinstance(right, (list, tuple, set)):
        raise ConditionEvaluationError(
            f"Operator 'in' requires a collection, got {type(right).__name__}"
        )
    return left in right


OPERATORS: dict[str, OperatorFn] = {
    "==": eval_eq,
    "!=": eval_ne,
    ">": eval_gt,
    "<": eval_lt,
    ">=": eval_ge,
    "<=": eval_le,
    "in": eval_in,
}


def evaluate(operator: str, left: Any, right: Any) -> bool:
    """Evaluate ``left <operator> right``."""
    fn = OPERATORS.get(operator)
    if fn is None:
        raise ConditionEvaluationError(f"Unsupported operator: {operator}")
    return fn(left, right)
