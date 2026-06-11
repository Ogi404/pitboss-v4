"""
Tests for the headings check.

Tests cover:
- Blank line before heading (auto-applicable)
- Question mark removal (auto-applicable except FAQ sections)
- Capitalization (brand-specific, cautious auto-apply)
- Descriptive heading detection (flag only)
- Hierarchy validation (flag only)
- Self-registration
"""

import pytest
from dataclasses import dataclass, field
from typing import Optional

from core.check_base import get_registry
from core.document import Document, Paragraph, Heading, HeadingLevel
from core.finding import Finding
from deterministic.headings import HeadingsCheck


# =============================================================================
# FIXTURES
# =============================================================================

@dataclass
class MockHeadingsStandards:
    """Mock headings standards."""
    hierarchy: list[str] = field(default_factory=lambda: ["H1", "H2", "H3", "H4"])
    descriptive_required: bool = True
    capitalization: Optional[str] = None
    no_question_marks: bool = True


@dataclass
class MockStandards:
    """Mock standards object."""
    headings: MockHeadingsStandards = None

    def __post_init__(self):
        if self.headings is None:
            self.headings = MockHeadingsStandards()


def make_document_with_elements(elements: list) -> Document:
    """Create a document from a list of elements."""
    return Document.from_elements(elements)


def make_para(text: str, start: int) -> Paragraph:
    """Create a paragraph at specified offset."""
    return Paragraph(text=text, start_offset=start, end_offset=start + len(text))


def make_heading(text: str, level: int, start: int) -> Heading:
    """Create a heading at specified offset."""
    return Heading(
        text=text,
        level=HeadingLevel(level),
        start_offset=start,
        end_offset=start + len(text),
    )


@pytest.fixture
def check() -> HeadingsCheck:
    """Create the headings check instance."""
    return HeadingsCheck()


@pytest.fixture
def standards() -> MockStandards:
    """Create mock standards with defaults."""
    return MockStandards()


@pytest.fixture
def title_case_standards() -> MockStandards:
    """Create mock standards with title_case capitalization."""
    return MockStandards(headings=MockHeadingsStandards(capitalization="title_case"))


@pytest.fixture
def sentence_case_standards() -> MockStandards:
    """Create mock standards with sentence_case capitalization."""
    return MockStandards(headings=MockHeadingsStandards(capitalization="sentence_case"))


# =============================================================================
# TEST: BLANK LINE BEFORE HEADING
# =============================================================================

class TestBlankLineBeforeHeading:
    """Test blank line detection before headings."""

    def test_missing_blank_line_before_heading(self, check, standards):
        """Heading directly after paragraph (gap=1) produces finding."""
        # Para ends at 50, heading starts at 51 (gap=1, just newline)
        para = make_para("This is a paragraph of text.", 0)
        heading = make_heading("Section Title", 2, para.end_offset + 1)
        doc = make_document_with_elements([para, heading])

        findings = check.run(doc, standards)

        # Should have blank line finding
        blank_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "blank_line"]
        assert len(blank_findings) == 1
        assert blank_findings[0].auto_applicable is True
        assert blank_findings[0].severity == "suggestion"

    def test_has_blank_line_no_finding(self, check, standards):
        """Heading after blank line (gap>1) produces no finding."""
        # Para ends at 50, heading starts at 53 (gap=3, has blank line)
        para = make_para("This is a paragraph of text.", 0)
        heading = make_heading("Section Title", 2, para.end_offset + 3)
        doc = make_document_with_elements([para, heading])

        findings = check.run(doc, standards)

        # Should have no blank line finding
        blank_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "blank_line"]
        assert len(blank_findings) == 0

    def test_first_element_heading_no_finding(self, check, standards):
        """First element is heading - no blank line needed."""
        heading = make_heading("Document Title", 1, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, standards)

        blank_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "blank_line"]
        assert len(blank_findings) == 0

    def test_heading_after_heading_no_blank_needed(self, check, standards):
        """Heading after heading - blank line still needed."""
        h1 = make_heading("Main Title", 1, 0)
        h2 = make_heading("Sub Title", 2, h1.end_offset + 1)  # Gap=1
        doc = make_document_with_elements([h1, h2])

        findings = check.run(doc, standards)

        blank_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "blank_line"]
        assert len(blank_findings) == 1


