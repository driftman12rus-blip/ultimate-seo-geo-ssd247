"""site_graph.fetch_url: every redirect hop is checked, and robots.txt is read.

Two defects found in the 2026-09-28 review, both in the one fetcher every
structure check reads (site_graph.json):

1. SSRF through redirects. fetch_url validated the first URL, then let requests
   follow redirects unchecked. A public page, a sitemap <loc> or a crawled link
   that 302s to http://169.254.169.254/ or a private host was fetched, and its
   title, H1 and links went into the graph and the report. fetch_page.py and
   crawl_adapter.py already walk redirects one validated hop at a time.
2. Sitemaps declared in robots.txt were never read. robots.txt is served as
   text/plain and fetch_url kept bodies only for HTML and XML, so the Sitemap:
   lines were dropped. A site whose sitemap is not at one of four guessed paths
   read as "no sitemap", and every completeness-gated structure claim was withheld.

Also: url_safety.validate_url raised ValueError on a malformed port, so a hostile
Location header crashed the fetch instead of being refused.

The network is faked below: requests.get answers from a dict, and DNS answers
from another, so nothing here leaves the machine.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import fetch_page  # noqa: E402
import site_graph  # noqa: E402
import url_safety  # noqa: E402

PUBLIC_IP = "93.184.216.34"
DNS = {"ex.com": [PUBLIC_IP], "www.ex.com": [PUBLIC_IP], "cdn.ex.com": [PUBLIC_IP],
       "rebind.ex.com": ["10.0.0.5"]}


class _Resp:
    def __init__(self, url, status=200, headers=None, text=""):
        self.url, self.status_code, self.text = url, status, text
        self.headers = headers or {}
        self.encoding = "utf-8"

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308) and "Location" in self.headers


def _redirect(url, to, status=302):
    return _Resp(url, status, {"Location": to})


def _page(url, html="<html><head><title>T</title></head><body><h1>H</h1></body></html>", ctype="text/html"):
    return _Resp(url, 200, {"Content-Type": ctype}, html)


@pytest.fixture
def net(monkeypatch):
    """A fake network: answers[url] -> _Resp. Records every URL actually requested."""
    answers, requested = {}, []

    def get(url, **kw):
        assert kw.get("allow_redirects") is False, "requests must never follow redirects on its own"
        requested.append(url)
        return answers.get(url) or _Resp(url, 404, {"Content-Type": "text/html"})

    def resolve(host):
        if host not in DNS:
            raise url_safety.socket.gaierror("unknown host")
        return DNS[host]

    monkeypatch.setattr(site_graph.requests, "get", get)
    monkeypatch.setattr(url_safety, "_resolve_host", resolve)
    return answers, requested


# --- 1. every redirect hop is validated ---------------------------------------

@pytest.mark.parametrize("target, reason", [
    ("http://169.254.169.254/latest/meta-data/", "169.254.169.254"),   # cloud metadata
    ("http://127.0.0.1:8080/admin", "127.0.0.1"),                      # loopback
    ("https://rebind.ex.com/", "10.0.0.5"),                            # public name, private address
    ("file:///etc/passwd", "scheme"),
])
def test_a_redirect_into_a_private_network_is_refused_and_never_requested(net, target, reason):
    answers, requested = net
    answers["https://ex.com/go"] = _redirect("https://ex.com/go", target)
    result = site_graph.fetch_url("https://ex.com/go")
    assert result["error"].startswith("URL safety check failed") and reason in result["error"]
    assert "redirect 1" in result["error"]
    assert requested == ["https://ex.com/go"]  # the private target was never fetched
    assert result["html"] == "" and result["status"] is None


def test_a_private_hop_deep_in_a_chain_is_still_refused(net):
    answers, requested = net
    answers["https://ex.com/a"] = _redirect("https://ex.com/a", "https://www.ex.com/b", 301)
    answers["https://www.ex.com/b"] = _redirect("https://www.ex.com/b", "http://169.254.169.254/")
    result = site_graph.fetch_url("https://ex.com/a")
    assert "redirect 2" in result["error"] and "169.254.169.254" not in " ".join(requested)


def test_a_public_redirect_chain_is_followed_to_the_page(net):
    answers, requested = net
    answers["http://ex.com/old"] = _redirect("http://ex.com/old", "https://ex.com/old", 301)
    answers["https://ex.com/old"] = _redirect("https://ex.com/old", "/new", 301)  # relative Location
    answers["https://ex.com/new"] = _page("https://ex.com/new")
    result = site_graph.fetch_url("http://ex.com/old")
    assert result["error"] is None and result["status"] == 200
    assert result["final_url"] == "https://ex.com/new" and "<h1>H</h1>" in result["html"]
    assert requested == ["http://ex.com/old", "https://ex.com/old", "https://ex.com/new"]


def test_a_redirect_loop_stops_at_the_limit(net):
    answers, requested = net
    answers["https://ex.com/a"] = _redirect("https://ex.com/a", "https://ex.com/b")
    answers["https://ex.com/b"] = _redirect("https://ex.com/b", "https://ex.com/a")
    result = site_graph.fetch_url("https://ex.com/a")
    assert result["error"] == f"too many redirects (over {site_graph.MAX_REDIRECTS})"
    assert len(requested) == site_graph.MAX_REDIRECTS + 1


def test_a_redirect_status_without_location_is_the_answer(net):
    answers, _ = net
    answers["https://ex.com/r"] = _Resp("https://ex.com/r", 302, {"Content-Type": "text/html"})
    result = site_graph.fetch_url("https://ex.com/r")
    assert result["status"] == 302 and result["error"] == "HTTP 302"


@pytest.mark.parametrize("location", ["http://ex.com:99999/", "http://ex.com:abc/"])
def test_a_malformed_port_in_location_is_refused_not_raised(net, location):
    answers, _ = net
    answers["https://ex.com/p"] = _redirect("https://ex.com/p", location)
    result = site_graph.fetch_url("https://ex.com/p")
    assert "invalid port" in result["error"]


@pytest.mark.parametrize("url", ["http://ex.com:99999/", "http://ex.com:abc/", "https://ex.com:-1/"])
def test_validate_url_refuses_a_malformed_port(url):
    result = url_safety.validate_url(url, resolve_dns=False)
    assert result.ok is False and result.reason == "invalid port"


def test_validate_url_keeps_a_valid_port(monkeypatch):
    result = url_safety.validate_url("https://example.com:8443/a", resolve_dns=False)
    assert result.ok and result.normalized_url == "https://example.com:8443/a"


def test_fetch_page_no_longer_crashes_on_a_malformed_port_redirect(monkeypatch):
    """fetch_page.py validates each hop itself; the ValueError used to escape its try block."""
    class Session:
        def get(self, url, **kw):
            return _redirect(url, "http://ex.com:99999/")

    monkeypatch.setattr(fetch_page.requests, "Session", Session)
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host: [PUBLIC_IP])
    result = fetch_page.fetch_page("https://ex.com/")
    assert "invalid port" in result["error"]


# --- 2. robots.txt is read, and the sitemaps it declares are used --------------

ROBOTS = "User-agent: *\nDisallow: /admin\n\nSitemap: https://ex.com/custom-map.xml\n"
SITEMAP = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           "<url><loc>https://ex.com/</loc></url><url><loc>https://ex.com/pricing</loc>"
           "<lastmod>2026-09-01</lastmod></url></urlset>")


def test_robots_txt_served_as_text_plain_is_read(net):
    answers, _ = net
    answers["https://ex.com/robots.txt"] = _page("https://ex.com/robots.txt", ROBOTS, "text/plain; charset=utf-8")
    result = site_graph.fetch_url("https://ex.com/robots.txt", plain_text=True)
    assert result["error"] is None and "Sitemap: https://ex.com/custom-map.xml" in result["html"]


def test_a_sitemap_declared_only_in_robots_txt_is_found(net):
    """The repro: a sitemap at a path none of the four guesses cover."""
    answers, requested = net
    answers["https://ex.com/robots.txt"] = _page("https://ex.com/robots.txt", ROBOTS, "text/plain")
    answers["https://ex.com/custom-map.xml"] = _page("https://ex.com/custom-map.xml", SITEMAP, "application/xml")
    out = site_graph.discover_sitemap("https://ex.com/")
    assert out["found"] is True and out["complete"] is True, out["reasons"]
    assert set(out["urls"]) == {"https://ex.com/", "https://ex.com/pricing"}
    assert out["urls"]["https://ex.com/pricing"]["lastmod"] == "2026-09-01"
    # Declared in robots.txt, so the usual paths are not guessed at once it loads.
    assert "https://ex.com/sitemap.xml" not in requested


def test_robots_txt_behind_a_redirect_is_still_read(net):
    answers, _ = net
    answers["https://ex.com/robots.txt"] = _redirect("https://ex.com/robots.txt", "https://www.ex.com/robots.txt", 301)
    answers["https://www.ex.com/robots.txt"] = _page("https://www.ex.com/robots.txt", ROBOTS, "text/plain")
    answers["https://ex.com/custom-map.xml"] = _page("https://ex.com/custom-map.xml", SITEMAP, "application/xml")
    assert site_graph.discover_sitemap("https://ex.com/")["found"] is True


def test_a_declared_sitemap_that_fails_is_a_stated_reason(net):
    """It used to vanish without a trace, reading as 'no sitemap' rather than 'sitemap broken'."""
    answers, _ = net
    answers["https://ex.com/robots.txt"] = _page("https://ex.com/robots.txt", ROBOTS, "text/plain")
    out = site_graph.discover_sitemap("https://ex.com/")
    assert out["found"] is False and out["complete"] is False
    assert any(r.startswith("sitemap declared in robots.txt unreadable: https://ex.com/custom-map.xml")
               for r in out["reasons"]), out["reasons"]


def test_a_second_declared_sitemap_that_fails_is_not_called_a_child(net):
    answers, _ = net
    robots = ROBOTS + "Sitemap: https://ex.com/news-map.xml\n"
    answers["https://ex.com/robots.txt"] = _page("https://ex.com/robots.txt", robots, "text/plain")
    answers["https://ex.com/custom-map.xml"] = _page("https://ex.com/custom-map.xml", SITEMAP, "application/xml")
    out = site_graph.discover_sitemap("https://ex.com/")
    assert out["found"] is True and out["complete"] is False
    assert any(r.startswith("sitemap declared in robots.txt unreadable: https://ex.com/news-map.xml")
               for r in out["reasons"]), out["reasons"]


def test_a_declared_sitemap_that_is_not_xml_makes_discovery_incomplete(net):
    answers, _ = net
    robots = ROBOTS + "Sitemap: https://ex.com/sitemap.txt\n"
    answers["https://ex.com/robots.txt"] = _page("https://ex.com/robots.txt", robots, "text/plain")
    answers["https://ex.com/custom-map.xml"] = _page("https://ex.com/custom-map.xml", SITEMAP, "application/xml")
    answers["https://ex.com/sitemap.txt"] = _page("https://ex.com/sitemap.txt", "https://ex.com/a\n", "application/xml")
    out = site_graph.discover_sitemap("https://ex.com/")
    assert out["complete"] is False
    assert any("sitemap.txt" in r and "not XML" in r for r in out["reasons"]), out["reasons"]


def test_a_missing_guess_is_still_not_an_error(net):
    """No robots.txt, nothing at the usual paths: 'no sitemap', with no per-guess noise."""
    out = site_graph.discover_sitemap("https://ex.com/")
    assert out["found"] is False and out["sources"] == []
    assert out["reasons"] == ["no sitemap found in robots.txt or at the usual paths"]


def test_a_crawled_page_served_as_text_plain_is_still_not_a_page(net):
    """plain_text is for robots.txt only: the crawl's rule for pages is unchanged."""
    answers, _ = net
    answers["https://ex.com/notes"] = _page("https://ex.com/notes", "just text", "text/plain")
    result = site_graph.fetch_url("https://ex.com/notes")
    assert result["html"] == "" and result["error"].startswith("non-HTML content-type")


