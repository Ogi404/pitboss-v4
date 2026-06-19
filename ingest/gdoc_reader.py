"""
Pitboss v4 - Google Docs Reader

Reads Google Docs via the Docs API into the Document model.
Produces the SAME Document structure as docx_reader for pipeline compatibility.

Usage:
    from ingest.gdoc_reader import read_gdoc
    doc = read_gdoc("1abc123...")  # Doc ID or URL
"""

from __future__ import annotations
import logging
import re
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
    TableRow,
    TableCell,
    TextRun,
    BlockElement,
)
from ingest.gdoc_auth import get_docs_service, extract_doc_id


logger = logging.getLogger(__name__)


# Heading style mapping (Google Docs named styles)
HEADING_STYLE_MAP = {
    'HEADING_1': HeadingLevel.H1,
    'HEADING_2': HeadingLevel.H2,
    'HEADING_3': HeadingLevel.H3,
    'HEADING_4': HeadingLevel.H4,
    'HEADING_5': HeadingLevel.H4,  # Map H5/H6 to H4
    'HEADING_6': HeadingLevel.H4,
    'TITLE': HeadingLevel.H1,
    'SUBTITLE': HeadingLevel.H2,
}

# Ordered list glyph types
ORDERED_GLYPH_TYPES = {
    'DECIMAL',
    'ZERO_DECIMAL',
    'UPPER_ALPHA',
    'ALPHA',
    'UPPER_ROMAN',
    'ROMAN',
}


def _detect_heading_level(paragraph: dict) -> Optional[HeadingLevel]:
    """Detect heading level from paragraph's named style."""
    para_style = paragraph.get('paragraphStyle', {})
    named_style = para_style.get('namedStyleType', '')
    return HEADING_STYLE_MAP.get(named_style)


def _is_list_item(paragraph: dict) -> bool:
    """Check if paragraph is a list item."""
    return 'bullet' in paragraph


def _get_list_info(paragraph: dict, lists_info: dict) -> tuple[Optional[ListType], int]:
    """
    Get list type and indent level for a list item paragraph.

    Args:
        paragraph: The paragraph dict from Docs API
        lists_info: The document's lists property (for glyph type lookup)

    Returns:
        (list_type, indent_level)
    """
    bullet = paragraph.get('bullet', {})
    list_id = bullet.get('listId')
    nesting_level = bullet.get('nestingLevel', 0)

    if not list_id or list_id not in lists_info:
        return ListType.UNORDERED, nesting_level

    # Get the list properties
    list_props = lists_info[list_id].get('listProperties', {})
    nesting_levels = list_props.get('nestingLevels', [])

    # Get glyph type for this nesting level
    if nesting_level < len(nesting_levels):
        level_props = nesting_levels[nesting_level]
        glyph_type = level_props.get('glyphType', '')

        if glyph_type in ORDERED_GLYPH_TYPES:
            return ListType.ORDERED, nesting_level

    return ListType.UNORDERED, nesting_level


def _map_highlight_color(bg_color: Optional[dict]) -> Optional[str]:
    """
    Map Google Docs backgroundColor RGB to a highlight color name.

    Google Docs uses RGB values (0-1 range).
    Match docx_reader's output format (e.g., "yellow (1)").
    """
    if not bg_color:
        return None

    color = bg_color.get('color', {})
    rgb = color.get('rgbColor', {})

    r = rgb.get('red', 0)
    g = rgb.get('green', 0)
    b = rgb.get('blue', 0)

    # Map common highlight colors
    # Yellow: high R, high G, low B
    if r > 0.8 and g > 0.8 and b < 0.5:
        return "yellow (1)"

    # Bright yellow (Google's default highlight)
    if r > 0.95 and g > 0.95 and b < 0.3:
        return "yellow (1)"

    # Green: low R, high G, low B
    if r < 0.5 and g > 0.7 and b < 0.5:
        return "bright green (4)"

    # Cyan: low R, high G, high B
    if r < 0.5 and g > 0.7 and b > 0.7:
        return "turquoise (3)"

    # Pink/Magenta: high R, low G, high B
    if r > 0.7 and g < 0.5 and b > 0.7:
        return "pink (5)"

    # Red: high R, low G, low B
    if r > 0.7 and g < 0.5 and b < 0.5:
        return "red (6)"

    # Blue: low R, low G, high B
    if r < 0.5 and g < 0.5 and b > 0.7:
        return "blue (9)"

    # Gray: similar R, G, B in mid range
    if 0.3 < r < 0.7 and abs(r - g) < 0.2 and abs(g - b) < 0.2:
        return "gray 25 (16)"

    # If we have any background color, return a generic highlight
    if r > 0 or g > 0 or b > 0:
        # Check if it's white/near-white (not a highlight)
        if r > 0.95 and g > 0.95 and b > 0.95:
            return None
        return "yellow (1)"  # Default to yellow for unknown colors

    return None


