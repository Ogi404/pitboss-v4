"""
Pitboss v4 - Grammar & Spelling Check

Deterministic check using LanguageTool (local/offline mode).
No data leaves the machine - runs embedded LanguageTool server.

Category filter (mechanical errors only):
- INCLUDE: TYPOS, GRAMMAR, PUNCTUATION, CASING, COMPOUNDING, CONFUSED_WORDS
- EXCLUDE: STYLE, REDUNDANCY, COLLOQUIALISMS, GENDER_NEUTRALITY, MISC

Auto-applicable: single-replacement TYPOS/CASING/PUNCTUATION only.
Grammar/ambiguous fixes are proposals requiring human review.
"""

from __future__ import annotations
import logging
import re
from typing import Any, Optional

from core.check_base import DeterministicCheck, register_check
from core.document import Document
from core.finding import Finding, FindingFactory, Category
from deterministic.domain_dictionary import DomainDictionary

logger = logging.getLogger(__name__)


# =============================================================================
# LOCALE MAPPING
# =============================================================================

# Map Pitboss spelling_region to LanguageTool locale codes
LOCALE_MAP = {
    'british': 'en-GB',
    'american': 'en-US',
    'canadian': 'en-CA',
    'australian': 'en-AU',
    'new_zealand': 'en-NZ',
}


# =============================================================================
# CATEGORY FILTERS
# =============================================================================

# Categories to INCLUDE (mechanical errors)
INCLUDE_CATEGORIES = {
    'TYPOS',           # Misspellings: lisensed -> licensed
    'GRAMMAR',         # Agreement, tense: he don't -> he doesn't
    'PUNCTUATION',     # Missing/wrong punctuation: want.The -> want. The
    'CASING',          # Capitalization errors
    'COMPOUNDING',     # Compound word errors: every day vs everyday
    'CONFUSED_WORDS',  # their/there/they're
}

# Rule IDs to explicitly EXCLUDE (noisy or editorial)
EXCLUDE_RULE_IDS = {
    'EN_QUOTES',                    # Quote style is editorial choice
    'DASH_RULE',                    # Hyphen vs en-dash is editorial
    'OXFORD_SPELLING_Z_NOT_S',      # Handled by locale_spelling
    # Note: MORFOLOGIK rules kept - they catch real typos like "lisensed"
    # Brand names filtered separately via standards.brand_name
}

# Categories to explicitly EXCLUDE (style opinions)
EXCLUDE_CATEGORIES = {
    'STYLE',
    'REDUNDANCY',
    'COLLOQUIALISMS',
    'GENDER_NEUTRALITY',
    'MISC',
    'SEMANTICS',       # Often false positives
}

# Rule IDs to explicitly INCLUDE even if category excluded
# (mechanical errors that happen to be categorized as TYPOGRAPHY)
INCLUDE_RULE_IDS = {
    'SENTENCE_WHITESPACE',   # Missing space after period: "want.The"
    'CONSECUTIVE_SPACES',    # Double spaces
    'DOUBLE_PUNCTUATION',    # Repeated punctuation
}


# =============================================================================
# DOUBLE SPACE DETECTION (separate from LanguageTool)
# =============================================================================

# Match double spaces in prose (not before code-like content)
DOUBLE_SPACE_PATTERN = re.compile(r'(?<=[a-zA-Z.,!?])  +(?=[a-zA-Z@])')


# =============================================================================
# GRAMMAR CHECK
# =============================================================================

