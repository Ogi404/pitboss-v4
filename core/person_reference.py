"""
Pitboss v4 - Person Reference Classifier

Classifies third-person references (players, users, etc.) as:
- READER_REF: Addresses the reader, convertible to "you"
- GENERIC_NOUN: Population reference, NOT convertible
- UNCLEAR: Ambiguous context

This classifier is foundational for voice conversion checks.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re


class PersonRefType(Enum):
    """Classification of a third-person reference."""
    READER_REF = "reader_ref"      # Convertible to "you"
    GENERIC_NOUN = "generic_noun"  # NOT convertible
    UNCLEAR = "unclear"            # Ambiguous


# Third-person nouns to classify
THIRD_PERSON_NOUNS = {
    'player', 'players', 'user', 'users', 'punter', 'punters',
    'bettor', 'bettors', 'customer', 'customers', 'gambler', 'gamblers'
}

# Compile pattern for finding third-person nouns
THIRD_PERSON_PATTERN = re.compile(
    r'\b(' + '|'.join(THIRD_PERSON_NOUNS) + r')\b',
    re.IGNORECASE
)


# =============================================================================
# READER_REF PATTERNS
# =============================================================================

# Modal/action verbs AFTER the noun → READER_REF
# "players can claim", "users must verify", "players should check"
# Note: [)\].,;:]* allows for punctuation between word and space
READER_REF_AFTER_PATTERNS = [
    # Modal verbs (with or without "to")
    r'^[)\].,;:]*\s+(can|must|should|will|may)\s+\w',
    r'^[)\].,;:]*\s+(need|have)\s+to\s+\w',
    r'^[)\].,;:]*\s+are\s+able\s+to\b',
    # Imperative framing
    r'^[)\].,;:]*\s+are\s+(allowed|asked|required|expected|encouraged|advised)\s+to\b',
    # Action adverbs followed by modal
    r'^[)\].,;:]*\s+(simply|first|also|then|just|only)\s+(need|have|must|can|should)\b',
    # "simply [verb]", "first [verb]" patterns
    r'^[)\].,;:]*\s+(simply|first|also|then|just)\s+\w+',
]

# Patterns BEFORE the noun → READER_REF
# "gives players", "allows users", "lets players"
READER_REF_BEFORE_PATTERNS = [
    r'\b(gives?|lets?|allows?|enables?|helps?|offers?|provides?)\s+$',
    r'\b(for)\s+$',  # "for players," when addressing (but check for qualifiers)
    r'\bif\s+$',     # "if players deposit"
]


# =============================================================================
# GENERIC_NOUN PATTERNS
# =============================================================================

# Adjective qualifiers BEFORE the noun → GENERIC_NOUN
# "new players", "experienced players", "slot players", "VIP players"
GENERIC_ADJECTIVE_PATTERNS = [
    r'\b(new|experienced|regular|casual|loyal|frequent|active|existing|returning)\s+$',
    r'\b(serious|recreational|high-roller|high\s+roller|low-stakes|high-stakes)\s+$',
    r'\b(slot|table|poker|live|mobile|online|crypto)\s+$',
    r'\b(vip|premium|elite|gold|silver|bronze|platinum)\s+$',
    # Platform/device qualifiers
    r'\b(android|ios|desktop|app|tablet|windows|mac|web|browser|pc)\s+$',
]

# Quantity/demographic qualifiers BEFORE → GENERIC_NOUN
# "most players", "Canadian players", "thousands of players"
GENERIC_QUANTITY_PATTERNS = [
    r'\b(most|many|some|all|few|other|certain|selected|more|fewer)\s+$',
    r'\b(canadian|australian|british|uk|european|american|asian|african)\s+$',
    r'\b(\d+|thousands?|millions?|hundreds?)\s+(of\s+)?$',
    r'\b(number|plenty|lots?|group|majority|minority)\s+of\s+$',
]

# Attraction/design framing BEFORE → GENERIC_NOUN
# "attracts players", "designed for players", "appeals to players"
GENERIC_ATTRACTION_PATTERNS = [
    r'\battracts?\s+$',
    r'\bappeals?\s+to\s+$',
    r'\bdesigned\s+(for|to\s+attract)\s+.*$',
    r'\btargets?\s+$',
    r'\bcaters?\s+to\s+$',
]

# Behavioral/observational patterns AFTER → GENERIC_NOUN
# "players usually prefer", "players from Canada", "players who like"
GENERIC_AFTER_PATTERNS = [
    # Behavioral observations
    r'^\s+(usually|often|sometimes|rarely|never|tend\s+to|prefer|like|love|enjoy|appreciate)\b',
    r'^\s+(keep|skip|forget|assume|expect|believe|think|feel|want)\b',
    # Geographic/demographic
    r'^\s+from\s+\w',
    # Relative clauses describing populations
    r'^\s+who\s+(like|prefer|enjoy|want|need|love|are|have|play)\b',
    # Possessive contexts
    r"^['\u2019]s\s+(journey|data|information|protection|activity|records|account|experience|perspective|behavior|habits?)\b",
    # Compound nouns - player/user as modifier before another noun
    # "player protection", "player safety", "user experience", "player-friendly"
    r'^\s+(protection|safety|support|engagement|retention|base|pool|count|feedback|preferences|satisfaction|loyalty|acquisition|segment|demographics)\b',
    r'^-(friendly|focused|centric|oriented|facing|driven)\b',
]


# =============================================================================
# DATACLASS
# =============================================================================

@dataclass
class PersonReference:
    """A classified person reference."""
    word: str                    # The matched word (player, users, etc.)
    ref_type: PersonRefType      # Classification
    start_pos: int               # Character position in text
    end_pos: int                 # End position
    context: str                 # Surrounding context for debugging


# =============================================================================
# CLASSIFICATION FUNCTIONS
# =============================================================================

def _check_patterns(text: str, patterns: list[str]) -> bool:
    """Check if any pattern matches the text."""
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _get_context_before(text: str, pos: int, max_chars: int = 50) -> str:
    """Get text before position, for lookbehind patterns."""
    start = max(0, pos - max_chars)
    return text[start:pos]


def _get_context_after(text: str, pos: int, word_len: int, max_chars: int = 50) -> str:
    """Get text after the word, for lookahead patterns."""
    start = pos + word_len
    end = min(len(text), start + max_chars)
    return text[start:end]


def _classify_single_reference(
    text: str,
    match: re.Match,
) -> PersonRefType:
    """
    Classify a single third-person reference.

    Args:
        text: The full sentence/text
        match: The regex match object for the third-person word

    Returns:
        PersonRefType classification
    """
    word = match.group(0).lower()
    start_pos = match.start()
    end_pos = match.end()

    # Get surrounding context
    before = _get_context_before(text, start_pos).lower()
    after = _get_context_after(text, start_pos, len(word)).lower()

    # Check GENERIC_NOUN patterns (higher priority - more specific)
    # These patterns indicate population/category references

    # Adjective qualifiers before
    if _check_patterns(before, GENERIC_ADJECTIVE_PATTERNS):
        return PersonRefType.GENERIC_NOUN

    # Quantity/demographic before
    if _check_patterns(before, GENERIC_QUANTITY_PATTERNS):
        return PersonRefType.GENERIC_NOUN

    # Attraction/design framing before
    if _check_patterns(before, GENERIC_ATTRACTION_PATTERNS):
        return PersonRefType.GENERIC_NOUN

    # Behavioral/observational after
    if _check_patterns(after, GENERIC_AFTER_PATTERNS):
        return PersonRefType.GENERIC_NOUN

    # Check READER_REF patterns
    # These indicate direct address to the reader

    # Modal/action verbs after
    if _check_patterns(after, READER_REF_AFTER_PATTERNS):
        return PersonRefType.READER_REF

    # Direct address patterns before
    if _check_patterns(before, READER_REF_BEFORE_PATTERNS):
        # But check if there's a qualifier that makes it generic
        # e.g., "for new players" vs "for players"
        combined = before + word
        if _check_patterns(combined[-30:], GENERIC_ADJECTIVE_PATTERNS):
            return PersonRefType.GENERIC_NOUN
        return PersonRefType.READER_REF

    # Default to UNCLEAR
    return PersonRefType.UNCLEAR


def classify_person_references(sentence: str) -> list[PersonReference]:
    """
    Classify all third-person references in a sentence.

    Args:
        sentence: The sentence to analyze

    Returns:
        List of PersonReference objects with classifications
    """
    if not sentence:
        return []

    results = []

    for match in THIRD_PERSON_PATTERN.finditer(sentence):
        ref_type = _classify_single_reference(sentence, match)

        # Get context snippet
        start = max(0, match.start() - 20)
        end = min(len(sentence), match.end() + 20)
        context = sentence[start:end]
        if start > 0:
            context = "..." + context
        if end < len(sentence):
            context = context + "..."

        results.append(PersonReference(
            word=match.group(0).lower(),
            ref_type=ref_type,
            start_pos=match.start(),
            end_pos=match.end(),
            context=context,
        ))

    return results


def count_person_references(text: str) -> tuple[int, int, int]:
    """
    Count person references in text by classification.

    Args:
        text: Text to analyze (can be multiple sentences)

    Returns:
        (reader_ref_count, generic_noun_count, unclear_count)
    """
    if not text:
        return 0, 0, 0

    reader_ref = 0
    generic_noun = 0
    unclear = 0

    for match in THIRD_PERSON_PATTERN.finditer(text):
        ref_type = _classify_single_reference(text, match)

        if ref_type == PersonRefType.READER_REF:
            reader_ref += 1
        elif ref_type == PersonRefType.GENERIC_NOUN:
            generic_noun += 1
        else:
            unclear += 1

    return reader_ref, generic_noun, unclear


def classify_person_reference_simple(sentence: str) -> list[PersonRefType]:
    """
    Classify all third-person references, returning just the types.

    Simpler alternative when full PersonReference objects aren't needed.

    Args:
        sentence: The sentence to analyze

    Returns:
        List of PersonRefType classifications
    """
    refs = classify_person_references(sentence)
    return [r.ref_type for r in refs]
