"""
Pitboss v4 - Document Comparison Script

Compares Document objects from docx_reader vs gdoc_reader.
Used to validate that gdoc_reader produces equivalent output.

Usage:
    python scripts/compare_gdoc_docx.py \
        --docx "corpora/Koifortune/Main Page_ Koi Fortune AU.docx" \
        --gdoc "1abc123..."
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.document import Document, Heading, Paragraph, List, Table
from ingest.docx_reader import read_docx
from ingest.gdoc_reader import read_gdoc


def count_by_type(doc: Document) -> dict:
    """Count elements by type."""
    counts = {
        'headings': 0,
        'paragraphs': 0,
        'lists': 0,
        'list_items': 0,
        'tables': 0,
        'table_cells': 0,
    }

    for element in doc.elements:
        if isinstance(element, Heading):
            counts['headings'] += 1
        elif isinstance(element, Paragraph):
            counts['paragraphs'] += 1
        elif isinstance(element, List):
            counts['lists'] += 1
            counts['list_items'] += len(element.items)
        elif isinstance(element, Table):
            counts['tables'] += 1
            for row in element.rows:
                counts['table_cells'] += len(row.cells)

    return counts


def get_heading_levels(doc: Document) -> list[tuple[str, int]]:
    """Get all headings with their levels."""
    headings = []
    for element in doc.elements:
        if isinstance(element, Heading):
            headings.append((element.text[:50], element.level.value))
    return headings


def get_highlights(doc: Document) -> list[tuple[str, str]]:
    """Get all highlighted spans (text, color)."""
    highlights = []
    for text, color, loc in doc.highlighted_spans():
        highlights.append((text[:30], color))
    return highlights


def get_hyperlinks(doc: Document) -> list[tuple[str, str]]:
    """Get all hyperlinks (anchor_text, url)."""
    links = []
    for anchor, url, loc in doc.hyperlinks():
        links.append((anchor[:30], url[:50]))
    return links


def compare_documents(docx_doc: Document, gdoc_doc: Document) -> dict:
    """
    Compare two Document objects and return detailed comparison.
    """
    docx_counts = count_by_type(docx_doc)
    gdoc_counts = count_by_type(gdoc_doc)

    docx_headings = get_heading_levels(docx_doc)
    gdoc_headings = get_heading_levels(gdoc_doc)

    docx_highlights = get_highlights(docx_doc)
    gdoc_highlights = get_highlights(gdoc_doc)

    docx_links = get_hyperlinks(docx_doc)
    gdoc_links = get_hyperlinks(gdoc_doc)

    docx_text = docx_doc.full_text()
    gdoc_text = gdoc_doc.full_text()

    return {
        'element_counts': {
            'docx': docx_counts,
            'gdoc': gdoc_counts,
            'match': docx_counts == gdoc_counts,
        },
        'headings': {
            'docx_count': len(docx_headings),
            'gdoc_count': len(gdoc_headings),
            'docx_levels': docx_headings,
            'gdoc_levels': gdoc_headings,
            'match': docx_headings == gdoc_headings,
        },
        'highlights': {
            'docx_count': len(docx_highlights),
            'gdoc_count': len(gdoc_highlights),
            'docx_items': docx_highlights[:10],  # First 10
            'gdoc_items': gdoc_highlights[:10],
            'match': len(docx_highlights) == len(gdoc_highlights),
        },
        'hyperlinks': {
            'docx_count': len(docx_links),
            'gdoc_count': len(gdoc_links),
            'docx_items': docx_links[:10],
            'gdoc_items': gdoc_links[:10],
            'match': len(docx_links) == len(gdoc_links),
        },
        'text': {
            'docx_length': len(docx_text),
            'gdoc_length': len(gdoc_text),
            'match': len(docx_text) == len(gdoc_text),
            'diff_preview': _text_diff_preview(docx_text, gdoc_text) if docx_text != gdoc_text else None,
        },
    }


def _text_diff_preview(text1: str, text2: str, context: int = 50) -> str:
    """Show where texts first differ."""
    for i, (c1, c2) in enumerate(zip(text1, text2)):
        if c1 != c2:
            start = max(0, i - context)
            return (
                f"First difference at position {i}:\n"
                f"  DOCX: ...{repr(text1[start:i+context])}...\n"
                f"  GDOC: ...{repr(text2[start:i+context])}..."
            )

    # One is longer than the other
    if len(text1) != len(text2):
        shorter = min(len(text1), len(text2))
        return (
            f"Texts match until position {shorter}, then:\n"
            f"  DOCX length: {len(text1)}\n"
            f"  GDOC length: {len(text2)}"
        )

    return "Texts are identical"


def print_comparison(result: dict):
    """Print comparison results in a readable format."""
    print("=" * 70)
    print("DOCUMENT COMPARISON: DOCX vs GDOC")
    print("=" * 70)
    print()

    # Element counts
    print("ELEMENT COUNTS:")
    print("-" * 50)
    ec = result['element_counts']
    for key in ec['docx']:
        docx_val = ec['docx'][key]
        gdoc_val = ec['gdoc'][key]
        match = "YES" if docx_val == gdoc_val else "NO"
        print(f"  {key:15} DOCX: {docx_val:4}  GDOC: {gdoc_val:4}  Match: {match}")
    print(f"  {'OVERALL':15} {'':4}  {'':4}  Match: {'YES' if ec['match'] else 'NO'}")
    print()

    # Headings
    print("HEADINGS:")
    print("-" * 50)
    h = result['headings']
    print(f"  Count: DOCX={h['docx_count']}, GDOC={h['gdoc_count']}, Match: {'YES' if h['docx_count']==h['gdoc_count'] else 'NO'}")
    if not h['match'] and h['docx_levels'] != h['gdoc_levels']:
        print("  Heading level differences:")
        for i, (docx_h, gdoc_h) in enumerate(zip(h['docx_levels'], h['gdoc_levels'])):
            if docx_h != gdoc_h:
                print(f"    [{i}] DOCX: {docx_h} vs GDOC: {gdoc_h}")
    print()

    # Highlights
    print("HIGHLIGHTS:")
    print("-" * 50)
    hl = result['highlights']
    print(f"  Count: DOCX={hl['docx_count']}, GDOC={hl['gdoc_count']}, Match: {'YES' if hl['match'] else 'NO'}")
    if hl['docx_items']:
        print("  DOCX samples:")
        for text, color in hl['docx_items'][:5]:
            print(f"    - '{text}...' ({color})")
    if hl['gdoc_items']:
        print("  GDOC samples:")
        for text, color in hl['gdoc_items'][:5]:
            print(f"    - '{text}...' ({color})")
    print()

    # Hyperlinks
    print("HYPERLINKS:")
    print("-" * 50)
    lk = result['hyperlinks']
    print(f"  Count: DOCX={lk['docx_count']}, GDOC={lk['gdoc_count']}, Match: {'YES' if lk['match'] else 'NO'}")
    if lk['docx_items']:
        print("  DOCX samples:")
        for anchor, url in lk['docx_items'][:3]:
            print(f"    - '{anchor}...' -> {url}...")
    if lk['gdoc_items']:
        print("  GDOC samples:")
        for anchor, url in lk['gdoc_items'][:3]:
            print(f"    - '{anchor}...' -> {url}...")
    print()

    # Text comparison
    print("TEXT CONTENT:")
    print("-" * 50)
    tx = result['text']
    print(f"  Length: DOCX={tx['docx_length']}, GDOC={tx['gdoc_length']}, Match: {'YES' if tx['match'] else 'NO'}")
    if tx['diff_preview']:
        print(f"  {tx['diff_preview']}")
    print()

    # Summary
    print("=" * 70)
    all_match = all([
        result['element_counts']['match'],
        result['headings']['match'],
        result['highlights']['match'],
        result['hyperlinks']['match'],
        result['text']['match'],
    ])
    if all_match:
        print("RESULT: DOCUMENTS MATCH")
    else:
        print("RESULT: DOCUMENTS DIFFER")
        print("Differences:")
        if not result['element_counts']['match']:
            print("  - Element counts differ")
        if not result['headings']['match']:
            print("  - Heading levels differ")
        if not result['highlights']['match']:
            print("  - Highlight counts differ")
        if not result['hyperlinks']['match']:
            print("  - Hyperlink counts differ")
        if not result['text']['match']:
            print("  - Text content differs")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Compare Document objects from docx vs gdoc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '--docx', '-d',
        type=Path,
        required=True,
        help='Path to .docx file'
    )

    parser.add_argument(
        '--gdoc', '-g',
        type=str,
        required=True,
        help='Google Doc ID or URL'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output'
    )

    args = parser.parse_args()

    if not args.docx.exists():
        print(f"Error: DOCX file not found: {args.docx}")
        sys.exit(1)

    print(f"Reading DOCX: {args.docx}")
    docx_doc = read_docx(args.docx)
    print(f"  -> {len(docx_doc.elements)} elements")

    print(f"Reading GDOC: {args.gdoc}")
    gdoc_doc = read_gdoc(args.gdoc)
    print(f"  -> {len(gdoc_doc.elements)} elements")
    print()

    result = compare_documents(docx_doc, gdoc_doc)
    print_comparison(result)


if __name__ == '__main__':
    main()
