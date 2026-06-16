"""
Pitboss v4 - Structure Check: Article vs Brief Requirements

Deterministic check comparing article structure against:
- Brief's required sections/headings
- General Writing Requirements §10 (descriptive headings, logical hierarchy,
  intro/outro paragraphs)

CRITICAL: All findings are FLAG/PROPOSAL, never auto-apply.
Structural changes require editorial judgment.
"""

from __future__ import annotations
import re
from typing import Any, Optional

from core.check_base import DeterministicCheck, register_check
from core.document import Document, Location, Heading, Paragraph
from core.finding import Finding, FindingFactory, Category
from ingest.brief_base import is_metadata_label


# =============================================================================
# CONSTANTS
# =============================================================================

# Word count deviation threshold (flag if >20% off)
WORD_COUNT_DEVIATION_THRESHOLD = 0.20

# Minimum words for a proper outro paragraph
MIN_OUTRO_WORDS = 20

# Fuzzy section match threshold (50% word overlap)
FUZZY_MATCH_THRESHOLD = 0.5


# =============================================================================
# FUZZY SECTION MATCHING
# =============================================================================

def normalize_heading(text: str) -> str:
    """Normalize heading for comparison: lowercase, strip punctuation."""
    return re.sub(r'[^\w\s]', '', text.lower()).strip()


def fuzzy_section_match(required: str, actual: str) -> bool:
    """
    Check if actual heading matches required section (fuzzy).

    Matches if:
    - Required is substring of actual (case-insensitive, normalized)
    - ≥50% of required words appear in actual

    This is intentionally fuzzy (unlike keyword exact-phrase matching)
    because we're matching concepts/sections, not SEO keywords.

    Examples:
        "Bonuses" matches "Welcome Bonuses and Promotions" (substring)
        "Payment Methods" matches "Methods of Payment" (50%+ word overlap)
        "Bonuses" does NOT match "Customer Support" (no overlap)
    """
    req_norm = normalize_heading(required)
    act_norm = normalize_heading(actual)

    if not req_norm:
        return False

    # Substring match (required appears within actual)
    if req_norm in act_norm:
        return True

    # Word overlap match
    req_words = set(req_norm.split())
    act_words = set(act_norm.split())

    if not req_words:
        return False

    overlap = len(req_words & act_words) / len(req_words)
    return overlap >= FUZZY_MATCH_THRESHOLD


def count_words(text: str) -> int:
    """Count words in text."""
    return len(re.findall(r'\b\w+\b', text))


# =============================================================================
# STRUCTURE CHECK
# =============================================================================

