"""
Pitboss v4 - Brief Model

Data models for structured brief representation with confidence scoring.
This is the fourth frozen contract - BriefModel is immutable once created.

Core rule: NEVER SILENTLY GUESS. Low confidence triggers clarification.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class ArticleType(Enum):
    """Article type clusters for voice model selection."""
    MAIN_REVIEW = "main_review"
    BONUS_PAGE = "bonus_page"
    APP_REVIEW = "app_review"
    GAME_REVIEW = "game_review"
    SPORTS_MARKET = "sports_market"
    PAYMENTS = "payments"
    REGISTRATION = "registration"
    CUSTOMER_SUPPORT = "customer_support"
    RESPONSIBLE_GAMING = "responsible_gaming"
    VIP_LOYALTY = "vip_loyalty"
    PRIVACY_POLICY = "privacy_policy"
    LIVE_CASINO = "live_casino"
    META_SEO = "meta_seo"  # Meta titles, descriptions, SEO snippets
    GENERAL = "general"  # Fallback for unknown types


class BriefState(Enum):
    """Result state of brief parsing."""
    READY = "ready"  # Brief parsed successfully, proceed to checks
    NEEDS_CLARIFICATION = "needs_clarification"  # Low confidence on critical element
    NEEDS_TASK_SELECTION = "needs_task_selection"  # Multi-task brief, user must pick


@dataclass(frozen=True)
class BriefKeyword:
    """
    A single keyword with quantity constraints and confidence.

    Quantity formats supported:
    - Exact: min_quantity=3, max_quantity=3 (use exactly 3 times)
    - Any: min_quantity=None, max_quantity=None (no constraint)
    - Range: min_quantity=1, max_quantity=3 (use 1-3 times)
    - Min only: min_quantity=2, max_quantity=None (at least 2)
    - Max only: min_quantity=None, max_quantity=5 (at most 5)
    """
    keyword: str
    min_quantity: Optional[int]  # None = no minimum
    max_quantity: Optional[int]  # None = no maximum
    group: str  # "main", "support", "lsi"
    confidence: float = 1.0

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0-1, got {self.confidence}")
        if self.min_quantity is not None and self.min_quantity < 0:
            raise ValueError(f"min_quantity must be non-negative, got {self.min_quantity}")
        if self.max_quantity is not None and self.max_quantity < 0:
            raise ValueError(f"max_quantity must be non-negative, got {self.max_quantity}")
        if (self.min_quantity is not None and self.max_quantity is not None
                and self.min_quantity > self.max_quantity):
            raise ValueError(f"min_quantity ({self.min_quantity}) cannot exceed max_quantity ({self.max_quantity})")
        if self.group not in ("main", "support", "lsi"):
            raise ValueError(f"Group must be main/support/lsi, got {self.group}")

    @property
    def quantity(self) -> int:
        """Backwards-compatible: return exact or min quantity, defaulting to 1."""
        if self.min_quantity is not None:
            return self.min_quantity
        if self.max_quantity is not None:
            return 1  # Has max but no min, default to 1
        return 1  # No constraints, default to 1

    @property
    def is_exact(self) -> bool:
        """Check if this is an exact quantity (min == max)."""
        return (self.min_quantity is not None and self.max_quantity is not None
                and self.min_quantity == self.max_quantity)

    @property
    def is_any(self) -> bool:
        """Check if this is 'any' (no constraints)."""
        return self.min_quantity is None and self.max_quantity is None


@dataclass(frozen=True)
class BriefKeywords:
    """Keywords grouped by type (main, support, LSI)."""
    main: tuple[BriefKeyword, ...] = field(default_factory=tuple)
    support: tuple[BriefKeyword, ...] = field(default_factory=tuple)
    lsi: tuple[BriefKeyword, ...] = field(default_factory=tuple)

    @property
    def all_keywords(self) -> tuple[BriefKeyword, ...]:
        """Return all keywords as a single tuple."""
        return self.main + self.support + self.lsi

    @property
    def total_count(self) -> int:
        """Total number of keyword instances required (using min_quantity or default 1)."""
        return sum(kw.quantity for kw in self.all_keywords)

    @property
    def min_confidence(self) -> float:
        """Lowest confidence among all keywords."""
        all_kw = self.all_keywords
        if not all_kw:
            return 0.0
        return min(kw.confidence for kw in all_kw)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        def kw_dict(k):
            return {
                "keyword": k.keyword,
                "min_quantity": k.min_quantity,
                "max_quantity": k.max_quantity,
                "confidence": k.confidence,
            }
        return {
            "main": [kw_dict(k) for k in self.main],
            "support": [kw_dict(k) for k in self.support],
            "lsi": [kw_dict(k) for k in self.lsi],
        }


@dataclass(frozen=True)
class BriefSection:
    """A required section/heading with optional word count."""
    heading: str
    word_count: Optional[int] = None
    is_required: bool = True
    confidence: float = 1.0

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0-1, got {self.confidence}")
        if self.word_count is not None and self.word_count < 0:
            raise ValueError(f"Word count must be non-negative, got {self.word_count}")


@dataclass(frozen=True)
class BriefLink:
    """
    A link specification from the brief.

    Internal links point within the same domain (relative paths or same domain).
    External links point to other domains.
    """
    anchor: str
    url: str
    link_type: str  # "internal" or "external"
    confidence: float = 1.0

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0-1, got {self.confidence}")
        if self.link_type not in ("internal", "external"):
            raise ValueError(f"link_type must be internal/external, got {self.link_type}")


@dataclass(frozen=True)
class Clarification:
    """A question for the user when confidence is low."""
    field: str  # "keywords", "sections", "article_type", "word_count", "locale"
    question: str  # Human-readable question
    detected_value: Any  # What we found (may be wrong)
    confidence: float  # How confident we are
    options: tuple[str, ...] = field(default_factory=tuple)  # Suggested alternatives

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0-1, got {self.confidence}")


@dataclass(frozen=True)
class BriefModel:
    """
    Structured brief data with confidence per element.

    This is the fourth frozen contract - immutable once created.
    Every element has an associated confidence score.
    """
    # Keywords with quantities
    keywords: BriefKeywords
    keywords_confidence: float

    # Required sections with word counts
    sections: tuple[BriefSection, ...]
    sections_confidence: float

    # Target word count
    target_word_count: int
    word_count_confidence: float

    # Task/article info
    task_name: str  # Raw task name from brief
    article_type: ArticleType  # Mapped cluster
    article_type_confidence: float

    # Locale/market
    locale: Optional[str]
    market: Optional[str]
    locale_confidence: float

    # Links
    links: tuple[BriefLink, ...] = field(default_factory=tuple)
    links_confidence: float = 0.5

    # Formatting hints extracted from brief instructions
    # Keys: "blank_rows" -> "required"|"none"
    # Only set if brief explicitly states formatting instructions
    formatting_hints: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    # Meta
    brand_name: str = ""
    source_path: str = ""
    source_format: str = ""  # "xlsx", "docx", "sheets"

    # Original extracted data for debugging
    raw_data: dict = field(default_factory=dict)

    def get_formatting_hint(self, key: str) -> Optional[str]:
        """Get a formatting hint value by key, or None if not set."""
        hints_dict = dict(self.formatting_hints)
        return hints_dict.get(key)

    def __post_init__(self):
        """Validate confidence values."""
        for field_name in ("keywords_confidence", "sections_confidence",
                           "word_count_confidence", "article_type_confidence",
                           "locale_confidence", "links_confidence"):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be 0-1, got {value}")

    @property
    def min_confidence(self) -> float:
        """Return the minimum confidence across all elements."""
        return min(
            self.keywords_confidence,
            self.sections_confidence,
            self.word_count_confidence,
            self.article_type_confidence,
            self.locale_confidence,
        )

    @property
    def is_high_confidence(self) -> bool:
        """Check if all elements have high confidence (>= 0.7)."""
        return self.min_confidence >= 0.7

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "keywords": self.keywords.to_dict(),
            "keywords_confidence": self.keywords_confidence,
            "sections": [
                {"heading": s.heading, "word_count": s.word_count,
                 "is_required": s.is_required, "confidence": s.confidence}
                for s in self.sections
            ],
            "sections_confidence": self.sections_confidence,
            "target_word_count": self.target_word_count,
            "word_count_confidence": self.word_count_confidence,
            "task_name": self.task_name,
            "article_type": self.article_type.value,
            "article_type_confidence": self.article_type_confidence,
            "locale": self.locale,
            "market": self.market,
            "locale_confidence": self.locale_confidence,
            "links": [
                {"anchor": link.anchor, "url": link.url,
                 "link_type": link.link_type, "confidence": link.confidence}
                for link in self.links
            ],
            "links_confidence": self.links_confidence,
            "brand_name": self.brand_name,
            "source_path": self.source_path,
            "source_format": self.source_format,
        }


@dataclass(frozen=True)
class BriefResult:
    """
    Result of brief parsing - one of three states.

    - READY: Brief parsed successfully, proceed to checks
    - NEEDS_CLARIFICATION: Critical elements unclear, ask user first
    - NEEDS_TASK_SELECTION: Multi-task brief, user must pick a task
    """
    state: BriefState
    brief: Optional[BriefModel] = None  # Present if READY, may be partial if NEEDS_CLARIFICATION
    clarifications: tuple[Clarification, ...] = field(default_factory=tuple)
    task_options: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Validate state consistency."""
        if self.state == BriefState.READY and self.brief is None:
            raise ValueError("READY state requires a brief")
        if self.state == BriefState.NEEDS_CLARIFICATION and not self.clarifications:
            raise ValueError("NEEDS_CLARIFICATION state requires clarifications")
        if self.state == BriefState.NEEDS_TASK_SELECTION and not self.task_options:
            raise ValueError("NEEDS_TASK_SELECTION state requires task_options")

    @property
    def is_ready(self) -> bool:
        """Check if brief is ready to use."""
        return self.state == BriefState.READY

    @property
    def needs_input(self) -> bool:
        """Check if user input is needed."""
        return self.state in (BriefState.NEEDS_CLARIFICATION, BriefState.NEEDS_TASK_SELECTION)
