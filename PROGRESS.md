# Pitboss v4 Build Progress

## Current Phase

**Phase 2: In Progress** - Deterministic Layer (the 95%)

Checks complete:
- `deterministic/voice.py` - third-to-second person conversion
- `deterministic/stop_words.py` - weighted stop word detection (hard/soft tiers)
- `deterministic/headings.py` - capitalization, question marks, hierarchy, blank lines
- `deterministic/currency.py` - symbol/code consistency, combined violations, multi-convention gating

### Phase 1 Recap
Voice models built from 270 articles across 17 brands:
- House model: 22.46:1 person ratio, 14.93 words/sentence
- 13 type models, 12 brand models

## Frozen Contracts (Phase 0)

These three files are **frozen** - no modifications without explicit discussion:

### 1. `core/document.py`
The Document model representing parsed content:
- `Document` - container with elements, metadata, full_text
- `Paragraph`, `Heading`, `List`, `ListItem`, `Table`, `TableRow`, `TableCell`
- `TextRun` - inline formatting spans (bold, italic, hyperlinks, highlights)
- All elements have `start_offset`/`end_offset` for Finding anchoring

### 2. `core/finding.py`
The Finding dataclass for check results:
- `Finding` - severity, message, span offsets, check_id, suggestion, metadata
- `Severity` enum: ERROR, WARNING, INFO, STYLE
- Immutable, JSON-serializable

### 3. `core/check_base.py`
The Check interface with registry:
- `Check` abstract base class with `run(doc, standards) -> list[Finding]`
- `CheckRegistry` for discovering and running checks
- `@register_check` decorator

## Build Sequence

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Core contracts (Document, Finding, Check) | **Complete** |
| 1 | Layered Voice Model Builder | **Complete** |
| 2 | Deterministic Layer (the 95%) | **In Progress** |
| 3 | Brief agent (confidence-scored extraction) | Pending |
| 4 | Output/redline (Google Doc integration) | Pending |
| 5 | Judgment layer (the 5%) | Pending |
| 6 | Learning loop (feedback calibration) | Pending |
| 7 | Fact-checker (claim-driven verification) | Pending |

## Phase 1 Deliverables

### Files Created
- `ingest/docx_reader.py` - Parse .docx to Document model
- `core/voice_model.py` - Complete voice model system (~800 lines)
- `core/person_reference.py` - Third-person reference classifier (~200 lines)
- `tests/fixtures/generate_fixtures.py` - Creates test .docx files
- `tests/test_voice_model.py` - 51 comprehensive tests
- `tests/test_person_reference.py` - 69 comprehensive tests

### Key Components
- `VoiceFingerprint` - Measurable voice characteristics
- `VoiceModel` - Layer wrapper (house/type/brand)
- `FingerprintBuilder` - Extract fingerprint from documents
- `VoiceModelBuilder` - Build all three layers
- `get_voice_layers()` - Blend helper returning available layers
- `generate_corpus_index()` - First-pass type inference from filenames
- `PersonRefType` - Enum: READER_REF, GENERIC_NOUN, UNCLEAR
- `classify_person_references()` - Classify third-person nouns by context

## Session Decisions

### Transition Phrase Extraction
**Decision:** Combine predefined list with discovered patterns

Implementation:
1. Predefined list of ~50 common transitions (However, In addition, etc.)
2. Discover frequent sentence-start patterns from corpus
3. Normalize case and strip brand name from openers
4. Report frequency as **rate per 100 sentences** for corpus size comparability
5. Flag any discovered opener matching banned/weak transitions as `discouraged_observed`

### Brand Model Threshold
**Decision:** 10 articles minimum for brand-level voice model

Brands with fewer articles rely on house + type layers only.

### Type Inference
**Decision:** First-pass inference from filename patterns, stored in `corpus_index.csv`

User reviews and corrects the `inferred=true` entries before final build.

