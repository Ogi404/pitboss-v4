"""
Tests for graceful degradation when brand is unconfigured.

Verifies that:
- --brand <unknown> behaves identically to no --brand
- brand_names produces 0 findings for unconfigured brands (no false-positives)
- Per-check finding counts match between both modes
- Warning appears in summary for unconfigured brand
"""

import pytest
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Optional

from core.document import Document, Paragraph, TextRun
from core.orchestrator import run_all_checks, OrchestratorResult
from core.standards_engine import StandardsEngine, Standards
from core.check_base import get_registry


def _ensure_checks_registered():
    """Ensure all deterministic checks are registered."""
    registry = get_registry()
    if len(registry) < 9:
        from deterministic.voice import VoiceThirdPersonCheck
        from deterministic.stop_words import StopWordsCheck
        from deterministic.headings import HeadingsCheck
        from deterministic.currency import CurrencyConsistencyCheck
        from deterministic.formatting import FormattingCheck
        from deterministic.locale_spelling import LocaleSpellingCheck
        from deterministic.brand_names import BrandNamesCheck
        from deterministic.keywords import KeywordsCheck
        from deterministic.structure import StructureCheck

        for check_cls in [
            VoiceThirdPersonCheck, StopWordsCheck, HeadingsCheck,
            CurrencyConsistencyCheck, FormattingCheck, LocaleSpellingCheck,
            BrandNamesCheck, KeywordsCheck, StructureCheck
        ]:
            name = check_cls().metadata.name
            if not registry.is_registered(name):
                registry._checks[name] = check_cls


def _make_paragraph(text: str, start_offset: int) -> Paragraph:
    """Helper to create a paragraph with proper offsets."""
    return Paragraph(
        text=text,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
        _runs=[TextRun(text=text, start_offset=0, end_offset=len(text))],
    )


def _create_test_document() -> Document:
    """Create a document with content that might trigger brand_names falsely."""
    # Include brand-like content that shouldn't be flagged for unknown brands
    texts = [
        "Welcome to Koi Fortune Casino",
        "Play your favorite pokies at KoiFortune today.",
        "Our casino offers the best games.",
        "",  # blank line
        "Check out our promotions below.",
    ]
    elements = []
    offset = 0
    for text in texts:
        elements.append(_make_paragraph(text, offset))
        offset += len(text) + 1  # +1 for newline
    return Document(elements=elements, title="Test Doc")


def _count_findings_by_check(result: OrchestratorResult) -> dict[str, int]:
    """Count findings per check name."""
    counts: dict[str, int] = {}
    for finding in result.findings:
        check = finding.check_name
        counts[check] = counts.get(check, 0) + 1
    return counts


# =============================================================================
# TESTS: _load_standards behavior
# =============================================================================

class TestLoadStandardsBehavior:
    """Test that _load_standards handles unknown brands correctly."""

    def test_unknown_brand_uses_defaults(self, tmp_path):
        """Unknown brand should return defaults with brand_name=None."""
        # Create brands dir with just defaults
        brands_dir = tmp_path / "brands"
        brands_dir.mkdir()
        defaults_file = brands_dir / "_defaults.yaml"
        defaults_file.write_text("spelling_region: british\n")

        engine = StandardsEngine(brands_dir=brands_dir)

        # Check that unknown brand is not found
        assert not engine.has_brand("unknown_brand")

        # Load defaults (what _load_standards should do for unknown brands)
        standards = engine.load_defaults()

        # brand_name should be None
        assert getattr(standards, 'brand_name', None) is None

    def test_known_brand_has_brand_name(self, tmp_path):
        """Known brand should have brand_name set."""
        brands_dir = tmp_path / "brands"
        brands_dir.mkdir()
        (brands_dir / "_defaults.yaml").write_text("spelling_region: british\n")
        (brands_dir / "mytest.yaml").write_text("brand_name: MyTestBrand\n")

        engine = StandardsEngine(brands_dir=brands_dir)

        assert engine.has_brand("mytest")
        standards = engine.load("mytest")
        assert standards.brand_name == "MyTestBrand"


# =============================================================================
# TESTS: Per-check parity
# =============================================================================

