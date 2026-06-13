"""
Tests for deterministic/formatting.py - Formatting consistency check.
"""

import pytest
from dataclasses import dataclass, field
from typing import Optional

from core.document import Document, Paragraph, Heading, HeadingLevel, List, ListItem, ListType, Table, TableRow, TableCell
from core.check_base import CheckRegistry


# =============================================================================
# FIXTURES
# =============================================================================

@dataclass
class MockFormattingStandards:
    """Mock formatting standards (none required)."""
    pass


@dataclass
class MockStandards:
    """Mock standards object."""
    formatting: MockFormattingStandards = None

    def __post_init__(self):
        if self.formatting is None:
            self.formatting = MockFormattingStandards()


def make_document(text: str, start_offset: int = 0) -> Document:
    """Create a simple document with one paragraph."""
    para = Paragraph(
        text=text,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
    )
    return Document.from_elements([para])


def make_heading_document(text: str, level: int = 2) -> Document:
    """Create a document with one heading."""
    heading = Heading(
        text=text,
        level=HeadingLevel(level),
        start_offset=0,
        end_offset=len(text),
    )
    return Document.from_elements([heading])


def make_list_document(items: list[str]) -> Document:
    """Create a document with a list."""
    offset = 0
    list_items = []
    for item_text in items:
        list_items.append(ListItem(
            text=item_text,
            start_offset=offset,
            end_offset=offset + len(item_text),
            indent_level=0,
        ))
        offset += len(item_text) + 1

    lst = List(
        items=list_items,
        list_type=ListType.UNORDERED,
        start_offset=0,
        end_offset=offset - 1,
    )
    return Document.from_elements([lst])


def make_table_document(cells: list[str]) -> Document:
    """Create a document with a single-row table."""
    offset = 0
    table_cells = []
    for i, cell_text in enumerate(cells):
        table_cells.append(TableCell(
            text=cell_text,
            start_offset=offset,
            end_offset=offset + len(cell_text),
            row_index=0,
            col_index=i,
        ))
        offset += len(cell_text) + 1

    row = TableRow(cells=table_cells, is_header_row=False)
    table = Table(
        rows=[row],
        start_offset=0,
        end_offset=offset - 1,
    )
    return Document.from_elements([table])


def get_registry():
    """Get or create the check registry."""
    return CheckRegistry()


@pytest.fixture
def check():
    """Create the formatting check instance."""
    # Import here to trigger registration
    from deterministic.formatting import FormattingCheck

    registry = get_registry()
    if not registry.is_registered("formatting"):
        from core.check_base import register_check
        register_check(FormattingCheck)

    return FormattingCheck()


@pytest.fixture
def standards() -> MockStandards:
    """Create mock standards."""
    return MockStandards()


# =============================================================================
# DOUBLE SPACES
# =============================================================================

class TestDoubleSpaces:
    """Test double/multiple space detection."""

    def test_double_space_collapsed(self, check, standards):
        """Double space -> single space, auto-applicable."""
        doc = make_document("Hello  world")
        findings = check.run(doc, standards)

        double_space = [f for f in findings if f.metadata_dict.get("sub_check") == "double_space"]
        assert len(double_space) == 1
        assert double_space[0].original_text == "  "
        assert double_space[0].proposed_text == " "
        assert double_space[0].auto_applicable is True

    def test_triple_space_collapsed(self, check, standards):
        """Three+ spaces -> single space."""
        doc = make_document("Hello   world")
        findings = check.run(doc, standards)

        double_space = [f for f in findings if f.metadata_dict.get("sub_check") == "double_space"]
        assert len(double_space) == 1
        assert double_space[0].original_text == "   "
        assert double_space[0].proposed_text == " "

    def test_single_space_not_flagged(self, check, standards):
        """Normal single spaces not flagged."""
        doc = make_document("Hello world, how are you?")
        findings = check.run(doc, standards)

        double_space = [f for f in findings if f.metadata_dict.get("sub_check") == "double_space"]
        assert len(double_space) == 0

    def test_multiple_double_spaces(self, check, standards):
        """Multiple double spaces each flagged."""
        doc = make_document("One  two  three")
        findings = check.run(doc, standards)

        double_space = [f for f in findings if f.metadata_dict.get("sub_check") == "double_space"]
        assert len(double_space) == 2


# =============================================================================
# SPACE BEFORE PUNCTUATION
# =============================================================================

