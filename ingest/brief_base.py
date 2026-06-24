"""
Pitboss v4 - Brief Parser Base Classes

Abstract base class and registry for format-specific brief parsers.
Uses self-registration pattern - parsers register themselves on import.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union, Optional, Any
import re


# Confidence thresholds for triggering clarification
KEYWORD_CONFIDENCE_THRESHOLD = 0.7
SECTION_CONFIDENCE_THRESHOLD = 0.6
ARTICLE_TYPE_CONFIDENCE_THRESHOLD = 0.6
WORD_COUNT_CONFIDENCE_THRESHOLD = 0.5


# =============================================================================
# METADATA LABELS - These are NEVER keywords
# =============================================================================
METADATA_LABELS = frozenset({
    # Structure markers
    "section", "platform", "target url", "word count", "template variant",
    "tone", "title tag", "meta description", "meta title",
    # Heading markers (base forms, patterns handle numbered)
    "h1", "h2", "h3", "h4", "h5", "h6",
    # Link markers (base forms)
    "link", "anchor", "url",
    # Strategy markers
    "key competitions", "key competition", "unique aspects", "unique aspect",
    "faq targets", "faq target", "content strategy", "primary market focus",
    # Quantity headers
    "qty", "quantity", "count", "#", "amount",
    # Brief structure
    "keyword", "keywords", "main keyword", "main keywords",
    "support keyword", "support keywords", "supporting keyword",
    "lsi keyword", "lsi keywords", "related keyword", "related keywords",
    "primary keyword", "primary keywords", "secondary keyword", "secondary keywords",
    # Other common labels
    "task", "topic", "type", "brand", "client", "locale", "market", "language",
    "region", "geo", "target", "target length", "total words", "content type",
    "article type", "brief", "instructions", "notes", "comments",
})

# Pattern-based metadata labels (h2 #1, link 1 — anchor, etc.)
METADATA_LABEL_PATTERNS = [
    re.compile(r"^h[1-6]\s*(?:#\s*\d+)?$", re.IGNORECASE),  # h1, h2 #1, h2 #2, etc.
    re.compile(r"^link\s*\d+(?:\s*[—\-–]\s*(?:anchor|url))?$", re.IGNORECASE),  # link 1, link 1 - anchor
    re.compile(r"^(?:internal|external)\s*link\s*\d*$", re.IGNORECASE),  # internal link 1
    re.compile(r"^anchor\s*\d*$", re.IGNORECASE),  # anchor 1
    re.compile(r"^url\s*\d*$", re.IGNORECASE),  # url 1
]


def is_metadata_label(text: str) -> bool:
    """
    Check if text is a metadata label, not a keyword.

    This prevents extracting structural labels like "Section", "H1",
    "Link 1 - Anchor" as keywords.
    """
    if not text:
        return True  # Empty is not a keyword

    normalized = text.lower().strip()

    # Check exact match in set
    if normalized in METADATA_LABELS:
        return True

    # Check pattern-based matches
    for pattern in METADATA_LABEL_PATTERNS:
        if pattern.match(normalized):
            return True

    return False


def _parse_quantity_range(value: Any) -> tuple[Optional[int], Optional[int]]:
    """
    Parse quantity specification into (min, max).

    Examples:
        "Exact 1", "1" → (1, 1)
        "Any", "", None → (None, None)
        "1-3" → (1, 3)
        "Min 2" → (2, None)
        "Max 5" → (None, 5)
        "2x" or "x2" → (2, 2)
    """
    if value is None:
        return (None, None)

    text = str(value).strip().lower()
    if not text or text == "any":
        return (None, None)

    # "Exact N" pattern
    exact_match = re.match(r"exact\s+(\d+)$", text)
    if exact_match:
        n = int(exact_match.group(1))
        return (n, n)

    # Range "N-M" or "N–M" (en-dash)
    range_match = re.match(r"(\d+)\s*[-–]\s*(\d+)$", text)
    if range_match:
        return (int(range_match.group(1)), int(range_match.group(2)))

    # "Min N"
    min_match = re.match(r"min\s+(\d+)$", text)
    if min_match:
        return (int(min_match.group(1)), None)

    # "Max N"
    max_match = re.match(r"max\s+(\d+)$", text)
    if max_match:
        return (None, int(max_match.group(1)))

    # "Nx" or "xN" patterns (e.g., "3x" or "x3")
    x_match = re.match(r"(\d+)\s*[x×]$", text) or re.match(r"[x×]\s*(\d+)$", text)
    if x_match:
        n = int(x_match.group(1))
        return (n, n)

    # Bare number
    bare_match = re.match(r"^(\d+)$", text)
    if bare_match:
        n = int(bare_match.group(1))
        return (n, n)

    # Fallback: extract first number as exact
    num_match = re.search(r"(\d+)", text)
    if num_match:
        n = int(num_match.group(1))
        return (n, n)

    return (None, None)


def clean_keyword(text: str) -> str:
    """
    Clean a keyword: strip parenthetical translations, normalize whitespace.

    Examples:
        "bonus (bônus)" → "bonus"
        "(ITA: bonus) bônus" → "bônus"
        "  casino  review  " → "casino review"
    """
    # Strip leading parenthetical (ITA:, PT:, etc. translations)
    cleaned = re.sub(r"^\s*\([^)]+\)\s*", "", text)
    # Strip trailing parenthetical (translations)
    cleaned = re.sub(r"\s*\([^)]+\)\s*$", "", cleaned)
    # Normalize whitespace
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


# =============================================================================
# FORMATTING HINTS EXTRACTION
# =============================================================================

# Precise patterns for blank_rows detection
# These phrases indicate explicit formatting instructions in the brief
BLANK_ROWS_REQUIRED_PATTERNS = [
    re.compile(r"empty\s+rows?\s+between\s+paragraphs?", re.IGNORECASE),
    re.compile(r"indents?\s+between\s+paragraphs?\s+and\s+headings?", re.IGNORECASE),
    re.compile(r"blank\s+(?:lines?|rows?)\s+between\s+(?:paragraphs?|sections?)", re.IGNORECASE),
    re.compile(r"add\s+(?:empty|blank)\s+(?:lines?|rows?)\s+between", re.IGNORECASE),
    re.compile(r"separate\s+(?:paragraphs?|sections?)\s+with\s+(?:empty|blank)\s+(?:lines?|rows?)", re.IGNORECASE),
]

BLANK_ROWS_NONE_PATTERNS = [
    re.compile(r"no\s+(?:empty|blank)\s+(?:lines?|rows?)\s+between", re.IGNORECASE),
    re.compile(r"don'?t\s+add\s+(?:empty|blank)\s+(?:lines?|rows?)", re.IGNORECASE),
    re.compile(r"remove\s+(?:empty|blank)\s+(?:lines?|rows?)", re.IGNORECASE),
]


def extract_formatting_hints(text: str) -> dict:
    """
    Extract formatting hints from brief text.

    Uses precise phrase matching to detect explicit formatting instructions.
    Only matches specific instruction phrases - does NOT match incidental
    mentions of "indent" or "paragraph" in other contexts.

    Args:
        text: Full text content from brief

    Returns:
        Dict of formatting hints, e.g. {"blank_rows": "required"}
        Empty dict if no explicit hints detected.
    """
    hints = {}

    # Normalize text for matching
    normalized = " ".join(text.split())

    # Check for "none" patterns FIRST (negative instructions take precedence)
    # "don't add blank rows" contains "blank rows" but should be "none"
    for pattern in BLANK_ROWS_NONE_PATTERNS:
        if pattern.search(normalized):
            hints["blank_rows"] = "none"
            return hints  # Explicit negative instruction wins

    # Check for "required" patterns
    for pattern in BLANK_ROWS_REQUIRED_PATTERNS:
        if pattern.search(normalized):
            hints["blank_rows"] = "required"
            break

    return hints


@dataclass
class RawKeywordGroup:
    """Raw extracted keyword group before normalization."""
    # Each keyword is (keyword, min_quantity, max_quantity)
    # None values indicate no constraint
    keywords: list[tuple[str, Optional[int], Optional[int]]]
    group_name: str  # "main", "support", "lsi", or detected name
    confidence: float = 1.0


@dataclass
class RawLink:
    """Raw extracted link specification."""
    anchor: str
    url: str
    link_type: str  # "internal" or "external"
    confidence: float = 1.0


@dataclass
class RawSection:
    """Raw extracted section before normalization."""
    heading: str
    word_count: Optional[int] = None
    confidence: float = 1.0


@dataclass
class RawBriefExtraction:
    """
    Raw data extracted from a brief file.

    This is the intermediate representation before building BriefModel.
    Each field has associated confidence from the extraction process.
    """
    # Source info
    source_path: str
    source_format: str

    # Tasks detected (for multi-task briefs)
    tasks: list[str] = field(default_factory=list)

    # Keywords by group
    keyword_groups: list[RawKeywordGroup] = field(default_factory=list)
    keywords_confidence: float = 0.0

    # Sections/structure
    sections: list[RawSection] = field(default_factory=list)
    sections_confidence: float = 0.0

    # Word count
    target_word_count: Optional[int] = None
    word_count_confidence: float = 0.0

    # Task/article info
    task_name: Optional[str] = None
    task_name_confidence: float = 0.0

    # Locale/market
    locale: Optional[str] = None
    market: Optional[str] = None
    locale_confidence: float = 0.0

    # Brand
    brand_name: Optional[str] = None
    brand_confidence: float = 0.0

    # Links
    links: list[RawLink] = field(default_factory=list)
    links_confidence: float = 0.0

    # Formatting hints extracted from brief instructions
    # Keys: "blank_rows" -> "required"|"none"
    formatting_hints: dict = field(default_factory=dict)

    # Raw data for debugging
    raw_data: dict = field(default_factory=dict)

    @property
    def is_multi_task(self) -> bool:
        """Check if this is a multi-task brief."""
        return len(self.tasks) > 1

    @property
    def has_keywords(self) -> bool:
        """Check if any keywords were extracted."""
        return any(len(g.keywords) > 0 for g in self.keyword_groups)


class BriefParser(ABC):
    """
    Abstract base class for format-specific brief parsers.

    Subclasses implement format-specific extraction logic.
    Each parser self-registers via the @register_brief_parser decorator.
    """

    @abstractmethod
    def get_format_name(self) -> str:
        """
        Return format identifier (e.g., "xlsx", "docx", "sheets").

        This is used for registry lookup and logging.
        """
        ...

    @abstractmethod
    def can_parse(self, source: Union[Path, str]) -> bool:
        """
        Check if this parser can handle the given source.

        Args:
            source: File path or URL to check

        Returns:
            True if this parser can handle the source
        """
        ...

    @abstractmethod
    def extract(self, source: Union[Path, str]) -> RawBriefExtraction:
        """
        Extract raw data from the brief.

        This does format-specific parsing and returns raw extracted data
        with per-element confidence scores. The BriefAgent then normalizes
        this into a BriefModel.

        Args:
            source: File path or URL to parse

        Returns:
            RawBriefExtraction with extracted data and confidence scores
        """
        ...


class BriefParserRegistry:
    """
    Self-registering parser registry.

    Parsers register themselves when their module is imported.
    The BriefAgent queries this registry to find the right parser.
    """
    _parsers: dict[str, BriefParser] = {}

    @classmethod
    def register(cls, parser: BriefParser) -> None:
        """
        Register a parser instance.

        Args:
            parser: Parser instance to register
        """
        format_name = parser.get_format_name()
        cls._parsers[format_name] = parser

    @classmethod
    def get(cls, format_name: str) -> BriefParser:
        """
        Get parser by format name.

        Args:
            format_name: Format identifier (e.g., "xlsx")

        Returns:
            Parser instance

        Raises:
            KeyError: If no parser registered for format
        """
        if format_name not in cls._parsers:
            available = list(cls._parsers.keys())
            raise KeyError(f"No parser for format '{format_name}'. Available: {available}")
        return cls._parsers[format_name]

    @classmethod
    def detect_and_get(cls, source: Union[Path, str]) -> BriefParser:
        """
        Auto-detect format and return appropriate parser.

        Args:
            source: File path or URL

        Returns:
            Parser that can handle the source

        Raises:
            ValueError: If no parser can handle the source
        """
        for parser in cls._parsers.values():
            if parser.can_parse(source):
                return parser

        raise ValueError(f"No parser found for source: {source}")

    @classmethod
    def list_formats(cls) -> list[str]:
        """List all registered format names."""
        return list(cls._parsers.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear registry (for testing)."""
        cls._parsers.clear()


