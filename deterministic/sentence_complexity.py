"""
Pitboss v4 - Sentence Complexity Outlier Detection

Deterministic check that flags sentences significantly more complex than the
article's baseline. Uses statistical outlier detection (z-score) combined
with absolute thresholds.

Design rationale:
- No LLM calls ($0 cost)
- Relative detection: flags only outliers within article's own style
- Dual-gate: statistical outlier AND absolute complexity
- Proposals only: editor decides whether to split/simplify

Trigger logic:
1. Statistical outlier: >2.0 standard deviations above article mean depth
2. Absolute floor: >=40 words OR >=3 clause markers
Both conditions must be true to trigger.

Depth score = word_count + (clause_count * 8)
This weights clauses heavily because embedded subordination is harder to parse.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.check_base import register_check, DeterministicCheck
from core.document import Location
from core.finding import FindingFactory, Finding

if TYPE_CHECKING:
    from core.document import Document, Paragraph
    from standards.voice import VoiceModel


# =============================================================================
# CLAUSE DETECTION
# =============================================================================

# Subordinating conjunctions and relative pronouns that indicate clauses
CLAUSE_MARKERS = [
    r'\bwhich\b', r'\bthat\b', r'\bwho\b', r'\bwhom\b', r'\bwhose\b',
    r'\bwhere\b', r'\bwhen\b', r'\bwhile\b', r'\bwhereas\b',
    r'\bbecause\b', r'\bsince\b', r'\balthough\b', r'\bthough\b',
    r'\beven though\b', r'\bif\b', r'\bunless\b', r'\buntil\b',
    r'\bbefore\b', r'\bafter\b', r'\bas\b', r'\bso that\b',
]

# Compile patterns for efficiency
CLAUSE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CLAUSE_MARKERS]

# Sentence boundary pattern (handles common cases)
SENTENCE_PATTERN = re.compile(r'[.!?]+\s+|\n')


# =============================================================================
# SENTENCE ANALYSIS
# =============================================================================

@dataclass
class SentenceStats:
    """Statistics for a single sentence."""
    text: str
    word_count: int
    clause_count: int
    depth_score: float
    z_score: float = 0.0
    triggers: bool = False
    element_index: int = 0
    char_offset: int = 0  # Offset within the paragraph


def count_clauses(sentence: str) -> int:
    """Count subordinate clause markers in a sentence."""
    count = 0
    for pattern in CLAUSE_PATTERNS:
        count += len(pattern.findall(sentence))
    return count


def split_sentences(text: str) -> list[tuple[str, int]]:
    """
    Split text into sentences with their character offsets.

    Returns list of (sentence_text, char_offset) tuples.
    """
    if not text:
        return []

    sentences = []
    current_pos = 0

    for match in SENTENCE_PATTERN.finditer(text):
        sentence = text[current_pos:match.start()].strip()
        if sentence and len(sentence.split()) >= 3:  # Skip very short fragments
            sentences.append((sentence, current_pos))
        current_pos = match.end()

    # Handle final sentence (no trailing punctuation match)
    final = text[current_pos:].strip()
    if final and len(final.split()) >= 3:
        sentences.append((final, current_pos))

    return sentences


def analyze_sentence(text: str, element_index: int, char_offset: int) -> SentenceStats:
    """Analyze a single sentence and compute its stats."""
    word_count = len(text.split())
    clause_count = count_clauses(text)
    depth_score = word_count + (clause_count * 8)

    return SentenceStats(
        text=text,
        word_count=word_count,
        clause_count=clause_count,
        depth_score=depth_score,
        element_index=element_index,
        char_offset=char_offset,
    )


# =============================================================================
# TRIGGER DETECTION
# =============================================================================

# Thresholds
Z_SCORE_THRESHOLD = 2.0  # Standard deviations above mean
WORD_THRESHOLD = 40      # Absolute word count floor
CLAUSE_THRESHOLD = 3     # Absolute clause count floor
MIN_SENTENCES = 5        # Minimum sentences for meaningful analysis


def find_outliers(sentences: list[SentenceStats]) -> list[SentenceStats]:
    """
    Find statistical outliers that also exceed absolute thresholds.

    Both conditions must be true:
    1. z-score > 2.0 (statistical outlier within this article)
    2. word_count >= 40 OR clause_count >= 3 (absolute complexity)
    """
    if len(sentences) < MIN_SENTENCES:
        return []

    # Compute article baseline
    depth_scores = [s.depth_score for s in sentences]
    mean_depth = statistics.mean(depth_scores)
    stdev_depth = statistics.stdev(depth_scores) if len(depth_scores) > 1 else 0

    if stdev_depth == 0:
        # All sentences have same depth - no outliers possible
        return []

    outliers = []
    for sent in sentences:
        # Compute z-score
        sent.z_score = (sent.depth_score - mean_depth) / stdev_depth

        # Check dual-gate trigger
        is_statistical_outlier = sent.z_score > Z_SCORE_THRESHOLD
        is_absolutely_complex = (sent.word_count >= WORD_THRESHOLD) or (sent.clause_count >= CLAUSE_THRESHOLD)

        sent.triggers = is_statistical_outlier and is_absolutely_complex

        if sent.triggers:
            outliers.append(sent)

    return outliers


# =============================================================================
# CHECK IMPLEMENTATION
# =============================================================================

@register_check
class SentenceComplexityCheck(DeterministicCheck):
    """
    Detect sentences that are statistical complexity outliers within an article.

    This is a proposal-only check: it flags potential issues for editor review
    but does not auto-apply any changes. The editor decides whether to split
    or simplify flagged sentences.
    """

    def _get_name(self) -> str:
        return "sentence_complexity"

    def _get_display_name(self) -> str:
        return "Sentence Complexity"

    def _get_category(self) -> str:
        return "readability"

    def _get_description(self) -> str:
        return "Flags sentences significantly more complex than the article's baseline"

    def _find_issues(self, document: "Document", standards) -> list[Finding]:
        """
        Find sentences that are statistical complexity outliers.

        Analyzes all sentences, computes article baseline, and flags
        those that exceed both statistical and absolute thresholds.
        """
        from core.document import Paragraph

        # Extract all sentences from prose paragraphs
        sentences: list[SentenceStats] = []

        for idx, element in enumerate(document.elements):
            if isinstance(element, Paragraph) and element.text:
                text = element.text.strip()
                if not text:
                    continue

                # Split paragraph into sentences with offsets
                for sent_text, char_offset in split_sentences(text):
                    stats = analyze_sentence(sent_text, idx, char_offset)
                    sentences.append(stats)

        # Find outliers
        outliers = find_outliers(sentences)

        if not outliers:
            return []

        # Compute article baseline for reasoning
        if sentences:
            word_counts = [s.word_count for s in sentences]
            mean_words = statistics.mean(word_counts)
        else:
            mean_words = 0

        findings = []
        for outlier in outliers:
            # Truncate long sentences for display
            display_text = outlier.text
            if len(display_text) > 150:
                display_text = display_text[:150] + "..."

            # Build concrete reasoning
            reasons = []
            if outlier.word_count >= WORD_THRESHOLD:
                reasons.append(f"{outlier.word_count} words")
            if outlier.clause_count >= CLAUSE_THRESHOLD:
                reasons.append(f"{outlier.clause_count} embedded clauses")

            reason_str = " and ".join(reasons) if reasons else f"{outlier.word_count} words"

            reasoning = (
                f"This sentence has {reason_str}, which is {outlier.z_score:.1f} "
                f"standard deviations above this article's average of {mean_words:.0f} words. "
                f"Consider splitting into shorter sentences for readability."
            )

            # Create location
            location = Location(
                paragraph_index=outlier.element_index,
                start_offset=outlier.char_offset,
                end_offset=outlier.char_offset + len(outlier.text),
            )

            finding = FindingFactory.create(
                check_name=self.metadata.name,
                category="readability",
                severity="info",
                confidence=1.0,  # Deterministic check
                location=location,
                original_text=display_text,
                reasoning=reasoning,
                auto_applicable=False,  # Proposal only
                proposed_text=None,  # No automatic replacement
                metadata={
                    "word_count": outlier.word_count,
                    "clause_count": outlier.clause_count,
                    "z_score": round(outlier.z_score, 2),
                    "article_mean_words": round(mean_words, 1),
                },
            )
            findings.append(finding)

        return findings
