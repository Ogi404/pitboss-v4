"""
Tests for deterministic/locale_spelling.py - Regional spelling check.
"""

import pytest
from dataclasses import dataclass

from core.document import Document, Paragraph, Heading, HeadingLevel, List, ListItem, ListType, Table, TableRow, TableCell
from core.check_base import CheckRegistry


# =============================================================================
# FIXTURES
# =============================================================================

@dataclass
class MockStandards:
    """Mock standards object with spelling_region property."""
    spelling_region: str = "british"


def make_document(text: str, start_offset: int = 0) -> Document:
    """Create a simple document with one paragraph."""
    para = Paragraph(
        text=text,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
    )
    return Document.from_elements([para])


def make_heading_document(text: str, level: int = 2) -> Document:
    """Create a document with one heading."""
    heading = Heading(
        text=text,
        level=HeadingLevel(level),
        start_offset=0,
        end_offset=len(text),
    )
    return Document.from_elements([heading])


def make_list_document(items: list[str]) -> Document:
    """Create a document with a list."""
    offset = 0
    list_items = []
    for item_text in items:
        list_items.append(ListItem(
            text=item_text,
            start_offset=offset,
            end_offset=offset + len(item_text),
            indent_level=0,
        ))
        offset += len(item_text) + 1

    lst = List(
        items=list_items,
        list_type=ListType.UNORDERED,
        start_offset=0,
        end_offset=offset - 1,
    )
    return Document.from_elements([lst])


def make_table_document(cells: list[str]) -> Document:
    """Create a document with a single-row table."""
    offset = 0
    table_cells = []
    for i, cell_text in enumerate(cells):
        table_cells.append(TableCell(
            text=cell_text,
            start_offset=offset,
            end_offset=offset + len(cell_text),
            row_index=0,
            col_index=i,
        ))
        offset += len(cell_text) + 1

    row = TableRow(cells=table_cells, is_header_row=False)
    table = Table(
        rows=[row],
        start_offset=0,
        end_offset=offset - 1,
    )
    return Document.from_elements([table])


def get_registry():
    """Get or create the check registry."""
    return CheckRegistry()


@pytest.fixture
def check():
    """Create the locale spelling check instance."""
    from deterministic.locale_spelling import LocaleSpellingCheck

    registry = get_registry()
    if not registry.is_registered("locale_spelling"):
        from core.check_base import register_check
        register_check(LocaleSpellingCheck)

    return LocaleSpellingCheck()


@pytest.fixture
def british_standards() -> MockStandards:
    """Standards for British spelling region."""
    return MockStandards(spelling_region="british")


@pytest.fixture
def american_standards() -> MockStandards:
    """Standards for American spelling region."""
    return MockStandards(spelling_region="american")


@pytest.fixture
def canadian_standards() -> MockStandards:
    """Standards for Canadian spelling region."""
    return MockStandards(spelling_region="canadian")


@pytest.fixture
def australian_standards() -> MockStandards:
    """Standards for Australian spelling region."""
    return MockStandards(spelling_region="australian")


@pytest.fixture
def new_zealand_standards() -> MockStandards:
    """Standards for New Zealand spelling region."""
    return MockStandards(spelling_region="new_zealand")


# =============================================================================
# BRITISH TARGET
# =============================================================================

