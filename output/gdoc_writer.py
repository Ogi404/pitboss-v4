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


def _is_empty_paragraph(element) -> bool:
    """Check if element is an existing blank row (empty paragraph)."""
    return isinstance(element, Paragraph) and not element.text.strip()


def _build_empty_paragraph_requests() -> list[dict]:
    """
    Build requests to insert an empty paragraph at index 1.

    Used for blank_rows insertion between content blocks.
    """
    return [
        {
            'insertText': {
                'location': {'index': 1},
                'text': '\n'  # Single newline = empty paragraph
            }
        },
        {
            'updateParagraphStyle': {
                'range': {'startIndex': 1, 'endIndex': 1},
                'paragraphStyle': {'namedStyleType': 'NORMAL_TEXT'},
                'fields': 'namedStyleType'
            }
        }
    ]


def write_gdoc(
    document: Document,
    title: Optional[str] = None,
    blank_rows: Optional[str] = None,
) -> str:
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
        blank_rows: Blank row handling mode:
            - "required": Insert empty paragraphs between content blocks
              (headings, paragraphs, lists, tables). Idempotent - won't
              double-insert if source already has empty rows. Lists exempt
              (no empty rows between list items).
            - "none": Don't insert blank rows (preserve source as-is)
            - None: Preserve source as-is (same as "none")

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

    # 2. Build content requests (two phases for tables)
    phase1_requests, table_info = _build_content_requests_phase1(document, blank_rows)

    # 3. Execute phase 1 (structure: text, headings, lists, table structures)
    if phase1_requests:
        service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': phase1_requests}
        ).execute()
        logger.info(f"Phase 1: {len(phase1_requests)} requests")

    # 4. If we have tables, populate their cells in phase 2
    if table_info:
        # Read document to get actual table structure indices
        doc_content = service.documents().get(documentId=doc_id).execute()
        phase2_requests = _build_table_content_requests(doc_content, table_info)

        if phase2_requests:
            service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': phase2_requests}
            ).execute()
            logger.info(f"Phase 2 (tables): {len(phase2_requests)} requests")

    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    logger.info(f"Document URL: {url}")
    return url


def _build_content_requests_phase1(
    document: Document,
    blank_rows: Optional[str] = None,
) -> tuple[list[dict], list[Table]]:
    """
    Build phase 1 requests using REVERSE insertion order.

    By inserting elements from last to first at index 1, each new
    insertion pushes previous content down. This avoids index
    calculation errors, especially for tables.

    Tables are inserted as empty structures. Their cell contents are
    populated in phase 2 after reading back the actual indices.

    Args:
        document: The Document to write
        blank_rows: "required" to insert empty paragraphs between blocks,
                   None/"none" to preserve source as-is

    Returns:
        Tuple of (requests, table_list) where table_list contains
        the Table objects in DOCUMENT order for phase 2 population.
    """
    requests = []
    tables = []
    elements = document.elements
    num_elements = len(elements)

    # Process elements in REVERSE order for insertion at index 1
    for i, element in enumerate(reversed(elements)):
        # Original index in document order
        orig_idx = num_elements - 1 - i

        # Step 1: Insert the actual element
        if isinstance(element, Heading):
            reqs = _build_heading_requests_rev(element)
            requests.extend(reqs)
        elif isinstance(element, Paragraph):
            reqs = _build_paragraph_requests_rev(element)
            requests.extend(reqs)
        elif isinstance(element, List):
            reqs = _build_list_requests_rev(element)
            requests.extend(reqs)
        elif isinstance(element, Table):
            # Phase 1: insert table structure only (no cell content)
            reqs = _build_table_structure_requests_rev(element)
            requests.extend(reqs)
            tables.insert(0, element)  # Prepend to maintain document order

        # Step 2: Check if we need to insert empty row BEFORE this element
        # (In reverse insertion, this means inserting AFTER the element request)
        if blank_rows == "required":
            prev_element = elements[orig_idx - 1] if orig_idx > 0 else None
            needs_empty = (
                not _is_empty_paragraph(element) and  # Current isn't already empty
                orig_idx > 0 and                       # Not first element
                not _is_empty_paragraph(prev_element) and  # Prev isn't empty
                # Exempt table-to-table adjacency (corpus: 100% directly adjacent)
                not (isinstance(element, Table) and isinstance(prev_element, Table))
            )
            if needs_empty:
                requests.extend(_build_empty_paragraph_requests())

    return requests, tables


def _build_table_structure_requests_rev(table: Table) -> list[dict]:
    """Build request to insert empty table structure at index 1 (reverse order)."""
    requests = []

    if not table.rows:
        return requests

    num_rows = len(table.rows)
    num_cols = max(len(row.cells) for row in table.rows) if table.rows else 0

    if num_cols == 0:
        return requests

    # Insert empty table structure at index 1
    requests.append({
        'insertTable': {
            'location': {'index': 1},
            'rows': num_rows,
            'columns': num_cols
        }
    })

    return requests


