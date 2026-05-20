"""Application-specific exceptions."""


class RagMcpError(Exception):
    """Base exception for the application."""


class ConfigurationError(RagMcpError):
    """Raised when configuration is invalid."""


class IngestionError(RagMcpError):
    """Raised when ingestion fails."""


class SourceValidationError(IngestionError):
    """Raised when a local source file fails validation checks."""


class QueryError(RagMcpError):
    """Raised when query execution fails."""


class EvaluationError(RagMcpError):
    """Raised when evaluation execution fails."""


class ProviderError(RagMcpError):
    """Raised when an external model provider call fails."""


class NotFoundError(RagMcpError):
    """Raised when a requested entity does not exist."""
