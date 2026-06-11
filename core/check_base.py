"""
Pitboss v4 - Check Interface (Frozen Contract #3)

This module defines the check interface that EVERY check implements.
It is one of the three frozen contracts that forms the foundation of the system.

Key components:
- CheckBase: Abstract base class with run(document, standards, voice_model) signature
- CheckRegistry: Self-registration mechanism for check discovery
- @register_check: Decorator for check registration
- DeterministicCheck / JudgmentCheck: Helper base classes

Design principle: A new check is a new file satisfying the interface. The orchestrator
discovers registered checks; it never hardcodes a list.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Type, Any
from enum import Enum

from .document import Document
from .finding import Finding, Category


class CheckType(Enum):
    """Classification of check types."""
    DETERMINISTIC = "deterministic"  # Pure code, no LLM - the 95%
    JUDGMENT = "judgment"            # LLM-assisted - the 5%


@dataclass(frozen=True)
class CheckMetadata:
    """
    Metadata about a check for discovery and documentation.

    Frozen to ensure metadata is immutable after creation.
    """
    name: str
    """Unique identifier (e.g., 'voice.third_person', 'stop_words.hard')"""

    display_name: str
    """Human-readable name (e.g., 'Third Person Detection')"""

    category: Category
    """Primary category for grouping"""

    check_type: CheckType
    """Deterministic or judgment"""

    description: str
    """What this check does"""

    enabled_by_default: bool = True
    """Whether to run by default"""

    required_standards: tuple[str, ...] = field(default_factory=tuple)
    """Standards keys needed (e.g., ('stop_words.hard', 'voice.person'))"""

    schema_version: str = "1.0"
    """Schema version for this check's metadata"""


class CheckBase(ABC):
    """
    Abstract base class for all checks.

    Every check in the system (deterministic or judgment) implements this interface.
    The run() method receives the document, standards, and optional voice model,
    and returns a list of findings.

    This is a frozen contract - the interface signature is stable.
    """

    @property
    @abstractmethod
    def metadata(self) -> CheckMetadata:
        """Return metadata about this check."""
        pass

    @abstractmethod
    def run(
        self,
        document: Document,
        standards: Any,  # Standards object from standards_engine
        voice_model: Optional[Any] = None,  # VoiceModel, None for Phase 0
    ) -> list[Finding]:
        """
        Execute this check against a document.

        Args:
            document: The parsed document to check
            standards: The loaded standards (brand-specific, merged with defaults)
            voice_model: The layered voice model (None in Phase 0)

        Returns:
            List of Finding objects for any issues detected
        """
        pass

    @property
    def name(self) -> str:
        """Convenience property for check name."""
        return self.metadata.name

    @property
    def category(self) -> Category:
        """Convenience property for check category."""
        return self.metadata.category

    @property
    def is_deterministic(self) -> bool:
        """Whether this check is deterministic (no LLM)."""
        return self.metadata.check_type == CheckType.DETERMINISTIC

    @property
    def is_judgment(self) -> bool:
        """Whether this check uses LLM judgment."""
        return self.metadata.check_type == CheckType.JUDGMENT

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.name}'>"


class CheckRegistry:
    """
    Central registry for all checks in the system.

    Checks self-register using the @register_check decorator.
    The orchestrator queries this registry to discover available checks.

    Implemented as a singleton to ensure global consistency.
    """

    _instance: Optional[CheckRegistry] = None
    _checks: dict[str, Type[CheckBase]]

    def __new__(cls) -> CheckRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._checks = {}
        return cls._instance

    def register(self, check_class: Type[CheckBase]) -> Type[CheckBase]:
        """
        Register a check class.

        Args:
            check_class: The check class to register

        Returns:
            The check class (for decorator chaining)

        Raises:
            ValueError: If a check with the same name is already registered
        """
        # Instantiate to get metadata
        instance = check_class()
        name = instance.metadata.name

        if name in self._checks:
            raise ValueError(f"Check '{name}' is already registered")

        self._checks[name] = check_class
        return check_class

    def get(self, name: str) -> Optional[Type[CheckBase]]:
        """Get a check class by name."""
        return self._checks.get(name)

    def get_instance(self, name: str) -> Optional[CheckBase]:
        """Get an instance of a check by name."""
        check_class = self.get(name)
        return check_class() if check_class else None

    def all_checks(self) -> list[Type[CheckBase]]:
        """Return all registered check classes."""
        return list(self._checks.values())

    def all_instances(self) -> list[CheckBase]:
        """Return instances of all registered checks."""
        return [cls() for cls in self._checks.values()]

    def checks_by_category(self, category: Category) -> list[Type[CheckBase]]:
        """Return checks for a specific category."""
        return [
            cls for cls in self._checks.values()
            if cls().metadata.category == category
        ]

    def checks_by_type(self, check_type: CheckType) -> list[Type[CheckBase]]:
        """Return checks of a specific type (deterministic or judgment)."""
        return [
            cls for cls in self._checks.values()
            if cls().metadata.check_type == check_type
        ]

    def deterministic_checks(self) -> list[Type[CheckBase]]:
        """Return all deterministic checks."""
        return self.checks_by_type(CheckType.DETERMINISTIC)

    def judgment_checks(self) -> list[Type[CheckBase]]:
        """Return all judgment checks."""
        return self.checks_by_type(CheckType.JUDGMENT)

    def enabled_checks(self) -> list[Type[CheckBase]]:
        """Return checks that are enabled by default."""
        return [
            cls for cls in self._checks.values()
            if cls().metadata.enabled_by_default
        ]

    def check_names(self) -> list[str]:
        """Return names of all registered checks."""
        return list(self._checks.keys())

    def is_registered(self, name: str) -> bool:
        """Check if a check is registered."""
        return name in self._checks

    def clear(self) -> None:
        """Clear the registry (for testing)."""
        self._checks.clear()

    def __len__(self) -> int:
        return len(self._checks)

    def __contains__(self, name: str) -> bool:
        return name in self._checks


