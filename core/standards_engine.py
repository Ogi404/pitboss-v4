"""
Pitboss v4 - Standards Engine

Loads brand configuration YAML and serves rules as structured, queryable objects.
Supports inheritance: load brands/_defaults.yaml first, then deep-merge a specific
brand's YAML on top (brand overrides default; nested dicts merge; lists replace).

This is the same inheritance model that worked in v3.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, Union
from pathlib import Path
import copy

import yaml


def deep_merge(base: dict, overlay: dict) -> dict:
    """
    Deep merge two dictionaries.

    Rules:
    - Nested dicts merge recursively
    - Lists replace (not extend)
    - Scalars replace
    - Overlay wins on conflicts

    Args:
        base: The base dictionary
        overlay: The overlay dictionary (takes precedence)

    Returns:
        A new dictionary with merged values
    """
    result = copy.deepcopy(base)

    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)

    return result


@dataclass
class VoiceStandards:
    """Voice-related standards."""
    person: str = "second"
    on_behalf_of: str = "gambling expert team"

    @classmethod
    def from_dict(cls, data: dict) -> VoiceStandards:
        return cls(
            person=data.get("person", "second"),
            on_behalf_of=data.get("on_behalf_of", "gambling expert team"),
        )


@dataclass
class ReadabilityStandards:
    """Readability-related standards."""
    max_sentence_words: int = 25
    paragraph_sentences_min: int = 3
    paragraph_sentences_max: int = 5
    require_para_between_headings: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> ReadabilityStandards:
        para_range = data.get("paragraph_sentences", [3, 5])
        return cls(
            max_sentence_words=data.get("max_sentence_words", 25),
            paragraph_sentences_min=para_range[0] if len(para_range) > 0 else 3,
            paragraph_sentences_max=para_range[1] if len(para_range) > 1 else 5,
            require_para_between_headings=data.get("require_para_between_headings", True),
        )


@dataclass
class KeywordStandards:
    """Keyword-related standards."""
    use_all_main: bool = True
    max_density_percent: float = 3.0
    highlight_color: str = "yellow"
    warn_brand_name_overuse: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> KeywordStandards:
        return cls(
            use_all_main=data.get("use_all_main", True),
            max_density_percent=data.get("max_density_percent", 3.0),
            highlight_color=data.get("highlight_color", "yellow"),
            warn_brand_name_overuse=data.get("warn_brand_name_overuse", True),
        )


@dataclass
class CurrencyStandards:
    """Currency-related standards."""
    mode: str = "exclusive"  # "exclusive" = symbol XOR abbreviation
    symbol: Optional[str] = None  # Brand-specific override

    @classmethod
    def from_dict(cls, data: dict) -> CurrencyStandards:
        return cls(
            mode=data.get("mode", "exclusive"),
            symbol=data.get("symbol"),
        )


@dataclass
class HeadingsStandards:
    """Headings-related standards."""
    hierarchy: list[str] = field(default_factory=lambda: ["H1", "H2", "H3", "H4"])
    descriptive_required: bool = True
    capitalization: Optional[str] = None  # "title_case", "sentence_case", None=locale default
    no_question_marks: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> HeadingsStandards:
        return cls(
            hierarchy=data.get("hierarchy", ["H1", "H2", "H3", "H4"]),
            descriptive_required=data.get("descriptive_required", True),
            capitalization=data.get("capitalization"),
            no_question_marks=data.get("no_question_marks", True),
        )


@dataclass
class StopWordsStandards:
    """Stop words standards with weighted tiers."""
    hard: list[str] = field(default_factory=list)  # Weight 1.0
    soft: list[str] = field(default_factory=list)  # Weight 0.3

    @classmethod
    def from_dict(cls, data: dict) -> StopWordsStandards:
        return cls(
            hard=data.get("hard", []),
            soft=data.get("soft", []),
        )

    def is_hard(self, word: str) -> bool:
        """Check if a word is in the hard stop words list."""
        word_lower = word.lower()
        return any(w.lower() == word_lower for w in self.hard)

    def is_soft(self, word: str) -> bool:
        """Check if a word is in the soft stop words list."""
        word_lower = word.lower()
        return any(w.lower() == word_lower for w in self.soft)

    def is_stop_word(self, word: str) -> bool:
        """Check if a word is any kind of stop word."""
        return self.is_hard(word) or self.is_soft(word)

    def weight(self, word: str) -> float:
        """Get the weight for a stop word (1.0 for hard, 0.3 for soft, 0.0 otherwise)."""
        if self.is_hard(word):
            return 1.0
        if self.is_soft(word):
            return 0.3
        return 0.0

    def tier(self, word: str) -> Optional[str]:
        """Get the tier for a stop word ('hard', 'soft', or None)."""
        if self.is_hard(word):
            return "hard"
        if self.is_soft(word):
            return "soft"
        return None


@dataclass
class ProhibitedStyleStandards:
    """Prohibited style elements."""
    latin_abbreviations: list[str] = field(default_factory=lambda: ["e.g.", "i.e.", "etc."])
    profanity_mild: list[str] = field(default_factory=lambda: ["sucks", "jerk"])

    @classmethod
    def from_dict(cls, data: Any) -> ProhibitedStyleStandards:
        result = cls()

        # Handle both list format and dict format
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    if "latin_abbreviations" in item:
                        result.latin_abbreviations = item["latin_abbreviations"]
                    if "profanity_mild" in item:
                        result.profanity_mild = item["profanity_mild"]
        elif isinstance(data, dict):
            if "latin_abbreviations" in data:
                result.latin_abbreviations = data["latin_abbreviations"]
            if "profanity_mild" in data:
                result.profanity_mild = data["profanity_mild"]

        return result

    def is_prohibited(self, text: str) -> bool:
        """Check if text contains any prohibited style element."""
        text_lower = text.lower()
        for abbrev in self.latin_abbreviations:
            if abbrev.lower() in text_lower:
                return True
        for word in self.profanity_mild:
            if word.lower() in text_lower:
                return True
        return False


@dataclass
class LocaleMapping:
    """Locale to spelling region mapping."""
    british: list[str] = field(default_factory=lambda: ["UK", "IN", "LK", "PK", "SG", "MM", "HK", "KE", "NG"])
    american: list[str] = field(default_factory=lambda: ["US", "PH", "TW", "KR", "JP"])
    canadian: list[str] = field(default_factory=lambda: ["CA"])
    australian: list[str] = field(default_factory=lambda: ["AU"])
    new_zealand: list[str] = field(default_factory=lambda: ["NZ"])

    @classmethod
    def from_dict(cls, data: dict) -> LocaleMapping:
        return cls(
            british=data.get("british", ["UK", "IN", "LK", "PK", "SG", "MM", "HK", "KE", "NG"]),
            american=data.get("american", ["US", "PH", "TW", "KR", "JP"]),
            canadian=data.get("canadian", ["CA"]),
            australian=data.get("australian", ["AU"]),
            new_zealand=data.get("new_zealand", ["NZ"]),
        )

    def spelling_region(self, country_code: str) -> str:
        """
        Get spelling region for a country code.

        Args:
            country_code: Two-letter country code (e.g., "CA", "UK")

        Returns:
            Spelling region name: "british", "american", "canadian", "australian", "new_zealand"
            Defaults to "british" if not found.
        """
        code = country_code.upper()
        if code in self.british:
            return "british"
        if code in self.american:
            return "american"
        if code in self.canadian:
            return "canadian"
        if code in self.australian:
            return "australian"
        if code in self.new_zealand:
            return "new_zealand"
        return "british"  # Default


@dataclass
class BrandNormalization:
    """Brand name normalization rules."""
    mappings: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> BrandNormalization:
        return cls(mappings=data if isinstance(data, dict) else {})

    def normalize(self, text: str) -> str:
        """Normalize a brand name according to mappings."""
        return self.mappings.get(text, text)


@dataclass
class Standards:
    """
    Fully typed standards object with all configuration domains.

    Constructed by merging _defaults.yaml with brand-specific YAML.
    """
    voice: VoiceStandards = field(default_factory=VoiceStandards)
    readability: ReadabilityStandards = field(default_factory=ReadabilityStandards)
    keywords: KeywordStandards = field(default_factory=KeywordStandards)
    currency: CurrencyStandards = field(default_factory=CurrencyStandards)
    headings: HeadingsStandards = field(default_factory=HeadingsStandards)
    stop_words: StopWordsStandards = field(default_factory=StopWordsStandards)
    prohibited_style: ProhibitedStyleStandards = field(default_factory=ProhibitedStyleStandards)
    locale_mappings: LocaleMapping = field(default_factory=LocaleMapping)
    brand_normalization: BrandNormalization = field(default_factory=BrandNormalization)
    forbidden_brands: bool = True

    # Brand-specific fields
    brand_name: Optional[str] = None
    market: Optional[str] = None  # Country code (e.g., "CA", "UK")
    locale: Optional[str] = None  # Full locale (e.g., "en-CA")

    # Schema version
    schema_version: str = "1.0"

    # Raw data for extension access
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict) -> Standards:
        """Create Standards from a dictionary (merged config)."""
        return cls(
            voice=VoiceStandards.from_dict(data.get("voice", {})),
            readability=ReadabilityStandards.from_dict(data.get("readability", {})),
            keywords=KeywordStandards.from_dict(data.get("keywords", {})),
            currency=CurrencyStandards.from_dict(data.get("currency", {})),
            headings=HeadingsStandards.from_dict(data.get("headings", {})),
            stop_words=StopWordsStandards.from_dict(data.get("stop_words", {})),
            prohibited_style=ProhibitedStyleStandards.from_dict(data.get("prohibited_style", [])),
            locale_mappings=LocaleMapping.from_dict(data.get("locale_mappings", {})),
            brand_normalization=BrandNormalization.from_dict(data.get("brand_normalization", {})),
            forbidden_brands=data.get("forbidden_brands", True),
            brand_name=data.get("brand_name"),
            market=data.get("market"),
            locale=data.get("locale"),
            schema_version=data.get("schema_version", "1.0"),
            _raw=data,
        )

    def get(self, path: str, default: Any = None) -> Any:
        """
        Get a value by dot-separated path for extension access.

        Example: standards.get("voice.person") -> "second"

        Args:
            path: Dot-separated path to the value
            default: Default value if path not found

        Returns:
            The value at the path, or default if not found
        """
        parts = path.split(".")
        current = self._raw
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    @property
    def spelling_region(self) -> str:
        """Get the spelling region for this brand's market."""
        if self.market:
            return self.locale_mappings.spelling_region(self.market)
        return "british"  # Default


