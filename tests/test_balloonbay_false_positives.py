"""Four false or unsafe findings from a live audit of balloonbay.us (2026-09-29).

1. internal_links.py read only visible text, so a logo link named by its image's
   alt and a card link carrying aria-label were "links with no anchor text"
   (medium), although the finding's own fix says aria-label/alt is the remedy.
   site_graph.py recorded the same visible-text-only anchor for the anchor audit.
2. image_checker.py took the first <img> in document order as the LCP image. On
   balloonbay.us that is a 52px decorative header logo (alt="", aria-hidden),
   while the hero is preloaded with <link rel=preload as=image fetchpriority=high>.
3. sitemap_checker.py passed verify=False to requests: TLS certificates were not
   checked, and a failed certificate read as a healthy page.
4. content_quality.py counted every regex hit as a claim: the phone number's last
   four digits (8 times), review dates, "(c) 2026", "Last updated: ..." and
   "since 2019" gave "1 claim(s) appear to need stronger citation support".

All fixtures are inline HTML modelled on the live page; nothing touches the network.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import content_quality  # noqa: E402
import image_checker  # noqa: E402
import internal_links  # noqa: E402
import site_graph  # noqa: E402
import sitemap_checker  # noqa: E402
import url_safety  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

SITE = "https://balloonbay.us/"


# --- 1. link anchors are the accessible name -----------------------------------

LINKS_HTML = """<html><body><main>
<section class="clients">
  <a href="/case-studies/intuit/"><img alt="Intuit" src="/img/intuit.webp" width="120" height="40"></a>
  <a href="/case-studies/coreweave/"><img alt="CoreWeave" src="/img/coreweave.webp"></a>
</section>
<article class="card">
  <a aria-label="Balloon Wall Ideas: Creative Designs" href="/balloon-wall-ideas/"><img alt="" src="/img/wall.webp"></a>
  <h3 id="bouquet-title">Balloon Bouquet Ideas</h3>
  <a aria-labelledby="bouquet-title" href="/balloon-bouquet-ideas/"><img alt="" src="/img/b.webp"></a>
  <a href="/instagram/"><svg viewBox="0 0 24 24"><title>Instagram</title><path d="M0 0"/></svg></a>
  <a href="/empty/"><img alt="" src="/img/x.webp"></a>
</article>
</main></body></html>"""


def _anchors():
    links = internal_links.extract_internal_links(LINKS_HTML, SITE, "balloonbay.us")
    return {l["url"].replace("https://balloonbay.us", ""): l["anchor_text"] for l in links}


def test_image_alt_and_aria_label_name_a_link():
    anchors = _anchors()
    assert anchors["/case-studies/intuit/"] == "Intuit"
    assert anchors["/case-studies/coreweave/"] == "CoreWeave"
    assert anchors["/balloon-wall-ideas/"] == "Balloon Wall Ideas: Creative Designs"
    assert anchors["/balloon-bouquet-ideas/"] == "Balloon Bouquet Ideas"
    assert anchors["/instagram/"] == "Instagram"


def test_only_a_link_with_no_accessible_name_has_no_anchor_text():
    anchors = _anchors()
    assert [u for u, a in anchors.items() if a == "[no text]"] == ["/empty/"]


def test_accessible_name_order():
    soup = BeautifulSoup(
        '<span id="l">From labelledby</span>'
        '<a id="a1" aria-label="From aria" href="/"><img alt="From alt">Visible</a>'
        '<a id="a2" aria-labelledby="l missing" href="/">Visible</a>'
        '<a id="a3" aria-labelledby="missing" href="/">Visible  text</a>'
        '<a id="a4" title="From title" href="/"><img alt=""></a>', "html.parser")
    name = lambda i: site_graph.accessible_name(soup.find(id=i))  # noqa: E731
    assert name("a1") == "From aria"
    assert name("a2") == "From labelledby"
    assert name("a3") == "Visible text"          # unresolvable labelledby falls through
    assert name("a4") == "From title"


def test_site_graph_records_the_accessible_name_so_the_anchor_audit_agrees():
    page = site_graph.extract_page(LINKS_HTML, SITE, "balloonbay.us")
    anchors = {l["href"].replace("https://balloonbay.us", ""): l["anchor"] for l in page["out_links"]}
    assert anchors["/case-studies/intuit/"] == "Intuit"
    assert anchors["/balloon-wall-ideas/"] == "Balloon Wall Ideas: Creative Designs"
    assert [u for u, a in anchors.items() if not internal_links.normalise_anchor(a)] == ["/empty/"]


# --- 2. the LCP candidate skips decorative and small images ----------------------

HERO_HTML = """<html><head>
<link rel="preload" as="image" imageSrcSet="/img/logo-96.webp 96w, /img/logo-176.webp 176w"/>
<link rel="preload" as="image" href="/img/hero-slide.webp" fetchPriority="high"/>
</head><body>
<header><img src="/img/logo-176.webp" srcset="/img/logo-96.webp 96w, /img/logo-176.webp 176w"
  alt="" aria-hidden="true" width="176" height="176"></header>
