"""
Tests for deterministic/semantic_match.py - Semantic Heading Matching

Tests the semantic similarity matching for brief sections to article headings.
Handles both semantic (sentence-transformers) and fuzzy (fallback) modes.
"""

import pytest
from unittest.mock import patch, MagicMock

from deterministic.semantic_match import (
    fuzzy_word_overlap,
    heading_matches,
    SEMANTIC_THRESHOLD,
    SEMANTIC_AVAILABLE,
)


# =============================================================================
# FUZZY WORD OVERLAP TESTS (Always Available)
# =============================================================================

class TestFuzzyWordOverlap:
    """Tests for fuzzy_word_overlap fallback function."""

    def test_exact_match(self):
        """Exact match should return 1.0."""
        assert fuzzy_word_overlap("Payment Methods", "Payment Methods") == 1.0

    def test_subset_match(self):
        """Smaller text fully contained in larger should return 1.0."""
        result = fuzzy_word_overlap("Payment", "Payment Methods Available")
        assert result == 1.0  # "Payment" fully appears in the larger text

    def test_partial_overlap(self):
        """Partial word overlap should return proportional score."""
        # "Payment Methods" has 2 words, "Payment Options" has 1/2 overlap
        result = fuzzy_word_overlap("Payment Methods", "Payment Options")
        assert result == 0.5

    def test_no_overlap(self):
        """No word overlap should return 0.0."""
        result = fuzzy_word_overlap("Registration Process", "Deposit Options")
        assert result == 0.0

    def test_case_insensitive(self):
        """Matching should be case-insensitive."""
        result = fuzzy_word_overlap("PAYMENT METHODS", "payment methods")
        assert result == 1.0

    def test_empty_strings(self):
        """Empty strings should return 0.0."""
        assert fuzzy_word_overlap("", "Something") == 0.0
        assert fuzzy_word_overlap("Something", "") == 0.0
        assert fuzzy_word_overlap("", "") == 0.0


# =============================================================================
# HEADING MATCHES TESTS
# =============================================================================

class TestHeadingMatches:
    """Tests for heading_matches function (combined semantic + fuzzy)."""

    def test_exact_match_returns_match(self):
        """Exact text match should always match."""
        matches, score, method = heading_matches("Bonuses", "Bonuses")
        assert matches is True
        assert score >= 0.5

    def test_returns_method_info(self):
        """Should return match method (semantic, synonym, or fuzzy)."""
        _, _, method = heading_matches("Test", "Test")
        assert method in ("semantic", "synonym", "fuzzy")

    def test_fuzzy_fallback_when_semantic_unavailable(self):
        """When semantic is unavailable, should fall back to fuzzy."""
        with patch('deterministic.semantic_match._get_model', return_value=None):
            matches, score, method = heading_matches(
                "Payment Methods", "Payment Options"
            )
            assert method == "fuzzy"
            # 50% word overlap should match with default fuzzy threshold
            assert matches is True

    def test_no_match_for_unrelated_headings(self):
        """Completely unrelated headings should not match."""
        matches, score, method = heading_matches(
            "Customer Support", "Registration Process"
        )
        # Should not match regardless of method
        assert matches is False or score < SEMANTIC_THRESHOLD


# =============================================================================
# SEMANTIC MATCHING TESTS (Conditional on Availability)
# =============================================================================

@pytest.mark.skipif(not SEMANTIC_AVAILABLE, reason="sentence-transformers not installed")
class TestSemanticMatching:
    """Tests that require sentence-transformers to be installed."""

    def test_reworded_heading_matches(self):
        """Semantically similar headings should match."""
        from deterministic.semantic_match import semantic_similarity

        # These are semantically related but have zero word overlap
        score = semantic_similarity("Registration Process", "How to Sign Up")
        assert score is not None
        # Should have reasonable similarity
        assert score > 0.4, f"Expected similarity > 0.4, got {score}"

    def test_synonymous_concepts_match(self):
        """Synonym-based variations should match."""
        from deterministic.semantic_match import semantic_similarity

        score = semantic_similarity("Payment Methods", "Banking Options")
        assert score is not None
        # Synonymous concepts should have reasonable similarity
        assert score > 0.3, f"Expected similarity > 0.3, got {score}"

    def test_unrelated_concepts_low_score(self):
        """Unrelated concepts should have low similarity."""
        from deterministic.semantic_match import semantic_similarity

        score = semantic_similarity("Customer Support", "Welcome Bonus")
        assert score is not None
        # Unrelated should be < 0.5
        assert score < 0.5, f"Expected similarity < 0.5, got {score}"

    def test_semantic_threshold_default(self):
        """Default semantic threshold should be 0.45 (validated on HellSpin brief)."""
        assert SEMANTIC_THRESHOLD == 0.45

    def test_heading_matches_uses_semantic(self):
        """heading_matches should use semantic method when available."""
        _, _, method = heading_matches("Registration", "Sign Up")
        assert method == "semantic"


