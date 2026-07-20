"""
Tests for deterministic/readability.py - Readability Metrics Check.
"""

import pytest
from unittest.mock import Mock

from deterministic.readability import (
    ReadabilityCheck,
    count_words,
    split_sentences,
    LONG_SENTENCE_THRESHOLD,
    DENSE_PARAGRAPH_THRESHOLD,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def readability_check():
    """Fresh ReadabilityCheck instance."""
    return ReadabilityCheck()


@pytest.fixture
def mock_standards():
    """Mock standards object."""
    return Mock()


def make_mock_document(text: str, paragraphs: list[str] = None):
    """Create a mock document with full_text, paragraphs, and elements."""
    from core.document import Paragraph, Heading

    doc = Mock()
    doc.full_text = Mock(return_value=text)

    if paragraphs is None:
        paragraphs = [text]

    # Build mock paragraph objects
    mock_paras = []
    elements = []
    offset = 0
    for para_text in paragraphs:
        para = Mock(spec=Paragraph)
        para.text = para_text
        para.start_offset = offset
        para.end_offset = offset + len(para_text)
        mock_paras.append(para)
        elements.append(para)
        offset += len(para_text) + 1

    doc.paragraphs = Mock(return_value=mock_paras)
    doc.elements = elements

    # Mock sections
    doc.all_sections_flat = Mock(return_value=[])

    # Mock location_for_span
    doc.location_for_span = Mock(return_value=Mock(
        section_index=0,
        section_title=None,
        paragraph_index=0,
        element_type="paragraph",
        start_offset=0,
        end_offset=len(text),
    ))

    return doc


# =============================================================================
# UTILITY TESTS
# =============================================================================

class TestCountWords:
    """Test word counting utility."""

    def test_simple_sentence(self):
        assert count_words("Hello world") == 2

    def test_empty_string(self):
        assert count_words("") == 0

    def test_punctuation(self):
        assert count_words("Hello, world!") == 2

    def test_numbers(self):
        assert count_words("I have 100 apples") == 4

    def test_contractions(self):
        # "don't" counts as 2 words with \b\w+\b pattern
        assert count_words("I don't know") == 4


class TestSplitSentences:
    """Test sentence splitting utility."""

    def test_two_sentences(self):
        sentences = split_sentences("Hello world. This is a test.")
        assert len(sentences) == 2
        assert "Hello world." in sentences[0]
        assert "This is a test." in sentences[1]

    def test_question_mark(self):
        sentences = split_sentences("What is this? It is a test.")
        assert len(sentences) == 2

    def test_exclamation(self):
        sentences = split_sentences("Wow! That is great.")
        assert len(sentences) == 2

    def test_no_split_without_capital(self):
        # Should not split on period followed by lowercase
        sentences = split_sentences("This is version 1.0 of the software.")
        assert len(sentences) == 1

    def test_empty_string(self):
        assert split_sentences("") == []


# =============================================================================
# METADATA TESTS
# =============================================================================

class TestReadabilityCheckMetadata:
    """Test check metadata is correctly defined."""

    def test_check_name(self, readability_check):
        assert readability_check.name == "readability"

    def test_display_name(self, readability_check):
        assert readability_check.metadata.display_name == "Readability Metrics"

    def test_category(self, readability_check):
        assert readability_check.category == "readability"


# =============================================================================
# METRICS CALCULATION TESTS
# =============================================================================

class TestMetricsCalculation:
    """Test metrics summary calculation."""

    def test_metrics_summary_finding(self, readability_check, mock_standards):
        """Should produce a metrics summary finding."""
        text = "This is a test. Here is another sentence. And a third one."
        doc = make_mock_document(text)

        findings = readability_check.run(doc, mock_standards)

        # Should have at least the metrics summary
        assert len(findings) >= 1
        summary = findings[0]
        assert summary.check_name == "readability"
        assert summary.severity == "info"

        # Check metadata
        metadata = dict(summary.metadata)
        assert "total_words" in metadata
        assert "total_sentences" in metadata
        assert "avg_sentence_length" in metadata
        assert metadata["total_sentences"] == 3

    def test_word_count_calculation(self, readability_check, mock_standards):
        """Should calculate correct word count."""
        text = "One two three four five. Six seven eight nine ten."
        doc = make_mock_document(text)

        findings = readability_check.run(doc, mock_standards)

        metadata = dict(findings[0].metadata)
        assert metadata["total_words"] == 10


# =============================================================================
# LONG SENTENCE TESTS
# =============================================================================

class TestLongSentenceDetection:
    """Test long sentence flagging."""

    def test_flags_long_sentence(self, readability_check, mock_standards):
        """Should flag sentences over threshold."""
        # Create a sentence with more than 40 words
        long_sentence = " ".join(["word"] * 45) + "."
        text = f"Short sentence. {long_sentence} Another short one."
        doc = make_mock_document(text)

        findings = readability_check.run(doc, mock_standards)

        long_findings = [f for f in findings if "long_sentence" in f.check_name]
        assert len(long_findings) >= 1

        # Check metadata
        metadata = dict(long_findings[0].metadata)
        assert metadata["word_count"] >= 45  # May include trailing words
        assert metadata["threshold"] == LONG_SENTENCE_THRESHOLD

    def test_does_not_flag_short_sentences(self, readability_check, mock_standards):
        """Should not flag sentences under threshold."""
        text = "This is short. Another short sentence. A third one here."
        doc = make_mock_document(text)

        findings = readability_check.run(doc, mock_standards)

        long_findings = [f for f in findings if "long_sentence" in f.check_name]
        assert len(long_findings) == 0

    def test_long_sentence_is_advisory(self, readability_check, mock_standards):
        """Long sentence findings should be info severity and not auto-applicable."""
        long_sentence = " ".join(["word"] * 45) + "."
        doc = make_mock_document(long_sentence)

        findings = readability_check.run(doc, mock_standards)

        long_findings = [f for f in findings if "long_sentence" in f.check_name]
        assert len(long_findings) >= 1
        assert long_findings[0].severity == "info"
        assert long_findings[0].auto_applicable is False


# =============================================================================
# DENSE PARAGRAPH TESTS
# =============================================================================

class TestDenseParagraphDetection:
    """Test dense paragraph flagging."""

    def test_flags_dense_paragraph(self, readability_check, mock_standards):
        """Should flag paragraphs over threshold."""
        # Create a paragraph with more than 150 words
        dense_para = " ".join(["word"] * 160)
        doc = make_mock_document(dense_para, [dense_para])

        findings = readability_check.run(doc, mock_standards)

        dense_findings = [f for f in findings if "dense_paragraph" in f.check_name]
        assert len(dense_findings) >= 1

        metadata = dict(dense_findings[0].metadata)
        assert metadata["word_count"] == 160
        assert metadata["threshold"] == DENSE_PARAGRAPH_THRESHOLD

    def test_does_not_flag_normal_paragraphs(self, readability_check, mock_standards):
        """Should not flag paragraphs under threshold."""
        normal_para = " ".join(["word"] * 50)
        doc = make_mock_document(normal_para, [normal_para])

        findings = readability_check.run(doc, mock_standards)

        dense_findings = [f for f in findings if "dense_paragraph" in f.check_name]
        assert len(dense_findings) == 0

    def test_dense_paragraph_is_advisory(self, readability_check, mock_standards):
        """Dense paragraph findings should be info severity and not auto-applicable."""
        dense_para = " ".join(["word"] * 160)
        doc = make_mock_document(dense_para, [dense_para])

        findings = readability_check.run(doc, mock_standards)

        dense_findings = [f for f in findings if "dense_paragraph" in f.check_name]
        assert len(dense_findings) >= 1
        assert dense_findings[0].severity == "info"
        assert dense_findings[0].auto_applicable is False


# =============================================================================
# SECTION STATS TESTS
# =============================================================================

class TestSectionStats:
    """Test per-section word count calculation."""

    def test_section_stats_in_metadata(self, readability_check, mock_standards):
        """Section stats should be in metrics summary metadata."""
        text = "This is a test document."
        doc = make_mock_document(text)

        findings = readability_check.run(doc, mock_standards)

        metadata = dict(findings[0].metadata)
        assert "section_stats" in metadata
        assert isinstance(metadata["section_stats"], list)


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases."""

    def test_empty_document(self, readability_check, mock_standards):
        """Should handle empty document gracefully."""
        doc = make_mock_document("")
        findings = readability_check.run(doc, mock_standards)
        assert len(findings) == 0

    def test_whitespace_only(self, readability_check, mock_standards):
        """Should handle whitespace-only document."""
        doc = make_mock_document("   \n\t  ")
        findings = readability_check.run(doc, mock_standards)
        assert len(findings) == 0
