"""
Tests for deterministic/brand_names.py - Brand name normalization and competitor detection.
"""

import pytest
from dataclasses import dataclass, field

from core.document import Document, Paragraph, Heading, HeadingLevel, Table, TableRow, TableCell, List, ListItem, ListType
from core.check_base import CheckRegistry


# =============================================================================
# FIXTURES
# =============================================================================

@dataclass
class MockBrandNormalization:
    """Mock brand normalization with mappings."""
    mappings: dict = field(default_factory=dict)


@dataclass
class MockStandards:
    """Mock standards object with brand info."""
    brand_name: str = "KoiFortune"
    brand_normalization: MockBrandNormalization = None

    def __post_init__(self):
        if self.brand_normalization is None:
            self.brand_normalization = MockBrandNormalization()


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


@pytest.fixture
def check():
    """Create the brand names check instance."""
    from deterministic.brand_names import BrandNamesCheck
    return BrandNamesCheck()


@pytest.fixture
def koifortune_standards() -> MockStandards:
    """Standards for KoiFortune brand (corpus-verified canonical)."""
    return MockStandards(
        brand_name="KoiFortune",
        brand_normalization=MockBrandNormalization(mappings={
            "koifortune": "KoiFortune",
            "Koifortune": "KoiFortune",
            "Koi Fortune": "KoiFortune",
            "koi fortune": "KoiFortune",
        })
    )


@pytest.fixture
def standards_22bet() -> MockStandards:
    """Standards for 22Bet brand."""
    return MockStandards(
        brand_name="22Bet",
        brand_normalization=MockBrandNormalization(mappings={
            "22bet": "22Bet",
            "22 Bet": "22Bet",
            "22BET": "22Bet",
        })
    )


@pytest.fixture
def betlabel_standards() -> MockStandards:
    """Standards for BetLabel brand (hypothetical)."""
    return MockStandards(
        brand_name="BetLabel",
        brand_normalization=MockBrandNormalization(mappings={
            "betlabel": "BetLabel",
            "Bet Label": "BetLabel",
            "bet label": "BetLabel",
            "BETLABEL": "BetLabel",
        })
    )


@pytest.fixture
def vave_standards() -> MockStandards:
    """Standards for Vave brand."""
    return MockStandards(
        brand_name="Vave",
        brand_normalization=MockBrandNormalization(mappings={
            "vave": "Vave",
            "VAVE": "Vave",
        })
    )


# =============================================================================
# OWN-BRAND NORMALIZATION TESTS
# =============================================================================

