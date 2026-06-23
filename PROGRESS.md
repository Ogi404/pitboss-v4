# Pitboss v4 Build Progress

## Current Phase

**Phase 4a: Complete** - Output Pipeline Core (Local DOCX) — all 5 artifact verification bugs fixed

**Phase 3: Complete** - Brief Understanding Agent

**Phase 2: Complete** - Deterministic Layer (the 95%) - ALL 9 CHECKS DONE

Checks complete:
- `deterministic/voice.py` - third-to-second person conversion
- `deterministic/stop_words.py` - weighted stop word detection (hard/soft tiers)
- `deterministic/headings.py` - capitalization, question marks, hierarchy, blank lines
- `deterministic/currency.py` - symbol/code consistency, combined violations, multi-convention gating
- `deterministic/formatting.py` - whitespace, punctuation spacing, Latin abbreviations
- `deterministic/locale_spelling.py` - regional variant enforcement (British/American/Canadian/Australian/NZ)
- `deterministic/brand_names.py` - own-brand normalization with dominance threshold, competitor detection
- `deterministic/keywords.py` - keyword coverage/density against brief (exact-phrase matching per §8)
- `deterministic/structure.py` - article structure vs brief requirements + §10 (fuzzy section matching, hierarchy, intro/outro, word count)

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
| 2 | Deterministic Layer (the 95%) | **Complete** (9/9 checks) |
| 3 | Brief agent (confidence-scored extraction) | **Complete** |
| 4a | Output pipeline core (local DOCX) | **Complete** |
| 4b | Google Docs integration | **Stage 3 Complete** (read/write/comments) |
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
818 tests passing (3 skipped)
├── 148 tests (Phase 0 - core contracts)
├── 51 tests (Phase 1 - voice model)
├── 78 tests (Phase 1 - person reference classifier)
├── 59 tests (Phase 2 - voice check)
├── 35 tests (Phase 2 - stop words check)
├── 34 tests (Phase 2 - headings check)
├── 41 tests (Phase 2 - currency check)
├── 46 tests (Phase 2 - formatting check, 3 skipped)
├── 78 tests (Phase 2 - locale spelling check)
├── 33 tests (Phase 2 - brand names check)
├── 40 tests (Phase 2 - keywords check)
├── 52 tests (Phase 2 - structure check)
├── 67 tests (Phase 3 - brief agent)
├── 17 tests (Phase 4a - orchestrator)
└── 42 tests (Phase 4a - apply layer)
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
- `brands/koifortune.yaml` - Brand config for title_case (corpus: 89.5% title case)

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
- Capitalization findings vary by brand config (title_case vs sentence_case)
- Proper nouns, acronyms, question headings → routed to proposals (not auto)
- **158 auto-applicable blank lines** (pure formatting, always safe)
- FAQ question marks correctly preserved inside FAQ sections (14 preserved)
- Question mark proposals for ambiguous non-FAQ questions (2 proposals)

**Koifortune Config Corrected:** Corpus analysis (315/352 = 89.5% title case) proved `sentence_case` config was wrong. Changed to `title_case` — now 0 auto-fixes on correct headings.

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

### Formatting Check (Complete)

**Files:**
- `deterministic/formatting.py` - Mechanical formatting consistency (~500 lines)
- `tests/test_formatting_check.py` - 46 tests (3 skipped)

**Six Sub-Checks:**

| Sub-check | Detection | auto_applicable | Status |
|-----------|-----------|-----------------|--------|
| `double_space` | Two+ consecutive spaces | True | Active |
| `space_before_punct` | Space before `,` `.` `;` `:` `!` `?` | True | Active |
| `missing_space_after` | Missing space after `,` `.` | True (clear), False (ambiguous) | Active |
| `latin_abbrev` | `e.g.`, `i.e.`, `etc.`, `viz.`, `cf.` | False (contextual) | Active |
| `ui_quoting` | Unquoted UI elements | False | **DISABLED** |
| `trailing_whitespace` | Trailing spaces/tabs | True | Active |

**Key Features:**

1. **Whitespace Auto-Fixes**: Double spaces, space-before-punctuation, and trailing whitespace are always safe to auto-apply. Corpus is clean (writers have good formatting hygiene).

2. **Missing Space After Punctuation**: Catches real typos ("now.Solid" → "now. Solid") with extensive false-positive exclusions:
   - Decimals: `3.5`, `0.99`
   - Thousands separators: `1,000`
   - Domains/TLDs: `.com`, `.ai`, `.co.uk`
   - Abbreviations: `e.g.`, `i.e.`, `N.V.`, `Dr.`
   - Version numbers: `v1.2`

3. **Latin Abbreviations**: Requirements prohibit `e.g.`, `i.e.`, `etc.` ("get straight to the point"). Flagged as proposals with suggested replacements:
   - `e.g.` → "for example"
   - `i.e.` → "that is"
   - `etc.` → "[rephrase to be specific]"