### Article Type Clusters (13 total)
app_review, bonus_page, game_review, sports_market, payments, registration,
customer_support, responsible_gaming, vip_loyalty, privacy_policy, live_casino,
main_review, general

### Person Reference Classification
**Decision:** Classify third-person nouns (player/user/punter/bettor/customer/gambler) into three categories:

1. **READER_REF** - Addresses the reader, convertible to "you"
   - Modal verbs: "players can/must/should/will/may"
   - Direct address: "gives players", "allows users", "lets players"
   - Conditional: "if players deposit"

2. **GENERIC_NOUN** - Population reference, NOT convertible
   - Adjective-qualified: "new players", "slot players", "VIP players"
   - Quantity: "most players", "thousands of players"
   - Behavioral: "players usually prefer", "players tend to"
   - Geographic: "Canadian players", "players from Canada"

3. **UNCLEAR** - Ambiguous context, default

**Result:** House model person ratio improved from 4.24:1 (all third-person) to 22.46:1 (reader-ref only), now within target range of 10-30:1.

**Phase 2 Voice Check Design:** The three classifications map to three conversion behaviors:
- **READER_REF** → Auto-applicable redline (high confidence, `auto_applicable=True`)
- **GENERIC_NOUN** → Never converted (skip silently)
- **UNCLEAR** → Low-confidence proposal (`auto_applicable=False`), surfaced for human review, never auto-applied

The 937 UNCLEAR count in the corpus confirms this middle path matters — silently converting or silently skipping them would both be wrong.

## Test Status

```
446 tests passing
├── 148 tests (Phase 0 - core contracts)
├── 51 tests (Phase 1 - voice model)
├── 78 tests (Phase 1 - person reference classifier)
├── 59 tests (Phase 2 - voice check)
├── 35 tests (Phase 2 - stop words check)
├── 34 tests (Phase 2 - headings check)
└── 41 tests (Phase 2 - currency check)
```

## Phase 2 Deliverables

### Voice Check (Complete)

**Files:**
- `deterministic/voice.py` - Third-to-second person conversion check
- `tests/test_voice_check.py` - 59 comprehensive tests

**Corpus Validation:**
- Tested against 3 real articles (22Bet, HellSpin, CookieCasino)
- **9 auto-applicable conversions** - all grammatically clean
- **0 broken auto-applies** - compound nouns, platform qualifiers, and relative clauses correctly handled
- **18 proposals** - uncertain cases routed to human review

**Three-Way Behavior:**
| Classification | Action | Confidence | auto_applicable |
|---------------|--------|------------|-----------------|
| READER_REF | Convert | 0.95 | True |
| GENERIC_NOUN | Skip | - | - |
| UNCLEAR | Propose | 0.4 | False |

