"""Regression tests for the core-script review fixes.

One block per defect, each named after the real page or input that exposed it:
a Yoast @graph page, a SPA shell, a HEAD-hostile server, a CDN that stamps
Access-Control-Allow-Origin on its 404s, and so on.
"""

import datetime
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
import requests
from requests.structures import CaseInsensitiveDict

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import fetch_page  # noqa: E402
import finding_verifier as fv  # noqa: E402
import generate_report as gr  # noqa: E402
import jsonld  # noqa: E402
import page_network as pn  # noqa: E402
import parse_html  # noqa: E402
import readability  # noqa: E402
import redirect_checker  # noqa: E402
import report_data_lint  # noqa: E402
import url_safety  # noqa: E402

PUBLIC_IP = "93.184.216.34"


# --- 1. JSON-LD: @graph expanded, one extractor ------------------------------------------------

YOAST_NEWS = """<html><head><title>Rates held</title>
<script type="application/ld+json" class="yoast-schema-graph">{"@context": "https://schema.org", "@graph": [
  {"@type": "NewsMediaOrganization", "@id": "https://news.example/#org", "name": "Example News"},
  {"@type": "WebPage", "@id": "https://news.example/rates/"},
  {"@type": ["NewsArticle", "Article"], "headline": "Rates held"},
  {"@type": "ClaimReview", "claimReviewed": "x"},
  {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": "Why?",
     "acceptedAnswer": {"@type": "Answer", "text": "Because the committee voted to hold rates steady."}}]}
]}</script></head><body><h1>Rates held</h1><p>Short story.</p></body></html>"""


def test_yoast_graph_page_reports_each_node_not_one_unknown():
    schema = parse_html.parse_html(YOAST_NEWS, "https://news.example/rates/")["schema"]
    types = [s["@type"] for s in schema]
    assert "Unknown" not in types
    assert "NewsMediaOrganization" in types and ["NewsArticle", "Article"] in types
    by_type = {jsonld.type_names(s["@type"])[0]: s for s in schema}
    assert by_type["ClaimReview"]["status"] == "deprecated"
    assert by_type["FAQPage"]["faq_answers_missing_from_html"], "FAQ parity must run on @graph members"
    # Members inherit the wrapper's @context.
    assert all(s["has_context"] for s in schema)


def test_uppercase_ld_json_type_attribute_is_parsed_like_every_other_caller_counts_it():
    html = '<script type="application/LD+json">{"@context": "https://schema.org", "@type": "Organization"}</script>'
    assert len(jsonld.script_blocks(html)) == 1
    assert [s["@type"] for s in parse_html.parse_html(html)["schema"]] == ["Organization"]


def test_jsonld_nodes_expands_graph_and_keeps_a_typed_wrapper():
    wrapped = {"@context": "https://schema.org", "@graph": [{"@type": "A"}, "junk", {"@type": "B"}]}
    assert [n["@type"] for n in jsonld.nodes(wrapped)] == ["A", "B"]
    typed = {"@type": "Dataset", "@graph": [{"@type": "C"}]}
    out = jsonld.nodes(typed)
    assert [n["@type"] for n in out] == ["Dataset", "C"] and "@graph" not in out[0]
    assert [n["@type"] for n in jsonld.nodes([wrapped, {"@type": "D"}])] == ["A", "B", "D"]
    assert jsonld.nodes({"@type": "E"}) == [{"@type": "E"}]


def test_preferred_sources_finding_fires_on_a_yoast_news_site():
    op = parse_html.parse_html(YOAST_NEWS, "https://news.example/rates/")
    data = {"url": "https://news.example/", "environment": {"primary": "WordPress"},
            "sections": {"onpage": op, "preferred_sources": {"implemented": False, "integration": {}}}}
    titles = [f["title"] for f in gr.build_environment_fixes(data)]
    assert "No preferred sources opt-in found" in titles


# --- 2. parse_html CLI on a non-UTF-8 file ---------------------------------------------------