@register_check
class GrammarCheck(DeterministicCheck):
    """
    Grammar and spelling check via LanguageTool (offline).

    Uses local LanguageTool server - no data leaves the machine.
    Filters to mechanical errors only (typos, grammar, punctuation).
    Style opinions are suppressed.
    """

    _tool_cache: dict[str, Any] = {}  # Cache LanguageTool instances per locale

    def _get_name(self) -> str:
        return "grammar"

    def _get_display_name(self) -> str:
        return "Grammar & Spelling"

    def _get_category(self) -> Category:
        return "grammar"

    def _get_description(self) -> str:
        return (
            "Checks for grammar errors, spelling mistakes, and punctuation issues "
            "using LanguageTool (offline). Locale-aware - uses the same English "
            "variant as locale_spelling (en-AU, en-GB, en-US, etc.)."
        )

    def _get_required_standards(self) -> tuple[str, ...]:
        return ("spelling_region",)

    def _get_tool(self, locale: str) -> Any:
        """Get or create LanguageTool instance for locale."""
        if locale not in self._tool_cache:
            try:
                import language_tool_python
                logger.info(f"Initializing LanguageTool for {locale}...")
                self._tool_cache[locale] = language_tool_python.LanguageTool(locale)
                logger.info(f"LanguageTool {locale} ready")
            except ImportError:
                raise RuntimeError(
                    "language-tool-python not installed. "
                    "Run: pip install language-tool-python"
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to start LanguageTool: {e}. "
                    "Ensure Java 8+ is installed and in PATH."
                )
        return self._tool_cache[locale]

    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """Find grammar, spelling, and punctuation issues."""
        findings: list[Finding] = []

        # Get locale from standards
        region = getattr(standards, 'spelling_region', 'british')
        lt_locale = LOCALE_MAP.get(region, 'en-GB')

        # Get brand name to filter false positives
        brand_name = getattr(standards, 'brand_name', '') or ''

        # Get full document text (full_text may be method or property)
        full_text = document.full_text() if callable(document.full_text) else document.full_text
        if not full_text or not full_text.strip():
            return []

        # Get LanguageTool instance
        try:
            tool = self._get_tool(lt_locale)
        except RuntimeError as e:
            logger.error(str(e))
            return []

        # Run LanguageTool check
        try:
            matches = tool.check(full_text)
        except Exception as e:
            logger.error(f"LanguageTool check failed: {e}")
            return []

        # Filter and convert matches to findings
        for match in matches:
            finding = self._match_to_finding(match, document, full_text, brand_name)
            if finding:
                findings.append(finding)

        # Note: Double spaces handled by LanguageTool's CONSECUTIVE_SPACES rule
        # (included via INCLUDE_RULE_IDS)

        return findings

    def _match_to_finding(
        self,
        match: Any,
        document: Document,
        full_text: str,
        brand_name: str = "",
    ) -> Optional[Finding]:
        """Convert a LanguageTool match to a Finding, with filtering."""

        # Get match details (language-tool-python uses snake_case)
        rule_id = getattr(match, 'rule_id', '') or getattr(match, 'ruleId', '')
        category = getattr(match, 'category', '')

        # Always exclude these rule IDs
        if rule_id in EXCLUDE_RULE_IDS:
            return None

        # Check if rule is explicitly included (overrides category exclusion)
        explicitly_included = rule_id in INCLUDE_RULE_IDS

        # Filter by excluded categories (unless explicitly included)
        if not explicitly_included and category in EXCLUDE_CATEGORIES:
            return None

        # Filter by included categories (unless explicitly included)
        if not explicitly_included and category and category not in INCLUDE_CATEGORIES:
            return None

        # Get match position (snake_case attributes)
        offset = getattr(match, 'offset', 0)
        length = getattr(match, 'error_length', 0) or getattr(match, 'errorLength', 0)
        if length == 0:
            return None

        start = offset
        end = offset + length

        # Get matched text
        original_text = full_text[start:end]
        # Skip if completely empty (but allow whitespace-only for CONSECUTIVE_SPACES)
        if not original_text:
            return None

        # MORFOLOGIK suppression: check domain dictionary for industry jargon
        # This is SPELLING-ONLY - other grammar rules still apply to these terms
        if rule_id.startswith('MORFOLOGIK_RULE_') or rule_id == 'HELL':
            domain_dict = DomainDictionary.get_instance()
            # EXACT-TOKEN MATCHING: "HellSpin" matches, "HellSpins" does NOT
            if domain_dict.is_domain_term(original_text):
                return None

        # Skip brand name false positives (backup check)
        if brand_name and original_text.lower() == brand_name.lower():
            return None

        # Get replacements
        replacements = getattr(match, 'replacements', [])
        proposed_text = replacements[0] if replacements else None

        # Determine if auto-applicable
        auto_applicable = self._is_auto_applicable(match, replacements)

        # Build reasoning
        message = getattr(match, 'message', 'Grammar/spelling issue')
        reasoning = f"{message}"
        if rule_id:
            reasoning += f" [{rule_id}]"

        # Create location
        try:
            location = document.location_for_span(start, end)
        except Exception:
            # Fallback location
            from core.finding import Location
            location = Location(
                section_index=None,
                section_title=None,
                paragraph_index=None,
                element_type="paragraph",
                start_offset=start,
                end_offset=end,
            )

        # Determine severity
        if category == 'TYPOS':
            severity = "error"
        elif category in ('GRAMMAR', 'PUNCTUATION'):
            severity = "warning"
        else:
            severity = "suggestion"

        return FindingFactory.create(
            check_name=self.name,
            category=self.category,
            severity=severity,
            confidence=0.9,  # LanguageTool is generally reliable
            location=location,
            original_text=original_text,
            proposed_text=proposed_text,
            reasoning=reasoning,
            auto_applicable=auto_applicable,
            metadata={
                "rule_id": rule_id,
                "lt_category": category,
                "replacements": replacements[:3] if replacements else [],
            },
        )

    def _is_auto_applicable(self, match: Any, replacements: list) -> bool:
        """
        Determine if a match should be auto-applicable.

        Auto-applicable: single unambiguous correction for TYPOS/CASING/PUNCTUATION.
        Advisory: grammar fixes, multiple options, confused words.
        """
        # Must have exactly one replacement
        if len(replacements) != 1:
            return False

        category = getattr(match, 'category', '')
        rule_id = getattr(match, 'rule_id', '') or getattr(match, 'ruleId', '')

        # TYPOS with single replacement = auto
        if category == 'TYPOS':
            return True

        # CASING with single replacement = auto
        if category == 'CASING':
            return True

        # PUNCTUATION with single replacement = auto
        if category == 'PUNCTUATION':
            return True

        # Explicitly included rules (like SENTENCE_WHITESPACE) = auto
        if rule_id in INCLUDE_RULE_IDS:
            return True

        # Everything else (GRAMMAR, CONFUSED_WORDS, etc.) = needs review
        return False

    def _check_double_spaces(
        self,
        document: Document,
        full_text: str,
    ) -> list[Finding]:
        """Check for double spaces in prose."""
        findings = []

        for match in DOUBLE_SPACE_PATTERN.finditer(full_text):
            start = match.start()
            end = match.end()
            original = match.group(0)

            try:
                location = document.location_for_span(start, end)
            except Exception:
                from core.finding import Location
                location = Location(
                    section_index=None,
                    section_title=None,
                    paragraph_index=None,
                    element_type="paragraph",
                    start_offset=start,
                    end_offset=end,
                )

            findings.append(FindingFactory.create(
                check_name=self.name,
                category=self.category,
                severity="warning",
                confidence=1.0,
                location=location,
                original_text=original,
                proposed_text=" ",  # Single space
                reasoning="Double space detected - replace with single space",
                auto_applicable=True,
                metadata={
                    "rule_id": "DOUBLE_SPACE",
                    "lt_category": "WHITESPACE",
                },
            ))

        return findings
