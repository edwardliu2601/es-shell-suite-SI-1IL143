"""ForwardEngine exceptions."""


class ForwardEngineError(Exception):
    """Base error for the forward-chaining engine."""


class InvalidKnowledgeBaseError(ForwardEngineError):
    """Knowledge base does not match the expected contract."""


class InvalidWorkingMemoryError(ForwardEngineError):
    """Working memory does not match the expected contract."""


class ConditionEvaluationError(ForwardEngineError):
    """A rule condition could not be evaluated."""