# --- 3. the same defect in the other scripts that validate, then follow --------
#
# page_network.py validated the llms.txt URL and then called requests.get with its
# default allow_redirects=True; link_profile.py validated and then used urlopen,
# which follows redirects on its own. Both now check every hop.

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

import requests  # noqa: E402  (page_network imports it inside the function)

import link_profile  # noqa: E402
import page_network  # noqa: E402


def test_get_validated_is_the_shared_walker(monkeypatch):
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host: DNS[host])
    calls = []
    hops = {"https://ex.com/a": _redirect("https://ex.com/a", "https://cdn.ex.com/b"),
            "https://cdn.ex.com/b": _page("https://cdn.ex.com/b")}
    resp, error = url_safety.get_validated(lambda u: (calls.append(u), hops[u])[1], "https://ex.com/a")
    assert error is None and resp.url == "https://cdn.ex.com/b" and calls == list(hops)
    hops["https://cdn.ex.com/b"] = _redirect("https://cdn.ex.com/b", "http://10.1.2.3/")
    resp, error = url_safety.get_validated(lambda u: hops[u], "https://ex.com/a")
    assert resp is None and "10.1.2.3" in error and "redirect 2" in error


def test_page_network_llms_txt_redirect_into_private_network_is_refused(monkeypatch):
    requested = []

    def get(url, **kw):
        assert kw.get("allow_redirects") is False
        requested.append(url)
        return _redirect(url, "http://169.254.169.254/latest/meta-data/")

    monkeypatch.setattr(url_safety, "_resolve_host", lambda host: DNS[host])
    monkeypatch.setattr(requests, "get", get)
    out = page_network.fetch_llms_txt("https://ex.com/llms.txt")
    assert "169.254.169.254" in out["error"] and requested == ["https://ex.com/llms.txt"]


