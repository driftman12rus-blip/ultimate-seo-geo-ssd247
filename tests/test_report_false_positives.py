"""Five report defects a full live run on posthog.com and smashingmagazine.com exposed (2026-09-28).

Every fixture here is the shape those pages actually serve, not an idealised one:

1. Inline SVG icons carry their own <title> (an accessible name). Both sites have
   one real document title and two icon titles, and both got a Critical
   "Multiple <title> tags" finding.
2. posthog.com's Organization JSON-LD has a PostalAddress for its head office. The
   address regex read JSON-LD too, so a SaaS company was told (High) to add
   LocalBusiness schema, with no phone link and no map anywhere on the page.
3. navigation_checker.py emits High. navigation is display-only (shown, never
   weighted), yet High maps to the report's critical level, so an unweighted
   check could fail a --fail-on critical CI gate on its own.
4. The PageSpeed panel read "field_data" / "lab_data", keys pagespeed.py never
   writes ("metrics"), so LCP, INP and CLS showed "—" even when measured. The CrUX
   CLS percentile also arrives x100 and was shown raw ("5", target < 0.1).
5. security_headers.py, broken_links.py and internal_links.py raised bare strings,
   which reach the report with no fix and no evidence: a Critical "5 security
   headers missing" named none of the five.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import broken_links  # noqa: E402
import generate_report as gr  # noqa: E402
import internal_links  # noqa: E402
import jsonld  # noqa: E402
import local_signals_checker  # noqa: E402
import pagespeed  # noqa: E402
import parse_html  # noqa: E402
import security_headers  # noqa: E402

SVG_ICON = ('<svg viewBox="0 0 24 24" role="img"><title>{}</title>'
            '<path d="M0 0h24v24H0z"/></svg>')


# --- 1. SVG <title> is not a document title ---------------------------------

def _titles_page(head_titles, icon_titles):
    head = "".join(f"<title>{t}</title>" for t in head_titles)
    body = "".join(SVG_ICON.format(t) for t in icon_titles)
    return f"<html><head>{head}</head><body><h1>Hi</h1>{body}</body></html>"


def _title_issues(result):
    return [i for i in result["issues"] if "<title>" in i["finding"]]


def test_svg_icon_titles_are_not_duplicate_document_titles():
    """posthog.com and smashingmagazine.com: one head title, two icon titles."""
    result = parse_html.parse_html(_titles_page(["PostHog – product OS"], ["GitHub", "Close menu"]))
    assert _title_issues(result) == []
    assert result["title"] == "PostHog – product OS"


def test_mathml_title_is_not_a_document_title_either():
    html = "<html><head><title>Doc</title></head><body><math><title>x squared</title></math></body></html>"
    assert _title_issues(parse_html.parse_html(html)) == []


def test_two_real_document_titles_are_still_critical():
    result = parse_html.parse_html(_titles_page(["One", "Two"], ["icon"]))
    [issue] = _title_issues(result)
    assert issue["severity"] == "critical" and "(2)" in issue["finding"]


def test_an_icon_title_is_never_read_as_the_page_title():
    """No document title at all: the icon's label must not stand in for it."""
    result = parse_html.parse_html(_titles_page([], ["Search"]))
    assert result["title"] is None


# --- 2. An Organization's address is not a local business --------------------

POSTHOG_ORGANIZATION = (
    '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization",'
    '"name":"PostHog","url":"https://posthog.com","sameAs":["https://www.linkedin.com/company/posthog"],'
    '"address":{"@type":"PostalAddress","streetAddress":"2261 Market St #4008",'
    '"addressLocality":"San Francisco","addressRegion":"CA","postalCode":"94114"}}</script>'
)


class _Resp:
    status_code = 200

    def __init__(self, text):
        self.text = text


def _local(monkeypatch, html):
    monkeypatch.setattr(local_signals_checker.requests, "get", lambda *a, **k: _Resp(html))
    return local_signals_checker.check_local_signals("https://ex.com/")