4. **UI Quoting DISABLED**: Sub-check intended to flag unquoted UI elements ("tap Register" → "tap 'Register'"). **Disabled after 3/3 false positives** in corpus validation:
   - Flagged country names ("choose India")
   - Flagged nationalities ("choose Malaysian")
   - Flagged section headings ("Hit Wins With")
   - Method retained for future refinement if needed.

**Corpus Validation (20 articles):**
- **0 double_space** — corpus is clean
- **0 space_before_punct** — corpus is clean
- **1 missing_space_after** — valid typo caught
- **2 latin_abbrev** — "etc." correctly flagged
- **0 trailing_whitespace** — corpus is clean

Writers have good formatting hygiene; this check catches edge cases rather than systemic issues.

### Locale Spelling Check (Complete)

**Files:**
- `deterministic/locale_spelling.py` - Regional spelling variant enforcement (~480 lines)
- `tests/test_locale_spelling_check.py` - 55 comprehensive tests

**Section 4 Compliance:**
Enforce correct regional spelling variants based on brand's target market (read from `standards.spelling_region`).

**Five Spelling Regions:**

| Region | Countries | Key Patterns |
|--------|-----------|--------------|
| british | UK, IN, LK, PK, SG, MM, HK, KE, NG | -ise, -our, -re, -lled |
| american | US, PH, TW, KR, JP | -ize, -or, -er, -led |
| canadian | CA | **HYBRID**: British -our/-re + American -ize |
| australian | AU | Follows British |
| new_zealand | NZ | Follows British |

**Key Features:**

1. **Canadian Hybrid**: Critical for Koifortune (CA market). Correctly enforces:
   - British -our (colour, favour, favourite)
   - British -re (centre, metre, theatre)
   - American -ize (organize, realize, finalize) — British -ise is **wrong** in Canadian
   - British grey (not gray)

2. **100+ Word Pairs**: Covers -ise/-ize, -isation/-ization, -our/-or, -re/-er, -lled/-led, -ogue/-og patterns plus special cases (defence/defense, tyre/tire, cheque/check, programme/program, jewellery/jewelry, etc.)

3. **Case Preservation**: Maintains original casing (lowercase, UPPERCASE, Title Case)

4. **Exclusions**: Quoted strings, URLs, email addresses skipped (brand names, proper nouns protected)

5. **Auto-Applicable for Unambiguous Swaps**: All standard variant swaps are auto (confidence 0.95). Context-dependent words (programme/program for software) handled in standard swap.

**Corpus Validation (Koifortune/Canadian, 14 articles):**

| Finding | Count | Type |
|---------|-------|------|
| finalise → finalize | 1 | AUTO (Canadian uses -ize) |
| realise → realize | 1 | AUTO (Canadian uses -ize) |
| favor → favour | 1 | AUTO (Canadian uses -our) |
| favorite → favourite | 3 | AUTO (Canadian uses -our) |
| flavor → flavour | 2 | AUTO (Canadian uses -our) |

**8 findings total, all clean common words** — no brand names, game titles, or proper nouns touched. Canadian hybrid working correctly: British -ise flagged as wrong, American -or flagged as wrong.

### Brand Names Check (Complete)

**Files:**
- `deterministic/brand_names.py` - Own-brand normalization and competitor detection (~550 lines)
- `tests/test_brand_names_check.py` - 33 comprehensive tests
- `config/known_operators.txt` - Competitor brand list (corpus + external operators)
- `brands/*.yaml` - 17 brand configs with corpus-derived canonicals and dominance ratios

**Section 9 Compliance:**
1. Normalize own-brand variants to canonical form (auto or proposal based on dominance)
2. Flag competitor brand mentions (always proposal)

**Two Sub-Checks:**

| Sub-check | Detection | auto_applicable |
|-----------|-----------|-----------------|
| `own_brand` | Brand variants (KoiFortune → Koifortune) | Conditional (see dominance threshold) |
| `competitor` | Other operator names in text | False (always proposal) |

**Key Feature: Corpus-Derived Canonicals with Dominance Threshold**

Canonicals are DERIVED FROM CORPUS analysis, not hand-set. Each brand YAML stores:
- `brand_name`: Corpus-dominant form (e.g., "KoiFortune" not "Koifortune")
- `canonical_dominance`: Ratio of canonical vs all variants in corpus

**85% Dominance Threshold:**

| Dominance | Mode | Behavior |
|-----------|------|----------|
| ≥ 85% | AUTO | Safe to auto-normalize (overwhelming corpus consensus) |
| < 85% | PROPOSAL | Human review required (mixed usage in corpus) |

**Final Brand Status:**

