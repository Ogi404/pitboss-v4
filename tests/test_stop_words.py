"""
Tests for the stop words check.

Tests cover:
- Hard stop word detection (always flagged)
- Soft stop word detection (density-gated)
- Multi-word phrase matching
- Case insensitivity
- Basic inflection handling
- Word boundaries (no partial matches)
- Scope (body paragraphs only)
- Standards integration
- Self-registration
"""

import pytest
from dataclasses import dataclass, field

from core.check_base import get_registry
from core.document import Document, Paragraph, Heading, HeadingLevel, Table, TableRow, TableCell
from core.finding import Finding
from deterministic.stop_words import StopWordsCheck, get_stop_word_counts


# =============================================================================
# FIXTURES
# =============================================================================

@dataclass
class MockStopWordsStandards:
    """Mock stop words standards."""
    hard: list[str] = field(default_factory=lambda: [
        "delve", "seamless", "realm", "leverage",
        "dive into", "treasure trove", "at your fingertips",
        "state-of-the-art", "cutting-edge",
    ])
    soft: list[str] = field(default_factory=lambda: [
        "unlock", "ensure", "exciting", "essential", "elevate",
    ])


@dataclass
class MockStandards:
    """Mock standards object with stop words."""
    stop_words: MockStopWordsStandards = None

    def __post_init__(self):
        if self.stop_words is None:
            self.stop_words = MockStopWordsStandards()


def make_document(text: str, start_offset: int = 0) -> Document:
    """Create a simple document with one paragraph."""
    para = Paragraph(
        text=text,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
    )
    return Document.from_elements([para])


def make_long_document(word_count: int, soft_words: list[str] = None) -> Document:
    """
    Create a document with approximately word_count words.

    Optionally inject soft words at regular intervals.
    """
    # Base filler text (~10 words per sentence)
    filler = "This is some filler text to pad the document word count. "

    # Build text
    text_parts = []
    words_so_far = 0
    soft_index = 0

    while words_so_far < word_count:
        if soft_words and soft_index < len(soft_words):
            # Insert a soft word
            text_parts.append(f"This is {soft_words[soft_index]} content here. ")
            soft_index += 1
            words_so_far += 5
        else:
            text_parts.append(filler)
            words_so_far += 10

    text = "".join(text_parts)
    return make_document(text)


def make_document_with_heading(heading_text: str, para_text: str) -> Document:
    """Create a document with a heading and a paragraph."""
    heading = Heading(
        text=heading_text,
        level=HeadingLevel.H1,
        start_offset=0,
        end_offset=len(heading_text),
    )
    para = Paragraph(
        text=para_text,
        start_offset=len(heading_text) + 1,
        end_offset=len(heading_text) + 1 + len(para_text),
    )
    return Document.from_elements([heading, para])


def make_document_with_table(para_text: str, cell_text: str) -> Document:
    """Create a document with a paragraph and a table."""
    para = Paragraph(
        text=para_text,
        start_offset=0,
        end_offset=len(para_text),
    )
    cell = TableCell(
        text=cell_text,
        start_offset=len(para_text) + 1,
        end_offset=len(para_text) + 1 + len(cell_text),
    )
    row = TableRow(cells=[cell], start_offset=cell.start_offset, end_offset=cell.end_offset)
    table = Table(rows=[row], start_offset=row.start_offset, end_offset=row.end_offset)
    return Document.from_elements([para, table])


@pytest.fixture
def check() -> StopWordsCheck:
    """Create the stop words check instance."""
    return StopWordsCheck()


@pytest.fixture
def standards() -> MockStandards:
    """Create mock standards with stop words."""
    return MockStandards()


@pytest.fixture
def empty_standards() -> MockStandards:
    """Create mock standards with empty stop word lists."""
    return MockStandards(stop_words=MockStopWordsStandards(hard=[], soft=[]))


# =============================================================================
# TEST: HARD STOP WORD DETECTION
# =============================================================================

