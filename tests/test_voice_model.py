"""
Tests for core/voice_model.py - Layered Voice Model Builder

Tests:
- Fingerprint extraction (sentence length, person ratio, etc.)
- Model builder (house, type, brand layers)
- Brand threshold enforcement
- Blend helper
- Corpus indexer
- Docx reader
"""

import pytest
from pathlib import Path
import shutil
import tempfile

from core.voice_model import (
    # Text analysis utilities
    split_sentences,
    count_words,
    detect_person,
    is_title_case,
    detect_heading_case,
    extract_sentence_openers,
    extract_transitions,
    compute_punctuation_density,
    extract_stop_word_usage,
    infer_article_type,
    # Dataclasses
    VoiceFingerprint,
    VoiceModel,
    BuildResult,
    # Builder
    FingerprintBuilder,
    VoiceModelBuilder,
    # Corpus index
    generate_corpus_index,
    load_corpus_index,
    # Blend helper
    get_voice_layers,
    available_layers,
)
from core.document import Document, Paragraph, Heading, HeadingLevel
from ingest.docx_reader import read_docx, read_docx_text_only, get_docx_headings


# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestSplitSentences:
    """Tests for sentence splitting."""

    def test_simple_sentences(self):
        """Test splitting simple sentences."""
        text = "Hello world. This is a test. Another sentence here."
        sentences = split_sentences(text)
        assert len(sentences) == 3

    def test_handles_abbreviations(self):
        """Test that abbreviations don't cause false splits."""
        text = "Dr. Smith went to the store. He bought milk."
        sentences = split_sentences(text)
        assert len(sentences) == 2

    def test_handles_decimals(self):
        """Test that decimals don't cause false splits."""
        text = "The bonus is 100.50 dollars. That is a good deal."
        sentences = split_sentences(text)
        assert len(sentences) == 2

    def test_empty_text(self):
        """Test empty text returns empty list."""
        assert split_sentences("") == []
        assert split_sentences("   ") == []


class TestCountWords:
    """Tests for word counting."""

    def test_simple_count(self):
        """Test basic word counting."""
        assert count_words("Hello world") == 2
        assert count_words("One two three four five") == 5

    def test_empty_text(self):
        """Test empty text returns zero."""
        assert count_words("") == 0
        assert count_words("   ") == 0


class TestDetectPerson:
    """Tests for person detection with third-person classification."""

    def test_second_person_dominant(self):
        """Test detecting second person dominance."""
        text = "You can play here. Your account is ready. You will enjoy this."
        second, reader_ref, generic_noun, unclear = detect_person(text)
        assert second > 0
        assert reader_ref + generic_noun + unclear == 0  # no third-person

    def test_third_person_present(self):
        """Test detecting third person references with classification."""
        # "Players can deposit" → READER_REF (modal verb)
        # "Users enjoy games" → GENERIC_NOUN (behavioral verb)
        # "The player wins" → UNCLEAR
        text = "Players can deposit. Users enjoy games. The player wins."
        second, reader_ref, generic_noun, unclear = detect_person(text)
        third = reader_ref + generic_noun + unclear
        assert third > 0

    def test_mixed_person(self):
        """Test mixed person usage."""
        text = "You can play. Players love this. Your experience matters."
        second, reader_ref, generic_noun, unclear = detect_person(text)
        third = reader_ref + generic_noun + unclear
        assert second > 0
        assert third > 0

    def test_ratio_calculation(self):
        """Test that ratio can be computed correctly."""
        # 4 second-person words
        text = "You can play. Your games. You win. Your bonus."
        second, reader_ref, generic_noun, unclear = detect_person(text)
        assert second == 4
        assert reader_ref + generic_noun + unclear == 0

    def test_reader_ref_classification(self):
        """Test that modal verbs classify as READER_REF."""
        text = "Players can claim the bonus. Users must verify."
        second, reader_ref, generic_noun, unclear = detect_person(text)
        assert reader_ref == 2  # both are READER_REF

    def test_generic_noun_classification(self):
        """Test that adjective-qualified references classify as GENERIC_NOUN."""
        text = "New players get bonuses. Experienced users prefer high stakes."
        second, reader_ref, generic_noun, unclear = detect_person(text)
        assert generic_noun == 2  # both are GENERIC_NOUN


