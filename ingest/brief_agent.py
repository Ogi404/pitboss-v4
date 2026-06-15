"""
Pitboss v4 - Brief Understanding Agent

First-class subsystem for parsing briefs into structured, confidence-scored data.
Core rule: NEVER SILENTLY GUESS. Low confidence triggers clarification.

Returns one of three states:
- READY: Brief parsed successfully, proceed to checks
- NEEDS_CLARIFICATION: Critical elements unclear, ask user
- NEEDS_TASK_SELECTION: Multi-task brief, user must pick
"""

from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Union, Optional, Any

from ingest.brief_model import (
    ArticleType,
    BriefState,
    BriefKeyword,
    BriefKeywords,
    BriefSection,
    BriefLink,
    Clarification,
    BriefModel,
    BriefResult,
)
from ingest.brief_base import (
    BriefParserRegistry,
    RawBriefExtraction,
    RawKeywordGroup,
    KEYWORD_CONFIDENCE_THRESHOLD,
    SECTION_CONFIDENCE_THRESHOLD,
    ARTICLE_TYPE_CONFIDENCE_THRESHOLD,
    WORD_COUNT_CONFIDENCE_THRESHOLD,
    map_task_to_article_type,
)

# Import to trigger parser registration
import ingest.brief_formats  # noqa: F401


