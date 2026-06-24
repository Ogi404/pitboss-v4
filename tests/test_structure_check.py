"""
Tests for deterministic/structure.py - Document Structure Check

Tests structure validation against brief requirements and
General Writing Requirements §10.
"""

import pytest
from dataclasses import dataclass, field
from typing import Optional

from core.document import (
    Document, Paragraph, Heading, HeadingLevel, TextRun, Location
)
from core.finding import Finding
from deterministic.structure import (
    StructureCheck,
    normalize_heading,
    fuzzy_section_match,
    count_words,
    WORD_COUNT_DEVIATION_THRESHOLD,
    MIN_OUTRO_WORDS,
    FUZZY_MATCH_THRESHOLD,
)


# =============================================================================
# FIXTURES
# =============================================================================

@dataclass
class MockBriefSection:
    """Mock BriefSection for testing."""
    heading: str
    word_count: Optional[int] = None
    is_required: bool = True


@dataclass
class MockBriefModel:
    """Mock BriefModel for testing."""
    sections: tuple = ()
    target_word_count: Optional[int] = None
    brand_name: str = ""


@dataclass
class MockStandards:
    """Mock standards for testing."""
    brand_name: str = ""


def make_document(
    elements: list = None,
    text: str = None,
) -> Document:
    """
    Create a Document from elements or simple text.

    If text is provided, creates a single paragraph document.
    If elements are provided, uses them directly.
    """
    if text is not None:
        para = Paragraph(
            text=text,
            start_offset=0,
            end_offset=len(text),
            _runs=[TextRun(
                text=text,
                start_offset=0,
                end_offset=len(text),
            )],
        )
        return Document(elements=[para])

    return Document(elements=elements or [])


def make_heading(text: str, level: int, start_offset: int) -> Heading:
    """Create a Heading element."""
    return Heading(
        text=text,
        level=HeadingLevel(level),
        start_offset=start_offset,
        end_offset=start_offset + len(text),
    )


def make_paragraph(text: str, start_offset: int) -> Paragraph:
    """Create a Paragraph element."""
    return Paragraph(
        text=text,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
        _runs=[TextRun(
            text=text,
            start_offset=start_offset,
            end_offset=start_offset + len(text),
        )],
    )


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

class TestNormalizeHeading:
    """Tests for normalize_heading function."""

    def test_lowercase(self):
        assert normalize_heading("WELCOME BONUSES") == "welcome bonuses"

    def test_strip_punctuation(self):
        assert normalize_heading("Bonuses!") == "bonuses"
        assert normalize_heading("What's New?") == "whats new"

    def test_strip_whitespace(self):
        assert normalize_heading("  Bonuses  ") == "bonuses"

    def test_mixed(self):
        assert normalize_heading("  WELCOME Bonuses!  ") == "welcome bonuses"


class TestFuzzySectionMatch:
    """Tests for fuzzy_section_match function."""

    def test_exact_match(self):
        assert fuzzy_section_match("Bonuses", "Bonuses") is True

    def test_substring_match(self):
        assert fuzzy_section_match("Bonuses", "Welcome Bonuses and Promotions") is True

    def test_substring_case_insensitive(self):
        assert fuzzy_section_match("bonuses", "WELCOME BONUSES") is True

    def test_word_overlap_match(self):
        # "Payment Methods" has 2 words, "Methods of Payment" has 2/2 overlap = 100%
        assert fuzzy_section_match("Payment Methods", "Methods of Payment") is True

    def test_partial_overlap_50_percent(self):
        # "Payment Methods" has 2 words, "Payment Options" has 1/2 overlap = 50%
        assert fuzzy_section_match("Payment Methods", "Payment Options") is True

    def test_partial_overlap_below_threshold(self):
        # "Banking Payment Methods" has 3 words
        # "Quick Withdrawal Options" has 0/3 overlap
        assert fuzzy_section_match("Banking Payment Methods", "Quick Withdrawal Options") is False

    def test_no_match(self):
        assert fuzzy_section_match("Bonuses", "Customer Support") is False

    def test_empty_required(self):
        assert fuzzy_section_match("", "Something") is False

    def test_punctuation_ignored(self):
        assert fuzzy_section_match("What's New?", "Whats New Section") is True


class TestCountWords:
    """Tests for count_words function."""

    def test_simple(self):
        assert count_words("one two three") == 3

    def test_with_punctuation(self):
        assert count_words("Hello, world! How are you?") == 5

    def test_empty(self):
        assert count_words("") == 0

    def test_whitespace_only(self):
        assert count_words("   ") == 0