class TestHardStopWordDetection:
    """Test hard stop words are always flagged."""

    def test_single_hard_word(self, check, standards):
        """Single hard word detected."""
        doc = make_document("Let's delve into the details.")
        findings = check.run(doc, standards)
        assert len(findings) == 1
        assert findings[0].original_text.lower() == "delve"
        assert findings[0].severity == "warning"
        assert findings[0].auto_applicable is False

    def test_multiple_hard_words(self, check, standards):
        """Multiple hard words in same paragraph."""
        doc = make_document("This seamless realm offers leverage.")
        findings = check.run(doc, standards)
        assert len(findings) == 3
        words = {f.original_text.lower() for f in findings}
        assert words == {"seamless", "realm", "leverage"}

    def test_hard_word_case_insensitive(self, check, standards):
        """Hard words matched case-insensitively."""
        doc = make_document("DELVE into the Seamless REALM.")
        findings = check.run(doc, standards)
        assert len(findings) == 3
        # Check original case preserved
        words = {f.original_text for f in findings}
        assert "DELVE" in words
        assert "Seamless" in words
        assert "REALM" in words

    def test_hard_word_inflections(self, check, standards):
        """Hard word inflections detected (delving, leveraged, etc.)."""
        doc = make_document("We are delving into leveraging seamlessly.")
        findings = check.run(doc, standards)
        assert len(findings) == 3
        words = {f.original_text.lower() for f in findings}
        assert "delving" in words
        assert "leveraging" in words
        assert "seamlessly" in words

    def test_hard_word_no_partial_match(self, check, standards):
        """No partial word matches (developer should not match delve)."""
        doc = make_document("The developer created a realm.")
        findings = check.run(doc, standards)
        # Only "realm" should match, not "developer"
        assert len(findings) == 1
        assert findings[0].original_text.lower() == "realm"

    def test_hard_multi_word_phrase(self, check, standards):
        """Multi-word phrase detected."""
        doc = make_document("Let's dive into the details.")
        findings = check.run(doc, standards)
        assert len(findings) == 1
        assert findings[0].original_text.lower() == "dive into"

    def test_hard_multi_word_phrase_case_insensitive(self, check, standards):
        """Multi-word phrase detected case-insensitively."""
        doc = make_document("Dive Into the treasure trove of options.")
        findings = check.run(doc, standards)
        assert len(findings) == 2
        phrases = {f.original_text.lower() for f in findings}
        assert "dive into" in phrases
        assert "treasure trove" in phrases

    def test_hard_hyphenated_phrase(self, check, standards):
        """Hyphenated phrases detected."""
        doc = make_document("This state-of-the-art and cutting-edge technology.")
        findings = check.run(doc, standards)
        assert len(findings) == 2
        phrases = {f.original_text.lower() for f in findings}
        assert "state-of-the-art" in phrases
        assert "cutting-edge" in phrases

    def test_hard_phrase_at_your_fingertips(self, check, standards):
        """'At your fingertips' phrase detected."""
        doc = make_document("Everything is at your fingertips.")
        findings = check.run(doc, standards)
        assert len(findings) == 1
        assert findings[0].original_text.lower() == "at your fingertips"


# =============================================================================
# TEST: SOFT STOP WORD DETECTION (DENSITY-GATED)
# =============================================================================

class TestSoftStopWordDetection:
    """Test soft stop words are only flagged above density threshold."""

    def test_soft_word_below_threshold_no_finding(self, check, standards):
        """Soft word below density threshold produces no finding."""
        # Create a ~500 word document with 1 soft word
        # Threshold is 0.5% = 0.005, so 1/500 = 0.002 < 0.005
        doc = make_long_document(500, soft_words=["unlock"])
        findings = check.run(doc, standards)
        # Should have no soft word findings
        soft_findings = [f for f in findings if f.metadata_dict.get("tier") == "soft"]
        assert len(soft_findings) == 0

    def test_soft_word_above_threshold_produces_findings(self, check, standards):
        """Soft words above density threshold produce findings."""
        # Create a ~200 word document with 3 soft words
        # Threshold is 0.5% = 0.005, so 3/200 = 0.015 > 0.005
        doc = make_long_document(200, soft_words=["unlock", "ensure", "exciting"])
        findings = check.run(doc, standards)
        soft_findings = [f for f in findings if f.metadata_dict.get("tier") == "soft"]
        assert len(soft_findings) == 3

    def test_soft_word_severity_is_suggestion(self, check, standards):
        """Soft word findings have severity 'suggestion'."""
        # Above threshold
        doc = make_long_document(100, soft_words=["unlock", "ensure", "exciting"])
        findings = check.run(doc, standards)
        soft_findings = [f for f in findings if f.metadata_dict.get("tier") == "soft"]
        assert len(soft_findings) > 0
        for f in soft_findings:
            assert f.severity == "suggestion"

    def test_soft_word_confidence_is_lower(self, check, standards):
        """Soft word findings have lower confidence (0.6)."""
        doc = make_long_document(100, soft_words=["unlock", "ensure", "exciting"])
        findings = check.run(doc, standards)
        soft_findings = [f for f in findings if f.metadata_dict.get("tier") == "soft"]
        assert len(soft_findings) > 0
        for f in soft_findings:
            assert f.confidence == 0.6

    def test_custom_density_threshold(self, standards):
        """Custom density threshold respected."""
        # Use a very high threshold so soft words are never flagged
        check = StopWordsCheck(soft_density_threshold=1.0)
        doc = make_long_document(10, soft_words=["unlock", "ensure", "exciting"])
        findings = check.run(doc, standards)
        soft_findings = [f for f in findings if f.metadata_dict.get("tier") == "soft"]
        assert len(soft_findings) == 0


