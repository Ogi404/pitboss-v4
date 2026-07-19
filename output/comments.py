"""
Pitboss v4 - Comment Drafting

Turns proposal findings into structured writer comments.
Proposals are findings that can't be auto-applied (need human review).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import logging

from core.document import Document
from core.finding import Finding


logger = logging.getLogger(__name__)


@dataclass
class DraftedComment:
    """A drafted writer comment."""

    finding_id: str
    """Stable ID of the source Finding (for linking back to comment_id)."""

    section: Optional[str]
    """Section heading title (if identifiable)."""

    paragraph_index: int
    """Element index in the document."""

    location_desc: str
    """Human-readable location description."""

    issue: str
    """What's wrong (the issue being flagged)."""

    suggestion: Optional[str]
    """Proposed fix (if any)."""

    reasoning: str
    """Why it's flagged."""

    severity: str
    """Severity level: error, warning, suggestion."""

    check_name: str
    """Name of the check that flagged this."""

    original_text: str
    """The original text that was flagged."""

    @property
    def has_suggestion(self) -> bool:
        """Whether this comment has a suggested fix."""
        return self.suggestion is not None

    @property
    def is_error(self) -> bool:
        """Whether this is an error-severity comment."""
        return self.severity == "error"


def draft_comments(
    proposals: list[Finding],
    document: Document,
    corrected_document: Optional[Document] = None,
) -> list[DraftedComment]:
    """
    Turn proposal findings into structured comments.

    Comments are grouped by section for readability.

    Args:
        proposals: List of findings (should be auto_applicable=False)
        document: The original document for context lookup
        corrected_document: The corrected document (after auto-fixes) for anchor
            reconciliation. If provided, anchor text will be verified against
            this document, and updated if the original text was modified by
            an auto-fix. This prevents "Original content deleted" errors when
            posting comments to the corrected document.

    Returns:
        List of DraftedComment objects, sorted by position
    """
    comments = []

    # Build corrected doc full text for anchor verification
    corrected_text = corrected_document.full_text() if corrected_document else None

    for finding in proposals:
        # Find section context
        section = document.section_at_offset(finding.location.start_offset)
        section_title = section.title if section else None

        # Get paragraph index
        para_idx = finding.location.paragraph_index
        if para_idx is None:
            para_idx = document.element_index_at_offset(finding.location.start_offset)

        # Build location description
        if section_title:
            loc_desc = f"In section '{section_title}'"
            if para_idx is not None:
                loc_desc += f", element {para_idx + 1}"
        else:
            if para_idx is not None:
                loc_desc = f"Element {para_idx + 1}"
            else:
                loc_desc = f"At position {finding.location.start_offset}"

        # Build issue description from reasoning
        issue = finding.reasoning
        if not issue:
            issue = f"Flagged by {finding.check_name}"

        # Reconcile anchor text with corrected document
        anchor_text = finding.original_text
        if corrected_text is not None and anchor_text not in corrected_text:
            # Original text was modified by auto-fix, find fallback anchor
            anchor_text = _find_fallback_anchor(
                finding, corrected_document, para_idx
            )
            if anchor_text != finding.original_text:
                logger.debug(
                    f"Anchor reconciled for {finding.check_name}: "
                    f"'{finding.original_text[:30]}...' -> '{anchor_text[:30]}...'"
                )

        comments.append(DraftedComment(
            finding_id=finding.finding_id,
            section=section_title,
            paragraph_index=para_idx if para_idx is not None else 0,
            location_desc=loc_desc,
            issue=issue,
            suggestion=finding.proposed_text,
            reasoning=finding.reasoning,
            severity=finding.severity,
            check_name=finding.check_name,
            original_text=anchor_text,  # Use reconciled anchor
        ))

    # Sort by section, then by paragraph index
    comments.sort(key=lambda c: (c.section or '', c.paragraph_index))

    logger.info(f"Drafted {len(comments)} comments from {len(proposals)} proposals")
    return comments


