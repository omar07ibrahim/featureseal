"""Public FeatureSeal exception types."""


class FeatureSealError(ValueError):
    """Base class for expected FeatureSeal failures."""


class ContractError(FeatureSealError):
    """Raised when a snapshot violates the bounded input contract."""


class VerificationError(FeatureSealError):
    """Raised when a receipt cannot be independently replayed."""