**Classifier Patterns Added:**
- Compound nouns: "player protection", "player safety", "user-friendly"
- Platform qualifiers: "Android users", "iOS players", "desktop users"
- Relative clause detection: "players who..." → proposal (can't swap cleanly)

### Auto-Applicable Bar (Design Principle)

**Grammatically clean every time, no exceptions.**

Any conversion pattern with occasional breakage must downgrade to a proposal (`auto_applicable=False`). The deterministic layer's value is 100% consistency — if we can't guarantee clean output, it goes to human review.

Examples that became proposals:
- "players who don't have time" → "you who don't have time" is broken → proposal
- Complex restructures the converter can't handle cleanly → proposal

### Stop Words Check (Complete)

**Files:**
- `deterministic/stop_words.py` - Weighted stop word detection
- `tests/test_stop_words.py` - 35 comprehensive tests

**Two-Tier Detection:**
| Tier | Weight | Severity | When Flagged |
|------|--------|----------|--------------|
| Hard | 1.0 | warning | Always |
| Soft | 0.3 | suggestion | Above 0.5% density |

**Features:**
- Multi-word phrase support ("dive into", "treasure trove", "at your fingertips")
- Inflection handling (delve → delving/delved, unlock → unlocking/unlocked)
- Case-insensitive matching with word boundaries
- No auto-fix (`auto_applicable=False`, `proposed_text=None`)

**Critical Fix: Reader-Reference Nouns Removed**

Reader-reference nouns (punters/bettors/players/users/customers/gamblers) belong to the **voice module only**, never the stop-word list. Having "punters" in `stop_words.hard` caused contradictory double-flagging:
- Stop words: "remove this word"
- Voice check: "convert to you"

**Fix:** Removed "punters" from `brands/_defaults.yaml` stop_words.hard. Other reader-reference nouns were already correctly absent.

**Corpus Validation (after fix):**
- 20Bet Betting: **3 hard findings** (genuine quality words: "seamless", "excitement", "seasoned")
- 20Bet Bonuses: **13 soft findings** at 0.75% density (7x "unlock", 2x "tailored", 2x "exciting", 2x "thrill")
- **0.5% soft density threshold confirmed sane** — only flags when soft words become frequent

### Headings Check (Complete)

**Files:**
- `deterministic/headings.py` - Heading formatting check (~500 lines)
- `tests/test_headings_check.py` - 34 comprehensive tests
- `brands/koifortune.yaml` - Brand config for sentence_case testing

**Dependencies:**
- `wordfreq>=3.0.0` - Dictionary lookup for proper noun detection

**Five Sub-Checks:**

| Sub-check | Detection | auto_applicable |
|-----------|-----------|-----------------|
| `blank_line` | Gap=1 between elements | True (pure formatting) |
| `question_mark` | Heading ends with `?` | True (non-FAQ), False (ambiguous) |
| `capitalization` | Mismatch with brand standard | True (ordinary words), False (acronyms) |
| `descriptive` | Single-word generic heading | False (flag only) |
| `hierarchy` | Skipped levels, multiple H1 | False (flag only) |

**Key Design Decisions:**

1. **FAQ Section Detection**: Question marks preserved inside FAQ/Frequently Asked sections
2. **"How to..." Pattern**: Treated as instructional (auto-remove `?`), not FAQ-like
3. **Dictionary-Based Capitalization**: Uses `wordfreq` library to distinguish common words from proper nouns
   - Dictionary words (games, casino, bonus) → auto-applicable
   - Non-dictionary words (Vave, Bonanza, NetEnt) → proposal (likely proper noun)
   - Known acronyms: iOS, VIP, FAQ, RNG, KYC, PWA, AI, etc.
   - Known proper nouns (belt-and-suspenders): Android, Windows, Pragmatic, Evolution, Bitcoin, etc.
   - Question headings (interrogative + ?) also route to proposal
4. **Title Case Algorithm**: Capitalize principal words, lowercase articles/prepositions (a, an, the, of, to, for, in, on, at, by, and, or, but)
5. **Sentence Case Algorithm**: Capitalize first word, preserve acronyms, lowercase others

**Corpus Validation (5 articles, 160 headings):**
- **52 auto-applicable capitalization** (common dictionary words only)
- **25 capitalization proposals** (proper nouns, acronyms, question headings)
- **158 auto-applicable blank lines** (pure formatting, always safe)
- FAQ question marks correctly preserved inside FAQ sections (14 preserved)
- Question mark proposals for ambiguous non-FAQ questions (2 proposals)

**Dictionary-Based Proper Noun Detection:**
Uses `wordfreq` library (word frequency threshold 1e-7) to distinguish common English words from proper nouns:
- If word is in dictionary → safe to auto-apply recase
- If word is NOT in dictionary → likely proper noun → route to proposal

This approach correctly handles:
- Common words: "Popular Games" → "Popular games" (auto)
- Game titles: "Sweet Bonanza Strategy" → proposal (Bonanza not in dictionary)
- Brand names: "Vave Casino Features" → proposal (Vave not in dictionary)
- Provider names: "NetEnt Slots" → proposal (NetEnt not in dictionary)

### Currency Check (Complete)

**Files:**
- `deterministic/currency.py` - Currency formatting consistency check (~560 lines)
- `tests/test_currency_check.py` - 41 comprehensive tests

**Section 11 Compliance:**
1. Use currency symbol OR abbreviation, never both
2. Be consistent within an article

**Two Sub-Checks:**

| Sub-check | Detection | auto_applicable |
|-----------|-----------|-----------------|
| `combined_violation` | Symbol + code together (`$20 CAD`) | True (definite §11 violation) |
| `style_inconsistency` | Minority style vs dominant | Conditional (see below) |

**Key Features:**

1. **Combined Violations Always Auto**: `$20 CAD` → `20 CAD` is a definite §11 violation (using both symbol AND code). These auto-apply regardless of convention count.

2. **Distinct Convention Tracking**: Each symbol/code tracked separately:
   - `symbol:A$`, `symbol:$`, `symbol:€` (different conventions)
   - `code:AUD`, `code:USD`, `code:USDT` (different conventions)
   - Bare `$` distinguished from prefixed symbols (`A$`, `C$`, `NZ$`)

3. **Multi-Convention Gating**: Lone-minority normalization (`10 AUD` → `A$10`) becomes PROPOSAL when:
   - 3+ distinct conventions present (no clear house style)
   - Prose and tables use different conventions
   - Dominant style ratio ≤70%

4. **Crypto Support**: USDT, USDC, BTC, ETH, etc. recognized; no symbol mapping for code-only crypto skips gracefully

**Corpus Validation:**
- **KoiFortune Bonus Canada**: 6 combined violations (`$20 CAD` → `20 CAD`) — all **AUTO**
- **KoiFortune Bonuses AU**: 4 conventions (A$, $, AUD, USDT) — `10 AUD` → `A$10` is **PROPOSAL**
  - Reasoning: "This article uses 4 different currency conventions. Human review needed to decide which style to standardize on."

### Auto-Apply Design Principle (Confirmed Across All Checks)

The same bar applies to all four completed checks:

**Auto-apply = edits you'd unambiguously make yourself.**

| Situation | Action | Reasoning |
|-----------|--------|-----------|
| Definite violation | AUTO | Clear rule broken (combined `$20 CAD`, hard stop word, `?` on non-FAQ heading) |
| Clear majority style | AUTO | >70% dominant, simple conversion (READER_REF → you, dictionary word recase) |
| Ambiguous/judgment call | PROPOSAL | Multiple conventions, unknown word, UNCLEAR classification |
| Context-dependent | PROPOSAL | Prose vs table differ, proper noun possible, relative clause |

This principle ensures the deterministic layer's value: 100% consistency for auto-applies, human review for anything requiring judgment.

### Remaining Phase 2 Checks

| Check | Description | Status |
|-------|-------------|--------|
| `voice.py` | Third-to-second person | **Complete** |
| `stop_words.py` | Weighted stop-word detection (hard/soft tiers) | **Complete** |
| `headings.py` | Capitalization, hierarchy, spacing, question marks | **Complete** |
| `currency.py` | Format consistency (symbol XOR abbreviation) | **Complete** |
| `brand_names.py` | Normalization (Bet Label → BetLabel) | Pending |
| `locale_spelling.py` | UK/US/CA/AU/NZ dictionary swaps | Pending |
| `formatting.py` | Whitespace, list punctuation, UI quoting | Pending |
| `keywords.py` | Keyword counting + density against brief | Pending |
| `structure.py` | Paragraph-between-headings, other structure rules | Pending |

---
*Last updated: Phase 2 in progress - voice, stop words, headings, and currency checks complete and validated (446 tests). Remaining: formatting, locale_spelling, brand_names, keywords, structure.*