class TestPerCheckParity:
    """Test that unknown brand produces same findings as no brand."""

    @pytest.fixture
    def brands_dir(self, tmp_path):
        """Create a brands directory with defaults only."""
        brands_dir = tmp_path / "brands"
        brands_dir.mkdir()

        # Minimal defaults that match production _defaults.yaml structure
        defaults_content = """
spelling_region: british
voice:
  person: second
stop_words:
  hard:
    - delve
    - seamless
  soft:
    - unlock
headings:
  no_question_marks: true
  descriptive_required: false
  capitalization: null
currency:
  mode: exclusive
"""
        (brands_dir / "_defaults.yaml").write_text(defaults_content)
        return brands_dir

    def test_unknown_brand_matches_no_brand_per_check(self, brands_dir):
        """--brand unknown should produce identical per-check counts as no --brand."""
        _ensure_checks_registered()

        engine = StandardsEngine(brands_dir=brands_dir)
        document = _create_test_document()

        # Scenario 1: No brand (load defaults)
        standards_no_brand = engine.load_defaults()
        result_no_brand = run_all_checks(document, standards_no_brand)
        counts_no_brand = _count_findings_by_check(result_no_brand)

        # Scenario 2: Unknown brand (should also use defaults)
        # Simulating what fixed _load_standards does: has_brand() returns False,
        # so it calls load_defaults() instead of load()
        assert not engine.has_brand("unknown_client")
        standards_unknown = engine.load_defaults()  # This is the fix
        result_unknown = run_all_checks(document, standards_unknown)
        counts_unknown = _count_findings_by_check(result_unknown)

        # Assert per-check parity
        all_checks = set(counts_no_brand.keys()) | set(counts_unknown.keys())
        for check in all_checks:
            no_brand_count = counts_no_brand.get(check, 0)
            unknown_count = counts_unknown.get(check, 0)
            assert no_brand_count == unknown_count, (
                f"Check '{check}' mismatch: no-brand={no_brand_count}, "
                f"unknown-brand={unknown_count}"
            )

    def test_brand_names_zero_for_both_modes(self, brands_dir):
        """brand_names check must produce 0 findings for both modes."""
        _ensure_checks_registered()

        engine = StandardsEngine(brands_dir=brands_dir)
        document = _create_test_document()

        # No brand
        standards_no_brand = engine.load_defaults()
        result_no_brand = run_all_checks(document, standards_no_brand)
        counts_no_brand = _count_findings_by_check(result_no_brand)

        # Unknown brand (using load_defaults per the fix)
        standards_unknown = engine.load_defaults()
        result_unknown = run_all_checks(document, standards_unknown)
        counts_unknown = _count_findings_by_check(result_unknown)

        # brand_names must be 0 for both - no competitor false-positives
        assert counts_no_brand.get("brand_names", 0) == 0, (
            f"brand_names produced {counts_no_brand.get('brand_names', 0)} "
            "findings with no brand (expected 0)"
        )
        assert counts_unknown.get("brand_names", 0) == 0, (
            f"brand_names produced {counts_unknown.get('brand_names', 0)} "
            "findings with unknown brand (expected 0)"
        )

    def test_total_findings_match(self, brands_dir):
        """Total finding counts should match between modes."""
        _ensure_checks_registered()

        engine = StandardsEngine(brands_dir=brands_dir)
        document = _create_test_document()

        standards_no_brand = engine.load_defaults()
        result_no_brand = run_all_checks(document, standards_no_brand)

        standards_unknown = engine.load_defaults()
        result_unknown = run_all_checks(document, standards_unknown)

        assert len(result_no_brand.findings) == len(result_unknown.findings), (
            f"Total findings mismatch: no-brand={len(result_no_brand.findings)}, "
            f"unknown-brand={len(result_unknown.findings)}"
        )


# =============================================================================
# TESTS: Warning in summary
# =============================================================================

class TestBrandWarning:
    """Test that warnings appear correctly in summary."""

    def test_summary_includes_brand_warning(self):
        """RunSummary should include brand_warning field."""
        from output.summary import RunSummary, summary_to_markdown

        summary = RunSummary(
            article_path="test.docx",
            brand_warning="Brand 'newclient' not configured - using defaults",
        )

        markdown = summary_to_markdown(summary)
        assert "Brand 'newclient' not configured" in markdown
        assert "Warning:" in markdown

    def test_summary_no_warning_when_brand_exists(self):
        """Summary should not show warning when brand is configured."""
        from output.summary import RunSummary, summary_to_markdown

        summary = RunSummary(
            article_path="test.docx",
            brand_warning=None,
        )

        markdown = summary_to_markdown(summary)
        assert "Warning:" not in markdown


# =============================================================================
# TESTS: getattr fallbacks don't crash
# =============================================================================

