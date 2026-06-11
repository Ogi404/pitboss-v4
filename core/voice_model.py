"""
Pitboss v4 - Layered Voice Model Builder

This module builds voice models from the approved articles corpus.
It's an OFFLINE build step, not part of per-article runtime.

Three layers:
1. House model (_house/) - all articles pooled
2. Type models (_types/<type>/) - one per article type
3. Brand models (<brand>/) - only for brands with 10+ articles

Each model captures measurable voice fingerprints that the judgment layer
uses to match rewrites to the approved corpus style.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
from datetime import datetime, timezone
import json
import re
import csv
import statistics
from collections import Counter

from core.document import Document, Paragraph, Heading, List, HeadingLevel


# ============================================================================
# TYPE INFERENCE PATTERNS
# ============================================================================

TYPE_PATTERNS: dict[str, list[str]] = {
    'app_review': ['app', 'mobile', 'android', 'ios', 'download', 'application'],
    'bonus_page': ['bonus', 'promo', 'welcome', 'no-deposit', 'free spin', 'offer',
                   'promotion', 'no deposit'],
    'game_review': ['slot', 'slots', 'game review', 'pragmatic', 'netent',
                    'play n go', 'casino game', 'rtp', 'volatility'],
    'sports_market': ['boxing', 'basketball', 'football', 'soccer', 'racing',
                      'tennis', 'cricket', 'nfl', 'nba', 'betting market',
                      'horse racing', 'ufc', 'mma', 'baseball', 'hockey'],
    'payments': ['payment', 'banking', 'deposit', 'withdrawal', 'crypto',
                 'bitcoin', 'visa', 'mastercard', 'skrill', 'neteller', 'payout'],
    'registration': ['register', 'sign up', 'create account', 'how to join',
                     'sign-up', 'signup', 'registration'],
    'customer_support': ['support', 'contact', 'help', 'live chat', 'customer service'],
    'responsible_gaming': ['responsible', 'gambling help', 'self-exclusion',
                           'responsible gambling', 'problem gambling'],
    'vip_loyalty': ['vip', 'loyalty', 'rewards program', 'cashback', 'loyalty program'],
    'privacy_policy': ['privacy', 'privacy policy', 'data protection'],
    'live_casino': ['live dealer', 'live casino', 'live table', 'live roulette',
                    'live blackjack', 'live baccarat'],
}

# Patterns that suggest main review (brand overview)
MAIN_REVIEW_PATTERNS = ['review', 'casino', 'sportsbook', 'betting site', 'overview']


def infer_article_type(filename: str, brand_name: str = "") -> str:
    """
    Infer article type from filename.

    Args:
        filename: The filename (without path)
        brand_name: Brand name to exclude from matching

    Returns:
        Inferred type string
    """
    # Normalize filename
    name_lower = filename.lower().replace('-', ' ').replace('_', ' ')

    # Remove brand name from consideration
    if brand_name:
        name_lower = name_lower.replace(brand_name.lower(), '')

    # Check each type pattern
    for article_type, patterns in TYPE_PATTERNS.items():
        for pattern in patterns:
            if pattern in name_lower:
                return article_type

    # Check for main review patterns
    for pattern in MAIN_REVIEW_PATTERNS:
        if pattern in name_lower:
            return 'main_review'

    # Default fallback
    return 'general'


# ============================================================================
# TRANSITION PHRASES
# ============================================================================

# Predefined common transition phrases to track
TRANSITION_PHRASES = [
    # Addition
    "additionally", "also", "and", "as well as", "besides", "furthermore",
    "in addition", "moreover", "not only", "what's more",
    # Contrast
    "although", "but", "conversely", "despite", "even though", "however",
    "in contrast", "nevertheless", "nonetheless", "on the other hand",
    "still", "though", "whereas", "while", "yet",
    # Cause/Effect
    "accordingly", "as a result", "because", "consequently", "due to",
    "for this reason", "hence", "since", "so", "therefore", "thus",
    # Example
    "for example", "for instance", "in particular", "namely", "specifically",
    "such as", "to illustrate",
    # Sequence
    "after", "afterward", "before", "finally", "first", "firstly", "later",
    "meanwhile", "next", "second", "secondly", "subsequently", "then",
    # Summary
    "all in all", "in conclusion", "in short", "in summary", "overall",
    "to conclude", "to summarize", "to sum up", "ultimately",
    # Emphasis
    "above all", "certainly", "clearly", "especially", "importantly",
    "in fact", "indeed", "most importantly", "notably", "of course",
    "particularly", "significantly", "undoubtedly",
]


# ============================================================================
# TEXT ANALYSIS UTILITIES
# ============================================================================

# Common abbreviations that shouldn't end sentences
ABBREVIATIONS = {'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr', 'vs', 'etc', 'e.g', 'i.e'}

# Second person pronouns/words
SECOND_PERSON = {'you', 'your', "you're", 'yourself', 'yours', 'youre'}

# Third person reader references
THIRD_PERSON = {
    'players', 'player', 'punters', 'punter', 'users', 'user',
    'bettors', 'bettor', 'customers', 'customer', 'gamblers', 'gambler',
}
THIRD_PERSON_PHRASES = [
    'the player', 'the user', 'the customer', 'the bettor', 'the punter',
]


def split_sentences(text: str) -> list[str]:
    """
    Split text into sentences.

    Handles common abbreviations and decimal numbers to avoid false splits.
    """
    if not text:
        return []

    # Simple approach: split on sentence-ending punctuation followed by space and capital
    # First, protect abbreviations by replacing their periods temporarily
    PLACEHOLDER = "|||PERIOD|||"
    protected = text

    for abbr in ABBREVIATIONS:
        # Replace "Dr." with "Dr|||PERIOD|||" to protect the period
        pattern = re.compile(r'\b' + re.escape(abbr) + r'\.', re.IGNORECASE)
        protected = pattern.sub(abbr + PLACEHOLDER, protected)

    # Also protect decimal numbers (e.g., "100.50")
    protected = re.sub(r'(\d)\.(\d)', r'\1' + PLACEHOLDER + r'\2', protected)

    # Now split on sentence-ending punctuation
    # Match period, exclamation, or question mark followed by space and capital letter
    parts = re.split(r'([.!?]+)\s+(?=[A-Z])', protected)

    # Reconstruct sentences
    sentences = []
    i = 0
    while i < len(parts):
        sentence = parts[i]
        # Add back the punctuation if it exists
        if i + 1 < len(parts) and re.match(r'^[.!?]+$', parts[i + 1]):
            sentence += parts[i + 1]
            i += 2
        else:
            i += 1

        # Restore protected characters
        sentence = sentence.replace(PLACEHOLDER, '.')
        sentence = sentence.strip()

        if sentence and len(sentence) > 1:
            sentences.append(sentence)

    return sentences


def count_words(text: str) -> int:
    """Count words in text."""
    if not text:
        return 0
    return len(text.split())


def detect_person(text: str) -> tuple[int, int, int, int]:
    """
    Count second-person and classified third-person references.

    Uses the person_reference classifier to distinguish:
    - READER_REF: Third-person references addressing the reader (convertible to "you")
    - GENERIC_NOUN: Population references (NOT convertible)
    - UNCLEAR: Ambiguous cases

    Returns:
        (second_person_count, reader_ref_count, generic_noun_count, unclear_count)
    """
    from core.person_reference import count_person_references

    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)

    # Count second person (unchanged)
    second_count = sum(1 for w in words if w in SECOND_PERSON)

    # Count third person with classification
    reader_ref, generic_noun, unclear = count_person_references(text)

    return second_count, reader_ref, generic_noun, unclear


def is_title_case(text: str) -> bool:
    """
    Check if text is in title case.

    Title case: most words capitalized (excluding articles, prepositions).
    """
    if not text:
        return False

    # Words to ignore in title case check
    minor_words = {'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'yet', 'so',
                   'at', 'by', 'in', 'of', 'on', 'to', 'up', 'as', 'is', 'it'}

    words = text.split()
    if not words:
        return False

    # First word should always be capitalized
    if not words[0][0].isupper():
        return False

    # Count capitalized significant words
    capitalized = 0
    total_significant = 0

    for word in words:
        # Skip minor words (except at start)
        clean_word = re.sub(r'[^\w]', '', word).lower()
        if clean_word in minor_words and word != words[0]:
            continue

        total_significant += 1
        if word and word[0].isupper():
            capitalized += 1

    if total_significant == 0:
        return True

    return (capitalized / total_significant) >= 0.7


def detect_heading_case(headings: list[str]) -> tuple[str, float]:
    """
    Detect dominant heading capitalization style.

    Returns:
        (style, title_case_ratio) where style is:
        - "title_case" if >70% title case
        - "sentence_case" if >70% sentence case
        - "mixed" otherwise
    """
    if not headings:
        return "mixed", 0.5

    title_case_count = sum(1 for h in headings if is_title_case(h))
    ratio = title_case_count / len(headings)

    if ratio >= 0.7:
        return "title_case", ratio
    elif ratio <= 0.3:
        return "sentence_case", ratio
    else:
        return "mixed", ratio


def extract_sentence_openers(
    sentences: list[str],
    brand_name: str = "",
    top_n: int = 20
) -> list[tuple[str, float]]:
    """
    Extract most common sentence opening words/phrases.

    Args:
        sentences: List of sentences
        brand_name: Brand name to strip from openers
        top_n: Number of top openers to return

    Returns:
        List of (opener, rate_per_100_sentences)
    """
    if not sentences:
        return []

    openers = []
    brand_lower = brand_name.lower() if brand_name else ""

    for sentence in sentences:
        # Get first 1-3 words
        words = sentence.split()[:3]
        if not words:
            continue

        # Normalize: lowercase, strip brand name
        opener = ' '.join(words).lower()
        if brand_lower and opener.startswith(brand_lower):
            opener = opener[len(brand_lower):].strip()

        if opener:
            openers.append(opener)

    # Count frequencies
    counter = Counter(openers)
    total = len(sentences)

    # Convert to rate per 100 sentences
    result = [
        (opener, (count / total) * 100)
        for opener, count in counter.most_common(top_n)
    ]

    return result


def extract_transitions(
    text: str,
    sentences: list[str],
    discouraged_phrases: list[str] = None
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Extract transition phrase usage.

    Args:
        text: Full text
        sentences: List of sentences (for rate calculation)
        discouraged_phrases: Phrases to flag as discouraged

    Returns:
        (transitions_used, discouraged_observed)
        Both are {phrase: rate_per_100_sentences}
    """
    if not sentences:
        return {}, {}

    text_lower = text.lower()
    total_sentences = len(sentences)
    discouraged_phrases = discouraged_phrases or []

    transitions = {}
    discouraged = {}

    # Count predefined transitions
    for phrase in TRANSITION_PHRASES:
        count = len(re.findall(r'\b' + re.escape(phrase) + r'\b', text_lower))
        if count > 0:
            rate = (count / total_sentences) * 100
            transitions[phrase] = rate

            # Check if discouraged
            if phrase in discouraged_phrases:
                discouraged[phrase] = rate

    return transitions, discouraged


