"""
Pitboss v4 - Apply Layer

Applies auto_applicable findings to produce a corrected Document.

Critical concerns:
- OFFSET MANAGEMENT: Applying an edit shifts all later offsets.
  Sort auto-applicable findings by position DESCENDING (apply last-to-first)
  so earlier offsets stay valid.
- CONFLICT DETECTION: Two findings may touch overlapping spans.
  When conflict: apply first, DOWNGRADE second to proposal.
- FORMATTING PRESERVATION: Preserve bold/italic/highlight/hyperlinks.
"""

from __future__ import annotations
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Union

from core.document import (
    Document,
    Paragraph,
    Heading,
    List,
    ListItem,
    Table,
    TextRun,
    BlockElement,
)
from core.finding import Finding


logger = logging.getLogger(__name__)


@dataclass
class ApplyResult:
    """Result of applying auto-applicable findings."""

    applied: list[Finding] = field(default_factory=list)
    """Successfully applied findings."""

    skipped: list[Finding] = field(default_factory=list)
    """Skipped due to validation failure (original_text mismatch)."""

    downgraded: list[Finding] = field(default_factory=list)
    """Downgraded to proposal due to conflict."""

    conflicts: list[tuple[Finding, Finding]] = field(default_factory=list)
    """Pairs that conflicted (first was applied, second downgraded)."""

    document: Document = field(default_factory=lambda: Document(elements=[]))
    """Modified document with edits applied."""

    @property
    def applied_count(self) -> int:
        """Count of successfully applied findings."""
        return len(self.applied)

    @property
    def skipped_count(self) -> int:
        """Count of skipped findings."""
        return len(self.skipped)

    @property
    def downgraded_count(self) -> int:
        """Count of downgraded findings."""
        return len(self.downgraded)

    @property
    def conflict_count(self) -> int:
        """Count of conflicts detected."""
        return len(self.conflicts)


@dataclass
class SkipReason:
    """Detailed reason why a finding was skipped."""
    finding_id: str
    check_name: str
    reason: str  # "text_mismatch" | "no_proposed_text" | "conflict" | "not_found"
    detail: str  # Human-readable explanation
    original_text: str | None = None
    actual_text: str | None = None  # For text_mismatch
    conflicting_with: str | None = None  # For conflict (finding_id of winner)


@dataclass
class SelectionApplyResult:
    """Result of applying user-selected findings (two-phase flow)."""

    applied: list[Finding] = field(default_factory=list)
    """Successfully applied findings."""

    skipped: list[SkipReason] = field(default_factory=list)
    """Skipped with detailed reasons."""

    downgraded: list[SkipReason] = field(default_factory=list)
    """Downgraded to proposal with reasons (conflict)."""

    document: Document = field(default_factory=lambda: Document(elements=[]))
    """Modified document with edits applied."""

    @property
    def applied_count(self) -> int:
        return len(self.applied)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def downgraded_count(self) -> int:
        return len(self.downgraded)


def apply_auto_findings(
    document: Document,
    findings: list[Finding],
) -> ApplyResult:
    """
    Apply auto_applicable findings to produce corrected document.

    CRITICAL: Sorts by position DESCENDING (apply last-to-first)
    so earlier offsets stay valid after edits.

    Args:
        document: The document to modify (will be deep-copied)
        findings: List of findings (filters to auto_applicable only)

    Returns:
        ApplyResult with modified document and tracking info
    """
    # Deep copy document to avoid mutating original
    doc = deepcopy(document)

    # Filter to only auto_applicable findings with proposed_text
    # Also exclude no-op edits where original == proposed (these damage run structure)
    auto_findings = [
        f for f in findings
        if f.auto_applicable
        and f.proposed_text is not None
        and f.proposed_text != f.original_text  # Skip no-op edits
    ]

    if not auto_findings:
        logger.info("No auto-applicable findings to apply")
        return ApplyResult(document=doc)

    logger.info(f"Processing {len(auto_findings)} auto-applicable findings")

    # Step 1: Validate original_text matches document
    validated, skipped = _validate_findings(doc, auto_findings)

    if skipped:
        logger.warning(f"Skipped {len(skipped)} findings due to text mismatch")

    # Step 2: Detect conflicts (overlapping spans)
    to_apply, downgraded, conflicts = _detect_conflicts(validated)

    if conflicts:
        logger.info(f"Detected {len(conflicts)} conflicts, downgraded {len(downgraded)} findings")

    # Step 3: Sort by position DESCENDING (apply last-to-first)
    sorted_findings = sorted(
        to_apply,
        key=lambda f: f.location.start_offset,
        reverse=True,
    )

    # Step 4: Apply each finding
    applied = []
    for finding in sorted_findings:
        success = _apply_single_finding(doc, finding)
        if success:
            applied.append(finding)
        else:
            skipped.append(finding)

    logger.info(
        f"Applied {len(applied)} findings, "
        f"skipped {len(skipped)}, downgraded {len(downgraded)}"
    )

    # Step 5: Recalculate element offsets
    _recalculate_offsets(doc)

    return ApplyResult(
        applied=applied,
        skipped=skipped,
        downgraded=downgraded,
        conflicts=conflicts,
        document=doc,
    )


