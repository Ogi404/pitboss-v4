"""
Tests for core/document.py - The Document Model (Frozen Contract #1)

Tests:
- Build a Document from sample structured input
- Assert sections/headings/paragraphs resolve correctly
- Assert a text span maps back to the right location
"""

import pytest
from core.document import (
    Document,
    Location,
    TextSpan,
    TextRun,
    Paragraph,
    Heading,
    HeadingLevel,
    List,
    ListItem,
    ListType,
    Table,
    TableRow,
    TableCell,
    Section,
)


class TestTextSpan:
    """Tests for TextSpan dataclass."""

    def test_text_span_creation(self):
        """Test basic TextSpan creation."""
        span = TextSpan("hello", 0, 5)
        assert span.text == "hello"
        assert span.start_offset == 0
        assert span.end_offset == 5
        assert len(span) == 5

    def test_text_span_offset_validation(self):
        """Test that TextSpan validates offsets match text length."""
        with pytest.raises(ValueError):
            TextSpan("hello", 0, 10)  # end_offset != start_offset + len(text)

    def test_text_span_contains_offset(self):
        """Test contains_offset method."""
        span = TextSpan("hello", 10, 15)
        assert span.contains_offset(10)
        assert span.contains_offset(12)
        assert span.contains_offset(14)
        assert not span.contains_offset(9)
        assert not span.contains_offset(15)  # exclusive end

    def test_text_span_overlaps(self):
        """Test overlaps method."""
        span1 = TextSpan("hello", 0, 5)
        span2 = TextSpan("world", 3, 8)
        span3 = TextSpan("other", 10, 15)

        assert span1.overlaps(span2)
        assert span2.overlaps(span1)
        assert not span1.overlaps(span3)
        assert not span3.overlaps(span1)

    def test_text_span_is_frozen(self):
        """Test that TextSpan is immutable."""
        span = TextSpan("hello", 0, 5)
        with pytest.raises(Exception):  # FrozenInstanceError
            span.text = "world"


class TestLocation:
    """Tests for Location dataclass."""

    def test_location_creation(self):
        """Test basic Location creation."""
        loc = Location(
            section_index=0,
            section_title="Introduction",
            paragraph_index=1,
            element_type="paragraph",
            start_offset=10,
            end_offset=50,
        )
        assert loc.section_index == 0
        assert loc.section_title == "Introduction"
        assert loc.paragraph_index == 1
        assert loc.element_type == "paragraph"
        assert loc.start_offset == 10
        assert loc.end_offset == 50

    def test_location_char_range(self):
        """Test char_range property."""
        loc = Location(start_offset=10, end_offset=50)
        assert loc.char_range == (10, 50)

    def test_location_span_length(self):
        """Test span_length property."""
        loc = Location(start_offset=10, end_offset=50)
        assert loc.span_length == 40

    def test_location_to_dict(self):
        """Test serialization to dictionary."""
        loc = Location(
            section_index=0,
            section_title="Intro",
            start_offset=10,
            end_offset=50,
        )
        data = loc.to_dict()
        assert data["section_index"] == 0
        assert data["section_title"] == "Intro"
        assert data["start_offset"] == 10
        assert data["end_offset"] == 50
        assert "paragraph_index" not in data  # None values omitted

    def test_location_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "section_index": 0,
            "start_offset": 10,
            "end_offset": 50,
        }
        loc = Location.from_dict(data)
        assert loc.section_index == 0
        assert loc.start_offset == 10
        assert loc.end_offset == 50
        assert loc.section_title is None

    def test_location_is_frozen(self):
        """Test that Location is immutable."""
        loc = Location(start_offset=0, end_offset=10)
        with pytest.raises(Exception):
            loc.start_offset = 5


class TestParagraph:
    """Tests for Paragraph element."""

    def test_paragraph_creation(self):
        """Test basic Paragraph creation."""
        para = Paragraph("Hello world.", 0, 12)
        assert para.text == "Hello world."
        assert para.start_offset == 0
        assert para.end_offset == 12

    def test_paragraph_span(self):
        """Test span property."""
        para = Paragraph("Hello world.", 0, 12)
        span = para.span
        assert span.text == "Hello world."
        assert span.start_offset == 0
        assert span.end_offset == 12


