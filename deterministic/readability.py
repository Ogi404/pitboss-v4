"""
Pitboss v4 - Readability Metrics Check

Deterministic check providing document metrics and outlier flags:
- Total words, sentences, average sentence length
- Long sentence flags (>40 words) - PROSE PARAGRAPHS ONLY
- Dense paragraph flags (>150 words)
- Per-section word counts

WORD COUNT DEFINITION:
- INCLUDES: Paragraphs (prose), Headings, List items (instructional content)
- EXCLUDES: Tables (info boxes, brand data), meta lines (if detected)

This matches the "article content" that a writer submits and is compared
against brief word-count targets.

No readability score (Flesch-Kincaid) as a pass/fail gate.
All findings are INFO/advisory - metrics only, not prescriptive.
"""

from __future__ import annotations
import re
from typing import Any, Optional

from core.check_base import DeterministicCheck, register_check
from core.document import Document, Paragraph, Section, Heading, Table, List
from core.finding import Finding, FindingFactory, Category, Location


# =============================================================================
# CONSTANTS
# =============================================================================

# Long sentence threshold (words)
LONG_SENTENCE_THRESHOLD = 40

# Dense paragraph threshold (words)
DENSE_PARAGRAPH_THRESHOLD = 150

# Sentence boundary pattern (split on .!? followed by space and capital)
SENTENCE_PATTERN = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')


# =============================================================================
# UTILITIES
# =============================================================================

def count_words(text: str) -> int:
    """Count words in text."""
    return len(re.findall(r'\b\w+\b', text))


def split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    if not text.strip():
        return []
    parts = SENTENCE_PATTERN.split(text)
    return [p.strip() for p in parts if p.strip()]


def is_prose_paragraph(para: Paragraph) -> bool:
    """
    Check if paragraph is prose content (not a meta line or data).

    Excludes:
    - Empty paragraphs
    - Very short lines that look like labels
    - Lines that look like table placeholders
    """
    text = para.text.strip()
    if not text:
        return False

    # Skip very short "label" paragraphs (< 5 words, no sentence-ending punctuation)
    words = count_words(text)
    if words < 5 and not re.search(r'[.!?]$', text):
        return False

    # Skip placeholder patterns
    if text.startswith('>') and text.endswith('<'):
        return False

    return True


# =============================================================================
# READABILITY CHECK
# =============================================================================

