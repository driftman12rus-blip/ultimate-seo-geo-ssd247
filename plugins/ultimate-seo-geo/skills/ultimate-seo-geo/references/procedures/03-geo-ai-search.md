> **Progressive disclosure:** Load this file only when the current task maps to this section (see `SKILL.md` §0). Do not load all procedure files for narrow tasks.

## 3. GEO — AI Search Visibility

GEO = getting content cited by AI engines: Google AI Overviews, AI Mode, ChatGPT Search, Perplexity.

### GEO Quick Check

Treat GEO as an experimental visibility layer. Do not fail a page because it misses a study-derived writing pattern.

| Check | What to verify | Interpretation |
|---|---|---|
| AI search crawler access | OAI-SearchBot and other target-engine search crawlers can reach intended public pages | A documented technical prerequisite for that engine's own crawling/search surface where applicable |
| Product/page facts | Important facts are visible, accurate, consistent and easy to extract | High value for SSD247; verify against visible content, structured data and feeds |
| Renderability | Important content is present in rendered HTML; initial HTML is preferred when practical | Google can render JavaScript; other crawlers may differ, so test the actual target engine |
| Answer clarity | Informational pages answer the user's question clearly and without unnecessary preamble | No fixed 40–60-word or passage-length requirement |
| Measured citations | Repeated prompt sampling shows whether SSD247 is cited and whether facts are correct | Use repeated runs; a single answer is anecdotal |

No item above creates a GEO "penalty" by itself. Product and collection pages do not require author bylines, publication dates, Reddit, YouTube, Wikipedia or Wikidata presence.

### GEO Audit — Step by Step

1. **Check AI crawler access** — Fetch `/robots.txt`. For ChatGPT Search, the relevant OpenAI crawler is **OAI-SearchBot**. `GPTBot` is for potential training use and can be blocked independently; `ChatGPT-User` is user-triggered and does not determine Search inclusion. For other engines, verify their current official crawler documentation before changing rules. Firewall/CDN refusals should be confirmed in real logs before recommending allowlists.
2. **Check llms.txt only as optional hygiene** — Do not score its absence and do not claim Google Search benefit. Use it only where a target non-Google system documents or demonstrably consumes it.
3. **Assess citability as a hypothesis, not a threshold test** — Clear, self-contained facts, useful specifications, comparisons and direct answers can make extraction easier. The bundled `citability_checker.py` reports structural diagnostics such as long prose blocks and paragraph shape; its score is internal and not weighted into the SSD247 decision unless repeated citation tests support the hypothesis. Do not require 134–167 words, a first-60-words answer, question headings, or a single H1.
4. **Check rendering** — Compare raw and rendered HTML. Google can render JavaScript, including JSON-LD; server-side/initial HTML can still improve reliability and helps bots that do not execute JavaScript. Report an actual visibility gap only when the important content is absent from the rendered page or the target crawler cannot access it.
5. **Skip publisher-only features on SSD247** — Preferred Sources, publication-date tactics, news schema and similar publisher features are not SSD247 requirements.
6. **Audit brand/entity facts only where useful** — Check whether AI answers confuse SSD247 with another entity or state wrong facts. Third-party profiles can help users and entity disambiguation, but missing Reddit/YouTube/Wikipedia/Wikidata is not an SEO defect and should not be auto-prioritized.
7. **Measure citation presence** — Use a fixed prompt set and repeated runs per engine. Record citations and factual correctness. Confidence intervals are useful for avoiding conclusions from a single run; do not turn any external study's percentages into expected uplift for SSD247.
8. **Report GEO as an experimental dashboard** — Separate documented access/indexation prerequisites from content hypotheses and measured citation outcomes. Any numeric GEO score is an internal comparison metric, not a score issued by Google, OpenAI, Perplexity or another platform.

### SSD247 GEO priorities

For this store, prioritize: correct product identity (model/SKU/GTIN/brand), price and availability consistency, useful specifications and comparisons, crawl/indexation health, rendered visibility, and repeated citation/fact testing. Treat stylistic patterns and third-party-channel correlations as optional experiments.

### GEO Finding Example

A valid High finding needs direct evidence, for example: OAI-SearchBot is intentionally blocked while ChatGPT Search visibility is a stated goal, or repeated citation samples consistently state the wrong SSD247 product fact. A page merely lacking a 148-word answer block is not a High finding.

### robots.txt: GEO vs traditional crawl directives

- **GEO guidance applies to AI-named crawlers** (e.g. OAI-SearchBot, Claude-SearchBot, PerplexityBot, GPTBot, ClaudeBot) and to `User-agent: *` rules that effectively block them from important content.
- **Do not** recommend removing **Googlebot/Bingbot** `Disallow` rules used for facets (`/*?`), filtered URLs, pagination, category/author paths, or other intentional crawl hygiene **unless** the user explicitly asks for a crawl-budget or indexation review of those rules.
- `robots_checker.py` focuses on AI crawler status; it does **not** flag facet or low-value-path disallows as errors — do not over-generalize GEO fixes into “remove all Disallow.”

### GEO Finding Example

```
Finding: Key answer buried below fold — target query not answered in first 30% of content
Evidence: "How does [product] work" answered in paragraph 6, ~800 words in.
           44.2% of AI citations come from first 30% of content — this page fails.
Impact: Low AI Overview and Perplexity citation rate for the site's core query.
Fix: Move the direct answer to the opening paragraph. Keep detail further down.
Confidence: Confirmed | Severity: 🟠 High
```

### Citation Demonstration (Evaluator-Optimizer Pattern)

When auditing a page's citation potential, always produce a **before/after citation demonstration** — not just a score. Show the user what an AI-quotable passage from their content would look like:

```
CURRENT (not citable — 340 words, no direct answer in first 30%)
  "Psilocybin has been the subject of considerable scientific investigation in recent
  years, with researchers from leading institutions exploring its..."

REWRITTEN (citable — 148 words, direct answer in first sentence, source attributed)
  "Psilocybin produces psychedelic effects by binding to serotonin 5-HT2A receptors
  in the brain, temporarily altering perception and cognition (Johns Hopkins Center
  for Psychedelic Research, 2024). Effects last 4–6 hours at typical doses of
  10–30 mg. A 2023 JAMA Psychiatry meta-analysis of 11 RCTs found response rates
  of 57–80% for treatment-resistant depression."

WHY IT'S CITABLE: Self-contained (148 words, within 134–167 target), direct answer
first, specific numeric stat, dated institutional source — exactly what AI systems
prefer for citation inclusion.
```

This concrete demonstration is more actionable than a score alone. Adapted from Anthropic's [Citations cookbook](https://github.com/anthropics/claude-cookbooks/blob/main/misc/using_citations.ipynb) pattern of showing source attribution in structured output.

→ See `references/ai-search-geo.md` (full platform data, brand correlation, Wikipedia/Wikidata setup, Passage Indexing, Princeton GEO research techniques, content type citation share, AI monitoring tools, platform source selection factors) | See `references/entity-optimization.md` (47-signal entity checklist, AI Entity Resolution Test, Knowledge Graph guide) | Run `scripts/robots_checker.py` Run `scripts/entity_checker.py` Run `scripts/llms_txt_checker.py` Run `scripts/social_meta.py`