class StandardsEngine:
    """
    Loads and serves standards with inheritance.

    Usage:
        engine = StandardsEngine(brands_dir="brands/")
        standards = engine.load("vave")  # Merges _defaults.yaml + vave.yaml
    """

    def __init__(self, brands_dir: Union[str, Path] = "brands"):
        """
        Initialize the standards engine.

        Args:
            brands_dir: Path to the brands directory containing YAML files
        """
        self.brands_dir = Path(brands_dir)
        self._defaults: Optional[dict] = None
        self._cache: dict[str, Standards] = {}

    def _load_yaml(self, path: Path) -> dict:
        """Load a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _get_defaults(self) -> dict:
        """Load and cache the defaults."""
        if self._defaults is None:
            defaults_path = self.brands_dir / "_defaults.yaml"
            if defaults_path.exists():
                self._defaults = self._load_yaml(defaults_path)
            else:
                self._defaults = {}
        return self._defaults

    def load(self, brand: str, use_cache: bool = True) -> Standards:
        """
        Load standards for a brand with inheritance.

        Merges _defaults.yaml with {brand}.yaml.
        Brand config overrides defaults; nested dicts merge; lists replace.

        Args:
            brand: Brand name (without .yaml extension)
            use_cache: Whether to use cached standards

        Returns:
            Standards object with merged configuration
        """
        if use_cache and brand in self._cache:
            return self._cache[brand]

        # Load defaults
        merged = copy.deepcopy(self._get_defaults())

        # Load brand-specific
        brand_path = self.brands_dir / f"{brand}.yaml"
        if brand_path.exists():
            brand_config = self._load_yaml(brand_path)
            merged = deep_merge(merged, brand_config)

        # Add brand name if not set
        if "brand_name" not in merged:
            merged["brand_name"] = brand

        standards = Standards.from_dict(merged)

        if use_cache:
            self._cache[brand] = standards

        return standards

    def load_defaults(self) -> Standards:
        """Load just the defaults (no brand override)."""
        return Standards.from_dict(self._get_defaults())

    def available_brands(self) -> list[str]:
        """List all available brand profiles."""
        brands = []
        if self.brands_dir.exists():
            for path in self.brands_dir.glob("*.yaml"):
                if path.stem != "_defaults":
                    brands.append(path.stem)
        return sorted(brands)

    def has_brand(self, brand: str) -> bool:
        """Check if a brand profile exists."""
        brand_path = self.brands_dir / f"{brand}.yaml"
        return brand_path.exists()

    def clear_cache(self) -> None:
        """Clear the standards cache."""
        self._cache.clear()
        self._defaults = None

    def reload(self, brand: str) -> Standards:
        """Force reload standards for a brand (bypass cache)."""
        return self.load(brand, use_cache=False)
