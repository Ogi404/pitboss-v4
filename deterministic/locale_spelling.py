"""
Pitboss v4 - Locale Spelling Check

Deterministic check for regional spelling variants per §4.
Not a spellchecker - a dictionary-swap for British↔American differences.

Regions:
- british: UK, IN, LK, PK, SG, MM, HK, KE, NG (and Australian/NZ follow)
- american: US, PH, TW, KR, JP
- canadian: HYBRID - British -our/-re but American -ize

Canadian is critical - Koifortune uses Canadian spelling.
"""

from __future__ import annotations
import re
from typing import Any

from core.check_base import DeterministicCheck, register_check
from core.document import Document
from core.finding import Finding, FindingFactory, Category


# =============================================================================
# WORD LISTS
# =============================================================================

# -ise/-ize words (British uses -ise, American/Canadian use -ize)
# List in British (-ise) form - includes verb and noun forms
ISE_IZE_WORDS = [
    # Verbs
    'organise', 'customise', 'prioritise', 'realise', 'recognise',
    'specialise', 'maximise', 'minimise', 'optimise', 'legalise',
    'authorise', 'categorise', 'emphasise', 'summarise', 'utilise',
    'apologise', 'criticise', 'harmonise', 'modernise', 'standardise',
    'normalise', 'visualise', 'finalise', 'capitalise', 'localise',
    'generalise', 'personalise', 'initialise', 'centralise', 'neutralise',
    'materialise', 'familiarise', 'memorise', 'characterise', 'symbolise',
    'analyse',  # British analyse → American analyze (special case)
    # Nouns (-isation/-ization)
    'organisation', 'customisation', 'prioritisation', 'realisation', 'recognition',
    'specialisation', 'maximisation', 'minimisation', 'optimisation', 'legalisation',
    'authorisation', 'categorisation', 'summarisation', 'utilisation',
    'harmonisation', 'modernisation', 'standardisation',
    'normalisation', 'visualisation', 'finalisation', 'capitalisation', 'localisation',
    'generalisation', 'personalisation', 'initialisation', 'centralisation', 'neutralisation',
    'materialisation', 'familiarisation', 'characterisation', 'symbolisation',
]

# -our/-or words (British/Canadian use -our, American uses -or)
# List in British (-our) form
OUR_OR_WORDS = [
    'colour', 'favour', 'behaviour', 'favourite', 'honour',
    'neighbour', 'flavour', 'labour', 'harbour', 'rumour',
    'humour', 'glamour', 'endeavour', 'savour', 'armour',
    'vapour', 'odour', 'vigour', 'valour', 'splendour',
    'candour', 'clamour', 'fervour', 'parlour', 'rancour',
]

# -re/-er words (British/Canadian use -re, American uses -er)
# List in British (-re) form
RE_ER_WORDS = [
    'centre', 'metre', 'theatre', 'fibre', 'litre',
    'calibre', 'lustre', 'sabre', 'sombre', 'spectre',
    'meagre', 'manoeuvre', 'reconnoitre',
]

# -lled/-led doubling (British doubles final L, American doesn't)
# List in British (doubled) form
LLED_LED_WORDS = [
    'travelled', 'travelling', 'traveller',
    'cancelled', 'cancelling', 'cancellation',
    'labelled', 'labelling',
    'modelled', 'modelling',
    'levelled', 'levelling',
    'tunnelled', 'tunnelling',
    'fuelled', 'fuelling',
    'signalled', 'signalling',
    'counselled', 'counselling', 'counsellor',
    'quarrelled', 'quarrelling',
    'marvelled', 'marvelling', 'marvellous',
    'jewellery',  # British jewellery → American jewelry
]

# -ogue/-og words (British uses -ogue, American uses -og)
# List in British (-ogue) form
OGUE_OG_WORDS = [
    'catalogue', 'dialogue', 'analogue', 'prologue', 'epilogue',
    'monologue', 'travelogue', 'demagogue',
]