class TestHeading:
    """Tests for Heading element."""

    def test_heading_creation(self):
        """Test basic Heading creation."""
        heading = Heading("Introduction", HeadingLevel.H1, 0, 12)
        assert heading.text == "Introduction"
        assert heading.level == HeadingLevel.H1
        assert heading.start_offset == 0
        assert heading.end_offset == 12

    def test_heading_levels_comparable(self):
        """Test that HeadingLevel can be compared."""
        assert HeadingLevel.H1 < HeadingLevel.H2
        assert HeadingLevel.H2 < HeadingLevel.H3
        assert HeadingLevel.H1 <= HeadingLevel.H1


class TestList:
    """Tests for List element."""

    def test_list_creation(self):
        """Test basic List creation."""
        items = [
            ListItem("Item 1", 0, 6),
            ListItem("Item 2", 7, 13),
        ]
        lst = List(ListType.UNORDERED, items, 0, 13)
        assert lst.list_type == ListType.UNORDERED
        assert len(lst) == 2
        assert lst.items[0].text == "Item 1"

    def test_list_item_indent_level(self):
        """Test nested list items."""
        item = ListItem("Nested item", 0, 11, indent_level=1)
        assert item.indent_level == 1


class TestTable:
    """Tests for Table element."""

    def test_table_creation(self):
        """Test basic Table creation."""
        cells = [
            TableCell("Header 1", 0, 8, 0, 0, is_header=True),
            TableCell("Header 2", 9, 17, 0, 1, is_header=True),
        ]
        row = TableRow(cells, is_header_row=True)
        table = Table([row], 0, 17)

        assert table.num_rows == 1
        assert table.num_cols == 2
        assert table.header_row() is not None
        assert table.header_row().is_header_row


class TestSection:
    """Tests for Section structure."""

    def test_section_creation(self):
        """Test basic Section creation."""
        heading = Heading("Chapter 1", HeadingLevel.H1, 0, 9)
        content = [Paragraph("First paragraph.", 10, 26)]
        section = Section(heading, content)

        assert section.title == "Chapter 1"
        assert section.level == HeadingLevel.H1
        assert section.start_offset == 0
        assert section.end_offset == 26

    def test_section_all_paragraphs(self):
        """Test all_paragraphs generator."""
        heading = Heading("Main", HeadingLevel.H1, 0, 4)
        para1 = Paragraph("Para 1", 5, 11)
        para2 = Paragraph("Para 2", 12, 18)
        section = Section(heading, [para1, para2])

        paragraphs = list(section.all_paragraphs())
        assert len(paragraphs) == 2
        assert paragraphs[0].text == "Para 1"
        assert paragraphs[1].text == "Para 2"


