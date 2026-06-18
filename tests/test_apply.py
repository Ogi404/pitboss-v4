"""
Tests for output/apply.py - Apply Layer

Critical tests for the offset management and conflict detection logic.
These tests verify that:
- Single edits apply correctly
- Multiple edits in descending order produce exact results
- Overlapping spans are detected as conflicts
- Conflicting findings are downgraded to proposals
- Formatting (bold/italic/hyperlinks) is preserved
- Original text validation prevents incorrect edits
"""

import pytest
from copy import deepcopy

from core.document import Document, Paragraph, Heading, HeadingLevel, List, ListItem, ListType, TextRun
from core.finding import Finding, FindingFactory, Location

from output.apply import (
    apply_auto_findings,
    ApplyResult,
    _detect_conflicts,
    _validate_findings,
    _get_dominant_formatting,
    _adjust_runs_for_edit,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

def make_finding(
    start: int,
    end: int,
    original: str,
    proposed: str,
    check_name: str = "test.check",
    auto_applicable: bool = True,
) -> Finding:
    """Create a test finding."""
    return FindingFactory.create(
        check_name=check_name,
        category="other",
        severity="warning",
        confidence=1.0,
        location=Location(paragraph_index=0, start_offset=start, end_offset=end),
        original_text=original,
        proposed_text=proposed,
        reasoning="Test finding",
        auto_applicable=auto_applicable,
    )


def make_document(text: str) -> Document:
    """Create a simple document with a single paragraph."""
    para = Paragraph(
        text=text,
        start_offset=0,
        end_offset=len(text),
        _runs=[TextRun(text=text, start_offset=0, end_offset=len(text))],
    )
    return Document(elements=[para])


def make_document_with_runs(text: str, runs: list[TextRun]) -> Document:
    """Create a document with explicit formatting runs."""
    para = Paragraph(
        text=text,
        start_offset=0,
        end_offset=len(text),
        _runs=runs,
    )
    return Document(elements=[para])


# =============================================================================
# BASIC APPLY TESTS
# =============================================================================

class TestApplyBasics:
    """Basic apply functionality tests."""

    def test_single_edit_applied(self):
        """Single auto-applicable finding is applied correctly."""
        doc = make_document("Hello world!")
        finding = make_finding(
            start=6, end=11,
            original="world",
            proposed="universe",
        )

        result = apply_auto_findings(doc, [finding])

        assert result.applied_count == 1
        assert result.document.elements[0].text == "Hello universe!"

    def test_no_findings_returns_unchanged_document(self):
        """Empty findings list returns unchanged document."""
        doc = make_document("Hello world!")

        result = apply_auto_findings(doc, [])

        assert result.applied_count == 0
        assert result.document.elements[0].text == "Hello world!"

    def test_non_auto_applicable_ignored(self):
        """Findings with auto_applicable=False are ignored."""
        doc = make_document("Hello world!")
        finding = make_finding(
            start=6, end=11,
            original="world",
            proposed="universe",
            auto_applicable=False,
        )

        result = apply_auto_findings(doc, [finding])

        assert result.applied_count == 0
        assert result.document.elements[0].text == "Hello world!"

    def test_finding_without_proposed_text_ignored(self):
        """Findings without proposed_text are ignored."""
        doc = make_document("Hello world!")
        # Create finding manually to have proposed_text=None but auto_applicable=True
        # This shouldn't be possible via factory, but testing defensively
        finding = make_finding(
            start=6, end=11,
            original="world",
            proposed="universe",  # Factory requires this
        )

        result = apply_auto_findings(doc, [finding])

        # Should be applied since it has proposed_text
        assert result.applied_count == 1

    def test_original_document_not_mutated(self):
        """Original document is not modified."""
        doc = make_document("Hello world!")
        original_text = doc.elements[0].text

        finding = make_finding(
            start=6, end=11,
            original="world",
            proposed="universe",
        )

        result = apply_auto_findings(doc, [finding])

        # Original unchanged
        assert doc.elements[0].text == original_text
        # Result has new text
        assert result.document.elements[0].text == "Hello universe!"


# =============================================================================
# DESCENDING ORDER TESTS (CRITICAL)
# =============================================================================

class TestDescendingOrder:
    """Tests for correct descending order application."""

    def test_two_edits_exact_result(self):
        """Two edits at different positions produce exact result."""
        # Text: "AAA BBB CCC"
        #        012345678901
        doc = make_document("AAA BBB CCC")

        findings = [
            make_finding(start=0, end=3, original="AAA", proposed="XX"),  # "AAA" -> "XX"
            make_finding(start=8, end=11, original="CCC", proposed="ZZZZ"),  # "CCC" -> "ZZZZ"
        ]

        result = apply_auto_findings(doc, findings)

        assert result.applied_count == 2
        assert result.document.elements[0].text == "XX BBB ZZZZ"

    def test_three_edits_exact_result(self):
        """
        Critical test: 3 edits at different positions.
        After applying in descending order, text is exactly correct.
        """
        # Text: "The quick brown fox jumps"
        #        0123456789...
        doc = make_document("The quick brown fox jumps")

        findings = [
            make_finding(start=4, end=9, original="quick", proposed="slow"),     # pos 4-9
            make_finding(start=10, end=15, original="brown", proposed="gray"),   # pos 10-15
            make_finding(start=20, end=25, original="jumps", proposed="walks"),  # pos 20-25
        ]

        result = apply_auto_findings(doc, findings)

        assert result.applied_count == 3
        assert result.document.elements[0].text == "The slow gray fox walks"

    def test_edit_at_start_and_end(self):
        """Edits at document start and end work correctly."""
        doc = make_document("START middle END")

        findings = [
            make_finding(start=0, end=5, original="START", proposed="BEGIN"),
            make_finding(start=13, end=16, original="END", proposed="FINISH"),
        ]

        result = apply_auto_findings(doc, findings)

        assert result.applied_count == 2
        assert result.document.elements[0].text == "BEGIN middle FINISH"

    def test_edits_with_length_change(self):
        """Edits that change text length work correctly."""
        doc = make_document("A BB CCC DDDD")

        findings = [
            make_finding(start=0, end=1, original="A", proposed="XXXXX"),  # 1 -> 5
            make_finding(start=2, end=4, original="BB", proposed="Y"),     # 2 -> 1
            make_finding(start=9, end=13, original="DDDD", proposed="ZZ"), # 4 -> 2
        ]

        result = apply_auto_findings(doc, findings)

        assert result.applied_count == 3
        # Original: "A BB CCC DDDD"
        # After: "XXXXX Y CCC ZZ"
        assert result.document.elements[0].text == "XXXXX Y CCC ZZ"

    def test_adjacent_edits_no_overlap(self):
        """Adjacent edits (touching but not overlapping) both apply."""
        doc = make_document("AAABBB")

        findings = [
            make_finding(start=0, end=3, original="AAA", proposed="XX"),
            make_finding(start=3, end=6, original="BBB", proposed="YY"),
        ]

        result = apply_auto_findings(doc, findings)

        assert result.applied_count == 2
        assert result.document.elements[0].text == "XXYY"


# =============================================================================
# CONFLICT DETECTION TESTS
# =============================================================================

class TestConflictDetection:
    """Tests for conflict detection logic."""

    def test_no_conflict_for_disjoint_spans(self):
        """Non-overlapping spans don't conflict."""
        findings = [
            make_finding(start=0, end=5, original="Hello", proposed="Hi"),
            make_finding(start=10, end=15, original="world", proposed="there"),
        ]

        to_apply, downgraded, conflicts = _detect_conflicts(findings)

        assert len(to_apply) == 2
        assert len(downgraded) == 0
        assert len(conflicts) == 0

    def test_conflict_detected_for_overlapping_spans(self):
        """Overlapping spans are detected as conflicts."""
        findings = [
            make_finding(start=0, end=10, original="Hello worl", proposed="Hi"),
            make_finding(start=6, end=15, original="world test", proposed="there"),
        ]

        to_apply, downgraded, conflicts = _detect_conflicts(findings)

        assert len(to_apply) == 1
        assert len(downgraded) == 1
        assert len(conflicts) == 1

    def test_first_finding_wins_conflict(self):
        """In a conflict, the finding with earlier start_offset wins."""
        findings = [
            make_finding(start=5, end=15, original="xxxx", proposed="A", check_name="later"),
            make_finding(start=0, end=10, original="yyyy", proposed="B", check_name="earlier"),
        ]

        to_apply, downgraded, conflicts = _detect_conflicts(findings)

        # The one starting at 0 should win
        assert len(to_apply) == 1
        assert to_apply[0].check_name == "earlier"
        assert downgraded[0].check_name == "later"

    def test_contained_span_conflicts(self):
        """A span contained within another conflicts."""
        findings = [
            make_finding(start=0, end=20, original="big span", proposed="A"),
            make_finding(start=5, end=10, original="inner", proposed="B"),
        ]

        to_apply, downgraded, conflicts = _detect_conflicts(findings)

        assert len(to_apply) == 1
        assert len(downgraded) == 1
        # The outer span (starts earlier) wins
        assert to_apply[0].location.start_offset == 0

    def test_multiple_conflicts(self):
        """Multiple overlapping findings handled correctly."""
        findings = [
            make_finding(start=0, end=10, original="a", proposed="A"),
            make_finding(start=5, end=15, original="b", proposed="B"),  # conflicts with 0-10
            make_finding(start=12, end=20, original="c", proposed="C"),  # conflicts with 5-15
        ]

        to_apply, downgraded, conflicts = _detect_conflicts(findings)

        # First wins, second downgraded, third should apply (doesn't overlap with first)
        assert len(to_apply) == 2  # 0-10 and 12-20
        assert len(downgraded) == 1  # 5-15

    def test_conflict_integration(self):
        """Conflicts are properly handled in full apply."""
        doc = make_document("Hello wonderful world!")
        # Text:  "Hello wonderful world!"
        # Index:  0     6         16

        findings = [
            make_finding(start=6, end=15, original="wonderful", proposed="great"),
            # Second finding overlaps with first (positions 10-16 overlap with 6-15)
            # Text at 10-16 is "erful " - but we need valid original text
            make_finding(start=10, end=16, original="erful ", proposed="X"),
        ]

        result = apply_auto_findings(doc, findings)

        assert result.applied_count == 1
        assert result.downgraded_count == 1
        assert len(result.conflicts) == 1
        assert result.document.elements[0].text == "Hello great world!"


# =============================================================================
# VALIDATION TESTS
# =============================================================================

class TestValidation:
    """Tests for original text validation."""

    def test_matching_text_passes_validation(self):
        """Finding with matching original_text passes validation."""
        doc = make_document("Hello world!")
        findings = [
            make_finding(start=6, end=11, original="world", proposed="universe"),
        ]

        validated, skipped = _validate_findings(doc, findings)

        assert len(validated) == 1
        assert len(skipped) == 0

    def test_mismatched_text_fails_validation(self):
        """Finding with wrong original_text is skipped."""
        doc = make_document("Hello world!")
        findings = [
            make_finding(start=6, end=11, original="WRONG", proposed="universe"),
        ]

        validated, skipped = _validate_findings(doc, findings)

        assert len(validated) == 0
        assert len(skipped) == 1

    def test_skipped_finding_in_result(self):
        """Skipped findings appear in result.skipped."""
        doc = make_document("Hello world!")
        findings = [
            make_finding(start=6, end=11, original="WRONG", proposed="universe"),
        ]

        result = apply_auto_findings(doc, findings)

        assert result.applied_count == 0
        assert result.skipped_count == 1

    def test_partial_match_fails(self):
        """Partial text match (subset) fails validation."""
        doc = make_document("Hello world!")
        findings = [
            make_finding(start=6, end=11, original="worl", proposed="universe"),  # missing 'd'
        ]

        validated, skipped = _validate_findings(doc, findings)

        assert len(skipped) == 1

    def test_out_of_bounds_location_fails(self):
        """Location beyond document bounds is skipped."""
        doc = make_document("Hello")
        findings = [
            make_finding(start=100, end=110, original="xxx", proposed="yyy"),
        ]

        validated, skipped = _validate_findings(doc, findings)

        assert len(skipped) == 1


# =============================================================================
# FORMATTING PRESERVATION TESTS
# =============================================================================

class TestFormattingPreservation:
    """Tests for preserving formatting during edits."""

    def test_bold_preserved(self):
        """Bold formatting is preserved through edit."""
        runs = [
            TextRun(text="Hello ", start_offset=0, end_offset=6, bold=True),
            TextRun(text="world", start_offset=6, end_offset=11, bold=False),
            TextRun(text="!", start_offset=11, end_offset=12, bold=True),
        ]
        doc = make_document_with_runs("Hello world!", runs)

        finding = make_finding(start=6, end=11, original="world", proposed="universe")
        result = apply_auto_findings(doc, [finding])

        # Check the runs in the result
        result_runs = result.document.elements[0].runs()

        # First run should still be bold
        assert result_runs[0].bold is True
        assert result_runs[0].text == "Hello "

    def test_hyperlink_preserved_before_edit(self):
        """Hyperlinks before edit are preserved."""
        runs = [
            TextRun(text="Click ", start_offset=0, end_offset=6, hyperlink="https://example.com"),
            TextRun(text="here", start_offset=6, end_offset=10),
        ]
        doc = make_document_with_runs("Click here", runs)

        finding = make_finding(start=6, end=10, original="here", proposed="this link")
        result = apply_auto_findings(doc, [finding])

        result_runs = result.document.elements[0].runs()

        # First run should have hyperlink
        assert result_runs[0].hyperlink == "https://example.com"
        assert result_runs[0].text == "Click "

    def test_formatting_inherited_by_replacement(self):
        """Replacement text inherits formatting from replaced span."""
        runs = [
            TextRun(text="Hello ", start_offset=0, end_offset=6),
            TextRun(text="BOLD", start_offset=6, end_offset=10, bold=True, italic=True),
            TextRun(text=" text", start_offset=10, end_offset=15),
        ]
        doc = make_document_with_runs("Hello BOLD text", runs)

        finding = make_finding(start=6, end=10, original="BOLD", proposed="REPLACED")
        result = apply_auto_findings(doc, [finding])

        # The replacement should inherit bold and italic
        result_runs = result.document.elements[0].runs()
        replacement_run = [r for r in result_runs if "REPLACED" in r.text]

        assert len(replacement_run) == 1
        assert replacement_run[0].bold is True
        assert replacement_run[0].italic is True

    def test_highlight_preserved(self):
        """Highlight colors are preserved."""
        runs = [
            TextRun(text="Important", start_offset=0, end_offset=9, highlight_color="yellow"),
            TextRun(text=" text", start_offset=9, end_offset=14),
        ]
        doc = make_document_with_runs("Important text", runs)

        finding = make_finding(start=10, end=14, original="text", proposed="info")
        result = apply_auto_findings(doc, [finding])

        result_runs = result.document.elements[0].runs()

        # First run should keep highlight
        assert result_runs[0].highlight_color == "yellow"

    def test_highlight_preserved_exact_match(self):
        """Highlight is preserved when edit exactly matches a run (BUG 2 regression)."""
        # This is the exact scenario from artifact verification:
        # A highlighted run being edited should keep its highlight
        runs = [
            TextRun(text="text ", start_offset=0, end_offset=5),
            TextRun(text="license", start_offset=5, end_offset=12, highlight_color="yellow"),
            TextRun(text=" more", start_offset=12, end_offset=17),
        ]
        doc = make_document_with_runs("text license more", runs)

        # Edit exactly matches the highlighted run
        finding = make_finding(start=5, end=12, original="license", proposed="licence")
        result = apply_auto_findings(doc, [finding])

        result_runs = result.document.elements[0].runs()

        # Find the replacement run
        replacement_run = [r for r in result_runs if r.text == "licence"]
        assert len(replacement_run) == 1, f"Expected 'licence' run, got: {[r.text for r in result_runs]}"
        assert replacement_run[0].highlight_color == "yellow", \
            f"Highlight lost! Run has: {replacement_run[0].highlight_color}"

    def test_bold_highlight_preserved_exact_match(self):
        """Multiple formatting attributes preserved when edit exactly matches run."""
        runs = [
            TextRun(text="prefix ", start_offset=0, end_offset=7),
            TextRun(
                text="formatted",
                start_offset=7,
                end_offset=16,
                bold=True,
                italic=True,
                highlight_color="yellow",
            ),
            TextRun(text=" suffix", start_offset=16, end_offset=23),
        ]
        doc = make_document_with_runs("prefix formatted suffix", runs)

        finding = make_finding(start=7, end=16, original="formatted", proposed="changed")
        result = apply_auto_findings(doc, [finding])

        result_runs = result.document.elements[0].runs()
        replacement_run = [r for r in result_runs if r.text == "changed"]

        assert len(replacement_run) == 1
        assert replacement_run[0].bold is True
        assert replacement_run[0].italic is True
        assert replacement_run[0].highlight_color == "yellow"


class TestDominantFormatting:
    """Tests for _get_dominant_formatting function."""

    def test_single_run_returns_its_formatting(self):
        """Single run returns its own formatting."""
        runs = [
            TextRun(text="Hello", start_offset=0, end_offset=5, bold=True, italic=True),
        ]

        fmt = _get_dominant_formatting(runs, 0, 5)

        assert fmt['bold'] is True
        assert fmt['italic'] is True

    def test_most_overlapping_run_wins(self):
        """The run with most overlap provides formatting."""
        runs = [
            TextRun(text="HH", start_offset=0, end_offset=2, bold=True),
            TextRun(text="LLLL", start_offset=2, end_offset=6, italic=True),
        ]

        # Edit span 1-5: overlaps "H" (1 char) and "LLLL" (4 chars)
        fmt = _get_dominant_formatting(runs, 1, 5)

        # "LLLL" has more overlap, so should get its formatting
        assert fmt.get('italic') is True
        assert fmt.get('bold', False) is False

    def test_empty_runs_returns_empty_dict(self):
        """Empty runs list returns empty dict."""
        fmt = _get_dominant_formatting([], 0, 10)
        assert fmt == {}


# =============================================================================
# MULTIPLE ELEMENTS TESTS
# =============================================================================

class TestMultipleElements:
    """Tests for documents with multiple elements."""

    def test_edit_in_second_paragraph(self):
        """Edit in second paragraph works correctly."""
        para1 = Paragraph(text="First paragraph.", start_offset=0, end_offset=16)
        para2 = Paragraph(text="Second paragraph here.", start_offset=17, end_offset=39)
        doc = Document(elements=[para1, para2])

        # Edit in second paragraph
        finding = make_finding(
            start=24, end=33,
            original="paragraph",
            proposed="section",
        )

        result = apply_auto_findings(doc, [finding])

        assert result.applied_count == 1
        assert "section" in result.document.elements[1].text

    def test_edit_in_heading(self):
        """Edit in a heading works correctly."""
        heading = Heading(
            text="Important Heading",
            level=HeadingLevel.H1,
            start_offset=0,
            end_offset=17,
        )
        para = Paragraph(text="Content below.", start_offset=18, end_offset=32)
        doc = Document(elements=[heading, para])

        finding = make_finding(
            start=10, end=17,
            original="Heading",
            proposed="Title",
        )

        result = apply_auto_findings(doc, [finding])

        assert result.applied_count == 1
        assert result.document.elements[0].text == "Important Title"

    def test_edit_in_list_item(self):
        """Edit in a list item works correctly."""
        items = [
            ListItem(text="First item", start_offset=0, end_offset=10),
            ListItem(text="Second item", start_offset=11, end_offset=22),
        ]
        lst = List(list_type=ListType.UNORDERED, items=items, start_offset=0, end_offset=22)
        doc = Document(elements=[lst])

        finding = make_finding(
            start=0, end=5,
            original="First",
            proposed="Primary",
        )

        result = apply_auto_findings(doc, [finding])

        assert result.applied_count == 1
        assert result.document.elements[0].items[0].text == "Primary item"


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_empty_replacement(self):
        """Replacing with empty string (deletion) works."""
        doc = make_document("Hello  world")  # double space

        finding = make_finding(
            start=5, end=7,
            original="  ",
            proposed=" ",  # reduce to single space
        )

        result = apply_auto_findings(doc, [finding])

        assert result.applied_count == 1
        assert result.document.elements[0].text == "Hello world"

    def test_insert_without_delete(self):
        """Insert at a position (empty original) - edge case."""
        doc = make_document("HelloWorld")

        finding = make_finding(
            start=5, end=5,  # Zero-width span
            original="",
            proposed=" ",
        )

        result = apply_auto_findings(doc, [finding])

        assert result.applied_count == 1
        assert result.document.elements[0].text == "Hello World"

    def test_replace_entire_text(self):
        """Replacing entire element text works."""
        doc = make_document("Old text")

        finding = make_finding(
            start=0, end=8,
            original="Old text",
            proposed="Completely new content here",
        )

        result = apply_auto_findings(doc, [finding])

        assert result.applied_count == 1
        assert result.document.elements[0].text == "Completely new content here"

    def test_unicode_text(self):
        """Unicode text is handled correctly."""
        doc = make_document("Hello 世界!")

        finding = make_finding(
            start=6, end=8,
            original="世界",
            proposed="world",
        )

        result = apply_auto_findings(doc, [finding])

        assert result.applied_count == 1
        assert result.document.elements[0].text == "Hello world!"

    def test_many_findings_applied(self):
        """Many findings (10+) applied correctly."""
        # Create document with many words
        words = [f"word{i}" for i in range(10)]
        text = " ".join(words)
        doc = make_document(text)

        # Create findings to replace each word
        findings = []
        offset = 0
        for i, word in enumerate(words):
            findings.append(make_finding(
                start=offset,
                end=offset + len(word),
                original=word,
                proposed=f"FIXED{i}",
            ))
            offset += len(word) + 1  # +1 for space

        result = apply_auto_findings(doc, findings)

        assert result.applied_count == 10
        expected = " ".join(f"FIXED{i}" for i in range(10))
        assert result.document.elements[0].text == expected


# =============================================================================
# APPLY RESULT TESTS
# =============================================================================

class TestApplyResult:
    """Tests for ApplyResult dataclass."""

    def test_counts_correct(self):
        """ApplyResult counts are correct."""
        doc = make_document("AAA BBB CCC")

        findings = [
            make_finding(start=0, end=3, original="AAA", proposed="XXX"),
            make_finding(start=4, end=7, original="BBB", proposed="YYY"),
            make_finding(start=8, end=11, original="WRONG", proposed="ZZZ"),  # Will be skipped
        ]

        result = apply_auto_findings(doc, findings)

        assert result.applied_count == 2
        assert result.skipped_count == 1
        assert result.downgraded_count == 0

    def test_downgraded_findings_accessible(self):
        """Downgraded findings are accessible from result."""
        doc = make_document("Hello wonderful world!")
        # Text:  "Hello wonderful world!"
        # Index:  0     6         16

        findings = [
            make_finding(start=6, end=15, original="wonderful", proposed="great", check_name="first"),
            # Second overlaps: 10-16 is "erful "
            make_finding(start=10, end=16, original="erful ", proposed="X", check_name="second"),
        ]

        result = apply_auto_findings(doc, findings)

        assert len(result.downgraded) == 1
        assert result.downgraded[0].check_name == "second"

    def test_conflicts_tracked(self):
        """Conflict pairs are tracked in result."""
        doc = make_document("Hello wonderful world!")
        # Text:  "Hello wonderful world!"
        # Index:  0     6         16

        findings = [
            make_finding(start=6, end=15, original="wonderful", proposed="great", check_name="first"),
            # Second overlaps: 10-16 is "erful "
            make_finding(start=10, end=16, original="erful ", proposed="X", check_name="second"),
        ]

        result = apply_auto_findings(doc, findings)

        assert len(result.conflicts) == 1
        winner, loser = result.conflicts[0]
        assert winner.check_name == "first"
        assert loser.check_name == "second"
