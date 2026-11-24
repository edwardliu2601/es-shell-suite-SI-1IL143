"""Grupo 6 - BackwardEngine (encadenamiento hacia atras)."""

from .esb_engine_backward import (
    BackwardEngine,
    BackwardEngineError,
    BackwardResult,
    InvalidAnswerError,
    InvalidKnowledgeBaseError,
    InvalidWorkingMemoryError,
    Question,
    evaluate,
)

__all__ = [
    "BackwardEngine",
    "BackwardEngineError",
    "BackwardResult",
    "InvalidAnswerError",
    "InvalidKnowledgeBaseError",
    "InvalidWorkingMemoryError",
    "Question",
    "evaluate",
]

__version__ = "0.1.0"
