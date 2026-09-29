#!/usr/bin/env python3
"""
Image SEO checker: alt coverage, LCP signals, srcset, WebP, and CLS-prevention
attributes on a saved HTML file or fetched URL.

Usage:
  python image_checker.py /path/to/page.html --base-url https://example.com
  python image_checker.py --url https://example.com/page
  python image_checker.py page.html --base-url https://example.com --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print(json.dumps({"error": "beautifulsoup4 required"}))
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None

WEBP_EXTENSIONS = {".webp"}
RASTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}


def _src_extension(src: str) -> str:
    """Return lowercase file extension from an img src, ignoring query strings."""
    if not src:
        return ""
    path = src.split("?")[0].split("#")[0]
    dot = path.rfind(".")
    return path[dot:].lower() if dot != -1 else ""


SMALL_IMAGE_PX = 200  # both declared dimensions under this: an icon or logo, not the LCP element


def _attr(tag, name: str):
    """An attribute read case-insensitively (React emits fetchPriority, imageSrcSet)."""
    name = name.lower()
    for key, value in (tag.attrs or {}).items():
        if key.lower() == name:
            return " ".join(value) if isinstance(value, list) else value
    return None


def _px(value) -> int | None:
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*$", str(value or ""))
    return int(float(m.group(1))) if m else None


def is_decorative(img) -> bool:
    """alt="", aria-hidden="true" or role=presentation/none: never the LCP image a page is about."""
    alt = _attr(img, "alt")
    if alt is not None and str(alt).strip() == "":
        return True
    if (_attr(img, "aria-hidden") or "").strip().lower() == "true":
        return True
    return (_attr(img, "role") or "").strip().lower() in ("presentation", "none")


def is_small(img) -> bool:
    """Declared width and height both under SMALL_IMAGE_PX."""
    w, h = _px(_attr(img, "width")), _px(_attr(img, "height"))
    return w is not None and h is not None and w < SMALL_IMAGE_PX and h < SMALL_IMAGE_PX


def _declared_large(img) -> bool:
    w, h = _px(_attr(img, "width")), _px(_attr(img, "height"))
    return w is not None and h is not None and w >= SMALL_IMAGE_PX and h >= SMALL_IMAGE_PX


def lcp_candidate(imgs: list):
    """The first <img> likely to be the LCP element, or None.

    Small images (icons, logos) never are. A decorative image (alt="",
    aria-hidden, role=presentation) is skipped unless its declared size says
    it is large: a hero poster is often alt="" (balloonbay.us's 1920x696
    hero is), and LCP is decided by rendered size, not by alt text.
    """
    for img in imgs:
        if is_small(img):
            continue
        if is_decorative(img) and not _declared_large(img):
            continue
        return img
    return None


def hero_preload(soup):
    """A <link rel="preload" as="image" fetchpriority="high">, or None.

    Such a preload already starts the hero fetch at high priority, so the
    <img> itself needing fetchpriority is not a finding.
    """
    for link in soup.find_all("link"):
        rel = _attr(link, "rel") or ""
        if "preload" not in str(rel).lower().split():
            continue
        if (_attr(link, "as") or "").strip().lower() != "image":
            continue
        if (_attr(link, "fetchpriority") or "").strip().lower() == "high":
            return link
    return None


def analyze_html(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    imgs = soup.find_all("img")
    total = len(imgs)
    issues = []

    # --- Alt text ---
    missing_alt = 0
    decorative_ok = 0
    for img in imgs:
        alt = img.get("alt")
        if alt is None:
            missing_alt += 1
        elif str(alt).strip() == "":
            decorative_ok += 1
        elif len(str(alt).strip()) < 3:
            issues.append({
                "severity": "info",
                "finding": f"Very short alt text: {img.get('alt')!r}",
                "fix": "Use descriptive alt text (10–125 chars) for meaningful images.",
            })

    pct_missing_alt = round(100 * missing_alt / total, 1) if total else 0.0

    if missing_alt > 0:
        issues.append({
            "severity": "high" if pct_missing_alt > 25 else "warning",
            "finding": f"{missing_alt}/{total} images missing alt attribute ({pct_missing_alt}%).",
            "fix": "Add descriptive alt text (10–125 chars) for content images; use alt=\"\" only for decorative images.",
        })

    # --- LCP image signals ---
    # The LCP candidate skips small and decorative images (lcp_candidate). On
    # balloonbay.us the first <img> in the document is a 52px header logo with
    # alt="" aria-hidden="true"; the hero comes after it.
    lcp_issues = []
    candidate = lcp_candidate(imgs)
    if candidate is not None:
        first_img = candidate
        loading = (_attr(first_img, "loading") or "").lower()
        fetchpriority = (_attr(first_img, "fetchpriority") or "").lower()
        has_srcset = bool(_attr(first_img, "srcset"))
        evidence = f"LCP candidate: <img src=\"{_attr(first_img, 'src') or ''}\">"
        preload = hero_preload(soup)

        if loading == "lazy":
            lcp_issues.append({
                "severity": "critical",
                "finding": "First <img> has loading=\"lazy\" — this delays the LCP element.",
                "evidence": evidence,
                "fix": "Remove loading=\"lazy\" from the first/hero image. Only lazy-load below-the-fold images.",
            })
        if fetchpriority not in ("high",) and preload is None:
            lcp_issues.append({
                "severity": "warning",
                "finding": "First <img> is missing fetchpriority=\"high\".",
                "evidence": evidence,
                "fix": "Add fetchpriority=\"high\" to the LCP/hero image to preload it sooner.",
            })
        if not has_srcset:
            lcp_issues.append({
                "severity": "warning",
                "finding": "First <img> has no srcset attribute.",
                "evidence": evidence,
                "fix": "Add srcset with multiple resolutions (e.g. image-480w.webp 480w, image-800w.webp 800w) for responsive delivery.",
            })

    issues.extend(lcp_issues)

    # --- srcset + sizes coverage across all images ---
    missing_srcset = sum(1 for img in imgs if not img.get("srcset"))
    missing_sizes = sum(1 for img in imgs if img.get("srcset") and not img.get("sizes"))

    if total > 1 and missing_srcset > total // 2:
        issues.append({
            "severity": "warning",
            "finding": f"{missing_srcset}/{total} images lack srcset.",
            "fix": "Add srcset + sizes to serve correctly sized images on all screen densities.",
        })
    if missing_sizes > 0:
        issues.append({
            "severity": "info",
            "finding": f"{missing_sizes} image(s) have srcset but no sizes attribute.",
            "fix": "Add sizes attribute (e.g. sizes=\"(max-width: 600px) 100vw, 50vw\") so the browser can choose the right srcset entry.",
        })

    # --- width + height (CLS prevention) ---
    missing_dimensions = sum(
        1 for img in imgs
        if not (img.get("width") and img.get("height"))
    )
    if missing_dimensions > 0:
        issues.append({
            "severity": "warning" if missing_dimensions > total // 2 else "info",
            "finding": f"{missing_dimensions}/{total} images missing explicit width and/or height attributes.",
            "fix": "Set width and height on every <img> to reserve layout space and prevent CLS.",
        })

    # --- WebP format ---
    raster_srcs = [
        img.get("src", "") for img in imgs
        if _src_extension(img.get("src", "")) in RASTER_EXTENSIONS
    ]
    if raster_srcs:
        issues.append({
            "severity": "info",
            "finding": f"{len(raster_srcs)} image(s) served as JPEG/PNG instead of WebP.",
            "fix": "Convert to WebP format. WebP is typically 25–35% smaller than JPEG/PNG at equivalent quality.",
        })

    # --- Score ---
    deductions = 0
    if total == 0:
        score = 70
        issues.append({
            "severity": "info",
            "finding": "No <img> elements found on page.",
            "fix": "If this is a visual content page, add images with descriptive alt text.",
        })
    else:
        if pct_missing_alt > 25:
            deductions += 30
        elif pct_missing_alt > 10:
            deductions += 15
        elif pct_missing_alt > 0:
            deductions += 5
        if any(i["severity"] == "critical" for i in lcp_issues):
            deductions += 20
        if missing_dimensions > total // 2:
            deductions += 10
        if raster_srcs:
            deductions += 5
        score = max(0, 100 - deductions)

    recs = []
    if pct_missing_alt > 10:
        recs.append("See references/image-seo.md for alt text, WebP conversion, and srcset guidance.")
    if any(i["severity"] == "critical" for i in lcp_issues):
        recs.append("Fix lazy-loading on the hero/LCP image immediately — it directly delays Core Web Vitals.")

    return {
        "base_url": base_url,
        "total_images": total,
        "missing_alt": missing_alt,
        "empty_alt": decorative_ok,
        "missing_alt_pct": pct_missing_alt,
        "missing_srcset": missing_srcset,
        "missing_dimensions": missing_dimensions,
        "raster_images": len(raster_srcs),
        "score": score,
        "issues": issues[:20],
        "recommendations": recs,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Image SEO quick audit")
    p.add_argument("path", nargs="?", help="Path to local HTML file")
    p.add_argument("--url", help="Fetch this URL instead of reading a file")
    p.add_argument("--base-url", default="", help="Canonical base URL for context")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    html = ""
    base = args.base_url or ""

    if args.url:
        if not requests:
            print(json.dumps({"error": "requests required for --url"}))
            sys.exit(1)
        try:
            r = requests.get(
                args.url,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (compatible; UltimateSEO-Image/1.8)"},
            )
            html = r.text
            base = base or args.url
        except Exception as e:
            print(json.dumps({"error": str(e)}))
            sys.exit(1)
    elif args.path:
        fp = Path(args.path)
        if not fp.is_file():
            print(json.dumps({"error": f"not a file: {args.path}"}))
            sys.exit(1)
        html = fp.read_text(encoding="utf-8", errors="ignore")
        base = base or "https://example.com"
    else:
        print(json.dumps({"error": "Provide path or --url"}))
        sys.exit(1)

    data = analyze_html(html, base)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
