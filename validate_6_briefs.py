"""
Brief Agent Validation - 6 Real Briefs
Full raw output for each brief.
"""

import sys
import io
from pathlib import Path

# Force UTF-8 output for Unicode characters
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))

from ingest.brief_agent import BriefAgent
from ingest.brief_model import BriefState


BRIEFS_DIR = Path(r"C:\Users\User\Downloads\Lib_pitboss_v4\Briefs")

BRIEF_FILES = [
    "Content Task_ Koifortune AU.xlsx",
    "Content Task_ 22Bet.xlsx",
    "App Page Task Brief.docx",
    "Vave bonuses.docx",
    "Big Bass Splash_Slots_NG.docx",
    "Boxing_LINE_NG.docx",
    "Content task Mar'26 22bet.com.gh - 10 pages.docx",  # Multi-task test
]


def print_brief_result(brief_name: str, brief_path: Path, result):
    """Print full raw output for a brief parsing result."""
    print("=" * 80)
    print(f"BRIEF: {brief_name}")
    print(f"PATH: {brief_path}")
    print("=" * 80)
    print(f"\nSTATE: {result.state.value}")

    if result.state == BriefState.NEEDS_TASK_SELECTION:
        print(f"\nTASK OPTIONS ({len(result.task_options)} tasks detected):")
        for i, task in enumerate(result.task_options, 1):
            print(f"  {i}. {task}")
        print("\n[Multi-task brief - requires task selection before full extraction]")
        print("\n" + "=" * 80 + "\n\n")
        return

    if result.brief:
        brief = result.brief

        # Keywords
        print(f"\n{'='*40}")
        print("KEYWORDS:")
        print(f"{'='*40}")
        print(f"  Overall Keywords Confidence: {brief.keywords_confidence:.2f}")
        print(f"  Threshold Met (>= 0.7): {brief.keywords_confidence >= 0.7}")

        print(f"\n  MAIN KEYWORDS ({len(brief.keywords.main)}):")
        if brief.keywords.main:
            for kw in brief.keywords.main:
                print(f"    - '{kw.keyword}'")
                print(f"        group: {kw.group}, min: {kw.min_quantity}, max: {kw.max_quantity}, conf: {kw.confidence:.2f}")
        else:
            print("    (none)")

        print(f"\n  SUPPORT KEYWORDS ({len(brief.keywords.support)}):")
        if brief.keywords.support:
            for kw in brief.keywords.support:
                print(f"    - '{kw.keyword}'")
                print(f"        group: {kw.group}, min: {kw.min_quantity}, max: {kw.max_quantity}, conf: {kw.confidence:.2f}")
        else:
            print("    (none)")

        print(f"\n  LSI KEYWORDS ({len(brief.keywords.lsi)}):")
        if brief.keywords.lsi:
            for kw in brief.keywords.lsi:
                print(f"    - '{kw.keyword}'")
                print(f"        group: {kw.group}, min: {kw.min_quantity}, max: {kw.max_quantity}, conf: {kw.confidence:.2f}")
        else:
            print("    (none)")

        # Article Type
        print(f"\n{'='*40}")
        print("ARTICLE TYPE:")
        print(f"{'='*40}")
        print(f"  Task Name: '{brief.task_name}'")
        print(f"  Detected Type: {brief.article_type.value}")
        print(f"  Type Confidence: {brief.article_type_confidence:.2f}")

        # Sections (abbreviated)
        print(f"\n{'='*40}")
        print(f"SECTIONS ({len(brief.sections)} total):")
        print(f"{'='*40}")
        print(f"  Sections Confidence: {brief.sections_confidence:.2f}")
        for sec in brief.sections[:5]:
            wc = f"{sec.word_count} words" if sec.word_count else "no word count"
            print(f"    - '{sec.heading[:50]}{'...' if len(sec.heading) > 50 else ''}' | {wc}")
        if len(brief.sections) > 5:
            print(f"    ... and {len(brief.sections) - 5} more sections")

        # Links
        print(f"\n{'='*40}")
        print(f"LINKS ({len(brief.links)} total):")
        print(f"{'='*40}")
        print(f"  Links Confidence: {brief.links_confidence:.2f}")
        for link in brief.links[:3]:
            print(f"    - Anchor: '{link.anchor}' | URL: '{link.url}' | Type: {link.link_type}")
        if len(brief.links) > 3:
            print(f"    ... and {len(brief.links) - 3} more links")

        # Meta
        print(f"\n{'='*40}")
        print("META:")
        print(f"{'='*40}")
        print(f"  Brand: '{brief.brand_name}'")
        print(f"  Locale: {brief.locale}")
        print(f"  Market: {brief.market}")
        print(f"  Locale Confidence: {brief.locale_confidence:.2f}")
        print(f"  Target Word Count: {brief.target_word_count}")
        print(f"  Word Count Confidence: {brief.word_count_confidence:.2f}")

        # Overall confidence
        print(f"\n{'='*40}")
        print("OVERALL CONFIDENCE:")
        print(f"{'='*40}")
        print(f"  Min Confidence: {brief.min_confidence:.2f}")
        print(f"  High Confidence (>= 0.7): {brief.is_high_confidence}")

    # Clarifications
    if result.clarifications:
        print(f"\n{'='*40}")
        print(f"CLARIFICATIONS REQUIRED ({len(result.clarifications)}):")
        print(f"{'='*40}")
        for clar in result.clarifications:
            print(f"\n  Field: {clar.field}")
            print(f"  Question: {clar.question}")
            print(f"  Detected Value: {clar.detected_value}")
            print(f"  Confidence: {clar.confidence:.2f}")
            if clar.options:
                print(f"  Options: {clar.options[:5]}{'...' if len(clar.options) > 5 else ''}")

    print("\n" + "=" * 80 + "\n\n")


def main():
    print("\n" + "=" * 80)
    print("BRIEF AGENT VALIDATION - 6 REAL BRIEFS")
    print("=" * 80 + "\n")

    agent = BriefAgent()

    for brief_name in BRIEF_FILES:
        brief_path = BRIEFS_DIR / brief_name

        if not brief_path.exists():
            print(f"ERROR: Brief not found: {brief_path}")
            print("\n")
            continue

        try:
            result = agent.parse(brief_path)
            print_brief_result(brief_name, brief_path, result)
        except Exception as e:
            print(f"ERROR processing {brief_name}: {e}")
            import traceback
            traceback.print_exc()
            print("\n")


if __name__ == "__main__":
    main()
