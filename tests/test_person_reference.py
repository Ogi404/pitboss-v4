"""
Tests for the person reference classifier.

Tests cover:
- READER_REF: Modal verbs, direct address patterns
- GENERIC_NOUN: Adjective-qualified, behavioral, quantity framing
- UNCLEAR: Ambiguous cases
- Multiple references in same sentence
- count_person_references function
"""

import pytest
from core.person_reference import (
    PersonRefType,
    PersonReference,
    classify_person_references,
    classify_person_reference_simple,
    count_person_references,
)


class TestReaderRefClassification:
    """Tests for READER_REF classification."""

    def test_modal_verb_can(self):
        """'players can claim' → READER_REF"""
        refs = classify_person_references("Players can claim the bonus today.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_modal_verb_must(self):
        """'players must verify' → READER_REF"""
        refs = classify_person_references("Players must verify their account.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_modal_verb_should(self):
        """'players should check' → READER_REF"""
        refs = classify_person_references("Players should check the terms.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_modal_verb_will(self):
        """'players will receive' → READER_REF"""
        refs = classify_person_references("Players will receive their bonus.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_modal_verb_may(self):
        """'users may withdraw' → READER_REF"""
        refs = classify_person_references("Users may withdraw at any time.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_modal_verb_need_to(self):
        """'players need to register' → READER_REF"""
        refs = classify_person_references("Players need to register first.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_are_allowed(self):
        """'players are allowed to' → READER_REF"""
        refs = classify_person_references("Players are allowed to withdraw daily.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_are_required(self):
        """'users are required to' → READER_REF"""
        refs = classify_person_references("Users are required to verify identity.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_are_expected(self):
        """'players are expected to' → READER_REF"""
        refs = classify_person_references("Players are expected to follow rules.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_gives_players(self):
        """'gives players' → READER_REF"""
        refs = classify_person_references("The package gives players up to €200.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_allows_users(self):
        """'allows users' → READER_REF"""
        refs = classify_person_references("This feature allows users to withdraw.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_lets_players(self):
        """'lets players' → READER_REF"""
        refs = classify_person_references("The system lets players track progress.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_helps_users(self):
        """'helps users' → READER_REF"""
        refs = classify_person_references("This tool helps users manage settings.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_offers_players(self):
        """'offers players' → READER_REF"""
        refs = classify_person_references("The casino offers players free spins.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_conditional_if_players(self):
        """'if players deposit' → READER_REF"""
        refs = classify_person_references("If players deposit €50, they get bonus.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_simply_need(self):
        """'players simply need to' → READER_REF"""
        refs = classify_person_references("Players simply need to click the button.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_first_need(self):
        """'users first need to' → READER_REF"""
        refs = classify_person_references("Users first need to create an account.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF

    def test_also_can(self):
        """'players also can' → READER_REF"""
        refs = classify_person_references("Players also can access live games.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF


class TestGenericNounClassification:
    """Tests for GENERIC_NOUN classification."""

    # Adjective-qualified populations

    def test_new_players(self):
        """'new players' → GENERIC_NOUN"""
        refs = classify_person_references("The bonus is designed for new players.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_experienced_players(self):
        """'experienced players' → GENERIC_NOUN"""
        refs = classify_person_references("Experienced players prefer high volatility.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_regular_players(self):
        """'regular players' → GENERIC_NOUN"""
        refs = classify_person_references("Regular players earn more points.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_casual_players(self):
        """'casual players' → GENERIC_NOUN"""
        refs = classify_person_references("Casual players enjoy simple games.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_slot_players(self):
        """'slot players' → GENERIC_NOUN"""
        refs = classify_person_references("This appeals to slot players worldwide.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_vip_players(self):
        """'VIP players' → GENERIC_NOUN"""
        refs = classify_person_references("VIP players receive exclusive rewards.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_loyal_customers(self):
        """'loyal customers' → GENERIC_NOUN"""
        refs = classify_person_references("Loyal customers get special treatment.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_active_users(self):
        """'active users' → GENERIC_NOUN"""
        refs = classify_person_references("Active users benefit most from this.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    # Geographic/demographic

    def test_players_from_canada(self):
        """'players from Canada' → GENERIC_NOUN"""
        refs = classify_person_references("Players from Canada are welcome.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_canadian_players(self):
        """'Canadian players' → GENERIC_NOUN"""
        refs = classify_person_references("Canadian players have many options.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_australian_users(self):
        """'Australian users' → GENERIC_NOUN"""
        refs = classify_person_references("Australian users prefer fast payouts.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    # Quantity framing

    def test_most_players(self):
        """'most players' → GENERIC_NOUN"""
        refs = classify_person_references("Most players enjoy this feature.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_many_players(self):
        """'many players' → GENERIC_NOUN"""
        refs = classify_person_references("Many players prefer live games.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_some_users(self):
        """'some users' → GENERIC_NOUN"""
        refs = classify_person_references("Some users report issues.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_thousands_of_players(self):
        """'thousands of players' → GENERIC_NOUN"""
        refs = classify_person_references("Thousands of players enjoy this game.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_number_of_players(self):
        """'number of players' → GENERIC_NOUN"""
        refs = classify_person_references("The number of players is growing.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    # Behavioral observations

    def test_players_usually(self):
        """'players usually' → GENERIC_NOUN"""
        refs = classify_person_references("Players usually prefer faster withdrawals.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_players_often(self):
        """'players often' → GENERIC_NOUN"""
        refs = classify_person_references("Players often choose slots first.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_players_prefer(self):
        """'players prefer' → GENERIC_NOUN"""
        refs = classify_person_references("Players prefer simple interfaces.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_players_tend_to(self):
        """'players tend to' → GENERIC_NOUN"""
        refs = classify_person_references("Players tend to stay longer here.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_players_who_like(self):
        """'players who like' → GENERIC_NOUN"""
        refs = classify_person_references("Players who like slots will enjoy this.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_players_who_prefer(self):
        """'players who prefer' → GENERIC_NOUN"""
        refs = classify_person_references("Players who prefer crypto have options.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    # Attraction/design framing

    def test_attracts_players(self):
        """'attracts players' → GENERIC_NOUN"""
        refs = classify_person_references("The casino attracts players worldwide.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_appeals_to_players(self):
        """'appeals to players' → GENERIC_NOUN"""
        refs = classify_person_references("This appeals to players seeking bonuses.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_designed_for_players(self):
        """'designed for players' → GENERIC_NOUN"""
        refs = classify_person_references("The app is designed for players on mobile.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    # Possessive/data contexts

    def test_player_journey(self):
        """'player's journey' → GENERIC_NOUN"""
        refs = classify_person_references("Throughout the player's journey here.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_player_data(self):
        """'player's data' → GENERIC_NOUN"""
        refs = classify_person_references("We protect the player's data carefully.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_player_activity(self):
        """'player's activity' → GENERIC_NOUN"""
        refs = classify_person_references("We monitor player's activity for safety.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    # Compound nouns - player/user as modifier

    def test_player_protection(self):
        """'player protection' → GENERIC_NOUN (compound noun)"""
        refs = classify_person_references("Standards for player protection apply here.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_player_safety(self):
        """'player safety' → GENERIC_NOUN (compound noun)"""
        refs = classify_person_references("Player safety is our top priority.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_player_support(self):
        """'player support' → GENERIC_NOUN (compound noun)"""
        refs = classify_person_references("The player support team is available 24/7.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_player_friendly_hyphenated(self):
        """'player-friendly' → GENERIC_NOUN (hyphenated compound)"""
        refs = classify_person_references("This is a player-friendly interface.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_user_engagement(self):
        """'user engagement' → GENERIC_NOUN (compound noun)"""
        refs = classify_person_references("The site focuses on user engagement.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    # Platform/device qualifiers

    def test_android_users(self):
        """'Android users' → GENERIC_NOUN (platform qualifier)"""
        refs = classify_person_references("Android users can install the PWA.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_ios_players(self):
        """'iOS players' → GENERIC_NOUN (platform qualifier)"""
        refs = classify_person_references("iOS players prefer the app store version.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_desktop_users(self):
        """'desktop users' → GENERIC_NOUN (platform qualifier)"""
        refs = classify_person_references("Desktop users have more screen space.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_app_users(self):
        """'app users' → GENERIC_NOUN (platform qualifier)"""
        refs = classify_person_references("App users get notifications.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN


class TestUnclearClassification:
    """Tests for UNCLEAR classification."""

    def test_standalone_players(self):
        """'Players.' alone → UNCLEAR"""
        refs = classify_person_references("Players.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.UNCLEAR

    def test_players_get_ambiguous(self):
        """'Players get benefits' → UNCLEAR (ambiguous verb)"""
        refs = classify_person_references("Players get benefits here.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.UNCLEAR

    def test_players_have_access(self):
        """'Players have access' → UNCLEAR (could be either)"""
        refs = classify_person_references("Players have access to games.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.UNCLEAR

    def test_weak_context(self):
        """Weak context without clear signals → UNCLEAR"""
        refs = classify_person_references("The players are here.")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.UNCLEAR


class TestMultipleReferences:
    """Tests for sentences with multiple references."""

    def test_two_generic_nouns(self):
        """Two generic noun references"""
        text = "New players and experienced players both enjoy this."
        refs = classify_person_references(text)
        assert len(refs) == 2
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN
        assert refs[1].ref_type == PersonRefType.GENERIC_NOUN

    def test_mixed_generic_and_reader(self):
        """Mixed generic and reader-ref"""
        text = "New players can claim the welcome bonus."
        refs = classify_person_references(text)
        assert len(refs) == 1
        # "new players" should be GENERIC (adjective trumps modal)
        assert refs[0].ref_type == PersonRefType.GENERIC_NOUN

    def test_reader_ref_then_generic(self):
        """Reader-ref followed by generic"""
        text = "Players must verify before most players can withdraw."
        refs = classify_person_references(text)
        assert len(refs) == 2
        assert refs[0].ref_type == PersonRefType.READER_REF
        assert refs[1].ref_type == PersonRefType.GENERIC_NOUN

    def test_multiple_different_words(self):
        """Different third-person words in same sentence"""
        text = "Users can register and customers will receive bonuses."
        refs = classify_person_references(text)
        assert len(refs) == 2
        assert refs[0].ref_type == PersonRefType.READER_REF
        assert refs[1].ref_type == PersonRefType.READER_REF


class TestCountPersonReferences:
    """Tests for count_person_references function."""

    def test_count_single_sentence(self):
        """Count in single sentence"""
        reader, generic, unclear = count_person_references(
            "Players can claim the bonus."
        )
        assert reader == 1
        assert generic == 0
        assert unclear == 0

    def test_count_multiple_sentences(self):
        """Count across multiple sentences"""
        text = """
        Players can claim the bonus. New players are welcome.
        The casino attracts experienced players worldwide.
        """
        reader, generic, unclear = count_person_references(text)
        assert reader >= 1  # "can claim"
        assert generic >= 2  # "new players", "experienced players"

    def test_count_empty_text(self):
        """Empty text returns zeros"""
        reader, generic, unclear = count_person_references("")
        assert reader == 0
        assert generic == 0
        assert unclear == 0

    def test_count_no_references(self):
        """Text without third-person refs"""
        reader, generic, unclear = count_person_references(
            "You can claim the bonus today."
        )
        assert reader == 0
        assert generic == 0
        assert unclear == 0

    def test_count_all_categories(self):
        """Count including unclear"""
        text = """
        Players can claim bonuses. Most players enjoy this.
        Players are here.
        """
        reader, generic, unclear = count_person_references(text)
        assert reader >= 1
        assert generic >= 1
        assert unclear >= 1


class TestSimpleClassification:
    """Tests for classify_person_reference_simple function."""

    def test_returns_types_only(self):
        """Returns just PersonRefType enums"""
        types = classify_person_reference_simple("Players can claim the bonus.")
        assert len(types) == 1
        assert types[0] == PersonRefType.READER_REF
        assert isinstance(types[0], PersonRefType)

    def test_multiple_types(self):
        """Multiple types returned"""
        types = classify_person_reference_simple(
            "New players can claim bonuses for all players."
        )
        assert len(types) == 2


class TestPersonReferenceDataclass:
    """Tests for PersonReference dataclass."""

    def test_has_word(self):
        """PersonReference has word field"""
        refs = classify_person_references("Players can claim bonus.")
        assert refs[0].word == "players"

    def test_has_positions(self):
        """PersonReference has position fields"""
        refs = classify_person_references("Players can claim bonus.")
        assert refs[0].start_pos == 0
        assert refs[0].end_pos == 7

    def test_has_context(self):
        """PersonReference has context field"""
        refs = classify_person_references("The casino gives players free spins.")
        assert "players" in refs[0].context.lower()

    def test_context_truncated_long_sentence(self):
        """Context is truncated for long sentences"""
        text = "A" * 50 + " players " + "B" * 50
        refs = classify_person_references(text)
        assert len(refs[0].context) < len(text)
        assert "..." in refs[0].context


class TestEdgeCases:
    """Tests for edge cases."""

    def test_case_insensitive(self):
        """Classification is case-insensitive"""
        refs1 = classify_person_references("PLAYERS can claim.")
        refs2 = classify_person_references("players can claim.")
        refs3 = classify_person_references("Players can claim.")
        assert refs1[0].ref_type == refs2[0].ref_type == refs3[0].ref_type

    def test_different_third_person_words(self):
        """All third-person words are detected"""
        words = ["player", "players", "user", "users", "punter", "punters",
                 "bettor", "bettors", "customer", "customers", "gambler", "gamblers"]
        for word in words:
            refs = classify_person_references(f"{word.title()} can claim bonus.")
            assert len(refs) == 1, f"Failed for {word}"

    def test_word_boundaries(self):
        """Only matches whole words, not substrings"""
        # "splayer" should not match "player"
        refs = classify_person_references("The splayer is here.")
        assert len(refs) == 0

    def test_punctuation_handling(self):
        """Handles punctuation around words"""
        refs = classify_person_references("(Players) can claim!")
        assert len(refs) == 1
        assert refs[0].ref_type == PersonRefType.READER_REF
