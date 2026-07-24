"""Errors raised by Hermes lifecycle operations."""

from __future__ import annotations

from bho.core.hermes.models import HermesStatus


class HermesOperationError(RuntimeError):
    """Raised when a Hermes lifecycle operation cannot be completed safely."""


class HermesPartialInstallationError(HermesOperationError):
    """Raised when Hermes appears after an incomplete installation flow."""

    def __init__(self, message: str, status: HermesStatus) -> None:
        super().__init__(message)
        self.status = status