# =============================================================================
# THRESHOLD TESTS
# =============================================================================

class TestThresholds:
    """Tests for matching thresholds."""

    def test_fuzzy_threshold_50_percent(self):
        """Default fuzzy threshold is 50% word overlap."""
        # 1/2 words overlap = 50% = should match
        matches, score, _ = heading_matches(
            "Payment Methods", "Payment Options",
            fuzzy_threshold=0.5
        )
        # With fuzzy fallback, 50% overlap should match
        if not SEMANTIC_AVAILABLE:
            assert matches is True

    def test_custom_semantic_threshold(self):
        """Custom semantic threshold should be respected."""
        # With very high threshold, even similar text shouldn't match
        matches, score, _ = heading_matches(
            "Bonuses", "Promotions",
            semantic_threshold=0.99  # Very strict
        )
        if SEMANTIC_AVAILABLE:
            assert matches is False or score >= 0.99

    def test_custom_fuzzy_threshold(self):
        """Custom fuzzy threshold should be respected."""
        # With strict fuzzy threshold, partial overlap won't match
        with patch('deterministic.semantic_match._get_model', return_value=None):
            matches, score, method = heading_matches(
                "Payment Methods", "Payment Options",
                fuzzy_threshold=0.75  # Stricter than 50%
            )
            assert method == "fuzzy"
            # 50% overlap < 75% threshold = no match
            assert matches is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for realistic heading matching scenarios."""

    def test_casino_section_variations(self):
        """Test realistic casino article section variations."""
        test_cases = [
            # (brief_section, article_heading, should_match_description)
            ("Bonuses", "Welcome Bonuses and Promotions", "substring match"),
            ("Payment Methods", "How to Deposit", "may or may not match"),
            ("Customer Support", "Getting Help", "synonym match"),
            ("Mobile Casino", "Play on the Go", "concept match"),
        ]

        for brief, article, desc in test_cases:
            matches, score, method = heading_matches(brief, article)
            # Just verify it doesn't crash
            assert isinstance(matches, bool)
            assert 0 <= score <= 1
            assert method in ("semantic", "synonym", "fuzzy")

    def test_all_metadata_headings_excluded(self):
        """
        These metadata-style headings should NOT be real section requirements.
        The brief parser should filter these, but matching should handle gracefully.
        """
        metadata_labels = [
            "Main keywords",
            "Support keywords",
            "LSI keywords",
            "Word Count",
            "Meta Description",
            "Title Tag",
        ]

        for label in metadata_labels:
            # These shouldn't match regular article headings
            matches, score, _ = heading_matches(
                label, "Welcome to Our Casino"
            )
            # Score should be low for unrelated concepts
            assert score < 0.7, f"Metadata label '{label}' scored too high: {score}"


# =============================================================================
# SYNONYM MATCHING TESTS
# =============================================================================

class TestSynonymMatching:
    """Tests for domain-specific synonym matching."""

    def test_slots_pokies_synonym(self):
        """slots↔pokies should match via synonym table (regional slang)."""
        matches, score, method = heading_matches("Slots", "HellSpin Pokies")
        assert matches is True
        assert method == "synonym"
        assert score == 1.0

    def test_live_realtime_synonym(self):
        """live↔real-time should match via synonym table."""
        matches, score, method = heading_matches("Live Section", "Real-Time Action")
        assert matches is True
        assert method == "synonym"

    def test_withdrawal_payout_synonym(self):
        """withdrawal↔payout should match via synonym table."""
        matches, score, method = heading_matches("Withdrawal Methods", "Fast Payout Options")
        assert matches is True
        assert method == "synonym"

    def test_synonym_case_insensitive(self):
        """Synonym matching should be case-insensitive."""
        matches, score, method = heading_matches("SLOTS", "pokies")
        assert matches is True
        assert method == "synonym"

    def test_no_synonym_for_unrelated(self):
        """Unrelated terms should not match via synonyms."""
        matches, score, method = heading_matches("Bonuses", "Customer Support")
        assert method != "synonym"  # Should use semantic or fuzzy


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_empty_strings_no_crash(self):
        """Empty strings should not crash."""
        matches, score, method = heading_matches("", "Something")
        assert isinstance(matches, bool)

        matches, score, method = heading_matches("Something", "")
        assert isinstance(matches, bool)

    def test_unicode_handling(self):
        """Unicode characters should be handled gracefully."""
        matches, score, method = heading_matches(
            "Café Menu",
            "Restaurant Menu"
        )
        assert isinstance(matches, bool)

    def test_special_characters(self):
        """Special characters should not crash matching."""
        matches, score, method = heading_matches(
            "100% Bonus!",
            "Welcome Bonus 100%"
        )
        assert isinstance(matches, bool)
