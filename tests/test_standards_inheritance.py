"""
Tests for core/standards_engine.py - Standards Engine with Inheritance

Tests:
- Assert _defaults loads correctly
- Assert vave.yaml deep-merges on top
- Assert brand overrides win
- Assert nested dicts merge (voice.person inherited)
- Assert lists replace
- Assert typed accessors return expected values
"""

import pytest
from pathlib import Path
from core.standards_engine import (
    StandardsEngine,
    Standards,
    VoiceStandards,
    ReadabilityStandards,
    KeywordStandards,
    CurrencyStandards,
    HeadingsStandards,
    StopWordsStandards,
    ProhibitedStyleStandards,
    LocaleMapping,
    deep_merge,
)


class TestDeepMerge:
    """Tests for deep_merge function."""

    def test_simple_merge(self):
        """Test merging simple dicts."""
        base = {"a": 1, "b": 2}
        overlay = {"b": 3, "c": 4}

        result = deep_merge(base, overlay)

        assert result["a"] == 1  # From base
        assert result["b"] == 3  # Overlay wins
        assert result["c"] == 4  # From overlay

    def test_nested_dict_merge(self):
        """Test nested dicts merge recursively."""
        base = {"outer": {"a": 1, "b": 2}}
        overlay = {"outer": {"b": 10, "c": 3}}

        result = deep_merge(base, overlay)

        assert result["outer"]["a"] == 1   # Base preserved
        assert result["outer"]["b"] == 10  # Overlay wins
        assert result["outer"]["c"] == 3   # From overlay

    def test_lists_replace(self):
        """Test that lists replace, not extend."""
        base = {"items": [1, 2, 3]}
        overlay = {"items": [4, 5]}

        result = deep_merge(base, overlay)

        assert result["items"] == [4, 5]  # Replaced, not [1,2,3,4,5]

    def test_scalars_replace(self):
        """Test scalars are replaced."""
        base = {"value": "original"}
        overlay = {"value": "new"}

        result = deep_merge(base, overlay)

        assert result["value"] == "new"

    def test_deep_nested_merge(self):
        """Test deeply nested structure merge."""
        base = {
            "level1": {
                "level2": {
                    "level3": {"a": 1, "b": 2}
                }
            }
        }
        overlay = {
            "level1": {
                "level2": {
                    "level3": {"b": 20, "c": 3}
                }
            }
        }

        result = deep_merge(base, overlay)

        assert result["level1"]["level2"]["level3"]["a"] == 1
        assert result["level1"]["level2"]["level3"]["b"] == 20
        assert result["level1"]["level2"]["level3"]["c"] == 3

    def test_original_dicts_unchanged(self):
        """Test that original dicts are not mutated."""
        base = {"a": {"b": 1}}
        overlay = {"a": {"c": 2}}

        result = deep_merge(base, overlay)

        # Original dicts should be unchanged
        assert "c" not in base["a"]
        assert "b" not in overlay["a"]


class TestTypedAccessors:
    """Tests for typed accessor dataclasses."""

    def test_voice_standards(self):
        """Test VoiceStandards."""
        data = {"person": "third", "on_behalf_of": "test team"}
        voice = VoiceStandards.from_dict(data)

        assert voice.person == "third"
        assert voice.on_behalf_of == "test team"

    def test_voice_standards_defaults(self):
        """Test VoiceStandards defaults."""
        voice = VoiceStandards.from_dict({})

        assert voice.person == "second"
        assert voice.on_behalf_of == "gambling expert team"

    def test_readability_standards(self):
        """Test ReadabilityStandards."""
        data = {
            "max_sentence_words": 30,
            "paragraph_sentences": [2, 4],
            "require_para_between_headings": False,
        }
        read = ReadabilityStandards.from_dict(data)

        assert read.max_sentence_words == 30
        assert read.paragraph_sentences_min == 2
        assert read.paragraph_sentences_max == 4
        assert read.require_para_between_headings is False

    def test_stop_words_standards(self):
        """Test StopWordsStandards."""
        data = {
            "hard": ["delve", "leverage"],
            "soft": ["unlock", "ensure"],
        }
        stop = StopWordsStandards.from_dict(data)

        assert stop.is_hard("delve")
        assert stop.is_hard("DELVE")  # Case insensitive
        assert stop.is_soft("unlock")
        assert not stop.is_hard("unlock")
        assert not stop.is_soft("delve")

    def test_stop_words_weight(self):
        """Test stop word weight calculation."""
        stop = StopWordsStandards(hard=["delve"], soft=["unlock"])

        assert stop.weight("delve") == 1.0
        assert stop.weight("unlock") == 0.3
        assert stop.weight("normal") == 0.0

    def test_stop_words_tier(self):
        """Test stop word tier identification."""
        stop = StopWordsStandards(hard=["delve"], soft=["unlock"])

        assert stop.tier("delve") == "hard"
        assert stop.tier("unlock") == "soft"
        assert stop.tier("normal") is None

    def test_locale_mapping(self):
        """Test LocaleMapping."""
        mapping = LocaleMapping()

        assert mapping.spelling_region("UK") == "british"
        assert mapping.spelling_region("IN") == "british"
        assert mapping.spelling_region("US") == "american"
        assert mapping.spelling_region("CA") == "canadian"
        assert mapping.spelling_region("AU") == "australian"
        assert mapping.spelling_region("NZ") == "new_zealand"
        assert mapping.spelling_region("XX") == "british"  # Default

    def test_prohibited_style_list_format(self):
        """Test ProhibitedStyleStandards with list format."""
        data = [
            {"latin_abbreviations": ["e.g.", "i.e."]},
            {"profanity_mild": ["sucks"]},
        ]
        style = ProhibitedStyleStandards.from_dict(data)

        assert "e.g." in style.latin_abbreviations
        assert "sucks" in style.profanity_mild

    def test_prohibited_style_is_prohibited(self):
        """Test is_prohibited method."""
        style = ProhibitedStyleStandards(
            latin_abbreviations=["e.g.", "i.e."],
            profanity_mild=["sucks"],
        )

        assert style.is_prohibited("Use e.g. when needed")
        assert style.is_prohibited("This sucks")
        assert not style.is_prohibited("This is fine")


