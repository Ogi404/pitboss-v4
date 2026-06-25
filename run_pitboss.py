"""
Pitboss v4 - Unified Pipeline Entry Point

End-to-end pipeline supporting both local .docx and Google Docs:
  .docx article → corrected .docx + comments + summary
  Google Doc → corrected Google Doc + comments posted

Usage:
    # Local .docx
    python run_pitboss.py --article "article.docx" --brand "koifortune"

    # Google Doc
    python run_pitboss.py --gdoc "1abc123..." --brand "koifortune"
    python run_pitboss.py --gdoc "https://docs.google.com/document/d/1abc123/edit"
"""

from __future__ import annotations
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Union

# Import checks to ensure registration
import deterministic  # noqa: F401

from core.document import Document
from core.orchestrator import run_all_checks, OrchestratorResult
from core.standards_engine import StandardsEngine, Standards
from ingest.docx_reader import read_docx
from ingest.gdoc_reader import read_gdoc
from ingest.gdoc_auth import extract_doc_id
from ingest.brief_agent import BriefAgent
from ingest.brief_model import BriefState, BriefModel
from output.apply import apply_auto_findings, ApplyResult
from output.docx_writer import write_docx
from output.gdoc_writer import write_gdoc
from output.gdoc_comments import post_comments, post_comments_batch
from output.comments import draft_comments, comments_to_markdown
from output.summary import generate_summary, summary_to_markdown
from output.formatting_resolver import resolve_blank_rows, get_blank_rows_reason


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# SHARED PIPELINE CORE
# =============================================================================

def _run_pipeline_core(
    document: Document,
    standards: Standards,
    brief: Optional[BriefModel] = None,
) -> tuple[OrchestratorResult, ApplyResult]:
    """
    Run the core pipeline: checks → apply auto-fixes.

    This is the shared logic for both .docx and Google Docs paths.

    Args:
        document: The document to check
        standards: Brand standards to apply
        brief: Optional brief model

    Returns:
        Tuple of (orchestrator_result, apply_result)
    """
    # Run orchestrator (all checks)
    logger.info("Running checks...")
    orch_result = run_all_checks(document, standards, voice_model=None, brief=brief)
    logger.info(
        f"Checks complete: {len(orch_result.findings)} findings "
        f"({len(orch_result.auto_applicable)} auto, {len(orch_result.proposals)} proposals)"
    )

    if orch_result.errors:
        logger.warning(f"Check errors: {list(orch_result.errors.keys())}")

    # Apply auto-fixes
    logger.info(f"Applying {len(orch_result.auto_applicable)} auto-fixes...")
    apply_result = apply_auto_findings(document, orch_result.auto_applicable)
    logger.info(
        f"Applied: {apply_result.applied_count}, "
        f"skipped: {apply_result.skipped_count}, "
        f"downgraded: {apply_result.downgraded_count}"
    )

    return orch_result, apply_result


# =============================================================================
# LOCAL .DOCX PATH
# =============================================================================