def apply_selected_findings(
    document: Document,
    all_findings: list[Finding],
    selected_ids: list[str],
) -> SelectionApplyResult:
    """
    Apply user-selected findings (two-phase flow).

    Unlike apply_auto_findings(), this does NOT filter by auto_applicable.
    The user has explicitly chosen which findings to apply.

    Args:
        document: The CURRENT document to modify (re-read in Phase 2)
        all_findings: All findings from Phase 1
        selected_ids: finding_ids the user selected to apply

    Returns:
        SelectionApplyResult with applied findings and detailed skip reasons
    """
    # Deep copy document to avoid mutating original
    doc = deepcopy(document)

    # Build lookup for selected findings
    findings_by_id = {f.finding_id: f for f in all_findings}

    # Step 1: Gather selected findings, track not-found
    selected_findings: list[Finding] = []
    skipped: list[SkipReason] = []

    for fid in selected_ids:
        if fid not in findings_by_id:
            skipped.append(SkipReason(
                finding_id=fid,
                check_name="unknown",
                reason="not_found",
                detail=f"Finding ID '{fid}' not found in Phase 1 results",
            ))
            continue

        finding = findings_by_id[fid]

        # Check: has proposed_text?
        if finding.proposed_text is None:
            skipped.append(SkipReason(
                finding_id=fid,
                check_name=finding.check_name,
                reason="no_proposed_text",
                detail="This finding is advisory-only (no suggested fix)",
                original_text=finding.original_text,
            ))
            continue

        # Check: no-op edit?
        if finding.proposed_text == finding.original_text:
            skipped.append(SkipReason(
                finding_id=fid,
                check_name=finding.check_name,
                reason="no_proposed_text",
                detail="No change needed (proposed text matches original)",
                original_text=finding.original_text,
            ))
            continue

        selected_findings.append(finding)

    if not selected_findings:
        logger.info("No selected findings with valid proposed_text to apply")
        return SelectionApplyResult(document=doc, skipped=skipped)

    logger.info(f"Processing {len(selected_findings)} user-selected findings")

    # Step 2: Validate original_text matches CURRENT document
    validated: list[Finding] = []
    for finding in selected_findings:
        actual_text = _get_text_at_location(doc, finding)

        if actual_text is None:
            skipped.append(SkipReason(
                finding_id=finding.finding_id,
                check_name=finding.check_name,
                reason="text_mismatch",
                detail=f"Could not find text at offset {finding.location.start_offset}-{finding.location.end_offset}",
                original_text=finding.original_text,
                actual_text=None,
            ))
            continue

        if actual_text != finding.original_text:
            skipped.append(SkipReason(
                finding_id=finding.finding_id,
                check_name=finding.check_name,
                reason="text_mismatch",
                detail="Document text changed since Phase 1 - re-run check to get fresh findings",
                original_text=finding.original_text,
                actual_text=actual_text,
            ))
            continue

        validated.append(finding)

    if skipped:
        logger.warning(f"Skipped {len(skipped)} findings due to validation failures")

    # Step 3: Detect conflicts (overlapping spans)
    to_apply, conflict_findings, conflicts = _detect_conflicts(validated)

    downgraded: list[SkipReason] = []
    for winner, loser in conflicts:
        downgraded.append(SkipReason(
            finding_id=loser.finding_id,
            check_name=loser.check_name,
            reason="conflict",
            detail=f"Overlaps with '{winner.check_name}' which was applied first",
            original_text=loser.original_text,
            conflicting_with=winner.finding_id,
        ))

    if conflicts:
        logger.info(f"Detected {len(conflicts)} conflicts, downgraded {len(downgraded)} findings")

    # Step 4: Sort by position DESCENDING (apply last-to-first)
    sorted_findings = sorted(
        to_apply,
        key=lambda f: f.location.start_offset,
        reverse=True,
    )

    # Step 5: Apply each finding
    applied: list[Finding] = []
    for finding in sorted_findings:
        success = _apply_single_finding(doc, finding)
        if success:
            applied.append(finding)
        else:
            skipped.append(SkipReason(
                finding_id=finding.finding_id,
                check_name=finding.check_name,
                reason="text_mismatch",
                detail="Failed to apply edit (element not found)",
                original_text=finding.original_text,
            ))

    logger.info(
        f"Applied {len(applied)} findings, "
        f"skipped {len(skipped)}, downgraded {len(downgraded)}"
    )

    # Step 6: Recalculate element offsets
    _recalculate_offsets(doc)

    return SelectionApplyResult(
        applied=applied,
        skipped=skipped,
        downgraded=downgraded,
        document=doc,
    )


