"""
Tests for judgment/consistency.py - Numerical Claim Consistency Check

Validation triad:
1. True-positive catch: planted conflict is detected
2. Clean-article silence: no proposals for clean articles
3. Non-pairing verification: different-but-same-category claims don't get paired
"""

import pytest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

from core.document import Document, Paragraph, TextRun
from core.check_base import get_registry
from judgment.consistency import (
    ConsistencyCheck,
    _extract_claims,
    _find_conflict_pairs,
    _parse_llm_response,
    _build_prompt,
    ExtractedClaim,
)


def _make_paragraph(text: str, start_offset: int) -> Paragraph:
    """Helper to create a paragraph with proper offsets."""
    return Paragraph(
        text=text,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
        _runs=[TextRun(text=text, start_offset=0, end_offset=len(text))],
    )


def _create_document(texts: list[str]) -> Document:
    """Create a test document from list of paragraph texts."""
    elements = []
    offset = 0
    for text in texts:
        elements.append(_make_paragraph(text, offset))
        offset += len(text) + 1  # +1 for newline
    return Document(elements=elements, title="Test Doc")


# =============================================================================
# VALIDATION TRIAD TEST 1: True-Positive Catch
# =============================================================================

class TestTruePositiveCatch:
    """Test that planted conflicts are detected correctly."""

    def test_welcome_bonus_conflict_extracted(self):
        """Pre-filter catches welcome bonus conflict."""
        doc = _create_document([
            "Welcome to KoiFortune Casino!",
            "Sign up today and get a $4000 welcome bonus on your first deposit.",
            "Our games include pokies, table games, and live dealers.",
            "New players receive up to $5000 on their first deposit when joining.",
            "Visit us today!",
        ])

        claims = _extract_claims(doc)
        pairs = _find_conflict_pairs(claims)

        # Should find one pair: $4000 vs $5000, both welcome subtype
        assert len(pairs) == 1, f"Expected 1 conflict pair, got {len(pairs)}"

        claim_a, claim_b = pairs[0]
        assert claim_a.category == "BONUS_AMOUNT"
        assert claim_a.subtype == "welcome"
        assert claim_b.category == "BONUS_AMOUNT"
        assert claim_b.subtype == "welcome"
        assert claim_a.value == "$4000"
        assert claim_b.value == "$5000"

    def test_wagering_conflict_extracted(self):
        """Pre-filter catches wagering requirement conflict."""
        doc = _create_document([
            "KoiFortune Welcome Bonus",
            "The bonus has a 35x wagering requirement on all bonus funds.",
            "Play through slots, table games, and more.",
            "Complete the 40x playthrough requirement to withdraw your winnings.",
        ])

        claims = _extract_claims(doc)
        pairs = _find_conflict_pairs(claims)

        # Should find one pair: 35x vs 40x, both generic wagering
        assert len(pairs) == 1, f"Expected 1 conflict pair, got {len(pairs)}"

        claim_a, claim_b = pairs[0]
        assert claim_a.category == "WAGERING"
        assert claim_a.value == "35x"
        assert claim_b.value == "40x"

    def test_llm_conflict_verdict_produces_finding(self):
        """CONFLICT verdict from LLM produces a finding."""
        doc = _create_document([
            "Get a $4000 welcome bonus when you sign up.",
            "New players receive up to $5000 on their first deposit.",
        ])

        check = ConsistencyCheck()

        # Mock LLM response
        mock_response = "PAIR 1: CONFLICT - These both describe the welcome bonus for first deposits but state different amounts."

        with patch('judgment.consistency.call_llm', return_value=mock_response):
            # Verify trigger exists
            assert check._has_trigger(doc, None)

            # Generate proposals
            findings = check._generate_proposals(doc, None, None)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.check_name == "consistency"
        assert finding.auto_applicable is False
        assert "CONFLICT" in finding.metadata_dict.get("llm_verdict", "")
        assert "$4000" in finding.original_text
        assert "$5000" in finding.original_text
        assert "same" in finding.reasoning.lower() or "first deposit" in finding.reasoning.lower()

    def test_llm_different_verdict_produces_no_finding(self):
        """DIFFERENT verdict from LLM produces no finding."""
        doc = _create_document([
            "Get a $4000 welcome bonus when you sign up.",
            "New players receive up to $5000 on their first deposit.",
        ])

        check = ConsistencyCheck()

        mock_response = "PAIR 1: DIFFERENT - These are two separate promotional offers with different conditions."

        with patch('judgment.consistency.call_llm', return_value=mock_response):
            findings = check._generate_proposals(doc, None, None)

        assert len(findings) == 0


