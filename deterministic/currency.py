"""
Pitboss v4 - Currency Consistency Check

Deterministic check for currency formatting per General Writing Requirements Section 11:
1. Use currency symbol OR abbreviation, never both (e.g., "$500 USD" is wrong)
2. Be consistent within an article (don't mix "$500" and "500 EUR")

This check processes both body paragraphs AND tables, since currency appears
heavily in payment/bonus specification tables.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any, Optional

from core.check_base import DeterministicCheck, register_check
from core.document import Document, Paragraph, Table
from core.finding import Finding, FindingFactory, Category


# =============================================================================
# CURRENCY PATTERNS
# =============================================================================

# Currency symbols (single and compound)
CURRENCY_SYMBOLS = (
    r'€'      # Euro
    r'|£'     # British Pound
    r'|¥'     # Yen/Yuan
    r'|₹'     # Indian Rupee
    r'|₿'     # Bitcoin
    r'|C\$'   # Canadian Dollar
    r'|A\$'   # Australian Dollar
    r'|NZ\$'  # New Zealand Dollar
    r'|R\$'   # Brazilian Real
    r'|\$'    # Generic Dollar (USD or other) - must be last to avoid matching C$, A$, etc.
)

# ISO currency codes (fiat and crypto)
CURRENCY_CODES = (
    r'EUR|GBP|USD|CAD|AUD|NZD|INR|ZAR|JPY|CNY|BRL|CHF|SEK|NOK|DKK|PLN|CZK|HUF|RON|BGN|HRK|RUB|TRY|MXN|SGD|HKD|KRW|TWD|THB|MYR|PHP|IDR|VND|PKR|BDT|LKR|NGN|KES|GHS|EGP|MAD|AED|SAR|QAR|KWD|BHD|OMR'
    r'|BTC|ETH|USDT|USDC|LTC|DOGE|XRP|ADA|SOL|DOT|MATIC|AVAX|LINK|UNI|ATOM'
)

# Amount patterns with various separators
# Matches: 500, 1000, 1,000, 1.000, 1 000, 500.00, 500,50
AMOUNT_PATTERN = r'\d{1,3}(?:[,.\s]\d{3})*(?:[.,]\d{1,2})?'

# Compiled patterns
# Symbol + Amount: €500, $1,000, C$50.99
SYMBOL_AMOUNT_RE = re.compile(
    rf'(?<![A-Za-z])({CURRENCY_SYMBOLS})\s*({AMOUNT_PATTERN})(?![%\d])',
    re.IGNORECASE
)

# Amount + Code: 500 EUR, 1,000 USD
AMOUNT_CODE_RE = re.compile(
    rf'(?<![€£¥₹₿$\d])({AMOUNT_PATTERN})\s+({CURRENCY_CODES})(?![A-Za-z])',
    re.IGNORECASE
)

# Combined violation: €500 EUR, $500 USD, C$500 CAD
COMBINED_RE = re.compile(
    rf'(?<![A-Za-z])({CURRENCY_SYMBOLS})\s*({AMOUNT_PATTERN})\s+({CURRENCY_CODES})(?![A-Za-z])',
    re.IGNORECASE
)


# =============================================================================
# SYMBOL/CODE MAPPINGS
# =============================================================================

# Map symbols to their most common ISO code
SYMBOL_TO_CODE = {
    '€': 'EUR',
    '£': 'GBP',
    '¥': 'JPY',  # Could be CNY, but JPY more common in iGaming
    '₹': 'INR',
    '₿': 'BTC',
    '$': 'USD',   # Bare $ defaults to USD
    'C$': 'CAD',
    'A$': 'AUD',
    'NZ$': 'NZD',
    'R$': 'BRL',
}

# Map codes to their symbols (reverse mapping)
CODE_TO_SYMBOL = {
    'EUR': '€',
    'GBP': '£',
    'JPY': '¥',
    'CNY': '¥',
    'INR': '₹',
    'BTC': '₿',
    'USD': '$',
    'CAD': 'C$',
    'AUD': 'A$',
    'NZD': 'NZ$',
    'BRL': 'R$',
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CurrencyOccurrence:
    """A single currency occurrence in the document."""
    text: str               # Full matched text
    amount: str             # Numeric part
    symbol: Optional[str]   # Symbol if present
    code: Optional[str]     # Code if present
    style: str              # "symbol", "code", or "combined"
    start_offset: int       # Absolute position
    end_offset: int
    element_type: str       # "paragraph" or "table"


# =============================================================================
# CHECK IMPLEMENTATION
# =============================================================================

@register_check
class CurrencyConsistencyCheck(DeterministicCheck):
    """
    Checks currency formatting consistency.

    Detects:
    1. Combined symbol+code violations (e.g., "$500 USD")
    2. Inconsistent style within an article (mixing "$500" and "500 USD")

    Processes both paragraphs and table cells.
    """

    def _get_name(self) -> str:
        return "currency"

    def _get_display_name(self) -> str:
        return "Currency Consistency Check"

    def _get_category(self) -> Category:
        return "currency"

    def _get_description(self) -> str:
        return (
            "Ensures consistent currency formatting: use symbol OR abbreviation, "
            "never both, and maintain consistency throughout the article."
        )

    def _get_required_standards(self) -> tuple[str, ...]:
        return ("currency.mode",)

    def _find_issues(
        self,
        document: Document,
        standards: Any,
    ) -> list[Finding]:
        """Find currency formatting issues."""
        findings: list[Finding] = []

        # Check if currency mode requires exclusive formatting
        mode = getattr(standards.currency, 'mode', 'exclusive')
        if mode != 'exclusive':
            return findings  # Only check in exclusive mode

        # Collect all currency occurrences
        occurrences = self._collect_occurrences(document)

        if not occurrences:
            return findings

        # Step 1: Flag combined violations (always wrong)
        combined = [o for o in occurrences if o.style == 'combined']
        non_combined = [o for o in occurrences if o.style != 'combined']

        # Step 2: Determine dominant style from non-combined occurrences
        symbol_count = sum(1 for o in non_combined if o.style == 'symbol')
        code_count = sum(1 for o in non_combined if o.style == 'code')

        dominant_style, base_auto_applicable = self._determine_dominant_style(
            symbol_count, code_count
        )

        # Step 3: Create findings for combined violations
        # Combined violations are ALWAYS auto-applicable (genuine §11 violations)
        # regardless of dominant style ratio or convention count
        for occ in combined:
            findings.append(self._create_combined_finding(
                occ, dominant_style, document
            ))

        # Step 4: For lone-minority conversions, apply stricter gating
        if dominant_style and non_combined:
            # Count distinct conventions
            distinct_conventions = self._get_distinct_conventions(non_combined)
            num_conventions = len(distinct_conventions)

            # Check prose vs table context
            prose_conventions, table_conventions = self._get_prose_and_table_conventions(non_combined)
            prose_table_differ = (
                prose_conventions and table_conventions and
                prose_conventions != table_conventions
            )

            # Determine auto_applicable for lone-minority conversions
            # Stricter than combined violations
            if num_conventions >= 3:
                # Multiple conventions = no clear house style
                consistency_auto = False
                multi_conv_reason = (
                    f"This article uses {num_conventions} different currency conventions. "
                    f"Human review needed to decide which style to standardize on."
                )
            elif prose_table_differ:
                # Prose and tables use different styles
                consistency_auto = False
                multi_conv_reason = (
                    "Prose and tables use different currency conventions. "
                    "This may be intentional formatting."
                )
            elif not base_auto_applicable:
                # Dominant style wasn't clear enough
                consistency_auto = False
                multi_conv_reason = None
            else:
                consistency_auto = True
                multi_conv_reason = None

            # Create findings for inconsistent style
            for occ in non_combined:
                if occ.style != dominant_style:
                    finding = self._create_consistency_finding(
                        occ, dominant_style, consistency_auto, document,
                        multi_convention_reason=multi_conv_reason,
                    )
                    if finding:  # Skip if no valid conversion possible
                        findings.append(finding)

        return findings

    # =========================================================================
    # OCCURRENCE COLLECTION
    # =========================================================================

    def _collect_occurrences(self, document: Document) -> list[CurrencyOccurrence]:
        """Collect all currency occurrences from paragraphs and tables."""
        occurrences: list[CurrencyOccurrence] = []

        # Process paragraphs
        for para in document.paragraphs():
            para_occs = self._find_occurrences_in_text(
                para.text, para.start_offset, "paragraph"
            )
            occurrences.extend(para_occs)

        # Process tables
        for table in document.tables():
            for row in table.rows:
                for cell in row.cells:
                    cell_occs = self._find_occurrences_in_text(
                        cell.text, cell.start_offset, "table"
                    )
                    occurrences.extend(cell_occs)

        return occurrences

    def _find_occurrences_in_text(
        self,
        text: str,
        base_offset: int,
        element_type: str,
    ) -> list[CurrencyOccurrence]:
        """Find currency occurrences in a text span."""
        occurrences: list[CurrencyOccurrence] = []
        seen_spans: set[tuple[int, int]] = set()

        # First, find combined violations (symbol + amount + code)
        for match in COMBINED_RE.finditer(text):
            symbol = match.group(1)
            amount = match.group(2)
            code = match.group(3).upper()

            start = base_offset + match.start()
            end = base_offset + match.end()
            span = (start, end)

            if span not in seen_spans:
                seen_spans.add(span)
                occurrences.append(CurrencyOccurrence(
                    text=match.group(0),
                    amount=amount,
                    symbol=symbol,
                    code=code,
                    style='combined',
                    start_offset=start,
                    end_offset=end,
                    element_type=element_type,
                ))

        # Then, find symbol + amount patterns (not already captured)
        for match in SYMBOL_AMOUNT_RE.finditer(text):
            start = base_offset + match.start()
            end = base_offset + match.end()
            span = (start, end)

            # Check if this span overlaps with already seen spans
            if self._overlaps_any(span, seen_spans):
                continue

            symbol = match.group(1)
            amount = match.group(2)

            seen_spans.add(span)
            occurrences.append(CurrencyOccurrence(
                text=match.group(0),
                amount=amount,
                symbol=symbol,
                code=None,
                style='symbol',
                start_offset=start,
                end_offset=end,
                element_type=element_type,
            ))

        # Finally, find amount + code patterns (not already captured)
        for match in AMOUNT_CODE_RE.finditer(text):
            start = base_offset + match.start()
            end = base_offset + match.end()
            span = (start, end)

            if self._overlaps_any(span, seen_spans):
                continue

            amount = match.group(1)
            code = match.group(2).upper()

            seen_spans.add(span)
            occurrences.append(CurrencyOccurrence(
                text=match.group(0),
                amount=amount,
                symbol=None,
                code=code,
                style='code',
                start_offset=start,
                end_offset=end,
                element_type=element_type,
            ))

        return occurrences

    def _overlaps_any(
        self,
        span: tuple[int, int],
        seen: set[tuple[int, int]],
    ) -> bool:
        """Check if span overlaps with any seen span."""
        start, end = span
        for seen_start, seen_end in seen:
            if not (end <= seen_start or start >= seen_end):
                return True
        return False

    # =========================================================================
    # CONVENTION TRACKING
    # =========================================================================

    def _get_convention(self, occ: CurrencyOccurrence) -> str:
        """
        Get the distinct convention identifier for an occurrence.

        Distinguishes between different symbols (A$, $, €) and codes (AUD, USD, USDT).
        """
        if occ.style == 'combined':
            return f"combined:{occ.symbol}+{occ.code}"
        if occ.style == 'symbol':
            return f"symbol:{occ.symbol}"  # "symbol:A$", "symbol:$", "symbol:€"
        if occ.style == 'code':
            return f"code:{occ.code}"  # "code:AUD", "code:USDT"
        return "unknown"

    def _get_distinct_conventions(
        self,
        occurrences: list[CurrencyOccurrence],
    ) -> set[str]:
        """Count unique currency conventions (excluding combined violations)."""
        conventions = set()
        for occ in occurrences:
            if occ.style != 'combined':
                conventions.add(self._get_convention(occ))
        return conventions

    def _get_prose_and_table_conventions(
        self,
        occurrences: list[CurrencyOccurrence],
    ) -> tuple[set[str], set[str]]:
        """Get conventions used in prose vs tables separately."""
        prose = set()
        table = set()
        for occ in occurrences:
            if occ.style != 'combined':
                conv = self._get_convention(occ)
                if occ.element_type == 'paragraph':
                    prose.add(conv)
                elif occ.element_type == 'table':
                    table.add(conv)
        return prose, table

    # =========================================================================
    # DOMINANT STYLE DETECTION
    # =========================================================================

    def _determine_dominant_style(
        self,
        symbol_count: int,
        code_count: int,
    ) -> tuple[Optional[str], bool]:
        """
        Determine the dominant currency style (symbol vs code).

        Returns (dominant_style, auto_applicable).
        Note: auto_applicable may be overridden by convention count checks.
        """
        total = symbol_count + code_count

        if total == 0:
            return (None, False)

        # 100% one style → that style is dominant
        if code_count == 0 and symbol_count > 0:
            return ('symbol', True)
        if symbol_count == 0 and code_count > 0:
            return ('code', True)

        # Calculate ratios
        symbol_ratio = symbol_count / total
        code_ratio = code_count / total

        # Clear majority (>70%) for auto-applicable
        if symbol_ratio > 0.7:
            return ('symbol', True)
        if code_ratio > 0.7:
            return ('code', True)

        # Simple majority but close → proposal only
        if symbol_count > code_count:
            return ('symbol', False)
        if code_count > symbol_count:
            return ('code', False)

        # Exact tie → pick symbol as dominant (arbitrary), proposal only
        return ('symbol', False)

    # =========================================================================
    # FINDING CREATION
    # =========================================================================

    def _create_combined_finding(
        self,
        occ: CurrencyOccurrence,
        dominant_style: Optional[str],
        document: Document,
    ) -> Finding:
        """Create finding for combined symbol+code violation.

        Combined violations are ALWAYS auto-applicable since they violate §11
        (using both symbol AND code together), regardless of convention count.
        """
        location = document.location_for_span(occ.start_offset, occ.end_offset)

        # Propose fix based on dominant style
        if dominant_style == 'symbol':
            proposed = f"{occ.symbol}{occ.amount}"
            auto_applicable = True
        elif dominant_style == 'code':
            proposed = f"{occ.amount} {occ.code}"
            auto_applicable = True
        else:
            # No dominant style - prefer symbol (shorter), but proposal only
            proposed = f"{occ.symbol}{occ.amount}"
            auto_applicable = False

        return FindingFactory.create(
            check_name=self.name,
            category=self.category,
            severity="warning",
            confidence=0.95,
            location=location,
            original_text=occ.text,
            proposed_text=proposed,
            reasoning=(
                f"Currency uses both symbol and abbreviation ('{occ.text}'). "
                f"Use one format only: either '{occ.symbol}{occ.amount}' or "
                f"'{occ.amount} {occ.code}'."
            ),
            auto_applicable=auto_applicable,
            metadata={
                "sub_check": "combined_violation",
                "symbol": occ.symbol,
                "code": occ.code,
                "amount": occ.amount,
                "element_type": occ.element_type,
            },
        )

    def _create_consistency_finding(
        self,
        occ: CurrencyOccurrence,
        dominant_style: str,
        auto_applicable: bool,
        document: Document,
        multi_convention_reason: Optional[str] = None,
    ) -> Optional[Finding]:
        """Create finding for inconsistent style. Returns None if no fix possible."""
        # Generate proposed text based on dominant style
        if dominant_style == 'symbol' and occ.style == 'code':
            # Convert code-style to symbol-style
            symbol = CODE_TO_SYMBOL.get(occ.code)
            if symbol:
                proposed = f"{symbol}{occ.amount}"
            else:
                # No symbol mapping available (e.g., USDT) - skip this finding
                return None
        elif dominant_style == 'code' and occ.style == 'symbol':
            # Convert symbol-style to code-style
            code = SYMBOL_TO_CODE.get(occ.symbol)
            if code:
                proposed = f"{occ.amount} {code}"
            else:
                # No code mapping available - skip this finding
                return None
        else:
            return None

        location = document.location_for_span(occ.start_offset, occ.end_offset)
        style_name = "symbol" if dominant_style == "symbol" else "abbreviation"

        # Build reasoning
        if multi_convention_reason:
            reasoning = multi_convention_reason
        else:
            reasoning = (
                f"This article predominantly uses {style_name} style for currency. "
                f"Convert '{occ.text}' to '{proposed}' for consistency."
            )

        return FindingFactory.create(
            check_name=self.name,
            category=self.category,
            severity="suggestion",
            confidence=0.85 if auto_applicable else 0.5,
            location=location,
            original_text=occ.text,
            proposed_text=proposed,
            reasoning=reasoning,
            auto_applicable=auto_applicable,
            metadata={
                "sub_check": "style_inconsistency",
                "original_style": occ.style,
                "dominant_style": dominant_style,
                "element_type": occ.element_type,
            },
        )
