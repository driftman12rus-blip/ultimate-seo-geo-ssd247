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

## Precedence

When this file conflicts with a generic rule in `AGENTS.md`, `SKILL.md`, `references/`, or a script's narrative recommendation, this SSD247 profile wins. Keep upstream diagnostic capabilities where useful, but do not restore the excluded heuristic thresholds during upstream sync.
