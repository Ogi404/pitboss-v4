"""
Tests for formatting hints extraction from brief text.

Verifies:
- Precise phrase matching for explicit formatting instructions
- NO false positives on incidental mentions of "indent" or "paragraph"
"""

import pytest
from ingest.brief_base import extract_formatting_hints


class TestBlankRowsRequired:
    """Test detection of blank_rows='required' instructions."""

    def test_empty_rows_between_paragraphs(self):
        """Detects 'empty rows between paragraphs'."""
        text = "Please make empty rows between paragraphs for readability."
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "required"

    def test_indents_between_paragraphs_and_headings(self):
        """Detects 'indents between paragraphs and headings'."""
        text = "Add indents between paragraphs and headings throughout the article."
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "required"

    def test_blank_lines_between_sections(self):
        """Detects 'blank lines between sections'."""
        text = "Use blank lines between sections for better visual separation."
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "required"

    def test_add_empty_rows_between(self):
        """Detects 'add empty rows between'."""
        text = "Add empty rows between each content block."
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "required"

    def test_separate_paragraphs_with_blank_lines(self):
        """Detects 'separate paragraphs with blank lines'."""
        text = "Please separate paragraphs with blank lines."
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "required"

    def test_case_insensitive(self):
        """Detection is case-insensitive."""
        text = "EMPTY ROWS BETWEEN PARAGRAPHS please"
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "required"


class TestBlankRowsNone:
    """Test detection of blank_rows='none' instructions."""

    def test_no_empty_lines_between(self):
        """Detects 'no empty lines between'."""
        text = "Use no empty lines between paragraphs."
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "none"

    def test_dont_add_blank_rows(self):
        """Detects 'don't add blank rows'."""
        text = "Don't add blank rows between sections."
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "none"

    def test_remove_blank_lines(self):
        """Detects 'remove blank lines'."""
        text = "Remove blank lines from between paragraphs."
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "none"


class TestNoFalsePositives:
    """Test that incidental mentions don't trigger detection."""

    def test_indent_in_code_context(self):
        """Incidental 'indent' in code context doesn't trigger."""
        text = "Use proper indent levels in the code examples."
        hints = extract_formatting_hints(text)
        assert "blank_rows" not in hints

    def test_paragraph_in_general_context(self):
        """Incidental 'paragraph' mention doesn't trigger."""
        text = "Each paragraph should be 3-4 sentences long."
        hints = extract_formatting_hints(text)
        assert "blank_rows" not in hints

    def test_indent_as_verb_for_lists(self):
        """'Indent' as verb for lists doesn't trigger."""
        text = "Indent nested list items appropriately."
        hints = extract_formatting_hints(text)
        assert "blank_rows" not in hints

    def test_empty_in_other_context(self):
        """'Empty' in other context doesn't trigger."""
        text = "Don't leave the meta description empty."
        hints = extract_formatting_hints(text)
        assert "blank_rows" not in hints

    def test_rows_in_table_context(self):
        """'Rows' in table context doesn't trigger."""
        text = "Add two rows to the comparison table."
        hints = extract_formatting_hints(text)
        assert "blank_rows" not in hints

    def test_between_in_other_context(self):
        """'Between' in other context doesn't trigger."""
        text = "The word count should be between 1000-1500 words."
        hints = extract_formatting_hints(text)
        assert "blank_rows" not in hints

    def test_blank_in_form_context(self):
        """'Blank' in form context doesn't trigger."""
        text = "Fill in the blank with the keyword."
        hints = extract_formatting_hints(text)
        assert "blank_rows" not in hints


class TestMultilineText:
    """Test extraction from longer multi-line brief text."""

    def test_instruction_in_middle_of_text(self):
        """Finds instruction embedded in longer text."""
        text = """
        Article Requirements:
        - Word count: 1500 words
        - Tone: Professional but friendly
        - Format: Use empty rows between paragraphs
        - Include at least 3 headings
        """
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "required"

    def test_no_instruction_in_keyword_list(self):
        """Keyword list without formatting instruction."""
        text = """
        Main Keywords:
        - casino bonus (3x)
        - free spins (2x)
        - welcome offer (1x)

        Article should discuss the paragraph about bonuses in detail.
        Make sure to indent code examples properly.
        """
        hints = extract_formatting_hints(text)
        assert "blank_rows" not in hints

    def test_real_brief_example_with_instruction(self):
        """Real-style brief with formatting instruction."""
        text = """
        Task: Main Page Review
        Brand: Koifortune
        Market: AU
        Word Count: 2000

        Instructions:
        Write a comprehensive review. Make empty rows between paragraphs
        for better readability. Use H2 headings for main sections.
        """
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "required"

    def test_real_brief_without_instruction(self):
        """Real-style brief without formatting instruction."""
        text = """
        Task: Meta Title
        Brand: Vave
        Market: Global

        Instructions:
        Create compelling meta title under 60 characters.
        Include primary keyword near the beginning.
        """
        hints = extract_formatting_hints(text)
        assert "blank_rows" not in hints


class TestEmptyAndEdgeCases:
    """Edge cases for extraction."""

    def test_empty_string(self):
        """Empty string returns empty hints."""
        hints = extract_formatting_hints("")
        assert hints == {}

    def test_whitespace_only(self):
        """Whitespace-only string returns empty hints."""
        hints = extract_formatting_hints("   \n\t  ")
        assert hints == {}

    def test_none_safe(self):
        """Handles None gracefully (if called incorrectly)."""
        # The function expects str, but should handle gracefully
        try:
            hints = extract_formatting_hints(None)
            # If it doesn't raise, it should return empty
            assert hints == {}
        except (TypeError, AttributeError):
            # This is acceptable behavior too
            pass

    def test_unicode_text(self):
        """Handles unicode text."""
        text = "Add empty rows between paragraphs. Café résumé naïve."
        hints = extract_formatting_hints(text)
        assert hints.get("blank_rows") == "required"