def run_docx_pipeline(
    article_path: Path,
    brief_path: Optional[Path] = None,
    brand_id: Optional[str] = None,
    output_dir: Optional[Path] = None,
    task_selection: Optional[str] = None,
) -> tuple[Path, Path, Path]:
    """
    Run the full Pitboss pipeline on a local .docx file.

    Args:
        article_path: Path to the .docx article
        brief_path: Path to the brief file (optional)
        brand_id: Brand identifier for standards (optional)
        output_dir: Output directory (optional, auto-generated if not provided)
        task_selection: Task to select if brief has multiple tasks (optional)

    Returns:
        Tuple of (corrected_docx_path, comments_path, summary_path)
    """
    # 1. Setup output directory
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("output_runs") / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Output directory: {output_dir}")

    # 2. Read article → Document
    logger.info(f"Reading article: {article_path}")
    document = read_docx(article_path)
    logger.info(f"Document loaded: {len(document.elements)} elements, ~{len(document.full_text().split())} words")

    # 3. Parse brief (if provided)
    brief = _parse_brief(brief_path, task_selection)

    # 4. Load standards
    logger.info(f"Loading standards for brand: {brand_id or '_defaults'}")
    standards, brand_warning = _load_standards(brand_id)

    # 5. Run core pipeline
    orch_result, apply_result = _run_pipeline_core(document, standards, brief)

    # 6. Resolve blank_rows formatting
    brand_config = {"brand_name": brand_id} if brand_id else None
    blank_rows, reason = get_blank_rows_reason(
        brief=brief,
        brand_config=brand_config,
        filename=article_path.name,
    )
    logger.info(f"blank_rows resolved to: {blank_rows} ({reason})")

    # 7. Write corrected docx
    corrected_filename = f"corrected_{article_path.stem}.docx"
    corrected_path = output_dir / corrected_filename
    logger.info(f"Writing corrected document: {corrected_path}")
    write_docx(apply_result.document, corrected_path, blank_rows=blank_rows)

    # 8. Draft comments (from proposals + downgraded)
    all_proposals = list(orch_result.proposals) + list(apply_result.downgraded)
    comments = draft_comments(all_proposals, document)
    comments_path = output_dir / "comments.md"
    comments_path.write_text(comments_to_markdown(comments), encoding='utf-8')
    logger.info(f"Wrote {len(comments)} comments to: {comments_path}")

    # 9. Write summary
    summary = generate_summary(
        orch_result,
        apply_result,
        comments,
        document,
        brief,
        str(article_path),
        str(brief_path) if brief_path else None,
        brand_warning=brand_warning,
    )
    summary_path = output_dir / "summary.md"
    summary_path.write_text(summary_to_markdown(summary), encoding='utf-8')
    logger.info(f"Wrote summary to: {summary_path}")

    # Print summary to console
    _print_docx_summary(article_path, summary, corrected_path, comments_path, summary_path, brand_warning)

    return corrected_path, comments_path, summary_path


# =============================================================================
# GOOGLE DOCS PATH
# =============================================================================

def run_gdoc_pipeline(
    gdoc_id_or_url: str,
    brief_path: Optional[Path] = None,
    brand_id: Optional[str] = None,
    task_selection: Optional[str] = None,
    skip_comments: bool = False,
) -> tuple[str, int, int]:
    """
    Run the full Pitboss pipeline on a Google Doc.

    Args:
        gdoc_id_or_url: Google Doc ID or URL
        brief_path: Path to the brief file (optional)
        brand_id: Brand identifier for standards (optional)
        task_selection: Task to select if brief has multiple tasks (optional)
        skip_comments: If True, skip posting comments to the doc

    Returns:
        Tuple of (corrected_doc_url, auto_fix_count, comment_count)
    """
    # Extract doc ID
    doc_id = extract_doc_id(gdoc_id_or_url)
    logger.info(f"Processing Google Doc: {doc_id}")

    # 1. Read article from Google Doc
    logger.info("Reading document from Google Docs...")
    document = read_gdoc(doc_id)
    logger.info(
        f"Document loaded: {len(document.elements)} elements, "
        f"~{len(document.full_text().split())} words"
    )

    # 2. Parse brief (if provided)
    brief = _parse_brief(brief_path, task_selection)

    # 3. Load standards
    logger.info(f"Loading standards for brand: {brand_id or '_defaults'}")
    standards, brand_warning = _load_standards(brand_id)

    # 4. Run core pipeline
    orch_result, apply_result = _run_pipeline_core(document, standards, brief)

    # 5. Resolve blank_rows formatting
    # For Google Docs, use document title as filename proxy
    brand_config = {"brand_name": brand_id} if brand_id else None
    blank_rows, reason = get_blank_rows_reason(
        brief=brief,
        brand_config=brand_config,
        filename=document.title,
    )
    logger.info(f"blank_rows resolved to: {blank_rows} ({reason})")

    # 6. Write corrected Google Doc
    logger.info("Creating corrected Google Doc...")
    corrected_url = write_gdoc(
        apply_result.document,
        title=f"{document.title} - Corrected",
        blank_rows=blank_rows if blank_rows != "proposal" else None,
    )
    logger.info(f"Corrected document: {corrected_url}")

    # 7. Post comments for proposals
    comment_count = 0
    if not skip_comments:
        all_proposals = list(orch_result.proposals) + list(apply_result.downgraded)
        if all_proposals:
            logger.info(f"Drafting {len(all_proposals)} comments...")
            drafted = draft_comments(all_proposals, document)

            # Post to the CORRECTED doc
            corrected_doc_id = extract_doc_id(corrected_url)
            logger.info(f"Posting comments to corrected doc...")

            # Use batch for efficiency
            if len(drafted) > 10:
                comment_count = post_comments_batch(corrected_doc_id, drafted)
            else:
                comment_ids = post_comments(corrected_doc_id, drafted)
                comment_count = len(comment_ids)

            logger.info(f"Posted {comment_count} comments")
    else:
        logger.info("Skipping comment posting (--skip-comments)")

    # Print summary
    _print_gdoc_summary(doc_id, document, orch_result, apply_result, comment_count, corrected_url, brand_warning)

    return corrected_url, apply_result.applied_count, comment_count