class BriefAgent:
    """
    Orchestrator for brief parsing with confidence scoring.

    Usage:
        agent = BriefAgent()
        result = agent.parse("path/to/brief.xlsx")

        if result.state == BriefState.READY:
            brief = result.brief
            # proceed with checks
        elif result.state == BriefState.NEEDS_CLARIFICATION:
            # ask user to confirm/correct
            for clarification in result.clarifications:
                print(f"{clarification.question}")
        elif result.state == BriefState.NEEDS_TASK_SELECTION:
            # ask user to pick a task
            print(f"Pick a task: {result.task_options}")
    """

    def __init__(
        self,
        keyword_threshold: float = KEYWORD_CONFIDENCE_THRESHOLD,
        section_threshold: float = SECTION_CONFIDENCE_THRESHOLD,
        article_type_threshold: float = ARTICLE_TYPE_CONFIDENCE_THRESHOLD,
        word_count_threshold: float = WORD_COUNT_CONFIDENCE_THRESHOLD,
    ):
        """
        Initialize BriefAgent with confidence thresholds.

        Args:
            keyword_threshold: Minimum confidence for keywords (default 0.7)
            section_threshold: Minimum confidence for sections (default 0.6)
            article_type_threshold: Minimum confidence for article type (default 0.6)
            word_count_threshold: Minimum confidence for word count (default 0.5)
        """
        self.keyword_threshold = keyword_threshold
        self.section_threshold = section_threshold
        self.article_type_threshold = article_type_threshold
        self.word_count_threshold = word_count_threshold

    def parse(self, source: Union[Path, str]) -> BriefResult:
        """
        Parse a brief from file path or URL.

        Args:
            source: File path or Google Sheets URL

        Returns:
            BriefResult with one of three states:
            - READY: Brief parsed successfully
            - NEEDS_CLARIFICATION: Low confidence on critical element
            - NEEDS_TASK_SELECTION: Multi-task brief, user must pick
        """
        # Convert string to Path if needed
        if isinstance(source, str) and not source.startswith("http"):
            source = Path(source)

        # Step 1: Get parser from registry
        parser = BriefParserRegistry.detect_and_get(source)

        # Step 2: Extract raw data
        raw = parser.extract(source)

        # Step 3: Check for multi-task
        if raw.is_multi_task:
            return BriefResult(
                state=BriefState.NEEDS_TASK_SELECTION,
                brief=None,
                clarifications=(),
                task_options=tuple(raw.tasks),
            )

        # Step 4: Build BriefModel
        brief = self._build_brief_model(raw)

        # Step 5: Check for low-confidence critical elements
        clarifications = self._check_clarifications(brief)
        if clarifications:
            return BriefResult(
                state=BriefState.NEEDS_CLARIFICATION,
                brief=brief,  # Partial brief available for context
                clarifications=tuple(clarifications),
                task_options=(),
            )

        # Step 6: Return ready
        return BriefResult(
            state=BriefState.READY,
            brief=brief,
            clarifications=(),
            task_options=(),
        )

    def parse_with_task(self, source: Union[Path, str], task_name: str) -> BriefResult:
        """
        Parse multi-task brief with specific task selected.

        Args:
            source: File path or URL
            task_name: Selected task name

        Returns:
            BriefResult (may still need clarification)
        """
        if isinstance(source, str) and not source.startswith("http"):
            source = Path(source)

        parser = BriefParserRegistry.detect_and_get(source)
        raw = parser.extract(source)

        # Filter raw data to selected task
        raw.tasks = [task_name]
        if not raw.task_name:
            raw.task_name = task_name
            raw.task_name_confidence = 1.0

        # Build and check
        brief = self._build_brief_model(raw)
        clarifications = self._check_clarifications(brief)

        if clarifications:
            return BriefResult(
                state=BriefState.NEEDS_CLARIFICATION,
                brief=brief,
                clarifications=tuple(clarifications),
                task_options=(),
            )

        return BriefResult(
            state=BriefState.READY,
            brief=brief,
            clarifications=(),
            task_options=(),
        )

    def confirm_clarifications(
        self,
        brief: BriefModel,
        confirmations: dict[str, Any],
    ) -> BriefResult:
        """
        Confirm or correct low-confidence elements.

        Args:
            brief: The partially-parsed brief
            confirmations: Dict mapping field names to confirmed/corrected values
                e.g., {"keywords": [...], "article_type": "bonus_page"}

        Returns:
            Updated BriefResult
        """
        # Build updated brief with confirmations
        updates = {}

        if "keywords" in confirmations:
            kw_data = confirmations["keywords"]
            updates["keywords"] = self._build_keywords_from_confirmation(kw_data)
            updates["keywords_confidence"] = 1.0  # User confirmed

        if "sections" in confirmations:
            sec_data = confirmations["sections"]
            updates["sections"] = self._build_sections_from_confirmation(sec_data)
            updates["sections_confidence"] = 1.0

        if "article_type" in confirmations:
            type_val = confirmations["article_type"]
            if isinstance(type_val, str):
                updates["article_type"] = ArticleType(type_val)
            else:
                updates["article_type"] = type_val
            updates["article_type_confidence"] = 1.0

        if "target_word_count" in confirmations:
            updates["target_word_count"] = int(confirmations["target_word_count"])
            updates["word_count_confidence"] = 1.0

        if "locale" in confirmations:
            updates["locale"] = confirmations["locale"]
            updates["locale_confidence"] = 1.0

        if "market" in confirmations:
            updates["market"] = confirmations["market"]
            updates["locale_confidence"] = 1.0

        # Create updated brief (BriefModel is frozen, so we rebuild)
        updated_brief = BriefModel(
            keywords=updates.get("keywords", brief.keywords),
            keywords_confidence=updates.get("keywords_confidence", brief.keywords_confidence),
            sections=updates.get("sections", brief.sections),
            sections_confidence=updates.get("sections_confidence", brief.sections_confidence),
            target_word_count=updates.get("target_word_count", brief.target_word_count),
            word_count_confidence=updates.get("word_count_confidence", brief.word_count_confidence),
            task_name=brief.task_name,
            article_type=updates.get("article_type", brief.article_type),
            article_type_confidence=updates.get("article_type_confidence", brief.article_type_confidence),
            locale=updates.get("locale", brief.locale),
            market=updates.get("market", brief.market),
            locale_confidence=updates.get("locale_confidence", brief.locale_confidence),
            links=brief.links,
            links_confidence=brief.links_confidence,
            brand_name=brief.brand_name,
            source_path=brief.source_path,
            source_format=brief.source_format,
            raw_data=brief.raw_data,
        )

        # Re-check clarifications
        clarifications = self._check_clarifications(updated_brief)
        if clarifications:
            return BriefResult(
                state=BriefState.NEEDS_CLARIFICATION,
                brief=updated_brief,
                clarifications=tuple(clarifications),
                task_options=(),
            )

        return BriefResult(
            state=BriefState.READY,
            brief=updated_brief,
            clarifications=(),
            task_options=(),
        )

    def _build_brief_model(self, raw: RawBriefExtraction) -> BriefModel:
        """Build BriefModel from raw extraction."""
        # Build keywords
        keywords = self._build_keywords(raw.keyword_groups)

        # Build sections
        sections = tuple(
            BriefSection(
                heading=s.heading,
                word_count=s.word_count,
                is_required=True,
                confidence=s.confidence,
            )
            for s in raw.sections
        )

        # Map task to article type
        task_name = raw.task_name or ""
        article_type, type_confidence = map_task_to_article_type(task_name)

        # Use explicitly set task name confidence if higher
        if raw.task_name_confidence > type_confidence:
            type_confidence = raw.task_name_confidence

        # Build links
        links = tuple(
            BriefLink(
                anchor=link.anchor,
                url=link.url,
                link_type=link.link_type,
                confidence=link.confidence,
            )
            for link in raw.links
        )

        return BriefModel(
            keywords=keywords,
            keywords_confidence=raw.keywords_confidence,
            sections=sections,
            sections_confidence=raw.sections_confidence,
            target_word_count=raw.target_word_count or 0,
            word_count_confidence=raw.word_count_confidence,
            task_name=task_name,
            article_type=article_type,
            article_type_confidence=type_confidence,
            locale=raw.locale,
            market=raw.market,
            locale_confidence=raw.locale_confidence,
            links=links,
            links_confidence=raw.links_confidence,
            brand_name=raw.brand_name or "",
            source_path=raw.source_path,
            source_format=raw.source_format,
            raw_data=raw.raw_data,
        )

    def _build_keywords(self, groups: list[RawKeywordGroup]) -> BriefKeywords:
        """Convert raw keyword groups to BriefKeywords."""
        main_kws = []
        support_kws = []
        lsi_kws = []

        for group in groups:
            for kw_tuple in group.keywords:
                # New format: (keyword, min_qty, max_qty)
                keyword = kw_tuple[0]
                min_qty = kw_tuple[1] if len(kw_tuple) > 1 else None
                max_qty = kw_tuple[2] if len(kw_tuple) > 2 else None

                kw = BriefKeyword(
                    keyword=keyword,
                    min_quantity=min_qty,
                    max_quantity=max_qty,
                    group=group.group_name,
                    confidence=group.confidence,
                )

                if group.group_name == "main":
                    main_kws.append(kw)
                elif group.group_name == "support":
                    support_kws.append(kw)
                elif group.group_name == "lsi":
                    lsi_kws.append(kw)
                else:
                    # Default unknown groups to main
                    main_kws.append(kw)

        return BriefKeywords(
            main=tuple(main_kws),
            support=tuple(support_kws),
            lsi=tuple(lsi_kws),
        )

    def _build_keywords_from_confirmation(self, kw_data: Any) -> BriefKeywords:
        """Build BriefKeywords from user confirmation."""
        if isinstance(kw_data, BriefKeywords):
            return kw_data

        # Handle dict format
        main_kws = []
        support_kws = []
        lsi_kws = []

        def make_keyword(kw_info: dict, group: str) -> BriefKeyword:
            """Create BriefKeyword from dict with backwards compatibility."""
            min_qty = kw_info.get("min_quantity")
            max_qty = kw_info.get("max_quantity")
            # Backwards compatibility: if 'quantity' is present and min/max are not
            if min_qty is None and max_qty is None and "quantity" in kw_info:
                qty = kw_info["quantity"]
                min_qty = qty
                max_qty = qty
            return BriefKeyword(
                keyword=kw_info["keyword"],
                min_quantity=min_qty,
                max_quantity=max_qty,
                group=group,
                confidence=1.0,
            )

        if isinstance(kw_data, dict):
            for kw_info in kw_data.get("main", []):
                main_kws.append(make_keyword(kw_info, "main"))
            for kw_info in kw_data.get("support", []):
                support_kws.append(make_keyword(kw_info, "support"))
            for kw_info in kw_data.get("lsi", []):
                lsi_kws.append(make_keyword(kw_info, "lsi"))
        elif isinstance(kw_data, list):
            # Simple list treated as main keywords
            for kw in kw_data:
                if isinstance(kw, str):
                    main_kws.append(BriefKeyword(
                        keyword=kw,
                        min_quantity=None,
                        max_quantity=None,
                        group="main",
                        confidence=1.0,
                    ))
                elif isinstance(kw, dict):
                    main_kws.append(make_keyword(kw, "main"))

        return BriefKeywords(
            main=tuple(main_kws),
            support=tuple(support_kws),
            lsi=tuple(lsi_kws),
        )

    def _build_sections_from_confirmation(self, sec_data: Any) -> tuple[BriefSection, ...]:
        """Build sections from user confirmation."""
        if isinstance(sec_data, tuple):
            return sec_data

        sections = []
        if isinstance(sec_data, list):
            for item in sec_data:
                if isinstance(item, str):
                    sections.append(BriefSection(
                        heading=item,
                        word_count=None,
                        is_required=True,
                        confidence=1.0,
                    ))
                elif isinstance(item, dict):
                    sections.append(BriefSection(
                        heading=item["heading"],
                        word_count=item.get("word_count"),
                        is_required=item.get("is_required", True),
                        confidence=1.0,
                    ))

        return tuple(sections)

    def _check_clarifications(self, brief: BriefModel) -> list[Clarification]:
        """Check for elements needing clarification."""
        clarifications = []

        # Keywords are critical
        if brief.keywords_confidence < self.keyword_threshold:
            all_kws = brief.keywords.all_keywords
            detected = [kw.keyword for kw in all_kws] if all_kws else []

            if not detected:
                question = "No keywords were found in the brief. Please provide the keywords."
            else:
                question = f"I found these keywords but I'm not certain: {', '.join(detected[:10])}... Confirm or correct?"

            clarifications.append(Clarification(
                field="keywords",
                question=question,
                detected_value=detected,
                confidence=brief.keywords_confidence,
            ))

        # Sections are important
        if brief.sections_confidence < self.section_threshold:
            detected = [s.heading for s in brief.sections] if brief.sections else []

            if not detected:
                question = "No section structure was found. Please provide the required sections."
            else:
                question = f"I found these sections but I'm not certain: {', '.join(detected[:5])}... Confirm or correct?"

            clarifications.append(Clarification(
                field="sections",
                question=question,
                detected_value=detected,
                confidence=brief.sections_confidence,
            ))

        # Article type
        if brief.article_type_confidence < self.article_type_threshold:
            clarifications.append(Clarification(
                field="article_type",
                question=f"Task name '{brief.task_name}' is ambiguous. What type of article is this?",
                detected_value=brief.article_type.value,
                confidence=brief.article_type_confidence,
                options=tuple(t.value for t in ArticleType),
            ))

        # Word count - only if completely missing
        if brief.target_word_count == 0 and brief.word_count_confidence < self.word_count_threshold:
            clarifications.append(Clarification(
                field="target_word_count",
                question="Target word count not found. What is the target length?",
                detected_value=None,
                confidence=brief.word_count_confidence,
            ))

        return clarifications