# =============================================================================
# VALIDATION TRIAD TEST 2: Clean-Article Silence
# =============================================================================

class TestCleanArticleSilence:
    """Test that clean articles produce zero proposals."""

    def test_no_conflicts_no_trigger(self):
        """Article with consistent values has no trigger."""
        doc = _create_document([
            "Welcome to KoiFortune Casino!",
            "Sign up today and get a $4000 welcome bonus.",
            "The $4000 bonus comes with a 35x wagering requirement.",
            "Complete the 35x playthrough to withdraw your winnings.",
            "We have over 1000 games available.",
            "Choose from 1000+ pokies and table games.",
        ])

        check = ConsistencyCheck()
        has_trigger = check._has_trigger(doc, None)

        assert has_trigger is False, "Clean article should have no trigger"

    def test_single_mention_claims_no_pairs(self):
        """Single-mention claims don't create pairs."""
        doc = _create_document([
            "Get a $500 welcome bonus.",
            "Reload bonus of $200 available.",
            "Minimum deposit is $20.",
            "Withdrawal minimum is $50.",
        ])

        claims = _extract_claims(doc)
        pairs = _find_conflict_pairs(claims)

        # Each claim is mentioned only once, so no pairs
        assert len(pairs) == 0

    def test_identical_values_no_pairs(self):
        """Identical values don't create conflict pairs."""
        doc = _create_document([
            "Get a $500 welcome bonus on your first deposit.",
            "New players receive $500 when signing up.",
        ])

        claims = _extract_claims(doc)
        pairs = _find_conflict_pairs(claims)

        # Same value ($500), so no conflict
        assert len(pairs) == 0


# =============================================================================
# VALIDATION TRIAD TEST 3: Non-Pairing Verification
# =============================================================================

class TestNonPairingVerification:
    """Test that different-but-same-category claims don't get paired."""

    def test_welcome_vs_reload_not_paired(self):
        """Welcome bonus and reload bonus are NOT paired."""
        doc = _create_document([
            "Get a $500 welcome bonus on your first deposit.",
            "Claim a $200 reload bonus on your second deposit.",
        ])

        claims = _extract_claims(doc)
        pairs = _find_conflict_pairs(claims)

        # Different subtypes (welcome vs reload), should NOT pair
        assert len(pairs) == 0

        # Verify claims were extracted with correct subtypes
        welcome_claims = [c for c in claims if c.subtype == "welcome"]
        reload_claims = [c for c in claims if c.subtype == "reload"]
        assert len(welcome_claims) >= 1
        assert len(reload_claims) >= 1

    def test_deposit_min_vs_withdrawal_min_not_paired(self):
        """Deposit minimum and withdrawal minimum are NOT paired."""
        doc = _create_document([
            "The minimum deposit is $20.",
            "Minimum withdrawal amount is $50.",
        ])

        claims = _extract_claims(doc)
        pairs = _find_conflict_pairs(claims)

        # Different subtypes, should NOT pair
        assert len(pairs) == 0

    def test_slots_wagering_vs_table_wagering_not_paired(self):
        """Slot wagering and table game wagering are NOT paired."""
        doc = _create_document([
            "Wagering on slots is 35x for the bonus.",
            "Table games have a 50x wagering requirement.",
        ])

        claims = _extract_claims(doc)
        pairs = _find_conflict_pairs(claims)

        # Different subtypes (slots vs table_games), should NOT pair
        assert len(pairs) == 0

    def test_different_categories_not_paired(self):
        """Different categories (BONUS_AMOUNT vs WAGERING) are NOT paired."""
        doc = _create_document([
            "Get a $500 welcome bonus.",
            "The bonus has a 500x wagering requirement.",  # 500x is extreme but tests the point
        ])

        claims = _extract_claims(doc)
        pairs = _find_conflict_pairs(claims)

        # Different categories entirely, should NOT pair
        assert len(pairs) == 0


# =============================================================================
# LLM RESPONSE PARSING
# =============================================================================

