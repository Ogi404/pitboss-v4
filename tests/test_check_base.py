"""
Tests for core/check_base.py - The Check Interface (Frozen Contract #3)

Tests:
- Define a dummy check
- Assert it self-registers via @register_check
- Assert it's discoverable via registry.all_checks()
- Assert check_names() includes it
"""

import pytest
from core.document import Document, Paragraph
from core.finding import Finding, Location
from core.check_base import (
    CheckBase,
    CheckMetadata,
    CheckRegistry,
    CheckType,
    DeterministicCheck,
    JudgmentCheck,
    register_check,
    get_registry,
)


class TestCheckMetadata:
    """Tests for CheckMetadata dataclass."""

    def test_metadata_creation(self):
        """Test basic CheckMetadata creation."""
        meta = CheckMetadata(
            name="test.check",
            display_name="Test Check",
            category="voice",
            check_type=CheckType.DETERMINISTIC,
            description="A test check",
        )

        assert meta.name == "test.check"
        assert meta.display_name == "Test Check"
        assert meta.category == "voice"
        assert meta.check_type == CheckType.DETERMINISTIC
        assert meta.enabled_by_default is True
        assert meta.schema_version == "1.0"

    def test_metadata_is_frozen(self):
        """Test that CheckMetadata is immutable."""
        meta = CheckMetadata(
            name="test",
            display_name="Test",
            category="voice",
            check_type=CheckType.DETERMINISTIC,
            description="Test",
        )

        with pytest.raises(Exception):
            meta.name = "other"


class TestCheckRegistry:
    """Tests for CheckRegistry."""

    @pytest.fixture(autouse=True)
    def clean_registry(self):
        """Clear the registry before and after each test."""
        registry = get_registry()
        registry.clear()
        yield
        registry.clear()

    def test_registry_is_singleton(self):
        """Test that CheckRegistry is a singleton."""
        reg1 = CheckRegistry()
        reg2 = CheckRegistry()
        assert reg1 is reg2

    def test_register_check_decorator(self):
        """Test @register_check decorator."""

        @register_check
        class DummyCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="dummy.check",
                    display_name="Dummy Check",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="A dummy check for testing",
                )

            def run(self, document, standards, voice_model=None):
                return []

        registry = get_registry()
        assert "dummy.check" in registry.check_names()
        assert registry.is_registered("dummy.check")

    def test_registry_all_checks(self):
        """Test all_checks() returns registered checks."""

        @register_check
        class Check1(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="check1",
                    display_name="Check 1",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Check 1",
                )

            def run(self, document, standards, voice_model=None):
                return []

        @register_check
        class Check2(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="check2",
                    display_name="Check 2",
                    category="stop_words",
                    check_type=CheckType.DETERMINISTIC,
                    description="Check 2",
                )

            def run(self, document, standards, voice_model=None):
                return []

        registry = get_registry()
        all_checks = registry.all_checks()

        assert len(all_checks) == 2
        assert Check1 in all_checks
        assert Check2 in all_checks

    def test_registry_get_by_name(self):
        """Test getting a check by name."""

        @register_check
        class TestCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="test.check",
                    display_name="Test",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Test",
                )

            def run(self, document, standards, voice_model=None):
                return []

        registry = get_registry()
        check_class = registry.get("test.check")

        assert check_class is TestCheck
        assert registry.get("nonexistent") is None

    def test_registry_get_instance(self):
        """Test getting a check instance by name."""

        @register_check
        class InstanceCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="instance.check",
                    display_name="Instance",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Test",
                )

            def run(self, document, standards, voice_model=None):
                return []

        registry = get_registry()
        instance = registry.get_instance("instance.check")

        assert instance is not None
        assert isinstance(instance, InstanceCheck)
        assert instance.name == "instance.check"

    def test_registry_duplicate_name_raises(self):
        """Test that registering duplicate name raises error."""

        @register_check
        class FirstCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="duplicate.name",
                    display_name="First",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="First",
                )

            def run(self, document, standards, voice_model=None):
                return []

        with pytest.raises(ValueError, match="already registered"):

            @register_check
            class SecondCheck(CheckBase):
                @property
                def metadata(self):
                    return CheckMetadata(
                        name="duplicate.name",  # Same name
                        display_name="Second",
                        category="voice",
                        check_type=CheckType.DETERMINISTIC,
                        description="Second",
                    )

                def run(self, document, standards, voice_model=None):
                    return []

    def test_registry_checks_by_category(self):
        """Test filtering checks by category."""

        @register_check
        class VoiceCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="voice.check",
                    display_name="Voice",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Voice check",
                )

            def run(self, document, standards, voice_model=None):
                return []

        @register_check
        class StopCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="stop.check",
                    display_name="Stop",
                    category="stop_words",
                    check_type=CheckType.DETERMINISTIC,
                    description="Stop check",
                )

            def run(self, document, standards, voice_model=None):
                return []

        registry = get_registry()
        voice_checks = registry.checks_by_category("voice")
        stop_checks = registry.checks_by_category("stop_words")

        assert len(voice_checks) == 1
        assert len(stop_checks) == 1
        assert VoiceCheck in voice_checks
        assert StopCheck in stop_checks

    def test_registry_checks_by_type(self):
        """Test filtering checks by type."""

        @register_check
        class DetCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="det.check",
                    display_name="Deterministic",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Deterministic",
                )

            def run(self, document, standards, voice_model=None):
                return []

        @register_check
        class JudgCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="judg.check",
                    display_name="Judgment",
                    category="flow",
                    check_type=CheckType.JUDGMENT,
                    description="Judgment",
                )

            def run(self, document, standards, voice_model=None):
                return []

        registry = get_registry()
        det_checks = registry.deterministic_checks()
        judg_checks = registry.judgment_checks()

        assert len(det_checks) == 1
        assert len(judg_checks) == 1

    def test_registry_enabled_checks(self):
        """Test filtering enabled checks."""

        @register_check
        class EnabledCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="enabled.check",
                    display_name="Enabled",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Enabled",
                    enabled_by_default=True,
                )

            def run(self, document, standards, voice_model=None):
                return []

        @register_check
        class DisabledCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="disabled.check",
                    display_name="Disabled",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Disabled",
                    enabled_by_default=False,
                )

            def run(self, document, standards, voice_model=None):
                return []

        registry = get_registry()
        enabled = registry.enabled_checks()

        assert len(enabled) == 1
        assert EnabledCheck in enabled
        assert DisabledCheck not in enabled

    def test_registry_clear(self):
        """Test clearing the registry."""

        @register_check
        class TempCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="temp.check",
                    display_name="Temp",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Temp",
                )

            def run(self, document, standards, voice_model=None):
                return []

        registry = get_registry()
        assert len(registry) == 1

        registry.clear()
        assert len(registry) == 0

    def test_registry_contains(self):
        """Test 'in' operator for registry."""

        @register_check
        class ContainsCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="contains.check",
                    display_name="Contains",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Contains",
                )

            def run(self, document, standards, voice_model=None):
                return []

        registry = get_registry()
        assert "contains.check" in registry
        assert "nonexistent" not in registry