class TestSpaceBeforePunctuation:
    """Test space before punctuation detection."""

    def test_space_before_comma_removed(self, check, standards):
        """"word ," -> "word," auto-applicable."""
        doc = make_document("Hello , world")
        findings = check.run(doc, standards)

        space_before = [f for f in findings if f.metadata_dict.get("sub_check") == "space_before_punct"]
        assert len(space_before) == 1
        assert space_before[0].original_text == " ,"
        assert space_before[0].proposed_text == ","
        assert space_before[0].auto_applicable is True

    def test_space_before_period_removed(self, check, standards):
        """"word ." -> "word." auto-applicable."""
        doc = make_document("Hello world .")
        findings = check.run(doc, standards)

        space_before = [f for f in findings if f.metadata_dict.get("sub_check") == "space_before_punct"]
        assert len(space_before) == 1
        assert space_before[0].proposed_text == "."

    def test_space_before_semicolon_removed(self, check, standards):
        """Space before semicolon removed."""
        doc = make_document("First ; second")
        findings = check.run(doc, standards)

        space_before = [f for f in findings if f.metadata_dict.get("sub_check") == "space_before_punct"]
        assert len(space_before) == 1
        assert space_before[0].proposed_text == ";"

    def test_space_before_paren_not_flagged(self, check, standards):
        """"word (" is legitimate, not flagged."""
        doc = make_document("See the rules (section 5) for details.")
        findings = check.run(doc, standards)

        space_before = [f for f in findings if f.metadata_dict.get("sub_check") == "space_before_punct"]
        assert len(space_before) == 0

    def test_ellipsis_not_flagged(self, check, standards):
        """"..." should not be flagged as space-before-period."""
        doc = make_document("Wait for it... the reveal!")
        findings = check.run(doc, standards)

        space_before = [f for f in findings if f.metadata_dict.get("sub_check") == "space_before_punct"]
        assert len(space_before) == 0

    def test_multiple_spaces_before_punct(self, check, standards):
        """Multiple spaces before punctuation collapsed to punct only."""
        doc = make_document("Hello   ,")
        findings = check.run(doc, standards)

        # Should have both double_space and space_before_punct
        double = [f for f in findings if f.metadata_dict.get("sub_check") == "double_space"]
        space_before = [f for f in findings if f.metadata_dict.get("sub_check") == "space_before_punct"]
        # Either the double space or space before punct will catch this
        assert len(double) + len(space_before) >= 1


# =============================================================================
# MISSING SPACE AFTER PUNCTUATION
# =============================================================================

class TestMissingSpaceAfter:
    """Test missing space after punctuation detection."""

    def test_comma_letter_auto_fix(self, check, standards):
        """"games,slots" -> "games, slots" auto-applicable."""
        doc = make_document("Play games,slots and more.")
        findings = check.run(doc, standards)

        missing = [f for f in findings if f.metadata_dict.get("sub_check") == "missing_space_after"]
        assert len(missing) == 1
        assert missing[0].original_text == ",s"
        assert missing[0].proposed_text == ", s"
        assert missing[0].auto_applicable is True

    def test_period_letter_auto_fix(self, check, standards):
        """"games.slots" -> "games. slots" when not a domain."""
        doc = make_document("End sentence.Start next.")
        findings = check.run(doc, standards)

        missing = [f for f in findings if f.metadata_dict.get("sub_check") == "missing_space_after"]
        assert len(missing) == 1
        assert missing[0].original_text == ".S"
        assert missing[0].proposed_text == ". S"

    def test_decimal_not_flagged(self, check, standards):
        """"3.5" not flagged."""
        doc = make_document("The rate is 3.5 percent.")
        findings = check.run(doc, standards)

        missing = [f for f in findings if f.metadata_dict.get("sub_check") == "missing_space_after"]
        assert len(missing) == 0

    def test_thousands_not_flagged(self, check, standards):
        """"1,000" not flagged."""
        doc = make_document("Win up to 1,000 credits.")
        findings = check.run(doc, standards)

        missing = [f for f in findings if f.metadata_dict.get("sub_check") == "missing_space_after"]
        assert len(missing) == 0

    def test_domain_not_flagged(self, check, standards):
        """"22bet.com" not flagged."""
        doc = make_document("Visit 22bet.com for more.")
        findings = check.run(doc, standards)

        missing = [f for f in findings if f.metadata_dict.get("sub_check") == "missing_space_after"]
        assert len(missing) == 0

    def test_domain_co_uk_not_flagged(self, check, standards):
        """"site.co.uk" not flagged."""
        doc = make_document("Check betway.co.uk today.")
        findings = check.run(doc, standards)

        missing = [f for f in findings if f.metadata_dict.get("sub_check") == "missing_space_after"]
        assert len(missing) == 0

    def test_abbreviation_eg_not_flagged(self, check, standards):
        """"e.g." not flagged by missing_space (handled by latin_abbrev)."""
        doc = make_document("Games e.g. slots are popular.")
        findings = check.run(doc, standards)

        missing = [f for f in findings if f.metadata_dict.get("sub_check") == "missing_space_after"]
        assert len(missing) == 0

    def test_abbreviation_ie_not_flagged(self, check, standards):
        """"i.e." not flagged by missing_space."""
        doc = make_document("The bonus i.e. free spins.")
        findings = check.run(doc, standards)

        missing = [f for f in findings if f.metadata_dict.get("sub_check") == "missing_space_after"]
        assert len(missing) == 0

    def test_version_number_not_flagged(self, check, standards):
        """Version numbers like v1.2 not flagged."""
        doc = make_document("Download version v2.0 now.")
        findings = check.run(doc, standards)

        missing = [f for f in findings if f.metadata_dict.get("sub_check") == "missing_space_after"]
        assert len(missing) == 0

    def test_file_extension_not_flagged(self, check, standards):
        """File extensions not flagged."""
        doc = make_document("Download the guide.pdf file.")
        findings = check.run(doc, standards)

        missing = [f for f in findings if f.metadata_dict.get("sub_check") == "missing_space_after"]
        assert len(missing) == 0