class TestDocument:
    """Tests for Document model."""

    def test_document_from_elements(self):
        """Test Document construction from elements."""
        elements = [
            Heading("Title", HeadingLevel.H1, 0, 5),
            Paragraph("Introduction paragraph.", 6, 29),
            Heading("Section 1", HeadingLevel.H2, 30, 39),
            Paragraph("Section content.", 40, 56),
        ]
        doc = Document.from_elements(elements, title="Test Document")

        assert doc.title == "Test Document"
        assert len(doc) == 4

    def test_document_headings_accessor(self):
        """Test headings() accessor."""
        elements = [
            Heading("Title", HeadingLevel.H1, 0, 5),
            Paragraph("Content.", 6, 14),
            Heading("Section", HeadingLevel.H2, 15, 22),
        ]
        doc = Document.from_elements(elements)

        headings = doc.headings()
        assert len(headings) == 2
        assert headings[0].text == "Title"
        assert headings[1].text == "Section"

    def test_document_paragraphs_accessor(self):
        """Test paragraphs() accessor."""
        elements = [
            Heading("Title", HeadingLevel.H1, 0, 5),
            Paragraph("Para 1.", 6, 13),
            Paragraph("Para 2.", 14, 21),
        ]
        doc = Document.from_elements(elements)

        paragraphs = doc.paragraphs()
        assert len(paragraphs) == 2
        assert paragraphs[0].text == "Para 1."

    def test_document_sections_build(self):
        """Test automatic section hierarchy building."""
        elements = [
            Heading("Chapter 1", HeadingLevel.H1, 0, 9),
            Paragraph("Chapter intro.", 10, 24),
            Heading("Section 1.1", HeadingLevel.H2, 25, 36),
            Paragraph("Section content.", 37, 53),
            Heading("Chapter 2", HeadingLevel.H1, 54, 63),
            Paragraph("Chapter 2 content.", 64, 82),
        ]
        doc = Document.from_elements(elements)

        sections = doc.sections()
        assert len(sections) == 2  # Two H1 sections

        # First section has a subsection
        assert sections[0].title == "Chapter 1"
        assert len(sections[0].subsections) == 1
        assert sections[0].subsections[0].title == "Section 1.1"

        # Second section has no subsections
        assert sections[1].title == "Chapter 2"
        assert len(sections[1].subsections) == 0

    def test_document_all_sections_flat(self):
        """Test all_sections_flat generator."""
        elements = [
            Heading("H1", HeadingLevel.H1, 0, 2),
            Heading("H2", HeadingLevel.H2, 3, 5),
            Heading("H3", HeadingLevel.H3, 6, 8),
        ]
        doc = Document.from_elements(elements)

        all_sections = list(doc.all_sections_flat())
        assert len(all_sections) == 3
        assert all_sections[0].title == "H1"
        assert all_sections[1].title == "H2"
        assert all_sections[2].title == "H3"

    def test_document_location_at_offset(self):
        """Test location_at_offset mapping."""
        elements = [
            Heading("Title", HeadingLevel.H1, 0, 5),
            Paragraph("Hello world.", 6, 18),
        ]
        doc = Document.from_elements(elements)

        # Offset in heading
        loc1 = doc.location_at_offset(2)
        assert loc1.element_type == "heading"
        assert loc1.start_offset == 2

        # Offset in paragraph
        loc2 = doc.location_at_offset(10)
        assert loc2.element_type == "paragraph"
        assert loc2.start_offset == 10

    def test_document_location_for_span(self):
        """Test location_for_span mapping."""
        elements = [
            Paragraph("Hello world.", 0, 12),
        ]
        doc = Document.from_elements(elements)

        loc = doc.location_for_span(6, 11)  # "world"
        assert loc.start_offset == 6
        assert loc.end_offset == 11
        assert loc.element_type == "paragraph"

    def test_document_text_at_location(self):
        """Test text extraction at location."""
        elements = [
            Paragraph("Hello world.", 0, 12),
        ]
        doc = Document.from_elements(elements)

        loc = Location(start_offset=0, end_offset=5)
        text = doc.text_at_location(loc)
        assert text == "Hello"

    def test_document_serialization(self):
        """Test to_dict and from_dict roundtrip."""
        elements = [
            Heading("Title", HeadingLevel.H1, 0, 5),
            Paragraph("Content.", 6, 14),
            List(
                ListType.UNORDERED,
                [ListItem("Item 1", 15, 21)],
                15,
                21,
            ),
        ]
        doc = Document.from_elements(elements, title="Test")

        # Serialize
        data = doc.to_dict()
        assert data["title"] == "Test"
        assert len(data["elements"]) == 3

        # Deserialize
        doc2 = Document.from_dict(data)
        assert doc2.title == "Test"
        assert len(doc2) == 3
        assert doc2.headings()[0].text == "Title"
        assert doc2.paragraphs()[0].text == "Content."
        assert doc2.lists()[0].items[0].text == "Item 1"

    def test_document_lists_and_tables_accessors(self):
        """Test lists() and tables() accessors."""
        elements = [
            List(ListType.ORDERED, [ListItem("Item", 0, 4)], 0, 4),
            Table(
                [TableRow([TableCell("Cell", 5, 9, 0, 0)])],
                5,
                9,
            ),
        ]
        doc = Document.from_elements(elements)

        assert len(doc.lists()) == 1
        assert len(doc.tables()) == 1

    def test_document_full_text(self):
        """Test full_text reconstruction."""
        elements = [
            Heading("Title", HeadingLevel.H1, 0, 5),
            Paragraph("Para one.", 6, 15),
            Paragraph("Para two.", 16, 25),
        ]
        doc = Document.from_elements(elements)

        full = doc.full_text()
        assert "Title" in full
        assert "Para one." in full
        assert "Para two." in full