| Brand | Canonical | Dominance | Mode |
|-------|-----------|-----------|------|
| TonyBet | TonyBet | 94.9% | AUTO |
| Slotrave | Slotrave | 85.6% | AUTO |
| PlayAmo | PlayAmo | 97.8% | AUTO |
| HellSpin | HellSpin | 96.1% | AUTO |
| 22Bet | 22Bet | 96.8% | AUTO |
| Vave | Vave | 96.3% | AUTO |
| Mason Slots | Mason Slots | 97.3% | AUTO |
| Cookie Casino | Cookie Casino | 96.9% | AUTO |
| *(+ 5 more)* | - | 96-99% | AUTO |
| **KoiFortune** | KoiFortune | 58.0% | **PROPOSAL** |
| **Ivibet** | Ivibet | 64.3% | **PROPOSAL** |
| **Avalon78** | Avalon78 | 72.7% | **PROPOSAL** |
| **Royalxo** | Royalxo | 54.7% | **PROPOSAL** |

**Corpus Validation:**
- **13 AUTO brands**: 52 normalizations (genuine variants of high-dominance brands)
- **4 PROPOSAL brands**: 526 normalizations (mixed-usage brands → human review)

**Competitor Detection:**
- Flags mentions of other operators (bet365, DraftKings, etc.)
- High-precision mode for ambiguous names (stake/spin/royal/national/bet):
  - Only flags when capitalized AND not preceded by articles
  - "place your stake" → not flagged (common word)
  - "Stake offers crypto" → flagged (operator name)

**Load-Time Validation Guard:**
Warns if configured canonical doesn't match corpus-dominant form — catches config bugs before they cause mass mis-normalization.

### Keywords Check (Complete)

**Files:**
- `deterministic/keywords.py` - Keyword coverage and density check (~500 lines)
- `tests/test_keywords_check.py` - 40 comprehensive tests
- `validate_keywords_check.py` - Real article+brief validation script

**Section 8 Compliance:**
Compares article against READY BriefModel from brief agent. Exact-phrase matching per §8 ("use keywords as they are").

**Key Design Decision (Confirmed with Ogi):**
Reordered constructions like "Promotions at KoiFortune" do NOT satisfy keyword "Koifortune promotions". The brief requires the exact phrase as specified.

**Five Sub-Checks:**

| Sub-check | Detection | auto_applicable |
|-----------|-----------|-----------------|
| `keywords.missing` | Required keyword not found | False (always) |
| `keywords.quantity` | Count outside min/max range | False (always) |
| `keywords.density` | Overall density exceeds 3% | False (always) |
| `keywords.highlighting` | Main keywords not highlighted yellow | False (always) |
| `keywords.brand_overuse` / `keywords.location_overuse` | Stuffing detection | False (always) |

**ALL findings auto_applicable=False** — keyword fixes are always editorial judgment, never auto-applied.

**Missing Keyword Sub-Types:**

| Type | Meaning | Editor Action |
|------|---------|---------------|
| `truly_absent` | Concept not in article at all | Add new content |
| `wrong_construction` | Words present but not as exact phrase | Adjust existing wording |

For `wrong_construction` findings, reasoning includes nearby-text hint showing where the words appear:
> "Required keyword 'Koifortune promotions' not found. Note: article contains 'Promotions at KoiFortune AU' — the words are present but not as the exact keyword phrase."

**Key Features:**

1. **Exact Phrase Matching**: Word boundaries enforced, case-insensitive, singular/plural variants supported
2. **Longest-First Sorting**: Keywords sorted by length before matching to prevent overlap double-counting ("Koifortune Australia" matched before "Koifortune")
3. **Highlighting Detection**: Uses `document.highlighted_spans()` to check yellow highlighting per §8
4. **Density Calculation**: `(keyword_occurrences / total_words) * 100` with 50-word minimum threshold
5. **Brand/Location Overuse**: Flags when brand name or market location exceeds 2% density

**Corpus Validation (Koifortune article + brief):**

| Finding Type | Count | Details |
|--------------|-------|---------|
| Missing (wrong_construction) | 7 | Words present but not as phrase |
| Missing (truly_absent) | 7 | Concept not in article |
| Quantity (over max) | 2 | "Koifortune website" 3x (max 1) |
| Density | 1 | 3.2% overall (max 3%) |
| Brand overuse | 1 | 67 mentions (3.2% density) |

**All 14 missing findings are legitimate** — verified by manual inspection that exact phrases are genuinely absent.

### Structure Check (Complete)

**Files:**
- `deterministic/structure.py` - Article structure validation (~490 lines)
- `tests/test_structure_check.py` - 52 comprehensive tests
- `validate_structure_check.py` - Real article+brief validation script

**Section 10 Compliance:**
Compares article structure against brief requirements and General Writing Requirements §10.

**Five Sub-Checks:**

| Sub-check | Detection | auto_applicable |
|-----------|-----------|-----------------|
| `structure.missing_section` | Required section from brief not found | False (always) |
| `structure.hierarchy` | Multiple H1 or skipped heading levels | False (always) |
| `structure.missing_intro` | No paragraph before first heading | False (always) |
| `structure.missing_outro` | Ends with heading or <20 word paragraph | False (always) |
| `structure.word_count` | >20% deviation from brief target | False (always) |