class TestHeadingCase:
    """Tests for heading case detection."""

    def test_title_case_detection(self):
        """Test detecting title case headings."""
        assert is_title_case("Welcome to the Casino")
        assert is_title_case("How to Create an Account")

    def test_sentence_case_detection(self):
        """Test detecting sentence case headings."""
        assert not is_title_case("Welcome to the casino")
        assert not is_title_case("How to create an account")

    def test_heading_case_dominant_title(self):
        """Test detecting dominant title case."""
        headings = [
            "Welcome to Beta Casino",
            "Getting Started Today",
            "Main Features Available",
        ]
        style, ratio = detect_heading_case(headings)
        assert style == "title_case"
        assert ratio >= 0.7

    def test_heading_case_dominant_sentence(self):
        """Test detecting dominant sentence case."""
        headings = [
            "Welcome to beta casino",
            "Getting started today",
            "Main features available",
        ]
        style, ratio = detect_heading_case(headings)
        assert style == "sentence_case"
        assert ratio <= 0.3


class TestSentenceOpeners:
    """Tests for sentence opener extraction."""

    def test_extracts_common_openers(self):
        """Test extracting common sentence openers."""
        sentences = [
            "You can play here.",
            "You will enjoy this.",
            "You have options.",
            "We offer games.",
        ]
        openers = extract_sentence_openers(sentences, top_n=5)
        # "you" should be most common
        assert len(openers) > 0
        top_opener = openers[0][0]
        assert "you" in top_opener

    def test_rate_per_100_sentences(self):
        """Test that rates are per 100 sentences."""
        sentences = ["You can play."] * 50 + ["We offer games."] * 50
        openers = extract_sentence_openers(sentences, top_n=5)
        # Each should be ~50 per 100
        for opener, rate in openers:
            assert 40 <= rate <= 60


class TestTransitions:
    """Tests for transition extraction."""

    def test_finds_common_transitions(self):
        """Test finding predefined transitions."""
        text = "First, you sign up. However, you need to verify. Additionally, you can deposit."
        sentences = split_sentences(text)
        transitions, _ = extract_transitions(text, sentences)
        assert "however" in transitions
        assert "additionally" in transitions


class TestPunctuationDensity:
    """Tests for punctuation density calculation."""

    def test_comma_density(self):
        """Test comma density calculation."""
        text = "Hello, world, this is, a test"  # 3 commas, ~6 words
        punct = compute_punctuation_density(text, 6)
        assert punct['comma_density'] == 50.0  # 3/6 * 100

    def test_zero_words(self):
        """Test handling of zero words."""
        punct = compute_punctuation_density("", 0)
        assert punct['comma_density'] == 0.0


class TestStopWordUsage:
    """Tests for stop word detection."""

    def test_finds_hard_stop_words(self):
        """Test finding hard stop words."""
        text = "This delve into the realm of casino gaming is seamless."
        hard = ["delve", "realm", "seamless"]
        soft = ["unlock", "ensure"]
        hard_counts, soft_counts = extract_stop_word_usage(text, hard, soft)
        assert "delve" in hard_counts
        assert "realm" in hard_counts
        assert "seamless" in hard_counts

    def test_finds_soft_stop_words(self):
        """Test finding soft stop words."""
        text = "Unlock your potential and ensure great results."
        hard = ["delve"]
        soft = ["unlock", "ensure"]
        hard_counts, soft_counts = extract_stop_word_usage(text, hard, soft)
        assert "unlock" in soft_counts
        assert "ensure" in soft_counts


