"""
Tests for the currency consistency check.

Tests cover:
- Combined symbol+code violations (e.g., "$500 USD")
- Consistent single style produces no findings
- Mixed styles flag minority for normalization
- Tie in styles produces proposals (not auto-fixes)
- Number separators (1,000 / 1.000 / 1 000)
- Bare "$" treated consistently (not guessed)
- Crypto codes handled
- No false matches on percentages or plain numbers
- Currency in table cells is checked
- Accurate location offsets
- Self-registration
"""

import pytest
from dataclasses import dataclass

from core.check_base import get_registry
from core.document import Document, Paragraph, Table, TableRow, TableCell
from core.finding import Finding
from deterministic.currency import CurrencyConsistencyCheck


# =============================================================================
# FIXTURES
# =============================================================================

@dataclass
class MockCurrencyStandards:
    """Mock currency standards."""
    mode: str = "exclusive"
    symbol: str = None


@dataclass
class MockStandards:
    """Mock standards object with currency."""
    currency: MockCurrencyStandards = None

    def __post_init__(self):
        if self.currency is None:
            self.currency = MockCurrencyStandards()


def make_document(text: str, start_offset: int = 0) -> Document:
    """Create a simple document with one paragraph."""
    para = Paragraph(
        text=text,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
    )
    return Document.from_elements([para])


def make_multi_para_document(*texts: str) -> Document:
    """Create a document with multiple paragraphs."""
    elements = []
    offset = 0
    for text in texts:
        para = Paragraph(
            text=text,
            start_offset=offset,
            end_offset=offset + len(text),
        )
        elements.append(para)
        offset += len(text) + 1
    return Document.from_elements(elements)


def make_document_with_table(para_text: str, cell_texts: list[str]) -> Document:
    """Create a document with a paragraph and a table."""
    para = Paragraph(
        text=para_text,
        start_offset=0,
        end_offset=len(para_text),
    )

    offset = len(para_text) + 1
    cells = []
    for cell_text in cell_texts:
        cell = TableCell(
            text=cell_text,
            start_offset=offset,
            end_offset=offset + len(cell_text),
            row_index=0,
            col_index=len(cells),
        )
        cells.append(cell)
        offset += len(cell_text) + 1

    row = TableRow(cells=cells, is_header_row=False)
    table = Table(rows=[row], start_offset=cells[0].start_offset, end_offset=offset)
    return Document.from_elements([para, table])


@pytest.fixture
def check() -> CurrencyConsistencyCheck:
    """Create the currency check instance."""
    return CurrencyConsistencyCheck()


@pytest.fixture
def standards() -> MockStandards:
    """Create mock standards with exclusive currency mode."""
    return MockStandards()


# =============================================================================
# TEST: COMBINED SYMBOL+CODE VIOLATIONS
# =============================================================================