def test_parse_html_cli_reads_a_windows_1252_saved_page(tmp_path):
    page = tmp_path / "latin.html"
    page.write_bytes("<html><head><title>Café menu</title></head><body><h1>Menú</h1></body></html>".encode("cp1252"))
    run = subprocess.run([sys.executable, os.path.join(SCRIPTS, "parse_html.py"), str(page), "--json"],
                         capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["title"].startswith("Caf")


# --- 3. finding_verifier: other finding shapes, and the summary object ------------------------

def test_render_report_findings_keyed_by_title_are_not_collapsed_into_one():
    findings = [
        {"id": "F1", "title": "Brand demand is falling", "observation": "Clicks fell", "severity": "critical"},
        {"id": "F2", "title": "Canonicals are correct", "observation": "Self-referencing", "severity": "info"},
        {"issue": "Missing H1 on /pricing", "severity": "high"},
    ]
    assert fv.verify_findings(findings)["verified_count"] == 3


def test_same_words_on_two_sections_stay_two_findings_and_duplicates_still_merge():
    out = fv.verify_findings([
        {"finding": "Title too long", "section": "onpage", "severity": "low"},
        {"finding": "Title too long", "section": "social", "severity": "low"},
        {"finding": "Title too long", "section": "onpage", "severity": "high"},
    ])
    assert out["verified_count"] == 2
    assert {f["severity"] for f in out["findings"]} == {"high", "low"}


def test_verifier_cli_accepts_the_generate_report_summary_object(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"overall": 71, "findings": [
        {"finding": "Missing H1", "severity": "high", "section": "onpage"},
        {"finding": "No llms.txt", "severity": "info", "section": "llms_txt"},
    ]}))
    run = subprocess.run([sys.executable, os.path.join(SCRIPTS, "finding_verifier.py"),
                          "--findings-json", str(summary), "--json"], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["verified_count"] == 2


# --- 4. readability: a SPA shell is unmeasured, not Flesch 0 ---------------------------------

SPA_SHELL = ('<html><head><title>App</title></head><body><div id="root"></div>'
             '<noscript>You need to enable JavaScript to run this app.</noscript>'
             '<script src="/static/js/main.js"></script></body></html>')

BASE_SECTIONS = {
    "security": {"score": 80}, "social": {"score": 70}, "robots": {"status": 200, "sitemaps": ["x"]},
    "broken_links": {"summary": {"total": 50, "broken": 0}}, "canonical": {"score": 90},
}


def test_spa_shell_readability_is_not_measured_and_leaves_the_overall_score_alone():
    rd = readability.analyze_readability(readability.extract_text(SPA_SHELL))
    assert rd["measured"] is False and "not measured" in rd["error"].lower()
    assert not any("difficult" in str(i).lower() for i in rd["issues"])

    without = gr.calculate_overall_score({"sections": dict(BASE_SECTIONS)})
    with_shell = gr.calculate_overall_score({"sections": {**BASE_SECTIONS, "readability": rd}})
    assert with_shell["overall"] == without["overall"]
    assert with_shell["raw_categories"]["readability"] is None and "readability" in with_shell["unmeasured"]
    assert "Content readability is difficult" not in [
        f["title"] for f in gr.build_environment_fixes({"url": "https://ex.com/", "sections": {"readability": rd}})]


def test_real_prose_is_still_measured():
    text = " ".join(["The team shipped the new report on time and the client read it the same day."] * 6)
    rd = readability.analyze_readability(text)
    assert rd["measured"] is True and "error" not in rd and rd["flesch_reading_ease"] > 0


# --- 5. url_safety: IPv6 brackets, CGNAT --------------------------------------------------------

def test_public_ipv6_literal_keeps_its_brackets_and_is_allowed():
    for url in ("http://[2606:4700::1111]/", "https://[2606:4700::1111]:8443/dns"):
        result = url_safety.validate_url(url, resolve_dns=False)
        assert result.ok, result.reason
        assert "[2606:4700::1111]" in result.normalized_url


@pytest.mark.parametrize("url", ["http://100.64.0.1/", "http://100.127.255.254/", "http://[::1]/",
                                 "http://2130706433/", "http://[::ffff:127.0.0.1]/", "http://[::ffff:10.0.0.1]/"])
def test_cgnat_and_mapped_internal_addresses_are_refused(url):
    assert url_safety.validate_url(url, resolve_dns=False).ok is False


# --- 6. fetch_page: UTF-8 default; generate_report skips page checks on a 4xx/5xx page -------

def _response(body: bytes, ctype: str, status: int = 200):
    r = requests.models.Response()
    r._content = body
    r.status_code = status
    r.headers = CaseInsensitiveDict({"Content-Type": ctype})
    r.url = "https://ex.com/"
    # What requests' HTTPAdapter sets: ISO-8859-1 for any text/* without a charset.
    r.encoding = requests.utils.get_encoding_from_headers(r.headers)
    return r


def _fetch(monkeypatch, response):
    monkeypatch.setattr(fetch_page.requests, "Session", lambda: SimpleNamespace(get=lambda *a, **k: response))
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host: [PUBLIC_IP])
    return fetch_page.fetch_page("https://ex.com/")


