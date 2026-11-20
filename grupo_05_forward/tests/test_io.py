"""Unit tests for JSON contract loaders."""

import pytest

from grupo_05_forward.exceptions import (
    InvalidKnowledgeBaseError,
    InvalidWorkingMemoryError,
)
from grupo_05_forward.io import (
    parse_knowledge_base,
    parse_working_memory,
    save_working_memory,
    working_memory_to_dict,
)


def test_load_fixtures(knowledge_base, working_memory):
    assert len(knowledge_base.rules) == 4
    assert working_memory.session_id == "session-test-001"
    assert working_memory.facts["promedio"] == 2.5


def test_roundtrip_working_memory(working_memory, tmp_path):
    path = tmp_path / "memoria.json"
    save_working_memory(path, working_memory)
    payload = path.read_text(encoding="utf-8")
    assert "session-test-001" in payload

    as_dict = working_memory_to_dict(working_memory)
    restored = parse_working_memory(as_dict)
    assert restored.session_id == working_memory.session_id
    assert restored.facts == working_memory.facts


def test_invalid_knowledge_base_missing_rules():
    with pytest.raises(InvalidKnowledgeBaseError):
        parse_knowledge_base({"meta": {}, "attributes": []})


def test_invalid_rule_operator():
    payload = {
        "meta": {"project_title": "t", "version": "1", "author_group": "g"},
        "attributes": [{"id": "a", "name": "A", "type": "text"}],
        "rules": [
            {
                "id": "r1",
                "description": "bad",
                "priority": 1,
                "conditions": [
                    {"attribute_id": "a", "operator": "~~", "value": 1}
                ],
                "conclusion": {"attribute_id": "b", "value": 1},
                "explanation_template": "",
            }
        ],
    }
    with pytest.raises(InvalidKnowledgeBaseError):
        parse_knowledge_base(payload)


def test_invalid_working_memory_session():
    with pytest.raises(InvalidWorkingMemoryError):
        parse_working_memory(
            {
                "session_id": "",
                "facts": {},
                "derived_facts": {},
                "execution_trace": [],
            }
        )
