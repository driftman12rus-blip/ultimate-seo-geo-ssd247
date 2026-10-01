> **Progressive disclosure:** Load this file only when the current task maps to this section (see `SKILL.md` §0). Do not load all procedure files for narrow tasks.

## 24. E-commerce SEO

### Detect E-commerce Signals

Before running e-commerce–specific checks, confirm the site is actually an e-commerce property:

| Signal | Detection Method |
|--------|-----------------|
| Product schema | JSON-LD with `@type: "Product"` |
| Add-to-cart buttons | Elements with text/aria matching "add to cart", "buy now", "add to bag" |
| Product URL patterns | `/products/`, `/shop/`, `/p/`, `/item/`, `/dp/` in URL paths |
| Pricing elements | `<meta itemprop="price">`, `.price`, `data-price` attributes |
| Cart/checkout pages | `/cart`, `/checkout`, `/basket` paths |
| E-commerce platform markers | Shopify `cdn.shopify.com`, WooCommerce `wc-`, Magento `mage-` |

If ≥2 signals present → classify as e-commerce and run full e-commerce audit.

---

### E-commerce SEO Audit — Step by Step

#### Step 1: Validate Product Schema

Every product page needs complete `Product + Offer` schema. Required fields:

| Property | Required | Notes |
|----------|----------|-------|
| `name` | ✅ | Product title |
| `description` | ✅ | Unique description (not manufacturer copy) |
| `image` | ✅ | At least one product image URL |
| `offers` | ✅ | Must contain Offer or AggregateOffer |
| `brand` | ✅ | Brand name or Organization |
| `sku` / `gtin` / `mpn` | ✅ (at least one) | Product identifier — Google requires at least one |

#### Step 2: Validate Offer Schema

Within `offers`, check:

| Property | Required | Notes |
|----------|----------|-------|
| `@type` | ✅ | `Offer` or `AggregateOffer` |
| `price` | ✅ | Numeric value |
| `priceCurrency` | ✅ | ISO 4217 (USD, EUR, GBP) |
| `availability` | ✅ | Must use schema.org ItemAvailability values |
| `url` | ✅ | Canonical product URL |
| `priceValidUntil` | Recommended | Enables price drop appearance in search |
| `seller` | Recommended | Organization or Person |

#### Step 3: Check Return and Shipping Structured Data

**MerchantReturnPolicy** — validate the implementation that is actually in use. Do not require the same store-wide policy to be repeated inside every Product object when it is already provided correctly at store/organization level or through the relevant commerce integration.

| Property | Required | Notes |
|----------|----------|-------|
| `@type` | ✅ | `MerchantReturnPolicy` |
| `returnPolicyCountry` | ✅ | ISO 3166-1 alpha-2 country code |
| `returnPolicyCategory` | ✅ | `MerchantReturnFiniteReturnWindow`, `MerchantReturnNotPermitted`, etc. |
| `merchantReturnDays` | Conditional | Required if finite return window |
| `returnMethod` | Recommended | `ReturnByMail`, `ReturnInStore`, etc. |

**OfferShippingDetails** — validate when product-level shipping markup is present or intentionally used. Do not create a generic defect solely because shipping details are not repeated on every Product object.

| Property | Required | Notes |
|----------|----------|-------|
| `@type` | ✅ | `OfferShippingDetails` |
| `shippingRate` | ✅ | MonetaryAmount with value + currency |
| `deliveryTime` | ✅ | ShippingDeliveryTime with handling/transit days |
| `shippingDestination` | ✅ | DefinedRegion with addressCountry |

**LoyaltyProgram** (if store has loyalty/rewards program):

| Property | Required | Notes |
|----------|----------|-------|
| `@type` | ✅ | `LoyaltyProgram` |
| `name` | ✅ | Program name |
| `membershipPointsEarned` | Recommended | Points per purchase |

#### Step 4: EU-Specific Requirements

**Energy Labeling Migration:**
- `EnergyConsumptionDetails` → migrated to `Certification` (April 2025)
- Products requiring EU energy labels must use `Certification` schema with `certificationAuthority` and `certificationRating`
- Old `EnergyConsumptionDetails` is deprecated — flag for migration