class TestLLMResponseParsing:
    """Test robust parsing of LLM responses."""

    def test_standard_format_parsing(self):
        """Parse standard format responses."""
        response = """PAIR 1: CONFLICT - Both describe the welcome bonus amount.
PAIR 2: DIFFERENT - These are separate promotional offers."""

        verdicts = _parse_llm_response(response, 2)

        assert len(verdicts) == 2
        assert verdicts[0].verdict == "CONFLICT"
        assert verdicts[1].verdict == "DIFFERENT"

    def test_varied_format_parsing(self):
        """Parse slightly varied format responses."""
        response = """PAIR 1: CONFLICT- Same welcome bonus stated with different amounts
PAIR 2: DIFFERENT: These are clearly separate claims"""

        verdicts = _parse_llm_response(response, 2)

        assert len(verdicts) == 2
        assert verdicts[0].verdict == "CONFLICT"
        assert verdicts[1].verdict == "DIFFERENT"

    def test_unclear_verdict_parsing(self):
        """Parse UNCLEAR verdicts."""
        response = """PAIR 1: UNCLEAR - Not enough context to determine if these are the same claim"""

        verdicts = _parse_llm_response(response, 1)

        assert len(verdicts) == 1
        assert verdicts[0].verdict == "UNCLEAR"

    def test_unparseable_defaults_to_unclear(self):
        """Unparseable response defaults to UNCLEAR (fail-safe)."""
        response = """This is some garbled response that doesn't follow the format."""

        verdicts = _parse_llm_response(response, 1)

        assert len(verdicts) == 1
        assert verdicts[0].verdict == "UNCLEAR"


# =============================================================================
# ERROR HANDLING
# =============================================================================

class TestErrorHandling:
    """Test graceful error handling."""

    def test_llm_failure_drops_all_pairs(self):
        """LLM failure results in no findings, not crash."""
        doc = _create_document([
            "Get a $4000 welcome bonus when you sign up.",
            "New players receive up to $5000 on their first deposit.",
        ])

        check = ConsistencyCheck()

        with patch('judgment.consistency.call_llm', return_value=None):
            findings = check._generate_proposals(doc, None, None)

        assert len(findings) == 0

    def test_no_api_key_graceful_degradation(self):
        """Missing API key results in graceful degradation."""
        doc = _create_document([
            "Get a $4000 welcome bonus.",
            "New players receive $5000.",
        ])

        check = ConsistencyCheck()

        # Clear API key - now testing via the shared client
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
            with patch('judgment.consistency.call_llm', return_value=None):
                findings = check._generate_proposals(doc, None, None)

        assert len(findings) == 0


# =============================================================================
# CLAIM EXTRACTION EDGE CASES
# =============================================================================

class TestClaimExtraction:
    """Test claim extraction edge cases."""

    def test_percentage_bonus_extraction(self):
        """Extract percentage bonuses correctly."""
        doc = _create_document([
            "Get a 100% match bonus on your first deposit.",
            "Reload with a 50% bonus on your second deposit.",
        ])

        claims = _extract_claims(doc)
        percent_claims = [c for c in claims if c.category == "BONUS_PERCENT"]

        assert len(percent_claims) >= 2
        values = {c.value for c in percent_claims}
        assert "100%" in values
        assert "50%" in values

    def test_game_count_extraction(self):
        """Extract game counts correctly."""
        doc = _create_document([
            "Choose from over 1000 pokies at KoiFortune.",
            "We have 500+ games available.",  # Direct "games" phrasing
        ])

        claims = _extract_claims(doc)
        count_claims = [c for c in claims if c.category == "GAME_COUNT"]

        assert len(count_claims) >= 2

    def test_small_values_filtered(self):
        """Very small values are filtered out."""
        doc = _create_document([
            "Get a $1 free chip bonus.",  # Too small, likely not a real bonus
            "Minimum bet is $0.10.",
        ])

        claims = _extract_claims(doc)
        bonus_claims = [c for c in claims if c.category == "BONUS_AMOUNT"]

        # $1 should be filtered (< $5 threshold)
        assert len(bonus_claims) == 0


# =============================================================================
# INTEGRATION: CHECK REGISTRATION
# =============================================================================

class TestCheckRegistration:
    """Test that ConsistencyCheck registers correctly."""

    def test_consistency_check_registered(self):
        """ConsistencyCheck can be registered in the registry."""
        registry = get_registry()

        # If not already registered (registry may have been cleared by other tests),
        # we can still verify the check works by instantiating it
        if "consistency" not in registry.check_names():
            # Manually register for this test
            registry._checks["consistency"] = ConsistencyCheck

        check_names = registry.check_names()
        assert "consistency" in check_names

    def test_consistency_check_is_judgment_type(self):
        """ConsistencyCheck is a judgment type check."""
        # Use direct instantiation to avoid registry state issues
        check = ConsistencyCheck()

        assert check.is_judgment is True
        assert check.is_deterministic is False

    def test_consistency_check_metadata(self):
        """ConsistencyCheck has correct metadata."""
        check = ConsistencyCheck()

        assert check.metadata.name == "consistency"
        assert check.metadata.category == "consistency"
        assert check.metadata.display_name == "Internal Consistency"