class TestCheckBase:
    """Tests for CheckBase abstract class."""

    @pytest.fixture(autouse=True)
    def clean_registry(self):
        """Clear the registry before and after each test."""
        registry = get_registry()
        registry.clear()
        yield
        registry.clear()

    def test_check_properties(self):
        """Test convenience properties."""

        @register_check
        class PropCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="prop.check",
                    display_name="Prop",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Prop check",
                )

            def run(self, document, standards, voice_model=None):
                return []

        check = PropCheck()
        assert check.name == "prop.check"
        assert check.category == "voice"
        assert check.is_deterministic is True
        assert check.is_judgment is False

    def test_check_repr(self):
        """Test string representation."""

        @register_check
        class ReprCheck(CheckBase):
            @property
            def metadata(self):
                return CheckMetadata(
                    name="repr.check",
                    display_name="Repr",
                    category="voice",
                    check_type=CheckType.DETERMINISTIC,
                    description="Repr",
                )

            def run(self, document, standards, voice_model=None):
                return []

        check = ReprCheck()
        assert "ReprCheck" in repr(check)
        assert "repr.check" in repr(check)


class TestDeterministicCheck:
    """Tests for DeterministicCheck helper base class."""

    @pytest.fixture(autouse=True)
    def clean_registry(self):
        """Clear the registry before and after each test."""
        registry = get_registry()
        registry.clear()
        yield
        registry.clear()

    def test_deterministic_check_implementation(self):
        """Test implementing a deterministic check."""

        @register_check
        class SimpleDetCheck(DeterministicCheck):
            def _get_name(self):
                return "simple.det"

            def _get_display_name(self):
                return "Simple Deterministic"

            def _get_category(self):
                return "voice"

            def _get_description(self):
                return "A simple deterministic check"

            def _find_issues(self, document, standards):
                # Find any paragraph containing "bad"
                findings = []
                for para in document.paragraphs():
                    if "bad" in para.text.lower():
                        findings.append(
                            Finding(
                                check_name=self.name,
                                category=self.category,
                                severity="warning",
                                confidence=1.0,
                                location=Location(
                                    start_offset=para.start_offset,
                                    end_offset=para.end_offset,
                                ),
                                original_text=para.text,
                                proposed_text=para.text.replace("bad", "good"),
                                reasoning="'bad' should be 'good'",
                                auto_applicable=True,
                            )
                        )
                return findings

        check = SimpleDetCheck()
        assert check.metadata.check_type == CheckType.DETERMINISTIC
        assert check.is_deterministic is True

        # Test running the check
        elements = [Paragraph("This is bad text.", 0, 17)]
        doc = Document.from_elements(elements)

        findings = check.run(doc, None)  # standards=None for this test
        assert len(findings) == 1
        assert findings[0].original_text == "This is bad text."
        assert findings[0].proposed_text == "This is good text."