def _validate_findings(
    document: Document,
    findings: list[Finding],
) -> tuple[list[Finding], list[Finding]]:
    """
    Validate that each finding's original_text matches the document.

    Returns:
        (validated, skipped) tuple of findings lists
    """
    validated = []
    skipped = []

    for finding in findings:
        # Get the actual text at the finding's location
        actual_text = _get_text_at_location(document, finding)

        if actual_text is None:
            logger.warning(
                f"Could not find text at offset {finding.location.start_offset}-"
                f"{finding.location.end_offset} for finding {finding.check_name}"
            )
            skipped.append(finding)
            continue

        if actual_text != finding.original_text:
            logger.warning(
                f"Text mismatch for {finding.check_name}: "
                f"expected '{finding.original_text}', found '{actual_text}'"
            )
            skipped.append(finding)
            continue

        validated.append(finding)

    return validated, skipped


def _get_text_at_location(document: Document, finding: Finding) -> str | None:
    """Extract text from document at finding's location."""
    start = finding.location.start_offset
    end = finding.location.end_offset

    for element in document.elements:
        if element.start_offset <= start < element.end_offset:
            # Found the containing element
            if isinstance(element, (Paragraph, Heading)):
                # Calculate relative offset within element
                rel_start = start - element.start_offset
                rel_end = end - element.start_offset

                # Handle case where span crosses element boundary
                if rel_end > len(element.text):
                    rel_end = len(element.text)

                return element.text[rel_start:rel_end]

            elif isinstance(element, List):
                # Search within list items
                for item in element.items:
                    if item.start_offset <= start < item.end_offset:
                        rel_start = start - item.start_offset
                        rel_end = min(end - item.start_offset, len(item.text))
                        return item.text[rel_start:rel_end]

            elif isinstance(element, Table):
                # Search within table cells
                for row in element.rows:
                    for cell in row.cells:
                        if cell.start_offset <= start < cell.end_offset:
                            rel_start = start - cell.start_offset
                            rel_end = min(end - cell.start_offset, len(cell.text))
                            return cell.text[rel_start:rel_end]

    return None


def _detect_conflicts(
    findings: list[Finding],
) -> tuple[list[Finding], list[Finding], list[tuple[Finding, Finding]]]:
    """
    Detect overlapping spans among findings.

    Uses first-come-first-served: when two findings overlap,
    the one with the earlier start_offset wins and the other
    is downgraded to a proposal.

    Returns:
        (to_apply, downgraded, conflict_pairs)
    """
    if not findings:
        return [], [], []

    # Sort by start_offset ascending
    sorted_findings = sorted(findings, key=lambda f: f.location.start_offset)

    to_apply = []
    downgraded = []
    conflicts = []

    # Track occupied ranges
    occupied_ranges: list[tuple[int, int, Finding]] = []

    for finding in sorted_findings:
        # Defense in depth: skip no-op findings (original == proposed).
        # These can't block real edits even if they slip past upstream filter.
        if finding.proposed_text == finding.original_text:
            continue

        start = finding.location.start_offset
        end = finding.location.end_offset

        # Check overlap with any occupied range
        overlaps_with = None
        for occ_start, occ_end, occ_finding in occupied_ranges:
            # Overlap if ranges intersect
            if start < occ_end and end > occ_start:
                overlaps_with = occ_finding
                break

        if overlaps_with:
            downgraded.append(finding)
            conflicts.append((overlaps_with, finding))
            logger.debug(
                f"Conflict: {finding.check_name} at {start}-{end} "
                f"overlaps with {overlaps_with.check_name}"
            )
        else:
            to_apply.append(finding)
            occupied_ranges.append((start, end, finding))

    return to_apply, downgraded, conflicts


