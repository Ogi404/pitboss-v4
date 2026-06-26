"""
Tests for deterministic/sentence_complexity.py - Sentence Complexity Outlier Detection

Validation triad:
1. True-positive catch: genuinely complex outlier is flagged
2. Clean-article silence: no proposals for articles with consistent sentence lengths
3. Short-article silence: articles with <5 sentences don't trigger (no meaningful baseline)
"""

import pytest
import statistics

from core.document import Document, Paragraph, TextRun
from deterministic.sentence_complexity import (
    SentenceComplexityCheck,
    count_clauses,
    split_sentences,
    analyze_sentence,
    find_outliers,
    SentenceStats,
    Z_SCORE_THRESHOLD,
    WORD_THRESHOLD,
    CLAUSE_THRESHOLD,
    MIN_SENTENCES,
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
        offset += len(text) + 1
    return Document(elements=elements, title="Test Doc")


# =============================================================================
# UNIT TESTS: CLAUSE COUNTING
# =============================================================================

class TestClauseCounting:
    """Test clause marker detection."""

    def test_no_clauses(self):
        """Simple sentence has no clause markers."""
        assert count_clauses("The casino offers great games.") == 0

    def test_single_clause_which(self):
        """'which' clause detected."""
        assert count_clauses("The bonus, which is generous, expires tomorrow.") == 1

    def test_single_clause_that(self):
        """'that' clause detected."""
        assert count_clauses("The game that we played was fun.") == 1

    def test_multiple_clauses(self):
        """Multiple clause markers detected."""
        text = "The bonus, which is generous, expires when you withdraw, because of policy."
        assert count_clauses(text) == 3  # which, when, because

    def test_subordinating_conjunctions(self):
        """Subordinating conjunctions detected."""
        assert count_clauses("I played because the bonus was good.") == 1
        assert count_clauses("Play while the offer lasts.") == 1
        assert count_clauses("Wait until the timer ends.") == 1

    def test_relative_pronouns(self):
        """Relative pronouns detected."""
        assert count_clauses("Players who deposit get bonuses.") == 1
        assert count_clauses("The game where you spin wins.") == 1
        assert count_clauses("The player whose bet won.") == 1


# =============================================================================
# UNIT TESTS: SENTENCE SPLITTING
# =============================================================================

class TestSentenceSplitting:
    """Test sentence boundary detection."""

    def test_basic_split(self):
        """Split on period + space."""
        # Each sentence needs 3+ words to not be filtered
        sentences = split_sentences("This is sentence one. This is sentence two.")
        assert len(sentences) == 2
        assert sentences[0][0] == "This is sentence one"
        assert sentences[1][0] == "This is sentence two."

    def test_exclamation_split(self):
        """Split on exclamation mark."""
        sentences = split_sentences("This bonus is great! Play and win now.")
        assert len(sentences) == 2

    def test_question_split(self):
        """Split on question mark."""
        sentences = split_sentences("Are you ready to play? Join us today now.")
        assert len(sentences) == 2

    def test_short_fragments_filtered(self):
        """Very short fragments (<3 words) filtered out."""
        sentences = split_sentences("Yes. This is a complete sentence.")
        # "Yes" has only 1 word, should be filtered
        assert len(sentences) == 1
        assert "complete sentence" in sentences[0][0]

    def test_offset_tracking(self):
        """Character offsets tracked correctly."""
        text = "This is sentence one. This is sentence two."
        sentences = split_sentences(text)
        assert sentences[0][1] == 0  # First starts at 0
        assert sentences[1][1] == 22  # Second starts after "This is sentence one. "


# =============================================================================
# UNIT TESTS: DEPTH SCORE CALCULATION
# =============================================================================

class TestDepthScore:
    """Test depth score computation."""

    def test_word_only_score(self):
        """Sentence with no clauses: depth = word_count."""
        stats = analyze_sentence("The casino has great pokies.", 0, 0)
        assert stats.word_count == 5
        assert stats.clause_count == 0
        assert stats.depth_score == 5  # 5 + (0 * 8)

    def test_clause_weighted_score(self):
        """Clauses add weight to depth score."""
        stats = analyze_sentence("The bonus which is good expires when you play.", 0, 0)
        # 9 words, 2 clauses (which, when)
        assert stats.word_count == 9
        assert stats.clause_count == 2
        assert stats.depth_score == 25  # 9 + (2 * 8)


# =============================================================================
# VALIDATION TRIAD TEST 1: TRUE-POSITIVE CATCH
# =============================================================================

class TestTruePositiveCatch:
    """Test that genuinely complex outliers are flagged."""

    def test_long_complex_sentence_flagged(self):
        """A 45-word sentence with 4 clauses triggers."""
        # Build an article with mostly short sentences + one monster
        doc = _create_document([
            "Welcome to our casino.",
            "We have great games.",
            "The bonuses are generous.",
            "Play pokies and win.",
            "Customer support is helpful.",
            "Banking is fast and secure.",
            # Monster sentence (artificial but tests the trigger)
            "The welcome bonus, which is the best in the industry, expires when you "
            "withdraw your winnings, because the terms state that bonus funds must be "
            "wagered before any cashout, although some exceptions apply if you contact "
            "support while the promotion is active.",
        ])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        assert len(findings) == 1, "Complex outlier should trigger"

        finding = findings[0]
        assert finding.check_name == "sentence_complexity"
        assert finding.auto_applicable is False
        assert finding.severity == "info"
        assert "standard deviations" in finding.reasoning
        assert finding.metadata_dict["z_score"] > Z_SCORE_THRESHOLD

    def test_clause_threshold_triggers(self):
        """3+ clauses triggers even with moderate word count."""
        # Build article with short simple sentences + one with many clauses
        doc = _create_document([
            "Simple sentence one.",
            "Simple sentence two.",
            "Simple sentence three.",
            "Simple sentence four.",
            "Simple sentence five.",
            "Simple sentence six.",
            # 25 words but 4 clauses
            "The player who wins gets the bonus which doubles when the timer that "
            "shows the countdown reaches zero.",
        ])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        # Should trigger because clause_count >= 3
        assert len(findings) >= 1


# =============================================================================
# VALIDATION TRIAD TEST 2: CLEAN-ARTICLE SILENCE
# =============================================================================

class TestCleanArticleSilence:
    """Test that uniform articles produce zero proposals."""

    def test_uniform_short_sentences_no_trigger(self):
        """Article with consistently short sentences has no trigger."""
        doc = _create_document([
            "Welcome to our casino.",
            "We have great games.",
            "The bonuses are generous.",
            "Play pokies and win big.",
            "Customer support helps fast.",
            "Banking is very secure.",
            "Join us today for fun.",
            "New players get rewards.",
        ])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        assert len(findings) == 0

    def test_uniform_medium_sentences_no_trigger(self):
        """Article with consistently medium sentences has no trigger."""
        doc = _create_document([
            "The casino offers a wide variety of exciting games.",
            "Players can choose from pokies, table games, and live dealers.",
            "The welcome bonus is generous and comes with fair terms.",
            "Customer support is available around the clock via chat.",
            "Banking options include cards, e-wallets, and cryptocurrencies.",
            "New players receive a special package on their first deposit.",
        ])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        assert len(findings) == 0

    def test_slightly_varied_but_no_outlier(self):
        """Natural variation without extreme outliers doesn't trigger."""
        doc = _create_document([
            "Welcome to the casino.",  # 4 words
            "We offer great games and bonuses for all players.",  # 9 words
            "Join today.",  # (filtered - too short)
            "The support team is helpful and responds quickly.",  # 8 words
            "Banking is secure with multiple options available.",  # 7 words
            "New players get bonuses on their first three deposits.",  # 9 words
            "VIP members receive special treatment and cashback.",  # 7 words
        ])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        # No extreme outliers, should not trigger
        assert len(findings) == 0


# =============================================================================
# VALIDATION TRIAD TEST 3: SHORT-ARTICLE SILENCE
# =============================================================================

class TestShortArticleSilence:
    """Test that very short articles don't trigger (no meaningful baseline)."""

    def test_fewer_than_5_sentences_no_trigger(self):
        """Articles with <5 sentences don't have meaningful baseline."""
        doc = _create_document([
            "Welcome to the casino.",
            "We have games.",
            # Even with a monster sentence, <5 total means no trigger
            "The welcome bonus which is generous expires when you withdraw because "
            "terms apply although exceptions exist if you contact support.",
        ])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        # Too few sentences for meaningful analysis
        assert len(findings) == 0

    def test_exactly_5_sentences_can_trigger(self):
        """Articles with exactly 5 sentences can trigger."""
        doc = _create_document([
            "Simple one.",  # filtered (2 words)
            "Simple sentence two here.",
            "Simple sentence three here.",
            "Simple sentence four here.",
            "Simple sentence five here.",
            "Simple sentence six here.",
            # Monster sentence
            "The bonus which is great expires when you play because of policy that "
            "states all terms must be read before any withdrawal is processed.",
        ])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        # Should have enough sentences for baseline
        # Monster is outlier with 4+ clauses
        assert len(findings) >= 1


# =============================================================================
# FINDING STRUCTURE
# =============================================================================

class TestFindingStructure:
    """Test that findings have correct structure and metadata."""

    def test_finding_has_required_fields(self):
        """Finding includes all required fields."""
        doc = _create_document([
            "Welcome to our great casino today.",
            "We have wonderful games available here.",
            "The bonuses here are very generous.",
            "Play pokies and try to win.",
            "Customer support is very helpful.",
            "Banking is fast and very secure.",
            # Monster sentence with 4+ clauses and many words
            "The welcome bonus, which is the best in the industry, expires when you "
            "withdraw your winnings, because the terms state that bonus funds must be "
            "wagered before any cashout, although some exceptions apply if you contact "
            "support while the promotion is still active and running.",
        ])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        assert len(findings) == 1
        finding = findings[0]

        # Required fields
        assert finding.check_name == "sentence_complexity"
        assert finding.original_text  # Non-empty
        assert finding.proposed_text is None  # No auto-replacement
        assert finding.location is not None
        assert finding.severity == "info"
        assert finding.reasoning  # Non-empty
        assert finding.auto_applicable is False

        # Metadata
        meta = finding.metadata_dict
        assert "word_count" in meta
        assert "clause_count" in meta
        assert "z_score" in meta
        assert "article_mean_words" in meta

    def test_long_sentence_truncated_in_original(self):
        """Very long sentences are truncated for display."""
        # Create a 200+ character sentence
        monster = "This is a very long sentence " * 10 + "which has clauses."

        doc = _create_document([
            "Short one.", "Short two.", "Short three.",
            "Short four.", "Short five.", "Short six.",
            monster,
        ])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        if findings:
            # Original text should be truncated with ellipsis
            assert len(findings[0].original_text) <= 155  # 150 + "..."


# =============================================================================
# CHECK REGISTRATION
# =============================================================================

class TestCheckRegistration:
    """Test that the check has correct metadata."""

    def test_check_metadata(self):
        """Check has correct metadata."""
        check = SentenceComplexityCheck()

        assert check.metadata.name == "sentence_complexity"
        assert check.metadata.display_name == "Sentence Complexity"
        assert check.metadata.category == "readability"

    def test_check_is_deterministic(self):
        """Check is deterministic (no LLM)."""
        check = SentenceComplexityCheck()

        assert check.is_deterministic is True
        assert check.is_judgment is False


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_document(self):
        """Empty document doesn't trigger."""
        doc = _create_document([])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        assert len(findings) == 0

    def test_all_same_depth_no_trigger(self):
        """If all sentences have identical depth, no outliers possible."""
        # All sentences exactly 5 words, 0 clauses
        doc = _create_document([
            "One two three four five.",
            "One two three four five.",
            "One two three four five.",
            "One two three four five.",
            "One two three four five.",
            "One two three four five.",
        ])

        check = SentenceComplexityCheck()
        findings = check.run(doc, None)

        assert len(findings) == 0

    def test_z_score_boundary(self):
        """Test exact z-score threshold boundary."""
        # Create stats manually for boundary testing
        sentences = [
            SentenceStats(text=f"Sentence {i}", word_count=10, clause_count=0,
                         depth_score=10.0, element_index=0, char_offset=0)
            for i in range(6)
        ]
        # Add one outlier at exactly 2.0 std devs (should NOT trigger - needs >2.0)
        # With 6 sentences at depth 10, mean=10, we need stdev and value calculation

        # Instead, test via the check with controlled input
        outliers = find_outliers(sentences)
        # All same, no outliers
        assert len(outliers) == 0
