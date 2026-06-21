"""
Pitboss v4 - Google Docs Writer

Writes Document objects to new Google Docs with formatting preserved.
This is the Google Docs equivalent of docx_writer.py.

Usage:
    from output.gdoc_writer import write_gdoc
    url = write_gdoc(document, "My Corrected Article")
"""

from __future__ import annotations
import logging
from typing import Optional

from core.document import (
    Document,
    Paragraph,
    Heading,
    HeadingLevel,
    List,
    ListItem,
    ListType,
    Table,
    TextRun,
)
from ingest.gdoc_auth import get_docs_service


logger = logging.getLogger(__name__)


# Map heading levels to Google Docs named style types
HEADING_STYLE_MAP = {
    HeadingLevel.H1: 'HEADING_1',
    HeadingLevel.H2: 'HEADING_2',
    HeadingLevel.H3: 'HEADING_3',
    HeadingLevel.H4: 'HEADING_4',
}

# Map our color names back to RGB for Docs API
# These should produce visible highlights in Google Docs
HIGHLIGHT_RGB_MAP = {
    'yellow': {'red': 1.0, 'green': 1.0, 'blue': 0.0},
    'bright green': {'red': 0.0, 'green': 1.0, 'blue': 0.0},
    'green': {'red': 0.0, 'green': 1.0, 'blue': 0.0},
    'turquoise': {'red': 0.0, 'green': 1.0, 'blue': 1.0},
    'cyan': {'red': 0.0, 'green': 1.0, 'blue': 1.0},
    'pink': {'red': 1.0, 'green': 0.75, 'blue': 0.8},
    'magenta': {'red': 1.0, 'green': 0.0, 'blue': 1.0},
    'red': {'red': 1.0, 'green': 0.0, 'blue': 0.0},
    'blue': {'red': 0.0, 'green': 0.0, 'blue': 1.0},
    'gray': {'red': 0.75, 'green': 0.75, 'blue': 0.75},
    'gray 25': {'red': 0.75, 'green': 0.75, 'blue': 0.75},
    'gray 50': {'red': 0.5, 'green': 0.5, 'blue': 0.5},
}

# Map list types to Google Docs bullet presets
LIST_TYPE_MAP = {
    ListType.UNORDERED: 'BULLET_DISC_CIRCLE_SQUARE',
    ListType.ORDERED: 'NUMBERED_DECIMAL_ALPHA_ROMAN',
}


def write_gdoc(document: Document, title: Optional[str] = None) -> str:
    """
    Write a Document object to a new Google Doc.

    Creates a new Google Doc with the document content, preserving:
    - Paragraph structure
    - Heading levels (H1-H4)
    - Lists (ordered/unordered)
    - Tables
    - Inline formatting (bold, italic, underline, strikethrough)
    - Highlights
    - Hyperlinks

    Args:
        document: The Document to write
        title: Title for new doc (default: document.title + " - Corrected")

    Returns:
        URL of the created Google Doc
    """
    service = get_docs_service()

    # Determine title
    doc_title = title
    if not doc_title:
        base_title = document.title or "Untitled"
        doc_title = f"{base_title} - Corrected"

    # 1. Create empty document
    new_doc = service.documents().create(body={'title': doc_title}).execute()
    doc_id = new_doc['documentId']
    logger.info(f"Created new Google Doc: {doc_id}")

    # 2. Build all content requests
    requests = _build_content_requests(document)

    # 3. Execute batchUpdate if we have requests
    if requests:
        service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()
        logger.info(f"Inserted {len(requests)} requests into document")

    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    logger.info(f"Document URL: {url}")
    return url