# Other common swaps (British form → American form)
OTHER_BRITISH_AMERICAN = {
    'cheque': 'check',  # Financial
    'grey': 'gray',
    'programme': 'program',  # British programme → American program
    'enrol': 'enroll',
    'skilful': 'skillful',
    'fulfil': 'fulfill',
    'wilful': 'willful',
    'instalment': 'installment',
    'acknowledgement': 'acknowledgment',
    'judgement': 'judgment',
    'ageing': 'aging',
    'axe': 'ax',
    'defence': 'defense',
    'offence': 'offense',
    'pretence': 'pretense',
    'licence': 'license',  # Note: in British, licence=noun, license=verb
    'practise': 'practice',  # Note: in British, practice=noun, practise=verb
    'storey': 'story',  # Building floor
    'tyre': 'tire',  # Vehicle tire
    'kerb': 'curb',  # Road edge
    'draught': 'draft',  # Air current
    'plough': 'plow',
    'mould': 'mold',
    'smoulder': 'smolder',
    'aluminium': 'aluminum',
    'sulphur': 'sulfur',
    'sceptic': 'skeptic',
    'sceptical': 'skeptical',
    'scepticism': 'skepticism',
    'aeroplane': 'airplane',
    'artefact': 'artifact',
    'chequer': 'checker',
    'chequered': 'checkered',
    'cosy': 'cozy',
    'doughnut': 'donut',  # Though doughnut is also acceptable in US
    'gaol': 'jail',  # archaic British
    'moustache': 'mustache',
    'pyjamas': 'pajamas',
    'speciality': 'specialty',
    'encyclopaedia': 'encyclopedia',
    'mediaeval': 'medieval',  # Though medieval is now standard in British too
    'omelette': 'omelet',
    'annexe': 'annex',
    'disc': 'disk',  # Though both used in both regions depending on context
}

# Context-dependent words that require human review
# These have noun/verb distinctions or context-specific meanings
# Note: programme/program is actually in OTHER_BRITISH_AMERICAN for standard swap
# These are words where context determines correctness
CONTEXT_DEPENDENT = {
    # Currently empty - programme/program handled in standard swap
    # licence/license and practice/practise could go here but are complex
}


# =============================================================================
# SWAP MAP BUILDER
# =============================================================================

def _build_swap_maps() -> dict[str, dict[str, str]]:
    """
    Build swap maps for each spelling region.

    Each map: {wrong_spelling: correct_spelling}
    """
    # British target: American forms → British forms
    british_map: dict[str, str] = {}

    # -ize → -ise (including -isation → -ization)
    for word in ISE_IZE_WORDS:
        if 'isation' in word:  # organisation → organization
            american = word.replace('isation', 'ization')
            british_map[american] = word
        elif 'ise' in word:  # organise → organize
            american = word.replace('ise', 'ize')
            british_map[american] = word
        elif 'yse' in word:  # analyse → analyze
            american = word.replace('yse', 'yze')
            british_map[american] = word

    # -or → -our
    for word in OUR_OR_WORDS:
        american = word.replace('our', 'or')
        british_map[american] = word

    # -er → -re
    for word in RE_ER_WORDS:
        american = word.replace('re', 'er')
        british_map[american] = word

    # -led → -lled
    for word in LLED_LED_WORDS:
        # Handle various patterns
        if word == 'jewellery':
            british_map['jewelry'] = word
        elif 'lled' in word:
            american = word.replace('lled', 'led')
            british_map[american] = word
        elif 'lling' in word:
            american = word.replace('lling', 'ling')
            british_map[american] = word
        elif 'llor' in word:  # counsellor
            american = word.replace('llor', 'lor')
            british_map[american] = word
        elif 'llous' in word:  # marvellous
            american = word.replace('llous', 'lous')
            british_map[american] = word
        elif 'ller' in word:  # traveller
            american = word.replace('ller', 'ler')
            british_map[american] = word
        elif 'llation' in word:  # cancellation
            american = word.replace('llation', 'lation')
            british_map[american] = word

    # -og → -ogue
    for word in OGUE_OG_WORDS:
        american = word.replace('ogue', 'og')
        british_map[american] = word

    # Other swaps: American → British
    for british, american in OTHER_BRITISH_AMERICAN.items():
        british_map[american] = british

    # American target: British forms → American forms (reverse of british_map)
    american_map: dict[str, str] = {}
    for american, british in british_map.items():
        american_map[british] = american

    # Canadian: HYBRID
    # Uses British: -our, -re, cheque, grey
    # Uses American: -ize
    canadian_map: dict[str, str] = {}

    # British -our (swap American -or to British -our)
    for word in OUR_OR_WORDS:
        american = word.replace('our', 'or')
        canadian_map[american] = word

    # British -re (swap American -er to British -re)
    for word in RE_ER_WORDS:
        american = word.replace('re', 'er')
        canadian_map[american] = word

    # British cheque (swap American check)
    # Note: "check" has many meanings, so we'll only flag in context
    # For now, don't auto-swap check → cheque (too ambiguous)

    # British grey (swap American gray)
    canadian_map['gray'] = 'grey'

    # American -ize (swap British -ise to American -ize)
    for word in ISE_IZE_WORDS:
        if 'isation' in word:  # organisation → organization
            american = word.replace('isation', 'ization')
            canadian_map[word] = american  # British -isation → American -ization
        elif 'ise' in word:
            american = word.replace('ise', 'ize')
            canadian_map[word] = american  # British -ise → American -ize
        elif 'yse' in word:  # analyse → analyze
            american = word.replace('yse', 'yze')
            canadian_map[word] = american

    # Australian/NZ follow British
    australian_map = british_map.copy()
    new_zealand_map = british_map.copy()

    return {
        'british': british_map,
        'american': american_map,
        'canadian': canadian_map,
        'australian': australian_map,
        'new_zealand': new_zealand_map,
    }


