"""
Pitboss v4 - DOCX Writer

Writes Document objects back to .docx files with formatting preserved.
This is the inverse of ingest/docx_reader.py.
"""

from __future__ import annotations
from pathlib import Path
import logging

from docx import Document as DocxDocument
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

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


logger = logging.getLogger(__name__)


# Map highlight color names to Word highlight constants
HIGHLIGHT_MAP = {
    'yellow': WD_COLOR_INDEX.YELLOW,
    'bright green': WD_COLOR_INDEX.BRIGHT_GREEN,
    'green': WD_COLOR_INDEX.BRIGHT_GREEN,
    'turquoise': WD_COLOR_INDEX.TURQUOISE,
    'cyan': WD_COLOR_INDEX.TURQUOISE,
    'pink': WD_COLOR_INDEX.PINK,
    'magenta': WD_COLOR_INDEX.PINK,
    'blue': WD_COLOR_INDEX.BLUE,
    'red': WD_COLOR_INDEX.RED,
    'dark blue': WD_COLOR_INDEX.DARK_BLUE,
    'teal': WD_COLOR_INDEX.TEAL,
    'dark red': WD_COLOR_INDEX.DARK_RED,
    'dark yellow': WD_COLOR_INDEX.DARK_YELLOW,
    'gray': WD_COLOR_INDEX.GRAY_25,
    'gray 25': WD_COLOR_INDEX.GRAY_25,
    'gray 50': WD_COLOR_INDEX.GRAY_50,
}

# Map heading levels to Word styles
HEADING_STYLES = {
    HeadingLevel.H1: 'Heading 1',
    HeadingLevel.H2: 'Heading 2',
    HeadingLevel.H3: 'Heading 3',
    HeadingLevel.H4: 'Heading 4',
}


def write_docx(document: Document, output_path: Path) -> None:
    """
    Write a Document object to a .docx file.

    Preserves:
    - Paragraph structure
    - Heading levels (H1-H4)
    - Lists (ordered/unordered)
    - Tables
    - Inline formatting (bold, italic, underline, strikethrough)
    - Highlights
    - Hyperlinks

    Args:
        document: The Document to write
        output_path: Path for the output .docx file
    """
    doc = DocxDocument()

    for element in document.elements:
        if isinstance(element, Heading):
            _write_heading(doc, element)
        elif isinstance(element, Paragraph):
            _write_paragraph(doc, element)
        elif isinstance(element, List):
            _write_list(doc, element)
        elif isinstance(element, Table):
            _write_table(doc, element)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc.save(str(output_path))
    logger.info(f"Wrote document to {output_path}")


def _write_heading(doc: DocxDocument, heading: Heading) -> None:
    """Write a heading element."""
    style = HEADING_STYLES.get(heading.level, 'Heading 1')

    # Add heading with style
    para = doc.add_heading(level=heading.level.value)
    para.clear()  # Remove default run

    # Add formatted runs
    _add_runs_to_paragraph(para, heading.runs())


def _write_paragraph(doc: DocxDocument, paragraph: Paragraph) -> None:
    """Write a paragraph element."""
    para = doc.add_paragraph()
    _add_runs_to_paragraph(para, paragraph.runs())


def _write_list(doc: DocxDocument, lst: List) -> None:
    """Write a list element."""
    style = 'List Number' if lst.list_type == ListType.ORDERED else 'List Bullet'

    for item in lst.items:
        para = doc.add_paragraph(style=style)
        _add_runs_to_paragraph(para, item.runs())


def _write_table(doc: DocxDocument, table: Table) -> None:
    """Write a table element."""
    if not table.rows:
        return

    # Create table with appropriate dimensions
    num_rows = len(table.rows)
    num_cols = max(len(row.cells) for row in table.rows) if table.rows else 0

    if num_cols == 0:
        return

    docx_table = doc.add_table(rows=num_rows, cols=num_cols)
    docx_table.style = 'Table Grid'

    for row_idx, row in enumerate(table.rows):
        for col_idx, cell in enumerate(row.cells):
            docx_cell = docx_table.cell(row_idx, col_idx)

            # Clear default paragraph and add our content
            if docx_cell.paragraphs:
                para = docx_cell.paragraphs[0]
                para.clear()
            else:
                para = docx_cell.add_paragraph()

            _add_runs_to_paragraph(para, cell.runs())


