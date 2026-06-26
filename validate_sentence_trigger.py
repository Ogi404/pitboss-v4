#!/usr/bin/env python3
"""
Validate sentence complexity trigger on real corpus articles.

Tests:
1. How many sentences trigger per article on REAL data?
2. Are the triggered sentences TRUE run-ons or false alarms?
3. Edge cases: short articles, uniformly long articles
"""

import sys
import re
import statistics
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent))

from ingest.docx_reader import read_docx
from core.document import Paragraph, Heading


@dataclass
class SentenceStats:
    """Stats for a single sentence."""
    text: str
    word_count: int
    clause_count: int
    depth_score: float
    z_score: float  # How many std devs above mean
    triggers: bool
    element_index: int


# Subordinating conjunctions and relative pronouns that indicate clauses
CLAUSE_MARKERS = [
    r'\bwhich\b', r'\bthat\b', r'\bwho\b', r'\bwhom\b', r'\bwhose\b',
    r'\bwhere\b', r'\bwhen\b', r'\bwhile\b', r'\bwhereas\b',
    r'\bbecause\b', r'\bsince\b', r'\balthough\b', r'\bthough\b',
    r'\beven though\b', r'\bif\b', r'\bunless\b', r'\buntil\b',
    r'\bbefore\b', r'\bafter\b', r'\bas\b', r'\bso that\b',
]

# Compile patterns
CLAUSE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CLAUSE_MARKERS]

# Sentence splitter (simple, handles common cases)
SENTENCE_PATTERN = re.compile(r'[.!?]+\s+|\n')


def count_clauses(sentence: str) -> int:
    """Count subordinate clause markers in a sentence."""
    count = 0
    for pattern in CLAUSE_PATTERNS:
        count += len(pattern.findall(sentence))
    return count


def split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    if not text:
        return []

    # Split on sentence boundaries
    parts = SENTENCE_PATTERN.split(text)

    # Clean up
    sentences = []
    for part in parts:
        part = part.strip()
        if part and len(part.split()) >= 3:  # Skip very short fragments
            sentences.append(part)

    return sentences


def analyze_article(filepath: Path) -> dict:
    """Analyze a single article and return trigger results."""
    doc = read_docx(filepath)

    # Extract all prose sentences (skip headings, lists for now)
    all_sentences: list[SentenceStats] = []

    for idx, element in enumerate(doc.elements):
        if isinstance(element, Paragraph) and element.text:
            text = element.text.strip()
            if not text:
                continue

            # Split into sentences
            sentences = split_sentences(text)

            for sent in sentences:
                word_count = len(sent.split())
                clause_count = count_clauses(sent)
                depth_score = word_count + (clause_count * 8)

                all_sentences.append(SentenceStats(
                    text=sent,
                    word_count=word_count,
                    clause_count=clause_count,
                    depth_score=depth_score,
                    z_score=0.0,  # Computed below
                    triggers=False,  # Computed below
                    element_index=idx,
                ))

    if len(all_sentences) < 5:
        return {
            "filepath": str(filepath),
            "sentence_count": len(all_sentences),
            "error": "Too few sentences for analysis",
            "triggers": [],
        }

    # Compute article baseline
    depth_scores = [s.depth_score for s in all_sentences]
    article_mean = statistics.mean(depth_scores)
    article_stdev = statistics.stdev(depth_scores) if len(depth_scores) > 1 else 0

    word_counts = [s.word_count for s in all_sentences]
    word_mean = statistics.mean(word_counts)

    # Apply trigger logic
    triggered = []

    for sent in all_sentences:
        if article_stdev > 0:
            sent.z_score = (sent.depth_score - article_mean) / article_stdev
        else:
            sent.z_score = 0

        # Trigger conditions (all must be true):
        # 1. Statistical outlier: >2.0 std devs above mean
        # 2. Absolute threshold: >=40 words OR >=3 clauses
        is_outlier = sent.z_score > 2.0
        is_absolutely_complex = (sent.word_count >= 40) or (sent.clause_count >= 3)

        sent.triggers = is_outlier and is_absolutely_complex

        if sent.triggers:
            triggered.append(sent)

    return {
        "filepath": str(filepath.name),
        "sentence_count": len(all_sentences),
        "word_mean": round(word_mean, 1),
        "depth_mean": round(article_mean, 1),
        "depth_stdev": round(article_stdev, 1),
        "trigger_count": len(triggered),
        "triggers": triggered,
    }