# Pre-build the maps at module load
_SWAP_MAPS = _build_swap_maps()


# =============================================================================
# CHECK IMPLEMENTATION
# =============================================================================

@register_check
class LocaleSpellingCheck(DeterministicCheck):
    """
    Checks for regional spelling variants and proposes corrections.

    Detects:
    - American vs British spelling (-ize/-ise, -or/-our, -er/-re, etc.)
    - Canadian hybrid spelling (British -our/-re but American -ize)
    - Context-dependent words flagged for review

    Exclusions:
    - Quoted strings
    - URLs
    - Brand names (proper nouns)
    """

    def __init__(self) -> None:
        super().__init__()
        self._swap_maps = _SWAP_MAPS
        self._context_dependent = CONTEXT_DEPENDENT

    def _get_name(self) -> str:
        return "locale_spelling"

    def _get_display_name(self) -> str:
        return "Locale Spelling Check"

    def _get_category(self) -> Category:
        return "locale_spelling"

    def _get_description(self) -> str:
        return (
            "Checks for regional spelling variants (British/American/Canadian) "
            "and proposes corrections based on the brand's target market."
        )

    def _get_required_standards(self) -> tuple[str, ...]:
        return ("spelling_region",)

    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """Find spelling variants that don't match the target region."""
        findings: list[Finding] = []

        # Get spelling region from standards
        region = getattr(standards, 'spelling_region', 'british')
        swap_map = self._swap_maps.get(region, {})

        if not swap_map:
            return findings

        # Process paragraphs
        for para in document.paragraphs():
            findings.extend(self._check_element(para, document, swap_map, region))

        # Process headings
        for heading in document.headings():
            findings.extend(self._check_element(heading, document, swap_map, region))

        # Process list items
        for lst in document.lists():
            for item in lst.items:
                findings.extend(self._check_element(item, document, swap_map, region))

        # Process table cells
        for table in document.tables():
            for row in table.rows:
                for cell in row.cells:
                    findings.extend(self._check_element(cell, document, swap_map, region))

        return findings

    def _check_element(
        self,
        element: Any,
        document: Document,
        swap_map: dict[str, str],
        region: str,
    ) -> list[Finding]:
        """Check element text for wrong-variant words."""
        findings: list[Finding] = []
        text = element.text

        if not text:
            return findings

        # Find excluded spans (quoted strings, URLs)
        excluded_spans = self._find_excluded_spans(text)

        # Tokenize and check each word
        for match in re.finditer(r'\b[a-zA-Z]+\b', text):
            word = match.group(0)
            word_lower = word.lower()
            start = match.start()
            end = match.end()

            # Skip if in excluded span
            if self._in_excluded_span(start, end, excluded_spans):
                continue

            # Check standard swaps
            if word_lower in swap_map:
                correct = swap_map[word_lower]
                # Preserve case
                correct_cased = self._preserve_case(word, correct)

                abs_start = element.start_offset + start
                abs_end = element.start_offset + end
                location = document.location_for_span(abs_start, abs_end)

                findings.append(FindingFactory.create(
                    check_name=self.name,
                    category=self.category,
                    severity="warning",
                    confidence=0.95,
                    location=location,
                    original_text=word,
                    proposed_text=correct_cased,
                    reasoning=(
                        f"Use '{correct_cased}' instead of '{word}' for {region} spelling."
                    ),
                    auto_applicable=True,
                    metadata={
                        "region": region,
                        "original_word": word_lower,
                        "correct_word": correct,
                        "pattern_type": self._get_pattern_type(word_lower, correct),
                    },
                ))

            # Check context-dependent words
            elif word_lower in self._context_dependent:
                info = self._context_dependent[word_lower]

                # Determine swap based on region
                if region == 'american' and info.get('swap_american'):
                    correct = info['swap_american']
                elif region in ('british', 'australian', 'new_zealand') and info.get('swap_british'):
                    correct = info['swap_british']
                else:
                    continue  # No swap needed for this region

                correct_cased = self._preserve_case(word, correct)

                abs_start = element.start_offset + start
                abs_end = element.start_offset + end
                location = document.location_for_span(abs_start, abs_end)

                findings.append(FindingFactory.create(
                    check_name=self.name,
                    category=self.category,
                    severity="warning",
                    confidence=0.70,
                    location=location,
                    original_text=word,
                    proposed_text=correct_cased,
                    reasoning=(
                        f"'{word}' may need review: {info['note']}"
                    ),
                    auto_applicable=False,  # Always proposal for context-dependent
                    metadata={
                        "region": region,
                        "original_word": word_lower,
                        "correct_word": correct,
                        "context_dependent": True,
                        "note": info['note'],
                    },
                ))

        return findings

    def _get_pattern_type(self, original: str, correct: str) -> str:
        """Determine the pattern type for metadata."""
        # Check -ise/-ize pattern (including -isation/-ization)
        if 'ize' in original or 'ise' in original or 'ize' in correct or 'ise' in correct:
            return 'ise_ize'
        # Check -our/-or pattern (color/colour, favor/favour)
        if ('our' in original and 'or' in correct) or ('or' in original and 'our' in correct):
            # More specific: check if one has -our and other has -or in same position
            if 'our' in correct or 'our' in original:
                return 'our_or'
        # Check -re/-er pattern (centre/center)
        if (original.endswith('re') and correct.endswith('er')) or \
           (original.endswith('er') and correct.endswith('re')):
            return 're_er'
        # Check -lled/-led pattern (travelled/traveled)
        if 'lled' in original or 'lled' in correct or 'lling' in original or 'lling' in correct:
            return 'lled_led'
        # Check -ogue/-og pattern (catalogue/catalog)
        if 'ogue' in original or 'ogue' in correct:
            return 'ogue_og'
        return 'other'

    def _find_excluded_spans(self, text: str) -> list[tuple[int, int]]:
        """Find spans to exclude: quoted strings, URLs."""
        excluded: list[tuple[int, int]] = []

        # Quoted strings (single and double, including curly quotes)
        quote_patterns = [
            r'"[^"]*"',  # Double quotes
            r"'[^']*'",  # Single quotes
            r'\u201c[^\u201d]*\u201d',  # Curly double quotes
            r'\u2018[^\u2019]*\u2019',  # Curly single quotes
        ]
        for pattern in quote_patterns:
            for match in re.finditer(pattern, text):
                excluded.append((match.start(), match.end()))

        # URLs
        url_pattern = r'https?://\S+|www\.\S+|\S+\.(com|org|net|co\.uk|io|ai|bet|casino)\S*'
        for match in re.finditer(url_pattern, text, re.IGNORECASE):
            excluded.append((match.start(), match.end()))

        # Email addresses
        email_pattern = r'\b[\w.+-]+@[\w.-]+\.\w+\b'
        for match in re.finditer(email_pattern, text, re.IGNORECASE):
            excluded.append((match.start(), match.end()))

        return excluded

    def _in_excluded_span(
        self,
        start: int,
        end: int,
        excluded: list[tuple[int, int]],
    ) -> bool:
        """Check if word is inside an excluded span."""
        for ex_start, ex_end in excluded:
            if start >= ex_start and end <= ex_end:
                return True
        return False

    def _preserve_case(self, original: str, replacement: str) -> str:
        """Preserve the case pattern of the original word."""
        if not original or not replacement:
            return replacement

        if original.isupper():
            return replacement.upper()
        if original.istitle():
            return replacement.title()
        if original[0].isupper():
            return replacement[0].upper() + replacement[1:]
        return replacement.lower()
