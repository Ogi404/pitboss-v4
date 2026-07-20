"""
Pitboss v4 - iGaming Domain Dictionary

Corpus-grounded dictionary for suppressing MORFOLOGIK spelling false positives.
Extracts domain terms (brand names, game providers, payment methods, industry jargon)
from approved corpus articles.

Key rules:
- MULTI-ARTICLE THRESHOLD: Term must appear in 2+ different articles
- EXACT-TOKEN MATCHING: No prefix/suffix matching (HellSpin != HellSpins)
- SPELLING-ONLY: Only suppresses MORFOLOGIK, other grammar rules still apply
"""

from __future__ import annotations
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# PATHS
# =============================================================================

# Default paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
CORPORA_PATH = PROJECT_ROOT / "corpora"
KNOWN_OPERATORS_PATH = PROJECT_ROOT / "config" / "known_operators.txt"
CACHE_PATH = PROJECT_ROOT / "deterministic" / "domain_terms.json"


# =============================================================================
# SEED TERMS (iGaming common nouns that might not hit 2+ article threshold)
# =============================================================================

IGAMING_SEED_TERMS = {
    # Industry terms
    'igaming', 'paytable', 'payline', 'paylines', 'pokies', 'pokie',
    'megaways', 'rtp', 'wagering', 'cashout', 'freeroll', 'freebet',
    'freespins', 'freespin', 'rollover', 'playthrough', 'bankroll',
    'highroller', 'jackpot', 'jackpots', 'multiline', 'payouts',

    # Payment methods (common ones)
    'bitcoin', 'ethereum', 'litecoin', 'dogecoin', 'tether', 'usdt',
    'crypto', 'cryptocurrency', 'cryptocurrencies', 'ewallet', 'ewallets',

    # Licensing jurisdictions
    'curacao', 'curaçao', 'mga', 'ukgc', 'kahnawake',

    # Game providers (smaller studios that may not hit 2+ article threshold)
    'dynabit', 'netgames', 'reevo', 'spinmatic', 'fugaso', 'belatra',
    'spribe', 'bgaming', 'booongo', 'endorphina', 'habanero', 'kalamba',
    'wazdan', 'yggdrasil', 'thunderkick', 'relax', 'nolimit', 'hacksaw',

    # Brand-related (Hell from HellSpin context)
    'hell',
}


# =============================================================================
# CORPUS EXTRACTION
# =============================================================================

def extract_tokens_from_text(text: str) -> set[str]:
    """
    Extract potential domain terms from text.

    Patterns:
    - CamelCase: NetEnt, CashtoCode, HellSpin
    - Capitalized words: Paysafecard, Flexepin
    - camelCase: iGaming
    - Compound words with capital: Quickspin, Spinmatic
    """
    tokens = set()

    # Find all word tokens
    for match in re.finditer(r'\b[A-Za-z][A-Za-z0-9]*\b', text):
        word = match.group()

        # Skip very short words (likely not brand names)
        if len(word) < 3:
            continue

        # Skip common English words (basic filter)
        if word.lower() in COMMON_ENGLISH_WORDS:
            continue

        # Include if:
        # 1. Contains uppercase after first char (CamelCase/camelCase)
        # 2. Is a capitalized proper noun (but not at sentence start - hard to detect)
        # 3. Matches known patterns

        if re.search(r'[a-z][A-Z]', word):  # camelCase or CamelCase
            tokens.add(word)
        elif word[0].isupper() and len(word) > 4:  # Capitalized, 5+ chars
            tokens.add(word)

    return tokens


