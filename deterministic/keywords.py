"""
Pitboss v4 - Keywords Check: Coverage, Density, and Highlighting

Deterministic check that compares article content against brief requirements.
Enforces General Writing Requirements Section 8:
- Use ALL main keywords given in the task, as they are
- Main keywords should be highlighted in yellow
- Keyword density must be up to 3% (flag if exceeded)
- Don't overuse brand names or location keywords

CRITICAL: All findings are FLAG/PROPOSAL, never auto-apply.
Keyword work is inherently editorial judgment (Section 8: "prioritize
readability over keyword integration"). The check informs; the human decides.
"""

from __future__ import annotations
import re
from typing import Any, Optional
from collections import defaultdict

from core.check_base import DeterministicCheck, register_check
from core.document import Document, Location
from core.finding import Finding, FindingFactory, Category


# =============================================================================
# CONSTANTS
# =============================================================================

# Maximum keyword density before flagging (Section 8: "up to 3%")
MAX_DENSITY_PERCENT = 3.0

# Brand name overuse threshold (flag if brand exceeds this % of words)
BRAND_OVERUSE_PERCENT = 2.0

# Minimum words in document to compute meaningful density
MIN_WORDS_FOR_DENSITY = 50


# =============================================================================
# KEYWORD MATCHING UTILITIES
# =============================================================================

def normalize_keyword(kw: str) -> str:
    """Normalize keyword for matching: lowercase, collapse whitespace."""
    return " ".join(kw.lower().split())


def get_keyword_variants(kw: str) -> set[str]:
    """
    Generate variants of a keyword for matching.

    Handles:
    - Singular/plural forms (basic s/es)
    - Case variations (handled by normalize)

    Strategy: Generate BOTH singular and plural forms regardless of input,
    to handle cases where we don't know if input is singular or plural.
    """
    normalized = normalize_keyword(kw)
    variants = {normalized}

    words = normalized.split()
    if not words:
        return variants

    last_word = words[-1]
    prefix = " ".join(words[:-1])
    prefix_space = prefix + " " if prefix else ""

    # Generate potential singular forms (if word looks plural)
    if last_word.endswith("ies") and len(last_word) > 3:
        # categories -> category
        variants.add(prefix_space + last_word[:-3] + "y")
    if last_word.endswith("ses") and len(last_word) > 3:
        # bonuses -> bonus
        variants.add(prefix_space + last_word[:-2])
    if last_word.endswith("xes") and len(last_word) > 3:
        # boxes -> box
        variants.add(prefix_space + last_word[:-2])
    if last_word.endswith("ches") and len(last_word) > 4:
        # matches -> match
        variants.add(prefix_space + last_word[:-2])
    if last_word.endswith("shes") and len(last_word) > 4:
        # flashes -> flash
        variants.add(prefix_space + last_word[:-2])
    # Only strip final 's' for words that look like simple plurals
    # (end in consonant + s, not "ss", "us", "is")
    if (last_word.endswith("s") and len(last_word) > 2 and
            not last_word.endswith(("ss", "us", "is", "es"))):
        # slots -> slot
        variants.add(prefix_space + last_word[:-1])

    # Generate potential plural forms (if word looks singular)
    # Standard plural: slot -> slots
    if not last_word.endswith("s"):
        variants.add(prefix_space + last_word + "s")
    # -es plural for words ending in s, x, ch, sh
    if last_word.endswith(("s", "x", "ch", "sh")) and not last_word.endswith("es"):
        variants.add(prefix_space + last_word + "es")
    # -ies plural for words ending in consonant + y
    if last_word.endswith("y") and len(last_word) > 1 and last_word[-2] not in "aeiou":
        variants.add(prefix_space + last_word[:-1] + "ies")

    return variants


def find_keyword_occurrences(
    text: str,
    keyword: str,
    already_matched: Optional[set[tuple[int, int]]] = None,
) -> list[tuple[int, int]]:
    """
    Find all occurrences of a keyword in text.

    Returns list of (start, end) positions.
    Avoids double-counting overlapping matches if already_matched is provided.
    """
    if already_matched is None:
        already_matched = set()

    occurrences = []
    text_lower = text.lower()

    # Get all variants to match
    variants = get_keyword_variants(keyword)

    for variant in variants:
        if not variant:
            continue

        # Build regex for whole-phrase match (word boundaries)
        pattern = r"\b" + re.escape(variant) + r"\b"

        for match in re.finditer(pattern, text_lower):
            start, end = match.start(), match.end()

            # Check for overlap with already matched spans
            overlaps = False
            for (ms, me) in already_matched:
                # Overlap if ranges intersect
                if not (end <= ms or start >= me):
                    overlaps = True
                    break

            if not overlaps:
                occurrences.append((start, end))
                already_matched.add((start, end))

    return occurrences


