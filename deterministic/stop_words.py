"""
Pitboss v4 - Stop Words Check

Deterministic check that detects AI-associated stop words from weighted tiers:
- Hard tier (weight 1.0): Always flagged, severity "warning"
- Soft tier (weight 0.3): Flagged only above density threshold, severity "suggestion"

No auto-fix or proposed replacements - detection only.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any, Optional

from core.check_base import DeterministicCheck, register_check
from core.document import Document, Paragraph
from core.finding import Finding, FindingFactory, Category


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default density threshold for soft words (0.5% = 5 per 1000 words)
DEFAULT_SOFT_DENSITY_THRESHOLD = 0.005


# =============================================================================
# MATCH RESULT
# =============================================================================

@dataclass
class StopWordMatch:
    """A matched stop word occurrence."""
    word: str               # The matched text
    canonical: str          # The canonical form from the list
    tier: str               # "hard" or "soft"
    start_pos: int          # Position in paragraph text
    end_pos: int            # End position in paragraph text
    para: Paragraph         # The paragraph containing the match


# =============================================================================
# CHECK IMPLEMENTATION
# =============================================================================

@register_check
class StopWordsCheck(DeterministicCheck):
    """
    Detects AI-associated stop words from weighted tiers.

    Hard stop words (weight 1.0):
    - Always generate a Finding
    - Severity: "warning"
    - Confidence: 0.9

    Soft stop words (weight 0.3):
    - Only generate Findings if density exceeds threshold
    - Severity: "suggestion"
    - Confidence: 0.6

    Body paragraphs only - skips headings and tables.
    """

    def __init__(self, soft_density_threshold: float = DEFAULT_SOFT_DENSITY_THRESHOLD):
        """
        Initialize the check.

        Args:
            soft_density_threshold: Density threshold for soft words (default 0.5%)
        """
        self._soft_density_threshold = soft_density_threshold
        self._hard_patterns: list[tuple[re.Pattern, str]] = []
        self._soft_patterns: list[tuple[re.Pattern, str]] = []
        self._patterns_built = False

    def _get_name(self) -> str:
        return "stop_words"

    def _get_display_name(self) -> str:
        return "Stop Words Detection"

    def _get_category(self) -> Category:
        return "stop_words"

    def _get_description(self) -> str:
        return (
            "Detects AI-associated stop words from weighted tiers. "
            "Hard words always flagged; soft words flagged above density threshold."
        )

    def _get_required_standards(self) -> tuple[str, ...]:
        return ("stop_words.hard", "stop_words.soft")

    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """
        Find stop word occurrences in the document.

        Args:
            document: The document to check
            standards: Standards with stop_words.hard and stop_words.soft lists

        Returns:
            List of Findings for stop word occurrences
        """
        # Build patterns from standards (cached after first build)
        self._build_patterns(standards)

        findings: list[Finding] = []
        hard_matches: list[StopWordMatch] = []
        soft_matches: list[StopWordMatch] = []

        # Process body paragraphs only
        for para in document.paragraphs():
            para_hard, para_soft = self._process_paragraph(para)
            hard_matches.extend(para_hard)
            soft_matches.extend(para_soft)

        # Hard matches always become findings
        for match in hard_matches:
            finding = self._create_finding(match, document)
            findings.append(finding)

        # Soft matches only become findings if above density threshold
        total_words = self._count_words(document)
        if total_words > 0 and soft_matches:
            density = len(soft_matches) / total_words
            if density > self._soft_density_threshold:
                for match in soft_matches:
                    finding = self._create_finding(match, document)
                    findings.append(finding)

        return findings

    def _build_patterns(self, standards: Any) -> None:
        """Build compiled regex patterns from standards lists."""
        if self._patterns_built:
            return

        # Build hard patterns
        hard_list = standards.stop_words.hard
        self._hard_patterns = self._compile_patterns(hard_list)

        # Build soft patterns
        soft_list = standards.stop_words.soft
        self._soft_patterns = self._compile_patterns(soft_list)

        self._patterns_built = True

    def _compile_patterns(self, word_list: list[str]) -> list[tuple[re.Pattern, str]]:
        """
        Compile regex patterns for a word list.

        Multi-word phrases use exact matching.
        Single words handle basic inflections (-s, -ing, -ed, -ly).
        Handles 'e' dropping (delve -> delving) and consonant doubling.
        """
        patterns = []
        for word in word_list:
            word_lower = word.lower()

            if ' ' in word or '-' in word:
                # Multi-word phrase or hyphenated - exact match only
                pattern = r'\b' + re.escape(word_lower) + r'\b'
            else:
                # Single word - handle basic inflections
                escaped = re.escape(word_lower)

                # Build pattern that handles common inflection rules
                if word_lower.endswith('e'):
                    # Words ending in 'e': drop e before -ing, -ed (delve -> delving)
                    base = re.escape(word_lower[:-1])
                    pattern = (
                        r'\b(?:' +
                        escaped + r'(?:s|ly)?|' +  # delve, delves, delvely
                        base + r'(?:ing|ed)' +      # delving, delved
                        r')\b'
                    )
                else:
                    # Regular words: just append suffixes
                    pattern = r'\b' + escaped + r'(?:s|ing|ed|ly)?\b'

            compiled = re.compile(pattern, re.IGNORECASE)
            patterns.append((compiled, word))

        return patterns

    def _process_paragraph(
        self,
        para: Paragraph,
    ) -> tuple[list[StopWordMatch], list[StopWordMatch]]:
        """
        Process a single paragraph for stop word matches.

        Returns:
            (hard_matches, soft_matches)
        """
        hard_matches: list[StopWordMatch] = []
        soft_matches: list[StopWordMatch] = []

        text = para.text

        # Find hard matches
        for pattern, canonical in self._hard_patterns:
            for match in pattern.finditer(text):
                hard_matches.append(StopWordMatch(
                    word=match.group(0),
                    canonical=canonical,
                    tier="hard",
                    start_pos=match.start(),
                    end_pos=match.end(),
                    para=para,
                ))

        # Find soft matches
        for pattern, canonical in self._soft_patterns:
            for match in pattern.finditer(text):
                soft_matches.append(StopWordMatch(
                    word=match.group(0),
                    canonical=canonical,
                    tier="soft",
                    start_pos=match.start(),
                    end_pos=match.end(),
                    para=para,
                ))

        return hard_matches, soft_matches

    def _create_finding(
        self,
        match: StopWordMatch,
        document: Document,
    ) -> Finding:
        """Create a Finding for a stop word match."""
        # Calculate absolute offsets
        abs_start = match.para.start_offset + match.start_pos
        abs_end = match.para.start_offset + match.end_pos

        # Get location
        location = document.location_for_span(abs_start, abs_end)

        # Determine severity and confidence based on tier
        if match.tier == "hard":
            severity = "warning"
            confidence = 0.9
            reasoning = (
                f"'{match.word}' is a hard stop word (AI-associated language). "
                f"Consider rephrasing to avoid this term."
            )
        else:  # soft
            severity = "suggestion"
            confidence = 0.6
            reasoning = (
                f"'{match.word}' is a soft stop word that appears frequently. "
                f"Consider varying your word choice."
            )

        return FindingFactory.create(
            check_name=self.name,
            category=self.category,
            severity=severity,
            confidence=confidence,
            location=location,
            original_text=match.word,
            proposed_text=None,  # Detection only - no replacement
            reasoning=reasoning,
            auto_applicable=False,  # No auto-fix
            metadata={
                "tier": match.tier,
                "canonical_word": match.canonical,
                "weight": 1.0 if match.tier == "hard" else 0.3,
            },
        )

    def _count_words(self, document: Document) -> int:
        """Count total words in body paragraphs."""
        total = 0
        for para in document.paragraphs():
            # Simple word count - split on whitespace
            total += len(para.text.split())
        return total


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_stop_word_counts(
    document: Document,
    standards: Any,
) -> dict[str, int]:
    """
    Count stop word occurrences by tier without generating findings.

    Useful for analytics and reporting.

    Returns:
        {"hard": count, "soft": count, "total_words": count}
    """
    check = StopWordsCheck()
    check._build_patterns(standards)

    hard_count = 0
    soft_count = 0
    total_words = 0

    for para in document.paragraphs():
        total_words += len(para.text.split())
        hard_matches, soft_matches = check._process_paragraph(para)
        hard_count += len(hard_matches)
        soft_count += len(soft_matches)

    return {
        "hard": hard_count,
        "soft": soft_count,
        "total_words": total_words,
    }