**ALL findings auto_applicable=False** — structure fixes require editorial judgment, never auto-applied.

**Key Feature: Fuzzy Section Matching**

Unlike keywords (exact-phrase per §8), section matching uses fuzzy logic:
- Substring match: "Bonuses" matches "Welcome Bonuses and Promotions"
- Word overlap: "Payment Methods" matches "Methods of Payment" (≥50% word overlap)

This is intentional — sections represent concepts, not SEO phrases.

**Metadata Label Filter:**

Labels like "Main keywords", "Support keywords", "LSI keywords", "Word Count", "Meta Description" are filtered via `is_metadata_label()` and never treated as required article sections.

**Corpus Validation (Koifortune article + brief):**

| Finding Type | Count | Details |
|--------------|-------|---------|
| Missing sections | 0 | All brief sections fuzzy-matched |
| Hierarchy issues | 0 | Proper H1 → H2 → H3 structure |
| Intro/outro issues | 0 | Proper intro and conclusion |
| Word count deviation | 0 | 2091 vs 2000 target (4.5% over, within 20% threshold) |

**Zero false positives** — fuzzy matching correctly identifies present sections without false-flagging.

### KEY LESSON: Corpus Validation is Essential

**Three wrong canonicals were caught ONLY by corpus-validating against ground truth:**

1. **KoiFortune**: YAML said "Koifortune" but corpus dominant was "KoiFortune" (251 vs 171)
2. **RoyalXO**: YAML said "RoyalXO" but corpus dominant was "Royalxo" (226 vs 173)
3. **Ivibet/Avalon78**: Set as canonical but <85% dominant — mixed usage shouldn't auto-normalize

**All three passed unit tests.** Green tests prove internal consistency; only corpus validation proves correctness about the real domain.

**Principle for all future checks and the judgment layer:**
- A high auto-apply count is a **risk surface**, not a success metric
- The corpus is the source of truth for anything brand-specific
- Config values that CAN be corpus-derived MUST be corpus-derived
- Hand-set values MUST be cross-checked against corpus ground truth

### Auto-Apply Design Principle (Confirmed Across All Checks)

The same bar applies to all five completed checks:

**Auto-apply = edits you'd unambiguously make yourself.**

| Situation | Action | Reasoning |
|-----------|--------|-----------|
| Definite violation | AUTO | Clear rule broken (combined `$20 CAD`, hard stop word, `?` on non-FAQ heading) |
| Clear majority style | AUTO | >70% dominant, simple conversion (READER_REF → you, dictionary word recase) |
| Ambiguous/judgment call | PROPOSAL | Multiple conventions, unknown word, UNCLEAR classification |
| Context-dependent | PROPOSAL | Prose vs table differ, proper noun possible, relative clause |

This principle ensures the deterministic layer's value: 100% consistency for auto-applies, human review for anything requiring judgment.

### Phase 2 Check Summary (ALL COMPLETE)

| Check | Description | Status |
|-------|-------------|--------|
| `voice.py` | Third-to-second person | **Complete** |
| `stop_words.py` | Weighted stop-word detection (hard/soft tiers) | **Complete** |
| `headings.py` | Capitalization, hierarchy, spacing, question marks | **Complete** |
| `currency.py` | Format consistency (symbol XOR abbreviation) | **Complete** |
| `formatting.py` | Whitespace, punctuation spacing, Latin abbreviations | **Complete** |
| `locale_spelling.py` | UK/US/CA/AU/NZ regional variant enforcement | **Complete** |
| `brand_names.py` | Own-brand normalization with dominance threshold, competitor detection | **Complete** |
| `keywords.py` | Keyword coverage + density against brief (exact-phrase matching) | **Complete** |
| `structure.py` | Article structure vs brief + §10 (fuzzy section matching, hierarchy, intro/outro, word count) | **Complete** |

**PHASE 2 COMPLETE:** All 9 deterministic checks built, corpus-validated, committed. 735 tests passing.

### Tech Debt (Minor)

**Metadata labels in brief sections:** Keyword-group labels ("Main keywords", "Support keywords", etc.) are currently stored as brief sections by the xlsx parser and filtered per-check via `is_metadata_label()`. Cleaner long-term fix: brief parser should not put them in sections at all. Not urgent — filtering works correctly.

**docx_reader table ordering:** `docx_reader` places all tables at the end of the element list rather than their true document position (due to python-docx iterating `doc.paragraphs` then `doc.tables` separately). `gdoc_reader` preserves correct order. Currently harmless (checks operate per-element), but this could cause offset errors in the apply layer for table-adjacent edits. Revisit if table-boundary edits misbehave.

## Phase 3 Deliverables

### Brief Understanding Agent (Complete)