# =============================================================================
# SHARED HELPERS
# =============================================================================

def _parse_brief(
    brief_path: Optional[Path],
    task_selection: Optional[str] = None,
) -> Optional[BriefModel]:
    """Parse brief file if provided."""
    if not brief_path:
        return None

    if not brief_path.exists():
        logger.warning(f"Brief file not found: {brief_path}")
        return None

    logger.info(f"Parsing brief: {brief_path}")
    agent = BriefAgent()
    result = agent.parse(brief_path)

    if result.state == BriefState.NEEDS_CLARIFICATION:
        logger.warning("Brief needs clarification:")
        for clar in result.clarifications:
            logger.warning(f"  - {clar.question}")
        return result.brief

    elif result.state == BriefState.NEEDS_TASK_SELECTION:
        if task_selection:
            logger.info(f"Selecting task: {task_selection}")
            result = agent.parse_with_task(brief_path, task_selection)
            return result.brief
        else:
            logger.warning(f"Brief has multiple tasks: {result.task_options}")
            logger.warning("Using first task by default...")
            if result.task_options:
                result = agent.parse_with_task(brief_path, result.task_options[0])
                return result.brief
        return None

    else:
        brief = result.brief
        if brief:
            logger.info(f"Brief parsed: task={brief.task_name}, {len(brief.keywords.all_keywords)} keywords")
        return brief


def _load_standards(brand_id: Optional[str]) -> tuple[Standards, Optional[str]]:
    """
    Load standards for a brand (or defaults).

    Returns:
        Tuple of (Standards, warning_message or None).
        Warning is set when brand was requested but config doesn't exist.
    """
    brands_dir = Path("brands")
    if not brands_dir.exists():
        logger.warning("brands/ directory not found, using default standards")
        return Standards(), "brands/ directory not found - using defaults"

    engine = StandardsEngine(brands_dir=brands_dir)

    if brand_id:
        if engine.has_brand(brand_id):
            # Brand config exists - load it
            return engine.load(brand_id), None
        else:
            # Brand requested but not configured - use defaults, warn user
            warning = f"Brand '{brand_id}' not configured - using defaults"
            logger.warning(warning)
            return engine.load_defaults(), warning
    else:
        # No brand specified - intentional use of defaults
        return engine.load_defaults(), None


