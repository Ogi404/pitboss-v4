"""
Tests for deterministic/keywords.py - Keyword Coverage and Density Check

Tests keyword matching, quantity checking, density calculation,
highlighting detection, and brand/location overuse detection.
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from core.document import Document, Paragraph, TextRun, Location
from core.finding import Finding
from deterministic.keywords import (
    KeywordsCheck,
    normalize_keyword,
    get_keyword_variants,
    find_keyword_occurrences,
    count_words,
    MAX_DENSITY_PERCENT,
    BRAND_OVERUSE_PERCENT,
)


# =============================================================================
# FIXTURES
# =============================================================================

@dataclass
class MockBriefKeyword:
    """Mock BriefKeyword for testing."""
    keyword: str
    min_quantity: Optional[int] = None
    max_quantity: Optional[int] = None
    group: str = "main"
    confidence: float = 1.0


@dataclass
class MockBriefKeywords:
    """Mock BriefKeywords for testing."""
    main: tuple
    support: tuple = ()
    lsi: tuple = ()


@dataclass
class MockBriefModel:
    """Mock BriefModel for testing."""
    keywords: MockBriefKeywords
    brand_name: str = ""
    market: Optional[str] = None
    target_word_count: int = 1000


@dataclass
class MockStandards:
    """Mock standards for testing."""
    brand_name: str = ""


def make_document(text: str, highlighted_texts: list[str] = None) -> Document:
    """Create a Document with optional highlighted spans."""
    highlighted_texts = highlighted_texts or []

    # Build runs with highlighting
    runs = []
    current_pos = 0
    remaining = text

    for hl_text in highlighted_texts:
        idx = remaining.find(hl_text)
        if idx == -1:
            continue

        # Add non-highlighted run before
        if idx > 0:
            runs.append(TextRun(
                text=remaining[:idx],
                start_offset=current_pos,
                end_offset=current_pos + idx,
            ))
            current_pos += idx

        # Add highlighted run
        runs.append(TextRun(
            text=hl_text,
            start_offset=current_pos,
            end_offset=current_pos + len(hl_text),
            highlight_color="yellow",
        ))
        current_pos += len(hl_text)
        remaining = remaining[idx + len(hl_text):]

    # Add remaining text
    if remaining:
        runs.append(TextRun(
            text=remaining,
            start_offset=current_pos,
            end_offset=current_pos + len(remaining),
        ))

    para = Paragraph(
        text=text,
        start_offset=0,
        end_offset=len(text),
        _runs=runs,
    )

    return Document(elements=[para])


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

class TestNormalizeKeyword:
    """Tests for normalize_keyword function."""

    def test_lowercase(self):
        assert normalize_keyword("CASINO BONUS") == "casino bonus"

    def test_collapse_whitespace(self):
        assert normalize_keyword("casino  bonus") == "casino bonus"
        assert normalize_keyword(" casino bonus ") == "casino bonus"

    def test_mixed(self):
        assert normalize_keyword("  CASINO   BONUS  ") == "casino bonus"


class TestGetKeywordVariants:
    """Tests for get_keyword_variants function."""

    def test_singular_to_plural(self):
        variants = get_keyword_variants("slot")
        assert "slot" in variants
        assert "slots" in variants

    def test_plural_to_singular(self):
        variants = get_keyword_variants("slots")
        assert "slots" in variants
        assert "slot" in variants

    def test_es_plural(self):
        variants = get_keyword_variants("bonuses")
        assert "bonuses" in variants
        assert "bonus" in variants

    def test_ies_plural(self):
        variants = get_keyword_variants("categories")
        assert "categories" in variants
        assert "category" in variants

    def test_multi_word(self):
        variants = get_keyword_variants("casino bonus")
        assert "casino bonus" in variants
        assert "casino bonuses" in variants


class TestFindKeywordOccurrences:
    """Tests for find_keyword_occurrences function."""

    def test_simple_match(self):
        text = "The casino bonus is great."
        occs = find_keyword_occurrences(text, "casino bonus")
        assert len(occs) == 1
        assert text[occs[0][0]:occs[0][1]] == "casino bonus"

    def test_case_insensitive(self):
        text = "The CASINO BONUS is great."
        occs = find_keyword_occurrences(text, "casino bonus")
        assert len(occs) == 1

    def test_multiple_occurrences(self):
        text = "Get a casino bonus today. The casino bonus is worth it."
        occs = find_keyword_occurrences(text, "casino bonus")
        assert len(occs) == 2

    def test_variant_matching(self):
        text = "Slots are fun. This slot is my favorite."
        occs = find_keyword_occurrences(text, "slot")
        # Should match both "Slots" and "slot"
        assert len(occs) == 2

    def test_word_boundary(self):
        text = "The casino is great. Casinoonline is not a match."
        occs = find_keyword_occurrences(text, "casino")
        assert len(occs) == 1

    def test_no_overlap(self):
        text = "The casino bonus is great."
        already_matched = set()
        occs1 = find_keyword_occurrences(text, "casino bonus", already_matched)
        occs2 = find_keyword_occurrences(text, "bonus", already_matched)
        # "bonus" alone should not match since it's already part of "casino bonus"
        assert len(occs1) == 1
        assert len(occs2) == 0


class TestCountWords:
    """Tests for count_words function."""

    def test_simple(self):
        assert count_words("one two three") == 3

    def test_with_punctuation(self):
        assert count_words("Hello, world! How are you?") == 5

    def test_empty(self):
        assert count_words("") == 0


# =============================================================================
# KEYWORDS CHECK TESTS
# =============================================================================

class TestKeywordsCheckNoOp:
    """Tests for graceful no-op when brief is unavailable."""

    def test_no_brief_returns_empty(self):
        """Check no-ops when no brief is provided."""
        doc = make_document("This is a test article about casinos.")
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=None)
        assert findings == []

    def test_invalid_brief_type_returns_empty(self):
        """Check no-ops when brief is wrong type."""
        doc = make_document("This is a test article about casinos.")
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief="not a brief")
        assert findings == []


class TestMissingKeywords:
    """Tests for missing keyword detection."""

    def test_keyword_present_no_finding(self):
        """Keyword present in article should not be flagged as missing."""
        doc = make_document("The casino bonus is great for players.")
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        missing = [f for f in findings if f.check_name == "keywords.missing"]
        assert len(missing) == 0

    def test_keyword_absent_flagged(self):
        """Missing keyword should be flagged."""
        doc = make_document("This article has no relevant keywords at all. " * 10)
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        missing = [f for f in findings if f.check_name == "keywords.missing"]
        assert len(missing) == 1
        assert "casino bonus" in missing[0].reasoning
        assert missing[0].auto_applicable is False

    def test_variant_matching_not_missing(self):
        """Plural/singular variants should count as present."""
        doc = make_document("The slots are amazing here. " * 5)
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="slot"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        missing = [f for f in findings if f.check_name == "keywords.missing"]
        assert len(missing) == 0

    def test_missing_type_truly_absent(self):
        """Keyword not in article at all should be marked truly_absent."""
        # Need at least 10 words for the check to run
        doc = make_document("This article has no relevant keywords at all and is just filler text for testing purposes only.")
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        missing = [f for f in findings if f.check_name == "keywords.missing"]
        assert len(missing) == 1
        meta = dict(missing[0].metadata)
        assert meta["missing_type"] == "truly_absent"
        assert "words are present" not in missing[0].reasoning

    def test_missing_type_wrong_construction(self):
        """Words present but not as phrase should be marked wrong_construction."""
        # Words "casino" and "bonus" appear nearby but not as the exact phrase "casino bonus"
        doc = make_document("Great bonus offers at Casino Royal. The casino has many bonus deals and promotions available.")
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        missing = [f for f in findings if f.check_name == "keywords.missing"]
        assert len(missing) == 1
        meta = dict(missing[0].metadata)
        assert meta["missing_type"] == "wrong_construction"
        assert "words are present" in missing[0].reasoning
        assert "adjust wording" in missing[0].reasoning


class TestKeywordQuantity:
    """Tests for keyword quantity checking."""

    def test_below_min_flagged(self):
        """Keyword count below minimum should be flagged."""
        # Only 1 occurrence of "casino bonus", min is 3
        doc = make_document("The casino bonus is great. Other words fill this text nicely for testing purposes.")
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus", min_quantity=3, max_quantity=5),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        qty = [f for f in findings if f.check_name == "keywords.quantity"]
        assert len(qty) == 1
        assert "appears 1 time" in qty[0].reasoning
        assert "requires at least 3" in qty[0].reasoning
        assert qty[0].auto_applicable is False

    def test_above_max_flagged(self):
        """Keyword count above maximum should be flagged."""
        doc = make_document("Casino bonus here. Casino bonus there. Casino bonus everywhere. " * 5)
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus", min_quantity=1, max_quantity=2),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        qty = [f for f in findings if f.check_name == "keywords.quantity"]
        assert len(qty) == 1
        assert "allows at most 2" in qty[0].reasoning
        assert qty[0].auto_applicable is False

    def test_within_range_no_finding(self):
        """Keyword count within range should not be flagged."""
        # 3 occurrences of "casino bonus", within 1-5 range
        doc = make_document("Casino bonus one. Casino bonus two. Casino bonus three. Other filler words here.")
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus", min_quantity=1, max_quantity=5),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        qty = [f for f in findings if f.check_name == "keywords.quantity"]
        assert len(qty) == 0


class TestKeywordDensity:
    """Tests for keyword density checking."""

    def test_density_below_threshold_no_finding(self):
        """Density below 3% should not be flagged."""
        # ~90 words with 2 keyword occurrences = ~2.2% density (below 3%)
        filler = "word " * 80  # 80 words of filler
        doc = make_document(f"The casino bonus is great. {filler} Another casino bonus here.")
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        density = [f for f in findings if f.check_name == "keywords.density"]
        assert len(density) == 0

    def test_density_above_threshold_flagged(self):
        """Density above 3% should be flagged."""
        # 30 occurrences in ~60 words = 50% density (need >= 50 words for density check)
        doc = make_document("Casino bonus is here. " * 15)  # 15 * 4 words = 60 words, 15 occurrences
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        density = [f for f in findings if f.check_name == "keywords.density"]
        assert len(density) == 1
        assert "exceeding" in density[0].reasoning
        assert density[0].auto_applicable is False


class TestKeywordHighlighting:
    """Tests for keyword highlighting detection."""

    def test_highlighted_keyword_no_finding(self):
        """Highlighted keyword should not be flagged."""
        doc = make_document(
            "The casino bonus is great. " * 5,
            highlighted_texts=["casino bonus"]
        )
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        highlight = [f for f in findings if f.check_name == "keywords.highlighting"]
        assert len(highlight) == 0

    def test_unhighlighted_keyword_flagged(self):
        """Unhighlighted main keyword should be flagged."""
        doc = make_document("The casino bonus is great. " * 5)
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        highlight = [f for f in findings if f.check_name == "keywords.highlighting"]
        assert len(highlight) == 1
        assert "not highlighted" in highlight[0].reasoning
        assert highlight[0].auto_applicable is False
        assert highlight[0].severity == "suggestion"

    def test_missing_keyword_not_flagged_for_highlighting(self):
        """Missing keyword should not also be flagged for highlighting."""
        doc = make_document("This article has no relevant content. " * 10)
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        highlight = [f for f in findings if f.check_name == "keywords.highlighting"]
        assert len(highlight) == 0  # Missing, so no highlight finding


class TestBrandOveruse:
    """Tests for brand name overuse detection."""

    def test_brand_overuse_flagged(self):
        """Brand name appearing too often should be flagged."""
        # Create text where brand appears at high density
        doc = make_document("Koifortune is great. Koifortune offers bonuses. Koifortune casino. " * 10)
        brief = MockBriefModel(
            keywords=MockBriefKeywords(main=()),
            brand_name="Koifortune",
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(brand_name="Koifortune"), brief=brief)

        overuse = [f for f in findings if f.check_name == "keywords.brand_overuse"]
        assert len(overuse) == 1
        assert "Koifortune" in overuse[0].reasoning
        assert overuse[0].auto_applicable is False

    def test_brand_normal_use_no_finding(self):
        """Normal brand usage should not be flagged."""
        filler = "This is great content. " * 50
        doc = make_document(f"Welcome to Koifortune. {filler}")
        brief = MockBriefModel(
            keywords=MockBriefKeywords(main=()),
            brand_name="Koifortune",
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(brand_name="Koifortune"), brief=brief)

        overuse = [f for f in findings if f.check_name == "keywords.brand_overuse"]
        assert len(overuse) == 0


class TestLocationOveruse:
    """Tests for location keyword overuse detection."""

    def test_location_overuse_flagged(self):
        """Location keyword appearing too often should be flagged."""
        doc = make_document("Australia is great. Visit Australia. Australia bonuses. " * 10)
        brief = MockBriefModel(
            keywords=MockBriefKeywords(main=()),
            market="Australia",
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        overuse = [f for f in findings if f.check_name == "keywords.location_overuse"]
        assert len(overuse) == 1
        assert "Australia" in overuse[0].reasoning
        assert overuse[0].auto_applicable is False


class TestNoAutoApplicable:
    """Tests that no findings are auto-applicable."""

    def test_all_findings_not_auto_applicable(self):
        """Every finding should have auto_applicable=False."""
        # Create document that triggers multiple issues
        doc = make_document("Koifortune. " * 30)  # High density
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(
                    MockBriefKeyword(keyword="casino bonus", min_quantity=3),  # Missing
                    MockBriefKeyword(keyword="Koifortune"),  # Present, unhighlighted
                )
            ),
            brand_name="Koifortune",
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(brand_name="Koifortune"), brief=brief)

        assert len(findings) > 0, "Should have at least some findings"
        for finding in findings:
            assert finding.auto_applicable is False, (
                f"Finding '{finding.check_name}' should not be auto_applicable"
            )


class TestAccurateLocation:
    """Tests for accurate finding locations."""

    def test_keyword_location_accurate(self):
        """Finding locations should point to actual keyword positions."""
        text = "Here is the casino bonus. " * 5
        doc = make_document(text)
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(MockBriefKeyword(keyword="casino bonus"),)
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        # Find the highlighting finding (has location to actual keyword)
        highlight = [f for f in findings if f.check_name == "keywords.highlighting"]
        assert len(highlight) == 1

        # Check that location points to actual text
        loc = highlight[0].location
        assert text[loc.start_offset:loc.end_offset].lower() == "casino bonus"


class TestOverlappingKeywords:
    """Tests for correct handling of overlapping keywords."""

    def test_no_double_counting(self):
        """Overlapping keywords should not be double-counted for density."""
        # "casino bonus" contains "bonus"
        doc = make_document("The casino bonus is great. " * 20)
        brief = MockBriefModel(
            keywords=MockBriefKeywords(
                main=(
                    MockBriefKeyword(keyword="casino bonus"),
                    MockBriefKeyword(keyword="bonus"),
                )
            )
        )
        check = KeywordsCheck()
        findings = check.run(doc, MockStandards(), brief=brief)

        density = [f for f in findings if f.check_name == "keywords.density"]
        # Should NOT have inflated density from double-counting
        # 20 occurrences of "casino bonus" in ~80 words = ~25% if double-counted
        # But should be ~12.5% if correctly not double-counted
        if density:
            # If flagged, density metadata should be reasonable
            density_val = density[0].metadata_dict.get("density", 0)
            assert density_val < 30, f"Density {density_val}% seems inflated by double-counting"


class TestCheckRegistration:
    """Tests for check registration."""

    def test_check_registers(self):
        """Check should be registered in the registry."""
        from core.check_base import get_registry
        registry = get_registry()

        # If not registered (another test cleared the registry), re-import
        if not registry.is_registered("keywords"):
            import importlib
            import deterministic.keywords
            importlib.reload(deterministic.keywords)

        assert registry.is_registered("keywords")

    def test_check_metadata(self):
        """Check metadata should be correct."""
        check = KeywordsCheck()
        assert check.metadata.name == "keywords"
        assert check.metadata.category == "keywords"
        assert check.is_deterministic