def count_words(text: str) -> int:
    """Count words in text."""
    return len(re.findall(r"\b\w+\b", text))


def find_words_nearby(text: str, keyword: str, max_distance: int = 50) -> Optional[str]:
    """
    Check if the words of a multi-word keyword appear nearby in text,
    even if not as the exact phrase.

    Returns a sample of the text where words appear close together,
    or None if words don't appear nearby.

    Args:
        text: The document text to search
        keyword: The multi-word keyword to check
        max_distance: Maximum character distance between words

    Returns:
        Sample text showing the nearby occurrence, or None
    """
    words = keyword.lower().split()
    if len(words) < 2:
        return None

    text_lower = text.lower()

    # Find positions of each word
    word_positions: dict[str, list[int]] = {}
    for word in words:
        pattern = r"\b" + re.escape(word) + r"\b"
        word_positions[word] = [m.start() for m in re.finditer(pattern, text_lower)]

    # If any word is completely absent, return None
    if not all(word_positions.values()):
        return None

    # Find clusters where all words appear within max_distance characters
    for first_pos in word_positions[words[0]]:
        all_nearby = True
        for word in words[1:]:
            found_nearby = False
            for pos in word_positions[word]:
                if abs(pos - first_pos) < max_distance:
                    found_nearby = True
                    break
            if not found_nearby:
                all_nearby = False
                break

        if all_nearby:
            # Extract sample text around this cluster
            sample_start = max(0, first_pos - 5)
            sample_end = min(len(text), first_pos + max_distance + 10)
            sample = text[sample_start:sample_end].replace('\n', ' ').strip()
            return sample

    return None


# =============================================================================
# KEYWORDS CHECK
# =============================================================================

