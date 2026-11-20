"""Internal models aligned with the shared JSON contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SUPPORTED_OPERATORS = ("==", "!=", ">", "<", ">=", "<=", "in")


@dataclass(frozen=True, slots=True)
class Condition:
    attribute_id: str
    operator: str
    value: Any

    def __post_init__(self) -> None:
        if not self.attribute_id:
            raise ValueError("condition.attribute_id cannot be empty")
        if self.operator not in SUPPORTED_OPERATORS:
            raise ValueError(f"Unsupported operator: {self.operator}")
        if self.operator == "in" and not isinstance(self.value, list):
            raise ValueError("Operator 'in' requires a list value")


@dataclass(frozen=True, slots=True)
class Conclusion:
    attribute_id: str
    value: Any

    def __post_init__(self) -> None:
        if not self.attribute_id:
            raise ValueError("conclusion.attribute_id cannot be empty")


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    description: str
    priority: int
    conditions: tuple[Condition, ...]
    conclusion: Conclusion
    explanation_template: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("rule.id cannot be empty")
        if not self.conditions:
            raise ValueError(f"Rule {self.id} must have at least one condition")


@dataclass(frozen=True, slots=True)
class DerivedFact:
    value: Any
    derived_by_rule: str
    certainty_factor: float | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True, slots=True)
class TraceStep:
    step: int
    rule_fired: str
    added_fact: str


@dataclass(slots=True)
class WorkingMemory:
    """Working memory for one reasoning session."""

    session_id: str
    facts: dict[str, Any] = field(default_factory=dict)
    derived_facts: dict[str, DerivedFact] = field(default_factory=dict)
    execution_trace: list[TraceStep] = field(default_factory=list)

    def known_value(self, attribute_id: str) -> Any | None:
        if attribute_id in self.facts:
            return self.facts[attribute_id]
        if attribute_id in self.derived_facts:
            return self.derived_facts[attribute_id].value
        return None

    def has_fact(self, attribute_id: str) -> bool:
        return attribute_id in self.facts or attribute_id in self.derived_facts

    def all_facts(self) -> dict[str, Any]:
        merged = dict(self.facts)
        for key, derived in self.derived_facts.items():
            merged[key] = derived.value
        return merged


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    rules: tuple[Rule, ...]
    meta: dict[str, Any] = field(default_factory=dict)
    attributes: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.rules:
            raise ValueError("Knowledge base must include at least one rule")


@dataclass(frozen=True, slots=True)
class InferenceResult:
    """Outcome of one forward-chaining run."""

    working_memory: WorkingMemory
    fired_rules: tuple[str, ...]
    newly_derived: tuple[str, ...]
    halted_reason: str