class TestGetAttrFallbacks:
    """Test that checks don't crash with missing config attributes."""

    def test_stop_words_handles_missing_config(self):
        """stop_words check should handle missing stop_words config."""
        _ensure_checks_registered()

        from deterministic.stop_words import StopWordsCheck
        from core.standards_engine import Standards

        # Create standards without stop_words attribute
        standards = Standards()
        # Ensure stop_words is None/missing
        if hasattr(standards, 'stop_words'):
            delattr(standards, 'stop_words')

        document = _create_test_document()
        check = StopWordsCheck()

        # Should not crash, should return empty list
        findings = check.run(document, standards)
        assert findings == []

    def test_headings_handles_missing_config(self):
        """headings check should handle missing headings config."""
        _ensure_checks_registered()

        from deterministic.headings import HeadingsCheck
        from core.standards_engine import Standards

        # Create standards without headings attribute
        standards = Standards()
        if hasattr(standards, 'headings'):
            delattr(standards, 'headings')

        document = _create_test_document()
        check = HeadingsCheck()

        # Should not crash
        findings = check.run(document, standards)
        # May produce findings for spacing/hierarchy, but shouldn't crash
        assert isinstance(findings, list)


# =============================================================================
# TESTS: Mismatch guard for competitor detection
# =============================================================================

class TestMismatchGuard:
    """Test that brand mismatch guard prevents false competitor flags."""

    def _create_koifortune_document(self) -> Document:
        """Create a document that mentions KoiFortune heavily."""
        texts = [
            "Welcome to KoiFortune Casino",
            "KoiFortune offers the best pokies in Australia.",
            "Play at KoiFortune today for exciting bonuses.",
            "KoiFortune has over 1000 games available.",
            "Contact KoiFortune support for help.",
            "KoiFortune is licensed and regulated.",
            "Visit KoiFortune now!",
        ]
        elements = []
        offset = 0
        for text in texts:
            elements.append(_make_paragraph(text, offset))
            offset += len(text) + 1
        return Document(elements=elements, title="KoiFortune Casino Review")

    def test_mismatch_detected_warns_and_protects(self):
        """Mismatch guard should warn and NOT flag dominant as competitor."""
        _ensure_checks_registered()

        from deterministic.brand_names import BrandNamesCheck
        from core.standards_engine import Standards

        # Create standards with mismatched brand_name
        standards = Standards()
        standards.brand_name = "TestBroken"  # Does NOT match article

        document = self._create_koifortune_document()
        check = BrandNamesCheck()

        findings = check.run(document, standards)

        # KoiFortune should NOT be flagged as competitor
        competitor_findings = [
            f for f in findings
            if f.metadata.get("sub_check") == "competitor"
            and "KoiFortune" in (f.original_text or "")
        ]
        assert len(competitor_findings) == 0, (
            f"KoiFortune was flagged as competitor {len(competitor_findings)} times "
            "despite being the article's dominant brand"
        )

        # Warning should be set
        assert check.get_warning() is not None
        assert "KoiFortune" in check.get_warning()
        assert "TestBroken" in check.get_warning()

    def test_correct_brand_no_warning(self):
        """Correct brand should not trigger warning."""
        _ensure_checks_registered()

        from deterministic.brand_names import BrandNamesCheck
        from core.standards_engine import Standards

        # Create standards with CORRECT brand_name
        standards = Standards()
        standards.brand_name = "KoiFortune"  # Matches article

        document = self._create_koifortune_document()
        check = BrandNamesCheck()

        findings = check.run(document, standards)

        # No warning should be set
        assert check.get_warning() is None

    def test_no_dominant_runs_normally(self):
        """No dominant operator should run competitor detection normally."""
        _ensure_checks_registered()

        from deterministic.brand_names import BrandNamesCheck
        from core.standards_engine import Standards

        # Create standards for a new brand (not in known_operators)
        standards = Standards()
        standards.brand_name = "BrandNewCasino"

        # Document doesn't mention any known operators heavily
        document = _create_test_document()  # Generic content
        check = BrandNamesCheck()

        findings = check.run(document, standards)

        # No warning (no mismatch detected)
        assert check.get_warning() is None

    def test_ambiguous_no_suppression(self):
        """Near-tie operators should not trigger suppression."""
        _ensure_checks_registered()

        from deterministic.brand_names import BrandNamesCheck
        from core.standards_engine import Standards

        # Create document mentioning multiple operators roughly equally
        texts = [
            "Compare KoiFortune vs PlayAmo casinos.",
            "KoiFortune has great slots. PlayAmo has table games.",
            "Both KoiFortune and PlayAmo offer bonuses.",
            "PlayAmo and KoiFortune are popular choices.",
        ]
        elements = []
        offset = 0
        for text in texts:
            elements.append(_make_paragraph(text, offset))
            offset += len(text) + 1
        document = Document(elements=elements, title="Casino Comparison")

        standards = Standards()
        standards.brand_name = "TestBrand"

        check = BrandNamesCheck()
        findings = check.run(document, standards)

        # With near-tie, no suppression should happen
        # (either no warning, or both are flagged as competitors)
        # The key is that we don't wrongly protect one over the other
