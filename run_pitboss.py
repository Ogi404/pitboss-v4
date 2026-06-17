"""
Pitboss v4 - Pipeline Entry Point

End-to-end pipeline:
  .docx article + brief → run all checks → corrected .docx + comments + summary

Usage:
    python run_pitboss.py --article "article.docx" --brief "brief.xlsx"
    python run_pitboss.py --article "article.docx" --brand "koifortune"
"""

from __future__ import annotations
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

# Import checks to ensure registration
import deterministic  # noqa: F401

from core.document import Document
from core.orchestrator import run_all_checks, OrchestratorResult
from core.standards_engine import StandardsEngine, Standards
from ingest.docx_reader import read_docx
from ingest.brief_agent import BriefAgent
from ingest.brief_model import BriefState
from output.apply import apply_auto_findings, ApplyResult
from output.docx_writer import write_docx
from output.comments import draft_comments, comments_to_markdown
from output.summary import generate_summary, summary_to_markdown


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_pitboss(
    article_path: Path,
    brief_path: Optional[Path] = None,
    brand_id: Optional[str] = None,
    output_dir: Optional[Path] = None,
    task_selection: Optional[str] = None,
) -> tuple[Path, Path, Path]:
    """
    Run the full Pitboss pipeline.

    Args:
        article_path: Path to the .docx article
        brief_path: Path to the brief file (optional)
        brand_id: Brand identifier for standards (optional, defaults to "_defaults")
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
    brief = None
    if brief_path:
        logger.info(f"Parsing brief: {brief_path}")
        agent = BriefAgent()
        result = agent.parse(brief_path)

        if result.state == BriefState.NEEDS_CLARIFICATION:
            logger.warning("Brief needs clarification:")
            for clar in result.clarifications:
                logger.warning(f"  - {clar.question}")
            # Continue with partial brief data
            brief = result.brief

        elif result.state == BriefState.NEEDS_TASK_SELECTION:
            if task_selection:
                logger.info(f"Selecting task: {task_selection}")
                result = agent.parse_with_task(brief_path, task_selection)
                brief = result.brief
            else:
                logger.warning(f"Brief has multiple tasks: {result.task_options}")
                logger.warning("Using first task by default...")
                if result.task_options:
                    result = agent.parse_with_task(brief_path, result.task_options[0])
                    brief = result.brief

        else:
            brief = result.brief

        if brief:
            logger.info(f"Brief parsed: task={brief.task}, {len(brief.keywords.all_keywords)} keywords")

    # 4. Load standards
    logger.info(f"Loading standards for brand: {brand_id or '_defaults'}")
    standards = _load_standards(brand_id)

    # 5. Run orchestrator (all checks)
    logger.info("Running checks...")
    orch_result = run_all_checks(document, standards, voice_model=None, brief=brief)
    logger.info(
        f"Checks complete: {len(orch_result.findings)} findings "
        f"({len(orch_result.auto_applicable)} auto, {len(orch_result.proposals)} proposals)"
    )

    if orch_result.errors:
        logger.warning(f"Check errors: {list(orch_result.errors.keys())}")

    # 6. Apply auto-fixes
    logger.info(f"Applying {len(orch_result.auto_applicable)} auto-fixes...")
    apply_result = apply_auto_findings(document, orch_result.auto_applicable)
    logger.info(
        f"Applied: {apply_result.applied_count}, "
        f"skipped: {apply_result.skipped_count}, "
        f"downgraded: {apply_result.downgraded_count}"
    )

    # 7. Write corrected docx
    corrected_filename = f"corrected_{article_path.stem}.docx"
    corrected_path = output_dir / corrected_filename
    logger.info(f"Writing corrected document: {corrected_path}")
    write_docx(apply_result.document, corrected_path)

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
    )
    summary_path = output_dir / "summary.md"
    summary_path.write_text(summary_to_markdown(summary), encoding='utf-8')
    logger.info(f"Wrote summary to: {summary_path}")

    # Print summary to console
    print("\n" + "=" * 60)
    print("PITBOSS RUN COMPLETE")
    print("=" * 60)
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

    return corrected_path, comments_path, summary_path


def _load_standards(brand_id: Optional[str]) -> Standards:
    """Load standards for a brand (or defaults)."""
    # Check if brands directory exists
    brands_dir = Path("brands")
    if not brands_dir.exists():
        logger.warning("brands/ directory not found, using default standards")
        return Standards()

    engine = StandardsEngine(brands_dir=brands_dir)

    if brand_id:
        try:
            return engine.load(brand_id)
        except FileNotFoundError:
            logger.warning(f"Brand '{brand_id}' not found, using defaults")
            return engine.load_defaults()
    else:
        return engine.load_defaults()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Pitboss v4 - Document checking pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pitboss.py --article article.docx
  python run_pitboss.py --article article.docx --brief brief.xlsx
  python run_pitboss.py --article article.docx --brand koifortune --output-dir ./output
        """
    )

    parser.add_argument(
        "--article", "-a",
        type=Path,
        required=True,
        help="Path to the .docx article to check"
    )

    parser.add_argument(
        "--brief", "-b",
        type=Path,
        default=None,
        help="Path to the brief file (.xlsx, .pdf, etc.)"
    )

    parser.add_argument(
        "--brand",
        type=str,
        default=None,
        help="Brand identifier for standards (e.g., 'koifortune')"
    )

    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Output directory (default: output_runs/<timestamp>)"
    )

    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Task to select if brief has multiple tasks"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate inputs
    if not args.article.exists():
        print(f"Error: Article file not found: {args.article}")
        sys.exit(1)

    if args.brief and not args.brief.exists():
        print(f"Error: Brief file not found: {args.brief}")
        sys.exit(1)

    # Run pipeline
    try:
        corrected, comments, summary = run_pitboss(
            article_path=args.article,
            brief_path=args.brief,
            brand_id=args.brand,
            output_dir=args.output_dir,
            task_selection=args.task,
        )
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