def test_page_network_llms_txt_is_read_through_a_public_redirect(monkeypatch):
    hops = {"https://ex.com/llms.txt": _redirect("https://ex.com/llms.txt", "https://www.ex.com/llms.txt", 301),
            "https://www.ex.com/llms.txt": _page("https://www.ex.com/llms.txt", "# Ex\n- [API](https://ex.com/api)", "text/plain")}
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host: DNS[host])
    monkeypatch.setattr(requests, "get", lambda u, **kw: hops[u])
    for resp in hops.values():
        resp.ok = resp.status_code < 400
    out = page_network.fetch_llms_txt("https://ex.com/llms.txt")
    assert out["status"] == 200 and "[API]" in out["text"]


def _redirect_request(newurl):
    handler = link_profile._ValidatingRedirectHandler()
    req = urllib.request.Request("https://ex.com/page")
    return handler.redirect_request(req, None, 302, "Found", {}, newurl)


def test_link_profile_refuses_a_redirect_into_a_private_network(monkeypatch):
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host: DNS[host])
    for target in ("http://169.254.169.254/latest/meta-data/", "https://rebind.ex.com/", "http://127.0.0.1/"):
        with pytest.raises(urllib.error.URLError, match="URL safety check failed"):
            _redirect_request(target)


def test_link_profile_follows_a_public_redirect(monkeypatch):
    monkeypatch.setattr(url_safety, "_resolve_host", lambda host: DNS[host])
    assert _redirect_request("https://www.ex.com/new").full_url == "https://www.ex.com/new"


def test_link_profile_fetches_through_the_validating_opener():
    """urlopen would install no handler: the module must open through its own."""
    handlers = [type(h) for h in link_profile._open.__self__.handlers]
    assert link_profile._ValidatingRedirectHandler in handlers
    assert urllib.request.HTTPRedirectHandler not in handlers
