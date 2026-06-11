"""
Pitboss v4 - Voice Check: Third Person to Second Person

Deterministic check that converts third-person reader references to second person.
Uses person_reference.py classifier for intelligent three-way classification:
- READER_REF: Auto-convertible with high confidence (0.95)
- GENERIC_NOUN: Skipped entirely (population references, never convert)
- UNCLEAR: Proposal with low confidence (0.4), auto_applicable=False

This is the highest-value deterministic check (~40% of editing volume).
"""

from __future__ import annotations
import re
from typing import Any, Optional

from core.check_base import DeterministicCheck, register_check
from core.document import Document, Paragraph
from core.finding import Finding, FindingFactory, Category
from core.person_reference import (
    classify_person_references,
    PersonReference,
    PersonRefType,
)


# =============================================================================
# CONVERSION RULES
# =============================================================================

# Subject/object form conversions (all map to "you")
CONVERSION_RULES: dict[str, str] = {
    "players": "you",
    "player": "you",
    "users": "you",
    "user": "you",
    "punters": "you",
    "punter": "you",
    "bettors": "you",
    "bettor": "you",
    "customers": "you",
    "customer": "you",
    "gamblers": "you",
    "gambler": "you",
}

# Possessive conversions (all map to "your")
POSSESSIVE_PATTERNS: list[tuple[str, str]] = [
    # Standard apostrophe
    ("player's", "your"),
    ("players'", "your"),
    ("user's", "your"),
    ("users'", "your"),
    ("punter's", "your"),
    ("punters'", "your"),
    ("bettor's", "your"),
    ("bettors'", "your"),
    ("customer's", "your"),
    ("customers'", "your"),
    ("gambler's", "your"),
    ("gamblers'", "your"),
    # Curly apostrophe (Unicode U+2019)
    ("player\u2019s", "your"),
    ("players\u2019", "your"),
    ("user\u2019s", "your"),
    ("users\u2019", "your"),
    ("punter\u2019s", "your"),
    ("punters\u2019", "your"),
    ("bettor\u2019s", "your"),
    ("bettors\u2019", "your"),
    ("customer\u2019s", "your"),
    ("customers\u2019", "your"),
    ("gambler\u2019s", "your"),
    ("gamblers\u2019", "your"),
]

# Verb agreement fixes when converting singular nouns to "you"
# Singular nouns use singular verbs; "you" uses plural verb forms
VERB_AGREEMENT_FIXES: dict[str, str] = {
    "has": "have",
    "is": "are",
    "was": "were",
    "does": "do",
}

# Singular nouns that need verb agreement fixes
SINGULAR_NOUNS = {"player", "user", "punter", "bettor", "customer", "gambler"}

# Articles that can be stripped before third-person nouns
ARTICLE_PATTERNS = [
    (r"\bthe\s+", ""),  # "the player" -> "you"
    (r"\ba\s+", ""),    # "a player" -> "you"
    (r"\ban\s+", ""),   # "an user" (rare but handle it)
]

# Sentence boundary pattern
SENTENCE_PATTERN = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')


# =============================================================================
# CHECK IMPLEMENTATION
# =============================================================================