class TestDocumentEdgeCases:
    """Edge case tests for Document model."""

    def test_empty_document(self):
        """Test empty document handling."""
        doc = Document.from_elements([])
        assert len(doc) == 0
        assert doc.headings() == []
        assert doc.paragraphs() == []
        assert doc.sections() == []

    def test_document_without_headings(self):
        """Test document with no headings (no sections)."""
        elements = [
            Paragraph("Just paragraphs.", 0, 16),
            Paragraph("More text.", 17, 27),
        ]
        doc = Document.from_elements(elements)

        assert len(doc.headings()) == 0
        assert len(doc.paragraphs()) == 2
        assert len(doc.sections()) == 0

    def test_section_content_assignment(self):
        """Test that content is correctly assigned to sections."""
        elements = [
            Heading("H1", HeadingLevel.H1, 0, 2),
            Paragraph("P1", 3, 5),
            Paragraph("P2", 6, 8),
            Heading("H2", HeadingLevel.H2, 9, 11),
            Paragraph("P3", 12, 14),
        ]
        doc = Document.from_elements(elements)

        sections = doc.sections()
        assert len(sections) == 1  # One H1

        h1_section = sections[0]
        assert len(h1_section.content) == 2  # P1 and P2
        assert len(h1_section.subsections) == 1  # H2

        h2_section = h1_section.subsections[0]
        assert len(h2_section.content) == 1  # P3


class TestTextRun:
    """Tests for TextRun inline formatting."""

    def test_text_run_creation(self):
        """Test basic TextRun creation."""
        run = TextRun("hello", 0, 5)
        assert run.text == "hello"
        assert run.start_offset == 0
        assert run.end_offset == 5
        assert not run.bold
        assert not run.italic

    def test_text_run_with_formatting(self):
        """Test TextRun with formatting flags."""
        run = TextRun("bold text", 0, 9, bold=True, italic=True)
        assert run.bold
        assert run.italic
        assert run.is_formatted

    def test_text_run_is_formatted(self):
        """Test is_formatted property."""
        plain = TextRun("plain", 0, 5)
        assert not plain.is_formatted

        bold = TextRun("bold", 0, 4, bold=True)
        assert bold.is_formatted

        highlighted = TextRun("highlighted", 0, 11, highlight_color="yellow")
        assert highlighted.is_formatted

        linked = TextRun("link", 0, 4, hyperlink="https://example.com")
        assert linked.is_formatted

    def test_text_run_is_hyperlink(self):
        """Test is_hyperlink property."""
        run = TextRun("click here", 0, 10, hyperlink="https://example.com")
        assert run.is_hyperlink
        assert run.hyperlink == "https://example.com"

    def test_text_run_is_highlighted(self):
        """Test is_highlighted property."""
        run = TextRun("keyword", 0, 7, highlight_color="yellow")
        assert run.is_highlighted
        assert run.highlight_color == "yellow"

    def test_text_run_auto_fixes_end_offset(self):
        """Test that end_offset is auto-corrected to match text length."""
        run = TextRun("hello", 5, 999)  # Wrong end_offset
        assert run.end_offset == 10  # Should be start_offset + len(text)

    def test_text_run_serialization(self):
        """Test TextRun to_dict and from_dict."""
        run = TextRun(
            "link text",
            0, 9,
            bold=True,
            highlight_color="green",
            hyperlink="https://example.com",
        )
        data = run.to_dict()
        assert data["text"] == "link text"
        assert data["bold"] is True
        assert data["highlight_color"] == "green"
        assert data["hyperlink"] == "https://example.com"
        assert "italic" not in data  # False values omitted

        run2 = TextRun.from_dict(data)
        assert run2.text == "link text"
        assert run2.bold
        assert run2.highlight_color == "green"
        assert run2.hyperlink == "https://example.com"


class TestParagraphRuns:
    """Tests for Paragraph.runs() inline formatting."""

    def test_paragraph_default_run(self):
        """Test that plain paragraph returns single unformatted run."""
        para = Paragraph("Hello world.", 0, 12)
        runs = para.runs()

        assert len(runs) == 1
        assert runs[0].text == "Hello world."
        assert runs[0].start_offset == 0
        assert runs[0].end_offset == 12
        assert not runs[0].is_formatted

    def test_paragraph_with_explicit_runs(self):
        """Test paragraph with explicit formatting runs."""
        runs = [
            TextRun("Hello ", 0, 6),
            TextRun("bold", 6, 10, bold=True),
            TextRun(" world.", 10, 17),
        ]
        para = Paragraph("Hello bold world.", 0, 17, _runs=runs)

        assert len(para.runs()) == 3
        assert para.runs()[0].text == "Hello "
        assert para.runs()[1].text == "bold"
        assert para.runs()[1].bold
        assert para.runs()[2].text == " world."

    def test_paragraph_run_at_offset(self):
        """Test run_at_offset method."""
        runs = [
            TextRun("Hello ", 0, 6),
            TextRun("world", 6, 11, bold=True),
        ]
        para = Paragraph("Hello world", 0, 11, _runs=runs)

        run = para.run_at_offset(3)  # In "Hello "
        assert run.text == "Hello "

        run = para.run_at_offset(8)  # In "world"
        assert run.text == "world"
        assert run.bold

        run = para.run_at_offset(100)  # Out of range
        assert run is None