@register_check
class StructureCheck(DeterministicCheck):
    """
    Check article structure against brief requirements and §10 rules.

    Sub-checks:
    1. Missing required sections (fuzzy match against brief)
    2. Heading hierarchy (no skipped levels, single H1)
    3. Intro presence (content before first heading)
    4. Outro presence (proper closing paragraph)
    5. Word count vs brief target (>20% deviation)

    All findings are proposals (auto_applicable=False).
    """

    def _get_name(self) -> str:
        return "structure"

    def _get_display_name(self) -> str:
        return "Document Structure"

    def _get_category(self) -> Category:
        return "structure"

    def _get_description(self) -> str:
        return (
            "Validates article structure against brief requirements "
            "and General Writing Requirements Section 10"
        )

    def run(
        self,
        document: Document,
        standards: Any,
        voice_model: Optional[Any] = None,
        brief: Optional[Any] = None,
    ) -> list[Finding]:
        """
        Execute structure checks.

        Args:
            document: The document to check
            standards: Brand standards (not used by this check)
            voice_model: Ignored for this check
            brief: Optional BriefModel with structure requirements

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
        """Find structure-related issues."""
        findings: list[Finding] = []

        # Get document headings and text
        headings = document.headings()
        full_text = document.full_text()
        actual_word_count = count_words(full_text)

        # Sub-check 2: Hierarchy (doesn't need brief)
        findings.extend(self._check_hierarchy(headings))

        # Sub-check 3: Intro presence (doesn't need brief)
        findings.extend(self._check_intro(document, headings))

        # Sub-check 4: Outro presence (doesn't need brief)
        findings.extend(self._check_outro(document))

        # Brief-dependent checks: no-op gracefully if no brief
        if brief is None:
            return findings

        # Duck typing check for sections
        if not hasattr(brief, "sections"):
            return findings

        # Sub-check 1: Required sections present
        findings.extend(self._check_required_sections(brief, headings))

        # Sub-check 5: Word count vs target
        if hasattr(brief, "target_word_count") and brief.target_word_count:
            findings.extend(self._check_word_count(
                actual_word_count, brief.target_word_count
            ))

        return findings

    def _check_required_sections(
        self,
        brief: Any,
        headings: list[Heading],
    ) -> list[Finding]:
        """
        Check if required sections from brief are present in article.

        Uses fuzzy matching - "Bonuses" matches "Welcome Bonuses and Promotions".
        """
        findings: list[Finding] = []

        if not brief.sections:
            return findings

        article_headings = [h.text for h in headings]

        for section in brief.sections:
            required = section.heading

            # Skip metadata labels that aren't real article sections
            # (e.g., "Main keywords", "Support keywords", "LSI keywords", "Word Count")
            if is_metadata_label(required):
                continue

            # Check if any article heading matches (fuzzy)
            matched = any(
                fuzzy_section_match(required, actual)
                for actual in article_headings
            )

            if not matched:
                findings.append(FindingFactory.create(
                    check_name="structure.missing_section",
                    category="structure",
                    severity="warning",
                    confidence=0.85,
                    location=Location(paragraph_index=0, start_offset=0, end_offset=0),
                    original_text="",
                    reasoning=(
                        f"Brief requires a '{required}' section, but no matching "
                        f"heading found in article. The writer may need to add this section."
                    ),
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={
                        "required_section": required,
                        "article_headings": article_headings[:10],
                    },
                ))

        return findings

    def _check_hierarchy(self, headings: list[Heading]) -> list[Finding]:
        """
        Check heading hierarchy per §10.

        Flags:
        - Multiple H1 headings (should have only one main title)
        - Skipped levels (H1 → H3 with no H2)
        """
        findings: list[Finding] = []

        if not headings:
            return findings

        # Check for multiple H1
        h1_headings = [h for h in headings if h.level.value == 1]
        if len(h1_headings) > 1:
            # Location at second H1
            second_h1 = h1_headings[1]
            findings.append(FindingFactory.create(
                check_name="structure.hierarchy",
                category="structure",
                severity="warning",
                confidence=0.95,
                location=Location(
                    paragraph_index=0,
                    start_offset=second_h1.start_offset,
                    end_offset=second_h1.end_offset,
                ),
                original_text=second_h1.text,
                reasoning=(
                    f"Document has {len(h1_headings)} H1 headings. "
                    f"Per Section 10, there should be only one main title (H1)."
                ),
                auto_applicable=False,
                proposed_text=None,
                metadata={
                    "h1_count": len(h1_headings),
                    "h1_texts": [h.text for h in h1_headings],
                },
            ))

        # Check for skipped levels
        prev_level = 0
        for heading in headings:
            level = heading.level.value

            # Allow any level as first heading
            if prev_level == 0:
                prev_level = level
                continue

            # Check if level skipped (e.g., H1 → H3 with no H2)
            if level > prev_level + 1:
                findings.append(FindingFactory.create(
                    check_name="structure.hierarchy",
                    category="structure",
                    severity="warning",
                    confidence=0.90,
                    location=Location(
                        paragraph_index=0,
                        start_offset=heading.start_offset,
                        end_offset=heading.end_offset,
                    ),
                    original_text=heading.text,
                    reasoning=(
                        f"Heading '{heading.text}' is H{level} but follows H{prev_level}. "
                        f"Per Section 10, heading hierarchy should not skip levels "
                        f"(expected H{prev_level + 1} or lower)."
                    ),
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={
                        "heading_text": heading.text,
                        "heading_level": level,
                        "previous_level": prev_level,
                        "expected_max_level": prev_level + 1,
                    },
                ))

            prev_level = level

        return findings

    def _check_intro(
        self,
        document: Document,
        headings: list[Heading],
    ) -> list[Finding]:
        """
        Check for introductory content before first heading.

        §10: "first paragraph should stand out" - article should have
        an intro paragraph before diving into headings.
        """
        findings: list[Finding] = []

        if not headings:
            # No headings = can't check for content before first heading
            return findings

        first_heading_offset = headings[0].start_offset

        # Check if there's paragraph content before first heading
        intro_paragraphs = []
        for element in document.elements:
            if element.start_offset >= first_heading_offset:
                break
            if isinstance(element, Paragraph):
                # Only count paragraphs with meaningful content
                if count_words(element.text) > 5:
                    intro_paragraphs.append(element)

        if not intro_paragraphs:
            findings.append(FindingFactory.create(
                check_name="structure.missing_intro",
                category="structure",
                severity="suggestion",
                confidence=0.75,
                location=Location(paragraph_index=0, start_offset=0, end_offset=0),
                original_text="",
                reasoning=(
                    "Article begins directly with a heading without an introductory "
                    "paragraph. Per Section 10, the first paragraph should stand out "
                    "and introduce the content."
                ),
                auto_applicable=False,
                proposed_text=None,
                metadata={
                    "first_heading": headings[0].text,
                    "first_heading_level": headings[0].level.value,
                },
            ))

        return findings

    def _check_outro(self, document: Document) -> list[Finding]:
        """
        Check for proper closing paragraph.

        §10: "last paragraph should stand out" - article should have
        a proper conclusion, not end abruptly with a heading or very short text.
        """
        findings: list[Finding] = []

        if not document.elements:
            return findings

        last_element = document.elements[-1]

        # Check if last element is a heading (no conclusion at all)
        if isinstance(last_element, Heading):
            findings.append(FindingFactory.create(
                check_name="structure.missing_outro",
                category="structure",
                severity="suggestion",
                confidence=0.80,
                location=Location(
                    paragraph_index=0,
                    start_offset=last_element.start_offset,
                    end_offset=last_element.end_offset,
                ),
                original_text=last_element.text,
                reasoning=(
                    f"Article ends with the heading '{last_element.text}' rather "
                    f"than a concluding paragraph. Per Section 10, the last paragraph "
                    f"should stand out as a proper conclusion."
                ),
                auto_applicable=False,
                proposed_text=None,
                metadata={
                    "last_element_type": "heading",
                    "last_element_text": last_element.text,
                },
            ))
        elif isinstance(last_element, Paragraph):
            # Check if conclusion is too short
            word_count = count_words(last_element.text)
            if word_count < MIN_OUTRO_WORDS:
                findings.append(FindingFactory.create(
                    check_name="structure.missing_outro",
                    category="structure",
                    severity="suggestion",
                    confidence=0.70,
                    location=Location(
                        paragraph_index=0,
                        start_offset=last_element.start_offset,
                        end_offset=last_element.end_offset,
                    ),
                    original_text=last_element.text,
                    reasoning=(
                        f"Final paragraph has only {word_count} words. "
                        f"Per Section 10, the last paragraph should stand out "
                        f"as a proper conclusion (consider expanding to at least "
                        f"{MIN_OUTRO_WORDS} words)."
                    ),
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={
                        "last_element_type": "paragraph",
                        "word_count": word_count,
                        "min_words": MIN_OUTRO_WORDS,
                    },
                ))

        return findings

    def _check_word_count(self, actual: int, target: int) -> list[Finding]:
        """
        Check if article word count is within acceptable deviation from brief target.

        Flags if >20% deviation:
        - Under: likely missing content
        - Over: may need trimming
        """
        findings: list[Finding] = []

        if target <= 0:
            return findings

        deviation = abs(actual - target) / target

        if deviation > WORD_COUNT_DEVIATION_THRESHOLD:
            if actual < target:
                direction = "under"
                concern = "likely missing content"
            else:
                direction = "over"
                concern = "may need trimming"

            deviation_percent = round(deviation * 100, 1)

            findings.append(FindingFactory.create(
                check_name="structure.word_count",
                category="structure",
                severity="warning",
                confidence=0.90,
                location=Location(paragraph_index=0, start_offset=0, end_offset=0),
                original_text="",
                reasoning=(
                    f"Article is {actual} words, {direction} the brief's target of "
                    f"{target} words ({deviation_percent}% deviation). "
                    f"{concern.capitalize()}."
                ),
                auto_applicable=False,
                proposed_text=None,
                metadata={
                    "actual_words": actual,
                    "target_words": target,
                    "deviation_percent": deviation_percent,
                    "direction": direction,
                },
            ))

        return findings