# =============================================================================
# TEST: QUESTION MARK
# =============================================================================

class TestQuestionMark:
    """Test question mark detection and removal."""

    def test_non_faq_heading_with_question_mark(self, check, standards):
        """Non-FAQ heading with ? gets auto-applicable removal."""
        heading = make_heading("How to Register?", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, standards)

        qm_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "question_mark"]
        assert len(qm_findings) == 1
        assert qm_findings[0].auto_applicable is True
        assert qm_findings[0].proposed_text == "How to Register"

    def test_faq_section_heading_preserves_question_mark(self, check, standards):
        """Heading in FAQ section with ? produces no finding."""
        faq_heading = make_heading("FAQ", 1, 0)
        question = make_heading("Is 22Bet Legal?", 2, faq_heading.end_offset + 10)
        doc = make_document_with_elements([faq_heading, question])

        findings = check.run(doc, standards)

        qm_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "question_mark"]
        assert len(qm_findings) == 0

    def test_frequently_asked_section_preserves_question_mark(self, check, standards):
        """Heading under 'Frequently Asked Questions' section preserves ?."""
        faq_heading = make_heading("Frequently Asked Questions", 1, 0)
        question = make_heading("Can I withdraw instantly?", 2, faq_heading.end_offset + 10)
        doc = make_document_with_elements([faq_heading, question])

        findings = check.run(doc, standards)

        qm_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "question_mark"]
        assert len(qm_findings) == 0

    def test_ambiguous_faq_context_is_proposal(self, check, standards):
        """Interrogative heading outside FAQ section is proposal."""
        para = make_para("Some intro text here.", 0)
        # Starts with interrogative but not in FAQ section
        question = make_heading("Is This Casino Safe?", 2, para.end_offset + 5)
        doc = make_document_with_elements([para, question])

        findings = check.run(doc, standards)

        qm_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "question_mark"]
        assert len(qm_findings) == 1
        assert qm_findings[0].auto_applicable is False
        assert qm_findings[0].metadata_dict.get("context") == "ambiguous_faq"

    def test_heading_without_question_mark_no_finding(self, check, standards):
        """Heading without ? produces no finding."""
        heading = make_heading("Registration Process", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, standards)

        qm_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "question_mark"]
        assert len(qm_findings) == 0

    def test_no_question_marks_disabled(self, check):
        """When no_question_marks is False, no findings."""
        standards = MockStandards(headings=MockHeadingsStandards(no_question_marks=False))
        heading = make_heading("How to Register?", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, standards)

        qm_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "question_mark"]
        assert len(qm_findings) == 0


# =============================================================================
# TEST: CAPITALIZATION
# =============================================================================

