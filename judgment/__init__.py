"""
Pitboss v4 - Judgment Layer

LLM-assisted checks that require human review (the 5%).
All checks here produce proposals only, never auto-applied.

LLM client configuration:
    PITBOSS_LLM_PROVIDER: "openai" (default) or "anthropic"
    PITBOSS_LLM_MODEL: Override default model
    OPENAI_API_KEY: Required if using OpenAI
    ANTHROPIC_API_KEY: Required if using Anthropic
"""

from .llm_client import call_llm, get_config_summary
from .consistency import ConsistencyCheck

__all__ = ["ConsistencyCheck", "call_llm", "get_config_summary"]