def _apply_single_finding(document: Document, finding: Finding) -> bool:
    """
    Apply a single finding to the document.

    Modifies the document in place.

    Returns:
        True if successfully applied, False otherwise
    """
    start = finding.location.start_offset
    end = finding.location.end_offset
    new_text = finding.proposed_text

    for idx, element in enumerate(document.elements):
        if element.start_offset <= start < element.end_offset:
            if isinstance(element, Paragraph):
                new_element = _apply_to_paragraph(element, start, end, new_text)
                document.elements[idx] = new_element
                return True

            elif isinstance(element, Heading):
                new_element = _apply_to_heading(element, start, end, new_text)
                document.elements[idx] = new_element
                return True

            elif isinstance(element, List):
                success = _apply_to_list(element, start, end, new_text)
                return success

            elif isinstance(element, Table):
                success = _apply_to_table(element, start, end, new_text)
                return success

    logger.warning(
        f"Could not find element containing offset {start} for {finding.check_name}"
    )
    return False


def _apply_to_paragraph(
    para: Paragraph,
    abs_start: int,
    abs_end: int,
    new_text: str,
) -> Paragraph:
    """Apply edit to a paragraph, preserving formatting."""
    # Calculate relative offsets within element
    rel_start = abs_start - para.start_offset
    rel_end = abs_end - para.start_offset

    # Build new text
    old_text = para.text
    new_full_text = old_text[:rel_start] + new_text + old_text[rel_end:]

    # Calculate length delta
    delta = len(new_text) - (rel_end - rel_start)

    # Build new runs with adjusted offsets and formatting preserved
    new_runs = _adjust_runs_for_edit(
        para.runs(),
        rel_start,
        rel_end,
        new_text,
        delta,
    )

    return Paragraph(
        text=new_full_text,
        start_offset=para.start_offset,
        end_offset=para.start_offset + len(new_full_text),
        _runs=new_runs,
    )


def _apply_to_heading(
    heading: Heading,
    abs_start: int,
    abs_end: int,
    new_text: str,
) -> Heading:
    """Apply edit to a heading, preserving formatting."""
    rel_start = abs_start - heading.start_offset
    rel_end = abs_end - heading.start_offset

    old_text = heading.text
    new_full_text = old_text[:rel_start] + new_text + old_text[rel_end:]

    delta = len(new_text) - (rel_end - rel_start)

    new_runs = _adjust_runs_for_edit(
        heading.runs(),
        rel_start,
        rel_end,
        new_text,
        delta,
    )

    return Heading(
        text=new_full_text,
        level=heading.level,
        start_offset=heading.start_offset,
        end_offset=heading.start_offset + len(new_full_text),
        _runs=new_runs,
    )


def _apply_to_list(
    lst: List,
    abs_start: int,
    abs_end: int,
    new_text: str,
) -> bool:
    """Apply edit to a list item."""
    for i, item in enumerate(lst.items):
        if item.start_offset <= abs_start < item.end_offset:
            rel_start = abs_start - item.start_offset
            rel_end = abs_end - item.start_offset

            old_text = item.text
            new_full_text = old_text[:rel_start] + new_text + old_text[rel_end:]

            delta = len(new_text) - (rel_end - rel_start)
            new_runs = _adjust_runs_for_edit(
                item.runs(),
                rel_start,
                rel_end,
                new_text,
                delta,
            )

            lst.items[i] = ListItem(
                text=new_full_text,
                start_offset=item.start_offset,
                end_offset=item.start_offset + len(new_full_text),
                indent_level=item.indent_level,
                _runs=new_runs,
            )
            return True

    return False