class TestTypeInference:
    """Tests for article type inference from filename."""

    def test_app_review_inference(self):
        """Test inferring app_review from filename."""
        assert infer_article_type("vave-mobile-app.docx") == "app_review"
        assert infer_article_type("casino-android-download.docx") == "app_review"

    def test_bonus_page_inference(self):
        """Test inferring bonus_page from filename."""
        assert infer_article_type("welcome-bonus-offer.docx") == "bonus_page"
        assert infer_article_type("no-deposit-promo.docx") == "bonus_page"

    def test_sports_market_inference(self):
        """Test inferring sports_market from filename."""
        assert infer_article_type("boxing-betting-guide.docx") == "sports_market"
        assert infer_article_type("nfl-football-markets.docx") == "sports_market"

    def test_main_review_inference(self):
        """Test inferring main_review from filename."""
        assert infer_article_type("vave-casino-review.docx") == "main_review"

    def test_fallback_to_general(self):
        """Test fallback to general for unknown types."""
        assert infer_article_type("random-content.docx") == "general"

    def test_privacy_policy_inference(self):
        """Test inferring privacy_policy from filename."""
        assert infer_article_type("privacy-policy.docx") == "privacy_policy"
        assert infer_article_type("22bet-privacy.docx") == "privacy_policy"
        assert infer_article_type("data-protection-info.docx") == "privacy_policy"

    def test_live_casino_inference(self):
        """Test inferring live_casino from filename."""
        assert infer_article_type("live-dealer-games.docx") == "live_casino"
        assert infer_article_type("live-casino-review.docx") == "live_casino"
        assert infer_article_type("live-roulette-guide.docx") == "live_casino"
        # Ensure "live chat" still maps to customer_support (more specific pattern)
        assert infer_article_type("live-chat-support.docx") == "customer_support"


class TestVoiceFingerprint:
    """Tests for VoiceFingerprint dataclass."""

    def test_serialization_roundtrip(self):
        """Test that fingerprint serializes and deserializes correctly."""
        fp = VoiceFingerprint(
            sentence_length_mean=15.5,
            sentence_length_median=14.0,
            person_ratio=25.0,
            article_count=10,
        )
        data = fp.to_dict()
        fp2 = VoiceFingerprint.from_dict(data)
        assert fp2.sentence_length_mean == 15.5
        assert fp2.person_ratio == 25.0
        assert fp2.article_count == 10


class TestVoiceModel:
    """Tests for VoiceModel dataclass."""

    def test_serialization_roundtrip(self):
        """Test model serialization."""
        fp = VoiceFingerprint(article_count=5)
        model = VoiceModel(
            layer="brand",
            layer_name="vave",
            fingerprint=fp,
            article_count=5,
        )
        json_str = model.to_json()
        model2 = VoiceModel.from_json(json_str)
        assert model2.layer == "brand"
        assert model2.layer_name == "vave"
        assert model2.article_count == 5


class TestDocxReader:
    """Tests for docx reader."""

    def test_reads_paragraphs(self):
        """Test reading paragraphs from docx."""
        docx_path = FIXTURES_DIR / "brand_alpha" / "alpha-main-review.docx"
        if not docx_path.exists():
            pytest.skip("Fixture not found")

        doc = read_docx(docx_path)
        assert len(doc.paragraphs()) > 0

    def test_reads_headings(self):
        """Test reading headings from docx."""
        docx_path = FIXTURES_DIR / "brand_alpha" / "alpha-main-review.docx"
        if not docx_path.exists():
            pytest.skip("Fixture not found")

        doc = read_docx(docx_path)
        headings = doc.headings()
        assert len(headings) > 0

    def test_detects_heading_levels(self):
        """Test that heading levels are detected."""
        docx_path = FIXTURES_DIR / "brand_alpha" / "alpha-main-review.docx"
        if not docx_path.exists():
            pytest.skip("Fixture not found")

        headings = get_docx_headings(docx_path)
        # Should have H1 and H2 headings
        levels = [h[1] for h in headings]
        assert HeadingLevel.H1 in levels
        assert HeadingLevel.H2 in levels

    def test_text_only_reader(self):
        """Test plain text extraction."""
        docx_path = FIXTURES_DIR / "brand_alpha" / "alpha-main-review.docx"
        if not docx_path.exists():
            pytest.skip("Fixture not found")

        text = read_docx_text_only(docx_path)
        assert len(text) > 0
        assert "Alpha Casino" in text