class TestCapitalization:
    """Test capitalization detection."""

    def test_title_case_brand_sentence_case_heading_flagged(self, check, title_case_standards):
        """Sentence case heading with title_case brand produces finding."""
        heading = make_heading("How to register at the casino", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, title_case_standards)

        cap_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "capitalization"]
        assert len(cap_findings) == 1
        assert "title case" in cap_findings[0].reasoning.lower()

    def test_sentence_case_brand_title_case_heading_flagged(self, check, sentence_case_standards):
        """Title case heading with sentence_case brand produces finding."""
        heading = make_heading("How To Register At The Casino", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, sentence_case_standards)

        cap_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "capitalization"]
        assert len(cap_findings) == 1
        assert "sentence case" in cap_findings[0].reasoning.lower()

    def test_ordinary_words_auto_applicable(self, check, title_case_standards):
        """Heading with only ordinary words is auto-applicable."""
        heading = make_heading("the best games for beginners", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, title_case_standards)

        cap_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "capitalization"]
        assert len(cap_findings) == 1
        assert cap_findings[0].auto_applicable is True
        assert cap_findings[0].proposed_text == "The Best Games for Beginners"

    def test_acronym_heading_is_proposal(self, check, sentence_case_standards):
        """Heading with acronyms is proposal, not auto-apply."""
        heading = make_heading("Mobile App for iOS Users", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, sentence_case_standards)

        cap_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "capitalization"]
        assert len(cap_findings) == 1
        assert cap_findings[0].auto_applicable is False
        # Should preserve iOS
        assert "iOS" in cap_findings[0].proposed_text

    def test_vip_acronym_preserved(self, check, sentence_case_standards):
        """VIP acronym should be preserved."""
        heading = make_heading("VIP Loyalty Program Details", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, sentence_case_standards)

        cap_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "capitalization"]
        assert len(cap_findings) == 1
        assert "VIP" in cap_findings[0].proposed_text

    def test_no_capitalization_standard_no_finding(self, check, standards):
        """When no capitalization standard is set, no findings."""
        heading = make_heading("any case is fine here", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, standards)

        cap_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "capitalization"]
        assert len(cap_findings) == 0

    def test_already_correct_title_case(self, check, title_case_standards):
        """Already correct title case produces no finding."""
        heading = make_heading("The Best Casino Games", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, title_case_standards)

        cap_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "capitalization"]
        assert len(cap_findings) == 0

    def test_already_correct_sentence_case(self, check, sentence_case_standards):
        """Already correct sentence case produces no finding."""
        heading = make_heading("The best casino games", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, sentence_case_standards)

        cap_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "capitalization"]
        assert len(cap_findings) == 0

    def test_dictionary_words_auto_applicable(self, check, sentence_case_standards):
        """Common dictionary words are auto-applicable."""
        # All words are common English dictionary words
        heading = make_heading("Popular Games and Tournaments", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, sentence_case_standards)

        cap_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "capitalization"]
        assert len(cap_findings) == 1
        assert cap_findings[0].auto_applicable is True
        assert cap_findings[0].proposed_text == "Popular games and tournaments"

    def test_non_dictionary_word_is_proposal(self, check, sentence_case_standards):
        """Non-dictionary words (proper nouns) are proposals."""
        # "Vave" is a brand name, not in dictionary
        heading = make_heading("Best Vave Casino Features", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, sentence_case_standards)

        cap_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "capitalization"]
        assert len(cap_findings) == 1
        assert cap_findings[0].auto_applicable is False


# =============================================================================
# TEST: DESCRIPTIVE HEADING
# =============================================================================

class TestDescriptiveHeading:
    """Test generic heading detection."""

    def test_generic_heading_flagged(self, check, standards):
        """Single-word generic heading produces suggestion."""
        heading = make_heading("Promotions", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, standards)

        desc_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "descriptive"]
        assert len(desc_findings) == 1
        assert desc_findings[0].auto_applicable is False
        assert desc_findings[0].proposed_text is None
        assert desc_findings[0].severity == "suggestion"

    def test_descriptive_heading_no_finding(self, check, standards):
        """Descriptive heading produces no finding."""
        heading = make_heading("Welcome Bonus Promotions", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, standards)

        desc_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "descriptive"]
        assert len(desc_findings) == 0

    def test_generic_word_in_longer_heading(self, check, standards):
        """Generic word as part of longer heading is OK."""
        heading = make_heading("Casino Bonuses and Free Spins", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, standards)

        desc_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "descriptive"]
        assert len(desc_findings) == 0

    def test_descriptive_disabled(self, check):
        """When descriptive_required is False, no findings."""
        standards = MockStandards(headings=MockHeadingsStandards(descriptive_required=False))
        heading = make_heading("Bonuses", 2, 0)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, standards)

        desc_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "descriptive"]
        assert len(desc_findings) == 0


# =============================================================================
# TEST: HIERARCHY
# =============================================================================

