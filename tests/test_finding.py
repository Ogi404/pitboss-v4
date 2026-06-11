"""
Tests for core/finding.py - The Finding Dataclass (Frozen Contract #2)

Tests:
- Assert Finding constructs correctly
- Assert Finding is immutable (frozen)
- Assert serialization (to_dict/from_dict)
- Assert schema_version is present
- Assert FindingCollection filtering works
"""

import pytest
import json
from core.document import Location
from core.finding import (
    Finding,
    FindingFactory,
    FindingCollection,
    Severity,
    Category,
)


class TestFinding:
    """Tests for Finding dataclass."""

    def test_finding_creation(self):
        """Test basic Finding creation."""
        loc = Location(start_offset=0, end_offset=5)
        finding = Finding(
            check_name="test.check",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc,
            original_text="hello",
            reasoning="Test reason",
            auto_applicable=False,
        )

        assert finding.check_name == "test.check"
        assert finding.category == "voice"
        assert finding.severity == "warning"
        assert finding.confidence == 0.9
        assert finding.location == loc
        assert finding.original_text == "hello"
        assert finding.reasoning == "Test reason"
        assert finding.auto_applicable is False

    def test_finding_immutable(self):
        """Test that Finding is frozen (immutable)."""
        loc = Location(start_offset=0, end_offset=5)
        finding = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc,
            original_text="hello",
            reasoning="Test reason",
            auto_applicable=False,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            finding.check_name = "other"

    def test_finding_confidence_validation(self):
        """Test confidence must be between 0 and 1."""
        loc = Location(start_offset=0, end_offset=5)

        with pytest.raises(ValueError):
            Finding(
                check_name="test",
                category="voice",
                severity="warning",
                confidence=1.5,  # Invalid
                location=loc,
                original_text="hello",
                reasoning="Test",
                auto_applicable=False,
            )

        with pytest.raises(ValueError):
            Finding(
                check_name="test",
                category="voice",
                severity="warning",
                confidence=-0.1,  # Invalid
                location=loc,
                original_text="hello",
                reasoning="Test",
                auto_applicable=False,
            )

    def test_finding_auto_applicable_requires_proposed_text(self):
        """Test auto_applicable=True requires proposed_text."""
        loc = Location(start_offset=0, end_offset=5)

        with pytest.raises(ValueError):
            Finding(
                check_name="test",
                category="voice",
                severity="warning",
                confidence=1.0,
                location=loc,
                original_text="hello",
                reasoning="Test",
                auto_applicable=True,  # But no proposed_text
            )

    def test_finding_schema_version(self):
        """Test schema_version is present."""
        loc = Location(start_offset=0, end_offset=5)
        finding = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc,
            original_text="hello",
            reasoning="Test",
            auto_applicable=False,
        )

        assert finding.schema_version == "1.0"

    def test_finding_has_fix(self):
        """Test has_fix property."""
        loc = Location(start_offset=0, end_offset=5)

        # Without fix
        finding1 = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc,
            original_text="hello",
            reasoning="Test",
            auto_applicable=False,
        )
        assert finding1.has_fix is False

        # With fix
        finding2 = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=1.0,
            location=loc,
            original_text="hello",
            proposed_text="world",
            reasoning="Test",
            auto_applicable=True,
        )
        assert finding2.has_fix is True

    def test_finding_is_deterministic(self):
        """Test is_deterministic property."""
        loc = Location(start_offset=0, end_offset=5)

        # Deterministic: confidence=1.0 AND auto_applicable
        finding1 = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=1.0,
            location=loc,
            original_text="hello",
            proposed_text="world",
            reasoning="Test",
            auto_applicable=True,
        )
        assert finding1.is_deterministic is True

        # Not deterministic: confidence < 1.0
        finding2 = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc,
            original_text="hello",
            reasoning="Test",
            auto_applicable=False,
        )
        assert finding2.is_deterministic is False

    def test_finding_span_length(self):
        """Test span_length property."""
        loc = Location(start_offset=10, end_offset=50)
        finding = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc,
            original_text="some text",
            reasoning="Test",
            auto_applicable=False,
        )
        assert finding.span_length == 40

    def test_finding_overlaps(self):
        """Test overlaps method."""
        loc1 = Location(start_offset=0, end_offset=10)
        loc2 = Location(start_offset=5, end_offset=15)
        loc3 = Location(start_offset=20, end_offset=30)

        finding1 = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc1,
            original_text="text",
            reasoning="Test",
            auto_applicable=False,
        )
        finding2 = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc2,
            original_text="text",
            reasoning="Test",
            auto_applicable=False,
        )
        finding3 = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc3,
            original_text="text",
            reasoning="Test",
            auto_applicable=False,
        )

        assert finding1.overlaps(finding2)
        assert finding2.overlaps(finding1)
        assert not finding1.overlaps(finding3)

    def test_finding_metadata_dict(self):
        """Test metadata_dict property."""
        loc = Location(start_offset=0, end_offset=5)
        finding = Finding(
            check_name="test",
            category="stop_words",
            severity="warning",
            confidence=1.0,
            location=loc,
            original_text="delve",
            proposed_text="explore",
            reasoning="Stop word",
            auto_applicable=True,
            metadata=(("word", "delve"), ("tier", "hard")),
        )

        meta = finding.metadata_dict
        assert meta["word"] == "delve"
        assert meta["tier"] == "hard"