class TestJudgmentCheck:
    """Tests for JudgmentCheck helper base class."""

    @pytest.fixture(autouse=True)
    def clean_registry(self):
        """Clear the registry before and after each test."""
        registry = get_registry()
        registry.clear()
        yield
        registry.clear()

    def test_judgment_check_implementation(self):
        """Test implementing a judgment check."""

        @register_check
        class SimpleJudgCheck(JudgmentCheck):
            def _get_name(self):
                return "simple.judg"

            def _get_display_name(self):
                return "Simple Judgment"

            def _get_category(self):
                return "flow"

            def _get_description(self):
                return "A simple judgment check"

            def _has_trigger(self, document, standards):
                # Trigger if any paragraph is very long
                for para in document.paragraphs():
                    if len(para.text) > 50:
                        return True
                return False

            def _generate_proposals(self, document, standards, voice_model):
                findings = []
                for para in document.paragraphs():
                    if len(para.text) > 50:
                        findings.append(
                            Finding(
                                check_name=self.name,
                                category=self.category,
                                severity="suggestion",
                                confidence=0.7,
                                location=Location(
                                    start_offset=para.start_offset,
                                    end_offset=para.end_offset,
                                ),
                                original_text=para.text,
                                reasoning="Paragraph is too long",
                                auto_applicable=False,
                            )
                        )
                return findings

        check = SimpleJudgCheck()
        assert check.metadata.check_type == CheckType.JUDGMENT
        assert check.is_judgment is True

        # Test without trigger (short paragraph)
        short_doc = Document.from_elements([Paragraph("Short.", 0, 6)])
        findings = check.run(short_doc, None)
        assert len(findings) == 0

        # Test with trigger (long paragraph)
        long_text = "This is a very long paragraph that exceeds fifty characters."
        long_doc = Document.from_elements([Paragraph(long_text, 0, len(long_text))])
        findings = check.run(long_doc, None)
        assert len(findings) == 1
        assert findings[0].severity == "suggestion"
        assert findings[0].confidence == 0.7

    def test_judgment_check_restraint(self):
        """Test that judgment checks respect restraint (no trigger = no proposals)."""

        @register_check
        class RestraintCheck(JudgmentCheck):
            def _get_name(self):
                return "restraint.check"

            def _get_display_name(self):
                return "Restraint"

            def _get_category(self):
                return "flow"

            def _get_description(self):
                return "Tests restraint scoring"

            def _has_trigger(self, document, standards):
                return False  # Never triggers

            def _generate_proposals(self, document, standards, voice_model):
                # This should never be called
                return [
                    Finding(
                        check_name=self.name,
                        category=self.category,
                        severity="suggestion",
                        confidence=0.5,
                        location=Location(start_offset=0, end_offset=1),
                        original_text="x",
                        reasoning="Should not see this",
                        auto_applicable=False,
                    )
                ]

        check = RestraintCheck()
        doc = Document.from_elements([Paragraph("Some text.", 0, 10)])

        # Should return empty because _has_trigger returns False
        findings = check.run(doc, None)
        assert len(findings) == 0
