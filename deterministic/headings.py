"""
Pitboss v4 - Headings Check

Deterministic check for heading formatting issues:
1. Blank line before heading (auto-applicable)
2. Question mark removal (auto-applicable except FAQ sections)
3. Capitalization (brand-specific, cautious auto-apply)
4. Descriptive heading detection (flag only)
5. Hierarchy validation (flag only)

High-value check - heading edits are a large share of mechanical editing.
"""

from __future__ import annotations
import re
from typing import Any, Optional

from wordfreq import word_frequency

from core.check_base import DeterministicCheck, register_check
from core.document import Document, Heading, Paragraph, HeadingLevel, BlockElement
from core.finding import Finding, FindingFactory, Category


# =============================================================================
# DICTIONARY LOOKUP
# =============================================================================

# Function words that are always safe to recase
FUNCTION_WORDS = {
    'a', 'an', 'the', 'of', 'to', 'for', 'in', 'on', 'at', 'by',
    'and', 'or', 'but', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'can', 'if', 'so', 'as', 'it', 'we', 'you', 'i',
    'not', 'no', 'yes', 'all', 'any', 'some', 'each', 'every', 'this', 'that',
    'these', 'those', 'my', 'your', 'his', 'her', 'its', 'our', 'their',
    'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how',
}

# Frequency threshold: words above this are common English words
# word_frequency returns 0 for unknown words, ~1e-3 for very common words
WORD_FREQUENCY_THRESHOLD = 1e-7


def _is_dictionary_word(word: str) -> bool:
    """
    Check if word is a common English dictionary word.

    Uses wordfreq library to check word frequency.
    Words above the frequency threshold are considered dictionary words.
    """
    word_lower = word.lower()

    # Function words are always safe
    if word_lower in FUNCTION_WORDS:
        return True

    # Strip possessive suffix
    if word_lower.endswith("'s"):
        word_lower = word_lower[:-2]
    elif word_lower.endswith("s'"):
        word_lower = word_lower[:-2]

    # Check word frequency
    freq = word_frequency(word_lower, 'en')
    if freq > WORD_FREQUENCY_THRESHOLD:
        return True

    # Try without trailing 's' for plurals (if word is long enough)
    if len(word_lower) > 3 and word_lower.endswith('s'):
        base = word_lower[:-1]
        freq = word_frequency(base, 'en')
        if freq > WORD_FREQUENCY_THRESHOLD:
            return True

    return False


# =============================================================================
# CONSTANTS
# =============================================================================

# Articles and short prepositions/conjunctions for title case
# These should be lowercase unless first or last word
TITLE_CASE_LOWERCASE = {
    'a', 'an', 'the',           # Articles
    'of', 'to', 'for', 'in',    # Prepositions
    'on', 'at', 'by', 'with',
    'and', 'or', 'but', 'nor',  # Conjunctions
    'as', 'if', 'so', 'yet',
}

# Known acronyms that should preserve their case
KNOWN_ACRONYMS = {
    'iOS', 'VIP', 'FAQ', 'RNG', 'APK', 'SSL', 'RTP',
    'UK', 'US', 'CA', 'NZ', 'AU', 'EU',
    'HTML', 'CSS', 'API', 'URL', 'ID',
    'ATM', 'PIN', 'SMS', 'OTP', 'KYC', 'PWA', 'AI',
}

# Lowercase versions for detection
KNOWN_ACRONYMS_LOWER = {a.lower() for a in KNOWN_ACRONYMS}

# Known proper nouns (OS names, game providers, common brands)
# These should never be lowercased in sentence case
KNOWN_PROPER_NOUNS = {
    # Operating systems
    'Android', 'Windows', 'Mac', 'Linux',
    # Game providers
    'Pragmatic', 'Evolution', 'NetEnt', 'Microgaming', 'Playtech',
    'Betsoft', 'Quickspin', 'Yggdrasil', 'Thunderkick', 'Hacksaw',
    'Nolimit', 'Relax', 'Push', 'ELK', 'Big Time Gaming',
    # Common proper nouns in iGaming
    'Bitcoin', 'Ethereum', 'Tether', 'Litecoin', 'Dogecoin',
    'Visa', 'Mastercard', 'Interac', 'PayPal', 'Skrill', 'Neteller',
    'Canada', 'Canadian', 'Australia', 'Australian',
}