@register_check
class VoiceThirdPersonCheck(DeterministicCheck):
    """
    Converts third-person reader references to second person.

    Uses person_reference.py classifier to identify:
    - READER_REF: Auto-convertible with high confidence (0.95)
    - GENERIC_NOUN: Skipped entirely (never convert population references)
    - UNCLEAR: Proposal with low confidence (0.4), auto_applicable=False

    Body paragraphs only - skips headings and table cells per requirements.
    """

    def _get_name(self) -> str:
        return "voice.third_person"

    def _get_display_name(self) -> str:
        return "Third Person to Second Person"

    def _get_category(self) -> Category:
        return "voice"

    def _get_description(self) -> str:
        return (
            "Converts third-person reader references (players, users, etc.) "
            "to second person (you, your). Handles subject/object forms, "
            "possessives, and verb agreement."
        )

    def _get_required_standards(self) -> tuple[str, ...]:
        return ("voice.person",)

    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """
        Find third-person reader references and generate conversion Findings.

        Args:
            document: The document to check
            standards: Standards with voice.person setting

        Returns:
            List of Findings for voice conversions
        """
        # Early exit: if brand wants third-person voice, no-op
        if standards.voice.person != "second":
            return []

        findings: list[Finding] = []

        # Process body paragraphs only (skip headings, tables)
        for para in document.paragraphs():
            para_findings = self._process_paragraph(para, document)
            findings.extend(para_findings)

        return findings

    def _process_paragraph(
        self,
        para: Paragraph,
        document: Document,
    ) -> list[Finding]:
        """Process a single paragraph for voice conversions."""
        findings: list[Finding] = []

        # Split into sentences
        sentences = self._split_sentences(para.text)

        current_pos = 0
        for sentence in sentences:
            # Find sentence position in paragraph
            sentence_start = para.text.find(sentence, current_pos)
            if sentence_start == -1:
                continue

            # Classify references in this sentence
            refs = classify_person_references(sentence)

            for ref in refs:
                # Skip GENERIC_NOUN entirely
                if ref.ref_type == PersonRefType.GENERIC_NOUN:
                    continue

                # Create finding for READER_REF or UNCLEAR
                finding = self._create_finding_for_reference(
                    ref=ref,
                    sentence=sentence,
                    para=para,
                    sentence_offset_in_para=sentence_start,
                    document=document,
                )
                if finding:
                    findings.append(finding)

            current_pos = sentence_start + len(sentence)

        return findings

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences, preserving original text."""
        if not text.strip():
            return []

        # Split on sentence boundaries
        parts = SENTENCE_PATTERN.split(text)

        # Return non-empty parts
        return [p for p in parts if p.strip()]

    def _create_finding_for_reference(
        self,
        ref: PersonReference,
        sentence: str,
        para: Paragraph,
        sentence_offset_in_para: int,
        document: Document,
    ) -> Optional[Finding]:
        """Create a Finding for a single reference."""
        # Check if this is a complex conversion
        is_complex = self._is_complex_conversion(sentence, ref)

        # Perform conversion
        converted_sentence, conversion_success = self._convert_sentence(sentence, ref)

        if not conversion_success or converted_sentence == sentence:
            return None

        # Calculate absolute offsets for the sentence
        abs_start = para.start_offset + sentence_offset_in_para
        abs_end = abs_start + len(sentence)

        # Get location
        location = document.location_for_span(abs_start, abs_end)

        # Determine confidence and auto_applicable based on ref_type
        if ref.ref_type == PersonRefType.READER_REF:
            confidence = 0.95
            # Auto-applicable only if not complex
            auto_applicable = not is_complex
        else:  # UNCLEAR
            confidence = 0.4
            auto_applicable = False

        # Build reasoning
        if ref.ref_type == PersonRefType.READER_REF:
            if is_complex:
                reasoning = (
                    f"Convert third-person reference '{ref.word}' to second person 'you'. "
                    f"This sentence has complex structure requiring review - "
                    f"suggested conversion may need adjustment."
                )
            else:
                reasoning = (
                    f"Convert third-person reference '{ref.word}' to second person 'you'. "
                    f"This addresses the reader directly, aligning with the brand's "
                    f"second-person voice standard."
                )
        else:  # UNCLEAR
            reasoning = (
                f"Possible third-person reference '{ref.word}' detected. "
                f"Context is ambiguous - manual review recommended. "
                f"Suggested conversion to 'you' provided but requires human verification."
            )

        return FindingFactory.create(
            check_name=self.name,
            category=self.category,
            severity="warning",
            confidence=confidence,
            location=location,
            original_text=sentence,
            proposed_text=converted_sentence,
            reasoning=reasoning,
            auto_applicable=auto_applicable,
            metadata={
                "source_pronoun": ref.word,
                "target_pronoun": "you",
                "ref_type": ref.ref_type.value,
            },
        )

    def _is_complex_conversion(self, sentence: str, ref: PersonReference) -> bool:
        """
        Detect sentences that can't convert cleanly.

        Complex cases that require manual review:
        1. Reflexive constructions: "players themselves"
        2. Comparative constructions: "more than other players"
        3. Multiple refs with mixed classifications in same sentence
        """
        # Check for reflexive/emphatic pronouns
        reflexive_pattern = (
            r'\b(players?|users?|punters?|bettors?|customers?|gamblers?)'
            r'\s+(themselves|himself|herself|themself)\b'
        )
        if re.search(reflexive_pattern, sentence, re.IGNORECASE):
            return True

        # Check for comparative with "than other/some/many/most players"
        # Be specific to avoid false positives like "more than 10,500...players"
        comparative_pattern = (
            r'\bthan\s+(other|some|many|most|certain|different)\s+'
            r'(players?|users?|punters?|bettors?|customers?|gamblers?)\b'
        )
        if re.search(comparative_pattern, sentence, re.IGNORECASE):
            return True

        # Check for relative clause - "players who/that/whom" can't swap cleanly
        # "perfect for players who don't have time" → "perfect for you who" is broken
        relative_clause_pattern = (
            r'\b(players?|users?|punters?|bettors?|customers?|gamblers?)'
            r'\s+(who|that|whom)\b'
        )
        if re.search(relative_clause_pattern, sentence, re.IGNORECASE):
            return True

        # Check for multiple refs with mixed types
        all_refs = classify_person_references(sentence)
        if len(all_refs) > 1:
            ref_types = {r.ref_type for r in all_refs}
            # Mixed types: some READER_REF, some GENERIC_NOUN or UNCLEAR
            if len(ref_types) > 1:
                return True

        return False

    def _convert_sentence(
        self,
        sentence: str,
        ref: PersonReference,
    ) -> tuple[str, bool]:
        """
        Convert a sentence, replacing the third-person reference with second person.

        Returns:
            (converted_sentence, success)
        """
        word_lower = ref.word.lower()

        # First, check for possessive forms
        possessive_result = self._try_possessive_conversion(sentence, ref)
        if possessive_result is not None:
            return possessive_result, True

        # Standard subject/object conversion
        if word_lower in CONVERSION_RULES:
            replacement = CONVERSION_RULES[word_lower]

            # Get the actual word from the sentence (preserves original case)
            original_word = sentence[ref.start_pos:ref.end_pos]

            # Build result with case-matched replacement
            result = (
                sentence[:ref.start_pos] +
                self._match_case(replacement, original_word) +
                sentence[ref.end_pos:]
            )

            # Strip preceding article ("the player" -> "you")
            result = self._strip_article_before(result, ref.start_pos)

            # Fix verb agreement for singular nouns
            if word_lower in SINGULAR_NOUNS:
                result = self._fix_verb_agreement(result)

            return result, True

        return sentence, False

    def _try_possessive_conversion(
        self,
        sentence: str,
        ref: PersonReference,
    ) -> Optional[str]:
        """
        Try to convert possessive forms.

        Returns converted sentence if possessive found, None otherwise.
        """
        # Look at the text starting from the reference position
        # Include extra characters for possessive suffix ('s or ')
        end_check = min(ref.end_pos + 3, len(sentence))
        check_text = sentence[ref.start_pos:end_check].lower()

        for poss_form, replacement in POSSESSIVE_PATTERNS:
            if check_text.startswith(poss_form.lower()):
                # Found a possessive match
                poss_len = len(poss_form)
                actual_text = sentence[ref.start_pos:ref.start_pos + poss_len]

                result = (
                    sentence[:ref.start_pos] +
                    self._match_case(replacement, actual_text) +
                    sentence[ref.start_pos + poss_len:]
                )

                # Strip preceding article ("the player's" -> "your")
                result = self._strip_article_before(result, ref.start_pos)

                return result

        return None

    def _strip_article_before(self, text: str, pos: int) -> str:
        """
        Strip article (the, a, an) before the position if present.

        "The player can" with pos pointing to "player" becomes "You can"
        "A you has" -> "You has" (capitalize when at sentence start)
        """
        # Look at the text before the position
        prefix_start = max(0, pos - 5)
        prefix = text[prefix_start:pos]

        for pattern, replacement in ARTICLE_PATTERNS:
            match = re.search(pattern + "$", prefix, re.IGNORECASE)
            if match:
                # Found an article to strip
                article_start = prefix_start + match.start()
                # Remove the article
                result = text[:article_start] + text[pos:]

                # If article was at sentence start (position 0), capitalize the first letter
                if article_start == 0 and result:
                    result = result[0].upper() + result[1:]

                return result

        return text

    def _fix_verb_agreement(self, text: str) -> str:
        """
        Fix verb agreement after converting singular noun to "you".

        "you has" -> "you have"
        "you is" -> "you are"
        """
        for singular_verb, plural_verb in VERB_AGREEMENT_FIXES.items():
            # Match "you" followed by the singular verb
            pattern = rf'\byou\s+{singular_verb}\b'
            # Replace with plural form, preserving case
            def replacer(m: re.Match) -> str:
                matched = m.group(0)
                # Find where the verb starts
                verb_start = matched.lower().index(singular_verb)
                original_verb = matched[verb_start:verb_start + len(singular_verb)]
                fixed_verb = self._match_case(plural_verb, original_verb)
                return matched[:verb_start] + fixed_verb

            text = re.sub(pattern, replacer, text, flags=re.IGNORECASE)

        return text

    def _match_case(self, replacement: str, original: str) -> str:
        """Match the case pattern of the original word."""
        if not original:
            return replacement
        if original.isupper():
            return replacement.upper()
        elif original[0].isupper():
            return replacement.capitalize()
        else:
            return replacement.lower()
