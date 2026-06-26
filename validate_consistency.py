#!/usr/bin/env python3
"""
Validation script for consistency.py - demonstrates the validation triad.

1. True-positive catch: Planted conflict is detected
2. Clean-article silence: No proposals for clean article
3. Non-pairing verification: Different-but-same-category claims don't get paired
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.document import Document, Paragraph, TextRun
from judgment.consistency import (
    ConsistencyCheck,
    _extract_claims,
    _find_conflict_pairs,
)


def make_paragraph(text: str, start_offset: int) -> Paragraph:
    """Helper to create a paragraph with proper offsets."""
    return Paragraph(
        text=text,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
        _runs=[TextRun(text=text, start_offset=0, end_offset=len(text))],
    )


def create_document(texts: list[str], title: str = "Test Doc") -> Document:
    """Create a test document from list of paragraph texts."""
    elements = []
    offset = 0
    for text in texts:
        elements.append(make_paragraph(text, offset))
        offset += len(text) + 1
    return Document(elements=elements, title=title)


def print_separator(title: str):
    """Print a section separator."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def validate_true_positive():
    """VALIDATION 1: True-positive catch - planted conflict is detected."""
    print_separator("VALIDATION 1: TRUE-POSITIVE CATCH")

    doc = create_document([
        "Welcome to KoiFortune Casino!",
        "",
        "Sign up today and get a $4000 welcome bonus on your first deposit.",
        "Our welcome offer includes free spins and cashback rewards.",
        "",
        "Banking Options:",
        "We accept Visa, Mastercard, and crypto payments.",
        "",
        "Bonus Details:",
        "New players receive up to $5000 on their first deposit when joining.",
        "This generous welcome package is available to all Australian players.",
    ], title="KoiFortune Review - Planted Conflict")

    print("TEST DOCUMENT (planted conflict: $4000 vs $5000 welcome bonus):")
    print("-" * 50)
    for i, el in enumerate(doc.elements):
        if isinstance(el, Paragraph) and el.text:
            print(f"  [{i}] {el.text[:80]}{'...' if len(el.text) > 80 else ''}")
    print()

    # Step 1: Extract claims
    claims = _extract_claims(doc)
    print(f"EXTRACTED CLAIMS: {len(claims)}")
    for claim in claims:
        print(f"  - {claim.category}.{claim.subtype}: {claim.value} (element {claim.element_index})")
    print()

    # Step 2: Find conflict pairs
    pairs = _find_conflict_pairs(claims)
    print(f"POTENTIAL CONFLICT PAIRS: {len(pairs)}")
    for claim_a, claim_b in pairs:
        print(f"  - {claim_a.value} vs {claim_b.value} ({claim_a.category}.{claim_a.subtype})")
    print()

    # Step 3: Run check (with mock if no API key)
    check = ConsistencyCheck()
    has_trigger = check._has_trigger(doc, None)
    print(f"HAS TRIGGER (pre-filter found pairs): {has_trigger}")

    if not has_trigger:
        print("ERROR: Pre-filter should have found the conflict!")
        return False

    # Check for API key (OpenAI default)
    from judgment.llm_client import get_config_summary
    print(f"\nLLM CONFIG: {get_config_summary()}")

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        print("\nCalling LLM for judgment...")
        findings = check._generate_proposals(doc, None, None)

        if findings:
            print(f"\n*** CONFLICT DETECTED - {len(findings)} finding(s) ***")
            for finding in findings:
                print("\nPROPOSAL TEXT (what editor would see):")
                print("-" * 50)
                print(f"Check: {finding.check_name}")
                print(f"Severity: {finding.severity}")
                print(f"Original: {finding.original_text}")
                print(f"\nReasoning:")
                print(finding.reasoning)
                print("-" * 50)
            return True
        else:
            print("\nNo findings - LLM may have classified as DIFFERENT")
            return False
    else:
        print("\n[MOCK MODE - no OPENAI_API_KEY or ANTHROPIC_API_KEY set]")
        print("Pre-filter correctly identified the conflict pair.")
        print("With API key, LLM would be called to confirm CONFLICT vs DIFFERENT.")
        return True


