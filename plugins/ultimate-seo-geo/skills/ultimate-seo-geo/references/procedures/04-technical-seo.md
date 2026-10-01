> **Progressive disclosure:** Load this file only when the current task maps to this section (see `SKILL.md` §0). Do not load all procedure files for narrow tasks.

## 4. Technical SEO

### Core Web Vitals (INP replaced FID March 2024 — FID removed from CrUX/PSI Sept 2024; Lighthouse never reported FID)

| Metric | Good | Needs Improvement | Poor |
|---|---|---|---|
| **LCP** | < 2.5s | 2.5–4.0s | > 4.0s |
| **INP** | < 200ms | 200–500ms | > 500ms |
| **CLS** | < 0.1 | 0.1–0.25 | > 0.25 |

Measured at the 75th percentile in CrUX field data. Performance matters directly to users and Core Web Vitals; do not claim a fixed AI-citation multiplier from a third-party correlation.

### Technical Audit — Step by Step

1. **Run PageSpeed Insights** on homepage + top 3 pages. Record LCP, INP, CLS. For detailed CWV fix steps (LCP subparts, INP long task debugging, CLS prevention patterns), see `references/technical-checklist.md`.
2. **Check robots.txt** — CSS, JS, and important Search pages not unintentionally blocked. For OpenAI, `OAI-SearchBot` governs automatic ChatGPT Search crawling; `GPTBot` is a separate training-control choice, and `ChatGPT-User` is user-triggered and does not determine Search inclusion. Verify other AI crawler roles against current vendor documentation before changing rules.
3. **Check HTTPS** — Entire site over HTTPS. Mixed-content assets → force HTTPS via 301.
4. **Check canonical signals** — Run `scripts/canonical_checker.py URL` or `--crawl`. Self-referencing canonicals are useful hygiene, especially in Shopify, but canonical is a hint rather than a mandatory ranking tag. Prioritize conflicting targets, broken targets, duplicate URL variants and mismatches with intended indexation.
5. **Check redirect chains** — Chain >1 hop → collapse to direct redirect.
6. **Check orphan pages** — Any indexed page with zero internal links. Flag here; fix in § 9.
7. **Check mobile rendering and usability** — use rendered-page testing and Core Web Vitals. Treat touch/font sizes as accessibility/UX guidance rather than fixed SEO pass/fail thresholds.
8. **Check soft 404s** — Run `scripts/broken_links.py` on key pages; it detects pages returning 200 but showing "not found" in `<title>`. Also check `scripts/sitemap_checker.py` output for soft 404s in sitemap. Fix: return real 404/410 or add genuine content.
9. **Check for broken internal pages** — Run `scripts/internal_links.py` (now reports 404/5xx pages found during crawl) or `scripts/broken_links.py --crawl` for site-wide broken link scan.
10. **Check JavaScript rendering** — Compare raw source to rendered DOM. Google can render JavaScript; other bots differ. Flag a problem only when important content is absent from rendered output or the target crawler demonstrably cannot retrieve it.
11. **Check Open Graph + Twitter Card** — `og:title`, `og:description`, `og:image`, `twitter:card` on all shareable pages.
12. **Check security headers** — HSTS, X-Frame-Options, X-Content-Type-Options. ✅ Pass: `Strict-Transport-Security: max-age=31536000; includeSubDomains`. ❌ Fail: header absent or `max-age=0`.

For the full Critical Technical Issues + Fix Directives table (9 issues with detection methods and fixes), JavaScript SEO December 2025 clarifications (canonical conflicts, noindex behavior, JS-rendered structured data), and the mobile-first indexing note, see `references/technical-checklist.md`.

**Reliability preference**: put critical SEO elements in initial HTML where practical, particularly fast-changing product facts. Google can process JavaScript-generated content and JSON-LD, so JS-only is not automatically an error; verify rendered output and target-crawler behavior.

### What the Rendered Page Calls (network)

A raw-HTML crawl cannot see the requests a page's scripts send. `python scripts/page_network.py https://example.com/ https://example.com/pricing --llms-txt --json` renders each page and records every request. URLs are kept without query strings, and no header value is stored except CORS and content type. It reports two things:
- **Open write endpoints:** a first-party `POST`/`PUT`/`PATCH`/`DELETE` sent with no key to an endpoint that answers any origin. The script checks with the page's own response and one harmless `OPTIONS` preflight, and never sends a `POST` itself. Any website can make that call at the site's cost; on one client site it was an LLM endpoint called from a chat widget. `--llms-txt` probes the API-shaped URLs the site advertises there, and `--endpoint URL` probes one you found in its scripts.
- **Tag load:** the tracking vendors and third-party hosts each page loads. Many third-party scripts can contribute to poor INP, but vendor count alone does not prove causation; use performance traces to identify long tasks and actual cost.

What is *not* a finding: CORS open on a `GET` of public data (Gatsby page-data, a Next.js prefetch, a consent script), a site's own tag-manager proxy (`/_tag/`), and self-hosted analytics ingestion. A widget that calls its endpoint only after a click needs that interaction, which this script does not perform.

### Technical Finding Example

```
Finding: Redirect Chain Detected
Severity: 🟠 High | Confidence: Confirmed

Issue: /old-page → /temp-redirect → /final-destination (2-hop chain)
Every extra hop adds latency and crawl complexity; update controllable internal links to the final URL.

Fix: Update all internal links and any external links you control to point directly to
/final-destination. The redirect map remains as a safety net.
Expected impact: Cleaner internal navigation and less redirect overhead.
```

→ See `references/technical-checklist.md` (detailed CWV fix steps, LCP subparts, IndexNow setup) | Run `scripts/pagespeed.py` Run `scripts/robots_checker.py` Run `scripts/redirect_checker.py` Run `scripts/security_headers.py` Run `scripts/indexnow_checker.py` Run `scripts/broken_links.py --crawl` Run `scripts/sitemap_checker.py --sample 50`

> **Script note**: `pagespeed.py` calls googleapis.com. In proxy-restricted environments it will fail — fallback: ask user to run pagespeed.web.dev and share results, or use the manual CWV checklist in `references/technical-checklist.md`.

