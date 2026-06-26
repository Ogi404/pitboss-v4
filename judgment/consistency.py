"""
Pitboss v4 - Consistency Check (Judgment Layer)

Detects internal numerical contradictions where the same claim appears
with different values in different parts of the article.

Examples of REAL conflicts:
- "$4000 welcome bonus" in intro vs "$5000" in spec table
- "35x wagering" in one section vs "40x" in another

Examples of NOT conflicts (different claims):
- "100% welcome bonus" vs "50% reload bonus" (different bonus types)
- "$20 minimum deposit" vs "$50 minimum withdrawal" (different limits)

Design:
1. Pre-filter extracts claims with category + sub-type
2. Only same-category+same-subtype+different-value pairs go to LLM
3. LLM classifies CONFLICT/DIFFERENT/UNCLEAR
4. CONFLICT → propose, otherwise drop

LLM verdict IS the gate. No secondary confidence threshold.
"""

from __future__ import annotations
import re
import logging
from dataclasses import dataclass
from typing import Any, Optional
from itertools import combinations

from core.check_base import JudgmentCheck, register_check
from core.finding import Finding, FindingFactory, Category
from core.document import Document, Paragraph, Location
from judgment.llm_client import call_llm

logger = logging.getLogger(__name__)


# =============================================================================
# CLAIM EXTRACTION AND CLASSIFICATION
# =============================================================================

@dataclass
class ExtractedClaim:
    """A numerical claim extracted from the document."""
    category: str        # e.g., "BONUS_AMOUNT", "WAGERING"
    subtype: str         # e.g., "welcome", "reload", "generic"
    value: str           # The actual value (e.g., "$4000", "35x")
    normalized_value: float  # Numeric value for comparison
    context: str         # Surrounding text for LLM
    element_index: int   # Which paragraph/element
    offset: int          # Character offset in document


# Sub-type classification keywords
SUBTYPE_KEYWORDS = {
    "welcome": ["welcome", "first deposit", "sign-up", "sign up", "new player", "opening", "joining"],
    "reload": ["reload", "second", "third", "subsequent", "next deposit", "2nd", "3rd"],
    "no_deposit": ["no deposit", "free", "no-deposit", "registration", "sign up bonus"],
    "cashback": ["cashback", "cash back", "rebate"],
    "slots": ["slot", "pokie", "spin", "pokies"],
    "table_games": ["table", "blackjack", "roulette", "baccarat", "table games"],
    "live": ["live dealer", "live casino"],
    "deposit_min": ["minimum deposit", "min deposit", "deposit from", "deposit at least", "deposit minimum"],
    "deposit_max": ["maximum deposit", "max deposit", "deposit up to", "deposit limit"],
    "withdrawal_min": ["minimum withdrawal", "min withdrawal", "withdraw at least", "withdrawal minimum"],
    "withdrawal_max": ["maximum withdrawal", "max withdrawal", "withdraw up to", "withdrawal limit"],
    "total": ["total", "overall", "combined", "all games"],
}


def _classify_subtype(context: str) -> str:
    """Classify claim sub-type from context keywords."""
    context_lower = context.lower()
    for subtype, keywords in SUBTYPE_KEYWORDS.items():
        if any(kw in context_lower for kw in keywords):
            return subtype
    return "generic"


def _normalize_value(value_str: str) -> float:
    """Normalize a value string to a float for comparison."""
    # Remove currency symbols, commas, whitespace
    cleaned = re.sub(r'[$,\s]', '', value_str)
    # Remove trailing markers like +, x
    cleaned = re.sub(r'[x%+]$', '', cleaned, flags=re.IGNORECASE)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _extract_claims(document: Document) -> list[ExtractedClaim]:
    """Extract all numerical claims from the document with context."""
    claims: list[ExtractedClaim] = []

    # Patterns for different claim categories
    # Use word boundaries and non-greedy pre-context to avoid partial matches
    patterns = {
        "BONUS_AMOUNT": r'(?P<pre>.{0,40}?)(?P<value>\$[\d,]+(?:\.\d{2})?)(?P<post>.{0,40})',
        "BONUS_PERCENT": r'(?P<pre>.{0,40}?)(?P<value>\d{1,3}%)(?P<post>.{0,40})',
        "WAGERING": r'(?P<pre>.{0,40}?)(?P<value>\d{1,3}x)\b(?P<post>.{0,40})',
        "GAME_COUNT": r'(?P<pre>.{0,40}?)(?P<value>[\d,]+\+?)(?P<post>\s*(?:games?|slots?|pokies?|titles?|providers?).{0,20})',
    }

    for idx, element in enumerate(document.elements):
        if not isinstance(element, Paragraph):
            continue

        text = element.text
        if not text:
            continue

        for category, pattern in patterns.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group('value')
                pre = match.group('pre')
                post = match.group('post')
                context = f"{pre}{value}{post}"

                # Skip tiny values that aren't meaningful claims
                normalized = _normalize_value(value)
                if category == "GAME_COUNT" and normalized < 10:
                    continue
                if category == "BONUS_AMOUNT" and normalized < 5:
                    continue

                subtype = _classify_subtype(context)

                claims.append(ExtractedClaim(
                    category=category,
                    subtype=subtype,
                    value=value,
                    normalized_value=normalized,
                    context=context.strip(),
                    element_index=idx,
                    offset=element.start_offset + match.start(),
                ))

    return claims