def validate_clean_article():
    """VALIDATION 2: Clean-article silence - no proposals for clean article."""
    print_separator("VALIDATION 2: CLEAN-ARTICLE SILENCE")

    doc = create_document([
        "Welcome to KoiFortune Casino!",
        "",
        "Sign up today and get a $4000 welcome bonus on your first deposit.",
        "The $4000 bonus comes with a 35x wagering requirement.",
        "Complete the 35x playthrough to withdraw your winnings.",
        "",
        "We have over 1000 games available.",
        "Choose from 1000+ pokies and table games.",
        "",
        "Reload bonus of $200 is available on your second deposit.",
        "Minimum deposit is $20. Minimum withdrawal is $50.",
    ], title="KoiFortune Review - Clean Article")

    print("TEST DOCUMENT (consistent values throughout):")
    print("-" * 50)
    for i, el in enumerate(doc.elements):
        if isinstance(el, Paragraph) and el.text:
            print(f"  [{i}] {el.text[:80]}{'...' if len(el.text) > 80 else ''}")
    print()

    # Check for conflicts
    claims = _extract_claims(doc)
    pairs = _find_conflict_pairs(claims)

    print(f"EXTRACTED CLAIMS: {len(claims)}")
    print(f"POTENTIAL CONFLICT PAIRS: {len(pairs)}")

    check = ConsistencyCheck()
    has_trigger = check._has_trigger(doc, None)
    print(f"HAS TRIGGER: {has_trigger}")

    if has_trigger:
        print("\nWARNING: Pre-filter found pairs (checking if same values)...")
        for claim_a, claim_b in pairs:
            print(f"  - {claim_a.value} vs {claim_b.value}")
        return False
    else:
        print("\n*** CLEAN ARTICLE - NO TRIGGER ***")
        print("No LLM call made (cost control working correctly).")
        return True


def validate_non_pairing():
    """VALIDATION 3: Non-pairing - different-but-same-category claims don't get paired."""
    print_separator("VALIDATION 3: NON-PAIRING VERIFICATION")

    doc = create_document([
        "Welcome Bonus: Get $500 on your first deposit!",
        "",
        "Reload Bonus: Get $200 on your second deposit!",
        "",
        "Minimum deposit is $20.",
        "Minimum withdrawal is $50.",
        "",
        "Slot wagering is 35x on bonus funds.",
        "Table games have 50x wagering requirement.",
    ], title="Different Claims - Same Categories")

    print("TEST DOCUMENT (different claims in same categories):")
    print("-" * 50)
    for i, el in enumerate(doc.elements):
        if isinstance(el, Paragraph) and el.text:
            print(f"  [{i}] {el.text[:80]}")
    print()

    # Extract and show claims with subtypes
    claims = _extract_claims(doc)
    print(f"EXTRACTED CLAIMS: {len(claims)}")
    for claim in claims:
        print(f"  - {claim.category}.{claim.subtype}: {claim.value}")
    print()

    # Find pairs
    pairs = _find_conflict_pairs(claims)
    print(f"CONFLICT PAIRS FOUND: {len(pairs)}")

    if pairs:
        print("\nERROR: These should NOT be paired (different subtypes):")
        for claim_a, claim_b in pairs:
            print(f"  - {claim_a.value} ({claim_a.subtype}) vs {claim_b.value} ({claim_b.subtype})")
        return False
    else:
        print("\n*** NO FALSE PAIRS ***")
        print("Pre-filter correctly distinguished:")
        print("  - welcome bonus vs reload bonus (different subtypes)")
        print("  - deposit minimum vs withdrawal minimum (different subtypes)")
        print("  - slot wagering vs table wagering (different subtypes)")
        print("\nNo LLM call needed - pre-filter handled it.")
        return True


def main():
    """Run all three validations."""
    print("\n" + "=" * 70)
    print("  CONSISTENCY CHECK VALIDATION TRIAD")
    print("=" * 70)

    results = []

    results.append(("True-positive catch", validate_true_positive()))
    results.append(("Clean-article silence", validate_clean_article()))
    results.append(("Non-pairing verification", validate_non_pairing()))

    print_separator("VALIDATION SUMMARY")

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\nAll validations passed!")
    else:
        print("\nSome validations failed - review output above.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