# Common English words to exclude from domain term extraction
COMMON_ENGLISH_WORDS = {
    'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had',
    'her', 'was', 'one', 'our', 'out', 'has', 'his', 'how', 'its', 'may',
    'new', 'now', 'old', 'see', 'way', 'who', 'did', 'get', 'let', 'put',
    'say', 'she', 'too', 'use', 'also', 'back', 'been', 'call', 'come',
    'could', 'each', 'find', 'first', 'from', 'give', 'good', 'have',
    'here', 'into', 'just', 'know', 'like', 'long', 'look', 'made', 'make',
    'many', 'more', 'most', 'much', 'must', 'name', 'need', 'next', 'only',
    'other', 'over', 'part', 'same', 'some', 'such', 'take', 'than', 'that',
    'them', 'then', 'there', 'these', 'they', 'this', 'time', 'very', 'want',
    'well', 'were', 'what', 'when', 'which', 'while', 'will', 'with', 'work',
    'would', 'year', 'your', 'about', 'after', 'being', 'before', 'between',
    'both', 'down', 'during', 'even', 'every', 'great', 'high', 'however',
    'keep', 'last', 'little', 'might', 'never', 'often', 'place', 'point',
    'right', 'should', 'still', 'think', 'those', 'through', 'under', 'where',
    'world', 'years', 'always', 'another', 'around', 'because', 'before',
    'below', 'better', 'change', 'different', 'doing', 'enough', 'going',
    'having', 'large', 'later', 'number', 'people', 'possible', 'present',
    'rather', 'second', 'several', 'since', 'small', 'something', 'state',
    'things', 'today', 'using', 'without', 'within', 'following', 'general',
    'given', 'important', 'information', 'including', 'making', 'means',
    'nothing', 'once', 'order', 'particular', 'perhaps', 'process', 'provide',
    'real', 'reason', 'result', 'system', 'taken', 'times', 'until', 'whether',
    'whole', 'working', 'written',
    # Gambling-related common words (not brand names)
    'casino', 'casinos', 'slot', 'slots', 'bonus', 'bonuses', 'game', 'games',
    'play', 'player', 'players', 'playing', 'spin', 'spins', 'win', 'wins',
    'winning', 'deposit', 'deposits', 'withdraw', 'withdrawal', 'account',
    'welcome', 'offer', 'offers', 'free', 'match', 'table', 'tables', 'live',
    'dealer', 'dealers', 'betting', 'odds', 'sports', 'roulette', 'blackjack',
    'poker', 'baccarat', 'craps', 'video', 'online', 'mobile', 'app', 'site',
    'website', 'software', 'provider', 'providers', 'license', 'licensed',
    'support', 'customer', 'service', 'payment', 'payments', 'method', 'methods',
    'australia', 'australian', 'canada', 'canadian', 'review', 'reviews',
}


def scan_corpus(corpora_path: Path) -> dict[str, set[str]]:
    """
    Scan all .docx files in corpus and extract potential domain terms.

    Returns: {term: set of article paths where it appears}
    """
    from ingest.docx_reader import read_docx

    term_to_articles: dict[str, set[str]] = defaultdict(set)

    if not corpora_path.exists():
        logger.warning(f"Corpora path not found: {corpora_path}")
        return term_to_articles

    # Find all .docx files
    docx_files = list(corpora_path.rglob("*.docx"))
    logger.info(f"Scanning {len(docx_files)} corpus articles...")

    for docx_path in docx_files:
        try:
            doc = read_docx(docx_path)
            text = doc.full_text() if callable(doc.full_text) else doc.full_text

            tokens = extract_tokens_from_text(text)
            article_id = str(docx_path.relative_to(corpora_path))

            for token in tokens:
                term_to_articles[token.lower()].add(article_id)

        except Exception as e:
            logger.warning(f"Failed to read {docx_path}: {e}")
            continue

    return term_to_articles


