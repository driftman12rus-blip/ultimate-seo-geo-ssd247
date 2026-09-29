"""An object-fit: cover LCP image is not told to add srcset (1.21.3).

balloonbay.us's hero is <img width=1920 height=696 class="hero__poster"> inside
an aria-hidden .hero__bg, styled `.hero__poster{position:absolute;inset:0;
width:100%;height:100%;object-fit:cover}`. On a 375x812 phone its box is 375x946,
so cover draws the 1920px file 2608px wide: it is already below display
resolution, and a srcset would make phones pick smaller, blurrier files. 1.21.2
still raised "First <img> has no srcset attribute." for it.

Inline fixtures only; nothing touches the network.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import image_checker  # noqa: E402

SITE = "https://balloonbay.us/"
NO_SRCSET = "First <img> has no srcset attribute."
NOT_ASSESSED = "LCP image is object-fit: cover; srcset not assessed."

# Minified as Next.js inlines it: grouped selectors, a rule inside @media.
COVER_CSS = (
    ".hero{position:relative;overflow:hidden;min-height:clamp(480px,72vh,680px)}"
    ".hero__bg,.hero__poster{position:absolute;inset:0;z-index:0}"
    ".hero__poster{width:100%;height:100%;object-fit:cover;transition:opacity .6s ease}"
    "@media (prefers-reduced-motion:reduce){.hero__poster{transition:none}}"
)
HERO_IMG = ('<img src="/img/hero-slide.webp" alt="" width="1920" height="696" '
            'class="hero__poster" fetchPriority="high"/>')


def _page(style="", img=HERO_IMG, wrapper='<div class="hero__bg" aria-hidden="true">{}</div>'):
    head = f"<style>{style}</style>" if style else ""
    return (f"<html><head>{head}</head><body>"
            '<header><img src="/img/logo-176.webp" alt="" aria-hidden="true" width="52" height="52"></header>'
            f'<section class="hero">{wrapper.format(img)}</section></body></html>')


def _run(html):
    data = image_checker.analyze_html(html, SITE)
    return data, {i["finding"]: i for i in data["issues"]}


def test_balloonbay_hero_with_cover_css_has_no_srcset_finding():
    data, found = _run(_page(COVER_CSS))
    assert NO_SRCSET not in found
    note = found[NOT_ASSESSED]
    assert note["severity"] == "info" and "hero-slide.webp" in note["evidence"]
    assert data["lcp_srcset"] == {"assessed": False, "has_srcset": False,
                                  "reason": "object-fit: cover", "detected_by": "css"}


def test_same_image_without_cover_still_raises_the_finding():
    plain = '<div class="hero__media">{}</div>'
    img = HERO_IMG.replace('alt=""', 'alt="Balloon arch"').replace("hero__poster", "hero__image")
    data, found = _run(_page(".hero__image{width:100%;height:auto}", img=img, wrapper=plain))
    assert found[NO_SRCSET]["severity"] == "warning"          # wording and severity unchanged
    assert "hero-slide.webp" in found[NO_SRCSET]["evidence"]
    assert NOT_ASSESSED not in found
    assert data["lcp_srcset"] == {"assessed": True, "has_srcset": False}


def test_contain_is_not_cover():
    img = HERO_IMG.replace('alt=""', 'alt="Arch"').replace("hero__poster", "hero__pic")
    _, found = _run(_page(".hero__pic{object-fit:contain}", img=img, wrapper="<div>{}</div>"))
    assert NO_SRCSET in found


def test_inline_style_cover():
    img = '<img src="/h.webp" alt="Arch" width="1920" height="696" style="width:100%; object-fit: cover">'
    data, found = _run(_page(img=img, wrapper="<div>{}</div>"))
    assert NO_SRCSET not in found and data["lcp_srcset"]["detected_by"] == "inline-style"


@pytest.mark.parametrize("css", [
    "img.hero__poster{object-fit:cover}",
    "section.hero > div .hero__poster { object-fit : cover }",
    "/* x */ .other, .hero__poster{height:100%;object-fit:cover!important}",
    "img{object-fit:cover}",
])
def test_selector_forms_that_match(css):
    img = HERO_IMG.replace('alt=""', 'alt="Arch"')
    data, _ = _run(_page(css, img=img, wrapper="<div>{}</div>"))
    assert data["lcp_srcset"]["detected_by"] == "css"


@pytest.mark.parametrize("css", [
    ".hero__poster:hover{object-fit:cover}",      # pseudo-class: not the resting state
    "div.hero__poster{object-fit:cover}",          # a different element
    ".hero__poster.is-hidden{object-fit:cover}",   # a class the image does not carry
    ".hero__poster{object-position:cover}",
])
def test_selector_forms_that_do_not_match(css):
    img = HERO_IMG.replace('alt=""', 'alt="Arch"')
    _, found = _run(_page(css, img=img, wrapper="<div>{}</div>"))
    assert NO_SRCSET in found


def test_heuristic_decorative_poster_in_aria_hidden_container():
    # The live page's CSS may be in an external stylesheet the checker never fetches.
    data, found = _run(_page())
    assert NO_SRCSET not in found and NOT_ASSESSED in found
    assert data["lcp_srcset"]["detected_by"] == "heuristic"


@pytest.mark.parametrize("img,wrapper", [
    ('<img src="/h.webp" alt="" width="1920" height="696" class="page-backdrop">', "<div>{}</div>"),
    ('<img src="/h.webp" alt="" width="1920" height="696">', '<div class="hero-bg">{}</div>'),
    ('<img src="/h.webp" alt="" width="1920" height="696" style="width: 100%; height: 100%">', "<div>{}</div>"),
])
def test_heuristic_background_placements(img, wrapper):
    data, _ = _run(_page(img=img, wrapper=wrapper))
    assert data["lcp_srcset"]["detected_by"] == "heuristic"


def test_heuristic_needs_a_decorative_image():
    # A content image named "poster" (a film poster) keeps the finding.
    img = '<img src="/p.webp" alt="Film poster" width="1200" height="1800" class="poster">'
    _, found = _run(_page(img=img, wrapper='<div aria-hidden="true">{}</div>'))
    assert NO_SRCSET in found


def test_heuristic_needs_a_background_placement():
    # alt="" alone is not enough: 1.21.2's large alt-empty hero keeps its finding.
    _, found = _run(_page(img='<img src="/h.webp" alt="" width="1920" height="696">', wrapper="<div>{}</div>"))
    assert NO_SRCSET in found


def test_an_image_with_srcset_is_unaffected():
    img = HERO_IMG.replace("/>", ' srcset="/a.webp 800w, /b.webp 1920w"/>')
    data, found = _run(_page(COVER_CSS, img=img))
    assert NO_SRCSET not in found and NOT_ASSESSED not in found
    assert data["lcp_srcset"] == {"assessed": True, "has_srcset": True}