class TestFindingSerialization:
    """Tests for Finding serialization."""

    def test_finding_to_dict(self):
        """Test serialization to dictionary."""
        loc = Location(section_index=0, start_offset=0, end_offset=5)
        finding = Finding(
            check_name="test.check",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc,
            original_text="hello",
            reasoning="Test reason",
            auto_applicable=False,
        )

        data = finding.to_dict()
        assert data["check_name"] == "test.check"
        assert data["category"] == "voice"
        assert data["severity"] == "warning"
        assert data["confidence"] == 0.9
        assert data["location"]["start_offset"] == 0
        assert data["original_text"] == "hello"
        assert data["schema_version"] == "1.0"

    def test_finding_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "check_name": "test.check",
            "category": "voice",
            "severity": "warning",
            "confidence": 0.9,
            "location": {"start_offset": 0, "end_offset": 5},
            "original_text": "hello",
            "reasoning": "Test reason",
            "auto_applicable": False,
        }

        finding = Finding.from_dict(data)
        assert finding.check_name == "test.check"
        assert finding.category == "voice"
        assert finding.location.start_offset == 0

    def test_finding_roundtrip(self):
        """Test to_dict/from_dict roundtrip."""
        loc = Location(section_index=0, start_offset=10, end_offset=20)
        original = Finding(
            check_name="test.check",
            category="stop_words",
            severity="error",
            confidence=1.0,
            location=loc,
            original_text="delve",
            proposed_text="explore",
            reasoning="Hard stop word",
            auto_applicable=True,
            metadata=(("tier", "hard"),),
        )

        data = original.to_dict()
        restored = Finding.from_dict(data)

        assert restored.check_name == original.check_name
        assert restored.category == original.category
        assert restored.severity == original.severity
        assert restored.confidence == original.confidence
        assert restored.original_text == original.original_text
        assert restored.proposed_text == original.proposed_text

    def test_finding_to_json(self):
        """Test JSON serialization."""
        loc = Location(start_offset=0, end_offset=5)
        finding = Finding(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc,
            original_text="hello",
            reasoning="Test",
            auto_applicable=False,
        )

        json_str = finding.to_json()
        data = json.loads(json_str)
        assert data["check_name"] == "test"

    def test_finding_from_json(self):
        """Test JSON deserialization."""
        json_str = json.dumps({
            "check_name": "test",
            "category": "voice",
            "severity": "warning",
            "confidence": 0.9,
            "location": {"start_offset": 0, "end_offset": 5},
            "original_text": "hello",
            "reasoning": "Test",
            "auto_applicable": False,
        })

        finding = Finding.from_json(json_str)
        assert finding.check_name == "test"


class TestFindingFactory:
    """Tests for FindingFactory."""

    def test_factory_creates_with_id_and_timestamp(self):
        """Test factory generates ID and timestamp."""
        loc = Location(start_offset=0, end_offset=5)
        finding = FindingFactory.create(
            check_name="test",
            category="voice",
            severity="warning",
            confidence=0.9,
            location=loc,
            original_text="hello",
            reasoning="Test",
            auto_applicable=False,
        )

        assert finding.finding_id is not None
        assert len(finding.finding_id) == 16  # 16 hex chars
        assert finding.created_at is not None
        assert finding.created_at.endswith("Z")  # ISO format with Z

    def test_factory_with_metadata(self):
        """Test factory with metadata dict."""
        loc = Location(start_offset=0, end_offset=5)
        finding = FindingFactory.create(
            check_name="stop_words.hard",
            category="stop_words",
            severity="error",
            confidence=1.0,
            location=loc,
            original_text="delve",
            proposed_text="explore",
            reasoning="Hard stop word",
            auto_applicable=True,
            metadata={"word": "delve", "tier": "hard"},
        )

        assert finding.metadata_dict["word"] == "delve"
        assert finding.metadata_dict["tier"] == "hard"


