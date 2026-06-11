"""
Pitboss v4 - Finding Dataclass (Frozen Contract #2)

This module defines the Finding object that EVERY check returns.
It is one of the three frozen contracts that forms the foundation of the system.

The Finding is the single language every downstream consumer speaks:
- Redline builder
- Comment builder
- Report generator
- Learning loop

Design principle: A generous superset so new check types never need to change it.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal, Any, Iterator
from datetime import datetime, timezone
import json
import hashlib

from .document import Location


# Severity levels with clear semantics
Severity = Literal["error", "warning", "suggestion"]

# Categories align with check modules
Category = Literal[
    "voice",           # 3rd->2nd person
    "stop_words",      # Weighted stop word detection
    "headings",        # Capitalization, hierarchy, descriptive
    "brand_names",     # Normalization, forbidden brands
    "locale_spelling", # UK/US/CA/AU/NZ spelling
    "currency",        # Symbol vs abbreviation consistency
    "formatting",      # Whitespace, punctuation, quoting
    "keywords",        # Density, coverage, highlighting
    "structure",       # Hierarchy, paragraph-between-headings
    "readability",     # Sentence length, paragraph length
    "consistency",     # Internal fact consistency
    "brief_coverage",  # Missing required content
    "flow",            # Paragraph transitions, redundancy
    "factcheck",       # Verified/contradicted claims
    "other",           # Catch-all for extensions
]


@dataclass(frozen=True)
class Finding:
    """
    The universal output of every check in the system.

    Immutable (frozen) to ensure findings cannot be modified after creation.
    All downstream consumers work with Finding objects.

    Schema version is embedded for future migration support.
    """

    # === Required Fields ===

    check_name: str
    """Name of the check that produced this finding (e.g., 'voice.third_person')"""

    category: Category
    """Category for grouping and filtering"""

    severity: Severity
    """How serious is this finding?"""

    confidence: float
    """0.0-1.0 confidence score. Deterministic checks should be 1.0."""

    location: Location
    """Precise location in the document"""

    original_text: str
    """The text that triggered this finding"""

    reasoning: str
    """Human-readable explanation of why this is flagged"""

    auto_applicable: bool
    """True for deterministic fixes that can be auto-applied"""

    # === Optional Fields ===

    proposed_text: Optional[str] = None
    """Suggested replacement. None for comment-only findings."""

    # === Metadata ===

    schema_version: str = "1.0"
    """Schema version for migration support"""

    metadata: tuple = field(default_factory=tuple)
    """
    Extensible metadata as frozen tuple of key-value pairs.
    Use metadata_dict property to access as dict.

    Examples:
    - stop_words: (("word", "delve"), ("tier", "hard"), ("weight", 1.0))
    - voice: (("source_pronoun", "players"), ("target_pronoun", "you"))
    - factcheck: (("claim", "..."), ("source_url", "..."), ("status", "contradicted"))
    """

    created_at: Optional[str] = None
    """ISO timestamp of creation (set by factory)"""

    finding_id: Optional[str] = None
    """Unique identifier for tracking (set by factory)"""

    def __post_init__(self):
        """Validate fields."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0-1, got {self.confidence}")
        if self.auto_applicable and self.proposed_text is None:
            raise ValueError("Auto-applicable findings must have proposed_text")

    @property
    def metadata_dict(self) -> dict:
        """Return metadata as a dictionary."""
        if isinstance(self.metadata, dict):
            return self.metadata
        return dict(self.metadata) if self.metadata else {}

    # === Serialization ===

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "check_name": self.check_name,
            "category": self.category,
            "severity": self.severity,
            "confidence": self.confidence,
            "location": self.location.to_dict(),
            "original_text": self.original_text,
            "proposed_text": self.proposed_text,
            "reasoning": self.reasoning,
            "auto_applicable": self.auto_applicable,
            "schema_version": self.schema_version,
            "metadata": self.metadata_dict,
            "created_at": self.created_at,
            "finding_id": self.finding_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Finding:
        """Deserialize from dictionary."""
        location = Location.from_dict(data["location"])

        # Convert metadata dict to tuple for frozen dataclass
        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            metadata_tuple = tuple(metadata.items())
        else:
            metadata_tuple = tuple(metadata) if metadata else ()

        return cls(
            check_name=data["check_name"],
            category=data["category"],
            severity=data["severity"],
            confidence=data["confidence"],
            location=location,
            original_text=data["original_text"],
            proposed_text=data.get("proposed_text"),
            reasoning=data["reasoning"],
            auto_applicable=data["auto_applicable"],
            schema_version=data.get("schema_version", "1.0"),
            metadata=metadata_tuple,
            created_at=data.get("created_at"),
            finding_id=data.get("finding_id"),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> Finding:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    # === Utility Methods ===

    @property
    def has_fix(self) -> bool:
        """Whether this finding has a proposed fix."""
        return self.proposed_text is not None

    @property
    def is_deterministic(self) -> bool:
        """Whether this is a deterministic (non-LLM) finding."""
        return self.confidence == 1.0 and self.auto_applicable

    @property
    def span_length(self) -> int:
        """Length of the affected text span."""
        return self.location.end_offset - self.location.start_offset

    def overlaps(self, other: Finding) -> bool:
        """Check if this finding overlaps with another."""
        return not (
            self.location.end_offset <= other.location.start_offset or
            other.location.end_offset <= self.location.start_offset
        )


class FindingFactory:
    """
    Factory for creating Finding objects with consistent defaults.

    Handles:
    - Automatic ID generation
    - Timestamp setting
    - Default metadata population
    """

    @staticmethod
    def create(
        check_name: str,
        category: Category,
        severity: Severity,
        confidence: float,
        location: Location,
        original_text: str,
        reasoning: str,
        auto_applicable: bool,
        proposed_text: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Finding:
        """Create a Finding with auto-generated ID and timestamp."""

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Generate deterministic ID from content
        id_content = f"{check_name}:{location.start_offset}:{location.end_offset}:{original_text}"
        finding_id = hashlib.sha256(id_content.encode()).hexdigest()[:16]

        # Convert metadata dict to tuple
        metadata_tuple = tuple(metadata.items()) if metadata else ()

        return Finding(
            check_name=check_name,
            category=category,
            severity=severity,
            confidence=confidence,
            location=location,
            original_text=original_text,
            proposed_text=proposed_text,
            reasoning=reasoning,
            auto_applicable=auto_applicable,
            metadata=metadata_tuple,
            created_at=now,
            finding_id=finding_id,
        )


class FindingCollection:
    """
    A collection of findings with filtering and aggregation methods.

    Used by the orchestrator and output builders.
    """

    def __init__(self, findings: Optional[list[Finding]] = None):
        self._findings: list[Finding] = list(findings) if findings else []

    def add(self, finding: Finding) -> None:
        """Add a finding to the collection."""
        self._findings.append(finding)

    def extend(self, findings: list[Finding]) -> None:
        """Add multiple findings to the collection."""
        self._findings.extend(findings)

    def __iter__(self) -> Iterator[Finding]:
        return iter(self._findings)

    def __len__(self) -> int:
        return len(self._findings)

    def __getitem__(self, index: int) -> Finding:
        return self._findings[index]

    # === Filtering Methods ===

    def by_category(self, category: Category) -> list[Finding]:
        """Return findings for a specific category."""
        return [f for f in self._findings if f.category == category]

    def by_severity(self, severity: Severity) -> list[Finding]:
        """Return findings for a specific severity."""
        return [f for f in self._findings if f.severity == severity]

    def by_check(self, check_name: str) -> list[Finding]:
        """Return findings from a specific check."""
        return [f for f in self._findings if f.check_name == check_name]

    def auto_applicable(self) -> list[Finding]:
        """Return findings that can be auto-applied."""
        return [f for f in self._findings if f.auto_applicable]

    def proposals(self) -> list[Finding]:
        """Return findings that are proposals (not auto-applicable but have fixes)."""
        return [f for f in self._findings if not f.auto_applicable and f.has_fix]

    def comments_only(self) -> list[Finding]:
        """Return findings that have no proposed fix."""
        return [f for f in self._findings if not f.has_fix]

    def errors(self) -> list[Finding]:
        """Return error-severity findings."""
        return self.by_severity("error")

    def warnings(self) -> list[Finding]:
        """Return warning-severity findings."""
        return self.by_severity("warning")

    def suggestions(self) -> list[Finding]:
        """Return suggestion-severity findings."""
        return self.by_severity("suggestion")

    def deterministic(self) -> list[Finding]:
        """Return deterministic findings (confidence=1.0 and auto-applicable)."""
        return [f for f in self._findings if f.is_deterministic]

    def judgment(self) -> list[Finding]:
        """Return judgment findings (not deterministic)."""
        return [f for f in self._findings if not f.is_deterministic]

    # === Sorting Methods ===

    def sorted_by_position(self) -> list[Finding]:
        """Return findings sorted by document position."""
        return sorted(self._findings, key=lambda f: f.location.start_offset)

    def sorted_by_severity(self) -> list[Finding]:
        """Return findings sorted by severity (error > warning > suggestion)."""
        severity_order = {"error": 0, "warning": 1, "suggestion": 2}
        return sorted(self._findings, key=lambda f: severity_order.get(f.severity, 3))

    def sorted_by_confidence(self, descending: bool = True) -> list[Finding]:
        """Return findings sorted by confidence."""
        return sorted(self._findings, key=lambda f: f.confidence, reverse=descending)

    # === Aggregation Methods ===

    def summary(self) -> dict:
        """Return a summary of findings by category and severity."""
        categories = set(f.category for f in self._findings)
        return {
            "total": len(self._findings),
            "by_severity": {
                "error": len(self.errors()),
                "warning": len(self.warnings()),
                "suggestion": len(self.suggestions()),
            },
            "by_category": {
                cat: len(self.by_category(cat))
                for cat in categories
            },
            "auto_applicable": len(self.auto_applicable()),
            "proposals": len(self.proposals()),
            "comments_only": len(self.comments_only()),
        }

    def to_list(self) -> list[Finding]:
        """Return findings as a list."""
        return list(self._findings)

    def to_dict_list(self) -> list[dict]:
        """Return findings as a list of dictionaries."""
        return [f.to_dict() for f in self._findings]

    def to_json(self) -> str:
        """Return findings as JSON string."""
        return json.dumps(self.to_dict_list(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> FindingCollection:
        """Create collection from JSON string."""
        data = json.loads(json_str)
        findings = [Finding.from_dict(d) for d in data]
        return cls(findings)

    def clear(self) -> None:
        """Clear all findings."""
        self._findings.clear()

    def filter(self, predicate) -> FindingCollection:
        """Return a new collection with findings matching the predicate."""
        return FindingCollection([f for f in self._findings if predicate(f)])

    def merge(self, other: FindingCollection) -> FindingCollection:
        """Merge with another collection, returning a new collection."""
        return FindingCollection(self._findings + other._findings)