class TestBritishTarget:
    """Test British spelling region - American forms should be flagged."""

    def test_color_to_colour(self, check, british_standards):
        """American color -> British colour, auto-applicable."""
        doc = make_document("The color is red.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "color"
        assert findings[0].proposed_text == "colour"
        assert findings[0].auto_applicable is True
        assert findings[0].metadata_dict["region"] == "british"

    def test_organize_to_organise(self, check, british_standards):
        """American organize -> British organise, auto-applicable."""
        doc = make_document("Please organize the files.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "organize"
        assert findings[0].proposed_text == "organise"
        assert findings[0].auto_applicable is True

    def test_center_to_centre(self, check, british_standards):
        """American center -> British centre, auto-applicable."""
        doc = make_document("The data center is located downtown.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "center"
        assert findings[0].proposed_text == "centre"
        assert findings[0].auto_applicable is True

    def test_traveled_to_travelled(self, check, british_standards):
        """American traveled -> British travelled, auto-applicable."""
        doc = make_document("She traveled to London.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "traveled"
        assert findings[0].proposed_text == "travelled"
        assert findings[0].auto_applicable is True

    def test_gray_to_grey(self, check, british_standards):
        """American gray -> British grey, auto-applicable."""
        doc = make_document("The sky was gray.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "gray"
        assert findings[0].proposed_text == "grey"
        assert findings[0].auto_applicable is True

    def test_catalog_to_catalogue(self, check, british_standards):
        """American catalog -> British catalogue, auto-applicable."""
        doc = make_document("Browse the catalog for details.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "catalog"
        assert findings[0].proposed_text == "catalogue"
        assert findings[0].auto_applicable is True

    def test_correct_british_no_findings(self, check, british_standards):
        """Correct British spelling produces no findings."""
        doc = make_document("The colour is my favourite.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 0

    def test_multiple_american_words(self, check, british_standards):
        """Multiple American spellings in one paragraph."""
        doc = make_document("The favorite color is gray and you should organize it.")
        findings = check.run(doc, british_standards)

        # Should find: favorite, color, gray, organize
        assert len(findings) == 4
        words = {f.original_text for f in findings}
        assert words == {"favorite", "color", "gray", "organize"}


# =============================================================================
# AMERICAN TARGET
# =============================================================================

class TestAmericanTarget:
    """Test American spelling region - British forms should be flagged."""

    def test_colour_to_color(self, check, american_standards):
        """British colour -> American color, auto-applicable."""
        doc = make_document("The colour is red.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "colour"
        assert findings[0].proposed_text == "color"
        assert findings[0].auto_applicable is True
        assert findings[0].metadata_dict["region"] == "american"

    def test_organise_to_organize(self, check, american_standards):
        """British organise -> American organize, auto-applicable."""
        doc = make_document("Please organise the files.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "organise"
        assert findings[0].proposed_text == "organize"
        assert findings[0].auto_applicable is True

    def test_centre_to_center(self, check, american_standards):
        """British centre -> American center, auto-applicable."""
        doc = make_document("The data centre is located downtown.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "centre"
        assert findings[0].proposed_text == "center"
        assert findings[0].auto_applicable is True

    def test_travelled_to_traveled(self, check, american_standards):
        """British travelled -> American traveled, auto-applicable."""
        doc = make_document("She travelled to London.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "travelled"
        assert findings[0].proposed_text == "traveled"
        assert findings[0].auto_applicable is True

    def test_grey_to_gray(self, check, american_standards):
        """British grey -> American gray, auto-applicable."""
        doc = make_document("The sky was grey.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "grey"
        assert findings[0].proposed_text == "gray"
        assert findings[0].auto_applicable is True

    def test_correct_american_no_findings(self, check, american_standards):
        """Correct American spelling produces no findings."""
        doc = make_document("The color is my favorite.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 0


# =============================================================================
# CANADIAN TARGET - HYBRID
# =============================================================================

class TestCanadianTarget:
    """Test Canadian spelling region - hybrid British/American rules."""

    def test_color_to_colour_canadian(self, check, canadian_standards):
        """Canadian uses British -our: color -> colour, auto-applicable."""
        doc = make_document("The color is red.")
        findings = check.run(doc, canadian_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "color"
        assert findings[0].proposed_text == "colour"
        assert findings[0].auto_applicable is True
        assert findings[0].metadata_dict["region"] == "canadian"

    def test_organise_to_organize_canadian(self, check, canadian_standards):
        """Canadian uses American -ize: organise -> organize, auto-applicable.

        This is the critical hybrid test - British -ise is WRONG in Canadian.
        """
        doc = make_document("Please organise the files.")
        findings = check.run(doc, canadian_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "organise"
        assert findings[0].proposed_text == "organize"
        assert findings[0].auto_applicable is True

    def test_center_to_centre_canadian(self, check, canadian_standards):
        """Canadian uses British -re: center -> centre, auto-applicable."""
        doc = make_document("The data center is located downtown.")
        findings = check.run(doc, canadian_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "center"
        assert findings[0].proposed_text == "centre"
        assert findings[0].auto_applicable is True

    def test_gray_to_grey_canadian(self, check, canadian_standards):
        """Canadian uses British grey: gray -> grey, auto-applicable."""
        doc = make_document("The sky was gray.")
        findings = check.run(doc, canadian_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "gray"
        assert findings[0].proposed_text == "grey"
        assert findings[0].auto_applicable is True

    def test_canadian_correct_hybrid_no_findings(self, check, canadian_standards):
        """Correct Canadian hybrid spelling produces no findings.

        Canadian correct: colour (British) + organize (American)
        """
        doc = make_document("Organize the colour palette in the centre.")
        findings = check.run(doc, canadian_standards)

        # All three words (organize, colour, centre) are correct Canadian
        assert len(findings) == 0

    def test_canadian_both_wrong(self, check, canadian_standards):
        """Both British and American wrong forms flagged.

        Canadian wrong: color (American) + organise (British)
        """
        doc = make_document("Organise the color palette in the center.")
        findings = check.run(doc, canadian_standards)

        # Should flag: organise (British -ise), color (American -or), center (American -er)
        assert len(findings) == 3
        words = {f.original_text.lower() for f in findings}
        assert "organise" in words  # British -ise -> American -ize
        assert "color" in words     # American -or -> British -our
        assert "center" in words    # American -er -> British -re


# =============================================================================
# AUSTRALIAN/NZ TARGET
# =============================================================================

class TestAustralianTarget:
    """Test Australian spelling region - follows British rules."""

    def test_color_to_colour_australian(self, check, australian_standards):
        """Australian uses British spelling: color -> colour."""
        doc = make_document("The color is red.")
        findings = check.run(doc, australian_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "color"
        assert findings[0].proposed_text == "colour"
        assert findings[0].metadata_dict["region"] == "australian"

    def test_organize_to_organise_australian(self, check, australian_standards):
        """Australian uses British spelling: organize -> organise."""
        doc = make_document("Please organize the files.")
        findings = check.run(doc, australian_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "organize"
        assert findings[0].proposed_text == "organise"


class TestNewZealandTarget:
    """Test New Zealand spelling region - follows British rules."""

    def test_color_to_colour_nz(self, check, new_zealand_standards):
        """NZ uses British spelling: color -> colour."""
        doc = make_document("The color is red.")
        findings = check.run(doc, new_zealand_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "color"
        assert findings[0].proposed_text == "colour"
        assert findings[0].metadata_dict["region"] == "new_zealand"


# =============================================================================
# CASE PRESERVATION
# =============================================================================

class TestCasePreservation:
    """Test that case is preserved in corrections."""

    def test_preserve_lowercase(self, check, british_standards):
        """Lowercase preserved."""
        doc = make_document("The color is nice.")
        findings = check.run(doc, british_standards)

        assert findings[0].proposed_text == "colour"

    def test_preserve_uppercase(self, check, british_standards):
        """All caps preserved."""
        doc = make_document("THE COLOR IS NICE.")
        findings = check.run(doc, british_standards)

        assert findings[0].proposed_text == "COLOUR"

    def test_preserve_title_case(self, check, british_standards):
        """Title case preserved."""
        doc = make_document("Color is a good word.")
        findings = check.run(doc, british_standards)

        assert findings[0].proposed_text == "Colour"

    def test_preserve_case_with_suffix(self, check, british_standards):
        """Case preserved with longer words."""
        doc = make_document("ORGANIZATION is key.")
        findings = check.run(doc, british_standards)

        assert findings[0].proposed_text == "ORGANISATION"


# =============================================================================
# EXCLUSIONS
# =============================================================================

class TestExclusions:
    """Test exclusion of quoted strings, URLs, emails."""

    def test_quoted_string_not_flagged_double(self, check, british_standards):
        """Word inside double quotes not flagged."""
        doc = make_document('The game is called "Color Match" today.')
        findings = check.run(doc, british_standards)

        # "Color" in quotes should be skipped
        assert len(findings) == 0

    def test_quoted_string_not_flagged_single(self, check, british_standards):
        """Word inside single quotes not flagged."""
        doc = make_document("The game is called 'Color Match' today.")
        findings = check.run(doc, british_standards)

        # 'Color' in quotes should be skipped
        assert len(findings) == 0

    def test_url_not_flagged(self, check, british_standards):
        """Word inside URL not flagged."""
        doc = make_document("Visit colorbet.com for details.")
        findings = check.run(doc, british_standards)

        # colorbet.com should be skipped
        assert len(findings) == 0

    def test_url_https_not_flagged(self, check, british_standards):
        """Full HTTPS URL not flagged."""
        doc = make_document("Visit https://colorbet.com for details.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 0

    def test_email_not_flagged(self, check, british_standards):
        """Email address not flagged."""
        doc = make_document("Contact support@colorbet.com for help.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 0

    def test_word_outside_quotes_flagged(self, check, british_standards):
        """Word outside quotes is flagged."""
        doc = make_document('The "Premium" color scheme is nice.')
        findings = check.run(doc, british_standards)

        # "color" outside quotes should be flagged
        assert len(findings) == 1
        assert findings[0].original_text == "color"


# =============================================================================
# DOCUMENT ELEMENT TYPES
# =============================================================================

class TestDocumentElements:
    """Test checking various document elements."""

    def test_paragraph_checked(self, check, british_standards):
        """Paragraphs are checked."""
        doc = make_document("The color is nice.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1

    def test_heading_checked(self, check, british_standards):
        """Headings are checked."""
        doc = make_heading_document("Color Guide")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "Color"

    def test_list_items_checked(self, check, british_standards):
        """List items are checked."""
        doc = make_list_document(["Choose your favorite color"])
        findings = check.run(doc, british_standards)

        # favorite and color
        assert len(findings) == 2

    def test_table_cells_checked(self, check, british_standards):
        """Table cells are checked."""
        doc = make_table_document(["Color", "Flavor", "Size"])
        findings = check.run(doc, british_standards)

        # Color and Flavor (but not Size)
        assert len(findings) == 2


# =============================================================================
# CONTEXT-DEPENDENT WORDS
# =============================================================================

class TestContextDependent:
    """Test context-dependent words that need human review."""

    def test_programme_in_british_context(self, check, american_standards):
        """Programme flagged as proposal in American context."""
        doc = make_document("Check the programme schedule.")
        findings = check.run(doc, american_standards)

        # programme -> program is auto (standard swap)
        assert len(findings) == 1
        assert findings[0].original_text == "programme"
        assert findings[0].proposed_text == "program"
        assert findings[0].auto_applicable is True


# =============================================================================
# PATTERN TYPES
# =============================================================================

class TestPatternTypes:
    """Test metadata includes correct pattern type."""

    def test_ise_ize_pattern(self, check, british_standards):
        """ise/ize pattern detected."""
        doc = make_document("Organize the files.")
        findings = check.run(doc, british_standards)

        assert findings[0].metadata_dict["pattern_type"] == "ise_ize"

    def test_our_or_pattern(self, check, british_standards):
        """our/or pattern detected."""
        doc = make_document("The color is nice.")
        findings = check.run(doc, british_standards)

        assert findings[0].metadata_dict["pattern_type"] == "our_or"

    def test_re_er_pattern(self, check, british_standards):
        """re/er pattern detected."""
        doc = make_document("The center is here.")
        findings = check.run(doc, british_standards)

        assert findings[0].metadata_dict["pattern_type"] == "re_er"


# =============================================================================
# REGISTRATION
# =============================================================================

class TestRegistration:
    """Test check registration."""

    def test_check_registered(self, check):
        """Check is registered with correct name."""
        assert check.name == "locale_spelling"
        assert check.category == "locale_spelling"

    def test_check_description(self, check):
        """Check has description."""
        assert "regional spelling" in check.metadata.description.lower()

    def test_required_standards(self, check):
        """Check requires spelling_region."""
        required = check._get_required_standards()
        assert "spelling_region" in required


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_document(self, check, british_standards):
        """Empty document produces no findings."""
        doc = make_document("")
        findings = check.run(doc, british_standards)

        assert len(findings) == 0

    def test_no_target_words(self, check, british_standards):
        """Document with no target words produces no findings."""
        doc = make_document("Hello world this is a test.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 0

    def test_unknown_region_defaults_empty(self, check):
        """Unknown region returns empty findings."""
        standards = MockStandards(spelling_region="unknown")
        doc = make_document("The color is nice.")
        findings = check.run(doc, standards)

        # Unknown region has no swap map
        assert len(findings) == 0

    def test_word_at_start(self, check, british_standards):
        """Word at start of text is flagged."""
        doc = make_document("Color is important.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "Color"

    def test_word_at_end(self, check, british_standards):
        """Word at end of text is flagged."""
        doc = make_document("I like this color")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "color"

    def test_multiple_same_word(self, check, british_standards):
        """Multiple instances of same word all flagged."""
        doc = make_document("The color is nice and the other color is too.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 2
        assert all(f.original_text == "color" for f in findings)


# =============================================================================
# SPECIAL BRITISH WORDS
# =============================================================================

class TestSpecialWords:
    """Test special word transformations."""

    def test_analyze_to_analyse(self, check, british_standards):
        """American analyze -> British analyse."""
        doc = make_document("Let me analyze the data.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "analyze"
        assert findings[0].proposed_text == "analyse"

    def test_jewelry_to_jewellery(self, check, british_standards):
        """American jewelry -> British jewellery."""
        doc = make_document("Buy some jewelry.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "jewelry"
        assert findings[0].proposed_text == "jewellery"

    def test_defense_to_defence(self, check, british_standards):
        """American defense -> British defence."""
        doc = make_document("The defense was strong.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "defense"
        assert findings[0].proposed_text == "defence"

    def test_tire_to_tyre(self, check, british_standards):
        """American tire -> British tyre."""
        doc = make_document("Change the tire.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "tire"
        assert findings[0].proposed_text == "tyre"

    def test_skeptic_to_sceptic(self, check, british_standards):
        """American skeptic -> British sceptic."""
        doc = make_document("He is a skeptic.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "skeptic"
        assert findings[0].proposed_text == "sceptic"


# =============================================================================
# CONTEXT-DEPENDENT WORDS - BRITISH TARGET (PROPOSALS)
# =============================================================================

class TestContextDependentBritishTarget:
    """Test that American→British conversions for ambiguous words are proposals.

    These words have noun/verb distinctions or context-specific meanings:
    - check/cheque: verb (verify) vs noun (payment)
    - license/licence: verb vs noun in British
    - practice/practise: noun vs verb in British
    - program/programme: software vs TV/radio
    - etc.

    For British targets, these should be PROPOSALS (auto_applicable=False).
    """

    def test_check_to_cheque_is_proposal(self, check, british_standards):
        """'check' in British context is a proposal, not auto-applied."""
        doc = make_document("Double-check your balance before paying.")
        findings = check.run(doc, british_standards)

        check_findings = [f for f in findings if f.original_text.lower() == 'check']
        assert len(check_findings) == 1
        assert check_findings[0].auto_applicable is False
        assert check_findings[0].proposed_text.lower() == 'cheque'
        assert 'context' in check_findings[0].reasoning.lower() or 'verb' in check_findings[0].reasoning.lower()

    def test_license_to_licence_is_proposal(self, check, british_standards):
        """'license' in British context is a proposal, not auto-applied."""
        doc = make_document("You need a license to operate.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "license"
        assert findings[0].proposed_text == "licence"
        assert findings[0].auto_applicable is False

    def test_practice_to_practise_is_proposal(self, check, british_standards):
        """'practice' in British context is a proposal (could be noun or verb)."""
        doc = make_document("You should practice more.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "practice"
        assert findings[0].proposed_text == "practise"
        assert findings[0].auto_applicable is False

    def test_program_to_programme_is_proposal(self, check, british_standards):
        """'program' in British context is a proposal (could be software)."""
        doc = make_document("Run the program to see results.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "program"
        assert findings[0].proposed_text == "programme"
        assert findings[0].auto_applicable is False

    def test_draft_to_draught_is_proposal(self, check, british_standards):
        """'draft' in British context is a proposal (document vs air current)."""
        doc = make_document("Review the draft before submitting.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "draft"
        assert findings[0].proposed_text == "draught"
        assert findings[0].auto_applicable is False

    def test_story_to_storey_is_proposal(self, check, british_standards):
        """'story' in British context is a proposal (narrative vs building floor)."""
        doc = make_document("The building has ten story.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "story"
        assert findings[0].proposed_text == "storey"
        assert findings[0].auto_applicable is False

    def test_disk_to_disc_is_proposal(self, check, british_standards):
        """'disk' in British context is a proposal (magnetic vs optical)."""
        doc = make_document("Insert the disk into the drive.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "disk"
        assert findings[0].proposed_text == "disc"
        assert findings[0].auto_applicable is False

    def test_multiple_context_dependent_all_proposals(self, check, british_standards):
        """Multiple context-dependent words all become proposals."""
        doc = make_document("Check your license and run the program.")
        findings = check.run(doc, british_standards)

        # Should have 3 findings: check, license, program
        assert len(findings) == 3
        for f in findings:
            assert f.auto_applicable is False

    def test_tire_to_tyre_is_proposal(self, check, british_standards):
        """'tire' in British context is a proposal (verb vs noun)."""
        doc = make_document("I tire easily after long drives.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "tire"
        assert findings[0].proposed_text == "tyre"
        assert findings[0].auto_applicable is False
        assert "fatigue" in findings[0].reasoning.lower() or "verb" in findings[0].reasoning.lower()

    def test_meter_to_metre_is_proposal(self, check, british_standards):
        """'meter' in British context is a proposal (device vs unit)."""
        doc = make_document("Check the parking meter before leaving.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 2  # "check" and "meter"
        meter_findings = [f for f in findings if f.original_text.lower() == 'meter']
        assert len(meter_findings) == 1
        assert meter_findings[0].proposed_text == "metre"
        assert meter_findings[0].auto_applicable is False

    def test_curb_to_kerb_is_proposal(self, check, british_standards):
        """'curb' in British context is a proposal (verb vs noun)."""
        doc = make_document("Tools to curb impulsive betting are available.")
        findings = check.run(doc, british_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "curb"
        assert findings[0].proposed_text == "kerb"
        assert findings[0].auto_applicable is False
        assert "restrain" in findings[0].reasoning.lower() or "verb" in findings[0].reasoning.lower()


# =============================================================================
# CONTEXT-DEPENDENT WORDS - AMERICAN TARGET (AUTO-APPLY)
# =============================================================================

class TestContextDependentAmericanTarget:
    """Test that British→American conversions for ambiguous words ARE auto-applied.

    The ambiguity is one-directional: British→American is always safe.
    - cheque → check: always correct in American
    - licence → license: always correct in American
    - practise → practice: always correct in American
    - programme → program: always correct in American
    """

    def test_cheque_to_check_is_auto(self, check, american_standards):
        """'cheque' in American context IS auto-applied."""
        doc = make_document("Pay by cheque.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "cheque"
        assert findings[0].proposed_text == "check"
        assert findings[0].auto_applicable is True  # Safe direction

    def test_licence_to_license_is_auto(self, check, american_standards):
        """'licence' in American context IS auto-applied."""
        doc = make_document("You need a licence.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "licence"
        assert findings[0].proposed_text == "license"
        assert findings[0].auto_applicable is True  # Safe direction

    def test_practise_to_practice_is_auto(self, check, american_standards):
        """'practise' in American context IS auto-applied."""
        doc = make_document("You should practise more.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "practise"
        assert findings[0].proposed_text == "practice"
        assert findings[0].auto_applicable is True  # Safe direction

    def test_programme_to_program_is_auto(self, check, american_standards):
        """'programme' in American context IS auto-applied."""
        doc = make_document("Watch the programme tonight.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "programme"
        assert findings[0].proposed_text == "program"
        assert findings[0].auto_applicable is True  # Safe direction

    def test_draught_to_draft_is_auto(self, check, american_standards):
        """'draught' in American context IS auto-applied."""
        doc = make_document("Feel the draught from the window.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "draught"
        assert findings[0].proposed_text == "draft"
        assert findings[0].auto_applicable is True  # Safe direction

    def test_storey_to_story_is_auto(self, check, american_standards):
        """'storey' in American context IS auto-applied."""
        doc = make_document("The building has ten storey.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "storey"
        assert findings[0].proposed_text == "story"
        assert findings[0].auto_applicable is True  # Safe direction

    def test_disc_to_disk_is_auto(self, check, american_standards):
        """'disc' in American context IS auto-applied."""
        doc = make_document("Insert the disc into the drive.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "disc"
        assert findings[0].proposed_text == "disk"
        assert findings[0].auto_applicable is True  # Safe direction

    def test_tyre_to_tire_is_auto(self, check, american_standards):
        """'tyre' in American context IS auto-applied."""
        doc = make_document("Change the tyre on the car.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "tyre"
        assert findings[0].proposed_text == "tire"
        assert findings[0].auto_applicable is True  # Safe direction

    def test_metre_to_meter_is_auto(self, check, american_standards):
        """'metre' in American context IS auto-applied."""
        doc = make_document("One metre is about three feet.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "metre"
        assert findings[0].proposed_text == "meter"
        assert findings[0].auto_applicable is True  # Safe direction

    def test_kerb_to_curb_is_auto(self, check, american_standards):
        """'kerb' in American context IS auto-applied."""
        doc = make_document("Park near the kerb.")
        findings = check.run(doc, american_standards)

        assert len(findings) == 1
        assert findings[0].original_text == "kerb"
        assert findings[0].proposed_text == "curb"
        assert findings[0].auto_applicable is True  # Safe direction


# =============================================================================
# CONTEXT-DEPENDENT WORDS - AUSTRALIAN/NZ (SAME AS BRITISH)
# =============================================================================

class TestContextDependentAustralianTarget:
    """Test that Australian also treats ambiguous words as proposals."""

    def test_check_to_cheque_is_proposal_australian(self, check, australian_standards):
        """'check' in Australian context is a proposal, not auto-applied."""
        doc = make_document("Double-check your selections before placing a bet.")
        findings = check.run(doc, australian_standards)

        check_findings = [f for f in findings if f.original_text.lower() == 'check']
        assert len(check_findings) == 1
        assert check_findings[0].auto_applicable is False

    def test_license_to_licence_is_proposal_australian(self, check, australian_standards):
        """'license' in Australian context is a proposal."""
        doc = make_document("The casino operates under a valid license.")
        findings = check.run(doc, australian_standards)

        license_findings = [f for f in findings if f.original_text.lower() == 'license']
        assert len(license_findings) == 1
        assert license_findings[0].auto_applicable is False