def compute_punctuation_density(text: str, word_count: int) -> dict[str, float]:
    """
    Compute punctuation per 100 words.

    Returns dict with comma_density, dash_density, semicolon_density.
    """
    if word_count == 0:
        return {'comma_density': 0.0, 'dash_density': 0.0, 'semicolon_density': 0.0}

    commas = text.count(',')
    dashes = text.count('-') + text.count('—') + text.count('–')
    semicolons = text.count(';')

    return {
        'comma_density': (commas / word_count) * 100,
        'dash_density': (dashes / word_count) * 100,
        'semicolon_density': (semicolons / word_count) * 100,
    }


def extract_stop_word_usage(
    text: str,
    hard_words: list[str],
    soft_words: list[str]
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Count usage of hard and soft stop words.

    Returns:
        (hard_counts, soft_counts) as {word: count} dicts
    """
    text_lower = text.lower()
    hard_counts = {}
    soft_counts = {}

    for word in hard_words:
        count = len(re.findall(r'\b' + re.escape(word.lower()) + r'\b', text_lower))
        if count > 0:
            hard_counts[word] = count

    for word in soft_words:
        count = len(re.findall(r'\b' + re.escape(word.lower()) + r'\b', text_lower))
        if count > 0:
            soft_counts[word] = count

    return hard_counts, soft_counts


# ============================================================================
# VOICE FINGERPRINT
# ============================================================================

@dataclass
class VoiceFingerprint:
    """Measurable voice characteristics extracted from a corpus."""

    # Sentence length distribution
    sentence_length_mean: float = 0.0
    sentence_length_median: float = 0.0
    sentence_length_stdev: float = 0.0
    sentence_length_p10: float = 0.0  # 10th percentile
    sentence_length_p90: float = 0.0  # 90th percentile

    # Paragraph length distribution
    para_sentences_mean: float = 0.0
    para_sentences_stdev: float = 0.0
    para_words_mean: float = 0.0
    para_words_stdev: float = 0.0

    # Person ratio (with third-person classification)
    second_person_count: int = 0
    reader_ref_count: int = 0       # Third-person reader-references (convertible)
    generic_noun_count: int = 0     # Third-person generic nouns (NOT convertible)
    unclear_person_count: int = 0   # Ambiguous third-person
    third_person_count: int = 0     # Total = reader_ref + generic + unclear (backwards compat)
    person_ratio: float = 0.0       # second / reader_ref (conversion-relevant)

    # Heading style
    heading_capitalization: str = "mixed"
    title_case_ratio: float = 0.5

    # Sentence openers (top N, rate per 100 sentences)
    common_openers: list = field(default_factory=list)

    # Transition phrases (rate per 100 sentences)
    transitions_used: dict = field(default_factory=dict)
    discouraged_observed: dict = field(default_factory=dict)

    # Punctuation density (per 100 words)
    comma_density: float = 0.0
    dash_density: float = 0.0
    semicolon_density: float = 0.0
    list_frequency: float = 0.0  # lists per 1000 words

    # Vocabulary fingerprint
    stop_words_hard: dict = field(default_factory=dict)
    stop_words_soft: dict = field(default_factory=dict)

    # Metadata
    schema_version: str = "1.0"
    article_count: int = 0
    total_words: int = 0
    total_sentences: int = 0

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "sentence_length_mean": self.sentence_length_mean,
            "sentence_length_median": self.sentence_length_median,
            "sentence_length_stdev": self.sentence_length_stdev,
            "sentence_length_p10": self.sentence_length_p10,
            "sentence_length_p90": self.sentence_length_p90,
            "para_sentences_mean": self.para_sentences_mean,
            "para_sentences_stdev": self.para_sentences_stdev,
            "para_words_mean": self.para_words_mean,
            "para_words_stdev": self.para_words_stdev,
            "second_person_count": self.second_person_count,
            "reader_ref_count": self.reader_ref_count,
            "generic_noun_count": self.generic_noun_count,
            "unclear_person_count": self.unclear_person_count,
            "third_person_count": self.third_person_count,
            "person_ratio": self.person_ratio,
            "heading_capitalization": self.heading_capitalization,
            "title_case_ratio": self.title_case_ratio,
            "common_openers": self.common_openers,
            "transitions_used": self.transitions_used,
            "discouraged_observed": self.discouraged_observed,
            "comma_density": self.comma_density,
            "dash_density": self.dash_density,
            "semicolon_density": self.semicolon_density,
            "list_frequency": self.list_frequency,
            "stop_words_hard": self.stop_words_hard,
            "stop_words_soft": self.stop_words_soft,
            "schema_version": self.schema_version,
            "article_count": self.article_count,
            "total_words": self.total_words,
            "total_sentences": self.total_sentences,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VoiceFingerprint:
        """Deserialize from dictionary."""
        return cls(
            sentence_length_mean=data.get("sentence_length_mean", 0.0),
            sentence_length_median=data.get("sentence_length_median", 0.0),
            sentence_length_stdev=data.get("sentence_length_stdev", 0.0),
            sentence_length_p10=data.get("sentence_length_p10", 0.0),
            sentence_length_p90=data.get("sentence_length_p90", 0.0),
            para_sentences_mean=data.get("para_sentences_mean", 0.0),
            para_sentences_stdev=data.get("para_sentences_stdev", 0.0),
            para_words_mean=data.get("para_words_mean", 0.0),
            para_words_stdev=data.get("para_words_stdev", 0.0),
            second_person_count=data.get("second_person_count", 0),
            reader_ref_count=data.get("reader_ref_count", 0),
            generic_noun_count=data.get("generic_noun_count", 0),
            unclear_person_count=data.get("unclear_person_count", 0),
            third_person_count=data.get("third_person_count", 0),
            person_ratio=data.get("person_ratio", 0.0),
            heading_capitalization=data.get("heading_capitalization", "mixed"),
            title_case_ratio=data.get("title_case_ratio", 0.5),
            common_openers=data.get("common_openers", []),
            transitions_used=data.get("transitions_used", {}),
            discouraged_observed=data.get("discouraged_observed", {}),
            comma_density=data.get("comma_density", 0.0),
            dash_density=data.get("dash_density", 0.0),
            semicolon_density=data.get("semicolon_density", 0.0),
            list_frequency=data.get("list_frequency", 0.0),
            stop_words_hard=data.get("stop_words_hard", {}),
            stop_words_soft=data.get("stop_words_soft", {}),
            schema_version=data.get("schema_version", "1.0"),
            article_count=data.get("article_count", 0),
            total_words=data.get("total_words", 0),
            total_sentences=data.get("total_sentences", 0),
        )


# ============================================================================
# VOICE MODEL
# ============================================================================

@dataclass
class VoiceModel:
    """A voice model for a layer (house, type, or brand)."""

    layer: str  # "house", "type", "brand"
    layer_name: str  # "" for house, type name, or brand name
    fingerprint: VoiceFingerprint
    article_count: int
    schema_version: str = "1.0"
    built_at: str = ""

    def __post_init__(self):
        if not self.built_at:
            self.built_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "layer": self.layer,
            "layer_name": self.layer_name,
            "fingerprint": self.fingerprint.to_dict(),
            "article_count": self.article_count,
            "schema_version": self.schema_version,
            "built_at": self.built_at,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> VoiceModel:
        """Deserialize from dictionary."""
        return cls(
            layer=data["layer"],
            layer_name=data["layer_name"],
            fingerprint=VoiceFingerprint.from_dict(data["fingerprint"]),
            article_count=data["article_count"],
            schema_version=data.get("schema_version", "1.0"),
            built_at=data.get("built_at", ""),
        )

    @classmethod
    def from_json(cls, json_str: str) -> VoiceModel:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def load(cls, path: Path) -> VoiceModel:
        """Load from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            return cls.from_json(f.read())

    def save(self, path: Path) -> None:
        """Save to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())


# ============================================================================
# FINGERPRINT BUILDER
# ============================================================================

class FingerprintBuilder:
    """Builds a VoiceFingerprint from a set of Documents."""

    def __init__(
        self,
        hard_stop_words: list[str] = None,
        soft_stop_words: list[str] = None,
        discouraged_phrases: list[str] = None,
        brand_name: str = ""
    ):
        self.hard_stop_words = hard_stop_words or []
        self.soft_stop_words = soft_stop_words or []
        self.discouraged_phrases = discouraged_phrases or []
        self.brand_name = brand_name

    def build(self, documents: list[Document]) -> VoiceFingerprint:
        """
        Extract fingerprint from pooled documents.

        All metrics are computed over the combined corpus,
        not averaged per-document.

        Prose metrics (sentence length, person ratio, openers, transitions,
        punctuation) are computed over BODY PARAGRAPHS ONLY — headings and
        list items are short fragments that would dilute the stats.

        Heading analysis is kept separate for capitalization fingerprint.
        """
        if not documents:
            return VoiceFingerprint(article_count=0)

        # Collect paragraphs (body prose), headings (for case analysis), and lists
        all_paragraphs = []  # Body prose only
        all_headings = []    # For capitalization analysis only
        list_count = 0

        for doc in documents:
            for element in doc.elements:
                if isinstance(element, Paragraph):
                    all_paragraphs.append(element.text)
                elif isinstance(element, Heading):
                    all_headings.append(element.text)
                elif isinstance(element, List):
                    list_count += 1

        # Prose text = paragraphs only (for sentence/person/punctuation analysis)
        prose_text = "\n".join(all_paragraphs)
        prose_sentences = []
        for p in all_paragraphs:
            prose_sentences.extend(split_sentences(p))

        prose_words = count_words(prose_text)
        total_sentences = len(prose_sentences)

        # Sentence length stats (prose only)
        sentence_lengths = [count_words(s) for s in prose_sentences]
        if sentence_lengths:
            sorted_lengths = sorted(sentence_lengths)
            n = len(sorted_lengths)
            sentence_mean = statistics.mean(sentence_lengths)
            sentence_median = statistics.median(sentence_lengths)
            sentence_stdev = statistics.stdev(sentence_lengths) if len(sentence_lengths) > 1 else 0.0
            sentence_p10 = sorted_lengths[int(n * 0.1)] if n >= 10 else sorted_lengths[0]
            sentence_p90 = sorted_lengths[int(n * 0.9)] if n >= 10 else sorted_lengths[-1]
        else:
            sentence_mean = sentence_median = sentence_stdev = 0.0
            sentence_p10 = sentence_p90 = 0.0

        # Paragraph length stats
        para_sentence_counts = [len(split_sentences(p)) for p in all_paragraphs]
        para_word_counts = [count_words(p) for p in all_paragraphs]

        if para_sentence_counts:
            para_sentences_mean = statistics.mean(para_sentence_counts)
            para_sentences_stdev = statistics.stdev(para_sentence_counts) if len(para_sentence_counts) > 1 else 0.0
        else:
            para_sentences_mean = para_sentences_stdev = 0.0

        if para_word_counts:
            para_words_mean = statistics.mean(para_word_counts)
            para_words_stdev = statistics.stdev(para_word_counts) if len(para_word_counts) > 1 else 0.0
        else:
            para_words_mean = para_words_stdev = 0.0

        # Person detection (prose only) with third-person classification
        second_count, reader_ref, generic_noun, unclear = detect_person(prose_text)
        third_count = reader_ref + generic_noun + unclear  # backwards compat
        # Conversion-relevant ratio: second-person / reader-ref (NOT generic nouns)
        person_ratio = second_count / reader_ref if reader_ref > 0 else float('inf') if second_count > 0 else 0.0

        # Heading case
        heading_style, title_case_ratio = detect_heading_case(all_headings)

        # Sentence openers (prose only)
        common_openers = extract_sentence_openers(prose_sentences, self.brand_name)

        # Transitions (prose only)
        transitions, discouraged = extract_transitions(
            prose_text, prose_sentences, self.discouraged_phrases
        )

        # Punctuation (prose only)
        punct = compute_punctuation_density(prose_text, prose_words)

        # List frequency (per 1000 prose words)
        list_frequency = (list_count / prose_words) * 1000 if prose_words > 0 else 0.0

        # Stop words (prose only)
        hard_counts, soft_counts = extract_stop_word_usage(
            prose_text, self.hard_stop_words, self.soft_stop_words
        )

        return VoiceFingerprint(
            sentence_length_mean=round(sentence_mean, 2),
            sentence_length_median=round(sentence_median, 2),
            sentence_length_stdev=round(sentence_stdev, 2),
            sentence_length_p10=round(sentence_p10, 2),
            sentence_length_p90=round(sentence_p90, 2),
            para_sentences_mean=round(para_sentences_mean, 2),
            para_sentences_stdev=round(para_sentences_stdev, 2),
            para_words_mean=round(para_words_mean, 2),
            para_words_stdev=round(para_words_stdev, 2),
            second_person_count=second_count,
            reader_ref_count=reader_ref,
            generic_noun_count=generic_noun,
            unclear_person_count=unclear,
            third_person_count=third_count,
            person_ratio=round(person_ratio, 2) if person_ratio != float('inf') else -1,
            heading_capitalization=heading_style,
            title_case_ratio=round(title_case_ratio, 2),
            common_openers=common_openers,
            transitions_used=transitions,
            discouraged_observed=discouraged,
            comma_density=round(punct['comma_density'], 2),
            dash_density=round(punct['dash_density'], 2),
            semicolon_density=round(punct['semicolon_density'], 2),
            list_frequency=round(list_frequency, 2),
            stop_words_hard=hard_counts,
            stop_words_soft=soft_counts,
            article_count=len(documents),
            total_words=prose_words,
            total_sentences=total_sentences,
        )


# ============================================================================
# BUILD RESULT
# ============================================================================

@dataclass
class BuildResult:
    """Result of building all voice models."""

    house_model: VoiceModel
    type_models: dict[str, VoiceModel]
    brand_models: dict[str, VoiceModel]
    skipped_brands: list[tuple[str, int]]  # (brand, article_count)
    articles_by_type: dict[str, int]  # type -> count
    articles_by_brand: dict[str, int]  # brand -> count

    def summary(self) -> str:
        """Return human-readable summary."""
        lines = [
            "=== Voice Model Build Summary ===",
            f"House model: {self.house_model.article_count} articles",
            f"  - Second-person ratio: {self.house_model.fingerprint.person_ratio}:1",
            f"  - Mean sentence length: {self.house_model.fingerprint.sentence_length_mean} words",
            "",
            f"Type models built: {len(self.type_models)}",
        ]
        for type_name, model in sorted(self.type_models.items()):
            lines.append(f"  - {type_name}: {model.article_count} articles")

        lines.append("")
        lines.append(f"Brand models built: {len(self.brand_models)}")
        for brand, model in sorted(self.brand_models.items()):
            lines.append(f"  - {brand}: {model.article_count} articles")

        if self.skipped_brands:
            lines.append("")
            lines.append(f"Brands skipped (<10 articles): {len(self.skipped_brands)}")
            for brand, count in sorted(self.skipped_brands):
                lines.append(f"  - {brand}: {count} articles")

        return "\n".join(lines)


# ============================================================================
# CORPUS INDEX
# ============================================================================

def generate_corpus_index(corpora_dir: Path) -> Path:
    """
    Scan corpus directory and generate corpus_index.csv.

    Returns path to the generated file.
    """
    index_path = corpora_dir / "corpus_index.csv"
    rows = []

    # Find all .docx files
    for docx_path in corpora_dir.rglob("*.docx"):
        # Skip special directories
        rel_path = docx_path.relative_to(corpora_dir)
        parts = rel_path.parts

        if parts[0].startswith('_'):
            continue  # Skip _house, _types, etc.

        # Brand is the first directory
        brand = parts[0] if len(parts) > 1 else "unknown"

        # Infer type from filename
        article_type = infer_article_type(docx_path.name, brand)

        rows.append({
            'filepath': str(rel_path).replace('\\', '/'),
            'brand': brand,
            'type': article_type,
            'inferred': 'true',
        })

    # Sort by brand then filename
    rows.sort(key=lambda r: (r['brand'], r['filepath']))

    # Write CSV
    with open(index_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['filepath', 'brand', 'type', 'inferred'])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {index_path} with {len(rows)} entries")
    return index_path


def load_corpus_index(corpora_dir: Path) -> list[dict]:
    """
    Load corpus_index.csv, generating if missing.

    Returns list of dicts with filepath, brand, type.
    """
    index_path = corpora_dir / "corpus_index.csv"

    if not index_path.exists():
        generate_corpus_index(corpora_dir)

    rows = []
    with open(index_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    return rows


# ============================================================================
# VOICE MODEL BUILDER
# ============================================================================

class VoiceModelBuilder:
    """Builds all three layers of voice models from corpus."""

    BRAND_THRESHOLD = 10  # Minimum articles for brand-level model

    def __init__(
        self,
        corpora_dir: Path,
        hard_stop_words: list[str] = None,
        soft_stop_words: list[str] = None,
        discouraged_phrases: list[str] = None,
    ):
        self.corpora_dir = Path(corpora_dir)
        self.hard_stop_words = hard_stop_words or []
        self.soft_stop_words = soft_stop_words or []
        self.discouraged_phrases = discouraged_phrases or []

    def load_documents(self) -> tuple[dict[str, list[Document]], dict[str, list[Document]]]:
        """
        Load all documents from corpus.

        Returns:
            (docs_by_brand, docs_by_type)
        """
        from ingest.docx_reader import read_docx

        index = load_corpus_index(self.corpora_dir)
        docs_by_brand: dict[str, list[Document]] = {}
        docs_by_type: dict[str, list[Document]] = {}

        for entry in index:
            filepath = self.corpora_dir / entry['filepath']
            if not filepath.exists():
                print(f"Warning: File not found: {filepath}")
                continue

            try:
                doc = read_docx(filepath)
            except Exception as e:
                print(f"Warning: Failed to read {filepath}: {e}")
                continue

            brand = entry['brand']
            article_type = entry['type']

            # Add to brand dict
            if brand not in docs_by_brand:
                docs_by_brand[brand] = []
            docs_by_brand[brand].append(doc)

            # Add to type dict
            if article_type not in docs_by_type:
                docs_by_type[article_type] = []
            docs_by_type[article_type].append(doc)

        return docs_by_brand, docs_by_type

    def build_house_model(self, all_docs: list[Document]) -> VoiceModel:
        """Build Layer 1: house model from all articles."""
        builder = FingerprintBuilder(
            hard_stop_words=self.hard_stop_words,
            soft_stop_words=self.soft_stop_words,
            discouraged_phrases=self.discouraged_phrases,
        )
        fingerprint = builder.build(all_docs)

        return VoiceModel(
            layer="house",
            layer_name="",
            fingerprint=fingerprint,
            article_count=len(all_docs),
        )

    def build_type_model(self, article_type: str, docs: list[Document]) -> VoiceModel:
        """Build Layer 2: type model."""
        builder = FingerprintBuilder(
            hard_stop_words=self.hard_stop_words,
            soft_stop_words=self.soft_stop_words,
            discouraged_phrases=self.discouraged_phrases,
        )
        fingerprint = builder.build(docs)

        return VoiceModel(
            layer="type",
            layer_name=article_type,
            fingerprint=fingerprint,
            article_count=len(docs),
        )

    def build_brand_model(self, brand: str, docs: list[Document]) -> VoiceModel:
        """Build Layer 3: brand model."""
        builder = FingerprintBuilder(
            hard_stop_words=self.hard_stop_words,
            soft_stop_words=self.soft_stop_words,
            discouraged_phrases=self.discouraged_phrases,
            brand_name=brand,
        )
        fingerprint = builder.build(docs)

        return VoiceModel(
            layer="brand",
            layer_name=brand,
            fingerprint=fingerprint,
            article_count=len(docs),
        )

    def build_all(self, save: bool = True) -> BuildResult:
        """
        Build all three layers of voice models.

        Args:
            save: Whether to save models to disk

        Returns:
            BuildResult with all models and statistics
        """
        docs_by_brand, docs_by_type = self.load_documents()

        # Flatten all docs
        all_docs = []
        for docs in docs_by_brand.values():
            all_docs.extend(docs)

        if not all_docs:
            raise ValueError("No documents found in corpus")

        # Build house model
        print(f"Building house model from {len(all_docs)} articles...")
        house_model = self.build_house_model(all_docs)

        if save:
            house_path = self.corpora_dir / "_house" / "voice_model.json"
            house_model.save(house_path)
            print(f"  Saved to {house_path}")

        # Build type models
        type_models = {}
        print(f"\nBuilding type models for {len(docs_by_type)} types...")
        for article_type, docs in docs_by_type.items():
            print(f"  Building {article_type} model ({len(docs)} articles)...")
            model = self.build_type_model(article_type, docs)
            type_models[article_type] = model

            if save:
                type_path = self.corpora_dir / "_types" / article_type / "voice_model.json"
                model.save(type_path)

        # Build brand models (only for brands with 10+ articles)
        brand_models = {}
        skipped_brands = []
        print(f"\nBuilding brand models (threshold: {self.BRAND_THRESHOLD} articles)...")

        for brand, docs in docs_by_brand.items():
            if len(docs) >= self.BRAND_THRESHOLD:
                print(f"  Building {brand} model ({len(docs)} articles)...")
                model = self.build_brand_model(brand, docs)
                brand_models[brand] = model

                if save:
                    brand_path = self.corpora_dir / brand / "voice_model.json"
                    model.save(brand_path)
            else:
                print(f"  Skipping {brand} ({len(docs)} articles < {self.BRAND_THRESHOLD})")
                skipped_brands.append((brand, len(docs)))

        # Collect stats
        articles_by_type = {t: len(d) for t, d in docs_by_type.items()}
        articles_by_brand = {b: len(d) for b, d in docs_by_brand.items()}

        return BuildResult(
            house_model=house_model,
            type_models=type_models,
            brand_models=brand_models,
            skipped_brands=skipped_brands,
            articles_by_type=articles_by_type,
            articles_by_brand=articles_by_brand,
        )


# ============================================================================
# BLEND HELPER
# ============================================================================

def get_voice_layers(
    brand: str,
    article_type: str,
    corpora_dir: Path
) -> list[VoiceModel]:
    """
    Return available voice model layers in priority order.

    Always includes house model.
    Adds type model if that type exists.
    Adds brand model if that brand has one (10+ articles).

    Returns: [house, type?, brand?] — later layers have higher priority
    """
    corpora_dir = Path(corpora_dir)
    layers = []

    # Always include house
    house_path = corpora_dir / "_house" / "voice_model.json"
    if house_path.exists():
        layers.append(VoiceModel.load(house_path))

    # Add type if exists
    type_path = corpora_dir / "_types" / article_type / "voice_model.json"
    if type_path.exists():
        layers.append(VoiceModel.load(type_path))

    # Add brand if exists
    brand_path = corpora_dir / brand / "voice_model.json"
    if brand_path.exists():
        layers.append(VoiceModel.load(brand_path))

    return layers


def available_layers(brand: str, article_type: str, corpora_dir: Path) -> list[str]:
    """
    Return names of available layers.

    Returns list like: ['house', 'type:bonus_page', 'brand:vave']
    """
    corpora_dir = Path(corpora_dir)
    result = []

    house_path = corpora_dir / "_house" / "voice_model.json"
    if house_path.exists():
        result.append("house")

    type_path = corpora_dir / "_types" / article_type / "voice_model.json"
    if type_path.exists():
        result.append(f"type:{article_type}")

    brand_path = corpora_dir / brand / "voice_model.json"
    if brand_path.exists():
        result.append(f"brand:{brand}")

    return result


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def print_build_summary(result: BuildResult):
    """Print build summary to console."""
    print("\n" + result.summary())

    # Print headline stats
    fp = result.house_model.fingerprint
    print("\n=== House Model Headline Stats ===")
    print(f"Second-person count: {fp.second_person_count:,}")
    print(f"Third-person breakdown:")
    print(f"  - Reader-ref (convertible): {fp.reader_ref_count:,}")
    print(f"  - Generic noun (not convertible): {fp.generic_noun_count:,}")
    print(f"  - Unclear: {fp.unclear_person_count:,}")
    print(f"  - Total: {fp.third_person_count:,}")
    print(f"Person ratio (second / reader-ref): {fp.person_ratio}:1 (target: 10-30:1)")
    print(f"Mean sentence length: {fp.sentence_length_mean} words (target: 14-17)")
    print(f"Total words analyzed: {fp.total_words:,}")
    print(f"Total sentences: {fp.total_sentences:,}")


if __name__ == "__main__":
    import sys

    corpora_dir = Path("corpora")

    if len(sys.argv) > 1 and sys.argv[1] == "index":
        # Generate/regenerate corpus_index.csv
        generate_corpus_index(corpora_dir)
    else:
        # Build all models
        # Load stop words from standards if available
        try:
            from core.standards_engine import StandardsEngine
            engine = StandardsEngine()
            standards = engine.load_defaults()
            hard_words = standards.stop_words.hard
            soft_words = standards.stop_words.soft
        except Exception:
            hard_words = []
            soft_words = []

        builder = VoiceModelBuilder(
            corpora_dir,
            hard_stop_words=hard_words,
            soft_stop_words=soft_words,
        )
        result = builder.build_all()
        print_build_summary(result)
