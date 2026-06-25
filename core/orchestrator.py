"""
Pitboss v4 - Check Orchestrator

Runs ALL registered checks against a Document and aggregates findings.
Uses the self-registration registry — never hardcodes check list.

Key features:
- Iterates all registered checks via registry
- Handles check errors gracefully (log, continue with others)
- Groups findings by auto_applicable vs proposals
- Groups findings by check_name
"""

from __future__ import annotations
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from .check_base import get_registry
from .document import Document
from .finding import Finding


logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """
    Result of running all checks against a document.

    Provides findings grouped by:
    - auto_applicable (True/False)
    - check_name
    - category

    Also tracks any check errors that occurred.
    """

    findings: list[Finding]
    """All findings from all checks."""

    auto_applicable: list[Finding]
    """Findings that can be auto-applied (auto_applicable=True)."""

    proposals: list[Finding]
    """Findings requiring human review (auto_applicable=False)."""

    by_check: dict[str, list[Finding]]
    """Findings grouped by check_name."""

    errors: dict[str, str] = field(default_factory=dict)
    """Check errors: check_name → error message."""

    warnings: dict[str, str] = field(default_factory=dict)
    """Check warnings: check_name → warning message."""

    @property
    def auto_count(self) -> int:
        """Count of auto-applicable findings."""
        return len(self.auto_applicable)

    @property
    def proposal_count(self) -> int:
        """Count of proposal findings."""
        return len(self.proposals)

    @property
    def total_count(self) -> int:
        """Total count of all findings."""
        return len(self.findings)

    @property
    def check_count(self) -> int:
        """Number of checks that produced findings."""
        return len(self.by_check)

    @property
    def error_count(self) -> int:
        """Number of checks that errored."""
        return len(self.errors)

    def findings_for_check(self, check_name: str) -> list[Finding]:
        """Get findings for a specific check."""
        return self.by_check.get(check_name, [])

    def auto_for_check(self, check_name: str) -> list[Finding]:
        """Get auto-applicable findings for a specific check."""
        return [f for f in self.findings_for_check(check_name) if f.auto_applicable]

    def proposals_for_check(self, check_name: str) -> list[Finding]:
        """Get proposal findings for a specific check."""
        return [f for f in self.findings_for_check(check_name) if not f.auto_applicable]

    def auto_counts_by_check(self) -> dict[str, int]:
        """Get auto-applicable count per check."""
        return {
            name: len([f for f in findings if f.auto_applicable])
            for name, findings in self.by_check.items()
        }

    def proposal_counts_by_check(self) -> dict[str, int]:
        """Get proposal count per check."""
        return {
            name: len([f for f in findings if not f.auto_applicable])
            for name, findings in self.by_check.items()
        }


