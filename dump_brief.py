"""
Diagnostic: Dump what the brief parser actually extracted from a brief file.

Usage:
    python dump_brief.py path/to/your/brief.xlsx

Outputs:
    - Extracted keywords (main, support, lsi) with quantities
    - Extracted sections/headings
    - Raw data from parser
"""

import sys
import json
from pathlib import Path

from ingest.brief_agent import BriefAgent
from ingest.brief_model import BriefState


def dump_brief(brief_path: str) -> None:
    """Parse brief and dump extracted data."""
    path = Path(brief_path)
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"BRIEF PARSER DIAGNOSTIC")
    print(f"{'='*70}")
    print(f"Input: {path}")
    print()

    agent = BriefAgent()
    result = agent.parse(path)

    print(f"Parse state: {result.state.value}")
    print()

    if result.state == BriefState.NEEDS_TASK_SELECTION:
        print("MULTI-TASK BRIEF - Available tasks:")
        for t in result.task_options:
            print(f"  - {t}")
        print("\nRe-run with: agent.parse_with_task(path, 'task_name')")
        return

    if result.state == BriefState.NEEDS_CLARIFICATION:
        print("NEEDS CLARIFICATION:")
        for c in result.clarifications:
            print(f"  - {c.field}: {c.question}")
            print(f"    Detected: {c.detected_value} (confidence: {c.confidence})")
        print()

    brief = result.brief
    if not brief:
        print("ERROR: No brief model created")
        return

    # Keywords
    print(f"{'='*70}")
    print("EXTRACTED KEYWORDS")
    print(f"{'='*70}")
    print(f"Keywords confidence: {brief.keywords_confidence}")
    print()

    print(f"MAIN KEYWORDS ({len(brief.keywords.main)} found):")
    for kw in brief.keywords.main:
        qty_str = ""
        if kw.min_quantity is not None and kw.max_quantity is not None:
            if kw.min_quantity == kw.max_quantity:
                qty_str = f" (exactly {kw.min_quantity}x)"
            else:
                qty_str = f" ({kw.min_quantity}-{kw.max_quantity}x)"
        elif kw.min_quantity is not None:
            qty_str = f" (min {kw.min_quantity}x)"
        elif kw.max_quantity is not None:
            qty_str = f" (max {kw.max_quantity}x)"
        else:
            qty_str = " (any)"
        print(f"  - '{kw.keyword}'{qty_str}")

    print()
    print(f"SUPPORT KEYWORDS ({len(brief.keywords.support)} found):")
    for kw in brief.keywords.support:
        print(f"  - '{kw.keyword}'")

    print()
    print(f"LSI KEYWORDS ({len(brief.keywords.lsi)} found):")
    for kw in brief.keywords.lsi:
        print(f"  - '{kw.keyword}'")

    # Sections
    print()
    print(f"{'='*70}")
    print("EXTRACTED SECTIONS")
    print(f"{'='*70}")
    print(f"Sections confidence: {brief.sections_confidence}")
    print()
    print(f"REQUIRED SECTIONS ({len(brief.sections)} found):")
    for sec in brief.sections:
        wc_str = f" ({sec.word_count} words)" if sec.word_count else ""
        print(f"  - '{sec.heading}'{wc_str}")

    # Meta
    print()
    print(f"{'='*70}")
    print("METADATA")
    print(f"{'='*70}")
    print(f"Task name: {brief.task_name}")
    print(f"Article type: {brief.article_type.value} (conf: {brief.article_type_confidence})")
    print(f"Brand name: {brief.brand_name or '(not found)'}")
    print(f"Locale: {brief.locale or '(not found)'}")
    print(f"Market: {brief.market or '(not found)'}")
    print(f"Target word count: {brief.target_word_count or '(not found)'}")
    print(f"Source format: {brief.source_format}")

    # Raw data
    print()
    print(f"{'='*70}")
    print("RAW DATA (for debugging)")
    print(f"{'='*70}")
    if brief.raw_data:
        print(json.dumps(brief.raw_data, indent=2, default=str))
    else:
        print("(no raw data captured)")

    print()
    print(f"{'='*70}")
    print("END DIAGNOSTIC")
    print(f"{'='*70}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python dump_brief.py path/to/brief.xlsx")
        sys.exit(1)
    dump_brief(sys.argv[1])