@register_check
class KeywordsCheck(DeterministicCheck):
    """
    Check keyword coverage, density, and highlighting against brief requirements.

    Sub-checks:
    1. Missing main keywords (flag absent required keywords)
    2. Keyword quantity (actual vs required min/max)
    3. Keyword density (flag if > 3%)
    4. Keyword highlighting (main keywords should be yellow)
    5. Brand/location overuse (flag stuffing)

    All findings are proposals (auto_applicable=False).
    """

    def _get_name(self) -> str:
        return "keywords"

    def _get_display_name(self) -> str:
        return "Keyword Coverage and Density"

    def _get_category(self) -> Category:
        return "keywords"

    def _get_description(self) -> str:
        return (
            "Checks keyword coverage, quantity, density, and highlighting "
            "against brief requirements (Section 8)"
        )

    def _get_required_standards(self) -> tuple[str, ...]:
        return ("brand_name",)

    def run(
        self,
        document: Document,
        standards: Any,
        voice_model: Optional[Any] = None,
        brief: Optional[Any] = None,
    ) -> list[Finding]:
        """
        Execute keyword checks.

        Args:
            document: The document to check
            standards: Brand standards
            voice_model: Ignored for this check
            brief: Optional BriefModel with keyword requirements

        Returns:
            List of findings (all proposals, never auto-applicable)
        """
        return self._find_issues(document, standards, brief)

    def _find_issues(
        self,
        document: Document,
        standards: Any,
        brief: Optional[Any] = None,
    ) -> list[Finding]:
        """Find keyword-related issues."""
        findings: list[Finding] = []

        # No brief = no-op gracefully
        if brief is None:
            return findings

        # Duck typing check - brief needs keywords attribute with main keywords
        if not hasattr(brief, "keywords") or not hasattr(brief.keywords, "main"):
            return findings

        # Get article text
        full_text = document.full_text()
        word_count = count_words(full_text)

        # Skip if document is too short for any meaningful analysis
        if word_count < 10:
            return findings

        # Get highlighted spans from document
        highlighted_spans = document.highlighted_spans()
        highlighted_text_lower = {
            span[0].lower() for span in highlighted_spans
        }

        # Track all keyword occurrences for density calculation
        all_keyword_occurrences: dict[str, list[tuple[int, int]]] = defaultdict(list)
        already_matched: set[tuple[int, int]] = set()

        # Get main keywords from brief, sorted by length (longest first)
        # This ensures longer phrases like "Koifortune Australia" are matched
        # before shorter ones like "Koifortune", preventing overlap collisions
        main_keywords: list[BriefKeyword] = sorted(
            brief.keywords.main,
            key=lambda kw: len(kw.keyword),
            reverse=True
        )

        # Sub-check 1 & 2: Missing keywords and quantity
        for kw_obj in main_keywords:
            keyword = kw_obj.keyword
            min_qty = kw_obj.min_quantity
            max_qty = kw_obj.max_quantity

            # Find occurrences
            occurrences = find_keyword_occurrences(
                full_text, keyword, already_matched
            )
            all_keyword_occurrences[keyword] = occurrences
            actual_count = len(occurrences)

            # Check if missing
            if actual_count == 0:
                # Build requirement string
                if min_qty is not None and max_qty is not None:
                    if min_qty == max_qty:
                        req_str = f"required exactly {min_qty} time(s)"
                    else:
                        req_str = f"required {min_qty}-{max_qty} time(s)"
                elif min_qty is not None:
                    req_str = f"required at least {min_qty} time(s)"
                elif max_qty is not None:
                    req_str = f"required at most {max_qty} time(s)"
                else:
                    req_str = "required in article"

                # Check if words appear nearby but not as exact phrase
                nearby_sample = find_words_nearby(full_text, keyword)

                if nearby_sample:
                    # Words present but wrong construction
                    missing_type = "wrong_construction"
                    reasoning = (
                        f"Required keyword '{keyword}' not found. "
                        f"Note: article contains '{nearby_sample}' — the words are present "
                        f"but not as the exact keyword phrase. The writer may need to adjust "
                        f"wording to use the keyword as specified. Brief specifies: {req_str}."
                    )
                else:
                    # Truly absent - concept not in article
                    missing_type = "truly_absent"
                    reasoning = (
                        f"Main keyword '{keyword}' is missing from the article. "
                        f"Brief specifies: {req_str}."
                    )

                findings.append(FindingFactory.create(
                    check_name="keywords.missing",
                    category="keywords",
                    severity="warning",
                    confidence=0.95,
                    location=Location(paragraph_index=0, start_offset=0, end_offset=0),
                    original_text="",
                    reasoning=reasoning,
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={
                        "keyword": keyword,
                        "actual_count": 0,
                        "min_qty": min_qty,
                        "max_qty": max_qty,
                        "missing_type": missing_type,
                    },
                ))
                continue

            # Check quantity (if min/max specified)
            if min_qty is not None and actual_count < min_qty:
                findings.append(FindingFactory.create(
                    check_name="keywords.quantity",
                    category="keywords",
                    severity="warning",
                    confidence=0.90,
                    location=Location(
                        paragraph_index=0,
                        start_offset=occurrences[0][0] if occurrences else 0,
                        end_offset=occurrences[0][1] if occurrences else 0,
                    ),
                    original_text=keyword,
                    reasoning=(
                        f"Keyword '{keyword}' appears {actual_count} time(s) but "
                        f"brief requires at least {min_qty}."
                    ),
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={"keyword": keyword, "actual_count": actual_count, "min_qty": min_qty},
                ))

            if max_qty is not None and actual_count > max_qty:
                findings.append(FindingFactory.create(
                    check_name="keywords.quantity",
                    category="keywords",
                    severity="warning",
                    confidence=0.90,
                    location=Location(
                        paragraph_index=0,
                        start_offset=occurrences[0][0] if occurrences else 0,
                        end_offset=occurrences[0][1] if occurrences else 0,
                    ),
                    original_text=keyword,
                    reasoning=(
                        f"Keyword '{keyword}' appears {actual_count} time(s) but "
                        f"brief allows at most {max_qty}."
                    ),
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={"keyword": keyword, "actual_count": actual_count, "max_qty": max_qty},
                ))

        # Sub-check 3: Keyword density (only for documents with enough words)
        total_keyword_occurrences = sum(
            len(occs) for occs in all_keyword_occurrences.values()
        )
        density = (total_keyword_occurrences / word_count) * 100

        if density > MAX_DENSITY_PERCENT and word_count >= MIN_WORDS_FOR_DENSITY:
            findings.append(FindingFactory.create(
                check_name="keywords.density",
                category="keywords",
                severity="warning",
                confidence=0.95,
                location=Location(paragraph_index=0, start_offset=0, end_offset=0),
                original_text="",
                reasoning=(
                    f"Overall keyword density is {density:.1f}%, exceeding the "
                    f"{MAX_DENSITY_PERCENT}% limit (Section 8). "
                    f"Total keywords: {total_keyword_occurrences}, words: {word_count}."
                ),
                auto_applicable=False,
                proposed_text=None,
                metadata={"density": density, "keyword_count": total_keyword_occurrences, "word_count": word_count},
            ))

        # Sub-check 4: Keyword highlighting
        # Check which main keywords appear but are NOT highlighted
        for kw_obj in main_keywords:
            keyword = kw_obj.keyword
            occurrences = all_keyword_occurrences.get(keyword, [])

            if not occurrences:
                continue  # Already flagged as missing

            # Check if any variant is highlighted
            variants = get_keyword_variants(keyword)
            is_highlighted = any(
                variant in highlighted_text_lower or variant.lower() in highlighted_text_lower
                for variant in variants
            )

            if not is_highlighted:
                # Find first occurrence for location
                first_occ = occurrences[0]
                findings.append(FindingFactory.create(
                    check_name="keywords.highlighting",
                    category="keywords",
                    severity="suggestion",
                    confidence=0.85,
                    location=Location(
                        paragraph_index=0,
                        start_offset=first_occ[0],
                        end_offset=first_occ[1],
                    ),
                    original_text=full_text[first_occ[0]:first_occ[1]],
                    reasoning=(
                        f"Main keyword '{keyword}' appears in article but is not "
                        f"highlighted in yellow (Section 8 requirement)."
                    ),
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={"keyword": keyword, "occurrences": len(occurrences)},
                ))

        # Sub-check 5: Brand name overuse
        brand_name = getattr(standards, "brand_name", None) or getattr(brief, "brand_name", None)
        if brand_name:
            brand_occurrences = find_keyword_occurrences(full_text, brand_name, set())
            brand_count = len(brand_occurrences)
            brand_density = (brand_count / word_count) * 100

            if brand_density > BRAND_OVERUSE_PERCENT:
                findings.append(FindingFactory.create(
                    check_name="keywords.brand_overuse",
                    category="keywords",
                    severity="warning",
                    confidence=0.85,
                    location=Location(
                        paragraph_index=0,
                        start_offset=brand_occurrences[0][0] if brand_occurrences else 0,
                        end_offset=brand_occurrences[0][1] if brand_occurrences else 0,
                    ),
                    original_text=brand_name,
                    reasoning=(
                        f"Brand name '{brand_name}' appears {brand_count} times "
                        f"({brand_density:.1f}% of words). Section 8 warns against "
                        f"overusing brand names. Consider natural variations."
                    ),
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={"brand_name": brand_name, "count": brand_count, "density": brand_density},
                ))

        # Check location keyword overuse (from brief's market field)
        market = getattr(brief, "market", None)
        if market and len(market) > 2:  # Skip short codes like "AU"
            market_occurrences = find_keyword_occurrences(full_text, market, set())
            market_count = len(market_occurrences)
            market_density = (market_count / word_count) * 100

            if market_density > BRAND_OVERUSE_PERCENT:
                findings.append(FindingFactory.create(
                    check_name="keywords.location_overuse",
                    category="keywords",
                    severity="warning",
                    confidence=0.80,
                    location=Location(
                        paragraph_index=0,
                        start_offset=market_occurrences[0][0] if market_occurrences else 0,
                        end_offset=market_occurrences[0][1] if market_occurrences else 0,
                    ),
                    original_text=market,
                    reasoning=(
                        f"Location keyword '{market}' appears {market_count} times "
                        f"({market_density:.1f}% of words). Section 8 warns against "
                        f"overusing location keywords."
                    ),
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={"location": market, "count": market_count, "density": market_density},
                ))

        return findings
