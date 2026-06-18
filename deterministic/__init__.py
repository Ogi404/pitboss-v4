# Deterministic checks (the 95%)
# Pure code: regex, lookups, dictionaries - no LLM

# Import checks to trigger @register_check decorator registration
from .voice import VoiceThirdPersonCheck  # noqa: F401
from .stop_words import StopWordsCheck  # noqa: F401
from .headings import HeadingsCheck  # noqa: F401
from .currency import CurrencyConsistencyCheck  # noqa: F401
from .formatting import FormattingCheck  # noqa: F401
from .locale_spelling import LocaleSpellingCheck  # noqa: F401
from .brand_names import BrandNamesCheck  # noqa: F401
from .keywords import KeywordsCheck  # noqa: F401
from .structure import StructureCheck  # noqa: F401
