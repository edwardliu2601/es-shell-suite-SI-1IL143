"""Unit tests for ForwardEngine inference."""

import pytest

from grupo_05_forward.engine import ForwardEngine
from grupo_05_forward.exceptions import ConditionEvaluationError
from grupo_05_forward.models import (
    Conclusion,
    Condition,
    KnowledgeBase,
    Rule,
    WorkingMemory,
)


def test_forward_chain_derives_facts(knowledge_base, working_memory):
    engine = ForwardEngine(knowledge_base)
    result = engine.run(working_memory)

    assert "rule_01" in result.fired_rules
    assert "rule_03" in result.fired_rules
    assert "rule_04" in result.fired_rules
    assert result.working_memory.derived_facts["dictamen"].value == "Elegible"
    assert result.working_memory.derived_facts["nivel"].value == "avanzado"
    assert result.working_memory.derived_facts["materia_valida"].value is True
    assert result.halted_reason == "quiescence"
    assert len(result.working_memory.execution_trace) >= 3


def test_priority_prefers_higher_rule():
    rules = (
        Rule(
            id="low",
            description="low",
            priority=1,
            conditions=(Condition("x", "==", 1),),
            conclusion=Conclusion("y", "from_low"),
        ),
        Rule(
            id="high",
            description="high",
            priority=100,
            conditions=(Condition("x", "==", 1),),
            conclusion=Conclusion("y", "from_high"),
        ),
    )
    kb = KnowledgeBase(rules=rules)
    memory = WorkingMemory(session_id="s1", facts={"x": 1})
    result = ForwardEngine(kb).run(memory)

    assert result.fired_rules == ("high",)
    assert memory.derived_facts["y"].value == "from_high"


def test_rule_does_not_fire_when_conditions_fail(knowledge_base):
    memory = WorkingMemory(
        session_id="s2",
        facts={
            "materia": "Trabajo de Graduacion",
            "promedio": 1.0,
            "creditos": 50,
        },
    )
    result = ForwardEngine(knowledge_base).run(memory)

    assert "rule_01" not in result.fired_rules
    assert "rule_02" in result.fired_rules
    assert memory.derived_facts["dictamen"].value == "No elegible"
    assert "nivel" not in memory.derived_facts


def test_no_overwrite_existing_fact(knowledge_base):
    memory = WorkingMemory(
        session_id="s3",
        facts={
            "materia": "Trabajo de Graduacion",
            "promedio": 2.5,
            "dictamen": "Ya definido",
        },
    )
    result = ForwardEngine(knowledge_base).run(memory)

    assert "rule_01" not in result.fired_rules
    assert memory.facts["dictamen"] == "Ya definido"
    assert "dictamen" not in memory.derived_facts


def test_idempotent_second_run(knowledge_base, working_memory):
    engine = ForwardEngine(knowledge_base)
    first = engine.run(working_memory)
    second = engine.run(working_memory)

    assert first.fired_rules
    assert second.fired_rules == ()
    assert second.halted_reason == "quiescence"


def test_run_from_facts(knowledge_base):
    engine = ForwardEngine(knowledge_base)
    result = engine.run_from_facts(
        "s4",
        {
            "materia": "Trabajo de Graduacion",
            "promedio": 2.2,
            "creditos": 120,
        },
    )
    assert result.working_memory.derived_facts["dictamen"].value == "Elegible"


def test_max_steps_halt():
    rules = (
        Rule(
            id="r1",
            description="ping",
            priority=1,
            conditions=(Condition("a", "==", 1),),
            conclusion=Conclusion("b", 1),
        ),
        Rule(
            id="r2",
            description="pong",
            priority=1,
            conditions=(Condition("b", "==", 1),),
            conclusion=Conclusion("c", 1),
        ),
        Rule(
            id="r3",
            description="pung",
            priority=1,
            conditions=(Condition("c", "==", 1),),
            conclusion=Conclusion("d", 1),
        ),
    )
    engine = ForwardEngine(KnowledgeBase(rules=rules), max_steps=2)
    result = engine.run(WorkingMemory(session_id="s5", facts={"a": 1}))
    assert result.halted_reason == "max_steps"
    assert len(result.fired_rules) == 2


def test_invalid_condition_can_raise():
    rules = (
        Rule(
            id="bad",
            description="bad compare",
            priority=1,
            conditions=(Condition("a", ">", "texto"),),
            conclusion=Conclusion("out", True),
        ),
    )
    engine = ForwardEngine(
        KnowledgeBase(rules=rules),
        skip_invalid_conditions=False,
    )
    with pytest.raises(ConditionEvaluationError):
        engine.run(WorkingMemory(session_id="s6", facts={"a": 1}))


def test_trace_records_rule_and_fact(knowledge_base, working_memory):
    result = ForwardEngine(knowledge_base).run(working_memory)
    steps = result.working_memory.execution_trace
    assert steps[0].step == 1
    assert all(step.rule_fired and step.added_fact for step in steps)