def _print_docx_summary(
    article_path: Path,
    summary,
    corrected_path: Path,
    comments_path: Path,
    summary_path: Path,
    brand_warning: Optional[str] = None,
) -> None:
    """Print summary for .docx pipeline."""
    print("\n" + "=" * 60)
    print("PITBOSS RUN COMPLETE")
    print("=" * 60)
    if brand_warning:
        print(f"WARNING: {brand_warning}")
        print()
    print(f"Article: {article_path.name}")
    print(f"Word count: ~{summary.word_count:,}")
    print(f"\nAuto-fixes applied: {summary.total_auto_applied}")
    print(f"Proposals for review: {summary.total_proposals}")
    print(f"Comments drafted: {summary.comments_drafted}")
    print(f"\nOutputs:")
    print(f"  - Corrected: {corrected_path}")
    print(f"  - Comments:  {comments_path}")
    print(f"  - Summary:   {summary_path}")
    print("=" * 60 + "\n")


def _print_gdoc_summary(
    doc_id: str,
    document: Document,
    orch_result: OrchestratorResult,
    apply_result: ApplyResult,
    comment_count: int,
    corrected_url: str,
    brand_warning: Optional[str] = None,
) -> None:
    """Print summary for Google Docs pipeline."""
    print("\n" + "=" * 70)
    print("GOOGLE DOCS PIPELINE COMPLETE")
    print("=" * 70)
    if brand_warning:
        print(f"WARNING: {brand_warning}")
        print()
    print(f"Source doc:       {doc_id}")
    print(f"Title:            {document.title}")
    print(f"Word count:       ~{len(document.full_text().split()):,}")
    print()
    print(f"Total findings:   {len(orch_result.findings)}")
    print(f"Auto-fixes:       {apply_result.applied_count}")
    print(f"Proposals:        {len(orch_result.proposals)}")
    print(f"Comments posted:  {comment_count}")
    print()
    print(f"Corrected doc:    {corrected_url}")
    print()
    print("Next steps:")
    print("  1. Open the corrected doc in Google Docs")
    print("  2. Use Tools > Compare Documents to see redlines")
    print("  3. Review comments in the sidebar")
    print("=" * 70 + "\n")


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Pitboss v4 - Document checking pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local .docx file
  python run_pitboss.py --article article.docx
  python run_pitboss.py --article article.docx --brief brief.xlsx
  python run_pitboss.py --article article.docx --brand koifortune

  # Google Doc
  python run_pitboss.py --gdoc "1abc123..."
  python run_pitboss.py --gdoc "https://docs.google.com/document/d/1abc123/edit" --brand koifortune
  python run_pitboss.py --gdoc "1abc123..." --skip-comments
        """
    )

    # Input source (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--article", "-a",
        type=Path,
        help="Path to a local .docx article"
    )
    input_group.add_argument(
        "--gdoc", "-g",
        type=str,
        help="Google Doc ID or URL"
    )

    # Common options
    parser.add_argument(
        "--brief", "-b",
        type=Path,
        default=None,
        help="Path to the brief file (.xlsx, .docx, etc.)"
    )

    parser.add_argument(
        "--brand",
        type=str,
        default=None,
        help="Brand identifier for standards (e.g., 'koifortune')"
    )

    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Task to select if brief has multiple tasks"
    )

    # .docx specific
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Output directory for .docx (default: output_runs/<timestamp>)"
    )

    # Google Docs specific
    parser.add_argument(
        "--skip-comments",
        action="store_true",
        help="Skip posting comments to Google Doc"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run appropriate pipeline
    try:
        if args.article:
            # Validate local file exists
            if not args.article.exists():
                print(f"Error: Article file not found: {args.article}")
                sys.exit(1)

            run_docx_pipeline(
                article_path=args.article,
                brief_path=args.brief,
                brand_id=args.brand,
                output_dir=args.output_dir,
                task_selection=args.task,
            )

        elif args.gdoc:
            run_gdoc_pipeline(
                gdoc_id_or_url=args.gdoc,
                brief_path=args.brief,
                brand_id=args.brand,
                task_selection=args.task,
                skip_comments=args.skip_comments,
            )

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