<main>
<img src="/img/hero-slide.webp" srcset="/img/hero-800.webp 800w, /img/hero-slide.webp 1920w"
  alt="Balloon arch at a corporate event" width="1920" height="696">
</main></body></html>"""


def _findings(html):
    return [i["finding"] for i in image_checker.analyze_html(html, SITE)["issues"]]


def test_decorative_logo_is_not_the_lcp_image_and_a_hero_preload_counts():
    assert not any("fetchpriority" in f for f in _findings(HERO_HTML))


def test_without_the_preload_the_hero_is_judged_not_the_logo():
    html = HERO_HTML.replace('fetchPriority="high"/>', "/>")
    findings = image_checker.analyze_html(html, SITE)["issues"]
    fp = [i for i in findings if "fetchpriority" in i["finding"]]
    assert len(fp) == 1 and "hero-slide.webp" in fp[0]["evidence"]
    assert fp[0]["finding"] == 'First <img> is missing fetchpriority="high".'   # wording (finding code) unchanged


def test_a_preload_without_high_priority_does_not_suppress_the_finding():
    html = HERO_HTML.replace('href="/img/hero-slide.webp" fetchPriority="high"', 'href="/img/hero-slide.webp"')
    assert any("fetchpriority" in f for f in _findings(html))


def test_a_large_alt_empty_hero_poster_is_still_the_candidate():
    # balloonbay.us's real hero is <img alt="" width="1920" height="696" fetchpriority="high">.
    html = ('<img src="/logo.webp" alt="" aria-hidden="true" width="176" height="176">'
            '<img src="/hero.webp" alt="" width="1920" height="696" loading="lazy">')
    assert any('loading="lazy"' in f for f in _findings(html))


@pytest.mark.parametrize("attrs", ['role="presentation"', 'aria-hidden="true"', 'alt=""', 'width="48" height="48" alt="Logo"'])
def test_small_or_decorative_images_alone_raise_no_lcp_finding(attrs):
    assert not any(f.startswith("First <img>") for f in _findings(f'<img src="/i.png" {attrs}>'))


def test_first_content_image_is_still_checked():
    assert any("fetchpriority" in f for f in _findings('<img src="/hero.jpg" alt="Hero" srcset="/a 1x">'))


# --- 3. sitemap_checker verifies TLS and every redirect hop ------------------------

class _Resp:
    def __init__(self, url, status=200, headers=None, text=""):
        self.url, self.status_code, self.text = url, status, text
        self.headers = headers or {}

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308) and "Location" in self.headers


@pytest.fixture
def net(monkeypatch):
    answers, calls = {}, []

    def fake(method):
        def call(url, **kw):
            calls.append((method, url, kw))
            answer = answers.get(url)
            if isinstance(answer, Exception):
                raise answer
            return answer or _Resp(url, 404, {"content-type": "text/html"})
        return call

    monkeypatch.setattr(sitemap_checker.requests, "head", fake("head"))
    monkeypatch.setattr(sitemap_checker.requests, "get", fake("get"))
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host: ["93.184.216.34"] if host != "internal.ex" else ["10.0.0.5"])
    return answers, calls


def test_no_request_disables_certificate_verification(net):
    answers, calls = net
    answers["https://ex.com/a"] = _Resp("https://ex.com/a", 200, {"content-type": "text/html"})
    sitemap_checker._head_check("https://ex.com/a")
    sitemap_checker._fetch("https://ex.com/a")
    assert calls and all(kw.get("verify", True) is not False for _, _, kw in calls)
    assert all(kw.get("allow_redirects") is False for _, _, kw in calls)


def test_source_has_no_verify_false():
    src = open(os.path.join(ROOT, "scripts", "sitemap_checker.py"), encoding="utf-8").read()
    assert "verify=False" not in src


def test_a_certificate_failure_is_named_not_healthy(net):
    answers, _ = net
    answers["https://ex.com/bad"] = sitemap_checker.requests.exceptions.SSLError("certificate verify failed")
    r = sitemap_checker._head_check("https://ex.com/bad")
    assert r["error"].startswith(sitemap_checker.TLS_ERROR) and r["status"] is None
    status, body = sitemap_checker._fetch("https://ex.com/bad")
    assert status is None and body.startswith(sitemap_checker.TLS_ERROR)


def test_redirect_hops_are_counted_and_each_one_validated(net):
    answers, calls = net
    answers["https://ex.com/old"] = _Resp("https://ex.com/old", 301, {"Location": "/mid"})
    answers["https://ex.com/mid"] = _Resp("https://ex.com/mid", 301, {"Location": "https://ex.com/new"})
    answers["https://ex.com/new"] = _Resp("https://ex.com/new", 200, {"content-type": "text/html"})
    r = sitemap_checker._head_check("https://ex.com/old")
    assert r["status"] == 200 and r["redirect"] == {"from": "https://ex.com/old", "to": "https://ex.com/new", "hops": 2}

    answers["https://ex.com/evil"] = _Resp("https://ex.com/evil", 302, {"Location": "http://internal.ex/admin"})
    r = sitemap_checker._head_check("https://ex.com/evil")
    assert "URL safety check failed" in r["error"]
    assert not any(url.startswith("http://internal.ex") for _, url, _ in calls)


def test_head_405_falls_back_to_get(net):
    answers, calls = net
    answers["https://ex.com/h"] = _Resp("https://ex.com/h", 405)

    def get_ok(url, **kw):
        calls.append(("get", url, kw))
        return _Resp(url, 200, {"content-type": "application/xml"})

    sitemap_checker.requests.get = get_ok  # monkeypatch restores it after the test
    r = sitemap_checker._head_check("https://ex.com/h")
    assert r["status"] == 200 and [m for m, _, _ in calls] == ["head", "get"]


def test_tls_failures_in_the_sample_become_a_stated_finding(monkeypatch):
    urlset = '<urlset><url><loc>https://ex.com/a</loc></url><url><loc>https://ex.com/b</loc></url></urlset>'
    monkeypatch.setattr(sitemap_checker, "_fetch", lambda url, timeout=12: (
        (200, "Sitemap: https://ex.com/sitemap.xml\n") if url.endswith("robots.txt") else (200, urlset)))
    monkeypatch.setattr(sitemap_checker, "_head_check", lambda url, timeout=10: {
        "url": url, "status": None, "redirect": None, "soft_404": False,
        "error": f"{sitemap_checker.TLS_ERROR}: certificate has expired"})
    out = sitemap_checker.check_sitemaps("https://ex.com", sample_size=5)
    tls = [i for i in out["issues"] if "TLS certificate" in i["finding"]]
    assert len(tls) == 1 and tls[0]["severity"] == "high" and "expired" in tls[0]["evidence"]


# --- 4. citation claims are sentences in content, not regex hits ------------------

CLAIMS_HTML = """<html><body>
<header><a href="tel:+16505025077">(650) 502-5077</a> <nav><a href="/report">Report</a></nav></header>
<main>
  <h1>Balloon decorations in the Bay Area</h1>
  <p>Balloon Bay has designed balloon decorations since 2019. Call (650) 502-5077 or text 650-502-5077 to book.</p>
  <p>Last updated: September 21, 2026</p>
  <div class="review"><p>Amazing arch for our wedding!</p><time>March 15, 2026</time></div>
  <div class="review"><p>Great team.</p><span>April 2, 2026</span></div>
  <p>Reach us at <a href="tel:6505025077">650.502.5077</a>.</p>
