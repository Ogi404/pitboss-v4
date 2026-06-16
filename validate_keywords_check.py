"""
Keywords Check Validation - Enriched Missing Keyword Findings

Shows the 14 missing keyword findings with enriched reasoning and sub-type tags.
"""

import sys
import io
from pathlib import Path

# Force UTF-8 output for Unicode characters
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))

from ingest.brief_agent import BriefAgent
from ingest.docx_reader import read_docx
from deterministic.keywords import KeywordsCheck


BRIEFS_DIR = Path(r"C:\Users\User\Downloads\Lib_pitboss_v4\Briefs")
ARTICLES_DIR = Path(r"C:\Users\User\Downloads\Lib_pitboss_v4\approved-articles\Koifortune")

BRIEF_FILE = "Content Task_ Koifortune AU.xlsx"
ARTICLE_FILE = "Main Page_ Koi Fortune AU.docx"


class MockStandards:
    """Mock standards with brand name."""
    brand_name = "Koifortune"


def main():
    print("\n" + "=" * 100)
    print("ENRICHED MISSING KEYWORD FINDINGS")
    print("=" * 100)

    # Parse brief
    brief_path = BRIEFS_DIR / BRIEF_FILE
    agent = BriefAgent()
    result = agent.parse(brief_path)
    brief = result.brief

    # Load article
    article_path = ARTICLES_DIR / ARTICLE_FILE
    document = read_docx(article_path)
    full_text = document.full_text()

    print(f"Brief: {BRIEF_FILE}")
    print(f"Article: {ARTICLE_FILE}")
    print(f"Article length: {len(full_text)} chars, {len(full_text.split())} words")

    # Run the keywords check
    check = KeywordsCheck()
    standards = MockStandards()
    findings = check.run(document, standards, brief=brief)

    # Get missing keyword findings
    missing_findings = [f for f in findings if f.check_name == "keywords.missing"]

    # Group by missing_type
    truly_absent = []
    wrong_construction = []

    for f in missing_findings:
        meta = dict(f.metadata)
        if meta.get("missing_type") == "truly_absent":
            truly_absent.append(f)
        else:
            wrong_construction.append(f)

    # Display findings
    print("\n" + "=" * 100)
    print(f"WRONG CONSTRUCTION ({len(wrong_construction)} findings)")
    print("Words present but not as exact phrase - writer needs to adjust wording")
    print("=" * 100)

    for i, f in enumerate(wrong_construction, 1):
        meta = dict(f.metadata)
        print(f"\n[{i}] KEYWORD: '{meta['keyword']}'")
        print(f"    TYPE: {meta['missing_type']}")
        print(f"    REASONING: {f.reasoning}")
        print(f"    auto_applicable: {f.auto_applicable}")

    print("\n" + "=" * 100)
    print(f"TRULY ABSENT ({len(truly_absent)} findings)")
    print("Concept not in article at all - writer needs to add new content")
    print("=" * 100)

    for i, f in enumerate(truly_absent, 1):
        meta = dict(f.metadata)
        print(f"\n[{i}] KEYWORD: '{meta['keyword']}'")
        print(f"    TYPE: {meta['missing_type']}")
        print(f"    REASONING: {f.reasoning}")
        print(f"    auto_applicable: {f.auto_applicable}")

    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total missing keywords: {len(missing_findings)}")
    print(f"  - wrong_construction: {len(wrong_construction)} (words present, phrase missing)")
    print(f"  - truly_absent: {len(truly_absent)} (concept not in article)")
    print(f"All findings have auto_applicable=False: {all(not f.auto_applicable for f in missing_findings)}")


if __name__ == "__main__":
    main()