**IPTC AI Image Labeling:**
- EU AI Act transparency requirements for AI-generated product images
- Check for IPTC metadata in product images indicating AI generation
- If product images are AI-generated, disclosure metadata should be present

**UCP (Unfair Commercial Practices) Compliance:**
- Fake urgency signals ("Only 2 left!" without real inventory data)
- Fake reviews or undisclosed incentivized reviews
- Hidden costs revealed only at checkout
- Pre-ticked consent boxes

#### Step 5: Category Page Optimization

| Check | Pass | Fail |
|-------|------|------|
| Schema type | `CollectionPage` or `ItemList` | `Product` schema on category page |
| Breadcrumbs | `BreadcrumbList` present with correct hierarchy | Missing or flat |
| Faceted navigation | Filtered views canonicalized to primary category | Each filter combo = unique indexable URL |
| Low-value filters | Treatment based on demand, duplication, crawl/index evidence and landing-page intent | Blanket threshold-based indexing rules |
| Pagination | Pages accessible via links (crawl hints) | Orphaned paginated pages |
| Category content | Useful category-specific content where it adds value | Content added only to satisfy an arbitrary word count |

**Faceted Navigation Rules:**
- Primary category page = canonical for all filter variations
- Allow crawling of high-value filter pages (popular brands, key attributes)
- Do not use a fixed product-count threshold to decide indexation.
- `robots.txt`, `noindex`, canonicalization, or allowing indexation can each be appropriate depending on crawl demand, duplication, search intent, and landing-page strategy. Remember that a `noindex` directive must be crawlable to be seen.
- `rel=next/prev` deprecated by Google but still useful as crawl hints for Bing and others

#### Step 6: Product Page Optimization

| Check | Requirement | Impact |
|-------|-------------|--------|
| Product description | Useful, accurate content that distinguishes the product where needed; no fixed word minimum | Duplicate intent/content problems should be evidenced, not inferred from length alone |
| Review markup | `AggregateRating` only with real customer reviews | Google policy violation if fake or imported reviews |
| Price signals | `priceValidUntil` set, `hasMerchantReturnPolicy` linked | Enables price drop rich results |
| Product category | `Product.category` present | Added to merchant listing docs July 7, 2026 — accepts **Text** *or* **CategoryCode**; align with the Google Merchant Center feed spec so feed and markup agree |
| Sale duration | Sale prices carry `priceSpecification` with `validFrom` / `validThrough` | Added July 7, 2026 — an open-ended sale price with no end date cannot be shown as a time-bound sale |
| Product images | Multiple angles, WebP format, alt text with product name | Image search traffic, AI citation likelihood |
| Internal linking | Link to related products, parent category, buying guides | Distributes link equity, improves crawl |

**Review Markup Policy (Google, enforced):**
- Only mark up reviews collected on your own site
- Third-party review aggregation (imported from Amazon, etc.) is NOT allowed in schema
- `AggregateRating` requires actual `reviewCount` and `ratingValue` from real reviews
- **Fake and undisclosed incentivized reviews are barred outright** (review snippet guideline, added July 24, 2026). This is a **global Google Search guideline**, not only an EU UCP matter — it applies wherever the site operates. Two prohibited cases:
  - Reviews not based on genuine experience of the product or service
  - Reviews given in exchange for money, discounts, vouchers or free products **without clear and prominent disclosure**
- The rule covers **both the visible page and the structured data** — disclosure buried in the markup while the page shows an unqualified rating still fails
- Incentivised reviews are permitted *when disclosed clearly and prominently*. The defect is the missing disclosure, not the incentive — do not tell a client to delete a compliant incentivised-review programme

**Sale pricing (July 7, 2026 guidance)** — a sale price needs its effective range stated, otherwise
it is just a price. Use a nested `priceSpecification`:

```json
{
  "@type": "Offer",
  "price": "24.99",
  "priceCurrency": "USD",
  "priceValidUntil": "2026-12-31",
  "priceSpecification": {
    "@type": "UnitPriceSpecification",
    "priceType": "https://schema.org/SalePrice",
    "price": "24.99",
    "priceCurrency": "USD",
    "validFrom": "2026-08-01",
    "validThrough": "2026-08-31"
  }
}
```

