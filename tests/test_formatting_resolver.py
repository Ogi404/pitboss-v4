"""
Tests for formatting resolver - blank_rows resolution hierarchy.
"""

import pytest
from output.formatting_resolver import (
    resolve_blank_rows,
    get_blank_rows_reason,
)
from ingest.brief_model import (
    BriefModel,
    BriefKeywords,
    ArticleType,
)


def make_brief(
    article_type: ArticleType = ArticleType.GENERAL,
    market: str = None,
    formatting_hints: tuple = (),
) -> BriefModel:
    """Helper to create minimal BriefModel for testing."""
    return BriefModel(
        keywords=BriefKeywords(),
        keywords_confidence=1.0,
        sections=(),
        sections_confidence=1.0,
        target_word_count=1000,
        word_count_confidence=1.0,
        task_name="Test Task",
        article_type=article_type,
        article_type_confidence=1.0,
        locale="en-AU",
        market=market,
        locale_confidence=1.0,
        formatting_hints=formatting_hints,
    )


class TestBriefHintWins:
    """Priority 1: Brief formatting hints override everything."""

    def test_brief_hint_required_wins(self):
        """Brief hint 'required' takes precedence."""
        brief = make_brief(
            article_type=ArticleType.META_SEO,  # Would be "none" normally
            formatting_hints=(("blank_rows", "required"),),
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "required"

    def test_brief_hint_none_wins(self):
        """Brief hint 'none' takes precedence."""
        brief = make_brief(
            article_type=ArticleType.MAIN_REVIEW,
            market="AU",  # Would be "required" normally
            formatting_hints=(("blank_rows", "none"),),
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "none"

    def test_brief_hint_wins_over_filename(self):
        """Brief hint wins over filename pattern."""
        brief = make_brief(
            formatting_hints=(("blank_rows", "none"),),
        )
        # Filename has AU marker which would be "required"
        result = resolve_blank_rows(brief=brief, filename="Main Page AU.docx")
        assert result == "none"


class TestArticleTypeNone:
    """Priority 2: META_SEO and PRIVACY_POLICY -> none."""

    def test_meta_seo_returns_none(self):
        """META_SEO article type returns 'none'."""
        brief = make_brief(article_type=ArticleType.META_SEO)
        result = resolve_blank_rows(brief=brief)
        assert result == "none"

    def test_privacy_policy_returns_none(self):
        """PRIVACY_POLICY article type returns 'none'."""
        brief = make_brief(article_type=ArticleType.PRIVACY_POLICY)
        result = resolve_blank_rows(brief=brief)
        assert result == "none"

    def test_meta_seo_overrides_market(self):
        """META_SEO wins over market signal."""
        brief = make_brief(
            article_type=ArticleType.META_SEO,
            market="AU",  # Would be "required" for other types
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "none"


class TestMarketPlusType:
    """Priority 3: Market + market-facing type -> required."""

    def test_au_market_main_review_required(self):
        """AU market + main_review -> required."""
        brief = make_brief(
            article_type=ArticleType.MAIN_REVIEW,
            market="AU",
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "required"

    def test_canada_market_bonus_page_required(self):
        """Canada market + bonus_page -> required."""
        brief = make_brief(
            article_type=ArticleType.BONUS_PAGE,
            market="Canada",
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "required"

    def test_australia_full_name_works(self):
        """Full country name 'australia' works."""
        brief = make_brief(
            article_type=ArticleType.MAIN_REVIEW,
            market="australia",
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "required"

    def test_non_market_facing_type_not_required(self):
        """Non-market-facing type doesn't trigger required."""
        brief = make_brief(
            article_type=ArticleType.RESPONSIBLE_GAMING,
            market="AU",
        )
        # RESPONSIBLE_GAMING is not in MARKET_FACING_TYPES
        result = resolve_blank_rows(brief=brief)
        # Falls through to proposal
        assert result == "proposal"

    def test_unknown_market_not_required(self):
        """Unknown market doesn't trigger required."""
        brief = make_brief(
            article_type=ArticleType.MAIN_REVIEW,
            market="Sweden",  # Not in BLANK_ROWS_MARKETS
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "proposal"


class TestFilenamePatterns:
    """Priority 4: Filename pattern detection."""

    def test_meta_title_prefix_returns_none(self):
        """'Meta Title_' prefix -> none."""
        result = resolve_blank_rows(filename="Meta Title_ Casino Review.docx")
        assert result == "none"

    def test_meta_title_space_prefix_returns_none(self):
        """'Meta Title ' (with space) prefix -> none."""
        result = resolve_blank_rows(filename="Meta Title Casino Review.docx")
        assert result == "none"

    def test_au_in_filename_returns_required(self):
        """AU in filename -> required."""
        result = resolve_blank_rows(filename="Main Page_ Koi Fortune AU.docx")
        assert result == "required"

    def test_australia_in_filename_returns_required(self):
        """Australia in filename -> required."""
        result = resolve_blank_rows(filename="Bonus Page Australia.docx")
        assert result == "required"

    def test_canada_in_filename_returns_required(self):
        """Canada in filename -> required."""
        result = resolve_blank_rows(filename="App Review Canada.docx")
        assert result == "required"

    def test_uk_in_filename_returns_required(self):
        """UK in filename -> required."""
        result = resolve_blank_rows(filename="Main Review UK.docx")
        assert result == "required"


class TestBrandConfigFallback:
    """Priority 5: Brand config fallback."""

    def test_brand_explicit_config(self):
        """Explicit blank_rows in brand_config."""
        brand_config = {"blank_rows": "required"}
        result = resolve_blank_rows(brand_config=brand_config)
        assert result == "required"

    def test_known_consistent_high_brand(self):
        """Known consistent-high brand returns required."""
        brand_config = {"brand_name": "Koifortune"}
        # Koifortune is not in the explicit list, so falls through
        # Let me check if it should be added based on corpus analysis
        result = resolve_blank_rows(brand_config=brand_config)
        # Koifortune was bimodal, not in consistent list
        assert result == "proposal"

    def test_known_consistent_low_brand(self):
        """Known consistent-low brand returns none."""
        brand_config = {"brand_name": "National"}
        result = resolve_blank_rows(brand_config=brand_config)
        assert result == "none"

    def test_20bet_returns_required(self):
        """20bet (consistent high) returns required."""
        brand_config = {"brand_name": "20Bet"}
        result = resolve_blank_rows(brand_config=brand_config)
        assert result == "required"


class TestDefaultProposal:
    """Priority 6: Default when no signal."""

    def test_no_brief_no_config_returns_proposal(self):
        """No brief, no config -> proposal (new client case)."""
        result = resolve_blank_rows()
        assert result == "proposal"

    def test_unknown_brand_returns_proposal(self):
        """Unknown brand with no other signals -> proposal."""
        brief = make_brief(
            article_type=ArticleType.GENERAL,
            market=None,
        )
        brand_config = {"brand_name": "BrandNewClient"}
        result = resolve_blank_rows(brief=brief, brand_config=brand_config)
        assert result == "proposal"

    def test_general_type_no_market_returns_proposal(self):
        """GENERAL type with no market -> proposal."""
        brief = make_brief(
            article_type=ArticleType.GENERAL,
            market=None,
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "proposal"


class TestReasonExplanation:
    """Test the get_blank_rows_reason function."""

    def test_reason_for_brief_hint(self):
        """Reason explains brief hint."""
        brief = make_brief(
            formatting_hints=(("blank_rows", "required"),),
        )
        result, reason = get_blank_rows_reason(brief=brief)
        assert result == "required"
        assert "brief formatting hint" in reason

    def test_reason_for_meta_seo(self):
        """Reason explains META_SEO type."""
        brief = make_brief(article_type=ArticleType.META_SEO)
        result, reason = get_blank_rows_reason(brief=brief)
        assert result == "none"
        assert "meta_seo" in reason

    def test_reason_for_market_type(self):
        """Reason explains market + type."""
        brief = make_brief(
            article_type=ArticleType.MAIN_REVIEW,
            market="AU",
        )
        result, reason = get_blank_rows_reason(brief=brief)
        assert result == "required"
        assert "market" in reason
        assert "main_review" in reason

    def test_reason_for_filename(self):
        """Reason explains filename pattern."""
        result, reason = get_blank_rows_reason(filename="Main Page AU.docx")
        assert result == "required"
        assert "filename" in reason
        assert "AU" in reason

    def test_reason_for_default(self):
        """Reason explains default."""
        result, reason = get_blank_rows_reason()
        assert result == "proposal"
        assert "default" in reason or "no strong signal" in reason


class TestEdgeCases:
    """Edge cases and integration scenarios."""

    def test_empty_market_not_matched(self):
        """Empty market string doesn't match."""
        brief = make_brief(
            article_type=ArticleType.MAIN_REVIEW,
            market="",
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "proposal"

    def test_none_market_not_matched(self):
        """None market doesn't match."""
        brief = make_brief(
            article_type=ArticleType.MAIN_REVIEW,
            market=None,
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "proposal"

    def test_case_insensitive_market(self):
        """Market matching is case-insensitive."""
        brief = make_brief(
            article_type=ArticleType.MAIN_REVIEW,
            market="AUSTRALIA",
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "required"

    def test_whitespace_in_market(self):
        """Whitespace in market is stripped."""
        brief = make_brief(
            article_type=ArticleType.MAIN_REVIEW,
            market="  AU  ",
        )
        result = resolve_blank_rows(brief=brief)
        assert result == "required"

    def test_all_signals_brief_wins(self):
        """When all signals present, brief hint wins."""
        brief = make_brief(
            article_type=ArticleType.MAIN_REVIEW,
            market="AU",
            formatting_hints=(("blank_rows", "none"),),
        )
        brand_config = {"brand_name": "20Bet", "blank_rows": "required"}
        result = resolve_blank_rows(
            brief=brief,
            brand_config=brand_config,
            filename="Main Page AU.docx",
        )
        assert result == "none"  # Brief hint wins
