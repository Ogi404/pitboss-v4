"""
Pitboss v4 - Brand Names Check

Deterministic check for brand name consistency per §9:
1. Own-brand normalization - ensure correct casing/spacing (auto-applicable)
2. Competitor detection - flag other operator names (proposal only)

The operator's own name must be spelled/cased consistently.
Other operators' names should not appear unless in brief keywords.
"""

from __future__ import annotations
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from core.check_base import DeterministicCheck, register_check
from core.document import Document
from core.finding import Finding, FindingFactory, Category


# =============================================================================
# CONFIGURATION
# =============================================================================

# Logger for validation warnings
logger = logging.getLogger(__name__)

# Path to known operators file
OPERATORS_FILE = Path(__file__).parent.parent / "config" / "known_operators.txt"

# Path to corpora for validation
CORPORA_PATH = Path(__file__).parent.parent / "corpora"

# Dominance threshold for auto-applicable normalizations
# >= threshold: own-brand normalization is AUTO (auto_applicable=True)
# < threshold: own-brand normalization is PROPOSAL (auto_applicable=False)
DOMINANCE_THRESHOLD = 0.85

# Ambiguous operator names that are also common gambling words
# Only flag these when capitalized AND not preceded by articles
AMBIGUOUS_OPERATORS = {'stake', 'spin', 'royal', 'national', 'bet'}

# Words that precede common word usage (not operator names)
COMMON_WORD_PREFIXES = (
    'a ', 'an ', 'the ', 'your ', 'my ', 'our ', 'their ',
    'place ', 'high ', 'low ', 'minimum ', 'maximum ', 'free ',
)

# URL/domain pattern for exclusion
URL_PATTERN = re.compile(
    r'https?://\S+|www\.\S+|\S+\.(com|org|net|co\.uk|io|ai|bet|casino|gg)\S*',
    re.IGNORECASE
)

# Email pattern for exclusion
EMAIL_PATTERN = re.compile(r'\b[\w.+-]+@[\w.-]+\.\w+\b', re.IGNORECASE)

# Quoted string patterns
QUOTE_PATTERNS = [
    re.compile(r'"[^"]*"'),
    re.compile(r"'[^']*'"),
    re.compile(r'\u201c[^\u201d]*\u201d'),  # Curly double quotes
    re.compile(r'\u2018[^\u2019]*\u2019'),  # Curly single quotes
]


# =============================================================================
# CHECK IMPLEMENTATION
# =============================================================================

