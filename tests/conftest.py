"""
Pytest configuration for Pitboss v4 tests.

Ensures deterministic checks are registered before any tests run.
"""

import pytest

# Import deterministic checks to ensure registration before any tests
import deterministic  # noqa: F401
