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
    it is large: a hero poster is often alt="" (one live site's 1920x696
    hero is), and LCP is decided by rendered size, not by alt text.
    """
    for img in imgs:
        if is_small(img):
            continue
        if is_decorative(img) and not _declared_large(img):
            continue
        return img
    return None


_OBJECT_FIT_COVER = re.compile(r"(?:^|[;{\s])object-fit\s*:\s*cover\b", re.I)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
# Innermost `selectors { declarations }` blocks, so rules nested in @media are read too.
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
# The subject (last compound) of a selector: optional tag, then #id / .class parts only.
_SIMPLE_COMPOUND = re.compile(r"^([a-z][a-z0-9-]*|\*)?((?:[.#][\w-]+)*)$", re.I)
_BACKGROUND_CLASS = re.compile(r"poster|backdrop|background|(?:^|[-_])bg(?:$|[-_])", re.I)


def _compound_matches(compound: str, img) -> bool:
    """Does a simple compound selector (img.a.b, .a, #id, img) select this <img>?"""
    m = _SIMPLE_COMPOUND.match(compound)
    if not m or not (m.group(1) or m.group(2)):
        return False
    tag, parts = (m.group(1) or "").lower(), m.group(2)
    if tag not in ("", "*", "img"):
        return False
    if not parts:
        return tag == "img"   # bare `img { object-fit: cover }`
    classes = set(str(_attr(img, "class") or "").split())
    for part in re.findall(r"[.#][\w-]+", parts):
        if part[0] == "." and part[1:] not in classes:
            return False
        if part[0] == "#" and part[1:] != (_attr(img, "id") or ""):
            return False
    return True


def _stylesheet_sets_cover(soup, img) -> bool:
    """A same-page <style> rule sets object-fit: cover on a selector matching the <img>.

    Only the selector's last compound is matched (ancestor parts are ignored);
    selectors with pseudo-classes or attribute parts are skipped.
    """
    for style in soup.find_all("style"):
        css = _CSS_COMMENT.sub("", style.get_text() or "")
        for selectors, decls in _CSS_RULE.findall(css):
            if not _OBJECT_FIT_COVER.search(";" + decls):
                continue
            for sel in selectors.split(","):
                sel = sel.strip()
                if not sel or sel.startswith("@") or any(c in sel for c in ":[]"):
                    continue
                last = re.split(r"\s*[>+~]\s*|\s+", sel)[-1]
                if _compound_matches(last, img):
                    return True
    return False


def _looks_like_background_poster(img) -> bool:
    """Heuristic when no CSS says so: a decorative image (alt="", aria-hidden,
    role=presentation) placed like a background, i.e. inside an aria-hidden
    ancestor, or carrying a background-style class (poster, backdrop,
    background, bg) on itself or its parent, or an inline width:100%;height:100%."""
    if not is_decorative(img):
        return False
    for parent in img.parents:
        if parent.name in (None, "[document]"):
            break
        if (_attr(parent, "aria-hidden") or "").strip().lower() == "true":
            return True
    for tag in (img, img.parent):
        if tag is not None and any(_BACKGROUND_CLASS.search(c) for c in str(_attr(tag, "class") or "").split()):
            return True
    style = str(_attr(img, "style") or "").replace(" ", "").lower()
    return "width:100%" in style and "height:100%" in style


def cover_fit(soup, img) -> str | None:
    """How the LCP image was found to be object-fit: cover, or None.

    "inline-style": its style attribute says so. "css": a rule in a same-page
    <style> block matches it. "heuristic": neither, but it is a decorative image
    placed like a background (_looks_like_background_poster).
    Not seen: external stylesheets (never fetched), styles applied by script
    after load, and rendered layout. The box size is never measured, so a cover
    image in a box wider than itself (where srcset would help) is not told apart.
    """
    if _OBJECT_FIT_COVER.search(";" + str(_attr(img, "style") or "")):
        return "inline-style"
    if _stylesheet_sets_cover(soup, img):
        return "css"
    if _looks_like_background_poster(img):
        return "heuristic"
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
                "fix": "For meaningful images, use concise descriptive alt text that fits the image context; decorative images should use alt=\"\".",
            })

    pct_missing_alt = round(100 * missing_alt / total, 1) if total else 0.0

    if missing_alt > 0:
        issues.append({
            "severity": "high" if pct_missing_alt > 25 else "warning",
            "finding": f"{missing_alt}/{total} images missing alt attribute ({pct_missing_alt}%).",
            "fix": "Add useful contextual alt text for meaningful images; use alt=\"\" for decorative images. There is no SEO character-count target.",
        })

    # --- LCP image signals ---
    # The LCP candidate skips small and decorative images (lcp_candidate). On
    # one live site the first <img> in the document is a 52px header logo with
    # alt="" aria-hidden="true"; the hero comes after it.
    lcp_issues = []
    lcp_srcset = None   # None: no LCP candidate
    candidate = lcp_candidate(imgs)
    if candidate is not None:
        first_img = candidate
        loading = (_attr(first_img, "loading") or "").lower()
        fetchpriority = (_attr(first_img, "fetchpriority") or "").lower()
        has_srcset = bool(_attr(first_img, "srcset"))
        evidence = f"LCP candidate: <img src=\"{_attr(first_img, 'src') or ''}\">"
        preload = hero_preload(soup)
        lcp_srcset = {"assessed": True, "has_srcset": has_srcset}

        if loading == "lazy":
            lcp_issues.append({
                "severity": "warning",
                "finding": "Likely hero/LCP candidate has loading=\"lazy\"; verify with PageSpeed/DevTools before treating it as the actual LCP element.",
                "evidence": evidence,
                "fix": "If measurement confirms this image is LCP/above the fold, remove lazy loading; otherwise no change is required.",
            })
        if fetchpriority not in ("high",) and preload is None:
            lcp_issues.append({
                "severity": "info",
                "finding": "Likely hero candidate has no fetchpriority=\"high\".",
                "evidence": evidence,
                "fix": "Consider fetchpriority only if measurement confirms this resource is LCP and priority is a bottleneck.",
            })
        # A cover-fitted image is scaled to fill its box. When the box is taller
        # relative to its width than the image (one live site's hero: a 375x946
        # box on a phone draws the 1920x696 file 2608px wide), smaller srcset
        # files would be blurry, so srcset is not assessed, and the report says so.
        cover = None if has_srcset else cover_fit(soup, first_img)
        if cover:
            lcp_srcset = {"assessed": False, "has_srcset": False, "reason": "object-fit: cover", "detected_by": cover}
            lcp_issues.append({
                "severity": "info",
                "kind": "data_gap",
                "finding": "LCP image is object-fit: cover; srcset not assessed.",
                "evidence": f"{evidence} (object-fit: cover, detected by {cover})",
                "fix": "No change needed when the image fills a box taller than its own aspect ratio: it is drawn "
                       "wider than the viewport, so smaller srcset files would look blurry. If the box is wider "
                       "than the image, add srcset and sizes as for any hero.",
            })
        elif not has_srcset:
            lcp_issues.append({
                "severity": "info",
                "finding": "Likely hero candidate has no srcset attribute.",
                "evidence": evidence,
                "fix": "Review actual rendered size and transferred bytes; add responsive candidates only when they improve delivery.",
            })

    issues.extend(lcp_issues)

    # --- srcset + sizes coverage across all images ---
    missing_srcset = sum(1 for img in imgs if not img.get("srcset"))
    missing_sizes = sum(1 for img in imgs if img.get("srcset") and not img.get("sizes"))

    if total > 1 and missing_srcset > total // 2:
        issues.append({
            "severity": "info",
            "finding": f"{missing_srcset}/{total} images lack srcset.",
            "fix": "Review actual responsive delivery/CDN behavior before changing markup; srcset is not a universal SEO requirement.",
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
            "severity": "info",
            "finding": f"{missing_dimensions}/{total} images lack explicit width and/or height attributes.",
            "fix": "Verify whether layout space is already reserved by CSS/aspect-ratio. Add intrinsic dimensions where useful to prevent measured CLS.",
        })

    # --- WebP format ---
    raster_srcs = [
        img.get("src", "") for img in imgs
        if _src_extension(img.get("src", "")) in RASTER_EXTENSIONS
    ]
    if raster_srcs:
        issues.append({
            "severity": "info",
            "finding": f"{len(raster_srcs)} image URL(s) use JPEG/PNG extensions; transferred format was not measured.",
            "fix": "Optimize actual delivered bytes and dimensions. JPEG/PNG/WebP/AVIF are all valid; on Shopify/CDNs the URL extension may differ from the negotiated format.",
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
        score = max(0, 100 - deductions)

    recs = []
    if pct_missing_alt > 10:
        recs.append("See references/image-seo.md for contextual alt text and responsive-image guidance.")
    if any(i["severity"] == "critical" for i in lcp_issues):
        recs.append("Fix lazy-loading on the hero/LCP image immediately — it directly delays Core Web Vitals.")

    return {
        "base_url": base_url,
        "total_images": total,
        "missing_alt": missing_alt,
        "empty_alt": decorative_ok,
        "missing_alt_pct": pct_missing_alt,
        "missing_srcset": missing_srcset,
        "lcp_srcset": lcp_srcset,
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