def test_saas_organization_address_is_not_a_local_signal(monkeypatch):
    result = _local(monkeypatch, f"<html><head>{POSTHOG_ORGANIZATION}</head><body>Product analytics</body></html>")
    assert result["structured_address_signals"] is False
    assert result["likely_local_business"] is False
    assert result["issues"] == [] and result["score"] is None


def test_a_map_link_inside_json_ld_is_not_a_local_signal(monkeypatch):
    html = ('<script type="application/ld+json">{"@type":"Organization",'
            '"hasMap":"https://www.google.com/maps/place/HQ"}</script>')
    result = _local(monkeypatch, html)
    assert result["map_embed_or_link"] is False and result["likely_local_business"] is False


def test_a_visible_address_and_phone_still_ask_for_localbusiness(monkeypatch):
    """The finding exists for this case and must survive: microdata address plus a phone link."""
    html = (f"<html><head>{POSTHOG_ORGANIZATION}</head><body>"
            '<a href="tel:+14155550100">Call</a><span itemprop="streetAddress">1 Main St</span></body></html>')
    result = _local(monkeypatch, html)
    assert result["likely_local_business"] is True
    assert any(i["severity"] == "high" and "LocalBusiness" in i["finding"] for i in result["issues"])


def test_a_localbusiness_block_is_still_detected(monkeypatch):
    html = ('<script type="application/ld+json">{"@type":"Dentist","name":"Smile",'
            '"address":{"@type":"PostalAddress","streetAddress":"1 Main St"}}</script>')
    result = _local(monkeypatch, html)
    assert result["localbusiness_types"] == ["Dentist"] and result["likely_local_business"] is True


def test_without_script_blocks_agrees_with_script_blocks():
    html = ('<p>before</p><script data-x="1" type="application/ld+json">{"a":1}</script>'
            '<script type="text/javascript">var streetAddress;</script><p>after</p>')
    assert jsonld.script_blocks(html) == ['{"a":1}']
    stripped = jsonld.without_script_blocks(html)
    assert '{"a":1}' not in stripped and "before" in stripped and "after" in stripped
    assert "var streetAddress" in stripped  # only JSON-LD is removed


# --- 3. A display-only check never reaches the critical level ---------------

NAV_HIGH = {"status": "measured", "issues": [{
    "type": "money_page_not_in_nav", "severity": "High",
    "finding": "3 product_feature page(s) exist; none of them is among the 13 primary-nav or 0 footer targets.",
    "evidence": "https://ex.com/cdp", "fix": "Add the product feature hub to the primary navigation.",
    "confidence": "Likely"}]}


def _findings(**sections):
    base = {"security": {"score": 90}, "onpage": {"title": "t" * 40, "meta_description": "m", "h1": ["h"]}}
    base.update(sections)
    data = {"url": "https://ex.com/", "domain": "ex.com", "timestamp": "2026-09-28T10:00:00", "sections": base}
    return gr.build_summary(data, gr.calculate_overall_score(data))


@pytest.mark.parametrize("section", gr.DISPLAY_ONLY_CHECKS)
def test_display_only_high_is_capped_at_medium(section):
    [finding] = [f for f in _findings(**{section: NAV_HIGH})["findings"] if f["section"] == section]
    assert (finding["severity"], finding["level"], finding["severity_capped_from"]) == ("medium", "warning", "high")


def test_display_only_finding_does_not_fail_a_critical_gate():
    summary = _findings(navigation=NAV_HIGH)
    assert gr.evaluate_gate(summary, fail_on="critical")["result"] == "pass"


def test_a_weighted_check_keeps_its_high_severity():
    summary = _findings(canonical={"score": 40, "issues": [{"severity": "high", "finding": "Canonical points to a 404", "fix": "f"}]})
    [finding] = [f for f in summary["findings"] if f["section"] == "canonical"]
    assert (finding["severity"], finding["level"], finding["severity_capped_from"]) == ("high", "critical", None)


# --- 4. The PageSpeed panel shows what pagespeed.py measured -----------------