**Files Created:**
- `ingest/brief_model.py` - Data models (~200 lines)
- `ingest/brief_base.py` - Parser ABC and registry (~230 lines)
- `ingest/brief_agent.py` - Orchestrator (~300 lines)
- `ingest/brief_formats/__init__.py` - Parser package init
- `ingest/brief_formats/xlsx_parser.py` - Excel brief parser (~300 lines)
- `ingest/brief_formats/docx_parser.py` - Word brief parser (~250 lines)
- `tests/test_brief_agent.py` - 62 comprehensive tests

**Core Rule: NEVER SILENTLY GUESS**

The Brief Agent is a first-class subsystem that parses briefs into structured, confidence-scored data. When confidence is low on critical elements, it asks rather than fabricating.

**BriefModel (The Fourth Frozen Contract):**
```python
@dataclass(frozen=True)
class BriefModel:
    keywords: BriefKeywords        # main, support, LSI groups
    keywords_confidence: float
    sections: tuple[BriefSection, ...]
    sections_confidence: float
    target_word_count: int
    word_count_confidence: float
    task_name: str
    article_type: ArticleType      # Mapped from task name
    article_type_confidence: float
    locale: Optional[str]
    market: Optional[str]
    locale_confidence: float
    brand_name: str
    source_path: str
    source_format: str             # xlsx, docx, sheets
```

**Three Return States:**

| State | When | Action |
|-------|------|--------|
| `READY` | All critical elements high confidence | Proceed to checks |
| `NEEDS_CLARIFICATION` | Keywords/sections below threshold | Ask user to confirm |
| `NEEDS_TASK_SELECTION` | Multi-task brief detected | Ask user to pick task |

**Confidence Thresholds:**

| Element | Threshold | Triggers |
|---------|-----------|----------|
| Keywords | 0.7 | Clarification if below |
| Sections | 0.6 | Clarification if below |
| Article Type | 0.6 | Clarification if below |
| Word Count | 0.5 | Clarification only if missing |

**Confidence Scoring by Extraction Quality:**

| Scenario | Confidence |
|----------|------------|
| Clean table with headers (Keyword/Qty) | 0.95 |
| Table without clear quantity column | 0.75-0.80 |
| Inline pattern ("Keywords: a, b, c") | 0.60-0.70 |
| Ambiguous inline blob | 0.40 |
| No keywords found | 0.0 (triggers NEEDS_CLARIFICATION) |

**Article Type Mapping:**
- 13 article type clusters from task name patterns
- Fuzzy pattern matching (e.g., "Bonus" → BONUS_PAGE)
- Unknown types fall back to GENERAL with low confidence

**Self-Registering Parser Pattern:**
```python
@register_brief_parser
class XlsxBriefParser(BriefParser):
    def get_format_name(self) -> str:
        return "xlsx"

    def can_parse(self, source) -> bool:
        return Path(source).suffix.lower() in (".xlsx", ".xls")

    def extract(self, source) -> RawBriefExtraction:
        # Format-specific parsing with confidence scoring
        ...
```

**Format Support:**
- **xlsx**: Single/multi-tab, multi-task detection (stacked Task-name/Topic blocks), keyword tables, section tables, meta fields
- **docx**: Inline keywords, key-value tables, structured tables, Title-styled multi-task detection
- **sheets**: Deferred (requires Google API credentials)

**Multi-Task Detection (Pluggable Detectors):**

Two detector patterns, extensible for future layouts:

| Detector | Format | Signal | Example |
|----------|--------|--------|---------|
| Stacked blocks | xlsx | Multiple "Task name:"/"Topic:" rows | Content Task 22Bet (stacked tasks) |
| Title-styled paragraphs | docx | `style=Title` paragraphs | 10-page Ghana briefs |

When any detector finds 2+ tasks → NEEDS_TASK_SELECTION with task list.

**Multi-Language Keyword Parsing:**

Handles messy multi-language keyword lines like:
```
LSI Keywords: bonus, cashback, VIP. (ITA: bonus, rimborso.) bonus, cashback (CZ)
```

**Translation stripping:**
- Strips `(ITA: ...)` parenthetical blocks
- Strips `.ITA:` bare language markers
- Strips trailing `(CZ)` markers
- Only extracts English portion before first translation marker

**Validation output:** 102 fragment-keywords → 41 clean English keywords

**Article Type Inference (Highest-Count-Wins):**

When task name is missing/ambiguous, infers type from keyword content:
- Counts matches for ALL categories (slot, sports, bonus, app, payments)
- Returns category with MOST matches (not first-match-wins)
- Ties or all-below-threshold → GENERAL with low confidence (asks user)

Example fix: Vave bonuses had 32 bonus matches vs 7 slot matches — now correctly returns `bonus_page` instead of `game_review`.

**Metadata Label Negative Filter:**

NEVER extracts structural labels as keywords:
- Section, Platform, Target URL, Word Count, Template Variant, Tone
- H1, H2, H2 #1, H2 #2, etc.
- Link 1, Link 1 — Anchor, Link 1 — URL, etc.
- Key Competitions, Unique Aspects, FAQ Targets, Content Strategy