# Global registry instance
_registry = CheckRegistry()


def register_check(cls: Type[CheckBase]) -> Type[CheckBase]:
    """
    Decorator to register a check class.

    Usage:
        @register_check
        class VoiceThirdPersonCheck(CheckBase):
            ...

    The check will be automatically discoverable by the orchestrator.
    """
    return _registry.register(cls)


def get_registry() -> CheckRegistry:
    """Get the global check registry."""
    return _registry


# === Helper Base Classes ===


class DeterministicCheck(CheckBase):
    """
    Base class for deterministic checks (the 95%).

    Provides common utilities for regex-based, lookup-based checks.
    Subclasses implement _get_* methods and _find_issues().

    Deterministic checks:
    - Use pure code: regex, lookups, dictionaries
    - Have confidence=1.0 (always certain)
    - Are auto-applicable (can be applied automatically)
    - Produce the same output for the same input
    """

    @property
    def metadata(self) -> CheckMetadata:
        return CheckMetadata(
            name=self._get_name(),
            display_name=self._get_display_name(),
            category=self._get_category(),
            check_type=CheckType.DETERMINISTIC,
            description=self._get_description(),
            enabled_by_default=self._get_enabled_by_default(),
            required_standards=self._get_required_standards(),
        )

    @abstractmethod
    def _get_name(self) -> str:
        """Return the unique check name."""
        pass

    @abstractmethod
    def _get_display_name(self) -> str:
        """Return the human-readable name."""
        pass

    @abstractmethod
    def _get_category(self) -> Category:
        """Return the check category."""
        pass

    @abstractmethod
    def _get_description(self) -> str:
        """Return the check description."""
        pass

    def _get_enabled_by_default(self) -> bool:
        """Return whether enabled by default. Override to change."""
        return True

    def _get_required_standards(self) -> tuple[str, ...]:
        """Return required standards keys. Override to specify."""
        return ()

    @abstractmethod
    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """
        Find issues in the document.

        Override in subclasses to implement the actual check logic.

        Args:
            document: The document to check
            standards: The standards to check against

        Returns:
            List of findings for any issues detected
        """
        pass

    def run(
        self,
        document: Document,
        standards: Any,
        voice_model: Optional[Any] = None,
    ) -> list[Finding]:
        """Execute the check."""
        # voice_model is ignored for deterministic checks
        return self._find_issues(document, standards)


class JudgmentCheck(CheckBase):
    """
    Base class for judgment checks (the 5%).

    Provides common utilities for LLM-based checks with restraint scoring.
    Subclasses implement _has_trigger() and _generate_proposals().

    Judgment checks:
    - Use LLM for analysis
    - Have confidence < 1.0 (varying certainty)
    - Are NOT auto-applicable (require human review)
    - May produce different output for the same input
    - Must have a concrete trigger before proposing changes
    """

    @property
    def metadata(self) -> CheckMetadata:
        return CheckMetadata(
            name=self._get_name(),
            display_name=self._get_display_name(),
            category=self._get_category(),
            check_type=CheckType.JUDGMENT,
            description=self._get_description(),
            enabled_by_default=self._get_enabled_by_default(),
            required_standards=self._get_required_standards(),
        )

    @abstractmethod
    def _get_name(self) -> str:
        """Return the unique check name."""
        pass

    @abstractmethod
    def _get_display_name(self) -> str:
        """Return the human-readable name."""
        pass

    @abstractmethod
    def _get_category(self) -> Category:
        """Return the check category."""
        pass

    @abstractmethod
    def _get_description(self) -> str:
        """Return the check description."""
        pass

    def _get_enabled_by_default(self) -> bool:
        """Return whether enabled by default. Override to change."""
        return True

    def _get_required_standards(self) -> tuple[str, ...]:
        """Return required standards keys. Override to specify."""
        return ()

    @abstractmethod
    def _has_trigger(self, document: Document, standards: Any) -> bool:
        """
        Check if there's a concrete trigger for this check.

        Restraint scoring: no trigger means no proposal.
        This prevents the "everything-gets-touched" homogenization.

        Examples of triggers:
        - sentence > 25 words AND >= 3 clauses
        - paragraph semantically duplicates an adjacent one
        - section content doesn't deliver the heading's promise

        Args:
            document: The document to analyze
            standards: The standards to check against

        Returns:
            True if there's a concrete reason to run this check
        """
        pass

    @abstractmethod
    def _generate_proposals(
        self,
        document: Document,
        standards: Any,
        voice_model: Any,
    ) -> list[Finding]:
        """
        Generate proposals using LLM.

        Override in subclasses to implement the actual proposal logic.
        This is only called if _has_trigger() returns True.

        Args:
            document: The document to analyze
            standards: The standards to check against
            voice_model: The layered voice model for exemplar matching

        Returns:
            List of proposed findings with reasoning attached
        """
        pass

    def run(
        self,
        document: Document,
        standards: Any,
        voice_model: Optional[Any] = None,
    ) -> list[Finding]:
        """
        Execute the check with restraint scoring.

        Only generates proposals if there's a concrete trigger.
        """
        if not self._has_trigger(document, standards):
            return []
        return self._generate_proposals(document, standards, voice_model)