def _build_table_content_requests(doc_content: dict, tables: list[Table]) -> list[dict]:
    """
    Build phase 2 requests: populate table cells with content.

    Reads the actual document structure to find table cell indices,
    then inserts text and formatting into each cell.

    IMPORTANT: Cells are processed in REVERSE INDEX ORDER to avoid
    index shifting issues when inserting text.
    """
    # Collect all cell insertions with their indices
    cell_insertions = []  # [(para_start, our_cell), ...]

    # Find all tables in the document body
    body_content = doc_content.get('body', {}).get('content', [])
    doc_tables = []

    for content_elem in body_content:
        if 'table' in content_elem:
            doc_tables.append(content_elem)

    if len(doc_tables) != len(tables):
        logger.warning(
            f"Table count mismatch: expected {len(tables)}, found {len(doc_tables)}. "
            f"Some tables may not be populated."
        )

    # Collect all cell insertions
    for table_idx, (doc_table, our_table) in enumerate(zip(doc_tables, tables)):
        table_elem = doc_table['table']
        table_rows = table_elem.get('tableRows', [])

        for row_idx, (doc_row, our_row) in enumerate(zip(table_rows, our_table.rows)):
            doc_cells = doc_row.get('tableCells', [])

            for col_idx, (doc_cell, our_cell) in enumerate(zip(doc_cells, our_row.cells)):
                if not our_cell.text:
                    continue

                # Find the paragraph index inside this cell
                cell_content = doc_cell.get('content', [])
                for content_elem in cell_content:
                    if 'paragraph' in content_elem:
                        para = content_elem['paragraph']
                        # Get the start index of the paragraph
                        para_start = para.get('elements', [{}])[0].get('startIndex', 0)

                        if para_start > 0:
                            cell_insertions.append((para_start, our_cell))
                        break  # Only handle first paragraph per cell

    # Sort by index DESCENDING so we insert from end to start
    # This prevents index shifting issues
    cell_insertions.sort(key=lambda x: x[0], reverse=True)

    # Build requests in reverse index order
    requests = []
    for para_start, our_cell in cell_insertions:
        # Insert text at the paragraph start
        requests.append({
            'insertText': {
                'location': {'index': para_start},
                'text': our_cell.text
            }
        })

        cell_end = para_start + len(our_cell.text)

        # Apply preserved paragraph spacing
        spacing_reqs = _build_paragraph_spacing_requests(our_cell, para_start, cell_end)
        requests.extend(spacing_reqs)

        # Apply formatting for cell runs
        for run in our_cell.runs():
            run_reqs = _build_run_formatting_requests(run, para_start)
            requests.extend(run_reqs)

    return requests


def _build_heading_requests_rev(heading: Heading) -> list[dict]:
    """Build requests for a heading element (reverse insertion at index 1)."""
    requests = []
    text = heading.text + '\n'
    start_idx = 1
    end_idx = start_idx + len(text)

    # Insert text at index 1
    requests.append({
        'insertText': {
            'location': {'index': start_idx},
            'text': text
        }
    })

    # IMPORTANT: Remove any inherited bullet styling from list content
    # that was pushed down by this insertion
    requests.append({
        'deleteParagraphBullets': {
            'range': {
                'startIndex': start_idx,
                'endIndex': end_idx - 1  # Exclude the newline
            }
        }
    })

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

    # Apply preserved paragraph spacing
    spacing_reqs = _build_paragraph_spacing_requests(heading, start_idx, end_idx - 1)
    requests.extend(spacing_reqs)

    # Apply any inline formatting from runs
    for run in heading.runs():
        run_reqs = _build_run_formatting_requests(run, start_idx)
        requests.extend(run_reqs)

    return requests


def _build_heading_requests(heading: Heading, start_idx: int) -> tuple[list[dict], int]:
    """Build requests for a heading element (forward insertion - deprecated)."""
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


def _build_paragraph_requests_rev(para: Paragraph) -> list[dict]:
    """Build requests for a paragraph element (reverse insertion at index 1)."""
    requests = []
    text = para.text + '\n'
    start_idx = 1
    end_idx = start_idx + len(text)

    # Insert text at index 1
    requests.append({
        'insertText': {
            'location': {'index': start_idx},
            'text': text
        }
    })

    # For empty paragraphs (just newline), skip formatting operations
    # since there's no text content to format
    if not para.text:
        return requests

    # IMPORTANT: Remove any inherited bullet styling from list content
    # that was pushed down by this insertion
    requests.append({
        'deleteParagraphBullets': {
            'range': {
                'startIndex': start_idx,
                'endIndex': end_idx - 1  # Exclude the newline
            }
        }
    })

    # Explicitly set NORMAL_TEXT style to prevent inheriting
    # heading styles from content being pushed down
    requests.append({
        'updateParagraphStyle': {
            'range': {
                'startIndex': start_idx,
                'endIndex': end_idx - 1  # Exclude the newline
            },
            'paragraphStyle': {
                'namedStyleType': 'NORMAL_TEXT'
            },
            'fields': 'namedStyleType'
        }
    })

    # Apply preserved paragraph spacing
    spacing_reqs = _build_paragraph_spacing_requests(para, start_idx, end_idx - 1)
    requests.extend(spacing_reqs)

    # Apply formatting for each run
    for run in para.runs():
        run_reqs = _build_run_formatting_requests(run, start_idx)
        requests.extend(run_reqs)

    return requests