**Keyword Validation:**

Keywords passing through must:
- Not contain language markers (ITA:, CZ:, parentheses)
- Not exceed 8 words (likely sentence fragments)
- Not be metadata labels

Invalid keywords dropped; many failures → lower confidence → asks user.

**Usage Example:**
```python
agent = BriefAgent()
result = agent.parse("path/to/brief.xlsx")

if result.state == BriefState.READY:
    brief = result.brief
    # proceed to checks
elif result.state == BriefState.NEEDS_CLARIFICATION:
    for clar in result.clarifications:
        print(f"{clar.question}")
        # Get user input...
    confirmed = agent.confirm_clarifications(result.brief, user_confirmations)
elif result.state == BriefState.NEEDS_TASK_SELECTION:
    print(f"Pick a task: {result.task_options}")
    result = agent.parse_with_task(path, selected_task)
```

**Key Design Decisions:**

1. **Frozen Immutability**: BriefModel is immutable (frozen=True) like Document and Finding
2. **Confidence Per Element**: Every extracted element has its own confidence score
3. **Clarification Interrupt**: Low confidence on critical elements stops parsing and asks user
4. **Registry Pattern**: Parsers self-register; adding new formats is a single file
5. **Raw Data Preservation**: Original extracted data stored for debugging
6. **Never Silently Guess**: Messy/ambiguous briefs ask rather than fabricate

**Real Brief Validation (7 briefs):**

| Brief | Format | State | Keywords | Article Type |
|-------|--------|-------|----------|--------------|
| Koifortune AU | xlsx | READY | 23 main | main_review |
| 22Bet Zambia | xlsx | READY | 24 main | main_review |
| App Page Task | docx | NEEDS_CLARIFICATION | 0 (none in brief) | asks |
| Vave bonuses | docx | NEEDS_CLARIFICATION | 41 LSI (clean) | bonus_page |
| Big Bass Splash | docx | NEEDS_CLARIFICATION | 10 main | game_review |
| Boxing LINE | docx | NEEDS_CLARIFICATION | 24 main | sports_market |
| 10-page Ghana | docx | NEEDS_TASK_SELECTION | — | 10 tasks listed |

### KEY LESSON REINFORCED: Real-Brief Validation is Essential

**This phase reported "complete" with passing tests THREE times before real-brief validation proved it correct.** Each pass caught real defects:

1. **First "complete"**: Missing features (multi-task detection, type inference) — 2-brief validation shortcut
2. **Second "complete"**: 6-brief validation found 3 genuine bugs:
   - Multi-task docx detection missing (10-page brief returned NEEDS_CLARIFICATION instead of NEEDS_TASK_SELECTION)
   - Type misclassification (Vave bonuses → game_review instead of bonus_page)
   - Translation-fragment leakage (102 garbage keywords instead of 41 clean)
3. **Third "complete"**: Edge case in translation stripping (`.ITA:` without space)

**Tests prove internal logic; only raw output from hard real cases proves correctness.**

Brief parsing was v3's biggest failure source — this discipline is why v4's is solid.

## Phase 4a Deliverables

### Output Pipeline Core (Complete)

**Files Created:**
- `core/orchestrator.py` - Run all registered checks, aggregate findings (~270 lines)
- `output/apply.py` - Apply auto-fixes with offset management and conflict detection (~450 lines)
- `output/docx_writer.py` - Write Document to .docx with formatting (~200 lines)
- `output/comments.py` - Draft writer comments from proposals (~180 lines)
- `output/summary.py` - Generate run summary report (~180 lines)
- `run_pitboss.py` - Pipeline entry point with CLI (~220 lines)
- `tests/test_orchestrator.py` - 17 orchestrator tests
- `tests/test_apply.py` - 39 apply layer tests (critical)
- `tests/conftest.py` - Test configuration for check registration

**End-to-End Pipeline:**
```
.docx article + brief → run all 9 checks → corrected .docx + comments.md + summary.md
```

**Pipeline Components:**

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| `Orchestrator` | Run all checks | Registry iteration, error isolation, finding aggregation |
| `Apply Layer` | Apply auto-fixes | Descending offset order, conflict detection, formatting preservation |
| `DOCX Writer` | Output corrected doc | Bold/italic/hyperlinks/highlights preserved |
| `Comments` | Draft writer feedback | Proposals grouped by section, markdown export |
| `Summary` | Run statistics | Counts by check, conflicts, errors |

**Critical Apply Layer Design:**

1. **Offset Management**: Sort findings by position DESCENDING (apply last-to-first) so earlier offsets stay valid after edits

2. **Conflict Detection**: When two findings overlap:
   - First finding (earlier start_offset) wins
   - Second finding DOWNGRADED to proposal
   - Conflict pairs tracked in result

3. **Validation**: Original text at location must match finding's `original_text` or finding is skipped