class TestOwnBrandNormalization:
    """Test own-brand name normalization."""

    def test_wrong_spacing_normalized(self, check, koifortune_standards):
        """'Koi Fortune' -> 'KoiFortune', auto."""
        doc = make_document("Welcome to Koi Fortune casino.")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1
        assert own_brand[0].original_text == "Koi Fortune"
        assert own_brand[0].proposed_text == "KoiFortune"
        assert own_brand[0].auto_applicable is True

    def test_wrong_case_normalized(self, check, koifortune_standards):
        """'koifortune' -> 'KoiFortune', auto."""
        doc = make_document("Play at koifortune today.")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1
        assert own_brand[0].original_text == "koifortune"
        assert own_brand[0].proposed_text == "KoiFortune"
        assert own_brand[0].auto_applicable is True

    def test_all_caps_normalized(self, check, koifortune_standards):
        """'KOIFORTUNE' -> 'KoiFortune', auto."""
        doc = make_document("KOIFORTUNE IS THE BEST")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1
        assert own_brand[0].proposed_text == "KoiFortune"

    def test_correct_brand_no_finding(self, check, koifortune_standards):
        """Correct 'KoiFortune' produces no own-brand finding."""
        doc = make_document("Welcome to KoiFortune casino.")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 0

    def test_22bet_spacing(self, check, standards_22bet):
        """'22 Bet' -> '22Bet', auto."""
        doc = make_document("Join 22 Bet today.")
        findings = check.run(doc, standards_22bet)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1
        assert own_brand[0].original_text == "22 Bet"
        assert own_brand[0].proposed_text == "22Bet"

    def test_22bet_lowercase(self, check, standards_22bet):
        """'22bet' -> '22Bet', auto."""
        doc = make_document("Play at 22bet now.")
        findings = check.run(doc, standards_22bet)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1
        assert own_brand[0].proposed_text == "22Bet"

    def test_betlabel_spacing(self, check, betlabel_standards):
        """'Bet Label' -> 'BetLabel', auto."""
        doc = make_document("Welcome to Bet Label casino.")
        findings = check.run(doc, betlabel_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1
        assert own_brand[0].original_text == "Bet Label"
        assert own_brand[0].proposed_text == "BetLabel"

    def test_url_not_touched(self, check, standards_22bet):
        """'22bet.com' not flagged - it's a URL."""
        doc = make_document("Visit 22bet.com for more info.")
        findings = check.run(doc, standards_22bet)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 0

    def test_https_url_not_touched(self, check, koifortune_standards):
        """Brand in HTTPS URL not flagged."""
        doc = make_document("Go to https://koifortune.com today.")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 0

    def test_email_not_touched(self, check, koifortune_standards):
        """Brand in email not flagged."""
        doc = make_document("Contact support@koifortune.com for help.")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 0

    def test_multiple_variants(self, check, koifortune_standards):
        """Multiple variants in same text."""
        doc = make_document("Koi Fortune and koifortune are the same as KoiFortune.")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        # Should find 2: "Koi Fortune" and "koifortune", but not "KoiFortune"
        assert len(own_brand) == 2

    def test_heading_checked(self, check, koifortune_standards):
        """Headings are checked for brand variants."""
        doc = make_heading_document("Welcome to Koi Fortune")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1

    def test_table_cell_checked(self, check, koifortune_standards):
        """Table cells are checked for brand variants."""
        doc = make_table_document(["Brand", "Koi Fortune"])
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1


# =============================================================================
# COMPETITOR DETECTION TESTS
# =============================================================================

class TestCompetitorDetection:
    """Test competitor brand detection."""

    def test_competitor_flagged(self, check, koifortune_standards):
        """bet365 in Koifortune article -> proposal."""
        doc = make_document("Unlike bet365, we offer better odds.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert len(competitor) == 1
        assert competitor[0].original_text == "bet365"
        assert competitor[0].auto_applicable is False
        assert competitor[0].proposed_text is None

    def test_competitor_bet365_capitalized(self, check, koifortune_standards):
        """Bet365 (capitalized) flagged."""
        doc = make_document("Bet365 is a competitor.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert len(competitor) == 1

    def test_own_brand_not_competitor(self, check, koifortune_standards):
        """Own brand not flagged as competitor."""
        doc = make_document("Koifortune is the best casino.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert len(competitor) == 0

    def test_stake_lowercase_not_flagged(self, check, koifortune_standards):
        """'stake' as common word not flagged."""
        doc = make_document("Place your stake on the game.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert len(competitor) == 0

    def test_stake_with_article_not_flagged(self, check, koifortune_standards):
        """'a Stake' with article not flagged (common word usage)."""
        doc = make_document("Place a Stake on the match.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert len(competitor) == 0

    def test_stake_capitalized_flagged(self, check, koifortune_standards):
        """'Stake' as operator flagged (no article)."""
        doc = make_document("Stake offers crypto betting options.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert len(competitor) == 1
        assert competitor[0].auto_applicable is False

    def test_national_lowercase_not_flagged(self, check, koifortune_standards):
        """'national' as adjective not flagged."""
        doc = make_document("Check national regulations before playing.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert len(competitor) == 0

    def test_draftkings_flagged(self, check, koifortune_standards):
        """DraftKings flagged as competitor."""
        doc = make_document("DraftKings operates in the US market.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert len(competitor) == 1
        assert "DraftKings" in competitor[0].original_text

    def test_multiple_competitors(self, check, koifortune_standards):
        """Multiple competitors flagged."""
        doc = make_document("Unlike bet365 and DraftKings, we offer more.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert len(competitor) == 2

    def test_competitor_in_url_not_flagged(self, check, koifortune_standards):
        """Competitor in URL not flagged."""
        doc = make_document("Visit bet365.com for comparison.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert len(competitor) == 0

    def test_competitor_severity_warning(self, check, koifortune_standards):
        """Competitor finding has warning severity."""
        doc = make_document("bet365 is different.")
        findings = check.run(doc, koifortune_standards)

        competitor = [f for f in findings if f.metadata_dict.get("sub_check") == "competitor"]
        assert competitor[0].severity == "warning"


# =============================================================================
# REGISTRATION TESTS
# =============================================================================

class TestRegistration:
    """Test check registration."""

    def test_check_registered(self, check):
        """Check is registered with correct name."""
        assert check.name == "brand_names"
        assert check.category == "brand_names"

    def test_required_standards(self, check):
        """Check requires brand_name."""
        required = check._get_required_standards()
        assert "brand_name" in required


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases."""

    def test_empty_document(self, check, koifortune_standards):
        """Empty document produces no findings."""
        doc = make_document("")
        findings = check.run(doc, koifortune_standards)
        assert len(findings) == 0

    def test_no_brand_name_in_standards(self, check):
        """No brand_name in standards produces no findings."""
        standards = MockStandards(brand_name=None)
        doc = make_document("Welcome to Koifortune")
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_quoted_brand_not_flagged(self, check, koifortune_standards):
        """Brand in quotes not flagged (intentional)."""
        doc = make_document('The app is called "Koi Fortune Casino".')
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 0

    def test_finding_has_location(self, check, koifortune_standards):
        """Finding has accurate location."""
        doc = make_document("Welcome to Koi Fortune today.")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1
        assert own_brand[0].location is not None
        assert own_brand[0].location.start_offset == 11  # "Welcome to " = 11 chars

    def test_vave_lowercase(self, check, vave_standards):
        """'vave' -> 'Vave', auto."""
        doc = make_document("Play at vave casino.")
        findings = check.run(doc, vave_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1
        assert own_brand[0].proposed_text == "Vave"

    def test_brand_at_start_of_sentence(self, check, koifortune_standards):
        """Brand at start of sentence detected."""
        doc = make_document("koifortune offers great bonuses.")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1

    def test_brand_at_end_of_text(self, check, koifortune_standards):
        """Brand at end of text detected."""
        doc = make_document("Play at koifortune")
        findings = check.run(doc, koifortune_standards)

        own_brand = [f for f in findings if f.metadata_dict.get("sub_check") == "own_brand"]
        assert len(own_brand) == 1
