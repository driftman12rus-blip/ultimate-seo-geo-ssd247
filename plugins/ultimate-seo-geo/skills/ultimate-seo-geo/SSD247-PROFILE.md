# SSD247 SEO/GEO Profile

This fork is the SSD247-specific layer on top of Ultimate SEO + GEO. These rules override generic heuristics elsewhere in the repository whenever SSD247 is being audited.

## Store context

- Platform: Shopify
- Theme family: Xtra
- Site type: e-commerce electronics / computer components
- Audit mode: Internal Mode
- Main page types: Homepage, Collection, Product, Brand, Policy / trust pages
- Product and collection templates must be evaluated separately; do not infer site-wide quality from the homepage alone.

## Override rules

### 1. Evidence beats heuristic thresholds

Do not convert arbitrary word-count or percentage thresholds into SEO defects.

- No minimum 150-word requirement for product descriptions.
- No minimum 200–300-word requirement for collection/category pages.
- No 30%, 40%, or similar content-uniqueness percentage may by itself create a Critical, High, or Warning finding.
- Word count, boilerplate ratio, and measured uniqueness may be reported as descriptive diagnostics only.
- Escalate only when there is concrete evidence such as duplicate intent, duplicate metadata, substantially duplicate pages, poor indexation, cannibalization, crawl waste, policy violations, or Search Console evidence.

### 2. Faceted navigation

Do not apply blanket rules to Shopify filter URLs.

- Do not automatically `noindex` a filter because it contains fewer than a fixed number of products.
- Do not state that faceted URLs must never be blocked in `robots.txt`.
- Do not canonicalize every filtered URL to the parent collection by default.
- Decide crawl/index/canonical treatment per URL pattern using search demand, crawl behavior, duplication, indexation, internal linking, and the intended landing-page strategy.
- `robots.txt` can be appropriate when the goal is to prevent crawling of low-value faceted spaces.
- `noindex` requires the URL to remain crawlable long enough for the directive to be seen.
- Canonical is for true duplicate or near-duplicate consolidation, not a substitute for an indexation strategy.

Any robots.txt, noindex, canonical, redirect, hreflang, or bulk-template change remains High-Risk and requires explicit approval before implementation.

### 3. Returns and shipping structured data

SSD247 has already implemented the store's return and shipping information. Do not raise a generic finding merely because a Product object does not repeat the same policy inline.

Report a return/shipping issue only when validation shows an actual defect, for example:

- invalid or malformed structured data;
- required fields missing from the implementation that is actually in use;
- visible policy and structured data contradict each other;
- product-level exception contradicts the store-level policy;
- Merchant Center / Shopify / structured-data values are materially inconsistent.

### 4. Product data consistency

For product pages, prioritize consistency among the visible Shopify page, structured data, Shopify product data, and any Merchant Center feed.

Check where available:

- SKU / Variant SKU;
- GTIN / EAN;
- MPN / model;
- brand;
- condition;
- availability;
- price and currency;
- product category;
- canonical URL.

Do not guess missing technical specifications.

### 5. Crawl strategy for SSD247

A seed-URL audit is not considered a complete SSD247 audit.

For broad audits:

1. inspect sitemap structure;
2. crawl a representative set of Product, Collection, Brand, Homepage, and Policy pages;
3. use deep crawl when link/canonical/faceted-navigation coverage is required;
4. state crawl limits and unmeasured areas;
5. use GSC evidence for indexation, queries, CTR, cannibalization, and traffic-impact prioritization when available.

### 6. Shopify implementation guidance

Generic findings must be translated into Shopify/Xtra implementation language before execution. A recommendation such as "edit the page template" is not complete until the relevant Shopify surface is identified (theme template/section, product data, collection data, navigation, metafield, structured-data snippet, Shopify setting, or app output).

### 7. Titles, descriptions and headings

Do not turn SERP-display heuristics into SEO defects.

- A missing or misleading `<title>` is a real on-page issue.
- Title character counts such as 50–60 or 60–65 are display heuristics only. Google title links are not governed by a fixed character limit.
- A missing meta description is an optimization opportunity, not a ranking failure; Google can generate snippets from page content.
- There is no fixed meta-description character limit. Length may be reported as a snippet/display note only.
- Multiple H1 elements are not, by themselves, a Google SEO error. Evaluate whether the main visual/page heading is clear and whether heading semantics are sensible for accessibility and users.
- Do not require exact H1→H2→H3 ordering for Google rankings; treat heading order as accessibility/content-structure guidance.

### 8. Images

- Do not require WebP. JPEG, PNG, WebP and AVIF are all valid supported formats; optimize actual bytes, dimensions and delivery rather than file extension alone.
- On Shopify/CDN URLs, the extension does not prove the transferred format because content negotiation/transformation may serve a different format.
- Do not use an arbitrary 10–125 character alt-text rule. Alt text should be useful, concise and contextual for meaningful images; decorative images should use `alt=""`.
- Missing alt attributes, lazy-loading of a confirmed LCP image, and measured CLS/image-size problems remain actionable.
- `srcset`, `sizes`, width/height attributes and fetchpriority are implementation tools, not universal requirements; flag only when the observed delivery/layout makes them relevant.

### 9. Duplicate content and canonicals

- Do not use the phrase "duplicate content penalty" for normal same-site duplication.
- Text-similarity percentages (including 85%) are triage signals, not proof that pages should be merged, noindexed or canonicalized.
- Non-self canonicals and multiple URLs sharing a canonical can be intentional. Escalate only when the canonical conflicts with intended indexation or Google/GSC behavior.
- A canonical hint is not mandatory for Google to index a page, though self-referencing canonicals are useful hygiene on Shopify indexable pages.
- Do not combine a robots.txt block with a new `noindex` recommendation for the same URL pattern: Google must be able to crawl a URL to see `noindex`.

### 10. GEO / AI-search evidence standard

Treat GEO optimization as an experimental layer, not as a set of Google ranking requirements.

- Do not require an answer in the first 40–60 words.
- Do not require 134–167-word answer blocks.
- Do not require Reddit, YouTube, Wikipedia, Wikidata, author bylines or publication dates on product/collection pages.
- Do not present exact citation multipliers, correlations, passage-length "sweet spots", freshness multipliers, or channel-presence percentages as guaranteed effects.
- Citability, passage structure, brand/entity presence and AI-crawler access may be measured and tested, but they must be labeled as diagnostics/experiments unless backed by platform documentation for the exact behavior claimed.
- A GEO score is an internal comparison metric, not a Google/ChatGPT/Perplexity score and not a ranking probability.
- For SSD247, prioritize product facts, price/availability consistency, crawlability, indexation, useful comparisons/specifications and measurable AI citation sampling over generic publishing heuristics.

### 11. Prioritization

Do not prioritize work only because it lowers the repository's internal Health Score. Separate findings into:

- search/indexation impact;
- Merchant Center / structured-data eligibility;
- user/performance/accessibility impact;
- GEO experiment;
- hygiene / informational.

Security headers, Open Graph/Twitter metadata, IndexNow support, exact text lengths, social-platform presence and similar hygiene items must not be described as Google ranking factors unless there is direct evidence for that claim.

## Precedence

When this file conflicts with a generic rule in `AGENTS.md`, `SKILL.md`, `references/`, or a script's narrative recommendation, this SSD247 profile wins. Keep upstream diagnostic capabilities where useful, but do not restore the excluded heuristic thresholds during upstream sync.