def register_brief_parser(parser_class: type[BriefParser]) -> type[BriefParser]:
    """
    Decorator for parser self-registration.

    Usage:
        @register_brief_parser
        class XlsxBriefParser(BriefParser):
            ...

    The parser is instantiated and registered automatically.
    """
    instance = parser_class()
    BriefParserRegistry.register(instance)
    return parser_class


# Common patterns for task name → article type mapping
from ingest.brief_model import ArticleType

TASK_TYPE_PATTERNS: dict[ArticleType, list[re.Pattern]] = {
    ArticleType.MAIN_REVIEW: [
        re.compile(r"^review$", re.IGNORECASE),
        re.compile(r"casino\s*review", re.IGNORECASE),
        re.compile(r"site\s*review", re.IGNORECASE),
        re.compile(r"brand\s*review", re.IGNORECASE),
        re.compile(r"full\s*review", re.IGNORECASE),
        re.compile(r"main\s*page", re.IGNORECASE),
        re.compile(r"^main$", re.IGNORECASE),
    ],
    ArticleType.BONUS_PAGE: [
        re.compile(r"bonus", re.IGNORECASE),
        re.compile(r"promotion", re.IGNORECASE),
        re.compile(r"no[\s\-]?deposit", re.IGNORECASE),
        re.compile(r"welcome[\s\-]?offer", re.IGNORECASE),
        re.compile(r"promo", re.IGNORECASE),
        re.compile(r"free\s*spin", re.IGNORECASE),
    ],
    ArticleType.APP_REVIEW: [
        re.compile(r"\bapp\b", re.IGNORECASE),
        re.compile(r"mobile", re.IGNORECASE),
        re.compile(r"android", re.IGNORECASE),
        re.compile(r"\bios\b", re.IGNORECASE),
        re.compile(r"download", re.IGNORECASE),
    ],
    ArticleType.GAME_REVIEW: [
        re.compile(r"\bslot\b", re.IGNORECASE),
        re.compile(r"game\s*review", re.IGNORECASE),
        re.compile(r"pragmatic", re.IGNORECASE),
        re.compile(r"netent", re.IGNORECASE),
        re.compile(r"specific\s*game", re.IGNORECASE),
    ],
    ArticleType.SPORTS_MARKET: [
        re.compile(r"\bsports?\b", re.IGNORECASE),
        re.compile(r"\bbetting\b", re.IGNORECASE),
        re.compile(r"boxing", re.IGNORECASE),
        re.compile(r"basketball", re.IGNORECASE),
        re.compile(r"racing", re.IGNORECASE),
        re.compile(r"football", re.IGNORECASE),
        re.compile(r"cricket", re.IGNORECASE),
        re.compile(r"tennis", re.IGNORECASE),
        re.compile(r"soccer", re.IGNORECASE),
    ],
    ArticleType.PAYMENTS: [
        re.compile(r"payment", re.IGNORECASE),
        re.compile(r"banking", re.IGNORECASE),
        re.compile(r"\bdeposit\b", re.IGNORECASE),
        re.compile(r"withdraw", re.IGNORECASE),
        re.compile(r"payout", re.IGNORECASE),
    ],
    ArticleType.REGISTRATION: [
        re.compile(r"regist", re.IGNORECASE),
        re.compile(r"sign[\s\-]?up", re.IGNORECASE),
        re.compile(r"create\s*account", re.IGNORECASE),
        re.compile(r"\bjoin\b", re.IGNORECASE),
    ],
    ArticleType.CUSTOMER_SUPPORT: [
        re.compile(r"\bsupport\b", re.IGNORECASE),
        re.compile(r"contact", re.IGNORECASE),
        re.compile(r"\bhelp\b", re.IGNORECASE),
        re.compile(r"live[\s\-]?chat", re.IGNORECASE),
    ],
    ArticleType.RESPONSIBLE_GAMING: [
        re.compile(r"responsible", re.IGNORECASE),
        re.compile(r"self[\s\-]?exclusion", re.IGNORECASE),
        re.compile(r"\blimits?\b", re.IGNORECASE),
        re.compile(r"addiction", re.IGNORECASE),
    ],
    ArticleType.VIP_LOYALTY: [
        re.compile(r"\bvip\b", re.IGNORECASE),
        re.compile(r"loyalty", re.IGNORECASE),
        re.compile(r"\brewards?\b", re.IGNORECASE),
        re.compile(r"\bpoints?\b", re.IGNORECASE),
    ],
    ArticleType.PRIVACY_POLICY: [
        re.compile(r"privacy", re.IGNORECASE),
        re.compile(r"\bpolicy\b", re.IGNORECASE),
        re.compile(r"terms", re.IGNORECASE),
        re.compile(r"conditions", re.IGNORECASE),
    ],
    ArticleType.LIVE_CASINO: [
        re.compile(r"live[\s\-]?casino", re.IGNORECASE),
        re.compile(r"live[\s\-]?dealer", re.IGNORECASE),
        re.compile(r"evolution", re.IGNORECASE),
    ],
}


def map_task_to_article_type(task_name: str) -> tuple[ArticleType, float]:
    """
    Map a task name to an article type cluster.

    Args:
        task_name: Raw task name from brief

    Returns:
        (ArticleType, confidence) tuple
    """
    if not task_name:
        return ArticleType.GENERAL, 0.3

    task_lower = task_name.lower().strip()

    # Check each article type's patterns
    for article_type, patterns in TASK_TYPE_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(task_lower):
                # Exact match at start gets higher confidence
                if pattern.match(task_lower):
                    return article_type, 0.95
                return article_type, 0.75

    # No match - return GENERAL with low confidence
    return ArticleType.GENERAL, 0.50