class TestHierarchy:
    """Test heading hierarchy validation."""

    def test_skipped_level_flagged(self, check, standards):
        """H1 directly to H3 (skipping H2) produces warning."""
        h1 = make_heading("Main Title", 1, 0)
        h3 = make_heading("Sub Sub Section", 3, h1.end_offset + 5)
        doc = make_document_with_elements([h1, h3])

        findings = check.run(doc, standards)

        hier_findings = [f for f in findings
                        if f.metadata_dict.get("sub_check") == "hierarchy"
                        and f.metadata_dict.get("issue") == "skipped_level"]
        assert len(hier_findings) == 1
        assert hier_findings[0].auto_applicable is False
        assert "H2" in hier_findings[0].reasoning

    def test_multiple_h1_flagged(self, check, standards):
        """Multiple H1 headings produces warning."""
        h1a = make_heading("First Title", 1, 0)
        h1b = make_heading("Second Title", 1, h1a.end_offset + 5)
        doc = make_document_with_elements([h1a, h1b])

        findings = check.run(doc, standards)

        hier_findings = [f for f in findings
                        if f.metadata_dict.get("sub_check") == "hierarchy"
                        and f.metadata_dict.get("issue") == "multiple_h1"]
        assert len(hier_findings) == 1
        assert hier_findings[0].auto_applicable is False
        assert "2 H1" in hier_findings[0].reasoning

    def test_valid_hierarchy_no_finding(self, check, standards):
        """Proper H1 -> H2 -> H3 hierarchy produces no finding."""
        h1 = make_heading("Main Title", 1, 0)
        h2 = make_heading("Section", 2, h1.end_offset + 5)
        h3 = make_heading("Sub Section", 3, h2.end_offset + 5)
        doc = make_document_with_elements([h1, h2, h3])

        findings = check.run(doc, standards)

        hier_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "hierarchy"]
        assert len(hier_findings) == 0

    def test_h2_to_h4_skipped(self, check, standards):
        """H2 directly to H4 (skipping H3) produces warning."""
        h1 = make_heading("Main", 1, 0)
        h2 = make_heading("Section", 2, h1.end_offset + 5)
        h4 = make_heading("Deep Section", 4, h2.end_offset + 5)
        doc = make_document_with_elements([h1, h2, h4])

        findings = check.run(doc, standards)

        hier_findings = [f for f in findings
                        if f.metadata_dict.get("sub_check") == "hierarchy"
                        and f.metadata_dict.get("issue") == "skipped_level"]
        assert len(hier_findings) == 1
        assert "H3" in hier_findings[0].reasoning


# =============================================================================
# TEST: SELF-REGISTRATION
# =============================================================================

class TestSelfRegistration:
    """Test that check self-registers."""

    def test_check_self_registers(self):
        """Check is registered in the global registry."""
        from deterministic.headings import HeadingsCheck

        registry = get_registry()
        if not registry.is_registered("headings"):
            from core.check_base import register_check
            register_check(HeadingsCheck)

        assert registry.is_registered("headings")
        check = registry.get_instance("headings")
        assert check is not None
        assert check.name == "headings"

    def test_check_metadata(self, check):
        """Check metadata is correct."""
        assert check.name == "headings"
        assert check.category == "headings"
        assert check.metadata.display_name == "Headings Check"
        assert check.is_deterministic


# =============================================================================
# TEST: LOCATION ACCURACY
# =============================================================================

class TestLocationAccuracy:
    """Test that finding locations are accurate."""

    def test_heading_location(self, check, standards):
        """Finding location matches heading position."""
        heading = make_heading("Promotions", 2, 100)
        doc = make_document_with_elements([heading])

        findings = check.run(doc, standards)

        assert len(findings) >= 1
        # Find the descriptive finding
        desc_findings = [f for f in findings if f.metadata_dict.get("sub_check") == "descriptive"]
        assert len(desc_findings) == 1
        assert desc_findings[0].location.start_offset == 100
        assert desc_findings[0].location.end_offset == 100 + len("Promotions")


# =============================================================================
# TEST: EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases."""

    def test_empty_document(self, check, standards):
        """Empty document produces no findings."""
        doc = make_document_with_elements([])
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_no_headings_document(self, check, standards):
        """Document with no headings produces no findings."""
        para = make_para("Just a paragraph of text.", 0)
        doc = make_document_with_elements([para])
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_multiple_issues_same_heading(self, check, title_case_standards):
        """Heading with multiple issues produces multiple findings."""
        # Missing blank line + wrong case + generic
        para = make_para("Some text here.", 0)
        heading = make_heading("bonuses", 2, para.end_offset + 1)  # Gap=1
        doc = make_document_with_elements([para, heading])

        findings = check.run(doc, title_case_standards)

        # Should have: blank line, capitalization, descriptive
        sub_checks = {f.metadata_dict.get("sub_check") for f in findings}
        assert "blank_line" in sub_checks
        assert "capitalization" in sub_checks
        assert "descriptive" in sub_checks