def _build_paragraph_requests(para: Paragraph, start_idx: int) -> tuple[list[dict], int]:
    """Build requests for a paragraph element (forward insertion - deprecated)."""
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


def _build_list_requests_rev(lst: List) -> list[dict]:
    """Build requests for a list element (reverse insertion at index 1)."""
    requests = []
    start_idx = 1

    # For reverse insertion, we insert ALL list items at once at index 1
    # The items are in order, so we build the combined text
    combined_text = ''
    for item in lst.items:
        combined_text += item.text + '\n'

    # Insert all list item text at index 1
    requests.append({
        'insertText': {
            'location': {'index': start_idx},
            'text': combined_text
        }
    })

    list_end = start_idx + len(combined_text)

    # IMPORTANT: Explicitly set NORMAL_TEXT style first to prevent inheriting
    # heading styles from content being pushed down
    requests.append({
        'updateParagraphStyle': {
            'range': {
                'startIndex': start_idx,
                'endIndex': list_end - 1  # Exclude final newline
            },
            'paragraphStyle': {
                'namedStyleType': 'NORMAL_TEXT'
            },
            'fields': 'namedStyleType'
        }
    })

    # Apply bullet/numbering to all list paragraphs
    bullet_preset = LIST_TYPE_MAP.get(lst.list_type, 'BULLET_DISC_CIRCLE_SQUARE')
    requests.append({
        'createParagraphBullets': {
            'range': {
                'startIndex': start_idx,
                'endIndex': list_end - 1  # Exclude final newline
            },
            'bulletPreset': bullet_preset
        }
    })

    # Apply inline formatting and spacing for each item
    item_start = start_idx
    for item in lst.items:
        item_len = len(item.text)
        item_end = item_start + item_len

        # Apply preserved spacing for this item
        spacing_reqs = _build_paragraph_spacing_requests(item, item_start, item_end)
        requests.extend(spacing_reqs)

        for run in item.runs():
            run_reqs = _build_run_formatting_requests(run, item_start)
            requests.extend(run_reqs)
        item_start += item_len + 1  # +1 for newline

    return requests


def _build_list_requests(lst: List, start_idx: int) -> tuple[list[dict], int]:
    """Build requests for a list element (forward insertion - deprecated)."""
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


def _build_run_formatting_requests(run: TextRun, para_start: int) -> list[dict]:
    """Build updateTextStyle requests for a single run's formatting."""
    requests = []

    # Calculate absolute indices
    run_start = para_start + run.start_offset
    run_end = para_start + run.end_offset

    # Build text style updates
    text_style = {}
    fields = []

    # ALWAYS set bold explicitly to override any inherited styles
    # (especially important for table cells which may inherit bold from headers)
    text_style['bold'] = run.bold
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

    # Preserved font formatting
    if run.font_name:
        text_style['weightedFontFamily'] = {
            'fontFamily': run.font_name,
            'weight': 400  # normal weight
        }
        fields.append('weightedFontFamily')

    if run.font_size_pt is not None:
        text_style['fontSize'] = {
            'magnitude': run.font_size_pt,
            'unit': 'PT'
        }
        fields.append('fontSize')

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


def _build_paragraph_spacing_requests(element, start_idx: int, end_idx: int) -> list[dict]:
    """
    Build updateParagraphStyle requests for preserved spacing.

    Works for Paragraph, Heading, or ListItem elements.
    """
    requests = []

    spacing_style = {}
    spacing_fields = []

    if hasattr(element, 'space_before_pt') and element.space_before_pt is not None:
        spacing_style['spaceAbove'] = {
            'magnitude': element.space_before_pt,
            'unit': 'PT'
        }
        spacing_fields.append('spaceAbove')

    if hasattr(element, 'space_after_pt') and element.space_after_pt is not None:
        spacing_style['spaceBelow'] = {
            'magnitude': element.space_after_pt,
            'unit': 'PT'
        }
        spacing_fields.append('spaceBelow')

    if hasattr(element, 'line_spacing') and element.line_spacing is not None:
        spacing_style['lineSpacing'] = element.line_spacing * 100  # percentage
        spacing_fields.append('lineSpacing')

    if spacing_fields:
        requests.append({
            'updateParagraphStyle': {
                'range': {
                    'startIndex': start_idx,
                    'endIndex': end_idx
                },
                'paragraphStyle': spacing_style,
                'fields': ','.join(spacing_fields)
            }
        })

    return requests


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
