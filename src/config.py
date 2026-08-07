"""Environment-backed application configuration.

Deployment-specific values must be supplied by the process environment. Docker
Compose loads them from the repository's untracked ``.env`` file.
"""

import os


def env(name: str) -> str:
    """Return a required, non-empty environment variable."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            "Copy .env.example to .env and configure it."
        )
    return value


def env_int(name: str) -> int:
    """Return a required environment variable parsed as an integer."""
    value = env(name)
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


def env_float(name: str) -> float:
    """Return a required environment variable parsed as a float."""
    value = env(name)
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be a number") from exc
