"""Grupo 5 — ForwardEngine library (forward chaining)."""

from .agenda import select_next, sort_by_priority
from .engine import ForwardEngine
from .exceptions import (
    ConditionEvaluationError,
    ForwardEngineError,
    InvalidKnowledgeBaseError,
    InvalidWorkingMemoryError,
)
from .io import (
    load_knowledge_base,
    load_working_memory,
    parse_knowledge_base,
    parse_working_memory,
    save_working_memory,
    working_memory_to_dict,
)
from .models import (
    Conclusion,
    Condition,
    DerivedFact,
    InferenceResult,
    KnowledgeBase,
    Rule,
    TraceStep,
    WorkingMemory,
)

__all__ = [
    "Conclusion",
    "Condition",
    "ConditionEvaluationError",
    "DerivedFact",
    "ForwardEngine",
    "ForwardEngineError",
    "InferenceResult",
    "InvalidKnowledgeBaseError",
    "InvalidWorkingMemoryError",
    "KnowledgeBase",
    "Rule",
    "TraceStep",
    "WorkingMemory",
    "load_knowledge_base",
    "load_working_memory",
    "parse_knowledge_base",
    "parse_working_memory",
    "save_working_memory",
    "select_next",
    "sort_by_priority",
    "working_memory_to_dict",
]

__version__ = "0.1.0"
