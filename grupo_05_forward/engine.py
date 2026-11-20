"""Forward-chaining inference engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from . import agenda, operators
from .exceptions import ConditionEvaluationError
from .models import (
    DerivedFact,
    InferenceResult,
    KnowledgeBase,
    Rule,
    TraceStep,
    WorkingMemory,
)


class ForwardEngine:
    """Data-driven forward chaining over SI-ENTONCES rules."""

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        *,
        max_steps: int = 10_000,
        skip_invalid_conditions: bool = True,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.max_steps = max_steps
        self.skip_invalid_conditions = skip_invalid_conditions
        # rule_id -> attribute ids already asserted by that rule
        self._fired: set[tuple[str, str]] = set()

    def reset_fire_history(self) -> None:
        self._fired.clear()

    def rule_is_satisfied(self, rule: Rule, memory: WorkingMemory) -> bool:
        for condition in rule.conditions:
            if not memory.has_fact(condition.attribute_id):
                return False
            left = memory.known_value(condition.attribute_id)
            try:
                if not operators.evaluate(condition.operator, left, condition.value):
                    return False
            except ConditionEvaluationError:
                if self.skip_invalid_conditions:
                    return False
                raise
        return True

    def collect_candidates(self, memory: WorkingMemory) -> list[Rule]:
        candidates: list[Rule] = []
        for rule in self.knowledge_base.rules:
            conclusion_key = rule.conclusion.attribute_id
            fire_key = (rule.id, conclusion_key)
            if fire_key in self._fired:
                continue
            # First assertion wins: do not overwrite existing facts.
            if memory.has_fact(conclusion_key):
                continue
            if self.rule_is_satisfied(rule, memory):
                candidates.append(rule)
        return candidates

    def fire_rule(self, rule: Rule, memory: WorkingMemory) -> str:
        attr = rule.conclusion.attribute_id
        memory.derived_facts[attr] = DerivedFact(
            value=rule.conclusion.value,
            derived_by_rule=rule.id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        step_no = len(memory.execution_trace) + 1
        memory.execution_trace.append(
            TraceStep(step=step_no, rule_fired=rule.id, added_fact=attr)
        )
        self._fired.add((rule.id, attr))
        return attr

    def run(
        self,
        memory: WorkingMemory,
        *,
        resume: bool = False,
    ) -> InferenceResult:
        """Run forward chaining until quiescence or max_steps."""
        if not resume:
            self.reset_fire_history()
            # Seed history from prior derived facts so resume-like reloads stay stable
            for attr, derived in memory.derived_facts.items():
                self._fired.add((derived.derived_by_rule, attr))

        fired_rules: list[str] = []
        newly_derived: list[str] = []
        halted_reason = "quiescence"

        for _ in range(self.max_steps):
            candidates = self.collect_candidates(memory)
            next_rule = agenda.select_next(candidates)
            if next_rule is None:
                halted_reason = "quiescence"
                break

            added = self.fire_rule(next_rule, memory)
            fired_rules.append(next_rule.id)
            newly_derived.append(added)
        else:
            halted_reason = "max_steps"

        return InferenceResult(
            working_memory=memory,
            fired_rules=tuple(fired_rules),
            newly_derived=tuple(newly_derived),
            halted_reason=halted_reason,
        )

    def run_from_facts(
        self,
        session_id: str,
        facts: dict,
        *,
        extra_rules: Iterable[Rule] | None = None,
    ) -> InferenceResult:
        if extra_rules:
            combined = KnowledgeBase(
                rules=tuple(self.knowledge_base.rules) + tuple(extra_rules),
                meta=dict(self.knowledge_base.meta),
                attributes=self.knowledge_base.attributes,
            )
            engine = ForwardEngine(
                combined,
                max_steps=self.max_steps,
                skip_invalid_conditions=self.skip_invalid_conditions,
            )
            memory = WorkingMemory(session_id=session_id, facts=dict(facts))
            return engine.run(memory)

        memory = WorkingMemory(session_id=session_id, facts=dict(facts))
        return self.run(memory)
