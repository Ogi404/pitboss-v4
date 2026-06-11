# Deterministic checks (the 95%)
# Pure code: regex, lookups, dictionaries - no LLM

# Import checks to trigger @register_check decorator registration
from .voice import VoiceThirdPersonCheck  # noqa: F401
from .stop_words import StopWordsCheck  # noqa: F401
from .headings import HeadingsCheck  # noqa: F401