def _find_conflict_pairs(claims: list[ExtractedClaim]) -> list[tuple[ExtractedClaim, ExtractedClaim]]:
    """
    Find pairs of claims that might conflict.

    Only pairs claims that:
    - Same category AND same sub-type
    - Different values
    """
    pairs: list[tuple[ExtractedClaim, ExtractedClaim]] = []

    # Group claims by (category, subtype)
    groups: dict[tuple[str, str], list[ExtractedClaim]] = {}
    for claim in claims:
        key = (claim.category, claim.subtype)
        if key not in groups:
            groups[key] = []
        groups[key].append(claim)

    # Find pairs within each group with different values
    for key, group_claims in groups.items():
        if len(group_claims) < 2:
            continue

        for claim_a, claim_b in combinations(group_claims, 2):
            # Different values → potential conflict
            if claim_a.normalized_value != claim_b.normalized_value:
                # Order by position for consistent output
                if claim_a.offset < claim_b.offset:
                    pairs.append((claim_a, claim_b))
                else:
                    pairs.append((claim_b, claim_a))

    return pairs


# =============================================================================
# LLM INTEGRATION
# =============================================================================

@dataclass
class LLMVerdict:
    """Result of LLM judgment on a claim pair."""
    verdict: str  # "CONFLICT", "DIFFERENT", or "UNCLEAR"
    reasoning: str
    pair_index: int


def _build_prompt(pairs: list[tuple[ExtractedClaim, ExtractedClaim]]) -> str:
    """Build the LLM prompt for conflict classification."""
    pair_descriptions = []

    for i, (claim_a, claim_b) in enumerate(pairs, 1):
        pair_descriptions.append(f"""
Pair {i}: {claim_a.category}.{claim_a.subtype}
  Location A (element {claim_a.element_index}): "{claim_a.context}"
  Value A: {claim_a.value}

  Location B (element {claim_b.element_index}): "{claim_b.context}"
  Value B: {claim_b.value}
""")

    return f"""You are checking a casino review article for internal factual consistency.

For each numbered pair below, determine if they describe THE SAME CLAIM with inconsistent values (an error the writer should fix), or if they are TWO DIFFERENT CLAIMS that legitimately have different values.

{chr(10).join(pair_descriptions)}

For EACH pair, respond with EXACTLY one of these formats:
PAIR 1: CONFLICT - [one sentence explaining why these are the same claim with inconsistent values]
PAIR 1: DIFFERENT - [one sentence explaining why these are separate claims]
PAIR 1: UNCLEAR - [one sentence explaining why this is ambiguous]

Important:
- CONFLICT means the article contradicts itself about a single fact
- DIFFERENT means these are legitimately two separate facts (e.g., welcome bonus vs reload bonus)
- UNCLEAR means there's not enough context to determine

Respond with one line per pair, in order."""


def _parse_llm_response(response_text: str, num_pairs: int) -> list[LLMVerdict]:
    """
    Parse LLM response robustly.

    Fail-safe: if we can't parse a clear CONFLICT, drop the pair.
    """
    verdicts: list[LLMVerdict] = []

    for i in range(1, num_pairs + 1):
        # Look for this pair's verdict
        pattern = rf'PAIR\s*{i}\s*:\s*(CONFLICT|DIFFERENT|UNCLEAR)\s*[-–—]?\s*(.+?)(?=PAIR\s*\d|$)'
        match = re.search(pattern, response_text, re.IGNORECASE | re.DOTALL)

        if match:
            verdict = match.group(1).upper()
            reasoning = match.group(2).strip()
            # Clean up reasoning
            reasoning = re.sub(r'\s+', ' ', reasoning)
            verdicts.append(LLMVerdict(
                verdict=verdict,
                reasoning=reasoning,
                pair_index=i - 1,
            ))
        else:
            # Couldn't parse - default to DROP (UNCLEAR)
            logger.warning(f"Could not parse verdict for pair {i}, defaulting to UNCLEAR")
            verdicts.append(LLMVerdict(
                verdict="UNCLEAR",
                reasoning="Could not parse LLM response for this pair",
                pair_index=i - 1,
            ))

    return verdicts