def test_non_ascii_title_without_a_charset_header_is_read_as_utf8(monkeypatch):
    html = "<html><head><title>Gehaltsrechner für Köln – 2026</title></head></html>"
    result = _fetch(monkeypatch, _response(html.encode("utf-8"), "text/html"))
    assert result["content"] == html


def test_meta_charset_is_respected_when_the_header_names_none(monkeypatch):
    html = '<html><head><meta charset="windows-1252"><title>Café</title></head></html>'
    result = _fetch(monkeypatch, _response(html.encode("cp1252"), "text/html"))
    assert "Café" in result["content"]


def test_header_charset_still_wins(monkeypatch):
    html = "<title>Café</title>"
    result = _fetch(monkeypatch, _response(html.encode("latin-1"), "text/html; charset=ISO-8859-1"))
    assert "Café" in result["content"]


def test_a_404_homepage_is_not_audited_as_the_page(monkeypatch):
    fetched = {"content": "<html><title>Page not found</title></html>", "status_code": 404,
               "rendered": False, "render_error": None, "error": None}
    monkeypatch.setattr(gr, "fetch_url", lambda *a, **k: fetched)
    assert gr.fetch_page("https://ex.com/") == ("", "")

    calls = []

    def fake_run(script, args, timeout=120):
        calls.append(script)
        return {}

    monkeypatch.setattr(gr, "run_script", fake_run)
    monkeypatch.setattr(gr, "build_site_graph", lambda url: None)
    data = gr.collect_data("https://ex.com/")
    assert "parse_html.py" not in calls and "readability.py" not in calls
    assert "HTTP 404" in data["page_fetch_error"]
    for name in gr.PAGE_LEVEL_CHECKS:
        assert "HTTP 404" in data["sections"][name]["error"]
    scores = gr.calculate_overall_score(data)
    assert {"onpage", "readability", "schema_validation", "image_seo"} <= set(scores["unmeasured"])
    titles = [f["title"] for f in gr.build_environment_fixes(data)]
    assert "Missing H1 on page" not in titles and "Title tag needs optimization" not in titles


# --- 7. report_data_lint: absence claims in defects too --------------------------------------

def test_a_defect_claiming_orphan_pages_from_an_incomplete_crawl_is_an_error():
    from test_report_set import _source

    src = _source()
    src["findings"] = [f for f in src["findings"] if f["kind"] != "opportunity"]
    src["recommendations"][1]["fixes"] = ["F1"]
    src["findings"].append({
        "id": "F4", "kind": "defect", "severity": "high", "title": "14 orphan pages",
        "observation": "No internal link reaches 14 pages", "evidence": "crawl", "evidence_status": "sampled",
        "confidence": "Likely", "falsifiability": "A full crawl finds links", "impact": "Unindexed pages",
        "fixes": ["T1"], "watch": "Orphans"})
    src["coverage"]["graph"]["sitemap"]["complete"] = False
    errors = report_data_lint.lint(src)["errors"]
    assert any(e["rule"] == "absence-claim" and e["where"] == "finding F4" for e in errors)
    src["coverage"]["graph"]["crawl"]["complete"] = True
    assert not any(e["rule"] == "absence-claim" for e in report_data_lint.lint(src)["errors"])


# --- 8. redirect_checker: a server that refuses HEAD ------------------------------------------

class _Hop:
    def __init__(self, status, location=None):
        self.status_code = status
        self.headers = {"Location": location} if location else {}
        self.elapsed = datetime.timedelta(milliseconds=5)
        self.closed = False

    def close(self):
        self.closed = True


