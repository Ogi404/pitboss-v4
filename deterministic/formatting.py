"""
Pitboss v4 - Formatting Check

Deterministic check for mechanical formatting consistency:
1. Double/multiple spaces - collapse to single
2. Space before punctuation - remove
3. Missing space after punctuation - add (with extensive exclusions)
4. Latin abbreviations (e.g., i.e., etc.) - flag for replacement
5. UI element quoting - flag unquoted button names
6. Trailing whitespace - strip

Auto-applies only for clear mechanical fixes; proposals for context-dependent issues.
"""

from __future__ import annotations
import re
from typing import Any, Optional

from core.check_base import DeterministicCheck, register_check
from core.document import Document, Paragraph, Heading, List, Table
from core.finding import Finding, FindingFactory, Category


# =============================================================================
# PATTERNS
# =============================================================================

# Double/multiple spaces (2+)
DOUBLE_SPACE_RE = re.compile(r'  +')

# Space before punctuation (excluding parens/brackets)
# Matches: " ," " ." " ;" " :" " !" " ?"
# Does NOT match: " (" or space before ellipsis
SPACE_BEFORE_PUNCT_RE = re.compile(r' +([,;:!?])|(?<!\.)( +\.)(?!\.)')

# Missing space after punctuation
# Matches: comma or period followed by letter
MISSING_SPACE_RE = re.compile(r'([,\.])([A-Za-z])')

# Latin abbreviations to flag
LATIN_ABBREV_RE = re.compile(r'\b(e\.g\.|i\.e\.|etc\.|viz\.|cf\.)', re.IGNORECASE)

# Latin abbreviation replacements
LATIN_REPLACEMENTS = {
    'e.g.': 'for example',
    'i.e.': 'that is',
    'etc.': '[rephrase to be specific]',
    'viz.': 'namely',
    'cf.': 'compare',
}

# UI action verbs (case-insensitive matching)
ACTION_VERBS_PATTERN = r'[Tt]ap|[Cc]lick|[Pp]ress|[Ss]elect|[Cc]hoose|[Hh]it|[Oo]pen'

# UI element pattern: action verb + unquoted Capitalized word(s)
# Matches: "tap Register", "click Add to Home" (1-3 Title Case words)
# Does NOT match: "tap 'Register'" (already quoted)
# Does NOT match: "tap the button" (lowercase after verb)
# Note: No IGNORECASE - we need [A-Z] to actually match uppercase only
UI_ELEMENT_RE = re.compile(
    rf'\b({ACTION_VERBS_PATTERN})\s+(?![\'"])([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}})\b'
)

# Trailing whitespace
TRAILING_SPACE_RE = re.compile(r'[ \t]+$')

# Domain/URL patterns for exclusion
DOMAIN_SUFFIXES = {
    # Common TLDs
    'com', 'org', 'net', 'io', 'co', 'uk', 'au', 'nz', 'ca', 'de', 'fr',
    'info', 'biz', 'edu', 'gov', 'app', 'dev', 'xyz', 'online', 'site',
    # Newer TLDs
    'ai', 'gg', 'tv', 'me', 'be', 'it', 'es', 'pl', 'nl', 'ru', 'jp',
    'cn', 'in', 'br', 'mx', 'za', 'ke', 'ng', 'ph', 'id', 'th', 'vn',
    'bet', 'casino', 'poker', 'games', 'club', 'live', 'win', 'money',
}

# Known abbreviations that look like missing-space issues
KNOWN_ABBREVS = {
    # Latin/common abbreviations
    'e.g.', 'i.e.', 'etc.', 'vs.', 'viz.', 'cf.',
    # Titles
    'dr.', 'mr.', 'mrs.', 'ms.', 'jr.', 'sr.', 'prof.',
    # Geographic/political
    'u.s.', 'u.k.', 'u.s.a.', 'e.u.',
    # Time
    'a.m.', 'p.m.', 'b.c.', 'a.d.',
    # Academic
    'ph.d.', 'm.d.', 'b.a.', 'm.a.', 'b.s.', 'm.s.',
    # Business/legal
    'inc.', 'ltd.', 'corp.', 'co.', 'llc.', 'plc.',
    'n.v.', 'b.v.', 's.a.', 'a.g.', 'gmbh.',  # International company suffixes
    # Units/addresses
    'no.', 'st.', 'ave.', 'blvd.', 'ft.', 'oz.', 'lb.', 'vol.', 'pp.',
    'apt.', 'dept.', 'fl.', 'ste.',
}


# =============================================================================
# CHECK IMPLEMENTATION
# =============================================================================

