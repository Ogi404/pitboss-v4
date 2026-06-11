# Pitboss v4 — Architecture & Build Plan

## Foundational Premise

This is a ground-up rebuild, not an upgrade. The decision to rebuild comes from a specific failure mode in v3: it treats every editorial check as a question for an LLM, which makes it inconsistent (the core complaint — catches ~60% of real issues but flags unimportant things as critical and misses important ones).

The rebuild is grounded in analysis of real editorial data:
- **270 approved articles** across 17 brands (~353K words) — the gold standard of on-brand output
- **Before/after editing pairs** (writer draft → editor's final) showing what editing actually changes
- **The General Writing Requirements** — the canonical company standard
- **Real briefs** in every format the job actually produces

### The central finding that shapes everything

A diff analysis of editor before/after pairs revealed the breakdown of what editing actually consists of:

| Category | Share of edits | Automatable how |
|---|---|---|
| Voice conversion (3rd → 2nd person) | ~40% | Deterministic + light LLM |
| Structural formatting (blank lines, heading style) | ~25% | Deterministic |
| Brand name normalization | ~10% | Deterministic (lookup) |
| Stop word removal | ~10% | Deterministic (weighted list) |
| Locale spelling | ~5% | Deterministic (dictionary) |
| Article/preposition insertion | ~5% | Light LLM |
| **Genuine judgment (rewrites, restructure, flow)** | **~5%** | **LLM proposal, human decision** |

**95% of editing is specification enforcement. Only ~5% needs genuine editorial judgment.**

v3's mistake was sending the 95% through the LLM along with the 5%, making the reliable part as inconsistent as the hard part. v4's architecture is built around this split: make the 95% deterministic and perfectly consistent, and concentrate LLM effort (and human review) on the 5% that actually needs it.

---

## Design Principles

1. **Deterministic by default.** If a rule can be expressed as code (regex, lookup, dictionary), it is never sent to an LLM. Deterministic checks are 100% consistent across runs — which directly fixes the top complaint.

2. **The Requirements doc and brand corpora are the source of truth.** Rules are loaded once and enforced, never re-derived per run. Brand voice targets come from analyzing approved articles, not from hand-written descriptions.

3. **Edit against exemplars, not against abstract "good writing."** The judgment layer's target is "make this read like the 20-30 approved articles for this brand" — this is the primary defense against robotic, homogenized output.

4. **Surgical restraint.** The judgment layer only acts when it can name a specific, identifiable problem. "Could be marginally smoother" is not a license to edit. A high bar to touch text is what separates an editor from a paraphrasing machine.

5. **Auto-apply the safe 95%, propose the risky 5%.** Deterministic fixes apply as redlines automatically. Rewrites and restructures are proposed with reasoning for human accept/reject. The human stays the editor.

6. **Confidence over silent guessing.** Especially in brief parsing: when the system isn't sure, it asks rather than fabricating.

7. **Weighted severity, not binary flags.** Calibrated from real data — e.g., even approved articles contain "soft" stop words like "unlock" (154×) and "ensure" (131×), so those are weighted far lower than hard-banned words like "delve" or "seamless". This prevents the "flags trivial things as critical" problem.

8. **Built to extend without rebuilding.** v3 needed a full rebuild because a core assumption ("every check is an LLM call") was wired through every component. v4 isolates what varies behind stable contracts so future growth — new brands, article types, brief formats, checks, output targets — is additive, never structural. (See Extensibility section.)

---

## System Architecture

```
pitboss-v4/
├── core/
│   ├── standards_engine.py     # Loads + serves the canonical rules
│   ├── brand_profile.py        # Per-brand config + learned voice model
│   └── document.py             # Unified doc model (paragraphs, headings, sections, positions)
├── ingest/
│   ├── gdoc_reader.py          # Pull article from Google Doc
│   ├── brief_agent.py          # Confidence-scored brief understanding (its own subsystem)
│   └── brief_formats/          # Format-specific parsers (xlsx, docx, sheets)
├── deterministic/              # THE 95% — no LLM, 100% consistent
│   ├── voice.py                # 3rd→2nd person detection + conversion
│   ├── stop_words.py           # Weighted stop-word list (hard/soft tiers)
│   ├── headings.py             # Capitalization, question marks, hierarchy, blank-line spacing
│   ├── brand_names.py          # Normalization (Bet Label → BetLabel)
│   ├── locale_spelling.py      # UK/US/CA/AU/NZ dictionary swaps
│   ├── currency.py             # Format consistency (symbol XOR abbreviation)
│   ├── formatting.py           # Whitespace, list punctuation, UI-element quoting
│   ├── keywords.py             # Keyword counting + density (≤3%) against brief
│   └── structure.py            # Heading hierarchy, paragraph-between-headings rule
├── judgment/                   # THE 5% — narrow, focused LLM calls; proposals only
│   ├── base.py                 # One-issue-per-call discipline; restraint scoring
│   ├── sentence_rewrite.py     # Awkward/overlong sentences → exemplar-matched rewrite
│   ├── paragraph_flow.py       # Redundancy, weak transitions, merge/split
│   ├── section_value.py        # Does this section deliver what its heading promises
│   ├── consistency.py          # Internal fact consistency (bonus amounts, etc.)
│   └── brief_coverage.py       # Does the article cover what the brief requires
├── factcheck/
│   ├── claim_extractor.py      # Article → list of verifiable claims (1 LLM call)
│   ├── router.py               # Maps each claim → page type that can settle it
│   ├── crawler.py              # Interactive Playwright crawl (click-to-reveal), claim-targeted
│   └── verifier.py             # Settles each claim: verified/contradicted/could-not-reach
├── learning/
│   ├── feedback_store.py       # Records accept/reject per finding type per brand
│   └── calibration.py          # Adjusts confidence thresholds from feedback
├── output/
│   ├── redline_builder.py      # Builds corrected Google Doc copy for Compare review
│   ├── comment_builder.py      # Drafts writer comments (missed sections, brief gaps)
│   └── report.py               # Summary surface
├── brands/                     # Per-brand profiles
│   ├── _defaults.yaml          # Company-wide (from General Writing Requirements)
│   ├── vave.yaml
│   ├── hellspin.yaml
│   └── ...
├── corpora/                    # Approved articles per brand (the exemplar bank)
│   ├── vave/
│   ├── hellspin/
│   └── ...
└── app.py                      # Orchestration + local control surface
```

---

## Component 1: Standards Engine

Loads the General Writing Requirements once and serves them as structured, queryable rules. This is the authoritative source — checks query it; they never hardcode or re-derive rules.

Encoded directly from the Requirements doc:

```yaml
# brands/_defaults.yaml (company-wide standard)
voice:
  person: second           # "write for people, by people" + observed 10:1 ratio in corpus
  on_behalf_of: "gambling expert team"

readability:
  max_sentence_words: 25   # "use shorter sentences"; corpus avg is 14-17
  paragraph_sentences: [3, 5]   # "3-5 sentences"
  require_para_between_headings: true

keywords:
  use_all_main: true
  max_density_percent: 3.0
  highlight_color: yellow
  warn_brand_name_overuse: true

currency:
  mode: exclusive          # abbreviation XOR symbol, never both

headings:
  hierarchy: [H1, H2, H3, H4]
  descriptive_required: true        # "Promotions" alone is not acceptable
  # capitalization is brand-specific (see note) — set per brand, not here

forbidden_brands: true     # no other casino/sportsbook names unless in keywords

stop_words:
  hard:    # rarely/never acceptable — weight 1.0
    [delve, "dive into", "dive in", realm, landscape, "state-of-the-art",
     leverage, robust, "cutting-edge", "top-tier", seamless, seamlessly,
     navigating, "treasure trove", galore, "hidden gem", embark, immerse,
     "picture this", "the icing on the cake", "cherry on top", thrilling,
     exhilarating, "top-notch", "at your fingertips"]
  soft:    # tolerated in context — weight 0.3 (corpus contains these in approved work)
     [unlock, selection, ensure, exciting, essential, tailored, elevate,
      cater, premier, destination, maximize, crucial, key, veteran, thrill]
  # "punters" is voice/locale-dependent, handled by voice module not stop-words

prohibited_style:
  - latin_abbreviations: ["e.g.", "i.e.", "etc."]   # "get straight to the point"
  - profanity_mild: [sucks, jerk]
```

**Heading capitalization note:** the corpus shows this is genuinely brand-specific — Koifortune uses sentence case ("Casino games", "In-play markets"), Vave uses title case ("Overview of the Vave Casino App"). So it lives in each brand profile, not the defaults. The data already told us this; the config respects it.

---

## Component 2: Brand Profiles & The Layered Voice Model

Each brand gets a YAML profile that overrides defaults (heading case, currency symbol, market/locale, banned terms specific to the brand) — same inheritance model proven in v3 Phase 5.

### The Layered Voice Model (the anti-robot + anti-brittle mechanism)

A per-brand-from-its-own-corpus model is brittle: new brands appear constantly from affiliate work, many brands have only 3-4 articles, and article types (specific game reviews, sports-market explainers, currency guides) are open-ended and unpredictable. A model that depends on a brand having its own large corpus would break exactly where the business is most fluid.

The voice model is therefore **layered, built from the whole corpus, with graceful fallback**:

**Layer 1 — House voice (global).** Built from ALL approved articles across ALL brands at once. Captures what all editorial output shares regardless of brand: second-person dominance, 14-17 word sentences, short paragraphs, stop-word discipline, conversational-not-robotic register. Applies to a brand-new brand with zero articles on day one. (The Requirements doc is the *rules*; house voice is the *measured reality* of those rules.)

**Layer 2 — Article-type voice.** Built by pooling articles of the same type across all brands — all app reviews together, all bonus pages together, all sports-market explainers together. A boxing-market article for a never-seen brand still learns from dozens of sibling sports-market articles. This is what handles unpredictable future article types: type clusters generalize across brands. The brief's task name usually identifies the type.

**Layer 3 — Brand voice (only when earned).** Activates only when a brand has 10+ articles — enough to be statistically real. Captures brand-specific quirks: heading capitalization, currency symbol, house terms. Below that threshold this layer is skipped; the system leans on Layers 1 and 2. No cold-start failure.

**At edit time the system blends what's available:** always Layer 1, plus Layer 2 if the type is recognized, plus Layer 3 if the brand is well-covered. Brand-new brand + unfamiliar type → solid Layer 1 guidance. Well-covered brand + familiar type → all three layers. It degrades gracefully instead of breaking.

Each layer extracts the same measurable fingerprints: sentence length distribution, paragraph length, second/third person ratio (Vave ~30:1), heading capitalization convention (detected not guessed), common openers/transitions actually used, punctuation/list density, and vocabulary fingerprint including which "stop words" are tolerated in practice.

### Article-type clusters

Task names from the brief map to type clusters. Seeded clusters (the recurring bulk of the work):

`main_review`, `bonus_page` (bonuses/promotions/no-deposit), `app_review` (app/mobile), `game_review` (slots & specific game reviews), `sports_market` (boxing/basketball/racing/etc.), `payments` (banking/deposit/withdrawal), `registration`, `customer_support`, `responsible_gaming`, `vip_loyalty`.

Plus an `unknown/general` fallback that uses house voice only — so an unrecognized type is safe, never broken. New clusters can be added later as pure data (see Extensibility).

### Corpora layout

Same source articles, indexed three ways, all regenerated when new approved articles are dropped in (tagged by brand + type):

```
corpora/
├── _house/voice_model.json          # Layer 1 — all articles
├── _types/<type>/voice_model.json   # Layer 2 — pooled by article type
└── <brand>/voice_model.json         # Layer 3 — only for brands with 10+ articles
```

---

## Component 3: Brief Understanding Agent

Brief parsing was v3's most persistent bug source because it was treated as a side concern. In v4 it's a first-class subsystem with one rule: **never silently guess.**

Pipeline:
1. **Format detection** — xlsx (single/multi-tab, multi-task), docx (inline keywords, key:value tables, structured tables), Google Sheet URL.
2. **Structured extraction** — keywords by group (main/support/LSI) with quantities, headings with word counts, meta specs, target word count, locale/market. (All the format variants already mapped during v3 debugging carry over as known patterns.)
3. **Confidence scoring** — each extracted element gets a confidence. A clean "Main keywords | Quantity" table → high. An ambiguous inline blob → low.
4. **Clarification interrupt** — if any critical element (keywords especially) is below threshold, the tool stops and asks you a specific question ("I found these as keywords but I'm not certain — confirm or correct?") *before* running checks. No fabricated keyword lists, ever.
5. **Task selection** — for multi-task briefs, the detected task list is presented; you pick (handles "Topic:" vs "Task name:" and all the variants already mapped).

---

## Component 4: Deterministic Layer (the 95%)

Every module here is pure code: regex, lookups, dictionaries, counting. Same input → same output, every time. This is what makes v4 consistent where v3 isn't.

**voice.py** — Detects third-person reader references ("players", "users", "bettors", "punters", "customers", "the player") and converts to second person ("you", "your"). Most cases are mechanical. The genuinely ambiguous ones (e.g. "players who deposited before noon" where "you" may not fit, or where "players" means the general population not the reader) are flagged at low confidence for the judgment layer rather than auto-converted. Conversion is proposed as a redline.

**stop_words.py** — Weighted detection against the two-tier list. Hard words flagged prominently; soft words flagged quietly and only above a density threshold (calibrated to corpus — soft words appear in approved work, so a single "unlock" is not an error). Each hit shows the word, surrounding context, and location. This weighting is the direct fix for "flags unimportant things as critical."

**headings.py** — Enforces: descriptive headings (flag bare "Promotions"-type), brand-specific capitalization, no question marks in headings (observed consistent edit: "How to Create an Account?" → "How to Create an Account"), one paragraph minimum between consecutive headings, correct H1→H2→H3→H4 nesting, blank line before headings (the single most common formatting edit observed).

**brand_names.py** — Per-brand normalization table ("Bet Label" → "BetLabel", correct casing). Flags other-brand mentions not present in the keyword list (Requirements §9).

**locale_spelling.py** — Dictionary-based swaps keyed to the brand's market (UK/IN/NG → British; US/PH → American; CA → Canadian; AU; NZ). E.g. "synchronized" → "synchronised" for CA. Uses established word lists, no LLM.

**currency.py** — Detects whether the article mixes symbols and abbreviations (Requirements §11: one or the other, never both) and flags the minority form for normalization.

**formatting.py** — Double spaces, space-before-punctuation, trailing list punctuation consistency, UI element quoting ('Share', 'Add to Home Screen' — an observed edit pattern), Latin abbreviations (e.g./i.e./etc. — prohibited).

**keywords.py** — Counts each brief keyword (exact + variant matching, the dedup logic from v3), checks against required quantities, computes density, flags >3% density and brand-name overuse. Pure counting against the brief agent's output.

**structure.py** — Validates article structure against brief: required sections present, heading hierarchy sound, intro and outro present (Requirements §10: "first and last paragraphs have to stand out").

---

## Component 5: Judgment Layer (the 5%)

This is where the LLM lives, and where the "get close to a human editor" ambition is realized. Strict disciplines:

**One issue per call.** Never "find all problems." Each module makes a focused call about one kind of judgment. This is what fixes inconsistency — a narrow prompt returns stable results; a kitchen-sink prompt returns whatever the model fixates on that run.

**Exemplar grounding.** Every rewrite prompt includes 3-5 relevant passages from the brand's approved corpus as the voice target, plus the brand voice model stats. The instruction is "match this voice," not "improve the writing."

**Restraint scoring.** Before proposing any rewrite, the module must identify a specific, nameable defect with a concrete trigger:
- sentence > 25 words AND ≥ 3 clauses → rewrite candidate
- paragraph semantically duplicates an adjacent one → merge candidate
- section content doesn't deliver the heading's promise → flag
- transition is on the banned-weak list AND no logical bridge present → rewrite candidate

No trigger, no proposal. This bar is what prevents the everything-gets-touched homogenization.

**Proposal, not application.** Output is a proposed redline with the defect named and the reasoning attached. You accept/reject/modify each. The tool never silently rewrites judgment-level content.

Modules:
- **sentence_rewrite.py** — overlong/awkward/passive sentences → exemplar-matched rewrite proposal
- **paragraph_flow.py** — redundancy, weak transitions, merge/split proposals
- **section_value.py** — flags sections that don't earn their place or don't match their heading (the hardest, weakest area — honest about this: flag + first-draft suggestion, your judgment decides)
- **consistency.py** — internal fact consistency (bonus amounts/wagering/dates consistent across the article) — high value, the kind of thing that's tedious for humans
- **brief_coverage.py** — does the article cover what the brief requires; missing required subtopics → writer comment

**Honest calibration of this layer:** sentence rewrites against exemplars will be genuinely good. Consistency checking will be excellent (tedious for humans, easy to make reliable). Section-value and argument-tightening will be the weakest — useful as flags and first drafts, but this is the ~5% where your judgment stays essential and the tool assists rather than replaces.

---

## Component 6: Fact-Checker (claim-driven verification)

The fundamental reframe from both predecessors: **don't extract the site, verify the claims.** v3's crawler tried to extract site content wholesale and compare (grabbed too little, mostly surface text). Sheldon pretends to read the site and hallucinates verification from training data (confident but fictional). Both are the wrong frame.

### Claim-driven pipeline

1. **Extract claims from the article.** One LLM call — the model is genuinely reliable at this. Pull every verifiable factual assertion: bonus amounts ("100% up to €500"), wagering ("35x"), min deposits, licence ("Curaçao"), named providers ("Pragmatic Play, NetEnt"), support channels ("24/7 live chat"), VIP tiers, payment methods, game/library claims ("5,000+ slots", named example titles).

2. **Route each claim to the page type that can settle it.** A bonus claim → bonus/promotions + T&C pages. A licence claim → footer/about. A provider claim → providers/games page.

3. **Crawl only the pages needed** to settle the extracted claims. Not the whole site — just what the article actually asserts. The interactive crawler clicks to reveal content (accordions, tabs, "read more", T&C modals), dismisses cookie/geo modals, and routes through allowed regions (the VPN/geo handling worked out in v3 — operator sites geo-block from some regions).

4. **Settle each claim:** `verified` / `contradicted` / `could-not-reach` — with source URL and quote for the first two. Deterministic string-matching settles most claims (free); only fuzzy matches need an LLM.

5. **Output:** contradictions become writer comments; could-not-reach claims are surfaced explicitly as "unverified — check manually." Never silently passed, never falsely confirmed. This explicit gap-flagging is the core discipline and the opposite of Sheldon's failure mode — you always know what was actually checked.

### Honest difficulty tiers (sets realistic expectations per claim type)

- **Tier 1 — reliable:** licence, responsible gambling, customer support. Static footer/page text. Near-perfect extraction.
- **Tier 2 — achievable, the core engineering:** bonuses, terms, payments, VIP. Content hidden behind accordions/tabs/modals — interactive crawl gets ~70-85% on common site patterns, gaps on unusual ones. Most verification value concentrates here.
- **Tier 3 — inherent ceiling, best-effort:** games/slots libraries (lazy-loaded, infinite-scroll — cannot reliably enumerate), providers (often logo grids with names only in alt-text), sportsbook markets (JS-heavy, sometimes geo-gated). Key insight: the article rarely claims an exact count needing unit-verification — it claims "5,000+ slots" and names examples. So verify "library exists + named examples present" rather than attempting full enumeration.

### Why this is Phase 7 (last)

Not because it's unimportant — it's the stated biggest pain point — but because it has an inherent reliability ceiling while the editor does not. The editor is reliable daily automation; fact-checking is "strong assistant that flags its own gaps." Build the part that will be excellent first, then the part that is genuinely-useful-but-bounded. Cost stays in low cents per article: one extraction call + mostly deterministic matching.

---

## Component 7: Learning Loop

Every finding you accept, reject, or modify is recorded against its type and brand. Over time:
- Finding types you consistently reject get their confidence lowered (eventually suppressed) for that brand
- Rewrite proposals you heavily modify feed back as signal that the exemplar match is off
- Accepted edits can be added to the approved corpus, strengthening the voice model

This is what turns a static tool into one that converges on *your* editorial judgment. It directly attacks the "flags unimportant stuff" problem: if you keep rejecting a category, it learns to stop.

---

## Component 8: Output & Review Surface

The workflow: **brief + Google Doc → tool → (redline copy + drafted comments) → your review.**

**Redline via Compare.** The Google Docs API can't write native suggestions (confirmed limitation in v3). So the tool creates a corrected *copy* of the Doc with all deterministic fixes and accepted-style rewrites applied, and you use Google Docs' built-in **Compare documents** feature to generate a full tracked-changes redline against the original. You accept/reject each change in the native Docs UI you already use. This handles both the auto-fixes and the proposed rewrites as reviewable suggestions.

**Writer comments.** Missed required sections, brief mismatches, factual problems, and major rewrites the writer should own become drafted Google Docs comments (Drive API, as in v3), anchored to the relevant text. You review and post.

**Summary surface.** A local view showing what was changed deterministically, what's proposed for judgment review, and what went to writer comments — with the learning-loop accept/reject controls.

---

## Extensibility — Leaving the Door Open

The goal: v4 is the last rebuild. Every change in the realm of "more brands, more article types, more brief formats, more checks, different output" must be additive, not structural. This is achieved by freezing three contracts and using registry + adapter patterns everywhere else.

### The three frozen contracts

Everything else can change as long as these hold:

1. **The Document model** (`core/document.py`) — the internal representation of an article: paragraphs, headings (with level), sections, lists, tables, and character positions for redlining. Designed generous from day one so a future check finds the structural detail it needs already present.

2. **The Finding object** — what every check returns, regardless of type:
   ```
   Finding(
     check_name, category, severity, confidence,
     location,            # section + paragraph + char range
     original_text,
     proposed_text,       # None for comment-only findings
     reasoning,           # human-readable why
     auto_applicable,     # True for deterministic, False for judgment
   )
   ```
   Every downstream consumer — redline builder, comment builder, report, learning loop — speaks only Finding. Add a hundred new checks and nothing downstream changes.

3. **The check interface** — every check is `run(Document, Standards, VoiceModel) -> list[Finding]`. A new check is a new file satisfying this signature. The orchestrator discovers registered checks; it never hardcodes a list.

### Registry + adapter pattern

- **Checks self-register.** Dropping a file in `deterministic/` or `judgment/` that registers itself makes it run. The orchestrator iterates the registry. No central edit.
- **Brief parsers self-register** in `brief_formats/`. A new format = one new parser file.
- **The edges are adapters.** Ingestion (where briefs and docs come from) and output (where redlines and comments go) are swappable adapters behind interfaces. Google Docs today; if WordPress or another CMS becomes a target, that's a new output adapter, core untouched.

### What future changes actually cost

| Future change | Cost |
|---|---|
| New article type | Tag articles, rebuild voice models. **Data, no code.** |
| New brand | Profile YAML + articles. **Data, no code.** |
| New stop word / rule tweak | Edit YAML. **Config, no code.** |
| New brief format | One parser file in `brief_formats/`. **Self-registers.** |
| New check (deterministic or judgment) | One module satisfying the interface. **Self-registers.** |
| New output target (CMS, etc.) | One output adapter. **Core untouched.** |
| New/swapped LLM model | Config change. **One line.** |

### Schema versioning

Voice models, brand profiles, and the feedback store carry a schema version. When a schema evolves, old artifacts still load (with migration or safe defaults) so accumulated data and corpora are never invalidated by an upgrade.

### The honest caveat

Doors not anticipated at all can still require structural work. If v4 were ever asked to *write articles from scratch* rather than edit them, that's a fundamentally different job that no foresight fully prepares for. But every change within the actual business reality — more checks, brands, types, formats, output destinations — is additive by design. That door is guaranteed open.

---

## Build Sequence

Each phase is independently testable and usable. The editor is the core; fact-check and learning come after it works.

1. **Phase 0 — Core scaffolding.** Document model, standards engine, brand profile loader with inheritance. Encode the General Writing Requirements into `_defaults.yaml`. Build one real brand profile (Vave) by hand to validate the schema.

2. **Phase 1 — Layered voice model builder.** Offline analysis of the whole corpus → `_house`, `_types/<type>`, and `<brand>` (10+ only) voice models. Validate against measured stats (house second-person dominance, 14-17w sentences; Vave ~30:1). Article-type tagging of the existing corpus.

3. **Phase 2 — Deterministic layer.** All nine modules. This delivers the consistent 95% and is independently valuable immediately. Test each module against the before/after pairs — the tool's output should match the human editor's actual changes.

4. **Phase 3 — Brief agent.** Confidence-scored extraction + clarification interrupts + task selection + article-type detection (maps task name → type cluster for voice-model selection). Test against every brief format in the repo.

5. **Phase 4 — Output/redline.** Google Doc read, corrected-copy generation, Compare-based review, comment drafting. End-to-end usable editor at this point.

6. **Phase 5 — Judgment layer.** One module at a time, exemplar-grounded, restraint-scored, proposals only. Start with consistency.py (highest value, most reliable), then sentence_rewrite.py, then the harder flow/section modules.

7. **Phase 6 — Learning loop.** Feedback store + calibration. Turns it into a system that converges on your judgment.

8. **Phase 7 — Fact-checker.** Claim-driven: extractor → router → interactive crawler → verifier, with explicit could-not-reach flagging. Build Tier 1 verification first (reliable), then Tier 2 (the interaction engineering), Tier 3 best-effort. The strong, honest, gap-aware add-on.

---

## Validation Method

The before/after pairs are the test harness. For each writer-draft → editor-final pair:
- Run the draft through v4
- Compare v4's changes to the human editor's actual changes
- **Precision:** of v4's changes, how many match what the human did? (low precision = noise = the v3 problem)
- **Recall:** of the human's changes, how many did v4 catch? (low recall = misses important stuff = the v3 problem)

Target for the deterministic layer: near-100% precision (it should never propose a change the rules don't support) and high recall on the mechanical categories. The judgment layer is measured separately and held to a lower, honest bar.

This gives an objective, data-grounded measure of "how close to a human editor" — the exact question that started this rebuild.