def _extract_text_from_paragraph(paragraph: dict) -> str:
    """Extract plain text from a paragraph's elements."""
    text_parts = []
    for element in paragraph.get('elements', []):
        if 'textRun' in element:
            content = element['textRun'].get('content', '')
            text_parts.append(content)
    # Strip trailing whitespace (Google conversion often adds trailing spaces)
    return ''.join(text_parts).rstrip()


def _extract_runs(paragraph: dict, start_offset: int = 0) -> list[TextRun]:
    """
    Extract TextRun objects from a Google Docs paragraph.

    Offsets are RELATIVE to the element (0 to len(text)).
    """
    runs = []
    current_offset = 0

    for element in paragraph.get('elements', []):
        if 'textRun' not in element:
            continue

        text_run = element['textRun']
        content = text_run.get('content', '')

        # Strip trailing newline for offset calculation
        # (Google Docs includes \n at end of paragraphs)
        text = content.rstrip('\n')
        if not text:
            continue

        # Extract text style
        text_style = text_run.get('textStyle', {})

        bold = text_style.get('bold', False)
        italic = text_style.get('italic', False)
        underline = text_style.get('underline', False)
        strikethrough = text_style.get('strikethrough', False)

        # Highlight color
        bg_color = text_style.get('backgroundColor')
        highlight = _map_highlight_color(bg_color)

        # Hyperlink
        link = text_style.get('link', {})
        hyperlink = link.get('url')

        runs.append(TextRun(
            text=text,
            start_offset=current_offset,
            end_offset=current_offset + len(text),
            bold=bold,
            italic=italic,
            underline=underline,
            strikethrough=strikethrough,
            highlight_color=highlight,
            hyperlink=hyperlink,
        ))

        current_offset += len(text)

    return runs


def _process_table(table: dict, current_offset: int) -> tuple[Table, int]:
    """
    Process a Google Docs table into Document model.

    Returns (Table, new_offset).
    """
    table_start = current_offset
    rows = []

    for row_idx, table_row in enumerate(table.get('tableRows', [])):
        cells = []
        is_header_row = row_idx == 0

        for col_idx, table_cell in enumerate(table_row.get('tableCells', [])):
            # Extract text from cell's content
            cell_text_parts = []
            cell_runs = []

            for content_elem in table_cell.get('content', []):
                if 'paragraph' in content_elem:
                    para = content_elem['paragraph']
                    para_text = _extract_text_from_paragraph(para)
                    if para_text:
                        cell_text_parts.append(para_text)
                        # Get runs from first paragraph only (like docx_reader)
                        if not cell_runs:
                            cell_runs = _extract_runs(para, 0)

            cell_text = ' '.join(cell_text_parts).strip()
            cell_start = current_offset
            cell_end = current_offset + len(cell_text)

            cells.append(TableCell(
                text=cell_text,
                start_offset=cell_start,
                end_offset=cell_end,
                row_index=row_idx,
                col_index=col_idx,
                is_header=is_header_row,
                _runs=cell_runs,
            ))

            current_offset = cell_end + 1

        rows.append(TableRow(
            cells=cells,
            is_header_row=is_header_row,
        ))

    table_end = current_offset
    return Table(
        rows=rows,
        start_offset=table_start,
        end_offset=table_end,
    ), current_offset