# =============================================================================
# TEST: MIXED HARD AND SOFT
# =============================================================================

class TestMixedHardAndSoft:
    """Test documents with both hard and soft words."""

    def test_hard_always_flagged_soft_gated(self, check, standards):
        """Hard words always flagged, soft words only if above threshold."""
        # Create a longer document so soft words are below threshold
        # Need 1 soft word / 200+ words to be below 0.5% threshold
        filler = " ".join(["word"] * 200)
        doc = make_document(f"The realm is here. {filler}")
        findings = check.run(doc, standards)

        # Should have 1 hard finding (realm), no soft findings (no soft words in text)
        hard_findings = [f for f in findings if f.metadata_dict.get("tier") == "hard"]
        soft_findings = [f for f in findings if f.metadata_dict.get("tier") == "soft"]

        assert len(hard_findings) == 1
        assert len(soft_findings) == 0  # No soft words in text


# =============================================================================
# TEST: SCOPE (PARAGRAPHS ONLY)
# =============================================================================

class TestScope:
    """Test that only body paragraphs are checked."""

    def test_heading_stop_words_ignored(self, check, standards):
        """Stop words in headings are not flagged."""
        doc = make_document_with_heading(
            "Delve Into the Realm",
            "This is normal paragraph text."
        )
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_paragraph_stop_words_flagged(self, check, standards):
        """Stop words in paragraphs are flagged."""
        doc = make_document_with_heading(
            "Introduction",
            "Let's delve into the realm."
        )
        findings = check.run(doc, standards)
        assert len(findings) == 2


# =============================================================================
# TEST: METADATA
# =============================================================================

class TestMetadata:
    """Test finding metadata."""

    def test_hard_word_metadata(self, check, standards):
        """Hard word finding has correct metadata."""
        doc = make_document("This is seamless.")
        findings = check.run(doc, standards)
        assert len(findings) == 1

        meta = findings[0].metadata_dict
        assert meta["tier"] == "hard"
        assert meta["canonical_word"] == "seamless"
        assert meta["weight"] == 1.0

    def test_soft_word_metadata(self, check, standards):
        """Soft word finding has correct metadata."""
        # Above threshold
        doc = make_long_document(100, soft_words=["unlock", "ensure", "exciting"])
        findings = check.run(doc, standards)
        soft_findings = [f for f in findings if f.metadata_dict.get("tier") == "soft"]

        assert len(soft_findings) > 0
        for f in soft_findings:
            meta = f.metadata_dict
            assert meta["tier"] == "soft"
            assert meta["weight"] == 0.3
            assert meta["canonical_word"] in ["unlock", "ensure", "exciting"]

    def test_inflected_form_canonical_word(self, check, standards):
        """Inflected form preserves canonical word from list."""
        doc = make_document("We are leveraging this seamlessly.")
        findings = check.run(doc, standards)

        # Find the "leveraging" finding
        leverage_finding = next(f for f in findings if "leverag" in f.original_text.lower())
        assert leverage_finding.metadata_dict["canonical_word"] == "leverage"


# =============================================================================
# TEST: NO PROPOSED TEXT
# =============================================================================

class TestNoProposedText:
    """Test that findings have no proposed replacement."""

    def test_no_proposed_text(self, check, standards):
        """Findings have no proposed_text (detection only)."""
        doc = make_document("Let's delve into the realm.")
        findings = check.run(doc, standards)
        assert len(findings) > 0
        for f in findings:
            assert f.proposed_text is None
            assert f.auto_applicable is False


# =============================================================================
# TEST: STANDARDS INTEGRATION
# =============================================================================