@register_check
class BrandNamesCheck(DeterministicCheck):
    """
    Checks for brand name consistency.

    Sub-check 1: Own-brand normalization
    - Detects variants of the brand's name with wrong casing/spacing
    - Auto-applicable when unambiguous

    Sub-check 2: Competitor detection
    - Flags mentions of other known operators
    - Proposal only (never auto-remove)
    """

    def __init__(self) -> None:
        super().__init__()
        self._known_operators: set[str] = set()
        self._operators_normalized: dict[str, str] = {}
        self._warning: Optional[str] = None
        self._protected_operator: Optional[str] = None  # Don't flag this as competitor
        self._load_known_operators()

    def get_warning(self) -> Optional[str]:
        """Return any warning generated during the check."""
        return self._warning

    def _load_known_operators(self) -> None:
        """Load known operators from config file."""
        if not OPERATORS_FILE.exists():
            return

        with open(OPERATORS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Normalize to prevent duplicates (bet365 vs Bet365)
                    normalized = line.lower().replace(' ', '').replace('-', '')
                    # Only add if not already seen (keeps first occurrence)
                    if normalized not in self._operators_normalized:
                        self._known_operators.add(line)
                        self._operators_normalized[normalized] = line

    def _detect_dominant_operator(
        self,
        document: Document,
        configured_brand: str,
    ) -> Optional[str]:
        """
        Detect the dominant known-operator in the article.

        Scans for all known operators, counts mentions, weights title/H1.
        Returns the dominant operator if clearly dominant AND different
        from configured brand. Returns None if no clear dominant or
        dominant matches configured brand.

        Args:
            document: The document to scan
            configured_brand: The configured brand_name

        Returns:
            Dominant operator name if mismatch detected, None otherwise
        """
        if not self._known_operators:
            return None

        text = document.full_text()
        title = document.title or ""

        # Get title/H1 text for weighting
        h1_text = ""
        for el in document.elements[:5]:
            if hasattr(el, 'text'):
                h1_text += el.text + " "

        # Count operator mentions
        counts: dict[str, int] = {}
        in_title: set[str] = set()

        for operator in self._known_operators:
            pattern = re.compile(rf'\b{re.escape(operator)}\b', re.IGNORECASE)
            matches = pattern.findall(text)
            if matches:
                counts[operator] = len(matches)
                # Check if in title/H1
                if pattern.search(title) or pattern.search(h1_text):
                    in_title.add(operator)

        if not counts:
            return None

        # Sort by count descending
        sorted_ops = sorted(counts.items(), key=lambda x: -x[1])
        top_op, top_count = sorted_ops[0]

        # Check for clear dominance:
        # - Must have significant mentions (at least 5)
        # - Must be clearly ahead of runner-up (2x or 10+ more)
        if top_count < 5:
            return None

        if len(sorted_ops) > 1:
            runner_up_count = sorted_ops[1][1]
            margin = top_count - runner_up_count
            # Not dominant if runner-up is close
            if runner_up_count > 0 and top_count < runner_up_count * 2 and margin < 10:
                return None

        # Bonus confidence if in title
        # (we don't require it, but it confirms dominance)

        # Check if dominant matches configured brand
        configured_normalized = configured_brand.lower().replace(' ', '').replace('-', '')
        top_normalized = top_op.lower().replace(' ', '').replace('-', '')

        if top_normalized == configured_normalized:
            # No mismatch - dominant IS the configured brand
            return None

        # Mismatch detected: dominant operator differs from configured brand
        return top_op

    def _validate_canonical_against_corpus(
        self,
        brand_folder: str,
        canonical: str,
    ) -> None:
        """
        Warn if canonical doesn't match corpus dominant form.

        The corpus is ground truth - a canonical that contradicts it
        is a configuration bug that would cause false normalizations.
        """
        corpus_path = CORPORA_PATH / brand_folder
        if not corpus_path.exists():
            return  # No corpus to validate against

        # Import here to avoid circular dependency
        try:
            from ingest.docx_reader import read_docx
        except ImportError:
            return  # Can't validate without reader

        # Build potential forms to check
        canonical_normalized = canonical.lower().replace(' ', '').replace('-', '')
        forms_to_check = [canonical]

        # Add common variants
        if ' ' in canonical:
            forms_to_check.append(canonical.replace(' ', ''))
        else:
            # Try adding space at case boundaries
            parts = []
            current = ""
            for i, char in enumerate(canonical):
                if i > 0 and char.isupper() and canonical[i-1].islower():
                    parts.append(current)
                    current = char
                else:
                    current += char
            if current:
                parts.append(current)
            if len(parts) > 1:
                forms_to_check.append(' '.join(parts))

        # Count occurrences in corpus
        counts: Counter[str] = Counter()
        articles = list(corpus_path.glob('*.docx'))[:10]  # Sample up to 10 articles

        for article in articles:
            try:
                doc = read_docx(article)
                text = doc.full_text()

                for form in forms_to_check:
                    pattern = re.compile(rf'\b{re.escape(form)}\b')
                    matches = pattern.findall(text)
                    counts[form] += len(matches)
            except Exception:
                pass

        if not counts:
            return

        # Check if another form is more common
        sorted_forms = sorted(counts.items(), key=lambda x: -x[1])
        dominant_form, dominant_count = sorted_forms[0]
        canonical_count = counts.get(canonical, 0)

        if dominant_form != canonical and dominant_count > canonical_count:
            logger.warning(
                f"Brand canonical mismatch: '{canonical}' configured but "
                f"'{dominant_form}' is dominant in corpus ({dominant_count} vs {canonical_count}). "
                f"Consider updating brand YAML to use corpus-dominant form."
            )

    def _get_name(self) -> str:
        return "brand_names"

    def _get_display_name(self) -> str:
        return "Brand Names Check"

    def _get_category(self) -> Category:
        return "brand_names"

    def _get_description(self) -> str:
        return (
            "Ensures consistent brand name formatting and flags "
            "competitor brand mentions per §9."
        )

    def _get_required_standards(self) -> tuple[str, ...]:
        return ("brand_name",)

    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """Find brand name issues in the document."""
        findings: list[Finding] = []

        # Reset per-run state
        self._warning = None
        self._protected_operator = None

        # Get canonical brand name
        canonical = getattr(standards, 'brand_name', None)
        if not canonical:
            return findings

        # Mismatch guard: detect if article's dominant operator differs from configured brand
        dominant_op = self._detect_dominant_operator(document, canonical)
        if dominant_op:
            # Mismatch detected - don't flag dominant as competitor, emit warning
            self._protected_operator = dominant_op
            self._warning = (
                f"Configured brand '{canonical}' but article appears to be about "
                f"'{dominant_op}' - check the --brand setting"
            )
            logger.warning(self._warning)

        # Get brand normalization mappings if available
        brand_norm = getattr(standards, 'brand_normalization', None)
        norm_mappings = brand_norm.mappings if brand_norm else {}

        # Get canonical dominance (default to 1.0 if not set = AUTO)
        dominance = getattr(standards, 'canonical_dominance', 1.0)

        # Build pattern for own-brand detection
        brand_pattern = self._build_brand_pattern(canonical)

        # Process all text elements
        for para in document.paragraphs():
            findings.extend(self._check_element(
                para, document, canonical, norm_mappings, brand_pattern, dominance
            ))

        for heading in document.headings():
            findings.extend(self._check_element(
                heading, document, canonical, norm_mappings, brand_pattern, dominance
            ))

        for table in document.tables():
            for row in table.rows:
                for cell in row.cells:
                    findings.extend(self._check_element(
                        cell, document, canonical, norm_mappings, brand_pattern, dominance
                    ))

        for lst in document.lists():
            for item in lst.items:
                findings.extend(self._check_element(
                    item, document, canonical, norm_mappings, brand_pattern, dominance
                ))

        return findings

    def _check_element(
        self,
        element: Any,
        document: Document,
        canonical: str,
        norm_mappings: dict[str, str],
        brand_pattern: re.Pattern,
        dominance: float,
    ) -> list[Finding]:
        """Check element for brand name issues."""
        findings: list[Finding] = []
        text = element.text

        if not text:
            return findings

        # Find excluded spans (URLs, emails, quotes)
        excluded = self._find_excluded_spans(text)

        # Sub-check 1: Own-brand normalization
        findings.extend(self._check_own_brand(
            element, document, text, canonical, norm_mappings, brand_pattern, excluded, dominance
        ))

        # Sub-check 2: Competitor detection
        findings.extend(self._check_competitors(
            element, document, text, canonical, excluded
        ))

        return findings

    # =========================================================================
    # SUB-CHECK 1: OWN-BRAND NORMALIZATION
    # =========================================================================

    def _build_brand_pattern(self, canonical: str) -> re.Pattern:
        """Build regex pattern to match brand name variants."""
        # Split on case boundaries and numbers
        # "KoiFortune" → ["Koi", "Fortune"]
        # "22Bet" → ["22", "Bet"]
        # "BetLabel" → ["Bet", "Label"]
        parts = self._split_brand_parts(canonical)

        # If we got only one part (no clear boundaries), try to infer
        # common word boundaries by looking for lowercase runs
        if len(parts) == 1 and len(canonical) > 3:
            # Try to split on common word patterns
            # E.g., "Koifortune" → might be "Koi" + "fortune"
            parts = self._infer_brand_parts(canonical)

        if not parts or len(parts) == 1:
            # Fallback: just match the canonical with optional spaces
            escaped = re.escape(canonical)
            return re.compile(rf'\b{escaped}\b', re.IGNORECASE)

        # Build pattern that matches parts with optional spaces/hyphens
        pattern_parts = []
        for part in parts:
            # Escape and make case-insensitive match
            escaped = re.escape(part)
            pattern_parts.append(escaped)

        # Join with optional whitespace/hyphen
        pattern_str = r'[\s\-]*'.join(pattern_parts)

        # Add word boundary at start (handle leading numbers)
        if parts[0][0].isdigit():
            pattern_str = rf'(?<![a-zA-Z0-9]){pattern_str}'
        else:
            pattern_str = rf'\b{pattern_str}'

        # Add word boundary at end
        pattern_str = rf'{pattern_str}\b'

        return re.compile(pattern_str, re.IGNORECASE)

    def _infer_brand_parts(self, canonical: str) -> list[str]:
        """Infer word parts from brand name using common gambling words."""
        # Common gambling word endings/components
        common_parts = [
            'fortune', 'casino', 'bet', 'spin', 'slots', 'play',
            'game', 'games', 'royal', 'king', 'queen', 'jack',
            'lucky', 'win', 'poker', 'roulette', 'blackjack',
            'chan', 'rave', 'ando', 'vave', 'ivi', 'hell',
        ]

        canonical_lower = canonical.lower()

        # Try to find a split point
        for part in common_parts:
            if canonical_lower.endswith(part) and len(canonical_lower) > len(part):
                prefix_len = len(canonical_lower) - len(part)
                prefix = canonical[:prefix_len]
                suffix = canonical[prefix_len:]
                return [prefix, suffix]
            if canonical_lower.startswith(part) and len(canonical_lower) > len(part):
                suffix = canonical[len(part):]
                prefix = canonical[:len(part)]
                return [prefix, suffix]

        return [canonical]

    def _split_brand_parts(self, name: str) -> list[str]:
        """Split brand name into constituent parts."""
        # Split on transitions: lowercase→uppercase, letter→number, number→letter
        parts = []
        current = ""

        for i, char in enumerate(name):
            if i == 0:
                current = char
                continue

            prev = name[i - 1]

            # Detect boundaries
            is_boundary = False

            # lowercase → uppercase
            if prev.islower() and char.isupper():
                is_boundary = True
            # letter → digit
            elif prev.isalpha() and char.isdigit():
                is_boundary = True
            # digit → letter
            elif prev.isdigit() and char.isalpha():
                is_boundary = True
            # space or hyphen
            elif char in ' -':
                if current:
                    parts.append(current)
                current = ""
                continue

            if is_boundary:
                if current:
                    parts.append(current)
                current = char
            else:
                current += char

        if current:
            parts.append(current)

        return parts

    def _check_own_brand(
        self,
        element: Any,
        document: Document,
        text: str,
        canonical: str,
        norm_mappings: dict[str, str],
        brand_pattern: re.Pattern,
        excluded: list[tuple[int, int]],
        dominance: float,
    ) -> list[Finding]:
        """Check for own-brand variants that need normalization."""
        findings: list[Finding] = []

        # Determine auto_applicable based on dominance threshold
        # High dominance (>= 85%) = AUTO, low dominance = PROPOSAL
        auto_applicable = dominance >= DOMINANCE_THRESHOLD

        for match in brand_pattern.finditer(text):
            surface = match.group(0)
            start = match.start()
            end = match.end()

            # Skip if in excluded span
            if self._in_excluded_span(start, end, excluded):
                continue

            # Skip if already correct
            if surface == canonical:
                continue

            # Check if this is a known variant from mappings
            if norm_mappings and surface in norm_mappings:
                correct = norm_mappings[surface]
            else:
                correct = canonical

            # Skip if surface matches correct (after mapping)
            if surface == correct:
                continue

            abs_start = element.start_offset + start
            abs_end = element.start_offset + end
            location = document.location_for_span(abs_start, abs_end)

            findings.append(FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="warning",
                confidence=0.95,
                location=location,
                original_text=surface,
                proposed_text=correct,
                reasoning=(
                    f"Normalize brand name '{surface}' to '{correct}' for consistency."
                ),
                auto_applicable=auto_applicable,
                metadata={
                    "sub_check": "own_brand",
                    "canonical": canonical,
                    "dominance": dominance,
                },
            ))

        return findings

    # =========================================================================
    # SUB-CHECK 2: COMPETITOR DETECTION
    # =========================================================================

    def _check_competitors(
        self,
        element: Any,
        document: Document,
        text: str,
        own_brand: str,
        excluded: list[tuple[int, int]],
    ) -> list[Finding]:
        """Check for competitor brand mentions."""
        findings: list[Finding] = []

        # Normalize own brand for comparison
        own_normalized = own_brand.lower().replace(' ', '').replace('-', '')

        # Normalize protected operator (mismatch guard)
        protected_normalized = None
        if self._protected_operator:
            protected_normalized = self._protected_operator.lower().replace(' ', '').replace('-', '')

        # Check each known operator
        for operator in self._known_operators:
            # Skip own brand
            op_normalized = operator.lower().replace(' ', '').replace('-', '')
            if op_normalized == own_normalized:
                continue

            # Skip protected operator (mismatch guard - article's actual brand)
            if protected_normalized and op_normalized == protected_normalized:
                continue

            # Find mentions of this operator
            # Use word boundary matching
            pattern = self._build_operator_pattern(operator)

            for match in pattern.finditer(text):
                surface = match.group(0)
                start = match.start()
                end = match.end()

                # Skip if in excluded span
                if self._in_excluded_span(start, end, excluded):
                    continue

                # Check if this is an ambiguous operator name
                if not self._is_competitor_mention(surface, text, start):
                    continue

                abs_start = element.start_offset + start
                abs_end = element.start_offset + end
                location = document.location_for_span(abs_start, abs_end)

                findings.append(FindingFactory.create(
                    check_name=self.name,
                    category=self.category,
                    severity="warning",
                    confidence=0.80,
                    location=location,
                    original_text=surface,
                    proposed_text=None,  # No auto-replacement
                    reasoning=(
                        f"Competitor brand '{surface}' mentioned. Per §9, other "
                        f"operators should not appear unless in brief keywords."
                    ),
                    auto_applicable=False,  # Always proposal
                    metadata={
                        "sub_check": "competitor",
                        "competitor_name": operator,
                    },
                ))

        return findings

    def _build_operator_pattern(self, operator: str) -> re.Pattern:
        """Build pattern to match an operator name."""
        # Handle operators with numbers (bet365, 888casino, 1xBet)
        escaped = re.escape(operator)

        # Word boundary handling for operators starting with numbers
        if operator[0].isdigit():
            pattern = rf'(?<![a-zA-Z0-9]){escaped}(?![a-zA-Z0-9])'
        else:
            pattern = rf'\b{escaped}\b'

        return re.compile(pattern, re.IGNORECASE)

    def _is_competitor_mention(
        self,
        surface: str,
        text: str,
        start: int,
    ) -> bool:
        """Check if surface form is a competitor mention vs common word."""
        surface_lower = surface.lower()

        # Check if this is an ambiguous operator name
        if surface_lower not in AMBIGUOUS_OPERATORS:
            return True  # Not ambiguous, definitely a competitor

        # Ambiguous word: only flag if capitalized
        if not surface[0].isupper():
            return False  # Lowercase "stake" is common word

        # Check preceding context for articles/possessives
        context_start = max(0, start - 15)
        context_before = text[context_start:start].lower()

        for prefix in COMMON_WORD_PREFIXES:
            if context_before.endswith(prefix):
                return False  # Preceded by article → likely common word

        return True  # Capitalized without article → likely operator

    # =========================================================================
    # EXCLUSION HELPERS
    # =========================================================================

    def _find_excluded_spans(self, text: str) -> list[tuple[int, int]]:
        """Find spans to exclude: URLs, emails, quoted strings."""
        excluded: list[tuple[int, int]] = []

        # URLs
        for match in URL_PATTERN.finditer(text):
            excluded.append((match.start(), match.end()))

        # Emails
        for match in EMAIL_PATTERN.finditer(text):
            excluded.append((match.start(), match.end()))

        # Quoted strings
        for pattern in QUOTE_PATTERNS:
            for match in pattern.finditer(text):
                excluded.append((match.start(), match.end()))

        return excluded

    def _in_excluded_span(
        self,
        start: int,
        end: int,
        excluded: list[tuple[int, int]],
    ) -> bool:
        """Check if position is inside an excluded span."""
        for ex_start, ex_end in excluded:
            if start >= ex_start and end <= ex_end:
                return True
        return False
