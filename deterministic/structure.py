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
from deterministic.semantic_match import heading_matches, SEMANTIC_AVAILABLE


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


def _is_conditional_section(heading: str) -> bool:
    """
    Detect if a brief section is conditional (optional).

    Conditional markers include:
    - "if not exist"
    - "if applicable"
    - "optional"
    - "(general info if not exist)"
    """
    lower = heading.lower()
    conditional_markers = [
        "if not exist",
        "if applicable",
        "optional",
        "if available",
        "if present",
    ]
    return any(marker in lower for marker in conditional_markers)


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

        Uses semantic matching (sentence-transformers) if available,
        falls back to fuzzy word overlap matching.

        Semantic matching handles cases like:
        - "Registration Process" ↔ "Register to Get Started"
        - "Payment Methods" ↔ "How to Deposit"

        Categorizes unmatched sections:
        - MISSING: Brief requires it, article lacks it → warning (actionable)
        - CONDITIONAL: Brief says "if not exist" → info (lower priority)
        - DUPLICATE: Same section appears twice in brief → suppressed
        """
        findings: list[Finding] = []

        if not brief.sections:
            return findings

        article_headings = [h.text for h in headings]

        # Track coverage for summary finding
        coverage_results = []
        matched_count = 0
        missing_count = 0
        conditional_count = 0

        # Track seen sections to detect duplicates
        seen_sections: set[str] = set()

        for section in brief.sections:
            required = section.heading

            # Skip metadata labels that aren't real article sections
            # (e.g., "Main keywords", "Support keywords", "LSI keywords", "Word Count")
            if is_metadata_label(required):
                continue

            # Normalize for duplicate detection
            normalized = required.lower().strip()

            # Skip duplicates (same section listed twice in brief)
            if normalized in seen_sections:
                continue
            seen_sections.add(normalized)

            # Detect conditional sections (brief says "if not exist" or similar)
            is_conditional = _is_conditional_section(required)

            # Find best matching heading using semantic matching
            best_match = None
            best_score = 0.0
            match_method = "none"

            for actual in article_headings:
                is_match, score, method = heading_matches(required, actual)
                if score > best_score:
                    best_score = score
                    best_match = actual
                    match_method = method
                    # Don't break early - always find the BEST match

            # Determine if matched
            is_matched, _, _ = heading_matches(required, best_match) if best_match else (False, 0.0, "none")

            # Determine status
            if is_matched:
                status = "present"
            elif is_conditional:
                status = "conditional"
            else:
                status = "missing"

            # Record coverage result
            coverage_result = {
                "brief_section": required,
                "matched_heading": best_match if is_matched else None,
                "similarity_score": round(best_score, 3),
                "match_method": match_method,
                "status": status,
            }
            coverage_results.append(coverage_result)

            if is_matched:
                matched_count += 1
            elif is_conditional:
                conditional_count += 1
                # Conditional sections get info severity (lower priority)
                findings.append(FindingFactory.create(
                    check_name="structure.conditional_section",
                    category="structure",
                    severity="info",
                    confidence=0.70,
                    location=Location(paragraph_index=0, start_offset=0, end_offset=0),
                    original_text="",
                    reasoning=(
                        f"Brief mentions '{required}' as conditional. "
                        f"No matching heading found (best match: '{best_match}' "
                        f"at {round(best_score * 100, 1)}% similarity). "
                        f"This section may be optional per brief instructions."
                    ),
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={
                        "required_section": required,
                        "best_match": best_match,
                        "similarity_score": round(best_score, 3),
                        "match_method": match_method,
                        "section_type": "conditional",
                    },
                ))
            else:
                missing_count += 1
                # Missing required sections get warning severity (actionable)
                findings.append(FindingFactory.create(
                    check_name="structure.missing_section",
                    category="structure",
                    severity="warning",
                    confidence=0.85,
                    location=Location(paragraph_index=0, start_offset=0, end_offset=0),
                    original_text="",
                    reasoning=(
                        f"MISSING SECTION: Brief requires '{required}', but no matching "
                        f"heading found in article (best match: '{best_match}' "
                        f"at {round(best_score * 100, 1)}% similarity). "
                        f"The writer should add this section."
                    ),
                    auto_applicable=False,
                    proposed_text=None,
                    metadata={
                        "required_section": required,
                        "best_match": best_match,
                        "similarity_score": round(best_score, 3),
                        "match_method": match_method,
                        "article_headings": article_headings[:10],
                        "section_type": "required",
                    },
                ))

        # Add coverage summary finding
        if coverage_results:
            findings.append(self._create_coverage_summary(
                coverage_results, matched_count, missing_count, conditional_count, article_headings
            ))

        return findings

    def _create_coverage_summary(
        self,
        coverage_results: list[dict],
        matched_count: int,
        missing_count: int,
        conditional_count: int,
        article_headings: list[str],
    ) -> Finding:
        """Create coverage summary finding."""
        # Total excludes conditional (they're optional)
        total_required = matched_count + missing_count
        coverage_percent = round(matched_count / total_required * 100, 1) if total_required > 0 else 0

        # Determine severity based on MISSING count (not conditional)
        if missing_count == 0:
            severity = "info"
        elif coverage_percent >= 80:
            severity = "suggestion"
        else:
            severity = "warning"

        # Build reasoning string
        parts = [f"Section coverage: {matched_count}/{total_required} required sections matched ({coverage_percent}%)."]
        if missing_count > 0:
            parts.append(f"{missing_count} section(s) MISSING (actionable).")
        if conditional_count > 0:
            parts.append(f"{conditional_count} conditional section(s) not found (optional).")
        if missing_count == 0 and conditional_count == 0:
            parts.append("All required sections found.")
        parts.append(f"Match method: {'semantic' if SEMANTIC_AVAILABLE else 'fuzzy'}.")

        return FindingFactory.create(
            check_name="structure.coverage",
            category="structure",
            severity=severity,
            confidence=1.0,
            location=Location(paragraph_index=0, start_offset=0, end_offset=0),
            original_text="",
            reasoning=" ".join(parts),
            auto_applicable=False,
            proposed_text=None,
            metadata={
                "matched_count": matched_count,
                "missing_count": missing_count,
                "conditional_count": conditional_count,
                "total_required": total_required,
                "coverage_percent": coverage_percent,
                "match_method": "semantic" if SEMANTIC_AVAILABLE else "fuzzy",
                "coverage_details": coverage_results,
                "article_headings": article_headings,
            },
        )

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

        Note: Skips trailing empty paragraphs (conversion cruft, blank_rows insertion)
        to find the true last content element.
        """
        findings: list[Finding] = []

        if not document.elements:
            return findings

        # Find last non-empty element (skip trailing empty paragraphs)
        last_element = None
        for element in reversed(document.elements):
            if isinstance(element, Paragraph) and not element.text.strip():
                continue  # Skip empty paragraph
            last_element = element
            break

        if last_element is None:
            # Document is all empty paragraphs - no content to check
            return findings

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
