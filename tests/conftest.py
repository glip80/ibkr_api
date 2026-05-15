"""
Shared pytest fixtures and configuration.

asyncio_mode = "auto" is set in pyproject.toml so all async tests
run without explicit @pytest.mark.asyncio decorators.
"""

import pytest


@pytest.fixture(autouse=True)
def _reset_logging() -> None:
    """Reset logging handlers between tests to avoid cross-test pollution."""
    import logging
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.level = original_level
