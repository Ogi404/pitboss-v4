"""
Structure Check Validation - Real Koifortune Article + Brief

Validates the structure check against a real article and brief to confirm:
1. Fuzzy section matching doesn't false-flag present sections
2. Hierarchy issues detected correctly
3. Intro/outro checks work
4. Word count comparison is sensible
5. All findings are proposals (auto_applicable=False)
"""

import sys
import io
from pathlib import Path

# Force UTF-8 output for Unicode characters
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))

from ingest.brief_agent import BriefAgent
from ingest.docx_reader import read_docx
from deterministic.structure import StructureCheck, count_words


BRIEFS_DIR = Path(r"C:\Users\User\Downloads\Lib_pitboss_v4\Briefs")
ARTICLES_DIR = Path(r"C:\Users\User\Downloads\Lib_pitboss_v4\approved-articles\Koifortune")

BRIEF_FILE = "Content Task_ Koifortune AU.xlsx"
ARTICLE_FILE = "Main Page_ Koi Fortune AU.docx"


class MockStandards:
    """Mock standards with brand name."""
    brand_name = "Koifortune"


def main():
    print("\n" + "=" * 100)
    print("STRUCTURE CHECK VALIDATION - Real Koifortune Article + Brief")
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
    actual_word_count = count_words(full_text)

    print(f"\nBrief: {BRIEF_FILE}")
    print(f"Article: {ARTICLE_FILE}")
    print(f"Article length: {len(full_text)} chars, {actual_word_count} words")

    # Display brief sections
    print("\n" + "-" * 60)
    print("BRIEF SECTIONS REQUIRED:")
    print("-" * 60)
    if hasattr(brief, "sections") and brief.sections:
        for i, section in enumerate(brief.sections, 1):
            print(f"  {i}. {section.heading}")
    else:
        print("  (No sections specified in brief)")

    # Display article headings
    print("\n" + "-" * 60)
    print("ARTICLE HEADINGS FOUND:")
    print("-" * 60)
    headings = document.headings()
    for h in headings:
        print(f"  H{h.level.value}: {h.text}")

    # Display brief target word count
    target_wc = getattr(brief, "target_word_count", None)
    print("\n" + "-" * 60)
    print("WORD COUNT ANALYSIS:")
    print("-" * 60)
    print(f"  Actual: {actual_word_count} words")
    print(f"  Target: {target_wc} words" if target_wc else "  Target: (not specified)")
    if target_wc and target_wc > 0:
        deviation = abs(actual_word_count - target_wc) / target_wc * 100
        direction = "over" if actual_word_count > target_wc else "under"
        print(f"  Deviation: {deviation:.1f}% {direction}")

    # Run the structure check
    check = StructureCheck()
    standards = MockStandards()
    findings = check.run(document, standards, brief=brief)

    # Group findings by check_name
    by_type = {}
    for f in findings:
        key = f.check_name
        if key not in by_type:
            by_type[key] = []
        by_type[key].append(f)

    # Display findings by category
    print("\n" + "=" * 100)
    print(f"STRUCTURE CHECK FINDINGS ({len(findings)} total)")
    print("=" * 100)

    for check_name, check_findings in sorted(by_type.items()):
        print(f"\n{check_name.upper()} ({len(check_findings)} findings)")
        print("-" * 60)
        for i, f in enumerate(check_findings, 1):
            print(f"\n[{i}] {f.check_name}")
            print(f"    Severity: {f.severity}")
            print(f"    Confidence: {f.confidence}")
            print(f"    Reasoning: {f.reasoning}")
            print(f"    auto_applicable: {f.auto_applicable}")
            if f.original_text:
                print(f"    Original text: '{f.original_text[:50]}...'")
            if f.metadata:
                print(f"    Metadata: {dict(f.metadata)}")

    # Summary
    print("\n" + "=" * 100)
    print("VALIDATION SUMMARY")
    print("=" * 100)

    # Check that fuzzy matching worked
    missing_sections = [f for f in findings if f.check_name == "structure.missing_section"]
    print(f"\n1. Missing Sections: {len(missing_sections)}")
    if missing_sections:
        for f in missing_sections:
            print(f"   - {f.metadata_dict.get('required_section', 'unknown')}")
    else:
        print("   All brief sections matched in article (fuzzy matching worked)")

    # Hierarchy issues
    hierarchy = [f for f in findings if f.check_name == "structure.hierarchy"]
    print(f"\n2. Hierarchy Issues: {len(hierarchy)}")
    for f in hierarchy:
        print(f"   - {f.reasoning[:60]}...")

    # Intro/outro
    intro = [f for f in findings if f.check_name == "structure.missing_intro"]
    outro = [f for f in findings if f.check_name == "structure.missing_outro"]
    print(f"\n3. Intro Issues: {len(intro)}")
    print(f"   Outro Issues: {len(outro)}")

    # Word count
    word_count = [f for f in findings if f.check_name == "structure.word_count"]
    print(f"\n4. Word Count Issues: {len(word_count)}")
    for f in word_count:
        print(f"   - {f.reasoning}")

    # Auto-applicable check
    all_proposals = all(not f.auto_applicable for f in findings)
    print(f"\n5. All findings are proposals (auto_applicable=False): {all_proposals}")

    print("\n" + "=" * 100)


if __name__ == "__main__":
    main()
