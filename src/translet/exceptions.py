class TransletError(Exception):
    """Base class for all translet errors."""


class ConversionError(TransletError):
    """Raised when a JSON conversion fails after exhausting retries."""

    def __init__(self, message: str, *, key: str | None = None, last_error: Exception | None = None):
        super().__init__(message)
        self.key = key
        self.last_error = last_error


class RuleGenerationError(TransletError):
    """Raised when the LLM fails to produce a usable JSONata rule."""


class StoreError(TransletError):
    """Raised on rule storage backend failures."""


class JsonataError(TransletError):
    """Raised when a JSONata expression fails to compile or evaluate."""


class ValidationError(TransletError):
    """Raised when a converted result does not match the target specification."""

    def __init__(self, message: str, *, expected: object = None, actual: object = None):
        super().__init__(message)
        self.expected = expected
        self.actual = actual