@register_check
class FormattingCheck(DeterministicCheck):
    """
    Checks mechanical formatting consistency.

    Detects:
    1. Double/multiple spaces
    2. Space before punctuation
    3. Missing space after punctuation
    4. Latin abbreviations (e.g., i.e., etc.)
    5. Unquoted UI elements
    6. Trailing whitespace
    """

    def _get_name(self) -> str:
        return "formatting"

    def _get_display_name(self) -> str:
        return "Formatting Check"

    def _get_category(self) -> Category:
        return "formatting"

    def _get_description(self) -> str:
        return (
            "Checks for whitespace issues, punctuation spacing, "
            "Latin abbreviations, and UI element quoting."
        )

    def _get_required_standards(self) -> tuple[str, ...]:
        return ()  # No required standards - always runs

    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """Find formatting issues in the document."""
        findings: list[Finding] = []

        # Process paragraphs (all sub-checks)
        for para in document.paragraphs():
            findings.extend(self._check_element(para, document, "paragraph"))

        # Process headings (whitespace + latin abbrev, no UI quoting)
        for heading in document.headings():
            findings.extend(self._check_element(heading, document, "heading"))

        # Process list items (whitespace only)
        for lst in document.lists():
            for item in lst.items:
                findings.extend(self._check_whitespace_only(item, document, "list_item"))

        # Process table cells (whitespace only)
        for table in document.tables():
            for row in table.rows:
                for cell in row.cells:
                    findings.extend(self._check_whitespace_only(cell, document, "table_cell"))

        return findings

    # =========================================================================
    # ELEMENT CHECKING
    # =========================================================================

    def _check_element(
        self,
        element: Any,
        document: Document,
        element_type: str,
    ) -> list[Finding]:
        """Run all applicable sub-checks for an element."""
        findings: list[Finding] = []
        text = element.text

        if not text:
            return findings

        # Whitespace checks (all elements)
        findings.extend(self._check_double_spaces(element, document, element_type))
        findings.extend(self._check_space_before_punct(element, document, element_type))
        findings.extend(self._check_missing_space_after(element, document, element_type))
        findings.extend(self._check_trailing_whitespace(element, document, element_type))

        # Latin abbreviations (paragraphs and headings)
        if element_type in ("paragraph", "heading"):
            findings.extend(self._check_latin_abbrevs(element, document, element_type))

        # UI quoting (paragraphs only)
        # NOTE: Disabled by default - too many false positives in corpus validation
        # (flags country names, section headings, etc. as UI elements)
        # Uncomment to enable: findings.extend(self._check_ui_quoting(element, document, element_type))
        # if element_type == "paragraph":
        #     findings.extend(self._check_ui_quoting(element, document, element_type))

        return findings

    def _check_whitespace_only(
        self,
        element: Any,
        document: Document,
        element_type: str,
    ) -> list[Finding]:
        """Run only whitespace sub-checks (for list items/table cells)."""
        findings: list[Finding] = []
        text = element.text

        if not text:
            return findings

        findings.extend(self._check_double_spaces(element, document, element_type))
        findings.extend(self._check_space_before_punct(element, document, element_type))
        findings.extend(self._check_missing_space_after(element, document, element_type))
        findings.extend(self._check_trailing_whitespace(element, document, element_type))

        return findings

    # =========================================================================
    # SUB-CHECK 1: DOUBLE SPACES
    # =========================================================================

    def _check_double_spaces(
        self,
        element: Any,
        document: Document,
        element_type: str,
    ) -> list[Finding]:
        """Find double/multiple spaces and propose collapsing to single."""
        findings: list[Finding] = []
        text = element.text

        for match in DOUBLE_SPACE_RE.finditer(text):
            abs_start = element.start_offset + match.start()
            abs_end = element.start_offset + match.end()
            location = document.location_for_span(abs_start, abs_end)

            findings.append(FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="suggestion",
                confidence=0.95,
                location=location,
                original_text=match.group(0),
                proposed_text=' ',
                reasoning="Multiple consecutive spaces should be collapsed to a single space.",
                auto_applicable=True,
                metadata={
                    "sub_check": "double_space",
                    "element_type": element_type,
                    "space_count": len(match.group(0)),
                },
            ))

        return findings

    # =========================================================================
    # SUB-CHECK 2: SPACE BEFORE PUNCTUATION
    # =========================================================================

    def _check_space_before_punct(
        self,
        element: Any,
        document: Document,
        element_type: str,
    ) -> list[Finding]:
        """Find space before punctuation and propose removal."""
        findings: list[Finding] = []
        text = element.text

        for match in SPACE_BEFORE_PUNCT_RE.finditer(text):
            # Get the full match and the punctuation
            full_match = match.group(0)

            # Skip if this is part of an ellipsis
            match_start = match.start()
            match_end = match.end()

            # Check for ellipsis context
            if self._is_ellipsis_context(text, match_start, match_end):
                continue

            # The fix is just the punctuation without the space
            punct = match.group(1) or match.group(2).strip()
            proposed = punct

            abs_start = element.start_offset + match_start
            abs_end = element.start_offset + match_end
            location = document.location_for_span(abs_start, abs_end)

            findings.append(FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="suggestion",
                confidence=0.95,
                location=location,
                original_text=full_match,
                proposed_text=proposed,
                reasoning=f"Remove space before '{punct}'.",
                auto_applicable=True,
                metadata={
                    "sub_check": "space_before_punct",
                    "element_type": element_type,
                    "punctuation": punct,
                },
            ))

        return findings

    def _is_ellipsis_context(self, text: str, start: int, end: int) -> bool:
        """Check if match is part of an ellipsis '...'."""
        # Check if there are periods before or after that form ellipsis
        before = text[max(0, start - 2):start]
        after = text[end:end + 2]
        return '..' in before or '..' in after

    # =========================================================================
    # SUB-CHECK 3: MISSING SPACE AFTER PUNCTUATION
    # =========================================================================

    def _check_missing_space_after(
        self,
        element: Any,
        document: Document,
        element_type: str,
    ) -> list[Finding]:
        """Find missing space after punctuation."""
        findings: list[Finding] = []
        text = element.text

        for match in MISSING_SPACE_RE.finditer(text):
            punct = match.group(1)
            letter = match.group(2)
            match_start = match.start()

            # Check for false positives
            is_false_positive, is_ambiguous = self._check_missing_space_false_positive(
                text, match_start, punct, letter
            )

            if is_false_positive:
                continue

            # Build proposed fix
            original = match.group(0)
            proposed = f"{punct} {letter}"

            abs_start = element.start_offset + match_start
            abs_end = element.start_offset + match.end()
            location = document.location_for_span(abs_start, abs_end)

            # Ambiguous cases become proposals
            auto_applicable = not is_ambiguous
            confidence = 0.90 if auto_applicable else 0.60

            findings.append(FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="suggestion",
                confidence=confidence,
                location=location,
                original_text=original,
                proposed_text=proposed,
                reasoning=(
                    f"Add space after '{punct}'."
                    if auto_applicable else
                    f"Possibly missing space after '{punct}'. Verify this isn't a domain, abbreviation, or number."
                ),
                auto_applicable=auto_applicable,
                metadata={
                    "sub_check": "missing_space_after",
                    "element_type": element_type,
                    "punctuation": punct,
                    "ambiguous": is_ambiguous,
                },
            ))

        return findings

    def _check_missing_space_false_positive(
        self,
        text: str,
        match_pos: int,
        punct: str,
        letter: str,
    ) -> tuple[bool, bool]:
        """
        Check if this is a false positive for missing-space-after.

        Returns (is_false_positive, is_ambiguous).
        - is_false_positive: definitely skip this match
        - is_ambiguous: emit as proposal, not auto
        """
        # Get surrounding context
        text_lower = text.lower()

        # 1. Check for decimal numbers (digit before period)
        if punct == '.' and match_pos > 0:
            if text[match_pos - 1].isdigit():
                return (True, False)

        # 2. Check for thousands separators (digit,digits)
        if punct == ',' and match_pos > 0:
            if text[match_pos - 1].isdigit():
                # Check if followed by digits
                after = text[match_pos + 1:match_pos + 5]
                if after and after[0].isdigit():
                    return (True, False)

        # 3. Check for domain patterns
        if punct == '.':
            # Get the part after the period
            after_punct = text[match_pos + 1:].split()[0] if match_pos + 1 < len(text) else ""
            after_lower = after_punct.lower()

            # Check if it's a known TLD
            for tld in DOMAIN_SUFFIXES:
                if after_lower.startswith(tld):
                    return (True, False)

            # Check for file extensions
            if after_lower in ('docx', 'pdf', 'xlsx', 'jpg', 'png', 'html', 'css', 'js', 'py'):
                return (True, False)

        # 4. Check for known abbreviations
        # Look back to capture the full potential abbreviation
        lookback = text_lower[max(0, match_pos - 4):match_pos + 3]
        for abbrev in KNOWN_ABBREVS:
            if abbrev in lookback:
                return (True, False)

        # 5. Check for version numbers (v1.2, 2.0.1)
        if punct == '.' and match_pos > 0:
            before = text[max(0, match_pos - 3):match_pos]
            if re.search(r'v?\d+$', before, re.IGNORECASE):
                return (True, False)

        # 6. Check for URLs
        # Look for http/https/www before
        lookback_url = text_lower[max(0, match_pos - 20):match_pos]
        if 'http' in lookback_url or 'www.' in lookback_url:
            return (True, False)

        # 7. Check for email patterns
        if '@' in text[max(0, match_pos - 30):match_pos + 30]:
            # Might be part of email domain
            return (False, True)  # Ambiguous

        # 8. Check if letter after could start a domain
        # e.g., "bet.com" - single letter + common TLD
        if punct == '.':
            word_after = ''
            for i in range(match_pos + 1, min(len(text), match_pos + 15)):
                if text[i].isalnum():
                    word_after += text[i].lower()
                else:
                    break
            if word_after in DOMAIN_SUFFIXES:
                return (True, False)

        # Not a clear false positive
        return (False, False)

    # =========================================================================
    # SUB-CHECK 4: LATIN ABBREVIATIONS
    # =========================================================================

    def _check_latin_abbrevs(
        self,
        element: Any,
        document: Document,
        element_type: str,
    ) -> list[Finding]:
        """Find Latin abbreviations and propose replacements."""
        findings: list[Finding] = []
        text = element.text

        for match in LATIN_ABBREV_RE.finditer(text):
            abbrev = match.group(1).lower()
            replacement = LATIN_REPLACEMENTS.get(abbrev, '[replace]')

            abs_start = element.start_offset + match.start()
            abs_end = element.start_offset + match.end()
            location = document.location_for_span(abs_start, abs_end)

            findings.append(FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="warning",
                confidence=0.85,
                location=location,
                original_text=match.group(0),
                proposed_text=replacement,
                reasoning=(
                    f"Avoid Latin abbreviation '{match.group(0)}'. "
                    f"Consider using '{replacement}' instead."
                ),
                auto_applicable=False,  # Always proposal - contextual replacement
                metadata={
                    "sub_check": "latin_abbrev",
                    "element_type": element_type,
                    "abbreviation": abbrev,
                    "suggestion": replacement,
                },
            ))

        return findings

    # =========================================================================
    # SUB-CHECK 5: UI ELEMENT QUOTING
    # =========================================================================

    def _check_ui_quoting(
        self,
        element: Any,
        document: Document,
        element_type: str,
    ) -> list[Finding]:
        """Find unquoted UI elements after action verbs."""
        findings: list[Finding] = []
        text = element.text

        for match in UI_ELEMENT_RE.finditer(text):
            verb = match.group(1)
            ui_element = match.group(2)

            # Skip if it looks like a common word, not a UI element
            if self._is_common_word(ui_element):
                continue

            # Build proposed fix with quotes
            original = match.group(0)
            proposed = f"{verb} '{ui_element}'"

            abs_start = element.start_offset + match.start()
            abs_end = element.start_offset + match.end()
            location = document.location_for_span(abs_start, abs_end)

            findings.append(FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="suggestion",
                confidence=0.55,  # Low confidence - hard to distinguish
                location=location,
                original_text=original,
                proposed_text=proposed,
                reasoning=(
                    f"UI element '{ui_element}' may need quotes for clarity."
                ),
                auto_applicable=False,  # Always proposal
                metadata={
                    "sub_check": "ui_quoting",
                    "element_type": element_type,
                    "action_verb": verb.lower(),
                    "ui_element": ui_element,
                },
            ))

        return findings

    def _is_common_word(self, word: str) -> bool:
        """Check if word is too common to be a UI element."""
        # Common words that might follow action verbs but aren't UI elements
        common = {
            'the', 'a', 'an', 'your', 'my', 'our', 'their', 'this', 'that',
            'here', 'there', 'now', 'any', 'all', 'some', 'one', 'two',
            'new', 'more', 'most', 'other', 'another', 'each', 'every',
        }
        return word.lower() in common

    # =========================================================================
    # SUB-CHECK 6: TRAILING WHITESPACE
    # =========================================================================

    def _check_trailing_whitespace(
        self,
        element: Any,
        document: Document,
        element_type: str,
    ) -> list[Finding]:
        """Find trailing whitespace and propose removal."""
        findings: list[Finding] = []
        text = element.text

        match = TRAILING_SPACE_RE.search(text)
        if match:
            abs_start = element.start_offset + match.start()
            abs_end = element.start_offset + match.end()
            location = document.location_for_span(abs_start, abs_end)

            findings.append(FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="suggestion",
                confidence=0.95,
                location=location,
                original_text=match.group(0),
                proposed_text='',
                reasoning="Remove trailing whitespace.",
                auto_applicable=True,
                metadata={
                    "sub_check": "trailing_whitespace",
                    "element_type": element_type,
                    "whitespace_count": len(match.group(0)),
                },
            ))

        return findings