class TestHeadingRuns:
    """Tests for Heading.runs() inline formatting."""

    def test_heading_default_run(self):
        """Test that plain heading returns single unformatted run."""
        heading = Heading("Title", HeadingLevel.H1, 0, 5)
        runs = heading.runs()

        assert len(runs) == 1
        assert runs[0].text == "Title"

    def test_heading_with_hyperlink(self):
        """Test heading with hyperlink run."""
        runs = [
            TextRun("See ", 0, 4),
            TextRun("docs", 4, 8, hyperlink="https://docs.example.com"),
        ]
        heading = Heading("See docs", HeadingLevel.H2, 0, 8, _runs=runs)

        assert len(heading.runs()) == 2
        assert heading.runs()[1].hyperlink == "https://docs.example.com"


class TestListItemRuns:
    """Tests for ListItem.runs() inline formatting."""

    def test_list_item_default_run(self):
        """Test that plain list item returns single unformatted run."""
        item = ListItem("Item text", 0, 9)
        runs = item.runs()

        assert len(runs) == 1
        assert runs[0].text == "Item text"

    def test_list_item_with_formatting(self):
        """Test list item with formatted runs."""
        runs = [
            TextRun("Important: ", 0, 11, bold=True),
            TextRun("details here", 11, 23),
        ]
        item = ListItem("Important: details here", 0, 23, _runs=runs)

        assert len(item.runs()) == 2
        assert item.runs()[0].bold


class TestTableCellRuns:
    """Tests for TableCell.runs() inline formatting."""

    def test_table_cell_default_run(self):
        """Test that plain table cell returns single unformatted run."""
        cell = TableCell("Cell content", 0, 12, 0, 0)
        runs = cell.runs()

        assert len(runs) == 1
        assert runs[0].text == "Cell content"


class TestDocumentHyperlinks:
    """Tests for Document.hyperlinks() accessor."""

    def test_hyperlinks_in_paragraph(self):
        """Test extracting hyperlinks from paragraphs."""
        runs = [
            TextRun("Click ", 0, 6),
            TextRun("here", 6, 10, hyperlink="https://example.com"),
            TextRun(" for more.", 10, 20),
        ]
        para = Paragraph("Click here for more.", 100, 120, _runs=runs)
        doc = Document.from_elements([para])

        links = doc.hyperlinks()
        assert len(links) == 1
        text, url, loc = links[0]
        assert text == "here"
        assert url == "https://example.com"
        assert loc.start_offset == 106  # 100 + 6
        assert loc.end_offset == 110    # 100 + 10
        assert loc.element_type == "paragraph"

    def test_multiple_hyperlinks(self):
        """Test extracting multiple hyperlinks."""
        runs1 = [
            TextRun("Link ", 0, 5),
            TextRun("one", 5, 8, hyperlink="https://one.com"),
        ]
        runs2 = [
            TextRun("Link ", 0, 5),
            TextRun("two", 5, 8, hyperlink="https://two.com"),
        ]
        para1 = Paragraph("Link one", 0, 8, _runs=runs1)
        para2 = Paragraph("Link two", 9, 17, _runs=runs2)
        doc = Document.from_elements([para1, para2])

        links = doc.hyperlinks()
        assert len(links) == 2
        assert links[0][1] == "https://one.com"
        assert links[1][1] == "https://two.com"

    def test_hyperlinks_in_list(self):
        """Test extracting hyperlinks from list items."""
        runs = [TextRun("link", 0, 4, hyperlink="https://list-link.com")]
        item = ListItem("link", 50, 54, _runs=runs)
        lst = List(ListType.UNORDERED, [item], 50, 54)
        doc = Document.from_elements([lst])

        links = doc.hyperlinks()
        assert len(links) == 1
        assert links[0][0] == "link"
        assert links[0][2].element_type == "list_item"


