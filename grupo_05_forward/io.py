"""Load and dump knowledge base / working memory JSON contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exceptions import InvalidKnowledgeBaseError, InvalidWorkingMemoryError
from .models import (
    Conclusion,
    Condition,
    DerivedFact,
    KnowledgeBase,
    Rule,
    TraceStep,
    WorkingMemory,
)


def _require_mapping(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError(f"{label} must be a JSON object")
    return payload


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    return _require_mapping(data, str(path))


def dump_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def parse_condition(raw: dict[str, Any]) -> Condition:
    try:
        return Condition(
            attribute_id=raw["attribute_id"],
            operator=raw["operator"],
            value=raw["value"],
        )
    except KeyError as exc:
        raise InvalidKnowledgeBaseError(
            f"Condition is missing required field: {exc}"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise InvalidKnowledgeBaseError(str(exc)) from exc


def parse_rule(raw: dict[str, Any]) -> Rule:
    try:
        conditions = tuple(parse_condition(item) for item in raw["conditions"])
        conclusion_raw = raw["conclusion"]
        conclusion = Conclusion(
            attribute_id=conclusion_raw["attribute_id"],
            value=conclusion_raw["value"],
        )
        return Rule(
            id=raw["id"],
            description=raw.get("description", ""),
            priority=int(raw["priority"]),
            conditions=conditions,
            conclusion=conclusion,
            explanation_template=raw.get("explanation_template", ""),
        )
    except KeyError as exc:
        raise InvalidKnowledgeBaseError(
            f"Rule is missing required field: {exc}"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise InvalidKnowledgeBaseError(str(exc)) from exc


def parse_knowledge_base(payload: dict[str, Any]) -> KnowledgeBase:
    try:
        rules_raw = payload["rules"]
        if not isinstance(rules_raw, list) or not rules_raw:
            raise InvalidKnowledgeBaseError("'rules' must be a non-empty list")
        rules = tuple(parse_rule(item) for item in rules_raw)
        attributes = tuple(payload.get("attributes", []))
        meta = dict(payload.get("meta", {}))
        return KnowledgeBase(rules=rules, meta=meta, attributes=attributes)
    except KeyError as exc:
        raise InvalidKnowledgeBaseError(
            f"Knowledge base is missing required field: {exc}"
        ) from exc


def parse_working_memory(payload: dict[str, Any]) -> WorkingMemory:
    try:
        session_id = payload["session_id"]
        if not isinstance(session_id, str) or not session_id:
            raise InvalidWorkingMemoryError("session_id must be a non-empty string")

        facts = dict(payload.get("facts", {}))
        if not isinstance(facts, dict):
            raise InvalidWorkingMemoryError("'facts' must be an object")

        derived_raw = payload.get("derived_facts", {})
        if not isinstance(derived_raw, dict):
            raise InvalidWorkingMemoryError("'derived_facts' must be an object")

        derived_facts: dict[str, DerivedFact] = {}
        for key, item in derived_raw.items():
            if not isinstance(item, dict):
                raise InvalidWorkingMemoryError(
                    f"derived_facts[{key!r}] must be an object"
                )
            derived_facts[key] = DerivedFact(
                value=item["value"],
                derived_by_rule=item["derived_by_rule"],
                certainty_factor=item.get("certainty_factor"),
                timestamp=item.get(
                    "timestamp",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        trace_raw = payload.get("execution_trace", [])
        if not isinstance(trace_raw, list):
            raise InvalidWorkingMemoryError("'execution_trace' must be a list")

        execution_trace: list[TraceStep] = []
        for item in trace_raw:
            execution_trace.append(
                TraceStep(
                    step=int(item["step"]),
                    rule_fired=item["rule_fired"],
                    added_fact=item["added_fact"],
                )
            )

        return WorkingMemory(
            session_id=session_id,
            facts=facts,
            derived_facts=derived_facts,
            execution_trace=execution_trace,
        )
    except KeyError as exc:
        raise InvalidWorkingMemoryError(
            f"Working memory is missing required field: {exc}"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise InvalidWorkingMemoryError(str(exc)) from exc


def working_memory_to_dict(memory: WorkingMemory) -> dict[str, Any]:
    derived: dict[str, Any] = {}
    for key, fact in memory.derived_facts.items():
        entry: dict[str, Any] = {
            "value": fact.value,
            "derived_by_rule": fact.derived_by_rule,
            "timestamp": fact.timestamp,
        }
        if fact.certainty_factor is not None:
            entry["certainty_factor"] = fact.certainty_factor
        derived[key] = entry

    return {
        "session_id": memory.session_id,
        "facts": dict(memory.facts),
        "derived_facts": derived,
        "execution_trace": [
            {
                "step": step.step,
                "rule_fired": step.rule_fired,
                "added_fact": step.added_fact,
            }
            for step in memory.execution_trace
        ],
    }


def load_knowledge_base(path: str | Path) -> KnowledgeBase:
    return parse_knowledge_base(load_json(path))


def load_working_memory(path: str | Path) -> WorkingMemory:
    return parse_working_memory(load_json(path))


def save_working_memory(path: str | Path, memory: WorkingMemory) -> None:
    dump_json(path, working_memory_to_dict(memory))