class TestFingerprintBuilder:
    """Tests for FingerprintBuilder."""

    def test_builds_from_documents(self):
        """Test building fingerprint from documents."""
        # Create simple test documents
        docs = [
            Document.from_elements([
                Heading("Test Heading", HeadingLevel.H1, 0, 12),
                Paragraph("You can play here. You will enjoy this.", 13, 53),
            ]),
        ]
        builder = FingerprintBuilder()
        fp = builder.build(docs)
        assert fp.article_count == 1
        assert fp.second_person_count > 0

    def test_sentence_length_stats(self):
        """Test that sentence length stats are computed correctly."""
        # Create document with known sentence lengths
        # "One two three four five." = 5 words
        # "One two three four five six seven eight nine ten." = 10 words
        docs = [
            Document.from_elements([
                Paragraph("One two three four five. One two three four five six seven eight nine ten.", 0, 75),
            ]),
        ]
        builder = FingerprintBuilder()
        fp = builder.build(docs)
        # Mean should be (5 + 10) / 2 = 7.5
        assert 7 <= fp.sentence_length_mean <= 8


class TestCorpusIndex:
    """Tests for corpus index generation."""

    def test_generates_index(self):
        """Test generating corpus index from fixtures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy fixtures to temp dir
            tmp_path = Path(tmpdir)
            shutil.copytree(FIXTURES_DIR / "brand_alpha", tmp_path / "brand_alpha")

            # Generate index
            index_path = generate_corpus_index(tmp_path)
            assert index_path.exists()

            # Load and verify
            index = load_corpus_index(tmp_path)
            assert len(index) == 3  # 3 articles in brand_alpha

    def test_infers_types_correctly(self):
        """Test that types are inferred from filenames."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            shutil.copytree(FIXTURES_DIR / "brand_alpha", tmp_path / "brand_alpha")

            index = load_corpus_index(tmp_path)

            # Check specific files
            for entry in index:
                if "bonus" in entry['filepath'].lower():
                    assert entry['type'] == "bonus_page"
                elif "app" in entry['filepath'].lower() or "mobile" in entry['filepath'].lower():
                    assert entry['type'] == "app_review"