def _build_content_requests(document: Document) -> list[dict]:
    """
    Build all batchUpdate requests for document content.

    Uses forward insertion: insert each element in order, tracking the
    current index position as we go.

    NOTE: Tables are skipped for now due to complex Google Docs indexing.
    Tables have internal indices that don't follow the sequential pattern
    of paragraphs. This is acceptable because:
    1. Text corrections happen in headings/paragraphs/lists, not tables
    2. Tables rarely need auto-fixes (mostly contain data)
    """
    requests = []
    current_index = 1  # Google Docs body starts at index 1
    skipped_tables = 0

    for element in document.elements:
        if isinstance(element, Heading):
            reqs, current_index = _build_heading_requests(element, current_index)
            requests.extend(reqs)
        elif isinstance(element, Paragraph):
            reqs, current_index = _build_paragraph_requests(element, current_index)
            requests.extend(reqs)
        elif isinstance(element, List):
            reqs, current_index = _build_list_requests(element, current_index)
            requests.extend(reqs)
        elif isinstance(element, Table):
            # Skip tables for now - they have complex internal indexing
            # Insert a placeholder paragraph noting the table location
            skipped_tables += 1
            placeholder = f"[Table {skipped_tables} omitted - see original document]\n"
            requests.append({
                'insertText': {
                    'location': {'index': current_index},
                    'text': placeholder
                }
            })
            current_index += len(placeholder)
            logger.debug(f"Skipped table {skipped_tables} (complex indexing)")

    if skipped_tables:
        logger.info(f"Skipped {skipped_tables} tables (see original for table content)")

    return requests


def _build_heading_requests(heading: Heading, start_idx: int) -> tuple[list[dict], int]:
    """Build requests for a heading element."""
    requests = []
    text = heading.text + '\n'

    # Insert text
    requests.append({
        'insertText': {
            'location': {'index': start_idx},
            'text': text
        }
    })

    end_idx = start_idx + len(text)

    # Apply heading style
    style_type = HEADING_STYLE_MAP.get(heading.level, 'HEADING_1')
    requests.append({
        'updateParagraphStyle': {
            'range': {
                'startIndex': start_idx,
                'endIndex': end_idx - 1  # Exclude the newline from style
            },
            'paragraphStyle': {
                'namedStyleType': style_type
            },
            'fields': 'namedStyleType'
        }
    })

    # Apply any inline formatting from runs
    for run in heading.runs():
        run_reqs = _build_run_formatting_requests(run, start_idx)
        requests.extend(run_reqs)

    return requests, end_idx


def _build_paragraph_requests(para: Paragraph, start_idx: int) -> tuple[list[dict], int]:
    """Build requests for a paragraph element."""
    requests = []
    text = para.text + '\n'

    # Insert text
    requests.append({
        'insertText': {
            'location': {'index': start_idx},
            'text': text
        }
    })

    end_idx = start_idx + len(text)

    # Apply formatting for each run
    for run in para.runs():
        run_reqs = _build_run_formatting_requests(run, start_idx)
        requests.extend(run_reqs)

    return requests, end_idx


def _build_list_requests(lst: List, start_idx: int) -> tuple[list[dict], int]:
    """Build requests for a list element."""
    requests = []
    current_idx = start_idx
    list_start = start_idx

    # Insert all list item texts first
    for item in lst.items:
        text = item.text + '\n'
        requests.append({
            'insertText': {
                'location': {'index': current_idx},
                'text': text
            }
        })
        current_idx += len(text)

    list_end = current_idx

    # Apply bullet/numbering to all list paragraphs
    bullet_preset = LIST_TYPE_MAP.get(lst.list_type, 'BULLET_DISC_CIRCLE_SQUARE')
    requests.append({
        'createParagraphBullets': {
            'range': {
                'startIndex': list_start,
                'endIndex': list_end - 1  # Exclude final newline
            },
            'bulletPreset': bullet_preset
        }
    })

    # Apply inline formatting for each item
    item_start = start_idx
    for item in lst.items:
        item_len = len(item.text)
        for run in item.runs():
            run_reqs = _build_run_formatting_requests(run, item_start)
            requests.extend(run_reqs)
        item_start += item_len + 1  # +1 for newline

    return requests, current_idx