def run_all_checks(
    document: Document,
    standards: Any,
    voice_model: Optional[Any] = None,
    brief: Optional[Any] = None,
) -> OrchestratorResult:
    """
    Run ALL registered checks against a document.

    Uses self-registration registry — never hardcodes the check list.
    This ensures extensibility: adding a new check requires only creating
    a new file with @register_check.

    Handles check errors gracefully:
    - Logs the error
    - Records it in errors dict
    - Continues with remaining checks

    Args:
        document: The parsed Document to check
        standards: Brand standards configuration
        voice_model: Optional layered voice model
        brief: Optional parsed BriefModel (for keywords, structure checks)

    Returns:
        OrchestratorResult with all findings grouped by various criteria
    """
    registry = get_registry()
    all_findings: list[Finding] = []
    errors: dict[str, str] = {}
    warnings: dict[str, str] = {}

    # Get all check instances
    checks = registry.all_instances()
    logger.info(f"Running {len(checks)} registered checks")

    for check in checks:
        check_name = check.metadata.name
        try:
            # Call run() with brief as keyword argument
            # Brief-aware checks (keywords, structure) accept it;
            # others ignore it via **kwargs or have it as optional param
            findings = check.run(
                document,
                standards,
                voice_model,
                brief=brief,
            )
            all_findings.extend(findings)
            logger.debug(f"Check '{check_name}' produced {len(findings)} findings")

            # Collect any warnings from the check
            if hasattr(check, 'get_warning') and check.get_warning():
                warnings[check_name] = check.get_warning()

        except TypeError as e:
            # Handle checks that don't accept brief parameter
            # Try again without brief
            if "brief" in str(e):
                try:
                    findings = check.run(document, standards, voice_model)
                    all_findings.extend(findings)
                    logger.debug(
                        f"Check '{check_name}' (no brief) produced {len(findings)} findings"
                    )
                    # Collect any warnings from the check
                    if hasattr(check, 'get_warning') and check.get_warning():
                        warnings[check_name] = check.get_warning()
                except Exception as inner_e:
                    errors[check_name] = str(inner_e)
                    logger.warning(f"Check '{check_name}' failed: {inner_e}")
            else:
                errors[check_name] = str(e)
                logger.warning(f"Check '{check_name}' failed: {e}")

        except Exception as e:
            # Log error, record it, continue with other checks
            errors[check_name] = str(e)
            logger.warning(f"Check '{check_name}' failed: {e}")
            continue

    # Partition by auto_applicable
    auto_applicable = [f for f in all_findings if f.auto_applicable]
    proposals = [f for f in all_findings if not f.auto_applicable]

    # Group by check_name
    by_check: dict[str, list[Finding]] = defaultdict(list)
    for finding in all_findings:
        by_check[finding.check_name].append(finding)

    logger.info(
        f"Orchestrator complete: {len(all_findings)} findings "
        f"({len(auto_applicable)} auto, {len(proposals)} proposals), "
        f"{len(errors)} errors"
    )

    return OrchestratorResult(
        findings=all_findings,
        auto_applicable=auto_applicable,
        proposals=proposals,
        by_check=dict(by_check),
        errors=errors,
        warnings=warnings,
    )


def run_checks_by_name(
    document: Document,
    standards: Any,
    check_names: list[str],
    voice_model: Optional[Any] = None,
    brief: Optional[Any] = None,
) -> OrchestratorResult:
    """
    Run specific checks by name.

    Useful for running a subset of checks or re-running specific ones.

    Args:
        document: The parsed Document to check
        standards: Brand standards configuration
        check_names: List of check names to run
        voice_model: Optional layered voice model
        brief: Optional parsed BriefModel

    Returns:
        OrchestratorResult with findings from specified checks
    """
    registry = get_registry()
    all_findings: list[Finding] = []
    errors: dict[str, str] = {}
    warnings: dict[str, str] = {}

    for name in check_names:
        check = registry.get_instance(name)
        if check is None:
            errors[name] = f"Check '{name}' not found in registry"
            logger.warning(f"Check '{name}' not found in registry")
            continue

        try:
            findings = check.run(document, standards, voice_model, brief=brief)
            all_findings.extend(findings)
            # Collect any warnings from the check
            if hasattr(check, 'get_warning') and check.get_warning():
                warnings[name] = check.get_warning()

        except TypeError as e:
            if "brief" in str(e):
                try:
                    findings = check.run(document, standards, voice_model)
                    all_findings.extend(findings)
                    # Collect any warnings from the check
                    if hasattr(check, 'get_warning') and check.get_warning():
                        warnings[name] = check.get_warning()
                except Exception as inner_e:
                    errors[name] = str(inner_e)
                    logger.warning(f"Check '{name}' failed: {inner_e}")
            else:
                errors[name] = str(e)
                logger.warning(f"Check '{name}' failed: {e}")

        except Exception as e:
            errors[name] = str(e)
            logger.warning(f"Check '{name}' failed: {e}")

    # Partition and group
    auto_applicable = [f for f in all_findings if f.auto_applicable]
    proposals = [f for f in all_findings if not f.auto_applicable]

    by_check: dict[str, list[Finding]] = defaultdict(list)
    for finding in all_findings:
        by_check[finding.check_name].append(finding)

    return OrchestratorResult(
        findings=all_findings,
        auto_applicable=auto_applicable,
        proposals=proposals,
        by_check=dict(by_check),
        errors=errors,
        warnings=warnings,
    )