PSI_RESPONSE = {
    "lighthouseResult": {"categories": {"performance": {"score": 0.71}}, "audits": {}},
    "loadingExperience": {"metrics": {
        "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2340, "category": "FAST", "distributions": []},
        "INTERACTION_TO_NEXT_PAINT": {"percentile": 180, "category": "FAST", "distributions": []},
        "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 5, "category": "FAST", "distributions": []},
    }},
}


class _PsiResp:
    status_code = 200

    def json(self):
        return PSI_RESPONSE


@pytest.fixture
def psi(monkeypatch):
    monkeypatch.setattr(pagespeed.requests, "get", lambda *a, **k: _PsiResp())
    return pagespeed.get_pagespeed("https://ex.com/")


def test_crux_cls_percentile_is_divided_by_100(psi):
    assert psi["metrics"]["CLS"]["value"] == 0.05


def test_pagespeed_panel_shows_measured_core_web_vitals(psi):
    data = {"url": "https://ex.com/", "domain": "ex.com", "sections": {"pagespeed": psi}}
    panel = gr._check_panels(data)["pagespeed"]
    assert "2,340 ms (fast, field)" in panel
    assert "180 ms (fast, field)" in panel
    assert "0.05 (fast, field)" in panel


def test_psi_metric_text_reads_lab_data_and_missing_metrics():
    section = {"metrics": {"LCP": {"value": 4100, "unit": "ms", "rating": "poor", "source": "lab"}}}
    assert gr.psi_metric_text(section, "LCP") == "4,100 ms (poor, lab)"
    assert gr.psi_metric_text(section, "INP") == "—"
    assert gr.psi_metric_text({}, "CLS") == "—"


# --- 5. Every finding a person must act on says what to do -------------------

class _HeaderResp:
    def __init__(self, url, headers):
        self.url, self.headers = url, headers


def _security(monkeypatch, url, headers):
    monkeypatch.setattr(security_headers.requests, "get", lambda *a, **k: _HeaderResp(url, headers))
    return security_headers.check_security_headers(url)


def test_missing_security_headers_are_named_with_a_fix_and_are_not_critical(monkeypatch):
    """posthog.com: HTTPS, HSTS without includeSubDomains, the other five headers absent."""
    result = _security(monkeypatch, "https://posthog.com/", {"Strict-Transport-Security": "max-age=31536000"})
    [missing] = [i for i in result["issues"] if i["code"] == "security-headers-missing"]
    assert missing["severity"] == "medium"
    for label in ("Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options",
                  "Referrer-Policy", "Permissions-Policy"):
        assert label in missing["finding"]
    assert "nosniff" in missing["fix"] and "SAMEORIGIN" in missing["fix"]
    [hsts] = [i for i in result["issues"] if i["code"] == "hsts-missing-includesubdomains-directive"]
    assert "includeSubDomains" in hsts["fix"] and hsts["evidence"] == "Strict-Transport-Security: max-age=31536000"


def test_no_https_is_still_critical(monkeypatch):
    result = _security(monkeypatch, "http://ex.com/", {})
    https = next(i for i in result["issues"] if i["code"] == "site-not-using-https")
    assert https["severity"] == "critical" and "301" in https["fix"]


def test_unreadable_hsts_max_age_is_reported_not_swallowed(monkeypatch):
    result = _security(monkeypatch, "https://ex.com/", {"Strict-Transport-Security": "max-age=forever; includeSubDomains"})
    assert any(i["code"] == "hsts-max-age-invalid" for i in result["issues"])


def test_security_finding_codes_are_the_ones_older_runs_recorded(monkeypatch):
    """--previous matches by code: a baseline written before this change must still line up."""
    result = _security(monkeypatch, "https://ex.com/", {"Strict-Transport-Security": "max-age=60"})
    codes = {gr.finding_code("security", i, i["finding"])[0] for i in result["issues"]}
    assert codes == {"security.security-headers-missing", "security.hsts-max-age-is-s",
                     "security.hsts-missing-includesubdomains-directive"}