`Product.category` accepts either a free-text path or a `CategoryCode`. Whichever is used, it must
match what the Merchant Center feed sends — a feed and markup that disagree on category is a
consistency defect, not two independent signals.

#### Step 7: Inventory & Availability Signals

**Schema Availability Values:**

| Value | When to Use |
|-------|-------------|
| `https://schema.org/InStock` | Available for purchase |
| `https://schema.org/OutOfStock` | Temporarily unavailable |
| `https://schema.org/PreOrder` | Not yet released, can pre-order |
| `https://schema.org/BackOrder` | Available but ships later |
| `https://schema.org/Discontinued` | Permanently unavailable |
| `https://schema.org/LimitedAvailability` | Low stock |

**Handling Out-of-Stock Products:**
- **Never** return 404 for product pages — destroys link equity and causes poor UX
- Keep page live with `OutOfStock` availability
- Show "back in stock" notification signup
- Link to alternatives or successor products
- If permanently discontinued: keep page with `Discontinued` schema, 301 to successor product or parent category after 6+ months with no traffic

**Handling Product Removal:**
- Product replaced by new version → 301 redirect to successor
- Product category discontinued → 301 to parent category
- Temporary seasonal removal → keep page with `OutOfStock`, add expected return date

---

### E-commerce Schema Quick Reference

| Page Type | Required Schema | Optional Schema |
|-----------|----------------|-----------------|
| Product page | Product + Offer, BreadcrumbList | AggregateRating, Review, MerchantReturnPolicy, OfferShippingDetails, ProductGroup (variants) |
| Category page | CollectionPage or ItemList, BreadcrumbList | — |
| Homepage | Organization, WebSite + SearchAction | — |
| Cart/Checkout | — (functional page — exempt from content checks) | — |
| Brand page | Brand or Organization, ItemList | — |
| Sale/Promo page | OfferCatalog, ItemList | Sale event schema |

---

### Common E-commerce SEO Issues

| Issue | Impact | Fix |
|-------|--------|-----|
| Faceted navigation creating crawl bloat | Diluted crawl budget, duplicate content | Choose robots/noindex/canonical/indexable treatment per URL pattern using evidence; avoid blanket thresholds |
| Manufacturer descriptions copied across products | Potential duplication when pages serve the same intent with little distinguishing value | Improve only where duplication, cannibalization, poor indexation, or weak usefulness is evidenced; no fixed word target |
| Out-of-stock pages returning 404 | Lost link equity, poor UX | Keep page, show alternatives, use `Discontinued` availability |
| Return/shipping structured data defect | Merchant information may be inconsistent or ineligible | Fix only validated missing/invalid/inconsistent implementation; do not require redundant per-product repetition |
| Category pages lacking useful context | May underserve search intent in some collections | Add helpful category content only where the query intent and page usefulness justify it; no fixed word target |
| Product variants as separate URLs without ProductGroup | Cannibalization, diluted signals | Use ProductGroup schema + canonical to primary variant |
| Review schema without real reviews | Google spam policy violation | Remove AggregateRating until genuine reviews collected |
| Price not in schema or mismatched | Lost price display in search | Ensure schema price matches visible page price exactly |
| Missing product identifiers | Ineligible for merchant features | Add at least one of: sku, gtin, mpn |
| Internal search pages indexed | Crawl waste, thin content | noindex all `/search?q=` pages |

---

### E-commerce GEO Considerations

AI search engines increasingly cite product pages. For AI citation readiness:

1. **Structured product summaries** — first 60 words should answer "What is this product and who is it for?"
2. **Comparison-friendly content** — include specs tables, pro/con lists
3. **Brand authority signals** — consistent brand entity across product pages
4. **Review richness** — real reviews with specific use cases get cited more than generic "great product" reviews

---

### Scripts

| Script | Purpose |
|--------|---------|
| `ecommerce_schema.py` | E-commerce schema validation (Product, Offer, MerchantReturnPolicy, shipping) |
| `validate_schema.py` | General JSON-LD validation |
| `image_checker.py` | Product image optimization |
| `duplicate_content.py` | Detect copied manufacturer descriptions |
| `canonical_checker.py` | Faceted navigation canonical audit |
| `sitemap_checker.py` | Product/category URL coverage in sitemap |

→ Run `python scripts/ecommerce_schema.py <url> --json`
