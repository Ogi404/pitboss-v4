"""
Tests for deterministic/grammar.py - Grammar & Spelling Check via LanguageTool.

Note: These tests require Java to be installed and language-tool-python.
Tests are skipped if LanguageTool is not available.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from deterministic.grammar import (
    GrammarCheck,
    LOCALE_MAP,
    INCLUDE_CATEGORIES,
    EXCLUDE_CATEGORIES,
    INCLUDE_RULE_IDS,
    EXCLUDE_RULE_IDS,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def grammar_check():
    """Fresh GrammarCheck instance."""
    return GrammarCheck()


@pytest.fixture
def mock_standards():
    """Mock standards with spelling region."""
    standards = Mock()
    standards.spelling_region = "australian"
    standards.brand_name = "TestBrand"
    return standards


@pytest.fixture
def mock_document():
    """Mock document with full_text method."""
    doc = Mock()
    doc.full_text = Mock(return_value="This is a test document.")
    doc.location_for_span = Mock(return_value=Mock(
        section_index=0,
        section_title="Test Section",
        paragraph_index=0,
        element_type="paragraph",
        start_offset=0,
        end_offset=10,
    ))
    return doc


# =============================================================================
# METADATA TESTS
# =============================================================================

class TestGrammarCheckMetadata:
    """Test check metadata is correctly defined."""

    def test_check_name(self, grammar_check):
        assert grammar_check.name == "grammar"

    def test_display_name(self, grammar_check):
        assert grammar_check.metadata.display_name == "Grammar & Spelling"

    def test_category(self, grammar_check):
        assert grammar_check.category == "grammar"

    def test_required_standards(self, grammar_check):
        assert "spelling_region" in grammar_check.metadata.required_standards


# =============================================================================
# LOCALE MAPPING TESTS
# =============================================================================

class TestLocaleMapping:
    """Test locale mapping is correct."""

    def test_australian_maps_to_en_au(self):
        assert LOCALE_MAP["australian"] == "en-AU"

    def test_british_maps_to_en_gb(self):
        assert LOCALE_MAP["british"] == "en-GB"

    def test_american_maps_to_en_us(self):
        assert LOCALE_MAP["american"] == "en-US"

    def test_canadian_maps_to_en_ca(self):
        assert LOCALE_MAP["canadian"] == "en-CA"

    def test_new_zealand_maps_to_en_nz(self):
        assert LOCALE_MAP["new_zealand"] == "en-NZ"


# =============================================================================
# CATEGORY FILTER TESTS
# =============================================================================

class TestCategoryFilters:
    """Test category filters are correctly configured."""

    def test_typos_included(self):
        assert "TYPOS" in INCLUDE_CATEGORIES

    def test_grammar_included(self):
        assert "GRAMMAR" in INCLUDE_CATEGORIES

    def test_punctuation_included(self):
        assert "PUNCTUATION" in INCLUDE_CATEGORIES

    def test_style_excluded(self):
        assert "STYLE" in EXCLUDE_CATEGORIES

    def test_redundancy_excluded(self):
        assert "REDUNDANCY" in EXCLUDE_CATEGORIES

    def test_sentence_whitespace_explicitly_included(self):
        assert "SENTENCE_WHITESPACE" in INCLUDE_RULE_IDS

    def test_consecutive_spaces_explicitly_included(self):
        assert "CONSECUTIVE_SPACES" in INCLUDE_RULE_IDS


# =============================================================================
# AUTO-APPLICABLE TESTS (mocked)
# =============================================================================

class TestAutoApplicable:
    """Test auto-applicable logic."""

    def test_typos_single_replacement_auto(self, grammar_check):
        match = Mock()
        match.category = "TYPOS"
        match.rule_id = "MORFOLOGIK_RULE_EN_AU"
        replacements = ["licensed"]
        assert grammar_check._is_auto_applicable(match, replacements) is True

    def test_typos_multiple_replacements_not_auto(self, grammar_check):
        match = Mock()
        match.category = "TYPOS"
        match.rule_id = "MORFOLOGIK_RULE_EN_AU"
        replacements = ["set", "test"]
        assert grammar_check._is_auto_applicable(match, replacements) is False

    def test_grammar_not_auto(self, grammar_check):
        match = Mock()
        match.category = "GRAMMAR"
        match.rule_id = "SOME_GRAMMAR_RULE"
        replacements = ["doesn't"]
        assert grammar_check._is_auto_applicable(match, replacements) is False

    def test_punctuation_single_auto(self, grammar_check):
        match = Mock()
        match.category = "PUNCTUATION"
        match.rule_id = "SOME_PUNCT_RULE"
        replacements = [". "]
        assert grammar_check._is_auto_applicable(match, replacements) is True

    def test_included_rule_auto(self, grammar_check):
        match = Mock()
        match.category = "TYPOGRAPHY"
        match.rule_id = "SENTENCE_WHITESPACE"
        replacements = [" The"]
        assert grammar_check._is_auto_applicable(match, replacements) is True


# =============================================================================
# BRAND NAME FILTER TESTS (mocked)
# =============================================================================

class TestBrandNameFilter:
    """Test brand name filtering."""

    def test_brand_name_filtered(self, grammar_check, mock_document):
        """Brand name should not be flagged as spelling error."""
        match = Mock()
        match.rule_id = "MORFOLOGIK_RULE_EN_AU"
        match.category = "TYPOS"
        match.offset = 0
        match.error_length = 9
        match.message = "Possible spelling mistake"
        match.replacements = ["Hell Spin"]

        full_text = "HellBrand is a great casino."

        # Should be filtered when brand_name matches
        result = grammar_check._match_to_finding(
            match, mock_document, full_text, brand_name="HellBrand"
        )
        assert result is None

    def test_non_brand_not_filtered(self, grammar_check, mock_document):
        """Non-brand words should still be flagged."""
        match = Mock()
        match.rule_id = "MORFOLOGIK_RULE_EN_AU"
        match.category = "TYPOS"
        match.offset = 0
        match.error_length = 8
        match.message = "Possible spelling mistake"
        match.replacements = ["licensed"]

        full_text = "lisensed is misspelled."

        result = grammar_check._match_to_finding(
            match, mock_document, full_text, brand_name="TestBrand"
        )
        assert result is not None
        assert result.original_text == "lisensed"


# =============================================================================
# INTEGRATION TESTS (require LanguageTool)
# =============================================================================

def lt_available():
    """Check if LanguageTool is available."""
    try:
        import language_tool_python
        # Try to initialize - will fail if no Java
        tool = language_tool_python.LanguageTool('en-AU')
        tool.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not lt_available(), reason="LanguageTool not available (requires Java)")
class TestLanguageToolIntegration:
    """Integration tests with real LanguageTool."""

    def test_catches_misspelling(self, grammar_check, mock_standards):
        """Should catch obvious misspellings like 'lisensed'."""
        doc = Mock()
        doc.full_text = Mock(return_value="HellSpin is Curaçao-lisensed.")
        doc.location_for_span = Mock(return_value=Mock(
            section_index=0,
            section_title=None,
            paragraph_index=0,
            element_type="paragraph",
            start_offset=0,
            end_offset=30,
        ))

        findings = grammar_check.run(doc, mock_standards)

        # Should catch "lisensed"
        misspelling_findings = [
            f for f in findings
            if "lisensed" in f.original_text.lower() or "licensed" in str(f.proposed_text).lower()
        ]
        assert len(misspelling_findings) >= 1, f"Expected to catch 'lisensed', got: {[f.original_text for f in findings]}"

    def test_catches_missing_space_after_period(self, grammar_check, mock_standards):
        """Should catch 'want.The' -> 'want. The'."""
        doc = Mock()
        doc.full_text = Mock(return_value="I want.The same thing.")
        doc.location_for_span = Mock(return_value=Mock(
            section_index=0,
            section_title=None,
            paragraph_index=0,
            element_type="paragraph",
            start_offset=0,
            end_offset=25,
        ))

        findings = grammar_check.run(doc, mock_standards)

        # Should catch the missing space via SENTENCE_WHITESPACE
        space_findings = [
            f for f in findings
            if "SENTENCE_WHITESPACE" in str(dict(f.metadata).get("rule_id", ""))
        ]
        assert len(space_findings) >= 1, f"Expected SENTENCE_WHITESPACE finding, got: {findings}"

    def test_catches_double_space(self, grammar_check, mock_standards):
        """Should catch double spaces in prose."""
        doc = Mock()
        # Use plain prose without email to ensure CONSECUTIVE_SPACES triggers
        doc.full_text = Mock(return_value="This is  a test with double space.")
        doc.location_for_span = Mock(return_value=Mock(
            section_index=0,
            section_title=None,
            paragraph_index=0,
            element_type="paragraph",
            start_offset=0,
            end_offset=40,
        ))

        findings = grammar_check.run(doc, mock_standards)

        # Should catch double space via CONSECUTIVE_SPACES
        space_findings = [
            f for f in findings
            if "CONSECUTIVE_SPACES" in str(dict(f.metadata).get("rule_id", ""))
            or "  " in f.original_text
        ]
        assert len(space_findings) >= 1, f"Expected double space finding, got: {findings}"

    def test_brand_name_not_flagged(self, grammar_check, mock_standards):
        """Brand name should not be flagged as misspelling."""
        mock_standards.brand_name = "HellSpin"

        doc = Mock()
        doc.full_text = Mock(return_value="Welcome to HellSpin casino.")
        doc.location_for_span = Mock(return_value=Mock(
            section_index=0,
            section_title=None,
            paragraph_index=0,
            element_type="paragraph",
            start_offset=0,
            end_offset=30,
        ))

        findings = grammar_check.run(doc, mock_standards)

        # Should NOT flag "HellSpin" as a typo
        hellspin_findings = [
            f for f in findings
            if f.original_text.lower() == "hellspin"
        ]
        assert len(hellspin_findings) == 0, f"Brand 'HellSpin' should not be flagged: {hellspin_findings}"
