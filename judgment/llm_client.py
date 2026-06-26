"""
Pitboss v4 - Shared LLM Client for Judgment Layer

Provider-agnostic LLM client for all judgment checks.
Configured via environment variables:

Environment Variables:
    PITBOSS_LLM_PROVIDER: "openai" (default) or "anthropic"
    PITBOSS_LLM_MODEL: Model name (default: "gpt-4o-mini" for OpenAI, "claude-3-haiku-20240307" for Anthropic)
    OPENAI_API_KEY: Required if using OpenAI
    ANTHROPIC_API_KEY: Required if using Anthropic

Usage:
    from judgment.llm_client import call_llm

    response = call_llm("Your prompt here")
    if response is None:
        # Handle graceful failure
        pass

Design principles:
- Graceful degradation: API errors return None, checks handle this
- Provider-agnostic: Same interface regardless of backend
- Configurable: Model/provider switchable via env vars
- Reusable: Phase 5 consistency, Phase 7 fact-checker, etc.
"""

from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Load .env file if it exists (for local development)
def _load_dotenv():
    """Load environment variables from .env file if present."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value and key not in os.environ:
                            os.environ[key] = value
        except Exception as e:
            logger.warning(f"Could not load .env file: {e}")

_load_dotenv()


# =============================================================================
# CONFIGURATION
# =============================================================================

# Provider: "openai" (default) or "anthropic"
PROVIDER_ENV_VAR = "PITBOSS_LLM_PROVIDER"
DEFAULT_PROVIDER = "openai"

# Model configuration per provider
MODEL_ENV_VAR = "PITBOSS_LLM_MODEL"
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-haiku-20240307",
}

# Timeout in seconds
TIMEOUT_ENV_VAR = "PITBOSS_LLM_TIMEOUT"
DEFAULT_TIMEOUT = 30


# =============================================================================
# CONFIGURATION HELPERS
# =============================================================================

def get_provider() -> str:
    """Get the configured LLM provider."""
    return os.environ.get(PROVIDER_ENV_VAR, DEFAULT_PROVIDER).lower()


def get_model(provider: str) -> str:
    """Get the configured model for the given provider."""
    # Check for explicit model override
    explicit = os.environ.get(MODEL_ENV_VAR)
    if explicit:
        return explicit
    return DEFAULT_MODELS.get(provider, DEFAULT_MODELS["openai"])


def get_timeout() -> int:
    """Get the configured timeout in seconds."""
    try:
        return int(os.environ.get(TIMEOUT_ENV_VAR, DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT


# =============================================================================
# PROVIDER IMPLEMENTATIONS
# =============================================================================

def _call_openai(prompt: str, model: str, timeout: int) -> Optional[str]:
    """Call OpenAI API."""
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed - run: pip install openai")
        return None

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set - cannot run judgment check")
        return None

    logger.info(f"Calling OpenAI LLM ({model})")

    try:
        client = OpenAI(api_key=api_key, timeout=timeout)
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        if response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content
            return content if content else None
        else:
            logger.warning("Empty response from OpenAI")
            return None

    except Exception as e:
        # Import timeout error for specific handling
        try:
            from openai import APITimeoutError
            if isinstance(e, APITimeoutError):
                logger.error(f"OpenAI API timeout after {timeout}s")
                return None
        except ImportError:
            pass
        logger.error(f"OpenAI API error: {e}")
        return None


def _call_anthropic(prompt: str, model: str, timeout: int) -> Optional[str]:
    """Call Anthropic API."""
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed - run: pip install anthropic")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set - cannot run judgment check")
        return None

    logger.info(f"Calling Anthropic LLM ({model})")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            timeout=timeout,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        if response.content and len(response.content) > 0:
            return response.content[0].text
        else:
            logger.warning("Empty response from Anthropic")
            return None

    except anthropic.APITimeoutError:
        logger.error(f"Anthropic API timeout after {timeout}s")
        return None
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error calling Anthropic: {e}")
        return None


# =============================================================================
# PUBLIC API
# =============================================================================

def call_llm(prompt: str) -> Optional[str]:
    """
    Call the configured LLM with the given prompt.

    This is the primary entry point for judgment checks.

    Args:
        prompt: The prompt to send to the LLM

    Returns:
        The LLM's response text, or None on any error.
        Callers should handle None gracefully (drop findings, continue pipeline).

    Configuration via environment variables:
        PITBOSS_LLM_PROVIDER: "openai" (default) or "anthropic"
        PITBOSS_LLM_MODEL: Override default model
        PITBOSS_LLM_TIMEOUT: Timeout in seconds (default: 30)
        OPENAI_API_KEY: Required for OpenAI
        ANTHROPIC_API_KEY: Required for Anthropic
    """
    provider = get_provider()
    model = get_model(provider)
    timeout = get_timeout()

    if provider == "openai":
        return _call_openai(prompt, model, timeout)
    elif provider == "anthropic":
        return _call_anthropic(prompt, model, timeout)
    else:
        logger.error(f"Unknown LLM provider: {provider}. Use 'openai' or 'anthropic'.")
        return None


def get_config_summary() -> str:
    """Get a summary of current LLM configuration for logging."""
    provider = get_provider()
    model = get_model(provider)
    timeout = get_timeout()

    # Check for API key
    if provider == "openai":
        has_key = bool(os.environ.get("OPENAI_API_KEY"))
    else:
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    return f"provider={provider}, model={model}, timeout={timeout}s, api_key={'set' if has_key else 'NOT SET'}"
