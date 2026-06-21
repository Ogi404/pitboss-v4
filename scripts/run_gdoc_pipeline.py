"""
Pitboss v4 - Google Docs Pipeline Test Script

End-to-end pipeline for Google Docs:
  Google Doc article + brief → run all checks → corrected Google Doc + comments

Usage:
    python scripts/run_gdoc_pipeline.py \
        --gdoc "1O4QTUAtkN9LvGFT7iDregCA-F5R5LKQQZTQ8qVX1xDQ" \
        --brief "corpora/Koifortune/voice_model.json"
"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import checks to ensure registration
import deterministic  # noqa: F401

from core.document import Document
from core.orchestrator import run_all_checks, OrchestratorResult
from core.standards_engine import StandardsEngine, Standards
from ingest.gdoc_reader import read_gdoc
from ingest.gdoc_auth import extract_doc_id
from output.apply import apply_auto_findings, ApplyResult
from output.gdoc_writer import write_gdoc
from output.gdoc_comments import post_comments, post_comments_batch
from output.comments import draft_comments, DraftedComment


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_gdoc_pipeline(
    gdoc_id_or_url: str,
    brief_path: Optional[Path] = None,
    brand_id: Optional[str] = None,
    skip_comments: bool = False,
) -> tuple[str, int, int]:
    """
    Run the full Pitboss pipeline on a Google Doc.

    Args:
        gdoc_id_or_url: Google Doc ID or URL
        brief_path: Path to the brief/voice_model file (optional)
        brand_id: Brand identifier for standards (optional)
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

    # 2. Load brief (optional, for voice model)
    brief = None
    if brief_path and brief_path.exists():
        logger.info(f"Loading brief/voice model: {brief_path}")
        # For now, we don't parse complex briefs in this test script
        # The orchestrator handles brief=None gracefully

    # 3. Load standards
    logger.info(f"Loading standards for brand: {brand_id or '_defaults'}")
    standards = _load_standards(brand_id)

    # 4. Run orchestrator (all checks)
    logger.info("Running checks...")
    orch_result = run_all_checks(document, standards, voice_model=None, brief=brief)
    logger.info(
        f"Checks complete: {len(orch_result.findings)} findings "
        f"({len(orch_result.auto_applicable)} auto, {len(orch_result.proposals)} proposals)"
    )

    if orch_result.errors:
        logger.warning(f"Check errors: {list(orch_result.errors.keys())}")

    # 5. Apply auto-fixes
    logger.info(f"Applying {len(orch_result.auto_applicable)} auto-fixes...")
    apply_result = apply_auto_findings(document, orch_result.auto_applicable)
    logger.info(
        f"Applied: {apply_result.applied_count}, "
        f"skipped: {apply_result.skipped_count}, "
        f"downgraded: {apply_result.downgraded_count}"
    )

    # 6. Write corrected Google Doc
    logger.info("Creating corrected Google Doc...")
    corrected_url = write_gdoc(
        apply_result.document,
        title=f"{document.title} - Corrected"
    )
    logger.info(f"Corrected document: {corrected_url}")

    # 7. Post comments for proposals
    comment_count = 0
    if not skip_comments:
        # Draft comments from proposals + downgraded findings
        all_proposals = list(orch_result.proposals) + list(apply_result.downgraded)
        if all_proposals:
            logger.info(f"Drafting {len(all_proposals)} comments...")
            drafted = draft_comments(all_proposals, document)

            # Post to the CORRECTED doc (so comments appear alongside fixes)
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
    print("\n" + "=" * 70)
    print("GOOGLE DOCS PIPELINE COMPLETE")
    print("=" * 70)
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

    return corrected_url, apply_result.applied_count, comment_count


def _load_standards(brand_id: Optional[str]) -> Standards:
    """Load standards for a brand (or defaults)."""
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
        description="Pitboss v4 - Google Docs pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_gdoc_pipeline.py --gdoc "1abc123..."
  python scripts/run_gdoc_pipeline.py --gdoc "1abc123..." --skip-comments
  python scripts/run_gdoc_pipeline.py --gdoc "https://docs.google.com/document/d/1abc123/edit"
        """
    )

    parser.add_argument(
        "--gdoc", "-g",
        type=str,
        required=True,
        help="Google Doc ID or URL"
    )

    parser.add_argument(
        "--brief", "-b",
        type=Path,
        default=None,
        help="Path to brief/voice_model file (optional)"
    )

    parser.add_argument(
        "--brand",
        type=str,
        default=None,
        help="Brand identifier for standards (e.g., 'koifortune')"
    )

    parser.add_argument(
        "--skip-comments",
        action="store_true",
        help="Skip posting comments to the document"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run pipeline
    try:
        corrected_url, auto_count, comment_count = run_gdoc_pipeline(
            gdoc_id_or_url=args.gdoc,
            brief_path=args.brief,
            brand_id=args.brand,
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