def build_dictionary(
    corpora_path: Path = CORPORA_PATH,
    known_operators_path: Path = KNOWN_OPERATORS_PATH,
    min_articles: int = 2,
) -> set[str]:
    """
    Build the domain dictionary from all sources.

    Args:
        corpora_path: Path to corpus directory
        known_operators_path: Path to known_operators.txt
        min_articles: Minimum number of articles a term must appear in

    Returns:
        Set of lowercase domain terms
    """
    terms = set()

    # 1. Corpus extraction (terms appearing in 2+ articles)
    logger.info("Extracting terms from corpus...")
    term_counts = scan_corpus(corpora_path)

    corpus_terms = {
        term for term, articles in term_counts.items()
        if len(articles) >= min_articles
    }
    logger.info(f"Found {len(corpus_terms)} terms appearing in {min_articles}+ articles")
    terms.update(corpus_terms)

    # 2. Known operators
    if known_operators_path.exists():
        with open(known_operators_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Normalize to lowercase for matching
                    terms.add(line.lower())
        logger.info(f"Added operators from {known_operators_path}")

    # 3. Seed terms
    terms.update(IGAMING_SEED_TERMS)
    logger.info(f"Added {len(IGAMING_SEED_TERMS)} seed terms")

    logger.info(f"Total dictionary size: {len(terms)} terms")
    return terms


def save_dictionary(terms: set[str], cache_path: Path = CACHE_PATH) -> None:
    """Save dictionary to JSON cache."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(sorted(terms), f, indent=2)
    logger.info(f"Saved dictionary to {cache_path}")


def load_dictionary(cache_path: Path = CACHE_PATH) -> Optional[set[str]]:
    """Load dictionary from JSON cache."""
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            terms = json.load(f)
        return set(terms)
    except Exception as e:
        logger.warning(f"Failed to load dictionary cache: {e}")
        return None


# =============================================================================
# DICTIONARY MANAGER
# =============================================================================

class DomainDictionary:
    """
    Manager for the iGaming domain dictionary.

    Provides efficient lookup for MORFOLOGIK suppression.
    Uses exact-token matching only (no prefix/suffix).
    """

    _instance: Optional['DomainDictionary'] = None
    _terms: set[str]

    def __init__(self, terms: Optional[set[str]] = None):
        if terms is not None:
            self._terms = terms
        else:
            # Try to load from cache, or build fresh
            cached = load_dictionary()
            if cached is not None:
                self._terms = cached
                logger.info(f"Loaded {len(self._terms)} domain terms from cache")
            else:
                logger.info("Building domain dictionary from corpus...")
                self._terms = build_dictionary()
                save_dictionary(self._terms)

    @classmethod
    def get_instance(cls) -> 'DomainDictionary':
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def rebuild(cls) -> 'DomainDictionary':
        """Force rebuild from corpus."""
        logger.info("Rebuilding domain dictionary...")
        terms = build_dictionary()
        save_dictionary(terms)
        cls._instance = cls(terms)
        return cls._instance

    def is_domain_term(self, word: str) -> bool:
        """
        Check if word is a known domain term.

        EXACT-TOKEN MATCHING ONLY:
        - "HellSpin" matches if "hellspin" in dictionary
        - "HellSpins" does NOT match (different token)
        - Case-insensitive comparison
        - Strips trailing punctuation before matching
        """
        # Normalize: lowercase, strip trailing punctuation
        normalized = word.lower().rstrip(".,;:!?'\"")

        # Exact match only
        return normalized in self._terms

    @property
    def term_count(self) -> int:
        return len(self._terms)

    def __contains__(self, word: str) -> bool:
        return self.is_domain_term(word)


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI for rebuilding the dictionary."""
    import argparse

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    parser = argparse.ArgumentParser(description='Build iGaming domain dictionary')
    parser.add_argument('--rebuild', action='store_true', help='Force rebuild from corpus')
    parser.add_argument('--stats', action='store_true', help='Show dictionary statistics')
    parser.add_argument('--check', type=str, help='Check if a word is in dictionary')

    args = parser.parse_args()

    if args.rebuild:
        dictionary = DomainDictionary.rebuild()
        print(f"\nDictionary rebuilt: {dictionary.term_count} terms")

    elif args.check:
        dictionary = DomainDictionary.get_instance()
        word = args.check
        result = dictionary.is_domain_term(word)
        print(f"'{word}' in dictionary: {result}")

    elif args.stats:
        dictionary = DomainDictionary.get_instance()
        print(f"Dictionary size: {dictionary.term_count} terms")

        # Show sample terms
        terms = load_dictionary()
        if terms:
            sample = sorted(terms)[:20]
            print(f"\nSample terms: {sample}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