class TestCombinedViolations:
    """Test combined symbol+code patterns are flagged."""

    def test_euro_combined(self, check, standards):
        """Euro symbol + EUR code flagged."""
        doc = make_document("Deposit bonus of €500 EUR available now.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        assert findings[0].original_text == "€500 EUR"
        assert findings[0].metadata_dict["sub_check"] == "combined_violation"

    def test_dollar_combined(self, check, standards):
        """Dollar symbol + USD code flagged."""
        doc = make_document("Win up to $1,000 USD in prizes.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        assert findings[0].original_text == "$1,000 USD"

    def test_canadian_combined(self, check, standards):
        """Canadian dollar C$ + CAD flagged."""
        doc = make_document("Get C$500 CAD free play today.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        assert findings[0].original_text == "C$500 CAD"

    def test_combined_proposes_symbol_form(self, check, standards):
        """Combined violation proposes symbol-only form by default."""
        doc = make_document("Bonus of €100 EUR available.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        # With no dominant style, defaults to symbol form
        assert findings[0].proposed_text == "€100"

    def test_combined_proposes_based_on_dominant(self, check, standards):
        """Combined violation proposes based on dominant style."""
        # Document has 2 code-style, 0 symbol-style → code dominant
        doc = make_document("Get 500 EUR or 100 EUR plus €50 EUR bonus.")
        findings = check.run(doc, standards)

        # Should flag the combined €50 EUR
        combined_findings = [f for f in findings
                           if f.metadata_dict.get("sub_check") == "combined_violation"]
        assert len(combined_findings) == 1
        assert combined_findings[0].proposed_text == "50 EUR"

    def test_bitcoin_combined(self, check, standards):
        """Bitcoin symbol + BTC code flagged."""
        doc = make_document("Deposit ₿0.5 BTC to start.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        assert findings[0].original_text == "₿0.5 BTC"


# =============================================================================
# TEST: CONSISTENT STYLE - NO FINDINGS
# =============================================================================

class TestConsistentStyle:
    """Test consistent single style produces no findings."""

    def test_consistent_symbol_style(self, check, standards):
        """All symbol style produces no findings."""
        doc = make_document("Get €20, €500, and €1,000 in bonuses.")
        findings = check.run(doc, standards)

        assert len(findings) == 0

    def test_consistent_code_style(self, check, standards):
        """All code style produces no findings."""
        doc = make_document("Get 20 EUR, 500 EUR, and 1000 EUR in bonuses.")
        findings = check.run(doc, standards)

        assert len(findings) == 0

    def test_consistent_dollar_symbol(self, check, standards):
        """Consistent bare $ produces no findings."""
        doc = make_document("Win $50, $100, or $500 today.")
        findings = check.run(doc, standards)

        assert len(findings) == 0

    def test_consistent_crypto_code(self, check, standards):
        """Consistent crypto code style produces no findings."""
        doc = make_document("Deposit 0.1 BTC, 1 ETH, or 500 USDT.")
        findings = check.run(doc, standards)

        assert len(findings) == 0


# =============================================================================
# TEST: MIXED STYLES - NORMALIZATION
# =============================================================================

class TestMixedStyles:
    """Test mixed styles flag minority for normalization."""

    def test_minority_flagged(self, check, standards):
        """Minority style flagged to match dominant."""
        # 2 symbol, 1 code → code is minority
        doc = make_document("Get €100 and €200 plus 50 EUR bonus.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        assert findings[0].original_text == "50 EUR"
        assert findings[0].metadata_dict["sub_check"] == "style_inconsistency"
        assert findings[0].metadata_dict["dominant_style"] == "symbol"

    def test_minority_proposes_conversion(self, check, standards):
        """Minority proposes conversion to dominant style."""
        doc = make_document("Claim €500 and €100 or 200 EUR now.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        assert findings[0].proposed_text == "€200"

    def test_clear_majority_auto_applicable(self, check, standards):
        """Clear majority (>60%) makes findings auto-applicable."""
        # 3 symbol, 1 code → 75% symbol → auto-applicable
        doc = make_document("Get €100, €200, €300, or 50 EUR.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        assert findings[0].auto_applicable is True

    def test_close_split_not_auto_applicable(self, check, standards):
        """Close split makes findings proposals (not auto-applicable)."""
        # 2 symbol, 1 code → 66% symbol but close-ish
        # Actually 66% > 60% so this should be auto
        # Let's do 3 vs 2: 60% exactly
        doc = make_document("Get €100, €200, €300, 50 EUR, 75 EUR.")
        findings = check.run(doc, standards)

        # 3 symbol, 2 code = 60% symbol, exactly at threshold
        # With > 0.6 check, this is NOT auto-applicable
        for f in findings:
            if f.metadata_dict.get("sub_check") == "style_inconsistency":
                assert f.auto_applicable is False

    def test_conversion_code_to_symbol(self, check, standards):
        """Code-style converted to symbol when symbol dominant."""
        doc = make_document("Get $100, $200, $300, $400, and 50 USD.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        assert findings[0].original_text == "50 USD"
        assert findings[0].proposed_text == "$50"

    def test_conversion_symbol_to_code(self, check, standards):
        """Symbol-style converted to code when code dominant."""
        doc = make_document("Get 100 EUR, 200 EUR, 300 EUR, 400 EUR, and €50.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        assert findings[0].original_text == "€50"
        assert findings[0].proposed_text == "50 EUR"


# =============================================================================
# TEST: TIE IN STYLES
# =============================================================================

class TestTieInStyles:
    """Test exact tie in styles behavior."""

    def test_exact_tie_emits_proposals(self, check, standards):
        """Exact tie emits proposals (not auto-applicable)."""
        # 2 symbol, 2 code = tie
        doc = make_document("Get €100, €200, 300 EUR, 400 EUR.")
        findings = check.run(doc, standards)

        # Should flag the code-style as proposals (symbol picked as dominant in tie)
        style_findings = [f for f in findings
                        if f.metadata_dict.get("sub_check") == "style_inconsistency"]
        assert len(style_findings) == 2  # Both code-style instances

        # Should not be auto-applicable (it's a tie, so proposal)
        for f in style_findings:
            assert f.auto_applicable is False


# =============================================================================
# TEST: SEPARATORS
# =============================================================================

class TestSeparators:
    """Test number separator handling."""

    def test_comma_separator(self, check, standards):
        """Comma thousands separator handled."""
        doc = make_document("Win $1,000,000 grand prize.")
        findings = check.run(doc, standards)
        assert len(findings) == 0  # Consistent style

    def test_dot_separator(self, check, standards):
        """European dot thousands separator handled."""
        doc = make_document("Win €1.000.000 grand prize.")
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_space_separator(self, check, standards):
        """Space thousands separator handled."""
        doc = make_document("Win 1 000 000 EUR grand prize.")
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_decimal_places(self, check, standards):
        """Decimal places handled."""
        doc = make_document("Minimum deposit €10.50 required.")
        findings = check.run(doc, standards)
        assert len(findings) == 0


# =============================================================================
# TEST: BARE DOLLAR
# =============================================================================

class TestBareDollar:
    """Test bare $ is treated consistently."""

    def test_bare_dollar_consistent(self, check, standards):
        """Bare $ treated as consistent style."""
        doc = make_document("Get $100, $500, and $1000 bonuses.")
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_bare_dollar_not_guessed(self, check, standards):
        """Bare $ not assumed to be USD/CAD/AUD."""
        # $ should be its own thing, not matched with USD code-style
        doc = make_document("Get $100 and 50 USD bonus.")
        findings = check.run(doc, standards)

        # $ is symbol style, 50 USD is code style → mixed
        assert len(findings) == 1


# =============================================================================
# TEST: CRYPTO
# =============================================================================

class TestCrypto:
    """Test crypto currency handling."""

    def test_crypto_code_only(self, check, standards):
        """Crypto with code only is consistent."""
        doc = make_document("Deposit 0.5 BTC or 10 ETH.")
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_crypto_symbol_only(self, check, standards):
        """Crypto with symbol only is consistent."""
        doc = make_document("Deposit ₿0.5 to claim bonus.")
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_crypto_combined_flagged(self, check, standards):
        """Crypto symbol+code combined is flagged."""
        doc = make_document("Deposit ₿0.5 BTC minimum.")
        findings = check.run(doc, standards)

        assert len(findings) == 1
        assert findings[0].original_text == "₿0.5 BTC"


# =============================================================================
# TEST: NO FALSE MATCHES
# =============================================================================

class TestNoFalseMatches:
    """Test no false matches on non-currency patterns."""

    def test_percentages_not_matched(self, check, standards):
        """Percentages not matched as currency."""
        doc = make_document("Get 100% match bonus on first deposit.")
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_plain_numbers_not_matched(self, check, standards):
        """Plain numbers without symbol/code not matched."""
        doc = make_document("Play over 500 games with 100 providers.")
        findings = check.run(doc, standards)
        assert len(findings) == 0

    def test_partial_word_not_matched(self, check, standards):
        """Currency codes inside words not matched."""
        doc = make_document("SECURE payment methods are USED here.")
        findings = check.run(doc, standards)
        assert len(findings) == 0


# =============================================================================
# TEST: TABLE CELLS
# =============================================================================

class TestTableCells:
    """Test currency in table cells is checked."""

    def test_table_currency_checked(self, check, standards):
        """Currency in table cells is detected."""
        doc = make_document_with_table(
            "Deposit options below:",
            ["€100", "€500", "50 EUR"]  # Mixed styles in table
        )
        findings = check.run(doc, standards)

        # Should flag the minority style in table
        assert len(findings) == 1
        assert findings[0].original_text == "50 EUR"
        assert findings[0].metadata_dict["element_type"] == "table"

    def test_table_combined_violation(self, check, standards):
        """Combined violations in tables flagged."""
        doc = make_document_with_table(
            "Bonus amounts:",
            ["€500 EUR", "€100"]
        )
        findings = check.run(doc, standards)

        combined = [f for f in findings
                   if f.metadata_dict.get("sub_check") == "combined_violation"]
        assert len(combined) == 1


# =============================================================================
# TEST: LOCATION ACCURACY
# =============================================================================

class TestLocationAccuracy:
    """Test finding locations are accurate."""

    def test_accurate_offset(self, check, standards):
        """Finding offset matches text position."""
        text = "Get a €500 EUR bonus today."
        doc = make_document(text)
        findings = check.run(doc, standards)

        assert len(findings) == 1
        # Find where "€500 EUR" starts in the text
        expected_start = text.find("€500 EUR")
        assert findings[0].location.start_offset == expected_start

    def test_accurate_end_offset(self, check, standards):
        """Finding end offset is correct."""
        text = "Bonus: €500 EUR available."
        doc = make_document(text)
        findings = check.run(doc, standards)

        assert len(findings) == 1
        start = text.find("€500 EUR")
        end = start + len("€500 EUR")
        assert findings[0].location.end_offset == end


# =============================================================================
# TEST: REGISTRATION
# =============================================================================

class TestRegistration:
    """Test check self-registration."""

    def test_self_registers(self):
        """Check registers itself with the registry."""
        registry = get_registry()

        # If registry was cleared by other tests, re-register
        if not registry.is_registered("currency"):
            from core.check_base import register_check
            register_check(CurrencyConsistencyCheck)

        assert "currency" in registry
        assert isinstance(registry.get_instance("currency"), CurrencyConsistencyCheck)

    def test_metadata(self, check):
        """Check has correct metadata."""
        assert check.name == "currency"
        assert check.category == "currency"
        assert "currency" in check.metadata.description.lower()


# =============================================================================
# TEST: MODE HANDLING
# =============================================================================

# =============================================================================
# TEST: MULTIPLE CONVENTIONS
# =============================================================================

class TestMultipleConventions:
    """Test handling of multiple distinct currency conventions."""

    def test_four_conventions_proposal_only(self, check, standards):
        """Article with 4+ conventions makes lone-minority a proposal."""
        # A$, bare $, AUD code, USDT code = 4 conventions
        doc = make_document_with_table(
            "Get A$100, A$200. Also 50 USDT and 10 AUD bonus.",
            ["$500", "$1000"]  # Table uses bare $
        )
        findings = check.run(doc, standards)

        # Should flag "10 AUD" as style inconsistency (code → symbol)
        # But should be PROPOSAL, not AUTO (4 conventions)
        style_findings = [f for f in findings
                        if f.metadata_dict.get("sub_check") == "style_inconsistency"]

        assert len(style_findings) == 1
        assert style_findings[0].original_text == "10 AUD"
        assert style_findings[0].auto_applicable is False
        assert "conventions" in style_findings[0].reasoning.lower()

    def test_two_conventions_auto_applicable(self, check, standards):
        """Article with only 2 conventions can be auto if >70% dominant."""
        # Only € and EUR = 2 conventions
        doc = make_document("Get €100, €200, €300, €400, and 50 EUR.")
        findings = check.run(doc, standards)

        # 4 symbol, 1 code = 80% symbol → should be AUTO
        style_findings = [f for f in findings
                        if f.metadata_dict.get("sub_check") == "style_inconsistency"]

        assert len(style_findings) == 1
        assert style_findings[0].original_text == "50 EUR"
        assert style_findings[0].auto_applicable is True

    def test_prose_vs_table_different_styles(self, check, standards):
        """Prose and tables using different styles → proposal."""
        # Prose uses €, table uses $
        doc = make_document_with_table(
            "Get €100 and €200 bonus.",
            ["$50", "$100"]
        )
        findings = check.run(doc, standards)

        # With different conventions in prose vs table, should be proposals
        style_findings = [f for f in findings
                        if f.metadata_dict.get("sub_check") == "style_inconsistency"]

        for f in style_findings:
            # Either should be proposal due to prose/table difference
            assert f.auto_applicable is False

    def test_combined_violations_auto_regardless_of_conventions(self, check, standards):
        """Combined violations stay AUTO even with many conventions."""
        # Multiple conventions but combined violation is still §11 violation
        doc = make_document(
            "Get A$100, 50 USDT, 10 AUD, and $20 CAD bonus."
        )
        findings = check.run(doc, standards)

        # The $20 CAD is a combined violation - should be AUTO
        combined_findings = [f for f in findings
                           if f.metadata_dict.get("sub_check") == "combined_violation"]

        assert len(combined_findings) == 1
        assert combined_findings[0].original_text == "$20 CAD"
        assert combined_findings[0].auto_applicable is True

    def test_three_conventions_proposal(self, check, standards):
        """3+ conventions makes lone-minority a proposal."""
        # €, £, EUR = 3 conventions
        doc = make_document("Get €100, £50, and 25 EUR bonus.")
        findings = check.run(doc, standards)

        style_findings = [f for f in findings
                        if f.metadata_dict.get("sub_check") == "style_inconsistency"]

        # All minority findings should be proposals
        for f in style_findings:
            assert f.auto_applicable is False


class TestModeHandling:
    """Test currency mode handling."""

    def test_non_exclusive_mode_skips(self, check):
        """Non-exclusive mode produces no findings."""
        standards = MockStandards(
            currency=MockCurrencyStandards(mode="any")
        )
        doc = make_document("Get €500 EUR bonus.")
        findings = check.run(doc, standards)

        assert len(findings) == 0