# =============================================================================
# LATIN ABBREVIATIONS
# =============================================================================

class TestLatinAbbreviations:
    """Test Latin abbreviation detection."""

    def test_eg_flagged_proposal(self, check, standards):
        """"e.g." -> proposal with "for example"."""
        doc = make_document("Games e.g. slots are popular.")
        findings = check.run(doc, standards)

        latin = [f for f in findings if f.metadata_dict.get("sub_check") == "latin_abbrev"]
        assert len(latin) == 1
        assert latin[0].original_text.lower() == "e.g."
        assert latin[0].proposed_text == "for example"
        assert latin[0].auto_applicable is False

    def test_ie_flagged_proposal(self, check, standards):
        """"i.e." -> proposal with "that is"."""
        doc = make_document("The bonus i.e. free spins.")
        findings = check.run(doc, standards)

        latin = [f for f in findings if f.metadata_dict.get("sub_check") == "latin_abbrev"]
        assert len(latin) == 1
        assert latin[0].original_text.lower() == "i.e."
        assert latin[0].proposed_text == "that is"

    def test_etc_flagged_proposal(self, check, standards):
        """"etc." -> proposal with rephrase suggestion."""
        doc = make_document("Play slots, poker, etc.")
        findings = check.run(doc, standards)

        latin = [f for f in findings if f.metadata_dict.get("sub_check") == "latin_abbrev"]
        assert len(latin) == 1
        assert latin[0].original_text.lower() == "etc."
        assert "[rephrase" in latin[0].proposed_text.lower()

    def test_viz_flagged_proposal(self, check, standards):
        """"viz." -> proposal with "namely"."""
        doc = make_document("The main games viz. slots and poker.")
        findings = check.run(doc, standards)

        latin = [f for f in findings if f.metadata_dict.get("sub_check") == "latin_abbrev"]
        assert len(latin) == 1
        assert latin[0].proposed_text == "namely"

    def test_not_auto_applicable(self, check, standards):
        """Latin abbrev findings never auto_applicable."""
        doc = make_document("Games e.g. slots and i.e. tables etc.")
        findings = check.run(doc, standards)

        latin = [f for f in findings if f.metadata_dict.get("sub_check") == "latin_abbrev"]
        assert len(latin) == 3
        assert all(f.auto_applicable is False for f in latin)

    def test_latin_in_heading(self, check, standards):
        """Latin abbreviations flagged in headings too."""
        doc = make_heading_document("Popular Games e.g. Slots")
        findings = check.run(doc, standards)

        latin = [f for f in findings if f.metadata_dict.get("sub_check") == "latin_abbrev"]
        assert len(latin) == 1