def _find_fallback_anchor(
    finding: Finding,
    corrected_document: Document,
    para_idx: Optional[int],
) -> str:
    """
    Find fallback anchor text when original was modified by auto-fix.

    Strategy:
    1. Try to find the element at paragraph_index in corrected doc
    2. Use that element's text as anchor (truncated if needed)
    3. If element not found, return original (will likely orphan)
    """
    if para_idx is None or para_idx >= len(corrected_document.elements):
        return finding.original_text

    element = corrected_document.elements[para_idx]
    element_text = element.text if hasattr(element, 'text') else ''

    if not element_text:
        return finding.original_text

    # Use element text as anchor (will be truncated to 100 chars by gdoc_comments)
    return element_text


def comments_to_markdown(comments: list[DraftedComment]) -> str:
    """
    Export comments as readable markdown.

    Groups comments by section for easy scanning.

    Args:
        comments: List of DraftedComment objects

    Returns:
        Markdown-formatted string
    """
    if not comments:
        return "# Writer Comments\n\nNo comments to address.\n"

    lines = ["# Writer Comments\n"]

    current_section = None
    for comment in comments:
        # Add section header if changed
        if comment.section != current_section:
            current_section = comment.section
            section_name = current_section or "General"
            lines.append(f"\n## {section_name}\n")

        # Format the comment
        severity_badge = f"[{comment.severity.upper()}]"
        lines.append(f"### {severity_badge} {comment.check_name}")
        lines.append(f"**Location:** {comment.location_desc}\n")

        # Quote original text
        original_preview = comment.original_text
        if len(original_preview) > 100:
            original_preview = original_preview[:100] + "..."
        lines.append(f"**Original:** \"{original_preview}\"\n")

        lines.append(f"**Issue:** {comment.issue}\n")

        if comment.suggestion:
            lines.append(f"**Suggestion:** \"{comment.suggestion}\"\n")

        lines.append("")  # Blank line between comments

    # Add summary
    error_count = sum(1 for c in comments if c.is_error)
    warning_count = sum(1 for c in comments if c.severity == "warning")
    suggestion_count = sum(1 for c in comments if c.severity == "suggestion")

    lines.append("---")
    lines.append(f"**Total:** {len(comments)} comments")
    if error_count:
        lines.append(f"- Errors: {error_count}")
    if warning_count:
        lines.append(f"- Warnings: {warning_count}")
    if suggestion_count:
        lines.append(f"- Suggestions: {suggestion_count}")

    return "\n".join(lines)


def comments_to_json(comments: list[DraftedComment]) -> list[dict]:
    """
    Export comments as JSON-serializable list.

    Useful for programmatic consumption.

    Args:
        comments: List of DraftedComment objects

    Returns:
        List of dictionaries
    """
    return [
        {
            "finding_id": c.finding_id,
            "section": c.section,
            "paragraph_index": c.paragraph_index,
            "location_desc": c.location_desc,
            "issue": c.issue,
            "suggestion": c.suggestion,
            "reasoning": c.reasoning,
            "severity": c.severity,
            "check_name": c.check_name,
            "original_text": c.original_text,
        }
        for c in comments
    ]


def group_comments_by_check(comments: list[DraftedComment]) -> dict[str, list[DraftedComment]]:
    """
    Group comments by check name.

    Useful for showing "X issues from stop_words check" summaries.

    Args:
        comments: List of DraftedComment objects

    Returns:
        Dict mapping check_name to list of comments
    """
    grouped: dict[str, list[DraftedComment]] = {}

    for comment in comments:
        if comment.check_name not in grouped:
            grouped[comment.check_name] = []
        grouped[comment.check_name].append(comment)

    return grouped


def group_comments_by_severity(comments: list[DraftedComment]) -> dict[str, list[DraftedComment]]:
    """
    Group comments by severity.

    Args:
        comments: List of DraftedComment objects

    Returns:
        Dict mapping severity to list of comments
    """
    grouped: dict[str, list[DraftedComment]] = {
        "error": [],
        "warning": [],
        "suggestion": [],
    }

    for comment in comments:
        if comment.severity in grouped:
            grouped[comment.severity].append(comment)

    return grouped