</main>
<footer>&copy; 2026 Balloon Bay. All rights reserved. (650) 502-5077</footer>
</body></html>"""


def test_phone_numbers_dates_copyright_and_chrome_are_not_claims():
    data = content_quality.analyze_html(CLAIMS_HTML, SITE)
    assert data["claim_count"] == 0 and data["citation_gap"] == 0
    assert not any("citation" in i["finding"] for i in data["issues"])


def test_real_claims_are_counted_per_sentence_and_named_in_evidence():
    html = CLAIMS_HTML.replace(
        "<p>Last updated",
        "<p>A 2024 survey found 72% of planners book decor 6 weeks ahead, and 3x more in December. "
        "According to one report, arches are the most requested piece.</p><p>Last updated")
    data = content_quality.analyze_html(html, SITE)
    assert data["claim_count"] == 2                      # two sentences, five regex hits
    gap = next(i for i in data["issues"] if "citation" in i["finding"])
    assert gap["finding"] == "2 claim(s) appear to need stronger citation support"   # wording unchanged
    assert "72% of planners" in gap["evidence"] and "According to one report" in gap["evidence"]
    assert data["claim_examples"][0].startswith("A 2024 survey")


def test_evidence_names_at_most_three_sentences():
    body = " ".join(f"Study {i} found {i}0% growth." for i in range(1, 7))
    data = content_quality.analyze_html(f"<main><p>{body}</p></main>", SITE)
    assert data["claim_count"] == 6
    assert len(data["claim_examples"]) == 3
    gap = next(i for i in data["issues"] if "citation" in i["finding"])
    assert gap["evidence"].count('"') == 6


def test_citation_deduction_is_unchanged():
    body = " ".join(f"Study {i} found {i}0% growth." for i in range(1, 7))
    data = content_quality.analyze_html(f"<main><p>{body}</p></main>", SITE)
    # 6 claims, 0 outbound links: 6 * 3 = 18; short page -20; no author -10; no date -5
    assert data["citation_gap"] == 6 and data["score"] == 100 - 18 - 20 - 10 - 5