def test_redirect_chains_and_soft_404s_carry_evidence_and_a_fix(monkeypatch):
    html = '<a href="/old/">Old</a><a href="/missing/">Missing</a><a href="/slow/">Slow</a>'
    chain = {"from": "https://ex.com/old/", "to": "https://ex.com/new/", "hops": 2, "codes": [301, 302]}

    def fake_check(link, timeout=10, **_kwargs):
        base = {**link, "status": 200, "error": None, "redirect": None, "response_time_ms": 1, "soft_404": False}
        if link["url"].endswith("/old/"):
            base["redirect"] = chain
        elif link["url"].endswith("/missing/"):
            base["soft_404"] = True
        else:
            base.update(status=None, error="timeout")
        return base

    class Page:
        status_code, text, url = 200, html, "https://ex.com/"

    monkeypatch.setattr(broken_links, "check_link", fake_check)
    monkeypatch.setattr(broken_links.requests, "get", lambda *a, **k: Page())
    result = broken_links.check_broken_links("https://ex.com/")
    by_finding = {i["finding"]: i for i in result["issues"]}
    chains = by_finding["1 redirect chain(s) detected (>1 hop)"]
    assert "https://ex.com/new/" in chains["evidence"] and "301, 302" in chains["evidence"] and chains["fix"]
    assert by_finding["1 link(s) timed out"]["fix"]
    soft = next(i for i in result["issues"] if "soft 404" in i["finding"])
    assert "missing" in soft["evidence"] and soft["fix"]


def test_a_page_with_no_links_is_an_open_question_not_a_defect(monkeypatch):
    class Page:
        status_code, text, url = 200, "<div id=root></div>", "https://ex.com/"

    monkeypatch.setattr(broken_links.requests, "get", lambda *a, **k: Page())
    [issue] = broken_links.check_broken_links("https://ex.com/")["issues"]
    assert issue["kind"] == "data_gap" and issue["severity"] == "info" and "--render" in issue["fix"]
    assert gr.finding_code("broken_links", issue, issue["finding"])[0] == "broken_links.no-links-found-on-page"


class _Page:
    def __init__(self, url, status, text):
        self.url, self.status_code, self.text = url, status, text
        self.headers = {"content-type": "text/html; charset=utf-8"}


def test_internal_link_findings_carry_evidence_and_a_fix(monkeypatch):
    """smashingmagazine.com / posthog.com: icon links with no text, nofollow internal links."""
    home = ('<html><body><a href="/a"><img src="/logo.png"></a>'
            '<a href="/b" rel="nofollow">B</a><a href="/gone">Gone</a></body></html>')
    site = {"https://ex.com/": (200, home), "https://ex.com/a": (200, "<a href='/'>Home</a>"),
            "https://ex.com/b": (200, "<a href='/'>Home</a>"), "https://ex.com/gone": (404, "")}
    monkeypatch.setattr(internal_links.requests, "get",
                        lambda url, **kw: _Page(url, *site.get(url, (200, ""))))
    result = internal_links.crawl_site("https://ex.com/", max_depth=1, max_pages=10)
    assert all(isinstance(i, dict) and i["fix"] and i["evidence"] for i in result["issues"]), result["issues"]
    no_text = next(i for i in result["issues"] if "no anchor text" in i["finding"])
    assert "https://ex.com/a" in no_text["evidence"] and "aria-label" in no_text["fix"]
    nofollow = next(i for i in result["issues"] if "nofollow" in i["finding"])
    assert "https://ex.com/b" in nofollow["evidence"]
    broken = next(i for i in result["issues"] if "404/4xx" in i["finding"])
    assert broken["severity"] == "critical" and "linked from 1 page(s)" in broken["evidence"]


@pytest.mark.parametrize("script", [security_headers, broken_links, internal_links])
def test_no_bare_string_issues_remain_in_these_scripts(script):
    """A bare string reaches the report with no fix; these three scripts must emit dicts."""
    import re
    source = open(script.__file__, encoding="utf-8").read()
    assert not re.search(r'issues"?\]?\.append\(\s*f?"', source), script.__name__