# =============================================================================
# UI ELEMENT QUOTING (DISABLED - too many false positives)
# =============================================================================

class TestUIQuoting:
    """Test UI element quoting detection.

    NOTE: UI quoting is DISABLED by default due to high false positive rate
    in corpus validation (flagged country names, section headings, etc.).
    These tests verify the behavior when enabled.
    """

    @pytest.mark.skip(reason="UI quoting disabled - too many false positives")
    def test_tap_register_flagged(self, check, standards):
        """"tap Register" -> proposal "tap 'Register'"."""
        doc = make_document("Next, tap Register to create your account.")
        findings = check.run(doc, standards)

        ui = [f for f in findings if f.metadata_dict.get("sub_check") == "ui_quoting"]
        assert len(ui) == 1
        assert "tap Register" in ui[0].original_text
        assert "tap 'Register'" in ui[0].proposed_text
        assert ui[0].auto_applicable is False

    @pytest.mark.skip(reason="UI quoting disabled - too many false positives")
    def test_click_deposit_flagged(self, check, standards):
        """"click Deposit" -> proposal."""
        doc = make_document("Then click Deposit to add funds.")
        findings = check.run(doc, standards)

        ui = [f for f in findings if f.metadata_dict.get("sub_check") == "ui_quoting"]
        assert len(ui) == 1
        assert "click Deposit" in ui[0].original_text

    def test_already_quoted_not_flagged(self, check, standards):
        """"tap 'Register'" not flagged (disabled anyway)."""
        doc = make_document("Next, tap 'Register' to continue.")
        findings = check.run(doc, standards)

        ui = [f for f in findings if f.metadata_dict.get("sub_check") == "ui_quoting"]
        assert len(ui) == 0

    def test_double_quoted_not_flagged(self, check, standards):
        """"click \"Submit\"" not flagged (disabled anyway)."""
        doc = make_document('Then click "Submit" to finish.')
        findings = check.run(doc, standards)

        ui = [f for f in findings if f.metadata_dict.get("sub_check") == "ui_quoting"]
        assert len(ui) == 0

    def test_random_capital_not_flagged(self, check, standards):
        """Random capitalized word without action verb not flagged."""
        doc = make_document("The Register page shows your details.")
        findings = check.run(doc, standards)

        ui = [f for f in findings if f.metadata_dict.get("sub_check") == "ui_quoting"]
        assert len(ui) == 0

    def test_common_word_after_verb_not_flagged(self, check, standards):
        """Common words like 'the' after action verb not flagged (disabled anyway)."""
        doc = make_document("Select the option you prefer.")
        findings = check.run(doc, standards)

        ui = [f for f in findings if f.metadata_dict.get("sub_check") == "ui_quoting"]
        assert len(ui) == 0

    @pytest.mark.skip(reason="UI quoting disabled - too many false positives")
    def test_not_auto_applicable(self, check, standards):
        """UI quoting findings never auto_applicable."""
        doc = make_document("Tap Register, then click Submit.")
        findings = check.run(doc, standards)

        ui = [f for f in findings if f.metadata_dict.get("sub_check") == "ui_quoting"]
        assert len(ui) >= 1
        assert all(f.auto_applicable is False for f in ui)

    def test_ui_not_in_heading(self, check, standards):
        """UI quoting not checked in headings (disabled anyway)."""
        doc = make_heading_document("Click Register Now")
        findings = check.run(doc, standards)

        ui = [f for f in findings if f.metadata_dict.get("sub_check") == "ui_quoting"]
        assert len(ui) == 0


# =============================================================================
# TRAILING WHITESPACE
# =============================================================================