# =============================================================================
# STRUCTURE CHECK - NO BRIEF
# =============================================================================

class TestStructureCheckNoOp:
    """Tests for graceful handling when brief is unavailable."""

    def test_no_brief_runs_doc_checks(self):
        """Check runs hierarchy/intro/outro checks even without brief."""
        # Document with proper structure
        elements = [
            make_paragraph("This is an intro paragraph with enough words.", 0),
            make_heading("Section One", 2, 50),
            make_paragraph("Section content here with enough words for testing purposes.", 70),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        # Should run but not crash, might have findings for structure issues
        assert isinstance(findings, list)

    def test_no_brief_no_section_checks(self):
        """Missing sections check should not run without brief."""
        doc = make_document(text="Simple content without any sections.")
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        # Should not have missing_section findings
        missing = [f for f in findings if f.check_name == "structure.missing_section"]
        assert len(missing) == 0

    def test_invalid_brief_type_graceful(self):
        """Check handles invalid brief type gracefully."""
        doc = make_document(text="Simple content.")
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief="not a brief")

        # Should not crash, just skip brief-dependent checks
        missing = [f for f in findings if f.check_name == "structure.missing_section"]
        assert len(missing) == 0


# =============================================================================
# REQUIRED SECTIONS TESTS
# =============================================================================