class TestDocumentHighlightedSpans:
    """Tests for Document.highlighted_spans() accessor."""

    def test_highlighted_keywords(self):
        """Test extracting highlighted spans."""
        runs = [
            TextRun("This is a ", 0, 10),
            TextRun("keyword", 10, 17, highlight_color="yellow"),
            TextRun(" in text.", 17, 26),
        ]
        para = Paragraph("This is a keyword in text.", 0, 26, _runs=runs)
        doc = Document.from_elements([para])

        highlights = doc.highlighted_spans()
        assert len(highlights) == 1
        text, color, loc = highlights[0]
        assert text == "keyword"
        assert color == "yellow"
        assert loc.start_offset == 10
        assert loc.end_offset == 17

    def test_multiple_highlight_colors(self):
        """Test multiple highlights with different colors."""
        runs = [
            TextRun("keyword1", 0, 8, highlight_color="yellow"),
            TextRun(" and ", 8, 13),
            TextRun("keyword2", 13, 21, highlight_color="green"),
        ]
        para = Paragraph("keyword1 and keyword2", 0, 21, _runs=runs)
        doc = Document.from_elements([para])

        highlights = doc.highlighted_spans()
        assert len(highlights) == 2
        assert highlights[0][1] == "yellow"
        assert highlights[1][1] == "green"


class TestDocumentRunsSerialization:
    """Tests for Document serialization with inline runs."""

    def test_plain_text_roundtrip(self):
        """Test that plain text serializes/deserializes without runs field."""
        para = Paragraph("Plain text.", 0, 11)
        doc = Document.from_elements([para])

        data = doc.to_dict()
        # Plain text should NOT have runs field (backward compatible)
        assert "runs" not in data["elements"][0]

        doc2 = Document.from_dict(data)
        assert doc2.paragraphs()[0].text == "Plain text."
        # Should still work with runs() accessor
        assert len(doc2.paragraphs()[0].runs()) == 1

    def test_formatted_runs_roundtrip(self):
        """Test serialization roundtrip preserves formatting runs."""
        runs = [
            TextRun("Hello ", 0, 6),
            TextRun("bold", 6, 10, bold=True),
            TextRun(" ", 10, 11),
            TextRun("link", 11, 15, hyperlink="https://example.com"),
            TextRun(" ", 15, 16),
            TextRun("highlight", 16, 25, highlight_color="yellow"),
        ]
        para = Paragraph("Hello bold link highlight", 0, 25, _runs=runs)
        doc = Document.from_elements([para])

        data = doc.to_dict()
        assert "runs" in data["elements"][0]
        assert len(data["elements"][0]["runs"]) == 6

        doc2 = Document.from_dict(data)
        restored_runs = doc2.paragraphs()[0].runs()
        assert len(restored_runs) == 6
        assert restored_runs[1].bold
        assert restored_runs[3].hyperlink == "https://example.com"
        assert restored_runs[5].highlight_color == "yellow"

    def test_heading_runs_roundtrip(self):
        """Test heading with runs serialization roundtrip."""
        runs = [
            TextRun("Title with ", 0, 11),
            TextRun("link", 11, 15, hyperlink="https://example.com"),
        ]
        heading = Heading("Title with link", HeadingLevel.H1, 0, 15, _runs=runs)
        doc = Document.from_elements([heading])

        data = doc.to_dict()
        doc2 = Document.from_dict(data)

        restored_runs = doc2.headings()[0].runs()
        assert len(restored_runs) == 2
        assert restored_runs[1].hyperlink == "https://example.com"

    def test_list_item_runs_roundtrip(self):
        """Test list item with runs serialization roundtrip."""
        runs = [TextRun("Important", 0, 9, bold=True)]
        item = ListItem("Important", 0, 9, _runs=runs)
        lst = List(ListType.UNORDERED, [item], 0, 9)
        doc = Document.from_elements([lst])

        data = doc.to_dict()
        doc2 = Document.from_dict(data)

        restored_item = doc2.lists()[0].items[0]
        assert restored_item.runs()[0].bold

    def test_table_cell_runs_roundtrip(self):
        """Test table cell with runs serialization roundtrip."""
        runs = [TextRun("Header", 0, 6, bold=True)]
        cell = TableCell("Header", 0, 6, 0, 0, is_header=True, _runs=runs)
        row = TableRow([cell], is_header_row=True)
        table = Table([row], 0, 6)
        doc = Document.from_elements([table])

        data = doc.to_dict()
        doc2 = Document.from_dict(data)

        restored_cell = doc2.tables()[0].rows[0].cells[0]
        assert restored_cell.runs()[0].bold
