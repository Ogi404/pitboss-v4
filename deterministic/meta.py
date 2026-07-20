"""
Pitboss v4 - Meta Tag Detection Check

Deterministic check to detect Title Tag and Meta Description presence.
Uses multiple detection strategies to avoid false "missing" reports:

1. Explicit labels: "Title Tag:", "Meta Description:", "SEO Title:", etc.
2. Table format: Meta info often appears in tables
3. Fallback heuristics: First short paragraph + H1 heading

Key rule: Only report "missing" if genuinely not found after thorough search.
"""

from __future__ import annotations
import re
from typing import Any, Optional
from dataclasses import dataclass

from core.check_base import DeterministicCheck, register_check
from core.document import Document, Paragraph, Heading, Table
from core.finding import Finding, FindingFactory, Category, Location


# =============================================================================
# DETECTION PATTERNS
# =============================================================================

# Explicit label patterns for title tag
TITLE_TAG_PATTERNS = [
    re.compile(r'^Title\s*Tag\s*[:\-]?\s*(.+)$', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^META\s*TITLE\s*[:\-]?\s*(.+)$', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^SEO\s*Title\s*[:\-]?\s*(.+)$', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^Title\s*[:\-]\s*(.+)$', re.IGNORECASE | re.MULTILINE),
]

# Explicit label patterns for meta description
META_DESC_PATTERNS = [
    re.compile(r'^Meta\s*Description\s*[:\-]?\s*(.+)$', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^META\s*DESC(?:RIPTION)?\s*[:\-]?\s*(.+)$', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^SEO\s*Description\s*[:\-]?\s*(.+)$', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^Description\s*[:\-]\s*(.+)$', re.IGNORECASE | re.MULTILINE),
]

# Table cell labels (for meta in table format)
TABLE_TITLE_LABELS = {'title tag', 'meta title', 'seo title', 'title'}
TABLE_DESC_LABELS = {'meta description', 'meta desc', 'seo description', 'description'}


# =============================================================================
# DETECTION RESULT
# =============================================================================

@dataclass
class MetaDetectionResult:
    """Result of meta tag detection."""
    title_tag: Optional[str] = None
    title_tag_source: Optional[str] = None  # e.g., "explicit_label", "table", "h1_fallback"
    meta_description: Optional[str] = None
    meta_description_source: Optional[str] = None
    search_log: list[str] = None  # What was searched

    def __post_init__(self):
        if self.search_log is None:
            self.search_log = []


# =============================================================================
# META CHECK
# =============================================================================

@register_check
class MetaCheck(DeterministicCheck):
    """
    Detect Title Tag and Meta Description presence.

    Multi-strategy detection:
    1. Explicit labels in paragraphs
    2. Table cell format
    3. Fallback: H1 as title, first paragraph as description

    Only reports "missing" after thorough search.
    """

    def _get_name(self) -> str:
        return "meta"

    def _get_display_name(self) -> str:
        return "Meta Tags"

    def _get_category(self) -> Category:
        return "meta"

    def _get_description(self) -> str:
        return (
            "Detects presence of Title Tag and Meta Description in the document. "
            "Uses multiple detection strategies (explicit labels, tables, fallbacks) "
            "to avoid false 'missing' reports."
        )

    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """Detect meta tags and report findings."""
        findings: list[Finding] = []

        # Run detection
        result = self._detect_meta_tags(document)

        # Report what was found
        if result.title_tag or result.meta_description:
            findings.append(self._create_found_finding(result))

        # Report what's missing (only if genuinely not found)
        missing = []
        if not result.title_tag:
            missing.append("Title Tag")
        if not result.meta_description:
            missing.append("Meta Description")

        if missing:
            findings.append(self._create_missing_finding(missing, result))

        return findings

    def _detect_meta_tags(self, document: Document) -> MetaDetectionResult:
        """Run all detection strategies."""
        result = MetaDetectionResult()

        # Strategy 1: Check first N paragraphs for explicit labels
        result.search_log.append("Checking first 10 paragraphs for explicit labels...")
        self._check_paragraphs(document, result)

        # Strategy 2: Check tables
        if not result.title_tag or not result.meta_description:
            result.search_log.append("Checking tables for meta info...")
            self._check_tables(document, result)

        # Strategy 3: Fallback heuristics
        if not result.title_tag:
            result.search_log.append("Checking H1 heading as title fallback...")
            self._try_h1_fallback(document, result)

        if not result.meta_description:
            result.search_log.append("Checking first paragraph as description fallback...")
            self._try_first_paragraph_fallback(document, result)

        return result

    def _check_paragraphs(self, document: Document, result: MetaDetectionResult) -> None:
        """Check paragraphs for explicit meta labels."""
        paragraphs = list(document.paragraphs())[:10]  # First 10 paragraphs

        for para in paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Check for title tag patterns
            if not result.title_tag:
                for pattern in TITLE_TAG_PATTERNS:
                    match = pattern.match(text)
                    if match:
                        result.title_tag = match.group(1).strip()
                        result.title_tag_source = "explicit_label"
                        result.search_log.append(f"Found title tag via explicit label: {text[:50]}...")
                        break

            # Check for meta description patterns
            if not result.meta_description:
                for pattern in META_DESC_PATTERNS:
                    match = pattern.match(text)
                    if match:
                        result.meta_description = match.group(1).strip()
                        result.meta_description_source = "explicit_label"
                        result.search_log.append(f"Found meta description via explicit label: {text[:50]}...")
                        break

    def _check_tables(self, document: Document, result: MetaDetectionResult) -> None:
        """Check tables for meta info in label/value format."""
        for element in document.elements:
            if not isinstance(element, Table):
                continue

            for row in element.rows:
                if len(row.cells) < 2:
                    continue

                # Check if first cell is a meta label
                label = row.cells[0].text.strip().lower()
                value = row.cells[1].text.strip()

                if not value:
                    continue

                # Title tag check
                if not result.title_tag and label in TABLE_TITLE_LABELS:
                    result.title_tag = value
                    result.title_tag_source = "table"
                    result.search_log.append(f"Found title tag in table: {label} = {value[:50]}...")

                # Meta description check
                if not result.meta_description and label in TABLE_DESC_LABELS:
                    result.meta_description = value
                    result.meta_description_source = "table"
                    result.search_log.append(f"Found meta description in table: {label} = {value[:50]}...")

    def _try_h1_fallback(self, document: Document, result: MetaDetectionResult) -> None:
        """Use H1 heading as title fallback."""
        headings = document.headings()
        for heading in headings:
            if heading.level.value == 1:
                result.title_tag = heading.text.strip()
                result.title_tag_source = "h1_fallback"
                result.search_log.append(f"Using H1 as title fallback: {heading.text[:50]}...")
                break

    def _try_first_paragraph_fallback(self, document: Document, result: MetaDetectionResult) -> None:
        """Use first substantial paragraph as description fallback."""
        paragraphs = list(document.paragraphs())

        # Find first non-empty paragraph before H1 (if any)
        h1_offset = None
        for heading in document.headings():
            if heading.level.value == 1:
                h1_offset = heading.start_offset
                break

        for para in paragraphs[:5]:  # Check first 5 paragraphs
            text = para.text.strip()
            if not text:
                continue

            # Skip if this is after the H1
            if h1_offset is not None and para.start_offset > h1_offset:
                continue

            # Skip if too short (likely a label or rating)
            word_count = len(text.split())
            if word_count < 10:
                continue

            # Skip if looks like an explicit label
            if any(pattern.match(text) for pattern in TITLE_TAG_PATTERNS + META_DESC_PATTERNS):
                continue

            # Use this paragraph
            result.meta_description = text
            result.meta_description_source = "first_paragraph_fallback"
            result.search_log.append(f"Using first paragraph as description fallback: {text[:50]}...")
            break

    def _create_found_finding(self, result: MetaDetectionResult) -> Finding:
        """Create finding for detected meta tags."""
        parts = []

        # Title tag with clear source indication
        if result.title_tag:
            title_preview = result.title_tag[:60] + "..." if len(result.title_tag) > 60 else result.title_tag
            if result.title_tag_source == "explicit_label":
                parts.append(f"Title Tag: \"{title_preview}\"")
            elif result.title_tag_source == "table":
                parts.append(f"Title Tag (from table): \"{title_preview}\"")
            elif result.title_tag_source == "h1_fallback":
                parts.append(f"Title Tag: NO EXPLICIT LABEL FOUND; using H1: \"{title_preview}\"")

        # Meta description with clear source indication
        if result.meta_description:
            desc_preview = result.meta_description[:60] + "..." if len(result.meta_description) > 60 else result.meta_description
            if result.meta_description_source == "explicit_label":
                parts.append(f"Meta Description: \"{desc_preview}\"")
            elif result.meta_description_source == "table":
                parts.append(f"Meta Description (from table): \"{desc_preview}\"")
            elif result.meta_description_source == "first_paragraph_fallback":
                parts.append(f"Meta Description: NO EXPLICIT LABEL FOUND; using first paragraph: \"{desc_preview}\"")

        return FindingFactory.create(
            check_name=self.name,
            category=self.category,
            severity="info",
            confidence=1.0,
            location=Location(paragraph_index=0, start_offset=0, end_offset=0),
            original_text="",
            proposed_text=None,
            reasoning=" | ".join(parts),
            auto_applicable=False,
            metadata={
                "title_tag": result.title_tag,
                "title_tag_source": result.title_tag_source,
                "meta_description": result.meta_description,
                "meta_description_source": result.meta_description_source,
                "search_log": result.search_log,
            },
        )

    def _create_missing_finding(
        self,
        missing: list[str],
        result: MetaDetectionResult,
    ) -> Finding:
        """Create finding for missing meta tags."""
        return FindingFactory.create(
            check_name=f"{self.name}.missing",
            category=self.category,
            severity="warning",
            confidence=0.9,
            location=Location(paragraph_index=0, start_offset=0, end_offset=0),
            original_text="",
            proposed_text=None,
            reasoning=(
                f"Missing meta tags: {', '.join(missing)}. "
                f"Searched: explicit labels in paragraphs, tables, and fallback heuristics."
            ),
            auto_applicable=False,
            metadata={
                "missing": missing,
                "search_log": result.search_log,
            },
        )