# Lowercase versions for detection
KNOWN_PROPER_NOUNS_LOWER = {p.lower() for p in KNOWN_PROPER_NOUNS}

# Generic headings that are not descriptive enough
GENERIC_HEADINGS = {
    'promotions', 'bonuses', 'bonus', 'games', 'slots', 'support',
    'banking', 'payments', 'deposit', 'withdrawal', 'withdrawals',
    'conclusion', 'summary', 'overview', 'introduction',
    'features', 'options', 'security', 'safety', 'licensing',
    'contacts', 'contact', 'help', 'faq', 'faqs',
}

# FAQ-related keywords in section titles
FAQ_KEYWORDS = {'faq', 'faqs', 'frequently asked', 'questions', 'q&a'}

# Interrogative words that suggest a question heading
INTERROGATIVE_STARTERS = {'is', 'are', 'can', 'do', 'does', 'how', 'what', 'why', 'when', 'where', 'will', 'should'}


# =============================================================================
# CHECK IMPLEMENTATION
# =============================================================================

@register_check
class HeadingsCheck(DeterministicCheck):
    """
    Checks heading formatting issues.

    Sub-checks:
    1. Blank line before heading (auto-applicable)
    2. Question mark in non-FAQ headings (auto-applicable with exceptions)
    3. Capitalization (brand-specific, cautious auto-apply)
    4. Descriptive heading (flag only)
    5. Hierarchy validation (flag only)
    """

    def _get_name(self) -> str:
        return "headings"

    def _get_display_name(self) -> str:
        return "Headings Check"

    def _get_category(self) -> Category:
        return "headings"

    def _get_description(self) -> str:
        return (
            "Checks heading formatting: blank lines, question marks, "
            "capitalization, descriptive titles, and hierarchy."
        )

    def _get_required_standards(self) -> tuple[str, ...]:
        return ("headings.capitalization", "headings.no_question_marks")

    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """Find heading issues in the document."""
        findings: list[Finding] = []

        # Build FAQ section detection
        faq_section_offsets = self._find_faq_sections(document)

        prev_element: Optional[BlockElement] = None
        seen_levels: set[int] = set()
        h1_count = 0
        prev_level: Optional[int] = None

        for element in document.elements:
            if isinstance(element, Heading):
                # Sub-check 1: Blank line before heading
                findings.extend(
                    self._check_blank_line(element, prev_element, document)
                )

                # Sub-check 2: Question mark
                if standards.headings.no_question_marks:
                    findings.extend(
                        self._check_question_mark(element, faq_section_offsets, document)
                    )

                # Sub-check 3: Capitalization
                findings.extend(
                    self._check_capitalization(element, standards, document)
                )

                # Sub-check 4: Descriptive heading
                if standards.headings.descriptive_required:
                    findings.extend(
                        self._check_descriptive(element, document)
                    )

                # Sub-check 5: Hierarchy (track for document-level check)
                if element.level == HeadingLevel.H1:
                    h1_count += 1

                # Check for skipped levels
                current_level = element.level.value
                if prev_level is not None and current_level > prev_level + 1:
                    findings.extend(
                        self._create_skipped_level_finding(
                            element, prev_level, current_level, document
                        )
                    )

                seen_levels.add(current_level)
                prev_level = current_level

            prev_element = element

        # Document-level hierarchy check: multiple H1s
        if h1_count > 1:
            findings.extend(self._create_multiple_h1_finding(document, h1_count))

        return findings

    # =========================================================================
    # SUB-CHECK 1: BLANK LINE BEFORE HEADING
    # =========================================================================

    def _check_blank_line(
        self,
        heading: Heading,
        prev_element: Optional[BlockElement],
        document: Document,
    ) -> list[Finding]:
        """Check if heading is preceded by a blank line."""
        if prev_element is None:
            # First element - no blank line needed
            return []

        # Gap of 1 = just a newline, no blank line
        # Gap of 2+ = has blank line(s)
        gap = heading.start_offset - prev_element.end_offset
        if gap <= 1:
            # Missing blank line
            location = document.location_for_span(
                heading.start_offset, heading.end_offset
            )

            return [FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="suggestion",
                confidence=0.95,
                location=location,
                original_text=heading.text,
                proposed_text=heading.text,  # Text unchanged, format change
                reasoning=(
                    f"Add a blank line before this heading for better readability. "
                    f"Headings should be visually separated from preceding content."
                ),
                auto_applicable=True,
                metadata={
                    "sub_check": "blank_line",
                    "heading_level": heading.level.value,
                },
            )]

        return []

    # =========================================================================
    # SUB-CHECK 2: QUESTION MARK
    # =========================================================================

    def _find_faq_sections(self, document: Document) -> set[tuple[int, int]]:
        """
        Find offset ranges of FAQ sections.

        Returns set of (start_offset, end_offset) tuples for sections
        whose heading contains FAQ-related keywords.
        """
        faq_ranges: set[tuple[int, int]] = set()

        for section in document.all_sections_flat():
            title_lower = section.title.lower()
            if any(kw in title_lower for kw in FAQ_KEYWORDS):
                faq_ranges.add((section.start_offset, section.end_offset))

        return faq_ranges

    def _is_in_faq_section(
        self,
        heading: Heading,
        faq_section_offsets: set[tuple[int, int]],
    ) -> bool:
        """Check if heading is within an FAQ section."""
        for start, end in faq_section_offsets:
            if start <= heading.start_offset < end:
                return True
        return False

    def _is_faq_like_heading(self, heading: Heading) -> bool:
        """
        Check if heading looks like an FAQ question.

        "How to Register" is an INSTRUCTIONAL pattern, not FAQ-like.
        "Is this legal?" or "How much can I deposit?" are FAQ-like.
        """
        text_lower = heading.text.lower().strip()
        words = text_lower.split()
        if not words:
            return False

        first_word = words[0]

        # "How to..." is instructional, not FAQ
        if first_word == "how" and len(words) > 1 and words[1] == "to":
            return False

        # Other interrogatives are FAQ-like
        return first_word in INTERROGATIVE_STARTERS

    def _check_question_mark(
        self,
        heading: Heading,
        faq_section_offsets: set[tuple[int, int]],
        document: Document,
    ) -> list[Finding]:
        """Check for question marks in non-FAQ headings."""
        if not heading.text.rstrip().endswith('?'):
            return []

        # Check if in FAQ section
        in_faq = self._is_in_faq_section(heading, faq_section_offsets)
        is_faq_like = self._is_faq_like_heading(heading)

        if in_faq:
            # Legitimate FAQ question - no finding
            return []

        location = document.location_for_span(
            heading.start_offset, heading.end_offset
        )

        # Remove trailing question mark(s) and whitespace
        proposed = heading.text.rstrip().rstrip('?').rstrip()

        if is_faq_like and not in_faq:
            # Looks like a question but not in FAQ section - ambiguous
            # Emit as proposal, not auto-apply
            return [FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="warning",
                confidence=0.6,
                location=location,
                original_text=heading.text,
                proposed_text=proposed,
                reasoning=(
                    f"This heading ends with a question mark but may be a legitimate "
                    f"FAQ-style question. Review whether it should be in an FAQ section "
                    f"or if the question mark should be removed."
                ),
                auto_applicable=False,
                metadata={
                    "sub_check": "question_mark",
                    "context": "ambiguous_faq",
                },
            )]
        else:
            # Non-FAQ heading with question mark - auto-remove
            return [FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="warning",
                confidence=0.9,
                location=location,
                original_text=heading.text,
                proposed_text=proposed,
                reasoning=(
                    f"Remove the question mark from this heading. "
                    f"Headings should be statements, not questions "
                    f"(except in FAQ sections)."
                ),
                auto_applicable=True,
                metadata={
                    "sub_check": "question_mark",
                    "context": "non_faq",
                },
            )]

    # =========================================================================
    # SUB-CHECK 3: CAPITALIZATION
    # =========================================================================

    def _check_capitalization(
        self,
        heading: Heading,
        standards: Any,
        document: Document,
    ) -> list[Finding]:
        """Check heading capitalization against brand standard."""
        cap_standard = standards.headings.capitalization
        if not cap_standard:
            # No capitalization standard set - skip
            return []

        text = heading.text.strip()
        if not text:
            return []

        # Determine expected case
        if cap_standard == "title_case":
            expected = self._to_title_case(text)
        elif cap_standard == "sentence_case":
            expected = self._to_sentence_case(text)
        else:
            return []

        # Check if already correct
        if text == expected:
            return []

        # Check if heading contains acronyms or proper nouns
        has_special_words = self._has_special_words(text)

        # Check if heading is a question (interrogative + ends with ?)
        # These are often FAQ items that slipped context detection
        is_question_heading = self._is_question_heading(text)

        location = document.location_for_span(
            heading.start_offset, heading.end_offset
        )

        # Route to proposal if special words OR question heading
        if has_special_words or is_question_heading:
            reason_detail = ""
            if has_special_words and is_question_heading:
                reason_detail = "Contains proper nouns/acronyms and is a question heading"
            elif has_special_words:
                reason_detail = "Contains words that may be proper nouns or acronyms"
            else:
                reason_detail = "Question-style heading may be an FAQ item"

            return [FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="warning",
                confidence=0.5,
                location=location,
                original_text=text,
                proposed_text=expected,
                reasoning=(
                    f"This heading may not match the brand's {cap_standard.replace('_', ' ')} "
                    f"standard. {reason_detail} - "
                    f"verify the suggested conversion preserves correct casing."
                ),
                auto_applicable=False,
                metadata={
                    "sub_check": "capitalization",
                    "standard": cap_standard,
                    "has_special_words": has_special_words,
                    "is_question": is_question_heading,
                },
            )]
        else:
            # Auto-applicable - ordinary lowercase words only (except first)
            return [FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="warning",
                confidence=0.85,
                location=location,
                original_text=text,
                proposed_text=expected,
                reasoning=(
                    f"Convert this heading to {cap_standard.replace('_', ' ')} "
                    f"to match the brand standard."
                ),
                auto_applicable=True,
                metadata={
                    "sub_check": "capitalization",
                    "standard": cap_standard,
                    "has_special_words": False,
                    "is_question": False,
                },
            )]

    def _is_question_heading(self, text: str) -> bool:
        """
        Check if heading is a question (interrogative word + ends with ?).

        Question headings are often FAQ items that slipped section detection,
        so we route their capitalization to proposal rather than auto-apply.
        """
        text_stripped = text.strip()
        if not text_stripped.endswith('?'):
            return False

        words = text_stripped.lower().split()
        if not words:
            return False

        first_word = words[0]
        return first_word in INTERROGATIVE_STARTERS

    def _has_special_words(self, text: str) -> bool:
        """
        Check if text contains acronyms or likely proper nouns.

        Uses dictionary lookup to distinguish common words from proper nouns:
        - Dictionary words (games, casino, bonus) → safe to recase
        - Non-dictionary words (Vave, Koifortune, NetEnt) → likely proper nouns
        """
        words = re.findall(r'\b\w+\b', text)

        for i, word in enumerate(words):
            word_lower = word.lower()

            # Check for known acronyms (including first word)
            if word_lower in KNOWN_ACRONYMS_LOWER:
                return True

            # Check for known proper nouns (explicit list, belt-and-suspenders)
            if word_lower in KNOWN_PROPER_NOUNS_LOWER:
                return True

            # Check for all-caps words (likely acronyms)
            if len(word) >= 2 and word.isupper():
                return True

            # Check for mixed case (like iOS, eBay, iGaming)
            if not word.islower() and not word.isupper() and not word.istitle():
                return True

            # Skip first word for mid-heading capitalization check
            if i == 0:
                continue

            # Mid-heading capitalized word: check if it's a dictionary word
            if word[0].isupper():
                # Handle hyphenated words: check each part
                parts = word.split('-')
                for part in parts:
                    if part and not _is_dictionary_word(part):
                        # Unknown word = likely proper noun → proposal
                        return True

        return False

    def _to_title_case(self, text: str) -> str:
        """
        Convert text to title case.

        Capitalizes principal words, lowercases articles/prepositions
        unless first or last word. Preserves known acronyms.
        """
        words = text.split()
        if not words:
            return text

        result = []
        for i, word in enumerate(words):
            word_lower = word.lower()
            word_stripped = re.sub(r'[^\w]', '', word_lower)

            # Preserve known acronyms
            if word_stripped in KNOWN_ACRONYMS_LOWER:
                # Find the correct case from KNOWN_ACRONYMS
                for acronym in KNOWN_ACRONYMS:
                    if acronym.lower() == word_stripped:
                        # Preserve punctuation
                        result.append(word.replace(word_stripped, acronym)
                                      if word_stripped in word.lower() else acronym)
                        break
                else:
                    result.append(word.upper())
            elif i == 0 or i == len(words) - 1:
                # First or last word - always capitalize
                result.append(word.capitalize())
            elif word_stripped in TITLE_CASE_LOWERCASE:
                # Article/preposition - lowercase
                result.append(word.lower())
            else:
                # Regular word - capitalize
                result.append(word.capitalize())

        return ' '.join(result)

    def _to_sentence_case(self, text: str) -> str:
        """
        Convert text to sentence case.

        Capitalizes first word, preserves already-capitalized
        proper nouns and acronyms, lowercases others.
        """
        words = text.split()
        if not words:
            return text

        result = []
        for i, word in enumerate(words):
            word_lower = word.lower()
            word_stripped = re.sub(r'[^\w]', '', word_lower)

            # Check for known acronym FIRST (even for first word)
            if word_stripped in KNOWN_ACRONYMS_LOWER:
                # Known acronym - preserve correct case
                for acronym in KNOWN_ACRONYMS:
                    if acronym.lower() == word_stripped:
                        result.append(acronym)
                        break
                else:
                    result.append(word.upper())
            elif word.isupper() and len(word) >= 2:
                # All caps - likely acronym, preserve
                result.append(word)
            elif not word.islower() and not word.isupper() and not word.istitle():
                # Mixed case (like iOS) - preserve
                result.append(word)
            elif i == 0:
                # First word (non-acronym) - capitalize
                result.append(word.capitalize())
            else:
                # Regular word - lowercase
                result.append(word.lower())

        return ' '.join(result)

    # =========================================================================
    # SUB-CHECK 4: DESCRIPTIVE HEADING
    # =========================================================================

    def _check_descriptive(
        self,
        heading: Heading,
        document: Document,
    ) -> list[Finding]:
        """Check if heading is too generic."""
        text = heading.text.strip()
        text_lower = text.lower()

        # Check if single word and generic
        words = text.split()
        if len(words) == 1 and text_lower in GENERIC_HEADINGS:
            location = document.location_for_span(
                heading.start_offset, heading.end_offset
            )

            return [FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="suggestion",
                confidence=0.6,
                location=location,
                original_text=text,
                proposed_text=None,  # No auto-fix
                reasoning=(
                    f"The heading '{text}' is too generic. "
                    f"Consider making it more descriptive to help readers "
                    f"understand what this section covers."
                ),
                auto_applicable=False,
                metadata={
                    "sub_check": "descriptive",
                },
            )]

        return []

    # =========================================================================
    # SUB-CHECK 5: HIERARCHY
    # =========================================================================

    def _create_skipped_level_finding(
        self,
        heading: Heading,
        prev_level: int,
        current_level: int,
        document: Document,
    ) -> list[Finding]:
        """Create finding for skipped heading level."""
        location = document.location_for_span(
            heading.start_offset, heading.end_offset
        )

        skipped = current_level - prev_level - 1
        skipped_levels = [f"H{prev_level + i + 1}" for i in range(skipped)]

        return [FindingFactory.create(
            check_name=self.name,
            category=self.category,
            severity="warning",
            confidence=0.8,
            location=location,
            original_text=heading.text,
            proposed_text=None,  # No auto-fix
            reasoning=(
                f"Heading hierarchy skips from H{prev_level} to H{current_level}, "
                f"missing {', '.join(skipped_levels)}. "
                f"Consider using proper heading hierarchy for accessibility."
            ),
            auto_applicable=False,
            metadata={
                "sub_check": "hierarchy",
                "issue": "skipped_level",
                "from_level": prev_level,
                "to_level": current_level,
            },
        )]

    def _create_multiple_h1_finding(
        self,
        document: Document,
        h1_count: int,
    ) -> list[Finding]:
        """Create finding for multiple H1 headings."""
        # Find the first H1 for location
        first_h1 = None
        for element in document.elements:
            if isinstance(element, Heading) and element.level == HeadingLevel.H1:
                first_h1 = element
                break

        if not first_h1:
            return []

        location = document.location_for_span(
            first_h1.start_offset, first_h1.end_offset
        )

        return [FindingFactory.create(
            check_name=self.name,
            category=self.category,
            severity="warning",
            confidence=0.8,
            location=location,
            original_text=first_h1.text,
            proposed_text=None,
            reasoning=(
                f"Document has {h1_count} H1 headings. "
                f"Typically a document should have only one H1 (the main title). "
                f"Consider demoting extra H1s to H2."
            ),
            auto_applicable=False,
            metadata={
                "sub_check": "hierarchy",
                "issue": "multiple_h1",
                "h1_count": h1_count,
            },
        )]