def _apply_to_table(
    table: Table,
    abs_start: int,
    abs_end: int,
    new_text: str,
) -> bool:
    """Apply edit to a table cell."""
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if cell.start_offset <= abs_start < cell.end_offset:
                rel_start = abs_start - cell.start_offset
                rel_end = abs_end - cell.start_offset

                old_text = cell.text
                new_full_text = old_text[:rel_start] + new_text + old_text[rel_end:]

                delta = len(new_text) - (rel_end - rel_start)
                new_runs = _adjust_runs_for_edit(
                    cell.runs(),
                    rel_start,
                    rel_end,
                    new_text,
                    delta,
                )

                # TableCell is mutable, update in place
                from core.document import TableCell
                row.cells[i] = TableCell(
                    text=new_full_text,
                    start_offset=cell.start_offset,
                    end_offset=cell.start_offset + len(new_full_text),
                    row_index=cell.row_index,
                    col_index=cell.col_index,
                    is_header=cell.is_header,
                    _runs=new_runs,
                )
                return True

    return False


def _adjust_runs_for_edit(
    runs: list[TextRun],
    rel_start: int,
    rel_end: int,
    new_text: str,
    delta: int,
) -> list[TextRun]:
    """
    Adjust TextRuns for an edit, preserving formatting.

    Strategy:
    1. Runs entirely before edit: keep unchanged
    2. Runs entirely after edit: shift by delta
    3. Runs overlapping edit: complex handling
       - Get formatting from most-overlapping run
       - Create new run with that formatting for replacement text
    """
    new_runs = []

    # Find formatting for the replacement text from the most-overlapping run
    replacement_formatting = _get_dominant_formatting(runs, rel_start, rel_end)

    for run in runs:
        if run.end_offset <= rel_start:
            # Run is entirely before edit - keep unchanged
            new_runs.append(run)

        elif run.start_offset >= rel_end:
            # Run is entirely after edit - shift by delta
            new_runs.append(TextRun(
                text=run.text,
                start_offset=run.start_offset + delta,
                end_offset=run.end_offset + delta,
                bold=run.bold,
                italic=run.italic,
                underline=run.underline,
                strikethrough=run.strikethrough,
                highlight_color=run.highlight_color,
                hyperlink=run.hyperlink,
            ))

        elif run.start_offset < rel_start and run.end_offset > rel_end:
            # Run completely spans the edit - split into three parts
            # Part 1: before edit
            before_text = run.text[:rel_start - run.start_offset]
            if before_text:
                new_runs.append(TextRun(
                    text=before_text,
                    start_offset=run.start_offset,
                    end_offset=rel_start,
                    bold=run.bold,
                    italic=run.italic,
                    underline=run.underline,
                    strikethrough=run.strikethrough,
                    highlight_color=run.highlight_color,
                    hyperlink=run.hyperlink,
                ))

            # Part 2: replacement text with inherited formatting
            if new_text:
                new_runs.append(TextRun(
                    text=new_text,
                    start_offset=rel_start,
                    end_offset=rel_start + len(new_text),
                    bold=run.bold,
                    italic=run.italic,
                    underline=run.underline,
                    strikethrough=run.strikethrough,
                    highlight_color=run.highlight_color,
                    hyperlink=run.hyperlink,
                ))

            # Part 3: after edit
            after_start_in_run = rel_end - run.start_offset
            after_text = run.text[after_start_in_run:]
            if after_text:
                new_runs.append(TextRun(
                    text=after_text,
                    start_offset=rel_start + len(new_text),
                    end_offset=rel_start + len(new_text) + len(after_text),
                    bold=run.bold,
                    italic=run.italic,
                    underline=run.underline,
                    strikethrough=run.strikethrough,
                    highlight_color=run.highlight_color,
                    hyperlink=run.hyperlink,
                ))

        elif run.start_offset < rel_start:
            # Run starts before edit but ends within - trim end
            before_text = run.text[:rel_start - run.start_offset]
            if before_text:
                new_runs.append(TextRun(
                    text=before_text,
                    start_offset=run.start_offset,
                    end_offset=rel_start,
                    bold=run.bold,
                    italic=run.italic,
                    underline=run.underline,
                    strikethrough=run.strikethrough,
                    highlight_color=run.highlight_color,
                    hyperlink=run.hyperlink,
                ))

        elif run.end_offset > rel_end:
            # Run starts within edit but ends after - trim start
            after_start_in_run = rel_end - run.start_offset
            after_text = run.text[after_start_in_run:]
            if after_text:
                new_runs.append(TextRun(
                    text=after_text,
                    start_offset=rel_start + len(new_text),
                    end_offset=rel_start + len(new_text) + len(after_text),
                    bold=run.bold,
                    italic=run.italic,
                    underline=run.underline,
                    strikethrough=run.strikethrough,
                    highlight_color=run.highlight_color,
                    hyperlink=run.hyperlink,
                ))

        elif run.start_offset >= rel_start and run.end_offset <= rel_end:
            # Run is entirely within edit range (including exact match)
            # Preserve formatting from first such run for the replacement text
            if new_text and run.start_offset == rel_start:
                # This run starts at edit start - use its formatting for replacement
                new_runs.append(TextRun(
                    text=new_text,
                    start_offset=rel_start,
                    end_offset=rel_start + len(new_text),
                    bold=run.bold,
                    italic=run.italic,
                    underline=run.underline,
                    strikethrough=run.strikethrough,
                    highlight_color=run.highlight_color,
                    hyperlink=run.hyperlink,
                ))
            # else: run is subset of edit range not at start - absorbed into replacement

        # else: should not reach here (all cases covered above)

    # If we haven't added the replacement text yet (no run spans the edit)
    # add it with the dominant formatting
    has_replacement = any(
        run.start_offset == rel_start and run.text == new_text
        for run in new_runs
    )

    if not has_replacement and new_text:
        # Find insertion point (after runs that are before rel_start)
        insert_idx = 0
        for i, run in enumerate(new_runs):
            if run.end_offset <= rel_start:
                insert_idx = i + 1
            else:
                break

        new_runs.insert(insert_idx, TextRun(
            text=new_text,
            start_offset=rel_start,
            end_offset=rel_start + len(new_text),
            bold=replacement_formatting.get('bold', False),
            italic=replacement_formatting.get('italic', False),
            underline=replacement_formatting.get('underline', False),
            strikethrough=replacement_formatting.get('strikethrough', False),
            highlight_color=replacement_formatting.get('highlight_color'),
            hyperlink=replacement_formatting.get('hyperlink'),
        ))

    return new_runs


