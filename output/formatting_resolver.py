"""
Pitboss v4 - Formatting Resolver

Resolves formatting decisions (like blank_rows) based on a priority hierarchy:
1. Brief formatting hints (explicit instructions)
2. Article type (META_SEO/PRIVACY_POLICY -> none)
3. Market + article type combination
4. Filename patterns
5. Brand config fallback
6. Default (proposal)

This logic is centralized here for testability and single-source-of-truth.
"""

from __future__ import annotations
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ingest.brief_model import BriefModel, ArticleType


# Markets that use blank rows when combined with market-facing article types
BLANK_ROWS_MARKETS = frozenset({
    "au", "australia",
    "ca", "canada",
    "nz", "new zealand",
    "uk", "united kingdom",
    "ie", "ireland",
})

# Article types that are market-facing (show blank rows when in a known market)
MARKET_FACING_TYPES = frozenset({
    "main_review",
    "bonus_page",
    "app_review",
    "game_review",
    "sports_market",
    "payments",
    "registration",
    "customer_support",
    "vip_loyalty",
    "live_casino",
})

# Article types that never use blank rows
NO_BLANK_ROWS_TYPES = frozenset({
    "meta_seo",
    "privacy_policy",
})

# Filename patterns for blank_rows detection
FILENAME_META_PATTERN = re.compile(r"^Meta\s*Title[_\s]", re.IGNORECASE)
FILENAME_REGION_PATTERNS = [
    re.compile(r"\b(AU|Australia)\b", re.IGNORECASE),
    re.compile(r"\b(CA|Canada)\b", re.IGNORECASE),
    re.compile(r"\b(NZ|New\s*Zealand)\b", re.IGNORECASE),
    re.compile(r"\b(UK|United\s*Kingdom)\b", re.IGNORECASE),
    re.compile(r"\b(IE|Ireland)\b", re.IGNORECASE),
]

# Brands with consistent blank_rows behavior (from corpus analysis)
# These are fallbacks when no brief/filename signal is available
BRAND_BLANK_ROWS_CONFIG = {
    # Consistent HIGH (35-45% empty paragraphs in corpus)
    "20bet": "required",
    "avalon78": "required",
    "casinochan": "required",
    "ivibet": "required",
    "masonslots": "required",
    "playamo": "required",
    "royalxo": "required",
    "slotrave": "required",
    # Consistent LOW (3-8% empty paragraphs in corpus)
    "national": "none",
    "safecasino": "none",
    # All other brands: not in this dict -> use default
}


def resolve_blank_rows(
    brief: Optional["BriefModel"] = None,
    brand_config: Optional[dict] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Resolve blank_rows setting based on priority hierarchy.

    Priority (highest to lowest):
    1. Brief formatting_hints["blank_rows"] - explicit instruction wins
    2. Article type META_SEO or PRIVACY_POLICY -> "none"
    3. Brief market (AU/Canada/etc) + market-facing article type -> "required"
    4. Filename patterns: "Meta Title_" -> "none"; region markers -> "required"
    5. Brand config (consistent-high -> required, consistent-low -> none)
    6. Default -> "proposal" (don't auto-insert, surface as comment)

    Args:
        brief: BriefModel with article_type, market, formatting_hints
        brand_config: Brand configuration dict (may have "blank_rows" key)
        filename: Original filename for pattern matching

    Returns:
        "required" | "none" | "proposal"
    """
    # Priority 1: Brief formatting hints (explicit instruction)
    if brief is not None:
        hint = brief.get_formatting_hint("blank_rows")
        if hint in ("required", "none"):
            return hint

    # Priority 2: Article type that never uses blank rows
    if brief is not None:
        article_type_value = brief.article_type.value
        if article_type_value in NO_BLANK_ROWS_TYPES:
            return "none"

    # Priority 3: Market + market-facing article type
    if brief is not None:
        market = (brief.market or "").lower().strip()
        article_type_value = brief.article_type.value

        if market in BLANK_ROWS_MARKETS and article_type_value in MARKET_FACING_TYPES:
            return "required"

    # Priority 4: Filename patterns
    if filename:
        # "Meta Title_" prefix -> none
        if FILENAME_META_PATTERN.search(filename):
            return "none"

        # Region markers -> required
        for pattern in FILENAME_REGION_PATTERNS:
            if pattern.search(filename):
                return "required"

    # Priority 5: Brand config fallback
    if brand_config is not None:
        # Check if brand_config has explicit blank_rows setting
        if "blank_rows" in brand_config:
            return brand_config["blank_rows"]

        # Check brand name against known consistent brands
        brand_name = brand_config.get("brand_name", "").lower().strip()
        if brand_name in BRAND_BLANK_ROWS_CONFIG:
            return BRAND_BLANK_ROWS_CONFIG[brand_name]

    # Priority 6: Default - proposal (don't auto-insert)
    return "proposal"


def get_blank_rows_reason(
    brief: Optional["BriefModel"] = None,
    brand_config: Optional[dict] = None,
    filename: Optional[str] = None,
) -> tuple[str, str]:
    """
    Get blank_rows resolution with explanation of why.

    Returns:
        Tuple of (resolution, reason) for debugging/logging.
    """
    # Priority 1: Brief formatting hints
    if brief is not None:
        hint = brief.get_formatting_hint("blank_rows")
        if hint in ("required", "none"):
            return hint, f"brief formatting hint: blank_rows={hint}"

    # Priority 2: Article type
    if brief is not None:
        article_type_value = brief.article_type.value
        if article_type_value in NO_BLANK_ROWS_TYPES:
            return "none", f"article type {article_type_value} never uses blank rows"

    # Priority 3: Market + type
    if brief is not None:
        market = (brief.market or "").lower().strip()
        article_type_value = brief.article_type.value

        if market in BLANK_ROWS_MARKETS and article_type_value in MARKET_FACING_TYPES:
            return "required", f"market '{market}' + type '{article_type_value}' -> required"

    # Priority 4: Filename
    if filename:
        if FILENAME_META_PATTERN.search(filename):
            return "none", f"filename pattern 'Meta Title_' -> none"

        for pattern in FILENAME_REGION_PATTERNS:
            match = pattern.search(filename)
            if match:
                return "required", f"filename region marker '{match.group()}' -> required"

    # Priority 5: Brand config
    if brand_config is not None:
        if "blank_rows" in brand_config:
            val = brand_config["blank_rows"]
            return val, f"brand config explicit: blank_rows={val}"

        brand_name = brand_config.get("brand_name", "").lower().strip()
        if brand_name in BRAND_BLANK_ROWS_CONFIG:
            val = BRAND_BLANK_ROWS_CONFIG[brand_name]
            return val, f"brand '{brand_name}' corpus pattern -> {val}"

    # Priority 6: Default
    return "proposal", "no strong signal, default to proposal (human review)"
