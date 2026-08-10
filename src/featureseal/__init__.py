"""Deterministic point-in-time feature-join receipts."""

from featureseal.engine import analyze_document
from featureseal.verify import verify_receipt

__all__ = ["analyze_document", "verify_receipt"]
__version__ = "0.1.0"