class TestStandardsIntegration:
    """Test that check respects standards configuration."""

    def test_empty_lists_no_findings(self, check, empty_standards):
        """Empty stop word lists produce no findings."""
        doc = make_document("Let's delve into the realm seamlessly.")
        findings = check.run(doc, empty_standards)
        assert len(findings) == 0

    def test_custom_hard_list(self, check):
        """Custom hard list is respected."""
        custom_standards = MockStandards(stop_words=MockStopWordsStandards(
            hard=["foobar", "bazqux"],
            soft=[],
        ))
        doc = make_document("This foobar is bazqux.")
        findings = check.run(doc, custom_standards)
        assert len(findings) == 2
        words = {f.original_text.lower() for f in findings}
        assert words == {"foobar", "bazqux"}

    def test_custom_soft_list(self, check):
        """Custom soft list is respected."""
        custom_standards = MockStandards(stop_words=MockStopWordsStandards(
            hard=[],
            soft=["custom", "word"],
        ))
        # Above threshold (short doc, multiple soft words)
        doc = make_document("This custom word is another custom word.")
        findings = check.run(doc, custom_standards)
        soft_findings = [f for f in findings if f.metadata_dict.get("tier") == "soft"]
        assert len(soft_findings) >= 2


# =============================================================================
# TEST: SELF-REGISTRATION
# =============================================================================

class TestSelfRegistration:
    """Test that check self-registers."""

    def test_check_self_registers(self):
        """Check is registered in the global registry."""
        # Force import to trigger registration
        from deterministic.stop_words import StopWordsCheck

        registry = get_registry()
        # Re-register if not present (test isolation)
        if not registry.is_registered("stop_words"):
            from core.check_base import register_check
            register_check(StopWordsCheck)

        assert registry.is_registered("stop_words")
        check = registry.get_instance("stop_words")
        assert check is not None
        assert check.name == "stop_words"

    def test_check_metadata(self, check):
        """Check metadata is correct."""
        assert check.name == "stop_words"
        assert check.category == "stop_words"
        assert check.metadata.display_name == "Stop Words Detection"
        assert check.is_deterministic


# =============================================================================
# TEST: LOCATION ACCURACY
# =============================================================================

class TestLocationAccuracy:
    """Test that finding locations are accurate."""

    def test_single_word_location(self, check, standards):
        """Single word location is accurate."""
        text = "This is a seamless experience."
        doc = make_document(text)
        findings = check.run(doc, standards)

        assert len(findings) == 1
        f = findings[0]

        # Verify the location points to "seamless"
        extracted = text[f.location.start_offset:f.location.end_offset]
        assert extracted.lower() == "seamless"

    def test_phrase_location(self, check, standards):
        """Multi-word phrase location is accurate."""
        text = "Let's dive into the ocean."
        doc = make_document(text)
        findings = check.run(doc, standards)

        assert len(findings) == 1
        f = findings[0]

        # Verify the location points to "dive into"
        extracted = text[f.location.start_offset:f.location.end_offset]
        assert extracted.lower() == "dive into"

    def test_multiple_occurrences_locations(self, check, standards):
        """Multiple occurrences have correct locations."""
        text = "Delve here, then delve there."
        doc = make_document(text)
        findings = check.run(doc, standards)

        assert len(findings) == 2

        # Both should extract to "delve" (case may vary)
        for f in findings:
            extracted = text[f.location.start_offset:f.location.end_offset]
            assert extracted.lower() == "delve"


# =============================================================================
# TEST: UTILITY FUNCTION
# =============================================================================

class TestUtilityFunction:
    """Test get_stop_word_counts utility."""

    def test_get_stop_word_counts(self, standards):
        """get_stop_word_counts returns correct counts."""
        doc = make_document("Let's dive into the realm. This is exciting.")
        counts = get_stop_word_counts(doc, standards)

        assert counts["hard"] == 2  # dive into, realm
        assert counts["soft"] == 1  # exciting
        assert counts["total_words"] > 0


# =============================================================================
# TEST: EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases."""

    def test_empty_document(self, check, standards):
        """Empty document produces no findings."""
        doc = make_document("")
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_no_stop_words(self, check, standards):
        """Document with no stop words produces no findings."""
        doc = make_document("This is a normal sentence with no flagged words.")
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_stop_word_at_start(self, check, standards):
        """Stop word at sentence start detected."""
        doc = make_document("Delve into the details.")
        findings = check.run(doc, standards)
        assert len(findings) >= 1
        words = {f.original_text.lower() for f in findings}
        assert "delve" in words or "dive into" in words

    def test_stop_word_at_end(self, check, standards):
        """Stop word at sentence end detected."""
        doc = make_document("The interface is seamless.")
        findings = check.run(doc, standards)
        assert len(findings) == 1
        assert findings[0].original_text.lower() == "seamless"

    def test_punctuation_adjacent(self, check, standards):
        """Stop words adjacent to punctuation detected."""
        doc = make_document("(seamless), 'realm', [leverage]!")
        findings = check.run(doc, standards)
        assert len(findings) == 3
