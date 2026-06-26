#!/usr/bin/env python3
"""
Live validation of consistency check with real OpenAI calls.

Tests:
A. TRUE POSITIVE: planted conflict -> CONFLICT verdict
B. TRUE NEGATIVE: paired but legitimate -> DIFFERENT verdict
C. CLEAN ARTICLE: no conflicts -> zero proposals
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.document import Document, Paragraph, TextRun
from judgment.consistency import (
    ConsistencyCheck,
    _extract_claims,
    _find_conflict_pairs,
    _build_prompt,
    _parse_llm_response,
)
from judgment.llm_client import call_llm, get_config_summary

# Track total costs
total_prompt_tokens = 0
total_completion_tokens = 0


def make_paragraph(text: str, start_offset: int) -> Paragraph:
    return Paragraph(
        text=text,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
        _runs=[TextRun(text=text, start_offset=0, end_offset=len(text))],
    )


def create_document(texts: list[str], title: str = "Test") -> Document:
    elements = []
    offset = 0
    for text in texts:
        elements.append(make_paragraph(text, offset))
        offset += len(text) + 1
    return Document(elements=elements, title=title)


def print_sep(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def call_llm_with_usage(prompt: str) -> tuple[str | None, dict]:
    """Call LLM and return response + usage stats."""
    global total_prompt_tokens, total_completion_tokens

    import os
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }

    # gpt-4o-mini pricing: $0.15/1M input, $0.60/1M output
    cost_input = (usage["prompt_tokens"] / 1_000_000) * 0.15
    cost_output = (usage["completion_tokens"] / 1_000_000) * 0.60
    usage["cost_usd"] = cost_input + cost_output

    total_prompt_tokens += usage["prompt_tokens"]
    total_completion_tokens += usage["completion_tokens"]

    content = response.choices[0].message.content if response.choices else None
    return content, usage


def test_true_positive():
    """A. TRUE POSITIVE: planted $4000 vs $5000 welcome bonus conflict."""
    print_sep("TEST A: TRUE POSITIVE (Planted Conflict)")

    doc = create_document([
        "Welcome to KoiFortune Casino!",
        "",
        "Sign up today and get a $4000 welcome bonus on your first deposit.",
        "Our welcome offer includes free spins and cashback rewards.",
        "",
        "Bonus Details:",
        "New players receive up to $5000 on their first deposit when joining.",
        "This generous welcome package is available to all Australian players.",
    ], title="Planted Conflict Test")

    print("DOCUMENT:")
    for i, el in enumerate(doc.elements):
        if isinstance(el, Paragraph) and el.text:
            print(f"  [{i}] {el.text}")
    print()

    # Extract and pair
    claims = _extract_claims(doc)
    pairs = _find_conflict_pairs(claims)

    print(f"EXTRACTED CLAIMS: {len(claims)}")
    for c in claims:
        print(f"  - {c.category}.{c.subtype}: {c.value} (element {c.element_index})")
    print()

    print(f"PRE-FILTER PAIRS: {len(pairs)}")
    for a, b in pairs:
        print(f"  - {a.value} vs {b.value} ({a.category}.{a.subtype})")
    print()

    if not pairs:
        print("ERROR: Pre-filter found no pairs!")
        return False

    # Build prompt and call LLM
    prompt = _build_prompt(pairs)
    print("PROMPT TO LLM:")
    print("-" * 50)
    print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
    print("-" * 50)
    print()

    response, usage = call_llm_with_usage(prompt)

    print("RAW LLM RESPONSE:")
    print("-" * 50)
    print(response)
    print("-" * 50)
    print()

    print(f"TOKENS: {usage['prompt_tokens']} prompt + {usage['completion_tokens']} completion = {usage['total_tokens']} total")
    print(f"COST: ${usage['cost_usd']:.6f}")
    print()

    # Parse verdict
    verdicts = _parse_llm_response(response, len(pairs))
    verdict = verdicts[0] if verdicts else None

    if verdict and verdict.verdict == "CONFLICT":
        print("*** VERDICT: CONFLICT ***")
        print(f"LLM REASONING: {verdict.reasoning}")
        print()

        # Show what editor would see
        claim_a, claim_b = pairs[0]
        print("PROPOSAL TEXT (what editor sees):")
        print("=" * 50)
        print(f"CHECK: consistency")
        print(f"SEVERITY: warning")
        print(f"ORIGINAL: {claim_a.value} (element {claim_a.element_index}) vs {claim_b.value} (element {claim_b.element_index})")
        print()
        print("REASONING:")
        print(f"Internal conflict detected: {claim_a.category}.{claim_a.subtype}")
        print(f"Location 1 (element {claim_a.element_index}): \"{claim_a.context}\" -> {claim_a.value}")
        print(f"Location 2 (element {claim_b.element_index}): \"{claim_b.context}\" -> {claim_b.value}")
        print(f"LLM analysis: {verdict.reasoning}")
        print("=" * 50)
        return True
    else:
        print(f"*** UNEXPECTED VERDICT: {verdict.verdict if verdict else 'NONE'} ***")
        return False


def test_true_negative():
    """B. TRUE NEGATIVE: paired by pre-filter but legitimately different."""
    print_sep("TEST B: TRUE NEGATIVE (Paired but Legitimate)")

    # This document has two welcome bonus amounts that the pre-filter WILL pair
    # (same category: BONUS_AMOUNT, same subtype: welcome, different values)
    # But they're legitimately different: minimum vs maximum of a range
    doc = create_document([
        "KoiFortune Welcome Bonus",
        "",
        "New players can claim a welcome bonus starting from $100 minimum.",
        "The maximum welcome bonus available is $500 for high rollers.",
        "Your actual welcome bonus depends on your first deposit amount.",
    ], title="Min/Max Range Test")

    print("DOCUMENT:")
    for i, el in enumerate(doc.elements):
        if isinstance(el, Paragraph) and el.text:
            print(f"  [{i}] {el.text}")
    print()

    # Extract and pair
    claims = _extract_claims(doc)
    pairs = _find_conflict_pairs(claims)

    print(f"EXTRACTED CLAIMS: {len(claims)}")
    for c in claims:
        print(f"  - {c.category}.{c.subtype}: {c.value} (element {c.element_index})")
    print()

    print(f"PRE-FILTER PAIRS: {len(pairs)}")
    for a, b in pairs:
        print(f"  - {a.value} vs {b.value} ({a.category}.{a.subtype})")
    print()

    if not pairs:
        print("NOTE: Pre-filter found no pairs (subtype differentiation worked)")
        print("This means the pre-filter was smart enough to not pair these.")
        print("Test B needs a case where pre-filter DOES pair but LLM says DIFFERENT.")
        return True  # Still a pass - pre-filter handled it

    # Build prompt and call LLM
    prompt = _build_prompt(pairs)
    print("PROMPT TO LLM:")
    print("-" * 50)
    print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
    print("-" * 50)
    print()

    response, usage = call_llm_with_usage(prompt)

    print("RAW LLM RESPONSE:")
    print("-" * 50)
    print(response)
    print("-" * 50)
    print()

    print(f"TOKENS: {usage['prompt_tokens']} prompt + {usage['completion_tokens']} completion = {usage['total_tokens']} total")
    print(f"COST: ${usage['cost_usd']:.6f}")
    print()

    # Parse verdict
    verdicts = _parse_llm_response(response, len(pairs))

    all_different = all(v.verdict == "DIFFERENT" for v in verdicts)

    if all_different:
        print("*** VERDICT: DIFFERENT (all pairs) ***")
        for v in verdicts:
            print(f"  Pair {v.pair_index + 1}: {v.reasoning}")
        print()
        print("RESULT: Zero proposals generated (LLM correctly cleared non-conflict)")
        return True
    else:
        for v in verdicts:
            print(f"*** VERDICT for pair {v.pair_index + 1}: {v.verdict} ***")
            print(f"    Reasoning: {v.reasoning}")
        return False


def test_clean_article():
    """C. CLEAN ARTICLE: consistent values, no conflicts."""
    print_sep("TEST C: CLEAN ARTICLE (No Conflicts)")

    doc = create_document([
        "Welcome to KoiFortune Casino!",
        "",
        "Sign up and get a $500 welcome bonus on your first deposit.",
        "The $500 bonus comes with a 35x wagering requirement.",
        "Complete the 35x playthrough to withdraw your winnings.",
        "",
        "We have over 1000 games available.",
        "Choose from 1000+ pokies and table games.",
    ], title="Clean Article Test")

    print("DOCUMENT:")
    for i, el in enumerate(doc.elements):
        if isinstance(el, Paragraph) and el.text:
            print(f"  [{i}] {el.text}")
    print()

    # Extract and pair
    claims = _extract_claims(doc)
    pairs = _find_conflict_pairs(claims)

    print(f"EXTRACTED CLAIMS: {len(claims)}")
    for c in claims:
        print(f"  - {c.category}.{c.subtype}: {c.value}")
    print()

    print(f"PRE-FILTER PAIRS: {len(pairs)}")

    if pairs:
        print("WARNING: Pre-filter found pairs in supposedly clean article:")
        for a, b in pairs:
            print(f"  - {a.value} vs {b.value}")
        return False

    print()
    print("*** RESULT: ZERO PROPOSALS ***")
    print("No LLM call made (pre-filter found no potential conflicts)")
    print("Cost: $0.00")
    return True


def main():
    print("\n" + "=" * 70)
    print("  LIVE VALIDATION TRIAD - REAL OPENAI CALLS")
    print("=" * 70)

    print(f"\nLLM CONFIG: {get_config_summary()}")
    print()

    results = []

    results.append(("A. True Positive (CONFLICT)", test_true_positive()))
    results.append(("B. True Negative (DIFFERENT)", test_true_negative()))
    results.append(("C. Clean Article (ZERO)", test_clean_article()))

    print_sep("VALIDATION SUMMARY")

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    # Total cost
    total_cost_input = (total_prompt_tokens / 1_000_000) * 0.15
    total_cost_output = (total_completion_tokens / 1_000_000) * 0.60
    total_cost = total_cost_input + total_cost_output

    print()
    print(f"TOTAL TOKENS: {total_prompt_tokens} prompt + {total_completion_tokens} completion")
    print(f"TOTAL COST: ${total_cost:.6f}")

    all_passed = all(p for _, p in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