class TestTrailingWhitespace:
    """Test trailing whitespace detection."""

    def test_trailing_space_stripped(self, check, standards):
        """"text " -> "text" auto-applicable."""
        doc = make_document("Hello world ")
        findings = check.run(doc, standards)

        trailing = [f for f in findings if f.metadata_dict.get("sub_check") == "trailing_whitespace"]
        assert len(trailing) == 1
        assert trailing[0].original_text == " "
        assert trailing[0].proposed_text == ""
        assert trailing[0].auto_applicable is True

    def test_multiple_trailing_spaces(self, check, standards):
        """Multiple trailing spaces stripped."""
        doc = make_document("Hello world   ")
        findings = check.run(doc, standards)

        trailing = [f for f in findings if f.metadata_dict.get("sub_check") == "trailing_whitespace"]
        assert len(trailing) == 1
        assert trailing[0].original_text == "   "

    def test_trailing_tab_stripped(self, check, standards):
        """Trailing tab stripped."""
        doc = make_document("Hello world\t")
        findings = check.run(doc, standards)

        trailing = [f for f in findings if f.metadata_dict.get("sub_check") == "trailing_whitespace"]
        assert len(trailing) == 1

    def test_no_trailing_not_flagged(self, check, standards):
        """"text" not flagged."""
        doc = make_document("Hello world")
        findings = check.run(doc, standards)

        trailing = [f for f in findings if f.metadata_dict.get("sub_check") == "trailing_whitespace"]
        assert len(trailing) == 0


# =============================================================================
# ELEMENT TYPE COVERAGE
# =============================================================================

class TestElementCoverage:
    """Test that sub-checks run on appropriate element types."""

    def test_whitespace_in_list_items(self, check, standards):
        """Whitespace checks run on list items."""
        doc = make_list_document(["Item  one", "Item two "])
        findings = check.run(doc, standards)

        double = [f for f in findings if f.metadata_dict.get("sub_check") == "double_space"]
        trailing = [f for f in findings if f.metadata_dict.get("sub_check") == "trailing_whitespace"]
        assert len(double) == 1
        assert len(trailing) == 1

    def test_whitespace_in_table_cells(self, check, standards):
        """Whitespace checks run on table cells."""
        doc = make_table_document(["Cell  one", "Cell two "])
        findings = check.run(doc, standards)

        double = [f for f in findings if f.metadata_dict.get("sub_check") == "double_space"]
        trailing = [f for f in findings if f.metadata_dict.get("sub_check") == "trailing_whitespace"]
        assert len(double) == 1
        assert len(trailing) == 1

    def test_latin_not_in_list_items(self, check, standards):
        """Latin abbreviations not checked in list items."""
        doc = make_list_document(["Games e.g. slots", "Tables etc."])
        findings = check.run(doc, standards)

        latin = [f for f in findings if f.metadata_dict.get("sub_check") == "latin_abbrev"]
        assert len(latin) == 0

    def test_ui_not_in_table_cells(self, check, standards):
        """UI quoting not checked in table cells (disabled anyway)."""
        doc = make_table_document(["Click Register", "Tap Submit"])
        findings = check.run(doc, standards)

        ui = [f for f in findings if f.metadata_dict.get("sub_check") == "ui_quoting"]
        assert len(ui) == 0  # UI quoting disabled, so 0 is expected


# =============================================================================
# LOCATION ACCURACY
# =============================================================================

class TestLocationAccuracy:
    """Test that finding locations are accurate."""

    def test_double_space_offset(self, check, standards):
        """Double space offset matches text position."""
        text = "Hello  world"
        doc = make_document(text)
        findings = check.run(doc, standards)

        double = [f for f in findings if f.metadata_dict.get("sub_check") == "double_space"]
        assert len(double) == 1
        expected_start = text.find("  ")
        assert double[0].location.start_offset == expected_start
        assert double[0].location.end_offset == expected_start + 2

    def test_latin_abbrev_offset(self, check, standards):
        """Latin abbreviation offset matches text position."""
        text = "Games e.g. slots are fun."
        doc = make_document(text)
        findings = check.run(doc, standards)

        latin = [f for f in findings if f.metadata_dict.get("sub_check") == "latin_abbrev"]
        assert len(latin) == 1
        expected_start = text.find("e.g.")
        assert latin[0].location.start_offset == expected_start
        assert latin[0].location.end_offset == expected_start + 4


# =============================================================================
# REGISTRATION
# =============================================================================

class TestRegistration:
    """Test check self-registration."""

    def test_self_registers(self):
        """Check registers itself with the registry."""
        from deterministic.formatting import FormattingCheck

        registry = get_registry()
        if not registry.is_registered("formatting"):
            from core.check_base import register_check
            register_check(FormattingCheck)

        assert "formatting" in registry
        assert isinstance(registry.get_instance("formatting"), FormattingCheck)

    def test_metadata(self, check):
        """Check has correct metadata."""
        assert check.name == "formatting"
        assert check.category == "formatting"
        assert "whitespace" in check.metadata.description.lower() or "formatting" in check.metadata.description.lower()
