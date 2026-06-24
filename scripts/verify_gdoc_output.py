"""Verify corrected Google Doc output."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.gdoc_reader import read_gdoc
from core.document import Table, Heading, Paragraph, List

source = read_gdoc('1O4QTUAtkN9LvGFT7iDregCA-F5R5LKQQZTQ8qVX1xDQ')
corrected = read_gdoc('1WwUnRTf1Axpa97Bh1NCmTujlBgFu7KoaYjSTyvkbUqc')

def count_elements(doc):
    tables = [e for e in doc.elements if isinstance(e, Table)]
    headings = [e for e in doc.elements if isinstance(e, Heading)]
    paragraphs = [e for e in doc.elements if isinstance(e, Paragraph)]
    lists = [e for e in doc.elements if isinstance(e, List)]
    highlights = []
    for elem in doc.elements:
        if isinstance(elem, (Heading, Paragraph)):
            for run in elem.runs():
                if run.highlight_color:
                    highlights.append(run.text[:30])
        elif isinstance(elem, List):
            for item in elem.items:
                for run in item.runs():
                    if run.highlight_color:
                        highlights.append(run.text[:30])
    return {
        'tables': len(tables),
        'headings': len(headings),
        'paragraphs': len(paragraphs),
        'lists': len(lists),
        'highlights': len(highlights)
    }

source_counts = count_elements(source)
corrected_counts = count_elements(corrected)
print('Element comparison (source -> corrected):')
for k in ['tables', 'headings', 'paragraphs', 'lists', 'highlights']:
    match = 'OK' if source_counts[k] == corrected_counts[k] else 'MISMATCH'
    print(f'  {k}: {source_counts[k]} -> {corrected_counts[k]} [{match}]')

source_headings = [e for e in source.elements if isinstance(e, Heading)]
corrected_headings = [e for e in corrected.elements if isinstance(e, Heading)]
print('\nHeading changes (Title Case -> Sentence case):')
count = 0
for i in range(len(source_headings)):
    s_text = source_headings[i].text
    c_text = corrected_headings[i].text
    if s_text != c_text:
        print(f'  "{s_text}" -> "{c_text}"')
        count += 1
        if count >= 8:
            remaining = sum(1 for j in range(i+1, len(source_headings))
                           if source_headings[j].text != corrected_headings[j].text)
            if remaining > 0:
                print(f'  ... ({remaining} more changes)')
            break

source_tables = [e for e in source.elements if isinstance(e, Table)]
corrected_tables = [e for e in corrected.elements if isinstance(e, Table)]
print('\nTable content verification:')
for i, (st, ct) in enumerate(zip(source_tables, corrected_tables)):
    # Check all cells match
    all_match = True
    for row_idx, (sr, cr) in enumerate(zip(st.rows, ct.rows)):
        for col_idx, (sc, cc) in enumerate(zip(sr.cells, cr.cells)):
            if sc.text != cc.text:
                all_match = False
                print(f'  Table {i+1} Cell[{row_idx},{col_idx}] MISMATCH: "{sc.text[:20]}" vs "{cc.text[:20]}"')

    if all_match:
        first_cell = ct.rows[0].cells[0].text if ct.rows else 'N/A'
        second_cell = ct.rows[0].cells[1].text if ct.rows and len(ct.rows[0].cells) > 1 else 'N/A'
        print(f'  Table {i+1}: [{first_cell}] | [{second_cell}] - OK ({len(ct.rows)} rows)')