class TestMissingSections:
    """Tests for required section detection."""

    def test_section_present_exact_no_finding(self):
        """Exact match for required section should not be flagged."""
        elements = [
            make_paragraph("Intro paragraph here.", 0),
            make_heading("Bonuses", 2, 30),
            make_paragraph("Content about bonuses with enough words for this test.", 45),
        ]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(MockBriefSection(heading="Bonuses"),)
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        missing = [f for f in findings if f.check_name == "structure.missing_section"]
        assert len(missing) == 0

    def test_section_present_fuzzy_substring_no_finding(self):
        """Fuzzy substring match should not be flagged."""
        elements = [
            make_paragraph("Intro paragraph here.", 0),
            make_heading("Welcome Bonuses and Promotions", 2, 30),
            make_paragraph("Content here with enough words for testing.", 75),
        ]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(MockBriefSection(heading="Bonuses"),)
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        missing = [f for f in findings if f.check_name == "structure.missing_section"]
        assert len(missing) == 0

    def test_section_present_fuzzy_overlap_no_finding(self):
        """Fuzzy word overlap match should not be flagged."""
        elements = [
            make_paragraph("Intro paragraph here.", 0),
            make_heading("Methods of Payment", 2, 30),
            make_paragraph("Content about payment methods.", 55),
        ]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(MockBriefSection(heading="Payment Methods"),)
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        missing = [f for f in findings if f.check_name == "structure.missing_section"]
        assert len(missing) == 0

    def test_section_absent_flagged(self):
        """Missing required section should be flagged."""
        elements = [
            make_paragraph("Intro paragraph here.", 0),
            make_heading("Customer Support", 2, 30),
            make_paragraph("Content about support.", 55),
        ]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(MockBriefSection(heading="Bonuses"),)
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        missing = [f for f in findings if f.check_name == "structure.missing_section"]
        assert len(missing) == 1
        assert "Bonuses" in missing[0].reasoning
        assert missing[0].auto_applicable is False

    def test_multiple_sections_some_missing(self):
        """Multiple sections with some missing should flag only missing ones."""
        elements = [
            make_paragraph("Intro.", 0),
            make_heading("Bonuses", 2, 10),
            make_paragraph("Bonus content.", 25),
            make_heading("FAQ", 2, 45),
            make_paragraph("FAQ content.", 55),
        ]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(
                MockBriefSection(heading="Bonuses"),      # Present
                MockBriefSection(heading="Payments"),     # Missing
                MockBriefSection(heading="FAQ"),          # Present
                MockBriefSection(heading="Live Casino"),  # Missing
            )
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        missing = [f for f in findings if f.check_name == "structure.missing_section"]
        assert len(missing) == 2
        missing_sections = [f.metadata_dict["required_section"] for f in missing]
        assert "Payments" in missing_sections
        assert "Live Casino" in missing_sections

    def test_metadata_labels_filtered(self):
        """Metadata labels like 'Main keywords' should not be treated as required sections."""
        elements = [
            make_paragraph("Intro paragraph here.", 0),
            make_heading("Some Section", 2, 30),
            make_paragraph("Content here.", 50),
        ]
        doc = make_document(elements=elements)
        # Brief with metadata labels that should be filtered out
        brief = MockBriefModel(
            sections=(
                MockBriefSection(heading="Main keywords"),      # Metadata label - skip
                MockBriefSection(heading="Support keywords"),   # Metadata label - skip
                MockBriefSection(heading="LSI keywords"),       # Metadata label - skip
                MockBriefSection(heading="Word Count"),         # Metadata label - skip
                MockBriefSection(heading="Meta Description"),   # Metadata label - skip
                MockBriefSection(heading="Some Section"),       # Real section - present
            )
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        # Should have no missing section findings (labels filtered, real section present)
        missing = [f for f in findings if f.check_name == "structure.missing_section"]
        assert len(missing) == 0


# =============================================================================
# HIERARCHY TESTS
# =============================================================================

class TestHierarchy:
    """Tests for heading hierarchy checks."""

    def test_proper_hierarchy_no_finding(self):
        """Proper hierarchy H1 -> H2 -> H3 -> H2 should not be flagged."""
        elements = [
            make_paragraph("Intro.", 0),
            make_heading("Main Title", 1, 10),
            make_heading("Section One", 2, 30),
            make_heading("Subsection", 3, 50),
            make_heading("Section Two", 2, 70),
            make_paragraph("Content.", 90),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        hierarchy = [f for f in findings if f.check_name == "structure.hierarchy"]
        assert len(hierarchy) == 0

    def test_multiple_h1_flagged(self):
        """Multiple H1 headings should be flagged."""
        elements = [
            make_heading("Title One", 1, 0),
            make_paragraph("Content.", 15),
            make_heading("Title Two", 1, 30),
            make_paragraph("More content.", 45),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        hierarchy = [f for f in findings if f.check_name == "structure.hierarchy"]
        assert len(hierarchy) == 1
        assert "H1" in hierarchy[0].reasoning
        assert hierarchy[0].auto_applicable is False

    def test_skipped_level_flagged(self):
        """Skipped heading level H1 -> H3 should be flagged."""
        elements = [
            make_heading("Title", 1, 0),
            make_heading("Deep Section", 3, 20),  # Skipped H2
            make_paragraph("Content.", 45),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        hierarchy = [f for f in findings if f.check_name == "structure.hierarchy"]
        assert len(hierarchy) == 1
        assert "H3" in hierarchy[0].reasoning
        assert "H1" in hierarchy[0].reasoning
        assert "skip" in hierarchy[0].reasoning.lower()
        assert hierarchy[0].auto_applicable is False

    def test_h2_to_h4_skipped(self):
        """Skipped level H2 -> H4 should be flagged."""
        elements = [
            make_heading("Title", 1, 0),
            make_heading("Section", 2, 15),
            make_heading("Deep Subsection", 4, 35),  # Skipped H3
            make_paragraph("Content.", 60),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        hierarchy = [f for f in findings if f.check_name == "structure.hierarchy"]
        assert len(hierarchy) == 1
        assert "H4" in hierarchy[0].reasoning
        assert "H2" in hierarchy[0].reasoning

    def test_no_headings_no_finding(self):
        """Document without headings should not trigger hierarchy findings."""
        doc = make_document(text="Just a simple paragraph with no headings at all.")
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        hierarchy = [f for f in findings if f.check_name == "structure.hierarchy"]
        assert len(hierarchy) == 0


# =============================================================================
# INTRO TESTS
# =============================================================================

class TestIntro:
    """Tests for intro paragraph detection."""

    def test_intro_present_no_finding(self):
        """Document with intro paragraph before first heading should not be flagged."""
        elements = [
            make_paragraph("This is a nice introductory paragraph that introduces the article.", 0),
            make_heading("Section One", 2, 70),
            make_paragraph("Section content.", 90),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        intro = [f for f in findings if f.check_name == "structure.missing_intro"]
        assert len(intro) == 0

    def test_no_intro_flagged(self):
        """Document starting directly with heading should be flagged."""
        elements = [
            make_heading("Section One", 2, 0),
            make_paragraph("Section content.", 20),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        intro = [f for f in findings if f.check_name == "structure.missing_intro"]
        assert len(intro) == 1
        assert "introductory" in intro[0].reasoning.lower()
        assert intro[0].auto_applicable is False

    def test_short_intro_not_counted(self):
        """Very short text before heading (< 6 words) should still flag."""
        elements = [
            make_paragraph("Hello there.", 0),  # Only 2 words
            make_heading("Section One", 2, 15),
            make_paragraph("Section content.", 35),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        intro = [f for f in findings if f.check_name == "structure.missing_intro"]
        assert len(intro) == 1

    def test_no_headings_no_intro_check(self):
        """Document without headings should not check for intro."""
        doc = make_document(text="Just content without any headings.")
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        intro = [f for f in findings if f.check_name == "structure.missing_intro"]
        assert len(intro) == 0


# =============================================================================
# OUTRO TESTS
# =============================================================================

class TestOutro:
    """Tests for outro/conclusion paragraph detection."""

    def test_proper_outro_no_finding(self):
        """Document ending with substantial paragraph should not be flagged."""
        elements = [
            make_heading("Section", 2, 0),
            make_paragraph(
                "This is a proper concluding paragraph that wraps up the article "
                "with enough words to qualify as a real conclusion section.",
                20
            ),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        outro = [f for f in findings if f.check_name == "structure.missing_outro"]
        assert len(outro) == 0

    def test_ends_with_heading_flagged(self):
        """Document ending with heading should be flagged."""
        elements = [
            make_paragraph("Some content.", 0),
            make_heading("Final Section", 2, 20),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        outro = [f for f in findings if f.check_name == "structure.missing_outro"]
        assert len(outro) == 1
        assert "heading" in outro[0].reasoning.lower()
        assert outro[0].auto_applicable is False

    def test_short_outro_flagged(self):
        """Document ending with very short paragraph should be flagged."""
        short_text = "Just a few words."  # < MIN_OUTRO_WORDS
        elements = [
            make_heading("Section", 2, 0),
            make_paragraph(short_text, 15),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        outro = [f for f in findings if f.check_name == "structure.missing_outro"]
        assert len(outro) == 1
        assert "words" in outro[0].reasoning.lower()
        assert outro[0].auto_applicable is False

    def test_empty_document_no_crash(self):
        """Empty document should not crash."""
        doc = make_document(elements=[])
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        outro = [f for f in findings if f.check_name == "structure.missing_outro"]
        assert len(outro) == 0

    def test_trailing_empty_paragraphs_skipped(self):
        """
        Trailing empty paragraphs should be skipped when finding last content element.

        This prevents false positives from:
        - blank_rows insertion adding trailing empty paragraphs
        - Google Docs conversion adding trailing newlines
        - General document cruft
        """
        elements = [
            make_heading("Section", 2, 0),
            make_paragraph(
                "This is a proper concluding paragraph that wraps up the article "
                "with enough words to qualify as a real conclusion section.",
                100
            ),
            make_paragraph("", 200),  # Empty trailing paragraph
            make_paragraph("", 201),  # Another empty trailing paragraph
            make_paragraph("   ", 202),  # Whitespace-only paragraph
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        # Should NOT flag missing_outro - the real last content is proper
        outro = [f for f in findings if f.check_name == "structure.missing_outro"]
        assert len(outro) == 0, "Trailing empty paragraphs should not trigger missing_outro"

    def test_all_empty_paragraphs_no_crash(self):
        """Document with only empty paragraphs should not crash."""
        elements = [
            make_paragraph("", 0),
            make_paragraph("", 1),
            make_paragraph("   ", 2),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        outro = [f for f in findings if f.check_name == "structure.missing_outro"]
        assert len(outro) == 0


# =============================================================================
# WORD COUNT TESTS
# =============================================================================

class TestWordCount:
    """Tests for word count deviation detection."""

    def test_within_tolerance_no_finding(self):
        """Word count within 20% of target should not be flagged."""
        # Create ~1900 word document, target 2000 (5% under)
        word = "word "
        text = word * 380  # 380 words
        elements = [
            make_paragraph(text, 0),
        ]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(),
            target_word_count=400,  # Within 20%
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        wc = [f for f in findings if f.check_name == "structure.word_count"]
        assert len(wc) == 0

    def test_under_target_flagged(self):
        """Word count significantly under target should be flagged."""
        text = "word " * 100  # 100 words
        elements = [make_paragraph(text, 0)]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(),
            target_word_count=200,  # 100 is 50% under
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        wc = [f for f in findings if f.check_name == "structure.word_count"]
        assert len(wc) == 1
        assert "under" in wc[0].reasoning.lower()
        assert "100" in wc[0].reasoning  # Actual count
        assert "200" in wc[0].reasoning  # Target count
        assert wc[0].auto_applicable is False

    def test_over_target_flagged(self):
        """Word count significantly over target should be flagged."""
        text = "word " * 300  # 300 words
        elements = [make_paragraph(text, 0)]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(),
            target_word_count=200,  # 300 is 50% over
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        wc = [f for f in findings if f.check_name == "structure.word_count"]
        assert len(wc) == 1
        assert "over" in wc[0].reasoning.lower()
        assert wc[0].auto_applicable is False

    def test_no_target_no_finding(self):
        """No target word count should not trigger check."""
        text = "word " * 100
        elements = [make_paragraph(text, 0)]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(),
            target_word_count=None,
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        wc = [f for f in findings if f.check_name == "structure.word_count"]
        assert len(wc) == 0

    def test_zero_target_no_finding(self):
        """Zero target word count should not trigger check."""
        text = "word " * 100
        elements = [make_paragraph(text, 0)]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(),
            target_word_count=0,
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        wc = [f for f in findings if f.check_name == "structure.word_count"]
        assert len(wc) == 0


# =============================================================================
# NO AUTO-APPLICABLE TESTS
# =============================================================================

class TestNoAutoApplicable:
    """Tests that all findings are proposals (not auto-applicable)."""

    def test_all_findings_not_auto_applicable(self):
        """Every structure finding should have auto_applicable=False."""
        # Create document that triggers multiple issues
        elements = [
            # No intro (starts with heading)
            make_heading("Title One", 1, 0),
            make_heading("Title Two", 1, 15),  # Multiple H1
            make_heading("Deep Section", 3, 35),  # Skipped level
            make_paragraph("Short.", 55),  # Short outro
        ]
        doc = make_document(elements=elements)
        brief = MockBriefModel(
            sections=(MockBriefSection(heading="Missing Section"),),
            target_word_count=1000,  # Way over what we have
        )
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        assert len(findings) > 0, "Should have at least some findings"
        for finding in findings:
            assert finding.auto_applicable is False, (
                f"Finding '{finding.check_name}' should not be auto_applicable"
            )


# =============================================================================
# ACCURATE LOCATION TESTS
# =============================================================================

class TestAccurateLocation:
    """Tests for accurate finding locations."""

    def test_hierarchy_location_at_problem_heading(self):
        """Hierarchy findings should point to the problematic heading."""
        elements = [
            make_heading("Title", 1, 0),
            make_heading("Deep Section", 3, 15),  # Problem here
            make_paragraph("Content.", 35),
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        hierarchy = [f for f in findings if f.check_name == "structure.hierarchy"]
        assert len(hierarchy) == 1
        # Location should point to the H3 heading
        loc = hierarchy[0].location
        assert loc.start_offset == 15
        assert hierarchy[0].original_text == "Deep Section"

    def test_outro_location_at_last_element(self):
        """Outro findings should point to the last element."""
        elements = [
            make_paragraph("Content.", 0),
            make_heading("Final", 2, 15),  # Problem: ends with heading
        ]
        doc = make_document(elements=elements)
        check = StructureCheck()
        findings = check.run(doc, MockStandards(), brief=None)

        outro = [f for f in findings if f.check_name == "structure.missing_outro"]
        assert len(outro) == 1
        assert outro[0].original_text == "Final"


# =============================================================================
# CHECK REGISTRATION TESTS
# =============================================================================

class TestCheckRegistration:
    """Tests for check registration."""

    def test_check_registers(self):
        """Check should be registered in the registry."""
        from core.check_base import get_registry
        registry = get_registry()

        # If not registered (another test cleared the registry), re-import
        if not registry.is_registered("structure"):
            import importlib
            import deterministic.structure
            importlib.reload(deterministic.structure)

        assert registry.is_registered("structure")

    def test_check_metadata(self):
        """Check metadata should be correct."""
        check = StructureCheck()
        assert check.metadata.name == "structure"
        assert check.metadata.category == "structure"
        assert check.is_deterministic


# =============================================================================
# CONSTANTS TESTS
# =============================================================================

class TestConstants:
    """Tests that constants are properly defined."""

    def test_deviation_threshold(self):
        """Word count deviation threshold should be 20%."""
        assert WORD_COUNT_DEVIATION_THRESHOLD == 0.20

    def test_min_outro_words(self):
        """Minimum outro words should be 20."""
        assert MIN_OUTRO_WORDS == 20

    def test_fuzzy_match_threshold(self):
        """Fuzzy match threshold should be 50%."""
        assert FUZZY_MATCH_THRESHOLD == 0.5