def _get_dominant_formatting(
    runs: list[TextRun],
    start: int,
    end: int,
) -> dict:
    """Get formatting from the run that most overlaps with the edit span."""
    best_run = None
    best_overlap = 0

    for run in runs:
        # Calculate overlap
        overlap_start = max(run.start_offset, start)
        overlap_end = min(run.end_offset, end)
        overlap = max(0, overlap_end - overlap_start)

        if overlap > best_overlap:
            best_overlap = overlap
            best_run = run

    if best_run:
        return {
            'bold': best_run.bold,
            'italic': best_run.italic,
            'underline': best_run.underline,
            'strikethrough': best_run.strikethrough,
            'highlight_color': best_run.highlight_color,
            'hyperlink': best_run.hyperlink,
        }

    return {}


def _recalculate_offsets(document: Document) -> None:
    """
    Recalculate all element offsets after modifications.

    After applying edits, element lengths may have changed.
    Walk through elements and fix their start/end offsets.
    """
    current_offset = 0

    for element in document.elements:
        if isinstance(element, Paragraph):
            element_len = len(element.text)
            object.__setattr__(element, 'start_offset', current_offset)
            object.__setattr__(element, 'end_offset', current_offset + element_len)
            current_offset += element_len + 1  # +1 for newline between elements

        elif isinstance(element, Heading):
            element_len = len(element.text)
            object.__setattr__(element, 'start_offset', current_offset)
            object.__setattr__(element, 'end_offset', current_offset + element_len)
            current_offset += element_len + 1

        elif isinstance(element, List):
            list_start = current_offset
            for item in element.items:
                item_len = len(item.text)
                object.__setattr__(item, 'start_offset', current_offset)
                object.__setattr__(item, 'end_offset', current_offset + item_len)
                current_offset += item_len + 1
            object.__setattr__(element, 'start_offset', list_start)
            object.__setattr__(element, 'end_offset', current_offset - 1)

        elif isinstance(element, Table):
            table_start = current_offset
            for row in element.rows:
                for cell in row.cells:
                    cell_len = len(cell.text)
                    object.__setattr__(cell, 'start_offset', current_offset)
                    object.__setattr__(cell, 'end_offset', current_offset + cell_len)
                    current_offset += cell_len + 1
            object.__setattr__(element, 'start_offset', table_start)
            object.__setattr__(element, 'end_offset', current_offset - 1)

    # Update document total_length
    object.__setattr__(document, 'total_length', current_offset)