@pytest.mark.parametrize("head_status", [405, 501, 403, 404])
def test_server_answering_head_with_an_error_is_walked_with_get(monkeypatch, head_status):
    gets = [_Hop(301, "https://ex.com/new"), _Hop(200)]
    got = []

    def fake_get(url, **kw):
        assert kw.get("stream") is True and kw.get("allow_redirects") is False
        got.append(url)
        return gets.pop(0)

    monkeypatch.setattr(redirect_checker.requests, "head", lambda u, **kw: _Hop(head_status))
    monkeypatch.setattr(redirect_checker.requests, "get", fake_get)
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host: [PUBLIC_IP])
    result = redirect_checker.check_redirects("https://ex.com/old")
    assert [h["status"] for h in result["chain"]] == [301, 200]
    assert result["final_url"] == "https://ex.com/new" and result["chain"][0]["method"] == "GET"
    # The --graph walk files a row under "broken" from the last hop's status, so
    # this link no longer "redirects to an error page".
    assert result["chain"][-1]["status"] < 400


def test_a_real_404_after_get_is_still_broken(monkeypatch):
    monkeypatch.setattr(redirect_checker.requests, "head", lambda u, **kw: _Hop(404))
    monkeypatch.setattr(redirect_checker.requests, "get", lambda u, **kw: _Hop(404))
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host: [PUBLIC_IP])
    result = redirect_checker.check_redirects("https://ex.com/gone")
    assert [h["status"] for h in result["chain"]] == [404]


# --- 9. page_network: Allow-Origin on a refused preflight opens nothing -----------------------

def test_cdn_allow_origin_on_a_404_endpoint_is_not_an_open_endpoint():
    get = {"status": 404, "content_type": "application/json", "allow_origin": "*", "www_authenticate": False}
    for pre in ({"status": 404, "allow_origin": "*"}, {"status": 405, "allow_origin": "*"}):
        assert pn.classify_endpoint("https://ex.com/api/x", get, pre)["open"] is False


def test_preflight_that_does_not_list_the_method_is_not_open():
    get = {"status": 405, "content_type": "application/json", "allow_origin": None, "www_authenticate": False}
    pre = {"status": 204, "allow_origin": "*", "allow_methods": "GET, OPTIONS"}
    assert pn.classify_endpoint("https://ex.com/api/x", get, pre)["open"] is False
    assert pn.classify_endpoint("https://ex.com/api/x", get, {**pre, "allow_methods": "GET, POST"})["open"] is True


def test_page_write_call_probed_with_a_405_preflight_is_not_reported():
    network = [{"url": "https://api.example.com/v1/answer", "method": "POST", "resource_type": "fetch",
                "has_auth_header": False, "request_content_type": None, "status": 200, "cors": {},
                "content_type": "application/json"}]
    page = pn.analyse_page("https://example.com/", network,
                           probe=lambda u, m: {"status": 405, "allow_origin": "*"})
    assert page["open_endpoints"] == [] and pn.build_issues([page], None) == []


# --- the same case-sensitive JSON-LD match in five more scripts -------------
#
# find_all("script", type="application/ld+json") compares the attribute exactly,
# so type="application/LD+json" was dropped by article_seo, drift_monitor,
# entity_checker, ecommerce_schema and maps_checker while script_blocks() counts it.

from bs4 import BeautifulSoup as _Soup  # noqa: E402

import article_seo  # noqa: E402
import drift_monitor  # noqa: E402
import ecommerce_schema  # noqa: E402
import entity_checker  # noqa: E402
import maps_checker  # noqa: E402

_ODD_CASE = ('<html><head><script type=" Application/LD+JSON ">'
             '{"@context":"https://schema.org","@type":"Organization","name":"Acme",'
             '"url":"https://acme.example/","sameAs":["https://x.com/acme"]}</script>'
             '<script type="application/ld+json">{"@type":"Dentist","name":"Smile"}</script>'
             '<script type="text/javascript">var x = {"@type": "Product"};</script></head><body></body></html>')


def test_soup_blocks_matches_script_blocks():
    assert jsonld.soup_blocks(_Soup(_ODD_CASE, "html.parser")) == jsonld.script_blocks(_ODD_CASE)
    assert len(jsonld.script_blocks(_ODD_CASE)) == 2


def test_every_soup_consumer_reads_an_odd_case_type_attribute():
    soup = _Soup(_ODD_CASE, "html.parser")
    assert any("Organization" in str(b) for b in article_seo.extract_structured_data(soup))
    assert any(e.get("type") == "Organization" for e in entity_checker.extract_entities_from_schema(soup))
    assert len(ecommerce_schema.extract_jsonld(_ODD_CASE)) == 2
    assert any(b.get("@type") == "Organization" for b in maps_checker._extract_jsonld_blocks(soup))
    assert drift_monitor.extract_snapshot(_ODD_CASE, "https://acme.example/")["schema_count"] == 2