4. **Formatting Preservation**:
   - TextRuns adjusted around edits
   - Formatting inherited from most-overlapping run
   - Hyperlinks preserved via OOXML manipulation

**Real Validation (Koifortune AU article, 2016 words):**

| Metric | Count |
|--------|-------|
| Total findings | 53 |
| Auto-applied | 42 |
| Proposals | 10 |
| Downgraded (conflicts) | 1 |
| Skipped (validation) | 0 |
| Comments drafted | 11 |

**Breakdown by Check:**
- headings: 37 auto-applied (capitalization fixes)
- locale_spelling: 5 auto-applied, 1 downgraded (conflict)
- voice.third_person: 10 proposals (ambiguous contexts)

**CLI Usage:**
```bash
python run_pitboss.py --article article.docx --brief brief.xlsx --brand koifortune
```

**Outputs:**
- `corrected_<filename>.docx` - Document with auto-fixes applied
- `comments.md` - Writer comments from proposals, grouped by section
- `summary.md` - Run statistics with counts per check

### Artifact Verification Bugs (Fixed)

After initial pipeline completion, ran full end-to-end on Koifortune AU article. Artifact inspection found 5 bugs:

| Bug | Severity | Issue | Fix | Status |
|-----|----------|-------|-----|--------|
| Bug 3 | CRITICAL | `locale_spelling` converted verb "check" to noun "cheque" | Ambiguity audit: 10 noun/verb pairs (check/cheque, licence/license, kerb/curb, metre/meter +6) route American→British direction to PROPOSAL; auto-apply bar is "no alternate meaning EXISTS" | **FIXED** |
| Bug 1 | HIGH | DOCX writer flattened lists to paragraphs (102→141 elements) | Create proper `w:numPr` XML with numbering definitions | **FIXED** |
| Bug 2 | HIGH | Yellow highlights lost (16→12, 25% dropped) | Add explicit handling for "run exactly matches edit" case in apply.py | **FIXED** |
| Bug 2b/4 | MEDIUM | No-op edits (original==proposed) damaged run structure | Skip findings where `proposed_text == original_text` | **FIXED** |
| Bug 5 | MEDIUM | Conflict detection lets structural finding block real text edit | Defense-in-depth: `_detect_conflicts` skips no-ops; `blank_line` changed to proposal (structural changes can't auto-apply via text replacement) | **FIXED** |

**Verification Results (Post-Fix):**
```
                    Original    Corrected    Match?
  Headings:               37           37    YES
  Paragraphs:             51           51    YES
  Lists:                  10           10    YES
  Tables:                  4            4    YES
  TOTAL:                 102          102    YES
  Highlights:             16           16    YES
```

**Final Pipeline Output (Koifortune AU, all bugs fixed + config corrected):**

| Category | Count | Details |
|----------|-------|---------|
| **Auto-fixes applied** | **0** | Headings already correct title case — no changes needed |
| **Proposals for review** | **62** | 37 `blank_line`, 9 `capitalization` (brand name edge cases), 10 `voice` (ambiguous), 6 `locale_spelling` (noun/verb pairs) |

The phantom "42 auto-fixes" count is gone. The old 25 auto-fixes were actually BREAKING correct title-case headings by converting them to sentence case (config bug).

**Phase 4a COMPLETE and VERIFIED.** All 5 artifact verification bugs fixed. End-to-end pipeline works: article + brief in → faithfully-corrected .docx + drafted comments out. Document structure preserved exactly (102 elements, 16/16 highlights). Next: Phase 4b (Google Docs integration) or Phase 5 (judgment layer).

## Phase 4b Deliverables

### Google Docs Integration (Stage 3 Complete)

**Files Created:**
- `ingest/gdoc_auth.py` - OAuth flow for Google Docs & Drive APIs (~180 lines)
- `ingest/gdoc_reader.py` - Read Google Doc → Document model (~430 lines)
- `output/gdoc_writer.py` - Write Document → new Google Doc (~300 lines)
- `output/gdoc_comments.py` - Post DraftedComments as Drive comments (~180 lines)
- `scripts/compare_gdoc_docx.py` - Validation script for reader parity (~300 lines)
- `scripts/run_gdoc_pipeline.py` - End-to-end Google Docs pipeline (~200 lines)

**Key Constraint:** Google Docs API CANNOT write native tracked-change suggestions. Workflow is:
1. Create corrected COPY of the document
2. User uses Google Docs "Compare" feature to see diff as redlines
3. Proposals posted as comments for human review

**Pattern:** ADAPTER ONLY — orchestrator, checks, and apply layer unchanged.

**Stage 1: OAuth (Complete)**

- Standard `google-auth-oauthlib` flow
- Scopes: `documents` (read/write) + `drive.file` (comments)
- Token caching in `token.json` (gitignored)
- Tested: Successfully read doc metadata via API

**Stage 2: Reader (Complete)**

`ingest/gdoc_reader.py` reads Google Docs into the same Document model as `docx_reader.py`.

| Element | Google Docs API | Document Model |
|---------|-----------------|----------------|
| Heading | `namedStyleType: HEADING_1` | `Heading(level=H1)` |
| Paragraph | `paragraph.elements` | `Paragraph` |
| List | `bullet.listId` + glyph type | `List` + `ListItem` |
| Table | `tableRows[].tableCells[]` | `Table` |
| Bold/Italic | `textStyle.bold/italic` | `TextRun` |
| Highlight | `backgroundColor.rgbColor` | `TextRun.highlight_color` |
| Hyperlink | `link.url` | `TextRun.hyperlink` |

**Critical Validation (Koifortune article via both readers):**
```
                 DOCX    GDOC    Match?
Headings:          37      37    YES
Paragraphs:        51      51    YES
Lists:             10      10    YES
Tables:             4       4    YES
Highlights:        16      16    YES

Pipeline findings:  86      86    IDENTICAL
  Auto-applicable:   25      25    IDENTICAL
  Proposals:         61      61    IDENTICAL
```

Both readers produce IDENTICAL findings from the same article content.

**Stage 3: Writer + Comments (Complete)**

`output/gdoc_writer.py` creates new Google Doc via two-phase batchUpdate:
1. `documents.create()` - Create empty doc
2. **Phase 1**: Insert all text/headings/lists/table structures (reverse order for index stability)
3. **Phase 2**: Populate table cells after reading back actual indices

**Reverse Insertion Pattern:** Elements inserted from last to first at index 1. Each insertion pushes previous content down, eliminating index calculation errors. Critical for tables where Google's index structure is complex.

**Formatting preserved:**
- Heading levels (H1-H4) via `updateParagraphStyle`
- Bold/italic/underline via `updateTextStyle`
- Highlights via `backgroundColor` RGB
- Hyperlinks via `link.url`
- Lists via `createParagraphBullets`
- **Tables via two-phase insert** (structure first, content second)

**Key Fix: Explicit Style Reset**

When inserting at index 1, content inherits styles from pushed-down content. Fixed by:
- `deleteParagraphBullets` for headings/paragraphs (prevents bullet inheritance from lists)
- `updateParagraphStyle: NORMAL_TEXT` for paragraphs (prevents heading style inheritance)

`output/gdoc_comments.py` posts proposals as Drive API comments:
- Anchored to flagged text via `quotedFileContent`
- Rate-limited batching (10 comments/batch, 1s pause) to avoid Drive API limits
- Structured format: `[SEVERITY] check_name` + issue + suggestion + location

**Full Pipeline Test (Koifortune Google Doc with brand standards):**
```
Source doc:       1O4QTUAtkN9LvGFT7iDregCA-F5R5LKQQZTQ8qVX1xDQ
Title:            Main Page_ Koi Fortune AU
Word count:       ~2,016

Total findings:   62
Auto-fixes:       0   (headings already correct title case)
Proposals:        62
Comments posted:  62 (0 failures)

Corrected doc:    https://docs.google.com/document/d/1JmQhNfC72sKuPbx5nx_9tM0DYpNePq_0VHXM3xZq3qY/edit
```

**Critical Verification (Source vs Corrected):**
```
Element comparison (source -> corrected):
  tables:     4 -> 4   [OK]
  headings:   37 -> 37 [OK]
  paragraphs: 51 -> 51 [OK]
  lists:      10 -> 10 [OK]
  highlights: 16 -> 16 [OK]

All 4 tables preserved with correct cell content.
NO heading changes - source headings are already correct Title Case.
```

**Finding Parity Confirmed:** Google pipeline produces consistent findings with DOCX pipeline when using same brand standards.

**Config Bug Fix (Heading Capitalization):**

Corpus validation revealed `koifortune.yaml` was misconfigured with `sentence_case` when corpus showed 89.5% title case usage (315/352 headings). The 25 "auto-fixes" were converting CORRECT title-case headings INTO incorrect sentence-case.

| Config | Corpus Truth | Pipeline Behavior |
|--------|--------------|-------------------|
| `sentence_case` (wrong) | 89.5% title case | 25 auto-fixes (breaking correct headings) |
| `title_case` (fixed) | 89.5% title case | 0 auto-fixes (headings already correct) |

**Title Case Logic Verified:**
- Minor words stay lowercase: a, an, the, of, to, for, in, on, at, by, with, and, or, but, nor, as, if, so, yet
- First/last words always capitalized
- Test: "how to create an account" → "How to Create an Account" ✓

This is another instance of the KEY LESSON: corpus validation catches config bugs that pass all unit tests.

**Stage 4 (Pending):** Wire into `run_pitboss.py` with `--gdoc` flag.

---
*Last updated: Phase 4b Stage 3 complete — Google Docs read/write/comments + tables working. Koifortune heading config fixed (sentence_case → title_case per corpus). 818 tests passing.*