class TestVoiceModelBuilder:
    """Tests for VoiceModelBuilder."""

    @pytest.fixture
    def temp_corpus(self):
        """Create temporary corpus from fixtures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Copy all fixtures
            for brand_dir in FIXTURES_DIR.iterdir():
                if brand_dir.is_dir() and brand_dir.name.startswith("brand_"):
                    shutil.copytree(brand_dir, tmp_path / brand_dir.name)
            yield tmp_path

    def test_builds_house_model(self, temp_corpus):
        """Test that house model aggregates all articles."""
        builder = VoiceModelBuilder(temp_corpus)
        result = builder.build_all(save=False)

        # House model should have all 20 articles (3 + 12 + 5)
        assert result.house_model.article_count == 20

    def test_builds_type_models(self, temp_corpus):
        """Test that type models pool across brands."""
        builder = VoiceModelBuilder(temp_corpus)
        result = builder.build_all(save=False)

        # Should have sports_market type with articles from beta and gamma
        assert "sports_market" in result.type_models
        sports_count = result.type_models["sports_market"].article_count
        assert sports_count >= 5  # At least gamma's 5

    def test_brand_threshold_enforced(self, temp_corpus):
        """Test that only brands with 10+ articles get models."""
        builder = VoiceModelBuilder(temp_corpus)
        result = builder.build_all(save=False)

        # Beta (12 articles) should have model
        assert "brand_beta" in result.brand_models

        # Alpha (3) and Gamma (5) should be skipped
        assert "brand_alpha" not in result.brand_models
        assert "brand_gamma" not in result.brand_models

        # Check skipped list
        skipped_names = [name for name, count in result.skipped_brands]
        assert "brand_alpha" in skipped_names
        assert "brand_gamma" in skipped_names

    def test_skipped_brands_logged(self, temp_corpus):
        """Test that skipped brands are recorded with counts."""
        builder = VoiceModelBuilder(temp_corpus)
        result = builder.build_all(save=False)

        # Find alpha in skipped
        alpha_entry = next(
            (entry for entry in result.skipped_brands if entry[0] == "brand_alpha"),
            None
        )
        assert alpha_entry is not None
        assert alpha_entry[1] == 3  # 3 articles


class TestBlendHelper:
    """Tests for blend helper functions."""

    @pytest.fixture
    def temp_corpus_with_models(self):
        """Create corpus with built models."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Copy fixtures
            for brand_dir in FIXTURES_DIR.iterdir():
                if brand_dir.is_dir() and brand_dir.name.startswith("brand_"):
                    shutil.copytree(brand_dir, tmp_path / brand_dir.name)

            # Build models
            builder = VoiceModelBuilder(tmp_path)
            builder.build_all(save=True)
            yield tmp_path

    def test_house_always_present(self, temp_corpus_with_models):
        """Test that house layer is always included."""
        layers = available_layers("unknown_brand", "unknown_type", temp_corpus_with_models)
        assert "house" in layers

    def test_well_covered_brand_known_type(self, temp_corpus_with_models):
        """Test layers for well-covered brand with known type."""
        layers = available_layers("brand_beta", "bonus_page", temp_corpus_with_models)
        assert "house" in layers
        assert "type:bonus_page" in layers
        assert "brand:brand_beta" in layers

    def test_new_brand_known_type(self, temp_corpus_with_models):
        """Test layers for new brand (below threshold) with known type."""
        layers = available_layers("brand_alpha", "bonus_page", temp_corpus_with_models)
        assert "house" in layers
        assert "type:bonus_page" in layers
        assert "brand:brand_alpha" not in layers  # Below threshold

    def test_new_brand_unknown_type(self, temp_corpus_with_models):
        """Test layers for new brand with unknown type."""
        layers = available_layers("brand_alpha", "nonexistent_type", temp_corpus_with_models)
        assert "house" in layers
        assert len(layers) == 1  # Only house

    def test_get_voice_layers_returns_models(self, temp_corpus_with_models):
        """Test that get_voice_layers returns actual VoiceModel objects."""
        layers = get_voice_layers("brand_beta", "bonus_page", temp_corpus_with_models)
        assert len(layers) >= 2  # At least house and type
        for layer in layers:
            assert isinstance(layer, VoiceModel)


class TestIntegration:
    """Integration tests using actual fixtures."""

    def test_full_build_pipeline(self):
        """Test the complete build pipeline on fixtures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Copy fixtures
            for brand_dir in FIXTURES_DIR.iterdir():
                if brand_dir.is_dir() and brand_dir.name.startswith("brand_"):
                    shutil.copytree(brand_dir, tmp_path / brand_dir.name)

            # Build
            builder = VoiceModelBuilder(tmp_path)
            result = builder.build_all(save=True)

            # Verify files created
            assert (tmp_path / "_house" / "voice_model.json").exists()
            assert (tmp_path / "brand_beta" / "voice_model.json").exists()

            # Verify type models
            assert (tmp_path / "_types" / "sports_market" / "voice_model.json").exists()

            # Verify house model stats
            fp = result.house_model.fingerprint
            assert fp.second_person_count > 0
            assert fp.sentence_length_mean > 0

    def test_person_ratio_is_second_dominant(self):
        """Test that fixtures have second-person dominance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            for brand_dir in FIXTURES_DIR.iterdir():
                if brand_dir.is_dir() and brand_dir.name.startswith("brand_"):
                    shutil.copytree(brand_dir, tmp_path / brand_dir.name)

            builder = VoiceModelBuilder(tmp_path)
            result = builder.build_all(save=False)

            # Fixtures are written with "you/your" dominant
            fp = result.house_model.fingerprint
            assert fp.second_person_count > fp.third_person_count