def print_results(results: dict):
    """Pretty print analysis results."""
    print(f"\n{'='*70}")
    print(f"ARTICLE: {results['filepath']}")
    print(f"{'='*70}")

    if "error" in results:
        print(f"  Error: {results['error']}")
        return

    print(f"  Sentences: {results['sentence_count']}")
    print(f"  Word mean: {results['word_mean']} words/sentence")
    print(f"  Depth mean: {results['depth_mean']} (stdev: {results['depth_stdev']})")
    print(f"  TRIGGERS: {results['trigger_count']}")

    if results['triggers']:
        print(f"\n  TRIGGERED SENTENCES:")
        print(f"  {'-'*60}")
        for sent in results['triggers']:
            # Truncate long sentences for display
            display_text = sent.text[:100] + "..." if len(sent.text) > 100 else sent.text
            print(f"\n  [{sent.element_index}] \"{display_text}\"")
            print(f"      -> {sent.word_count} words, {sent.clause_count} clauses, z={sent.z_score:.1f} std devs")
            print(f"      -> TRIGGER REASON: {sent.word_count} words, {sent.clause_count} clauses")
            print(f"         - {sent.z_score:.1f} std devs above this article's {results['word_mean']:.0f}-word average")
    else:
        print(f"\n  No sentences triggered (clean article)")


def main():
    print("\n" + "="*70)
    print("  SENTENCE COMPLEXITY TRIGGER VALIDATION")
    print("  Testing on real corpus articles")
    print("="*70)

    # Find test articles from different brands
    corpus_path = Path("corpora")

    test_articles = [
        corpus_path / "Koifortune" / "Main Page_ Koi Fortune AU.docx",
        corpus_path / "22Bet" / "22Bet App.docx",
        corpus_path / "Playamo" / "Playamo Review.docx",
        corpus_path / "HellSpin" / "HellSpin Review.docx",
    ]

    # Find articles that exist
    existing = []
    for path in test_articles:
        if path.exists():
            existing.append(path)

    # If not enough, grab some from the first available brand
    if len(existing) < 3:
        for brand_dir in corpus_path.iterdir():
            if brand_dir.is_dir() and not brand_dir.name.startswith('_'):
                for docx in brand_dir.glob("*.docx"):
                    existing.append(docx)
                    if len(existing) >= 4:
                        break
            if len(existing) >= 4:
                break

    if not existing:
        print("\nNo .docx files found in corpora/")
        return 1

    print(f"\nTesting {len(existing)} articles...")

    all_results = []
    total_sentences = 0
    total_triggers = 0

    for filepath in existing[:4]:  # Limit to 4 articles
        results = analyze_article(filepath)
        all_results.append(results)
        print_results(results)

        if "sentence_count" in results:
            total_sentences += results["sentence_count"]
            total_triggers += results["trigger_count"]

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  Articles analyzed: {len(all_results)}")
    print(f"  Total sentences: {total_sentences}")
    print(f"  Total triggers: {total_triggers}")
    print(f"  Trigger rate: {100*total_triggers/total_sentences:.1f}%" if total_sentences > 0 else "N/A")
    print(f"  Avg triggers/article: {total_triggers/len(all_results):.1f}")

    # Edge case analysis
    print(f"\n{'='*70}")
    print(f"  EDGE CASE ANALYSIS")
    print(f"{'='*70}")

    # Check if any article had uniformly long sentences
    for r in all_results:
        if "word_mean" in r and r["word_mean"] > 25:
            print(f"\n  HIGH BASELINE ARTICLE: {r['filepath']}")
            print(f"    Mean: {r['word_mean']} words/sentence")
            print(f"    Triggers: {r['trigger_count']} (relative detection working)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
