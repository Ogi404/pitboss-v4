"""
Tests for deterministic/meta.py - Meta Tag Detection Check.
"""

import pytest
from unittest.mock import Mock

from deterministic.meta import (
    MetaCheck,
    MetaDetectionResult,
    TITLE_TAG_PATTERNS,
    META_DESC_PATTERNS,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def meta_check():
    """Fresh MetaCheck instance."""
    return MetaCheck()


@pytest.fixture
def mock_standards():
    """Mock standards object."""
    return Mock()


def make_mock_document(
    paragraphs: list[str] = None,
    headings: list[tuple[int, str]] = None,
    tables: list[list[tuple[str, str]]] = None,
):
    """
    Create a mock document.

    Args:
        paragraphs: List of paragraph texts
        headings: List of (level, text) tuples
        tables: List of tables, each table is list of (label, value) tuples
    """
    doc = Mock()

    # Build elements list
    elements = []
    offset = 0

    # Add paragraphs
    mock_paras = []
    for para_text in (paragraphs or []):
        para = Mock()
        para.text = para_text
        para.start_offset = offset
        para.end_offset = offset + len(para_text)
        mock_paras.append(para)
        elements.append(para)
        offset += len(para_text) + 1

    doc.paragraphs = Mock(return_value=mock_paras)

    # Add headings
    mock_headings = []
    for level, text in (headings or []):
        heading = Mock()
        heading.text = text
        heading.level = Mock()
        heading.level.value = level
        heading.start_offset = offset
        heading.end_offset = offset + len(text)
        mock_headings.append(heading)
        elements.append(heading)
        offset += len(text) + 1

    doc.headings = Mock(return_value=mock_headings)

    # Add tables
    if tables:
        from core.document import Table
        for table_data in tables:
            table = Mock(spec=Table)
            rows = []
            for label, value in table_data:
                row = Mock()
                cell1 = Mock()
                cell1.text = label
                cell2 = Mock()
                cell2.text = value
                row.cells = [cell1, cell2]
                rows.append(row)
            table.rows = rows
            elements.append(table)

    doc.elements = elements

    # Full text
    texts = [p.text for p in mock_paras]
    texts.extend([h.text for h in mock_headings])
    doc.full_text = Mock(return_value="\n".join(texts))

    return doc


# =============================================================================
# METADATA TESTS
# =============================================================================

class TestMetaCheckMetadata:
    """Test check metadata is correctly defined."""

    def test_check_name(self, meta_check):
        assert meta_check.name == "meta"

    def test_display_name(self, meta_check):
        assert meta_check.metadata.display_name == "Meta Tags"

    def test_category(self, meta_check):
        assert meta_check.category == "meta"


# =============================================================================
# EXPLICIT LABEL DETECTION TESTS
# =============================================================================

class TestExplicitLabelDetection:
    """Test explicit meta label detection."""

    def test_detects_title_tag_label(self, meta_check, mock_standards):
        """Should detect 'Title Tag: ...' format."""
        doc = make_mock_document(
            paragraphs=["Title Tag: Best Casino Review 2024"],
            headings=[(1, "Main Heading")],
        )

        findings = meta_check.run(doc, mock_standards)

        # Should find title tag
        found_findings = [f for f in findings if f.check_name == "meta"]
        assert len(found_findings) >= 1

        metadata = dict(found_findings[0].metadata)
        assert metadata.get("title_tag") == "Best Casino Review 2024"
        assert metadata.get("title_tag_source") == "explicit_label"

    def test_detects_meta_description_label(self, meta_check, mock_standards):
        """Should detect 'Meta Description: ...' format."""
        doc = make_mock_document(
            paragraphs=["Meta Description: This is a great casino review."],
            headings=[(1, "Main Heading")],
        )

        findings = meta_check.run(doc, mock_standards)

        found_findings = [f for f in findings if f.check_name == "meta"]
        assert len(found_findings) >= 1

        metadata = dict(found_findings[0].metadata)
        assert "great casino review" in metadata.get("meta_description", "")
        assert metadata.get("meta_description_source") == "explicit_label"

    def test_detects_seo_title_label(self, meta_check, mock_standards):
        """Should detect 'SEO Title: ...' format."""
        doc = make_mock_document(
            paragraphs=["SEO Title: Amazing Casino Guide"],
            headings=[(1, "Main Heading")],
        )

        findings = meta_check.run(doc, mock_standards)

        found_findings = [f for f in findings if f.check_name == "meta"]
        metadata = dict(found_findings[0].metadata)
        assert metadata.get("title_tag") == "Amazing Casino Guide"

    def test_case_insensitive(self, meta_check, mock_standards):
        """Should match labels case-insensitively."""
        doc = make_mock_document(
            paragraphs=["TITLE TAG: All Caps Title", "meta description: lowercase desc"],
            headings=[(1, "Main Heading")],
        )

        findings = meta_check.run(doc, mock_standards)

        found_findings = [f for f in findings if f.check_name == "meta"]
        metadata = dict(found_findings[0].metadata)
        assert metadata.get("title_tag") is not None
        assert metadata.get("meta_description") is not None


# =============================================================================
# TABLE DETECTION TESTS
# =============================================================================

class TestTableDetection:
    """Test meta detection in tables."""

    def test_detects_meta_in_table(self, meta_check, mock_standards):
        """Should detect meta tags in table format."""
        doc = make_mock_document(
            paragraphs=["Some intro text."],
            headings=[(1, "Main Heading")],
            tables=[[
                ("Title Tag", "Table Title Value"),
                ("Meta Description", "Table description value."),
            ]],
        )

        findings = meta_check.run(doc, mock_standards)

        found_findings = [f for f in findings if f.check_name == "meta"]
        metadata = dict(found_findings[0].metadata)
        assert metadata.get("title_tag") == "Table Title Value"
        assert metadata.get("title_tag_source") == "table"
        assert "Table description value" in metadata.get("meta_description", "")
        assert metadata.get("meta_description_source") == "table"


# =============================================================================
# FALLBACK DETECTION TESTS
# =============================================================================

class TestFallbackDetection:
    """Test fallback heuristics."""

    def test_h1_fallback_for_title(self, meta_check, mock_standards):
        """Should use H1 as title fallback when no explicit label."""
        doc = make_mock_document(
            paragraphs=["Some intro paragraph here with enough words to be substantial."],
            headings=[(1, "H1 Fallback Title")],
        )

        findings = meta_check.run(doc, mock_standards)

        found_findings = [f for f in findings if f.check_name == "meta"]
        metadata = dict(found_findings[0].metadata)
        assert metadata.get("title_tag") == "H1 Fallback Title"
        assert metadata.get("title_tag_source") == "h1_fallback"

    def test_first_paragraph_fallback_for_description(self, meta_check, mock_standards):
        """Should use first substantial paragraph as description fallback."""
        intro = "This is a substantial introductory paragraph with enough words to qualify as a meta description fallback."
        doc = make_mock_document(
            paragraphs=[intro],
            headings=[(1, "Main Heading")],
        )

        findings = meta_check.run(doc, mock_standards)

        found_findings = [f for f in findings if f.check_name == "meta"]
        metadata = dict(found_findings[0].metadata)
        assert "introductory paragraph" in metadata.get("meta_description", "")
        assert metadata.get("meta_description_source") == "first_paragraph_fallback"


# =============================================================================
# MISSING META TESTS
# =============================================================================

class TestMissingMeta:
    """Test missing meta tag detection."""

    def test_reports_missing_when_not_found(self, meta_check, mock_standards):
        """Should report missing when meta tags genuinely not found."""
        doc = make_mock_document(
            paragraphs=["Short."],  # Too short for fallback
            headings=[],  # No H1 for title fallback
        )

        findings = meta_check.run(doc, mock_standards)

        missing_findings = [f for f in findings if "missing" in f.check_name]
        assert len(missing_findings) >= 1
        assert missing_findings[0].severity == "warning"

    def test_missing_metadata_contains_search_log(self, meta_check, mock_standards):
        """Missing finding should contain search log."""
        doc = make_mock_document(
            paragraphs=["Short."],
            headings=[],
        )

        findings = meta_check.run(doc, mock_standards)

        missing_findings = [f for f in findings if "missing" in f.check_name]
        metadata = dict(missing_findings[0].metadata)
        assert "search_log" in metadata
        assert len(metadata["search_log"]) > 0


# =============================================================================
# PATTERN TESTS
# =============================================================================

class TestPatterns:
    """Test regex pattern correctness."""

    def test_title_tag_patterns_match(self):
        """Title tag patterns should match expected formats."""
        test_cases = [
            "Title Tag: My Title",
            "Title Tag - My Title",
            "META TITLE: My Title",
            "SEO Title: My Title",
        ]

        for test in test_cases:
            matched = False
            for pattern in TITLE_TAG_PATTERNS:
                if pattern.match(test):
                    matched = True
                    break
            assert matched, f"Pattern should match: {test}"

    def test_meta_desc_patterns_match(self):
        """Meta description patterns should match expected formats."""
        test_cases = [
            "Meta Description: My description here.",
            "Meta Description - My description here.",
            "META DESC: My description here.",
            "SEO Description: My description here.",
        ]

        for test in test_cases:
            matched = False
            for pattern in META_DESC_PATTERNS:
                if pattern.match(test):
                    matched = True
                    break
            assert matched, f"Pattern should match: {test}"


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases."""

    def test_empty_document(self, meta_check, mock_standards):
        """Should handle empty document gracefully."""
        doc = make_mock_document(paragraphs=[], headings=[])
        findings = meta_check.run(doc, mock_standards)
        # Should still produce findings (missing)
        assert len(findings) >= 1

    def test_explicit_label_takes_priority_over_fallback(self, meta_check, mock_standards):
        """Explicit label should be preferred over H1 fallback."""
        doc = make_mock_document(
            paragraphs=["Title Tag: Explicit Title"],
            headings=[(1, "H1 Fallback Title")],
        )

        findings = meta_check.run(doc, mock_standards)

        found_findings = [f for f in findings if f.check_name == "meta"]
        metadata = dict(found_findings[0].metadata)
        assert metadata.get("title_tag") == "Explicit Title"
        assert metadata.get("title_tag_source") == "explicit_label"


# =============================================================================
# LABEL DETECTION VALIDATION
# =============================================================================

class TestLabelDetectionWorks:
    """Validate that label detection extracts from explicit labels, not fallbacks."""

    def test_both_labels_detected_from_explicit_text(self, meta_check, mock_standards):
        """When both Title Tag and Meta Description labels exist, extract from labels."""
        doc = make_mock_document(
            paragraphs=[
                "Title Tag: Best Online Casino Guide 2024",
                "Meta Description: Discover the top online casinos with our expert review.",
                "This is the body content that comes after the meta tags.",
            ],
            headings=[(1, "Main Article Heading")],
        )

        findings = meta_check.run(doc, mock_standards)

        # Should find meta tags
        found_findings = [f for f in findings if f.check_name == "meta"]
        assert len(found_findings) == 1

        metadata = dict(found_findings[0].metadata)

        # Title should come from explicit label, NOT H1 fallback
        assert metadata.get("title_tag") == "Best Online Casino Guide 2024"
        assert metadata.get("title_tag_source") == "explicit_label"

        # Description should come from explicit label, NOT first paragraph fallback
        assert "top online casinos" in metadata.get("meta_description", "")
        assert metadata.get("meta_description_source") == "explicit_label"

    def test_reasoning_indicates_explicit_label(self, meta_check, mock_standards):
        """Reasoning should NOT say 'NO EXPLICIT LABEL FOUND' when labels exist."""
        doc = make_mock_document(
            paragraphs=[
                "Title Tag: My Explicit Title",
                "Meta Description: My explicit description here.",
            ],
            headings=[(1, "H1 Heading")],
        )

        findings = meta_check.run(doc, mock_standards)
        found = [f for f in findings if f.check_name == "meta"][0]

        # Should NOT mention fallback in reasoning
        assert "NO EXPLICIT LABEL FOUND" not in found.reasoning
        assert "My Explicit Title" in found.reasoning
        assert "My explicit description" in found.reasoning

    def test_reasoning_indicates_fallback_when_no_labels(self, meta_check, mock_standards):
        """Reasoning should clearly indicate when fallback is used."""
        doc = make_mock_document(
            paragraphs=[
                "This is a substantial first paragraph with enough words to qualify as a fallback meta description for the article.",
            ],
            headings=[(1, "My H1 Title Used As Fallback")],
        )

        findings = meta_check.run(doc, mock_standards)
        found = [f for f in findings if f.check_name == "meta"][0]

        # Should indicate H1 fallback
        assert "NO EXPLICIT LABEL FOUND" in found.reasoning
        assert "using H1" in found.reasoning

        metadata = dict(found.metadata)
        assert metadata.get("title_tag_source") == "h1_fallback"