# _call_llm is now imported from judgment.llm_client


# =============================================================================
# CHECK IMPLEMENTATION
# =============================================================================

@register_check
class ConsistencyCheck(JudgmentCheck):
    """
    Internal numerical consistency check.

    Detects contradictions where the same claim appears with different
    values in different parts of the article.
    """

    def __init__(self):
        self._cached_pairs: Optional[list[tuple[ExtractedClaim, ExtractedClaim]]] = None
        self._last_document_id: Optional[int] = None

    def _get_name(self) -> str:
        return "consistency"

    def _get_display_name(self) -> str:
        return "Internal Consistency"

    def _get_category(self) -> Category:
        return "consistency"

    def _get_description(self) -> str:
        return "Detects internal numerical contradictions within the article"

    def _get_enabled_by_default(self) -> bool:
        # Enabled by default, but won't run without API key
        return True

    def _has_trigger(self, document: Document, standards: Any) -> bool:
        """
        Check if pre-filter found any potential conflict pairs.

        This is the cost-control gate: no pairs = no LLM call.
        """
        # Cache the pairs for reuse in _generate_proposals
        doc_id = id(document)
        if self._last_document_id != doc_id:
            claims = _extract_claims(document)
            self._cached_pairs = _find_conflict_pairs(claims)
            self._last_document_id = doc_id

            if self._cached_pairs:
                logger.info(f"Consistency check: {len(self._cached_pairs)} potential conflict pair(s) found")
            else:
                logger.debug("Consistency check: no potential conflicts, skipping LLM call")

        return bool(self._cached_pairs)

    def _generate_proposals(
        self,
        document: Document,
        standards: Any,
        voice_model: Any,
    ) -> list[Finding]:
        """Generate proposals for confirmed conflicts."""

        if not self._cached_pairs:
            return []

        pairs = self._cached_pairs

        # Build and send prompt to LLM
        prompt = _build_prompt(pairs)
        response = call_llm(prompt)

        if response is None:
            # LLM failed - graceful degradation, drop all pairs
            logger.warning("LLM call failed, dropping all potential conflicts")
            return []

        # Parse verdicts
        verdicts = _parse_llm_response(response, len(pairs))

        # Generate findings only for CONFLICT verdicts
        findings: list[Finding] = []

        for verdict in verdicts:
            if verdict.verdict != "CONFLICT":
                continue

            claim_a, claim_b = pairs[verdict.pair_index]

            # Create location using first claim's position
            location = Location(
                paragraph_index=claim_a.element_index,
                element_type="paragraph",
                start_offset=claim_a.offset,
                end_offset=claim_a.offset + len(claim_a.value),
            )

            # Format the proposal text showing both locations
            original_text = f"{claim_a.value} (element {claim_a.element_index}) vs {claim_b.value} (element {claim_b.element_index})"

            reasoning = (
                f"Internal conflict detected: {claim_a.category}.{claim_a.subtype}\n"
                f"Location 1 (element {claim_a.element_index}): \"{claim_a.context}\" → {claim_a.value}\n"
                f"Location 2 (element {claim_b.element_index}): \"{claim_b.context}\" → {claim_b.value}\n"
                f"LLM analysis: {verdict.reasoning}"
            )

            finding = FindingFactory.create(
                check_name="consistency",
                category="consistency",
                severity="warning",
                confidence=0.85,  # Judgment check, not 1.0
                location=location,
                original_text=original_text,
                reasoning=reasoning,
                auto_applicable=False,  # Proposals only, never auto-apply
                proposed_text=None,  # No automatic fix - editor decides which value is correct
                metadata={
                    "sub_check": "numerical_conflict",
                    "category": claim_a.category,
                    "subtype": claim_a.subtype,
                    "value_a": claim_a.value,
                    "value_b": claim_b.value,
                    "element_a": claim_a.element_index,
                    "element_b": claim_b.element_index,
                    "llm_verdict": verdict.verdict,
                    "llm_reasoning": verdict.reasoning,
                },
            )
            findings.append(finding)

        return findings
