"""Unit tests for condition operators."""

import pytest

from grupo_05_forward.exceptions import ConditionEvaluationError
from grupo_05_forward.operators import evaluate


@pytest.mark.parametrize(
    ("op", "left", "right", "expected"),
    [
        ("==", 2, 2, True),
        ("==", "a", "b", False),
        ("!=", 1, 2, True),
        (">", 3, 2, True),
        ("<", 1, 5, True),
        (">=", 2.0, 2.0, True),
        ("<=", 1.5, 2.0, True),
        ("in", "TG", ["TG", "SI"], True),
        ("in", "X", ["TG", "SI"], False),
    ],
)
def test_evaluate_operators(op, left, right, expected):
    assert evaluate(op, left, right) is expected


def test_unsupported_operator_raises():
    with pytest.raises(ConditionEvaluationError):
        evaluate("~=", 1, 1)


def test_in_requires_collection():
    with pytest.raises(ConditionEvaluationError):
        evaluate("in", "a", "abc")


def test_ordered_compare_type_error():
    with pytest.raises(ConditionEvaluationError):
        evaluate(">", "texto", 10)