class TestStandards:
    """Tests for Standards dataclass."""

    def test_standards_from_dict(self):
        """Test creating Standards from dict."""
        data = {
            "voice": {"person": "second"},
            "readability": {"max_sentence_words": 25},
            "forbidden_brands": True,
            "brand_name": "TestBrand",
            "market": "CA",
        }
        standards = Standards.from_dict(data)

        assert standards.voice.person == "second"
        assert standards.readability.max_sentence_words == 25
        assert standards.forbidden_brands is True
        assert standards.brand_name == "TestBrand"
        assert standards.market == "CA"

    def test_standards_get_path(self):
        """Test dot-path access via get()."""
        data = {
            "voice": {"person": "second"},
            "nested": {"deep": {"value": 42}},
        }
        standards = Standards.from_dict(data)

        assert standards.get("voice.person") == "second"
        assert standards.get("nested.deep.value") == 42
        assert standards.get("nonexistent.path") is None
        assert standards.get("nonexistent", "default") == "default"

    def test_standards_spelling_region(self):
        """Test spelling_region property."""
        standards = Standards.from_dict({"market": "CA"})
        assert standards.spelling_region == "canadian"

        standards = Standards.from_dict({"market": "UK"})
        assert standards.spelling_region == "british"

        standards = Standards.from_dict({})
        assert standards.spelling_region == "british"  # Default