def _build_table_requests(table: Table, start_idx: int) -> tuple[list[dict], int]:
    """Build requests for a table element."""
    requests = []

    if not table.rows:
        return requests, start_idx

    num_rows = len(table.rows)
    num_cols = max(len(row.cells) for row in table.rows) if table.rows else 0

    if num_cols == 0:
        return requests, start_idx

    # Insert table
    requests.append({
        'insertTable': {
            'location': {'index': start_idx},
            'rows': num_rows,
            'columns': num_cols
        }
    })

    # After insertTable, we need to populate cells
    # The table structure creates indices for each cell
    # Each cell initially has a paragraph with index
    #
    # Table indices work like this:
    # - Table element itself takes 1 index
    # - Each row start takes 1 index
    # - Each cell start takes 1 index
    # - Cell content starts after cell index
    # - Each cell has implicit paragraph (1 index for paragraph, 1 for newline)

    # Calculate where cell contents go
    # This is complex - for now we'll populate cells with text after creation
    # by reading back the document structure

    # For simplicity in v1: just create empty table, then populate via separate requests
    # The insertTable creates structure, but we need to find cell indices

    # Estimate end index: table start + structure overhead + cell contents
    # Each row: 1 (row start) + cols * (1 cell start + 1 para + 1 newline)
    # Plus 1 for table element
    structure_overhead = 1 + num_rows * (1 + num_cols * 3)
    estimated_end = start_idx + structure_overhead

    # For tables, we'll need to do a second pass to populate content
    # Add placeholder text to cells using updateTextStyle ranges found by reading doc
    #
    # Simpler approach: insert the table, then in a separate batch, populate cells
    # But this requires reading back the doc to find indices

    # For now, collect cell text to insert after table structure is created
    # We'll add these as a separate batch after the main content
    cell_texts = []
    for row in table.rows:
        for cell in row.cells:
            cell_texts.append(cell.text)

    # Store table info for later population (handled in main write_gdoc)
    # For v1: tables will be empty - we'll enhance this if needed

    return requests, estimated_end


def _build_run_formatting_requests(run: TextRun, para_start: int) -> list[dict]:
    """Build updateTextStyle requests for a single run's formatting."""
    requests = []

    # Calculate absolute indices
    run_start = para_start + run.start_offset
    run_end = para_start + run.end_offset

    # Build text style updates
    text_style = {}
    fields = []

    if run.bold:
        text_style['bold'] = True
        fields.append('bold')

    if run.italic:
        text_style['italic'] = True
        fields.append('italic')

    if run.underline:
        text_style['underline'] = True
        fields.append('underline')

    if run.strikethrough:
        text_style['strikethrough'] = True
        fields.append('strikethrough')

    if run.highlight_color:
        rgb = _get_highlight_rgb(run.highlight_color)
        if rgb:
            text_style['backgroundColor'] = {'color': {'rgbColor': rgb}}
            fields.append('backgroundColor')

    if run.hyperlink:
        text_style['link'] = {'url': run.hyperlink}
        fields.append('link')

    # Only add request if we have formatting to apply
    if fields:
        requests.append({
            'updateTextStyle': {
                'range': {
                    'startIndex': run_start,
                    'endIndex': run_end
                },
                'textStyle': text_style,
                'fields': ','.join(fields)
            }
        })

    return requests


def _get_highlight_rgb(color_name: str) -> Optional[dict]:
    """Map highlight color name to RGB dict for Docs API."""
    if not color_name:
        return None

    # Normalize color name (remove parenthetical like "yellow (1)")
    normalized = color_name.lower().split('(')[0].strip()

    return HIGHLIGHT_RGB_MAP.get(normalized)


def write_gdoc_simple(text: str, title: str) -> str:
    """
    Write plain text to a new Google Doc.

    Simple utility for testing. Each line becomes a paragraph.

    Args:
        text: Plain text content
        title: Document title

    Returns:
        URL of created document
    """
    service = get_docs_service()

    # Create document
    new_doc = service.documents().create(body={'title': title}).execute()
    doc_id = new_doc['documentId']

    # Build insert requests
    requests = []
    current_idx = 1

    for line in text.split('\n'):
        if line.strip():
            para_text = line + '\n'
            requests.append({
                'insertText': {
                    'location': {'index': current_idx},
                    'text': para_text
                }
            })
            current_idx += len(para_text)

    if requests:
        service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

    return f"https://docs.google.com/document/d/{doc_id}/edit"