class TestFindingCollection:
    """Tests for FindingCollection."""

    @pytest.fixture
    def sample_findings(self):
        """Create sample findings for testing."""
        loc1 = Location(start_offset=0, end_offset=5)
        loc2 = Location(start_offset=10, end_offset=15)
        loc3 = Location(start_offset=20, end_offset=25)

        return [
            Finding(
                check_name="voice.third_person",
                category="voice",
                severity="warning",
                confidence=1.0,
                location=loc1,
                original_text="players",
                proposed_text="you",
                reasoning="Third person",
                auto_applicable=True,
            ),
            Finding(
                check_name="stop_words.hard",
                category="stop_words",
                severity="error",
                confidence=1.0,
                location=loc2,
                original_text="delve",
                proposed_text="explore",
                reasoning="Hard stop word",
                auto_applicable=True,
            ),
            Finding(
                check_name="flow.redundant",
                category="flow",
                severity="suggestion",
                confidence=0.7,
                location=loc3,
                original_text="paragraph",
                reasoning="Redundant content",
                auto_applicable=False,
            ),
        ]

    def test_collection_creation(self, sample_findings):
        """Test collection creation."""
        collection = FindingCollection(sample_findings)
        assert len(collection) == 3

    def test_collection_add(self, sample_findings):
        """Test adding to collection."""
        collection = FindingCollection()
        collection.add(sample_findings[0])
        assert len(collection) == 1

    def test_collection_extend(self, sample_findings):
        """Test extending collection."""
        collection = FindingCollection()
        collection.extend(sample_findings)
        assert len(collection) == 3

    def test_collection_iteration(self, sample_findings):
        """Test iteration over collection."""
        collection = FindingCollection(sample_findings)
        findings = list(collection)
        assert len(findings) == 3

    def test_collection_by_category(self, sample_findings):
        """Test filtering by category."""
        collection = FindingCollection(sample_findings)
        voice = collection.by_category("voice")
        assert len(voice) == 1
        assert voice[0].category == "voice"

    def test_collection_by_severity(self, sample_findings):
        """Test filtering by severity."""
        collection = FindingCollection(sample_findings)
        errors = collection.by_severity("error")
        assert len(errors) == 1
        assert errors[0].severity == "error"

    def test_collection_errors_warnings_suggestions(self, sample_findings):
        """Test convenience severity filters."""
        collection = FindingCollection(sample_findings)
        assert len(collection.errors()) == 1
        assert len(collection.warnings()) == 1
        assert len(collection.suggestions()) == 1

    def test_collection_auto_applicable(self, sample_findings):
        """Test auto_applicable filter."""
        collection = FindingCollection(sample_findings)
        auto = collection.auto_applicable()
        assert len(auto) == 2
        for f in auto:
            assert f.auto_applicable is True

    def test_collection_proposals(self, sample_findings):
        """Test proposals filter (not auto-applicable but has fix)."""
        # Our sample doesn't have proposals (not auto but with fix)
        # Add one for testing
        loc = Location(start_offset=30, end_offset=35)
        proposal = Finding(
            check_name="judgment.rewrite",
            category="flow",
            severity="suggestion",
            confidence=0.8,
            location=loc,
            original_text="original",
            proposed_text="rewritten",
            reasoning="Better flow",
            auto_applicable=False,
        )
        collection = FindingCollection(sample_findings + [proposal])

        proposals = collection.proposals()
        assert len(proposals) == 1
        assert proposals[0].check_name == "judgment.rewrite"

    def test_collection_comments_only(self, sample_findings):
        """Test comments_only filter (no fix)."""
        collection = FindingCollection(sample_findings)
        comments = collection.comments_only()
        assert len(comments) == 1
        assert comments[0].has_fix is False

    def test_collection_sorted_by_position(self, sample_findings):
        """Test sorting by position."""
        # Reverse the order
        reversed_findings = list(reversed(sample_findings))
        collection = FindingCollection(reversed_findings)

        sorted_findings = collection.sorted_by_position()
        assert sorted_findings[0].location.start_offset == 0
        assert sorted_findings[1].location.start_offset == 10
        assert sorted_findings[2].location.start_offset == 20

    def test_collection_sorted_by_severity(self, sample_findings):
        """Test sorting by severity."""
        collection = FindingCollection(sample_findings)
        sorted_findings = collection.sorted_by_severity()

        # error, warning, suggestion
        assert sorted_findings[0].severity == "error"
        assert sorted_findings[1].severity == "warning"
        assert sorted_findings[2].severity == "suggestion"

    def test_collection_summary(self, sample_findings):
        """Test summary generation."""
        collection = FindingCollection(sample_findings)
        summary = collection.summary()

        assert summary["total"] == 3
        assert summary["by_severity"]["error"] == 1
        assert summary["by_severity"]["warning"] == 1
        assert summary["by_severity"]["suggestion"] == 1
        assert summary["auto_applicable"] == 2
        assert summary["comments_only"] == 1

    def test_collection_to_json(self, sample_findings):
        """Test JSON serialization of collection."""
        collection = FindingCollection(sample_findings)
        json_str = collection.to_json()
        data = json.loads(json_str)

        assert len(data) == 3
        assert data[0]["check_name"] == "voice.third_person"

    def test_collection_from_json(self, sample_findings):
        """Test JSON deserialization of collection."""
        collection = FindingCollection(sample_findings)
        json_str = collection.to_json()

        restored = FindingCollection.from_json(json_str)
        assert len(restored) == 3

    def test_collection_filter(self, sample_findings):
        """Test custom filter function."""
        collection = FindingCollection(sample_findings)
        high_confidence = collection.filter(lambda f: f.confidence >= 1.0)
        assert len(high_confidence) == 2

    def test_collection_merge(self, sample_findings):
        """Test merging collections."""
        col1 = FindingCollection(sample_findings[:2])
        col2 = FindingCollection(sample_findings[2:])

        merged = col1.merge(col2)
        assert len(merged) == 3
