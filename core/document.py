"""
Pitboss v4 - Document Model (Frozen Contract #1)

This module defines the internal representation of a document.
It is one of the three frozen contracts that forms the foundation of the system.

The Document model captures:
- Ordered paragraphs
- Headings with level (H1-H4)
- Logical sections (heading + content)
- Lists (ordered/unordered)
- Tables (rows/cells)
- Character positions/offsets for every element

Design principle: Capture MORE structure than currently needed so future checks
find the structural detail they need already present.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Iterator, Union, Any
from enum import Enum


class HeadingLevel(Enum):
    """Heading hierarchy levels."""
    H1 = 1
    H2 = 2
    H3 = 3
    H4 = 4

    def __lt__(self, other: HeadingLevel) -> bool:
        return self.value < other.value

    def __le__(self, other: HeadingLevel) -> bool:
        return self.value <= other.value


class ListType(Enum):
    """List type enumeration."""
    ORDERED = "ordered"
    UNORDERED = "unordered"


@dataclass
class TextRun:
    """
    A contiguous span of text with inline formatting attributes.

    Runs represent formatting within a text element (paragraph, heading, etc.).
    Each run carries text plus formatting flags (bold, italic, highlight, hyperlink).

    Offsets are RELATIVE to the parent element (0 to len(parent.text)).
    To get absolute document offset: parent.start_offset + run.start_offset
    """
    text: str
    start_offset: int  # Relative offset within parent element (0-based)
    end_offset: int    # Relative offset (exclusive)
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    highlight_color: Optional[str] = None  # e.g., "yellow", "green"
    hyperlink: Optional[str] = None        # URL target
    # Formatting preservation (Optional - populated by readers, used by writers)
    font_name: Optional[str] = None        # e.g., "Arial"
    font_size_pt: Optional[float] = None   # Font size in points

    def __post_init__(self):
        """Validate that end_offset matches text length."""
        expected_end = self.start_offset + len(self.text)
        if self.end_offset != expected_end:
            object.__setattr__(self, 'end_offset', expected_end)

    @property
    def is_formatted(self) -> bool:
        """Check if this run has any formatting."""
        return (
            self.bold or
            self.italic or
            self.underline or
            self.strikethrough or
            self.highlight_color is not None or
            self.hyperlink is not None
        )

    @property
    def is_hyperlink(self) -> bool:
        """Check if this run is a hyperlink."""
        return self.hyperlink is not None

    @property
    def is_highlighted(self) -> bool:
        """Check if this run is highlighted."""
        return self.highlight_color is not None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        result = {
            "text": self.text,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
        }
        if self.bold:
            result["bold"] = True
        if self.italic:
            result["italic"] = True
        if self.underline:
            result["underline"] = True
        if self.strikethrough:
            result["strikethrough"] = True
        if self.highlight_color:
            result["highlight_color"] = self.highlight_color
        if self.hyperlink:
            result["hyperlink"] = self.hyperlink
        if self.font_name:
            result["font_name"] = self.font_name
        if self.font_size_pt is not None:
            result["font_size_pt"] = self.font_size_pt
        return result

    @classmethod
    def from_dict(cls, data: dict) -> TextRun:
        """Deserialize from dictionary."""
        return cls(
            text=data["text"],
            start_offset=data["start_offset"],
            end_offset=data["end_offset"],
            bold=data.get("bold", False),
            italic=data.get("italic", False),
            underline=data.get("underline", False),
            strikethrough=data.get("strikethrough", False),
            highlight_color=data.get("highlight_color"),
            hyperlink=data.get("hyperlink"),
            font_name=data.get("font_name"),
            font_size_pt=data.get("font_size_pt"),
        )


@dataclass(frozen=True)
class TextSpan:
    """
    A contiguous range of text with absolute document positions.

    Immutable to ensure span integrity when passed around.
    """
    text: str
    start_offset: int
    end_offset: int

    def __post_init__(self):
        if self.end_offset != self.start_offset + len(self.text):
            raise ValueError(
                f"TextSpan offset mismatch: end_offset ({self.end_offset}) != "
                f"start_offset ({self.start_offset}) + len(text) ({len(self.text)})"
            )

    def contains_offset(self, offset: int) -> bool:
        """Check if an offset falls within this span."""
        return self.start_offset <= offset < self.end_offset

    def overlaps(self, other: TextSpan) -> bool:
        """Check if this span overlaps with another."""
        return not (self.end_offset <= other.start_offset or
                    other.end_offset <= self.start_offset)

    def __len__(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class Location:
    """
    Precise location within a document for anchoring findings.

    All fields except char range are optional to support different
    granularities (section-level vs character-level findings).

    This is a frozen (immutable) dataclass for safety.
    """
    section_index: Optional[int] = None
    section_title: Optional[str] = None
    paragraph_index: Optional[int] = None
    element_type: Optional[str] = None  # "paragraph", "heading", "list_item", "table_cell"
    start_offset: int = 0
    end_offset: int = 0

    @property
    def char_range(self) -> tuple[int, int]:
        """Return the character range as a tuple."""
        return (self.start_offset, self.end_offset)

    @property
    def span_length(self) -> int:
        """Length of the location span."""
        return self.end_offset - self.start_offset

    def to_dict(self) -> dict:
        """Serialize to dictionary, omitting None values."""
        result = {
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
        }
        if self.section_index is not None:
            result["section_index"] = self.section_index
        if self.section_title is not None:
            result["section_title"] = self.section_title
        if self.paragraph_index is not None:
            result["paragraph_index"] = self.paragraph_index
        if self.element_type is not None:
            result["element_type"] = self.element_type
        return result

    @classmethod
    def from_dict(cls, data: dict) -> Location:
        """Deserialize from dictionary."""
        return cls(
            section_index=data.get("section_index"),
            section_title=data.get("section_title"),
            paragraph_index=data.get("paragraph_index"),
            element_type=data.get("element_type"),
            start_offset=data.get("start_offset", 0),
            end_offset=data.get("end_offset", 0),
        )


@dataclass
class Paragraph:
    """A single paragraph of body text with optional inline formatting runs."""
    text: str
    start_offset: int
    end_offset: int
    _runs: list[TextRun] = field(default_factory=list)
    # Formatting preservation (Optional - populated by readers, used by writers)
    font_name: Optional[str] = None
    font_size_pt: Optional[float] = None
    space_before_pt: Optional[float] = None
    space_after_pt: Optional[float] = None
    line_spacing: Optional[float] = None  # Multiplier, e.g. 1.15

    @property
    def span(self) -> TextSpan:
        """Return this paragraph as a TextSpan."""
        return TextSpan(self.text, self.start_offset, self.end_offset)

    def runs(self) -> list[TextRun]:
        """
        Return formatting runs for this paragraph.

        If no runs were provided, returns a single unformatted run covering
        the entire text (backward compatible with plain-text construction).
        """
        if not self._runs:
            return [TextRun(self.text, 0, len(self.text))]
        return self._runs

    def run_at_offset(self, relative_offset: int) -> Optional[TextRun]:
        """Find the run containing a relative offset within this paragraph."""
        for run in self.runs():
            if run.start_offset <= relative_offset < run.end_offset:
                return run
        return None

    def __post_init__(self):
        # Auto-calculate end_offset if not provided correctly
        expected_end = self.start_offset + len(self.text)
        if self.end_offset != expected_end:
            object.__setattr__(self, 'end_offset', expected_end)


@dataclass
class Heading:
    """A heading element with level and optional inline formatting runs."""
    text: str
    level: HeadingLevel
    start_offset: int
    end_offset: int
    _runs: list[TextRun] = field(default_factory=list)
    # Formatting preservation (Optional - populated by readers, used by writers)
    font_name: Optional[str] = None
    font_size_pt: Optional[float] = None
    space_before_pt: Optional[float] = None
    space_after_pt: Optional[float] = None
    line_spacing: Optional[float] = None

    @property
    def span(self) -> TextSpan:
        """Return this heading as a TextSpan."""
        return TextSpan(self.text, self.start_offset, self.end_offset)

    def runs(self) -> list[TextRun]:
        """Return formatting runs for this heading."""
        if not self._runs:
            return [TextRun(self.text, 0, len(self.text))]
        return self._runs

    def __post_init__(self):
        expected_end = self.start_offset + len(self.text)
        if self.end_offset != expected_end:
            object.__setattr__(self, 'end_offset', expected_end)


@dataclass
class ListItem:
    """A single item in a list with optional inline formatting runs."""
    text: str
    start_offset: int
    end_offset: int
    indent_level: int = 0  # For nested lists (0 = top level)
    _runs: list[TextRun] = field(default_factory=list)
    # Formatting preservation (Optional - populated by readers, used by writers)
    font_name: Optional[str] = None
    font_size_pt: Optional[float] = None
    space_before_pt: Optional[float] = None
    space_after_pt: Optional[float] = None
    line_spacing: Optional[float] = None

    @property
    def span(self) -> TextSpan:
        """Return this list item as a TextSpan."""
        return TextSpan(self.text, self.start_offset, self.end_offset)

    def runs(self) -> list[TextRun]:
        """Return formatting runs for this list item."""
        if not self._runs:
            return [TextRun(self.text, 0, len(self.text))]
        return self._runs

    def __post_init__(self):
        expected_end = self.start_offset + len(self.text)
        if self.end_offset != expected_end:
            object.__setattr__(self, 'end_offset', expected_end)


@dataclass
class List:
    """An ordered or unordered list."""
    list_type: ListType
    items: list[ListItem]
    start_offset: int
    end_offset: int

    @property
    def span(self) -> TextSpan:
        """Return combined text of all items as a TextSpan."""
        full_text = "\n".join(item.text for item in self.items)
        return TextSpan(full_text, self.start_offset, self.end_offset)

    def __len__(self) -> int:
        return len(self.items)


@dataclass
class TableCell:
    """A single cell in a table with optional inline formatting runs."""
    text: str
    start_offset: int
    end_offset: int
    row_index: int
    col_index: int
    is_header: bool = False
    _runs: list[TextRun] = field(default_factory=list)
    # Formatting preservation (Optional - populated by readers, used by writers)
    font_name: Optional[str] = None
    font_size_pt: Optional[float] = None
    space_before_pt: Optional[float] = None
    space_after_pt: Optional[float] = None
    line_spacing: Optional[float] = None

    @property
    def span(self) -> TextSpan:
        """Return this cell as a TextSpan."""
        return TextSpan(self.text, self.start_offset, self.end_offset)

    def runs(self) -> list[TextRun]:
        """Return formatting runs for this table cell."""
        if not self._runs:
            return [TextRun(self.text, 0, len(self.text))]
        return self._runs


@dataclass
class TableRow:
    """A row of cells in a table."""
    cells: list[TableCell]
    is_header_row: bool = False

    @property
    def start_offset(self) -> int:
        """Start offset is the start of the first cell."""
        return self.cells[0].start_offset if self.cells else 0

    @property
    def end_offset(self) -> int:
        """End offset is the end of the last cell."""
        return self.cells[-1].end_offset if self.cells else 0

    def __len__(self) -> int:
        return len(self.cells)


@dataclass
class Table:
    """A table with rows and cells."""
    rows: list[TableRow]
    start_offset: int
    end_offset: int
    caption: Optional[str] = None

    @property
    def num_rows(self) -> int:
        """Number of rows in the table."""
        return len(self.rows)

    @property
    def num_cols(self) -> int:
        """Number of columns (max cells per row)."""
        return max(len(row.cells) for row in self.rows) if self.rows else 0

    def header_row(self) -> Optional[TableRow]:
        """Return the header row if present."""
        for row in self.rows:
            if row.is_header_row:
                return row
        return None


# Union type for any block-level element
BlockElement = Union[Paragraph, Heading, List, Table]


@dataclass
class Section:
    """
    A logical section: a heading plus all content until the next
    heading of same or higher level.

    Sections can be nested (H2 sections within H1 sections).
    """
    heading: Heading
    content: list[BlockElement] = field(default_factory=list)
    subsections: list[Section] = field(default_factory=list)

    @property
    def start_offset(self) -> int:
        """Start offset is the start of the heading."""
        return self.heading.start_offset

    @property
    def end_offset(self) -> int:
        """End offset is the end of the last element or subsection."""
        if self.subsections:
            return self.subsections[-1].end_offset
        elif self.content:
            return self.content[-1].end_offset
        return self.heading.end_offset

    @property
    def title(self) -> str:
        """The heading text of this section."""
        return self.heading.text

    @property
    def level(self) -> HeadingLevel:
        """The heading level of this section."""
        return self.heading.level

    def all_paragraphs(self) -> Iterator[Paragraph]:
        """Yield all paragraphs in this section and subsections."""
        for element in self.content:
            if isinstance(element, Paragraph):
                yield element
        for subsection in self.subsections:
            yield from subsection.all_paragraphs()

    def all_headings(self) -> Iterator[Heading]:
        """Yield all headings in this section (including self)."""
        yield self.heading
        for subsection in self.subsections:
            yield from subsection.all_headings()

    def all_text(self) -> str:
        """Return all text in this section concatenated."""
        parts = [self.heading.text]
        for element in self.content:
            if isinstance(element, Paragraph):
                parts.append(element.text)
            elif isinstance(element, List):
                parts.extend(item.text for item in element.items)
            elif isinstance(element, Table):
                for row in element.rows:
                    parts.extend(cell.text for cell in row.cells)
        for subsection in self.subsections:
            parts.append(subsection.all_text())
        return "\n".join(parts)


@dataclass
class Document:
    """
    The unified internal representation of a document.

    Constructed from parsed Google Docs, DOCX, or other sources.
    Provides traversal, lookup, and span-mapping capabilities.

    This is a frozen contract - the interface is stable.
    """
    # Flat ordered list of all block elements in document order
    elements: list[BlockElement] = field(default_factory=list)

    # Hierarchical section structure (built from elements)
    _sections: list[Section] = field(default_factory=list, repr=False)

    # Document metadata
    title: Optional[str] = None
    source_url: Optional[str] = None
    source_format: Optional[str] = None  # "gdoc", "docx", "html"

    # Total document length in characters
    total_length: int = 0

    # Schema version for future migrations
    schema_version: str = "1.0"

    def __post_init__(self):
        """Build section hierarchy if not provided."""
        if not self._sections and self.elements:
            self._sections = self._build_sections()
        if not self.total_length and self.elements:
            self.total_length = max(e.end_offset for e in self.elements)

    def _build_sections(self) -> list[Section]:
        """
        Build hierarchical section structure from flat elements.

        A section starts at a heading and includes all content until
        the next heading of the same or higher level.
        """
        if not self.elements:
            return []

        sections: list[Section] = []
        section_stack: list[Section] = []
        pending_content: list[BlockElement] = []

        for element in self.elements:
            if isinstance(element, Heading):
                # Assign pending content to the current section
                if section_stack:
                    section_stack[-1].content.extend(pending_content)
                pending_content = []

                # Pop sections of equal or lower level
                while (section_stack and
                       section_stack[-1].level.value >= element.level.value):
                    completed = section_stack.pop()
                    if section_stack:
                        section_stack[-1].subsections.append(completed)
                    else:
                        sections.append(completed)

                # Start new section
                new_section = Section(heading=element)
                section_stack.append(new_section)
            else:
                pending_content.append(element)

        # Finalize: assign remaining content and close all sections
        if section_stack:
            section_stack[-1].content.extend(pending_content)

        while section_stack:
            completed = section_stack.pop()
            if section_stack:
                section_stack[-1].subsections.append(completed)
            else:
                sections.append(completed)

        return sections

    # === Accessor Methods ===

    def headings(self) -> list[Heading]:
        """Return all headings in document order."""
        return [e for e in self.elements if isinstance(e, Heading)]

    def paragraphs(self) -> list[Paragraph]:
        """Return all paragraphs in document order."""
        return [e for e in self.elements if isinstance(e, Paragraph)]

    def lists(self) -> list[List]:
        """Return all lists in document order."""
        return [e for e in self.elements if isinstance(e, List)]

    def tables(self) -> list[Table]:
        """Return all tables in document order."""
        return [e for e in self.elements if isinstance(e, Table)]

    def hyperlinks(self) -> list[tuple[str, str, Location]]:
        """
        Return all hyperlinks in the document.

        Returns:
            List of (anchor_text, url, location) tuples where location
            has absolute document offsets.
        """
        results: list[tuple[str, str, Location]] = []

        def process_runs(element, element_start: int, element_index: int, elem_type: str):
            """Process runs from an element and extract hyperlinks."""
            for run in element.runs():
                if run.hyperlink:
                    abs_start = element_start + run.start_offset
                    abs_end = element_start + run.end_offset
                    loc = Location(
                        paragraph_index=element_index,
                        element_type=elem_type,
                        start_offset=abs_start,
                        end_offset=abs_end,
                    )
                    results.append((run.text, run.hyperlink, loc))

        for idx, element in enumerate(self.elements):
            if isinstance(element, Paragraph):
                process_runs(element, element.start_offset, idx, "paragraph")
            elif isinstance(element, Heading):
                process_runs(element, element.start_offset, idx, "heading")
            elif isinstance(element, List):
                for item in element.items:
                    process_runs(item, item.start_offset, idx, "list_item")
            elif isinstance(element, Table):
                for row in element.rows:
                    for cell in row.cells:
                        process_runs(cell, cell.start_offset, idx, "table_cell")

        return results

    def highlighted_spans(self) -> list[tuple[str, str, Location]]:
        """
        Return all highlighted text spans in the document.

        Returns:
            List of (text, highlight_color, location) tuples where location
            has absolute document offsets.
        """
        results: list[tuple[str, str, Location]] = []

        def process_runs(element, element_start: int, element_index: int, elem_type: str):
            """Process runs from an element and extract highlighted spans."""
            for run in element.runs():
                if run.highlight_color:
                    abs_start = element_start + run.start_offset
                    abs_end = element_start + run.end_offset
                    loc = Location(
                        paragraph_index=element_index,
                        element_type=elem_type,
                        start_offset=abs_start,
                        end_offset=abs_end,
                    )
                    results.append((run.text, run.highlight_color, loc))

        for idx, element in enumerate(self.elements):
            if isinstance(element, Paragraph):
                process_runs(element, element.start_offset, idx, "paragraph")
            elif isinstance(element, Heading):
                process_runs(element, element.start_offset, idx, "heading")
            elif isinstance(element, List):
                for item in element.items:
                    process_runs(item, item.start_offset, idx, "list_item")
            elif isinstance(element, Table):
                for row in element.rows:
                    for cell in row.cells:
                        process_runs(cell, cell.start_offset, idx, "table_cell")

        return results

    def sections(self) -> list[Section]:
        """Return top-level sections."""
        return self._sections

    def all_sections_flat(self) -> Iterator[Section]:
        """Yield all sections including nested, depth-first."""
        def walk(sections: list[Section]) -> Iterator[Section]:
            for section in sections:
                yield section
                yield from walk(section.subsections)
        yield from walk(self._sections)

    def get_element_at_index(self, index: int) -> Optional[BlockElement]:
        """Get element at a specific index."""
        if 0 <= index < len(self.elements):
            return self.elements[index]
        return None

    # === Location Mapping ===

    def element_at_offset(self, offset: int) -> Optional[BlockElement]:
        """Find the element containing a given offset."""
        for element in self.elements:
            if element.start_offset <= offset < element.end_offset:
                return element
        return None

    def element_index_at_offset(self, offset: int) -> Optional[int]:
        """Find the index of the element containing a given offset."""
        for i, element in enumerate(self.elements):
            if element.start_offset <= offset < element.end_offset:
                return i
        return None

    def section_at_offset(self, offset: int) -> Optional[Section]:
        """Find the section containing a given offset."""
        for section in self.all_sections_flat():
            if section.start_offset <= offset < section.end_offset:
                return section
        return None

    def location_at_offset(self, offset: int) -> Location:
        """
        Map an absolute character offset to a Location.

        Returns the most specific location possible (section, paragraph, char range).
        """
        # Find containing element
        element_index = self.element_index_at_offset(offset)
        element = self.element_at_offset(offset)

        # Find containing section
        section_idx = None
        section_title = None
        for idx, section in enumerate(self.all_sections_flat()):
            if section.start_offset <= offset < section.end_offset:
                section_idx = idx
                section_title = section.title
                break

        # Determine element type
        if element is not None:
            if isinstance(element, Paragraph):
                elem_type = "paragraph"
            elif isinstance(element, Heading):
                elem_type = "heading"
            elif isinstance(element, List):
                elem_type = "list"
            elif isinstance(element, Table):
                elem_type = "table"
            else:
                elem_type = "unknown"
        else:
            elem_type = None

        return Location(
            section_index=section_idx,
            section_title=section_title,
            paragraph_index=element_index,
            element_type=elem_type,
            start_offset=offset,
            end_offset=offset + 1,
        )

    def location_for_span(self, start: int, end: int) -> Location:
        """Map a character range to a Location."""
        loc = self.location_at_offset(start)
        return Location(
            section_index=loc.section_index,
            section_title=loc.section_title,
            paragraph_index=loc.paragraph_index,
            element_type=loc.element_type,
            start_offset=start,
            end_offset=end,
        )

    def text_at_location(self, loc: Location) -> str:
        """Extract text for a given location."""
        full = self.full_text()
        return full[loc.start_offset:loc.end_offset]

    def full_text(self) -> str:
        """
        Return the full document text with elements joined by newlines.

        Note: This is a reconstruction; actual offsets are preserved in elements.
        """
        parts = []
        for element in self.elements:
            if isinstance(element, Paragraph):
                parts.append(element.text)
            elif isinstance(element, Heading):
                parts.append(element.text)
            elif isinstance(element, List):
                parts.extend(item.text for item in element.items)
            elif isinstance(element, Table):
                for row in element.rows:
                    parts.extend(cell.text for cell in row.cells)
        return "\n".join(parts)

    # === Construction ===

    @classmethod
    def from_elements(
        cls,
        elements: list[BlockElement],
        title: Optional[str] = None,
        source_url: Optional[str] = None,
        source_format: Optional[str] = None,
    ) -> Document:
        """
        Construct a Document from a list of block elements.

        The standard constructor for parsers (gdoc_reader, docx_reader).
        """
        return cls(
            elements=elements,
            title=title,
            source_url=source_url,
            source_format=source_format,
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary for storage/transmission."""
        def serialize_runs(runs: list[TextRun]) -> list[dict]:
            """Serialize runs, omitting if just a single unformatted run."""
            if len(runs) == 1 and not runs[0].is_formatted:
                return []  # Don't serialize default unformatted run
            return [run.to_dict() for run in runs]

        def serialize_element(elem: BlockElement) -> dict:
            if isinstance(elem, Paragraph):
                result = {
                    "type": "paragraph",
                    "text": elem.text,
                    "start_offset": elem.start_offset,
                    "end_offset": elem.end_offset,
                }
                runs = serialize_runs(elem.runs())
                if runs:
                    result["runs"] = runs
                # Formatting preservation fields
                if elem.font_name:
                    result["font_name"] = elem.font_name
                if elem.font_size_pt is not None:
                    result["font_size_pt"] = elem.font_size_pt
                if elem.space_before_pt is not None:
                    result["space_before_pt"] = elem.space_before_pt
                if elem.space_after_pt is not None:
                    result["space_after_pt"] = elem.space_after_pt
                if elem.line_spacing is not None:
                    result["line_spacing"] = elem.line_spacing
                return result
            elif isinstance(elem, Heading):
                result = {
                    "type": "heading",
                    "text": elem.text,
                    "level": elem.level.value,
                    "start_offset": elem.start_offset,
                    "end_offset": elem.end_offset,
                }
                runs = serialize_runs(elem.runs())
                if runs:
                    result["runs"] = runs
                # Formatting preservation fields
                if elem.font_name:
                    result["font_name"] = elem.font_name
                if elem.font_size_pt is not None:
                    result["font_size_pt"] = elem.font_size_pt
                if elem.space_before_pt is not None:
                    result["space_before_pt"] = elem.space_before_pt
                if elem.space_after_pt is not None:
                    result["space_after_pt"] = elem.space_after_pt
                if elem.line_spacing is not None:
                    result["line_spacing"] = elem.line_spacing
                return result
            elif isinstance(elem, List):
                items_data = []
                for item in elem.items:
                    item_dict = {
                        "text": item.text,
                        "start_offset": item.start_offset,
                        "end_offset": item.end_offset,
                        "indent_level": item.indent_level,
                    }
                    runs = serialize_runs(item.runs())
                    if runs:
                        item_dict["runs"] = runs
                    # Formatting preservation fields for list item
                    if item.font_name:
                        item_dict["font_name"] = item.font_name
                    if item.font_size_pt is not None:
                        item_dict["font_size_pt"] = item.font_size_pt
                    if item.space_before_pt is not None:
                        item_dict["space_before_pt"] = item.space_before_pt
                    if item.space_after_pt is not None:
                        item_dict["space_after_pt"] = item.space_after_pt
                    if item.line_spacing is not None:
                        item_dict["line_spacing"] = item.line_spacing
                    items_data.append(item_dict)
                return {
                    "type": "list",
                    "list_type": elem.list_type.value,
                    "items": items_data,
                    "start_offset": elem.start_offset,
                    "end_offset": elem.end_offset,
                }
            elif isinstance(elem, Table):
                rows_data = []
                for row in elem.rows:
                    cells_data = []
                    for cell in row.cells:
                        cell_dict = {
                            "text": cell.text,
                            "start_offset": cell.start_offset,
                            "end_offset": cell.end_offset,
                            "row_index": cell.row_index,
                            "col_index": cell.col_index,
                            "is_header": cell.is_header,
                        }
                        runs = serialize_runs(cell.runs())
                        if runs:
                            cell_dict["runs"] = runs
                        # Formatting preservation fields for table cell
                        if cell.font_name:
                            cell_dict["font_name"] = cell.font_name
                        if cell.font_size_pt is not None:
                            cell_dict["font_size_pt"] = cell.font_size_pt
                        if cell.space_before_pt is not None:
                            cell_dict["space_before_pt"] = cell.space_before_pt
                        if cell.space_after_pt is not None:
                            cell_dict["space_after_pt"] = cell.space_after_pt
                        if cell.line_spacing is not None:
                            cell_dict["line_spacing"] = cell.line_spacing
                        cells_data.append(cell_dict)
                    rows_data.append({
                        "cells": cells_data,
                        "is_header_row": row.is_header_row,
                    })
                return {
                    "type": "table",
                    "rows": rows_data,
                    "start_offset": elem.start_offset,
                    "end_offset": elem.end_offset,
                    "caption": elem.caption,
                }
            return {}

        return {
            "schema_version": self.schema_version,
            "title": self.title,
            "source_url": self.source_url,
            "source_format": self.source_format,
            "total_length": self.total_length,
            "elements": [serialize_element(e) for e in self.elements],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Document:
        """Deserialize from dictionary."""
        def deserialize_runs(runs_data: list) -> list[TextRun]:
            """Deserialize runs from list of dicts."""
            return [TextRun.from_dict(r) for r in runs_data]

        def deserialize_element(elem_data: dict) -> BlockElement:
            elem_type = elem_data.get("type")

            if elem_type == "paragraph":
                runs = deserialize_runs(elem_data.get("runs", []))
                return Paragraph(
                    text=elem_data["text"],
                    start_offset=elem_data["start_offset"],
                    end_offset=elem_data["end_offset"],
                    _runs=runs,
                    font_name=elem_data.get("font_name"),
                    font_size_pt=elem_data.get("font_size_pt"),
                    space_before_pt=elem_data.get("space_before_pt"),
                    space_after_pt=elem_data.get("space_after_pt"),
                    line_spacing=elem_data.get("line_spacing"),
                )
            elif elem_type == "heading":
                runs = deserialize_runs(elem_data.get("runs", []))
                return Heading(
                    text=elem_data["text"],
                    level=HeadingLevel(elem_data["level"]),
                    start_offset=elem_data["start_offset"],
                    end_offset=elem_data["end_offset"],
                    _runs=runs,
                    font_name=elem_data.get("font_name"),
                    font_size_pt=elem_data.get("font_size_pt"),
                    space_before_pt=elem_data.get("space_before_pt"),
                    space_after_pt=elem_data.get("space_after_pt"),
                    line_spacing=elem_data.get("line_spacing"),
                )
            elif elem_type == "list":
                items = []
                for item in elem_data["items"]:
                    runs = deserialize_runs(item.get("runs", []))
                    items.append(ListItem(
                        text=item["text"],
                        start_offset=item["start_offset"],
                        end_offset=item["end_offset"],
                        indent_level=item.get("indent_level", 0),
                        _runs=runs,
                        font_name=item.get("font_name"),
                        font_size_pt=item.get("font_size_pt"),
                        space_before_pt=item.get("space_before_pt"),
                        space_after_pt=item.get("space_after_pt"),
                        line_spacing=item.get("line_spacing"),
                    ))
                return List(
                    list_type=ListType(elem_data["list_type"]),
                    items=items,
                    start_offset=elem_data["start_offset"],
                    end_offset=elem_data["end_offset"],
                )
            elif elem_type == "table":
                rows = []
                for row_data in elem_data["rows"]:
                    cells = []
                    for cell in row_data["cells"]:
                        runs = deserialize_runs(cell.get("runs", []))
                        cells.append(TableCell(
                            text=cell["text"],
                            start_offset=cell["start_offset"],
                            end_offset=cell["end_offset"],
                            row_index=cell["row_index"],
                            col_index=cell["col_index"],
                            is_header=cell.get("is_header", False),
                            _runs=runs,
                            font_name=cell.get("font_name"),
                            font_size_pt=cell.get("font_size_pt"),
                            space_before_pt=cell.get("space_before_pt"),
                            space_after_pt=cell.get("space_after_pt"),
                            line_spacing=cell.get("line_spacing"),
                        ))
                    rows.append(TableRow(
                        cells=cells,
                        is_header_row=row_data.get("is_header_row", False),
                    ))
                return Table(
                    rows=rows,
                    start_offset=elem_data["start_offset"],
                    end_offset=elem_data["end_offset"],
                    caption=elem_data.get("caption"),
                )

            raise ValueError(f"Unknown element type: {elem_type}")

        elements = [deserialize_element(e) for e in data.get("elements", [])]

        return cls(
            elements=elements,
            title=data.get("title"),
            source_url=data.get("source_url"),
            source_format=data.get("source_format"),
            total_length=data.get("total_length", 0),
            schema_version=data.get("schema_version", "1.0"),
        )

    def __len__(self) -> int:
        """Number of elements in the document."""
        return len(self.elements)
