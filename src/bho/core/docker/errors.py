"""Errors raised by Docker host setup operations."""


class DockerSetupError(RuntimeError):
    """Raised when Docker cannot be installed or configured safely."""