@register_check
class ReadabilityCheck(DeterministicCheck):
    """
    Readability metrics and outlier detection.

    WORD COUNT includes: Paragraphs, Headings, List items
    WORD COUNT excludes: Tables (info boxes)

    LONG SENTENCE detection: PROSE PARAGRAPHS ONLY
    (Tables and lists are excluded - they're not sentences)

    Provides:
    1. Document metrics summary (words, sentences, avg length)
    2. Long sentence flags (>40 words each) - prose only
    3. Dense paragraph flags (>150 words each)
    4. Per-section word counts

    All findings are INFO severity (advisory, not prescriptive).
    No auto-applicable findings - metrics only.
    """

    def _get_name(self) -> str:
        return "readability"

    def _get_display_name(self) -> str:
        return "Readability Metrics"

    def _get_category(self) -> Category:
        return "readability"

    def _get_description(self) -> str:
        return (
            "Calculates document metrics (word count, sentence count, "
            "average sentence length) and flags outliers (long sentences >40 words, "
            "dense paragraphs >150 words). Tables excluded from word count."
        )

    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """Calculate metrics and find outliers."""
        findings: list[Finding] = []

        # Calculate word counts by element type (EXCLUDING tables)
        total_words = 0
        para_words = 0
        heading_words = 0
        list_words = 0

        for el in document.elements:
            if isinstance(el, Paragraph):
                para_words += count_words(el.text)
            elif isinstance(el, Heading):
                heading_words += count_words(el.text)
            elif isinstance(el, List):
                for item in el.items:
                    list_words += count_words(item.text)
            # Tables are explicitly EXCLUDED from word count

        total_words = para_words + heading_words + list_words

        if total_words == 0:
            return []

        # Get prose paragraphs only (for sentence analysis)
        prose_paragraphs = [p for p in document.paragraphs() if is_prose_paragraph(p)]
        prose_text = "\n".join(p.text for p in prose_paragraphs)

        # Calculate sentence metrics from PROSE ONLY
        sentences = split_sentences(prose_text)
        total_sentences = len(sentences)
        avg_sentence_length = round(total_words / total_sentences, 1) if total_sentences > 0 else 0

        # Find long sentences in PROSE PARAGRAPHS ONLY
        long_sentences = []
        for para in prose_paragraphs:
            para_sentences = split_sentences(para.text)
            for sentence in para_sentences:
                word_count = count_words(sentence)
                if word_count > LONG_SENTENCE_THRESHOLD:
                    long_sentences.append({
                        'sentence': sentence,
                        'word_count': word_count,
                        'paragraph': para,
                    })

        # Find dense paragraphs (prose only)
        dense_paragraphs = []
        for para in prose_paragraphs:
            word_count = count_words(para.text)
            if word_count > DENSE_PARAGRAPH_THRESHOLD:
                dense_paragraphs.append({
                    'paragraph': para,
                    'word_count': word_count,
                })

        # Calculate section word counts
        section_stats = self._analyze_sections(document)

        # Emit metrics summary finding (INFO)
        findings.append(self._create_metrics_summary(
            total_words=total_words,
            total_sentences=total_sentences,
            avg_sentence_length=avg_sentence_length,
            long_sentences_count=len(long_sentences),
            dense_paragraphs_count=len(dense_paragraphs),
            section_stats=section_stats,
            word_count_breakdown={
                'paragraphs': para_words,
                'headings': heading_words,
                'lists': list_words,
                'tables_excluded': True,
            },
        ))

        # Emit individual long sentence findings
        for item in long_sentences:
            finding = self._create_long_sentence_finding(item, document)
            if finding:
                findings.append(finding)

        # Emit individual dense paragraph findings
        for item in dense_paragraphs:
            findings.append(self._create_dense_paragraph_finding(item, document))

        return findings

    def _analyze_sections(self, document: Document) -> list[dict]:
        """Calculate word counts for each section (excludes tables)."""
        section_stats = []

        for section in document.all_sections_flat():
            # Get only this section's direct content (not subsections)
            # Excludes tables to match the word count definition
            direct_text_parts = [section.heading.text]
            for element in section.content:
                if isinstance(element, Paragraph):
                    direct_text_parts.append(element.text)
                elif isinstance(element, List):
                    for item in element.items:
                        direct_text_parts.append(item.text)
                # Tables excluded
            direct_text = "\n".join(direct_text_parts)

            stats = {
                'title': section.title,
                'level': section.level.value,
                'word_count': count_words(direct_text),
            }
            section_stats.append(stats)

        return section_stats

    def _create_metrics_summary(
        self,
        total_words: int,
        total_sentences: int,
        avg_sentence_length: float,
        long_sentences_count: int,
        dense_paragraphs_count: int,
        section_stats: list[dict],
        word_count_breakdown: dict,
    ) -> Finding:
        """Create the metrics summary finding."""
        return FindingFactory.create(
            check_name=self.name,
            category=self.category,
            severity="info",
            confidence=1.0,
            location=Location(paragraph_index=0, start_offset=0, end_offset=0),
            original_text="",
            proposed_text=None,
            reasoning=(
                f"Document metrics: {total_words} words (tables excluded), "
                f"{total_sentences} sentences, {avg_sentence_length} avg words/sentence. "
                f"Outliers: {long_sentences_count} long sentences (>{LONG_SENTENCE_THRESHOLD} words), "
                f"{dense_paragraphs_count} dense paragraphs (>{DENSE_PARAGRAPH_THRESHOLD} words)."
            ),
            auto_applicable=False,
            metadata={
                "total_words": total_words,
                "total_sentences": total_sentences,
                "avg_sentence_length": avg_sentence_length,
                "long_sentences_count": long_sentences_count,
                "dense_paragraphs_count": dense_paragraphs_count,
                "section_stats": section_stats,
                "word_count_breakdown": word_count_breakdown,
            },
        )

    def _create_long_sentence_finding(
        self,
        item: dict,
        document: Document,
    ) -> Optional[Finding]:
        """Create a finding for a long sentence."""
        sentence = item['sentence']
        word_count = item['word_count']
        para = item['paragraph']

        try:
            location = document.location_for_span(para.start_offset, para.end_offset)
        except Exception:
            location = Location(
                paragraph_index=0,
                start_offset=para.start_offset,
                end_offset=para.end_offset,
            )

        # Preview: first 50 chars
        preview = sentence[:50] + "..." if len(sentence) > 50 else sentence

        return FindingFactory.create(
            check_name=f"{self.name}.long_sentence",
            category=self.category,
            severity="info",
            confidence=1.0,
            location=location,
            original_text=sentence,
            proposed_text=None,
            reasoning=(
                f"Long sentence ({word_count} words, threshold {LONG_SENTENCE_THRESHOLD}). "
                f"Consider breaking into shorter sentences for readability."
            ),
            auto_applicable=False,
            metadata={
                "word_count": word_count,
                "threshold": LONG_SENTENCE_THRESHOLD,
                "preview": preview,
            },
        )

    def _create_dense_paragraph_finding(
        self,
        item: dict,
        document: Document,
    ) -> Finding:
        """Create a finding for a dense paragraph."""
        para = item['paragraph']
        word_count = item['word_count']

        try:
            location = document.location_for_span(para.start_offset, para.end_offset)
        except Exception:
            location = Location(
                paragraph_index=0,
                start_offset=para.start_offset,
                end_offset=para.end_offset,
            )

        # Preview: first 60 chars
        preview = para.text[:60] + "..." if len(para.text) > 60 else para.text

        return FindingFactory.create(
            check_name=f"{self.name}.dense_paragraph",
            category=self.category,
            severity="info",
            confidence=1.0,
            location=location,
            original_text=para.text,
            proposed_text=None,
            reasoning=(
                f"Dense paragraph ({word_count} words, threshold {DENSE_PARAGRAPH_THRESHOLD}). "
                f"Consider breaking into smaller paragraphs for readability."
            ),
            auto_applicable=False,
            metadata={
                "word_count": word_count,
                "threshold": DENSE_PARAGRAPH_THRESHOLD,
                "preview": preview,
            },
        )