def read_gdoc(doc_id_or_url: str) -> Document:
    """
    Read a Google Doc into Document model.

    Produces the same Document structure as docx_reader for pipeline compatibility.

    Args:
        doc_id_or_url: Google Doc ID or full URL

    Returns:
        Document with all elements in document order
    """
    # Extract doc ID from URL if needed
    doc_id = extract_doc_id(doc_id_or_url)

    # Fetch document from API
    service = get_docs_service()
    doc = service.documents().get(documentId=doc_id).execute()

    logger.info(f"Reading Google Doc: {doc.get('title')}")

    # Get lists info for determining ordered/unordered
    lists_info = doc.get('lists', {})

    elements: list[BlockElement] = []
    current_offset = 0

    # Track list accumulation (like docx_reader)
    pending_list_items: list[ListItem] = []
    pending_list_type: Optional[ListType] = None
    list_start_offset: int = 0

    def flush_list():
        """Flush accumulated list items to elements."""
        nonlocal pending_list_items, pending_list_type, list_start_offset
        if pending_list_items:
            list_end = pending_list_items[-1].end_offset
            elements.append(List(
                list_type=pending_list_type or ListType.UNORDERED,
                items=pending_list_items,
                start_offset=list_start_offset,
                end_offset=list_end,
            ))
            pending_list_items = []
            pending_list_type = None

    # Process document content
    body = doc.get('body', {})
    content = body.get('content', [])

    for content_elem in content:
        if 'paragraph' in content_elem:
            para = content_elem['paragraph']

            # Extract text
            text = _extract_text_from_paragraph(para)
            if not text:
                # Empty paragraph - flush any pending list
                flush_list()
                continue

            # Calculate offsets
            text_len = len(text)
            start = current_offset
            end = current_offset + text_len

            # Extract formatting runs
            runs = _extract_runs(para, start)

            # Check for heading
            heading_level = _detect_heading_level(para)

            # Check for list item
            is_list = _is_list_item(para)

            if heading_level:
                # Flush any pending list before heading
                flush_list()
                elements.append(Heading(
                    text=text,
                    level=heading_level,
                    start_offset=start,
                    end_offset=end,
                    _runs=runs,
                ))

            elif is_list:
                # Accumulate list items
                list_type, indent_level = _get_list_info(para, lists_info)

                if not pending_list_items:
                    list_start_offset = start
                    pending_list_type = list_type

                pending_list_items.append(ListItem(
                    text=text,
                    start_offset=start,
                    end_offset=end,
                    indent_level=indent_level,
                    _runs=runs,
                ))

            else:
                # Regular paragraph
                flush_list()
                elements.append(Paragraph(
                    text=text,
                    start_offset=start,
                    end_offset=end,
                    _runs=runs,
                ))

            current_offset = end + 1  # +1 for newline separator

        elif 'table' in content_elem:
            # Flush any pending list before table
            flush_list()

            table, current_offset = _process_table(
                content_elem['table'],
                current_offset
            )
            elements.append(table)

        elif 'sectionBreak' in content_elem:
            # Section breaks don't produce elements, just flush lists
            flush_list()

    # Flush any remaining list
    flush_list()

    return Document.from_elements(
        elements=elements,
        title=doc.get('title'),
        source_url=f"https://docs.google.com/document/d/{doc_id}",
        source_format="gdoc",
    )


def read_gdoc_raw(doc_id_or_url: str) -> dict:
    """
    Read a Google Doc and return the raw API response.

    Useful for debugging and exploring the document structure.
    """
    doc_id = extract_doc_id(doc_id_or_url)
    service = get_docs_service()
    return service.documents().get(documentId=doc_id).execute()