def _add_runs_to_paragraph(para, runs: list[TextRun]) -> None:
    """Add formatted TextRuns to a paragraph."""
    for run in runs:
        if run.hyperlink:
            # Hyperlinks need special handling
            _add_hyperlink(para, run)
        else:
            _add_regular_run(para, run)


def _add_regular_run(para, text_run: TextRun) -> None:
    """Add a regular (non-hyperlink) run with formatting."""
    docx_run = para.add_run(text_run.text)

    # Apply formatting
    if text_run.bold:
        docx_run.bold = True
    if text_run.italic:
        docx_run.italic = True
    if text_run.underline:
        docx_run.underline = True
    if text_run.strikethrough:
        docx_run.font.strike = True

    # Apply highlight
    if text_run.highlight_color:
        color_name = text_run.highlight_color.lower()
        highlight = HIGHLIGHT_MAP.get(color_name)
        if highlight:
            docx_run.font.highlight_color = highlight
        else:
            # Default to yellow if unknown color
            docx_run.font.highlight_color = WD_COLOR_INDEX.YELLOW


def _add_hyperlink(para, text_run: TextRun) -> None:
    """
    Add a hyperlink run to a paragraph.

    Hyperlinks in OOXML require direct XML manipulation.
    """
    # Get the paragraph's part to access relationships
    part = para.part

    # Create relationship for the hyperlink
    r_id = part.relate_to(
        text_run.hyperlink,
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink',
        is_external=True,
    )

    # Create hyperlink element
    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('r:id'), r_id)

    # Create run element inside hyperlink
    new_run = OxmlElement('w:r')

    # Add run properties
    rPr = OxmlElement('w:rPr')

    # Hyperlink styling (blue, underlined)
    color = OxmlElement('w:color')
    color.set(qn('w:val'), '0000FF')  # Blue
    rPr.append(color)

    underline = OxmlElement('w:u')
    underline.set(qn('w:val'), 'single')
    rPr.append(underline)

    # Add other formatting
    if text_run.bold:
        bold = OxmlElement('w:b')
        rPr.append(bold)

    if text_run.italic:
        italic = OxmlElement('w:i')
        rPr.append(italic)

    if text_run.strikethrough:
        strike = OxmlElement('w:strike')
        rPr.append(strike)

    if text_run.highlight_color:
        highlight = OxmlElement('w:highlight')
        color_name = text_run.highlight_color.lower()
        # Word uses specific color names
        hl_val = _get_word_highlight_value(color_name)
        highlight.set(qn('w:val'), hl_val)
        rPr.append(highlight)

    new_run.append(rPr)

    # Add text element
    text_elem = OxmlElement('w:t')
    text_elem.text = text_run.text

    # Preserve whitespace
    text_elem.set(qn('xml:space'), 'preserve')

    new_run.append(text_elem)
    hyperlink.append(new_run)

    # Append hyperlink to paragraph
    para._p.append(hyperlink)


def _get_word_highlight_value(color_name: str) -> str:
    """Map color name to Word highlight value string."""
    mapping = {
        'yellow': 'yellow',
        'bright green': 'green',
        'green': 'green',
        'turquoise': 'cyan',
        'cyan': 'cyan',
        'pink': 'magenta',
        'magenta': 'magenta',
        'blue': 'blue',
        'red': 'red',
        'dark blue': 'darkBlue',
        'teal': 'darkCyan',
        'dark red': 'darkRed',
        'dark yellow': 'darkYellow',
        'gray': 'lightGray',
        'gray 25': 'lightGray',
        'gray 50': 'darkGray',
    }
    return mapping.get(color_name, 'yellow')


def write_docx_simple(text: str, output_path: Path) -> None:
    """
    Write plain text to a .docx file.

    Simple utility for testing or when full Document structure isn't needed.
    Each line becomes a paragraph.
    """
    doc = DocxDocument()

    for line in text.split('\n'):
        if line.strip():
            doc.add_paragraph(line)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
