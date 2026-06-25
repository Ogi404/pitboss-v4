"""
Pitboss v4 - Run Summary

Generates a summary report of a Pitboss run.
Includes counts by check, category, and severity.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime, timezone
import logging

from core.document import Document
from core.orchestrator import OrchestratorResult
from output.apply import ApplyResult
from output.comments import DraftedComment


logger = logging.getLogger(__name__)


@dataclass
class RunSummary:
    """Summary of a Pitboss run."""

    # File info
    article_path: str
    """Path to the article file."""

    brief_path: Optional[str] = None
    """Path to the brief file (if used)."""

    # Document stats
    word_count: int = 0
    """Approximate word count of the article."""

    element_count: int = 0
    """Number of elements in the document."""

    # Counts by check
    auto_applied: dict[str, int] = field(default_factory=dict)
    """Auto-applied finding count per check."""

    proposals: dict[str, int] = field(default_factory=dict)
    """Proposal finding count per check."""

    # Total counts
    total_auto_applied: int = 0
    """Total auto-applied findings."""

    total_proposals: int = 0
    """Total proposal findings."""

    comments_drafted: int = 0
    """Number of comments drafted."""

    # Conflicts and errors
    conflicts_downgraded: int = 0
    """Number of findings downgraded due to conflicts."""

    skipped_validation: int = 0
    """Number of findings skipped due to validation failure."""

    check_errors: dict[str, str] = field(default_factory=dict)
    """Check errors: check_name -> error message."""

    # Brief info (if available)
    brief_task: Optional[str] = None
    """Task from the brief."""

    brief_type: Optional[str] = None
    """Type from the brief."""

    # Timestamps
    run_timestamp: str = ""
    """ISO timestamp of the run."""

    # Warnings
    brand_warning: Optional[str] = None
    """Warning about brand config (e.g., brand not configured)."""

    @property
    def total_findings(self) -> int:
        """Total findings (auto + proposals)."""
        return self.total_auto_applied + self.total_proposals

    @property
    def has_errors(self) -> bool:
        """Whether any checks errored."""
        return len(self.check_errors) > 0


def generate_summary(
    orchestrator_result: OrchestratorResult,
    apply_result: ApplyResult,
    comments: list[DraftedComment],
    document: Document,
    brief: Optional[Any],
    article_path: str,
    brief_path: Optional[str] = None,
    brand_warning: Optional[str] = None,
) -> RunSummary:
    """
    Generate a run summary from pipeline results.

    Args:
        orchestrator_result: Result from running all checks
        apply_result: Result from applying auto-fixes
        comments: Drafted comments from proposals
        document: The document that was checked
        brief: The brief model (if used)
        article_path: Path to the article file
        brief_path: Path to the brief file (if used)

    Returns:
        RunSummary with all counts and info
    """
    # Calculate word count (approximate)
    full_text = document.full_text()
    word_count = len(full_text.split())

    # Count auto-applied by check
    auto_applied: dict[str, int] = {}
    for finding in apply_result.applied:
        check = finding.check_name
        auto_applied[check] = auto_applied.get(check, 0) + 1

    # Count proposals by check
    proposals: dict[str, int] = {}
    for finding in orchestrator_result.proposals:
        check = finding.check_name
        proposals[check] = proposals.get(check, 0) + 1

    # Add downgraded findings to proposals
    for finding in apply_result.downgraded:
        check = finding.check_name
        proposals[check] = proposals.get(check, 0) + 1

    # Brief info
    brief_task = None
    brief_type = None
    if brief:
        if hasattr(brief, 'task'):
            brief_task = brief.task
        if hasattr(brief, 'task_type'):
            brief_type = brief.task_type

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return RunSummary(
        article_path=article_path,
        brief_path=brief_path,
        word_count=word_count,
        element_count=len(document.elements),
        auto_applied=auto_applied,
        proposals=proposals,
        total_auto_applied=apply_result.applied_count,
        total_proposals=len(orchestrator_result.proposals) + apply_result.downgraded_count,
        comments_drafted=len(comments),
        conflicts_downgraded=apply_result.downgraded_count,
        skipped_validation=apply_result.skipped_count,
        check_errors=orchestrator_result.errors,
        brief_task=brief_task,
        brief_type=brief_type,
        run_timestamp=timestamp,
        brand_warning=brand_warning,
    )


def summary_to_markdown(summary: RunSummary) -> str:
    """
    Export summary as readable markdown.

    Args:
        summary: RunSummary object

    Returns:
        Markdown-formatted string
    """
    lines = ["# Pitboss Run Summary\n"]

    # File info
    lines.append(f"**Article:** {summary.article_path}")
    if summary.brief_path:
        lines.append(f"**Brief:** {summary.brief_path}")
    lines.append(f"**Word Count:** {summary.word_count:,}")
    lines.append(f"**Elements:** {summary.element_count}")
    lines.append(f"**Run Time:** {summary.run_timestamp}")
    if summary.brand_warning:
        lines.append(f"**Warning:** {summary.brand_warning}")
    lines.append("")

    # Brief info
    if summary.brief_task or summary.brief_type:
        lines.append("## Brief Info")
        if summary.brief_task:
            lines.append(f"- **Task:** {summary.brief_task}")
        if summary.brief_type:
            lines.append(f"- **Type:** {summary.brief_type}")
        lines.append("")

    # Auto-fixes applied
    if summary.auto_applied:
        lines.append(f"## Auto-Fixes Applied ({summary.total_auto_applied} total)\n")
        lines.append("| Check | Count |")
        lines.append("|-------|-------|")
        for check, count in sorted(summary.auto_applied.items(), key=lambda x: -x[1]):
            lines.append(f"| {check} | {count} |")
        lines.append("")
    else:
        lines.append("## Auto-Fixes Applied\n")
        lines.append("No auto-fixes applied.\n")

    # Proposals for review
    if summary.proposals:
        lines.append(f"## Proposals for Review ({summary.total_proposals} total)\n")
        lines.append("| Check | Count |")
        lines.append("|-------|-------|")
        for check, count in sorted(summary.proposals.items(), key=lambda x: -x[1]):
            lines.append(f"| {check} | {count} |")
        lines.append("")
    else:
        lines.append("## Proposals for Review\n")
        lines.append("No proposals requiring review.\n")

    # Comments
    lines.append(f"## Writer Comments Drafted: {summary.comments_drafted}\n")

    # Conflicts and skips
    if summary.conflicts_downgraded > 0 or summary.skipped_validation > 0:
        lines.append("## Processing Notes")
        if summary.conflicts_downgraded > 0:
            lines.append(f"- {summary.conflicts_downgraded} finding(s) downgraded due to overlapping spans")
        if summary.skipped_validation > 0:
            lines.append(f"- {summary.skipped_validation} finding(s) skipped due to text mismatch")
        lines.append("")

    # Errors
    if summary.check_errors:
        lines.append("## Errors\n")
        for check, error in summary.check_errors.items():
            lines.append(f"- **{check}:** {error}")
        lines.append("")
    else:
        lines.append("## Errors\n")
        lines.append("None.\n")

    return "\n".join(lines)


def summary_to_dict(summary: RunSummary) -> dict:
    """
    Export summary as JSON-serializable dictionary.

    Args:
        summary: RunSummary object

    Returns:
        Dictionary with all summary data
    """
    return {
        "article_path": summary.article_path,
        "brief_path": summary.brief_path,
        "word_count": summary.word_count,
        "element_count": summary.element_count,
        "auto_applied": summary.auto_applied,
        "proposals": summary.proposals,
        "total_auto_applied": summary.total_auto_applied,
        "total_proposals": summary.total_proposals,
        "comments_drafted": summary.comments_drafted,
        "conflicts_downgraded": summary.conflicts_downgraded,
        "skipped_validation": summary.skipped_validation,
        "check_errors": summary.check_errors,
        "brief_task": summary.brief_task,
        "brief_type": summary.brief_type,
        "run_timestamp": summary.run_timestamp,
        "brand_warning": summary.brand_warning,
    }
