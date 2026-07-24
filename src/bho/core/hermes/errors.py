"""Errors raised by Hermes lifecycle operations."""

from __future__ import annotations

from collections.abc import Sequence

from bho.core.hermes.models import HermesStatus


class HermesOperationError(RuntimeError):
    """Raised when a Hermes lifecycle operation cannot be completed safely."""


class HermesPartialInstallationError(HermesOperationError):
    """Raised when Hermes appears after an incomplete installation flow."""

    def __init__(self, message: str, status: HermesStatus) -> None:
        super().__init__(message)
        self.status = status


class HermesConfigurationError(HermesOperationError):
    """Raised when a Hermes configuration stage cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        completed_stages: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.completed_stages = tuple(completed_stages)