class TestStandardsEngine:
    """Tests for StandardsEngine with real files."""

    @pytest.fixture
    def engine(self):
        """Create StandardsEngine pointing to brands directory."""
        # Get the project root (parent of tests directory)
        project_root = Path(__file__).parent.parent
        brands_dir = project_root / "brands"
        return StandardsEngine(brands_dir=brands_dir)

    def test_load_defaults(self, engine):
        """Test loading defaults only."""
        standards = engine.load_defaults()

        # Check values from _defaults.yaml
        assert standards.voice.person == "second"
        assert standards.voice.on_behalf_of == "gambling expert team"
        assert standards.readability.max_sentence_words == 25
        assert standards.keywords.max_density_percent == 3.0
        assert standards.currency.mode == "exclusive"
        assert standards.forbidden_brands is True

    def test_defaults_stop_words(self, engine):
        """Test stop words from defaults."""
        standards = engine.load_defaults()

        # Hard stop words
        assert standards.stop_words.is_hard("delve")
        assert standards.stop_words.is_hard("seamless")
        assert standards.stop_words.is_hard("leverage")

        # Soft stop words
        assert standards.stop_words.is_soft("unlock")
        assert standards.stop_words.is_soft("ensure")
        assert standards.stop_words.is_soft("selection")

        # Weights
        assert standards.stop_words.weight("delve") == 1.0
        assert standards.stop_words.weight("unlock") == 0.3

    def test_defaults_prohibited_style(self, engine):
        """Test prohibited style from defaults."""
        standards = engine.load_defaults()

        assert "e.g." in standards.prohibited_style.latin_abbreviations
        assert "i.e." in standards.prohibited_style.latin_abbreviations
        assert "etc." in standards.prohibited_style.latin_abbreviations
        assert "sucks" in standards.prohibited_style.profanity_mild

    def test_defaults_locale_mappings(self, engine):
        """Test locale mappings from defaults."""
        standards = engine.load_defaults()

        assert "UK" in standards.locale_mappings.british
        assert "US" in standards.locale_mappings.american
        assert "CA" in standards.locale_mappings.canadian

    def test_load_brand_with_inheritance(self, engine):
        """Test loading brand config merges with defaults."""
        standards = engine.load("vave")

        # From defaults (inherited)
        assert standards.voice.person == "second"
        assert standards.readability.max_sentence_words == 25
        assert standards.forbidden_brands is True

        # From vave.yaml (override)
        assert standards.brand_name == "Vave"
        assert standards.market == "CA"
        assert standards.locale == "en-CA"
        assert standards.headings.capitalization == "title_case"
        assert standards.currency.symbol == "C$"

    def test_brand_overrides_win(self, engine):
        """Test that brand-specific values override defaults."""
        standards = engine.load("vave")

        # headings.capitalization is None in defaults but "title_case" in vave
        assert standards.headings.capitalization == "title_case"

        # currency.symbol is None in defaults but "C$" in vave
        assert standards.currency.symbol == "C$"

    def test_nested_dicts_merge(self, engine):
        """Test that nested dicts merge correctly."""
        standards = engine.load("vave")

        # headings should have both default and vave values
        # From defaults:
        assert standards.headings.hierarchy == ["H1", "H2", "H3", "H4"]
        assert standards.headings.descriptive_required is True
        assert standards.headings.no_question_marks is True

        # From vave override:
        assert standards.headings.capitalization == "title_case"

    def test_defaults_fall_through(self, engine):
        """Test that defaults fall through when brand is silent."""
        standards = engine.load("vave")

        # vave.yaml doesn't specify stop_words, so defaults should apply
        assert standards.stop_words.is_hard("delve")
        assert standards.stop_words.is_soft("unlock")

        # vave.yaml doesn't specify prohibited_style
        assert "e.g." in standards.prohibited_style.latin_abbreviations

    def test_available_brands(self, engine):
        """Test listing available brands."""
        brands = engine.available_brands()

        assert "vave" in brands
        # _defaults should not be included
        assert "_defaults" not in brands

    def test_has_brand(self, engine):
        """Test checking if brand exists."""
        assert engine.has_brand("vave") is True
        assert engine.has_brand("nonexistent") is False

    def test_caching(self, engine):
        """Test that standards are cached."""
        standards1 = engine.load("vave")
        standards2 = engine.load("vave")

        assert standards1 is standards2  # Same object (cached)

    def test_bypass_cache(self, engine):
        """Test loading without cache."""
        standards1 = engine.load("vave")
        standards2 = engine.load("vave", use_cache=False)

        assert standards1 is not standards2  # Different objects

    def test_clear_cache(self, engine):
        """Test clearing cache."""
        standards1 = engine.load("vave")
        engine.clear_cache()
        standards2 = engine.load("vave")

        assert standards1 is not standards2

    def test_reload(self, engine):
        """Test force reload."""
        standards1 = engine.load("vave")
        standards2 = engine.reload("vave")

        assert standards1 is not standards2

    def test_brand_normalization(self, engine):
        """Test brand normalization from vave.yaml."""
        standards = engine.load("vave")

        assert standards.brand_normalization.normalize("vave") == "Vave"
        assert standards.brand_normalization.normalize("VAVE") == "Vave"
        assert standards.brand_normalization.normalize("Other") == "Other"

    def test_spelling_region_for_brand(self, engine):
        """Test spelling region derived from market."""
        standards = engine.load("vave")

        # Vave is in CA market
        assert standards.market == "CA"
        assert standards.spelling_region == "canadian"


class TestStandardsEngineEdgeCases:
    """Edge case tests for StandardsEngine."""

    def test_nonexistent_brand_uses_defaults(self, tmp_path):
        """Test loading a nonexistent brand still returns defaults."""
        # Create a minimal _defaults.yaml
        brands_dir = tmp_path / "brands"
        brands_dir.mkdir()
        defaults_file = brands_dir / "_defaults.yaml"
        defaults_file.write_text("voice:\n  person: second\n")

        engine = StandardsEngine(brands_dir=brands_dir)
        standards = engine.load("nonexistent")

        # Should still have defaults
        assert standards.voice.person == "second"
        # Brand name should be set to the requested name
        assert standards.brand_name == "nonexistent"

    def test_empty_defaults(self, tmp_path):
        """Test with empty defaults file."""
        brands_dir = tmp_path / "brands"
        brands_dir.mkdir()
        defaults_file = brands_dir / "_defaults.yaml"
        defaults_file.write_text("")  # Empty

        engine = StandardsEngine(brands_dir=brands_dir)
        standards = engine.load_defaults()

        # Should have dataclass defaults
        assert standards.voice.person == "second"

    def test_missing_defaults_file(self, tmp_path):
        """Test with no defaults file."""
        brands_dir = tmp_path / "brands"
        brands_dir.mkdir()
        # No _defaults.yaml created

        engine = StandardsEngine(brands_dir=brands_dir)
        standards = engine.load_defaults()

        # Should have dataclass defaults
        assert standards.voice.person == "second"
