"""Regression tests for defects a review found in the Google-data scripts.

One test (or group) per defect, named after the real case. Nothing here calls a Google
API or signs in: responses are the documented shapes, services and clients are fakes.
"""

import csv
import json
import os
import sys
import types
from datetime import date

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import conversion_reconcile as cr  # noqa: E402
import crux_history  # noqa: E402
import google_auth as ga  # noqa: E402
import gsc_ai_import  # noqa: E402
import gsc_insights as gi  # noqa: E402
import gsc_query as gq  # noqa: E402
import index_coverage_diff as icd  # noqa: E402

CRED_ENV = ("GOOGLE_APPLICATION_CREDENTIALS", "GSC_CREDENTIALS", "GA4_CREDENTIALS", "GSC_CLIENT_SECRETS",
            "PAGESPEED_API_KEY", "GOOGLE_API_KEY", "XDG_CONFIG_HOME")


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Isolated config dir and skill folder; no credential env vars from the developer's shell."""
    for var in CRED_ENV + (ga._REEXEC_GUARD,):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ULTIMATE_SEO_GEO_HOME", str(tmp_path / "cfg"))
    monkeypatch.setattr(ga, "legacy_token_path", lambda: str(tmp_path / "skill" / "gsc-oauth-token.json"))
    monkeypatch.setattr(ga, "REPO_ROOT", str(tmp_path / "skill"))
    return tmp_path


def saved_login(home, scopes):
    path = home / "cfg" / "gsc-token.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"token": "access", "refresh_token": "refresh", "client_id": "cid",
                                "client_secret": "cs", "token_uri": "https://oauth2.googleapis.com/token",
                                "scopes": scopes, "expiry": "2099-01-01T00:00:00Z"}))
    return path


# --- 1. crux_history: densities are plain floats, "NaN" for missing periods -------------

# Shape of a real records:queryHistoryRecord response (trimmed to 4 periods): densities and
# p75s are bare values, a period without data is the string "NaN", CLS p75s are strings.
CRUX_HISTORY_RESPONSE = {
    "record": {
        "key": {"origin": "https://example.com"},
        "metrics": {
            "largest_contentful_paint": {
                "histogramTimeseries": [
                    {"start": 0, "end": 2500, "densities": [0.8123, "NaN", 0.8311, 0.8402]},
                    {"start": 2500, "end": 4000, "densities": [0.1204, "NaN", 0.1105, 0.1003]},
                    {"start": 4000, "densities": [0.0673, "NaN", 0.0584, 0.0602]},
                ],
                "percentilesTimeseries": {"p75s": [2210, "NaN", 2105, None]},
            },
            "cumulative_layout_shift": {
                "histogramTimeseries": [
                    {"start": "0.00", "end": "0.10", "densities": [0.9, 0.91, "NaN", 0.92]},
                    {"start": "0.10", "end": "0.25", "densities": [0.06, 0.05, "NaN", 0.05]},
                    {"start": "0.25", "densities": [0.04, 0.04, "NaN", 0.03]},
                ],
                "percentilesTimeseries": {"p75s": ["0.05", "0.04", "NaN", "0.03"]},
            },
        },
        "collectionPeriods": [
            {"firstDate": {"year": 2026, "month": 3, "day": d}, "lastDate": {"year": 2026, "month": 3, "day": d + 27}}
            for d in (1, 8, 15, 22)
        ],
    },
}


def test_crux_history_parses_float_densities_with_nan_periods():
    result = crux_history.parse_history(CRUX_HISTORY_RESPONSE)
    lcp = result["metrics"]["LCP"]
    assert lcp["good_pct_timeseries"] == [81.2, None, 83.1, 84.0]  # a missing period is None, not 0
    assert lcp["needs_improvement_pct_timeseries"] == [12.0, None, 11.1, 10.0]
    assert lcp["poor_pct_timeseries"] == [6.7, None, 5.8, 6.0]
    assert lcp["p75_timeseries"] == [2210, None, 2105, None]
    cls = result["metrics"]["CLS"]
    assert cls["good_pct_timeseries"] == [90.0, 91.0, None, 92.0]
    assert cls["p75_timeseries"] == ["0.05", "0.04", None, "0.03"]
    assert result["period_count"] == 4


def test_crux_history_prints_missing_periods_as_no_data(capsys):
    crux_history.print_human(crux_history.parse_history(CRUX_HISTORY_RESPONSE))
    out = capsys.readouterr().out
    assert "2.2s" in out and "n/a (no data)" in out
    assert "None" not in out


def test_crux_history_metric_filter_still_applies():
    result = crux_history.parse_history(CRUX_HISTORY_RESPONSE, metrics_filter=["cumulative_layout_shift"])
    assert list(result["metrics"]) == ["CLS"]


# --- 2-4. gsc_insights human basis --------------------------------------------------

AD_FRAUD = "https://improvado.io/blog/best-ad-fraud-detection-software"
BLOG = "https://improvado.io/blog/looker-studio"


def row(query, clicks, impressions, position, page=BLOG):
    return {"query": query, "page": page, "clicks": clicks, "impressions": impressions,
            "ctr": clicks / impressions if impressions else 0.0, "position": position}


SEP = [row("improvado", 321, 800, 1.5), row("looker studio", 37, 38_056, 7.1),
       row("ad fraud", 1, 191_486, 5.5, AD_FRAUD), row("ad fraud detection software", 0, 237_872, 2.1, AD_FRAUD)]


def test_non_human_finding_when_the_previous_window_has_no_rows(capsys):
    # A new property, or a --replay file saved with an empty previous window: position change is None.
    dataset = {"site_url": "sc-domain:improvado.io", "windows": {"current": ["2026-09-02", "2026-09-15"]},
               "query_page": {"rows": SEP}, "query_page_previous": {"rows": []}, "pages": {}}
    out = gi.analyse(dataset, {"human_basis", "topic_spikes"})
    assert out["human_basis"]["change"]["blended"]["position"] is None
    issue = next(i for i in out["issues"] if i["code"] == "non_human_queries")
    assert "n/a" in issue["finding"]
    assert "of the apparent gain" not in issue["finding"]
    gi.print_human(out)
    assert "position n/a blended, n/a human" in capsys.readouterr().out


def test_non_human_finding_when_every_query_is_machine(capsys):
    rows = [row("ad fraud", 1, 191_486, 5.5, AD_FRAUD), row("ad fraud detection software", 0, 237_872, 2.1, AD_FRAUD)]
    out = gi.analyse({"site_url": "sc-domain:improvado.io", "query_page": {"rows": rows}, "pages": {}}, {"human_basis"})
    assert out["human_basis"]["current"]["human"]["ctr"] is None
    issue = next(i for i in out["issues"] if i["code"] == "non_human_queries")
    assert "human n/a" in issue["evidence"]
    gi.print_human(out)
    assert "Human basis: 100%" in capsys.readouterr().out


# Blended position improves because a machine query arrives at position 1, while the one
# human query slips from 5.0 to 6.0. The old ratio (bp - hp) / bp read as 132%.
WORSE_PREV = [row("looker studio", 40, 10_000, 5.0)]
WORSE_NOW = [row("looker studio", 40, 10_000, 6.0), row("site:improvado.io looker", 0, 3_000, 1.0)]


def test_human_position_worsened_while_blended_improved_is_not_a_share_over_100():
    result = gi.human_basis(WORSE_NOW, gi.classify_queries(WORSE_NOW), WORSE_PREV)
    change = result["change"]
    assert change["blended"]["position"] < 0 < change["human"]["position"]
    assert change["position_gain_from_non_human"] == 1.0
    assert change["human_position_worsened"] is True


def test_human_position_worsened_finding_says_so():
    dataset = {"query_page": {"rows": WORSE_NOW}, "query_page_previous": {"rows": WORSE_PREV}, "pages": {}}
    out = gi.analyse(dataset, {"human_basis"})
    issue = next(i for i in out["issues"] if i["code"] == "non_human_queries")
    assert "human position worsened while blended improved" in issue["finding"]
    assert "132%" not in issue["finding"] and "of the apparent gain is" not in issue["finding"]


def test_share_of_gain_stays_between_0_and_1_when_human_also_improved():
    prev = [row("looker studio", 40, 10_000, 6.0)]
    now = [row("looker studio", 40, 10_000, 5.5), row("site:improvado.io looker", 0, 3_000, 1.0)]
    change = gi.human_basis(now, gi.classify_queries(now), prev)["change"]
    assert 0 <= change["position_gain_from_non_human"] <= 1
    assert "human_position_worsened" not in change


def test_spike_topic_queries_are_set_aside_in_the_previous_window_too(monkeypatch):
    # 'ad tech' passes the per-query rules in both windows; the topic-spike verdict sets it aside.
    # The previous window must lose it as well, or the human basis compares different query sets.
    prev = [row("improvado", 300, 800, 1.5), row("ad tech", 2, 5_000, 8.0)]
    now = [row("improvado", 321, 800, 1.5), row("ad tech", 3, 90_000, 4.0)]
    spike = {"verdict": "machine-suspect", "_members": ["ad tech"]}
    monkeypatch.setattr(gi, "topic_spikes", lambda rows, prev_rows, labels, limit=None: {
        "criteria": "", "count": 1, "items": [dict(spike)], "_all": [spike]})
    out = gi.analyse({"query_page": {"rows": now}, "query_page_previous": {"rows": prev}, "pages": {}},
                     {"human_basis"})
    hb = out["human_basis"]
    assert hb["current"]["machine"]["impressions"] == 90_000
    assert hb["previous"]["machine"]["impressions"] == 5_000
    assert hb["previous"]["human"]["impressions"] == 800


# --- 5. inclusive date windows ---------------------------------------------------------

class FakeGSC:
    """Search Analytics fake: pages through rows with startRow/rowLimit like the API."""

    def __init__(self, rows):
        self.rows = rows
        self.bodies = []

    def searchanalytics(self):
        return self

    def query(self, siteUrl, body):
        self.bodies.append(body)
        self._body = body
        return self

    def execute(self):
        start = self._body.get("startRow", 0)
        return {"rows": self.rows[start:start + self._body["rowLimit"]]}


def run_gsc_query(monkeypatch, capsys, rows, argv):
    service = FakeGSC(rows)
    monkeypatch.setattr(gq, "_load_credentials", lambda: object())
    monkeypatch.setattr(gq, "_build_service", lambda creds: service)
    monkeypatch.setattr(sys, "argv", ["gsc_query.py", *argv, "--json"])
    gq.main()
    return json.loads(capsys.readouterr().out), service


def test_gsc_query_days_28_is_28_days_inclusive(monkeypatch, capsys):
    out, service = run_gsc_query(monkeypatch, capsys, [], ["sc-domain:x.com", "--days", "28", "--end-date", "2026-09-25"])
    assert service.bodies[0]["startDate"] == "2026-08-29"  # Aug 29 .. Sep 25 is 28 days
    assert service.bodies[0]["endDate"] == "2026-09-25"
    assert (date.fromisoformat(out["end_date"]) - date.fromisoformat(out["start_date"])).days + 1 == 28


def test_gsc_query_window_matches_gsc_insights():
    end = date(2026, 9, 25)
    assert gq.date_window(28, end_date=end.isoformat()) == gi.window(end, 28)


def test_ga4_report_days_28_is_28_days_inclusive(monkeypatch, capsys):
    import ga4_report
    seen = {}

    def fake_report(**kwargs):
        seen.update(kwargs)
        return {"rows": []}

    monkeypatch.setattr(ga4_report, "run_ga4_report", fake_report)
    monkeypatch.setattr(ga4_report, "print_human", lambda result: None)
    monkeypatch.setattr(sys, "argv", ["ga4_report.py", "--property", "1", "--days", "28", "--end-date", "2026-09-25"])
    ga4_report.main()
    assert seen["start_date"] == "2026-08-29" and seen["end_date"] == "2026-09-25"


# --- 6. --top-queries N is the top N by impressions ------------------------------------

def api_row(query, clicks, impressions, position):
    return {"keys": [query], "clicks": clicks, "impressions": impressions,
            "ctr": clicks / impressions, "position": position}


# In click order, as the API returns them: the query with most impressions has few clicks.
BY_CLICKS = [api_row("improvado", 321, 800, 1.5), api_row("improvado pricing", 90, 1_200, 1.2),
             api_row("marketing data warehouse", 4, 61_000, 9.8), api_row("looker studio", 3, 38_056, 7.1)]


def test_top_queries_ranks_every_row_by_impressions(monkeypatch, capsys):
    out, service = run_gsc_query(monkeypatch, capsys, BY_CLICKS, ["sc-domain:x.com", "--top-queries", "2"])
    assert [r["query"] for r in out["rows"]] == ["marketing data warehouse", "looker studio"]
    assert service.bodies[0]["rowLimit"] == gq.API_MAX_ROWS
    assert out["truncated"] is False


def test_top_queries_pages_through_more_than_one_request(monkeypatch, capsys):
    monkeypatch.setattr(gq, "API_MAX_ROWS", 2)
    out, service = run_gsc_query(monkeypatch, capsys, BY_CLICKS, ["sc-domain:x.com", "--top-queries", "1"])
    assert [b.get("startRow", 0) for b in service.bodies] == [0, 2, 4]
    assert out["rows"][0]["query"] == "marketing data warehouse"


def test_top_queries_reports_the_row_cap(monkeypatch, capsys):
    monkeypatch.setattr(gq, "API_MAX_ROWS", 2)
    monkeypatch.setattr(gq, "TOP_N_MAX_ROWS", 2)
    raw, truncated = gq.fetch_all_rows(FakeGSC(BY_CLICKS), "sc-domain:x.com", "2026-09-01", "2026-09-28", ["query"])
    assert truncated is True and len(raw["rows"]) == 2


# --- 7. index coverage: every Search Console reason in its own bucket -----------------

@pytest.mark.parametrize("reason,key,klass", [
    ("Indexed, though blocked by robots.txt", "indexed, though blocked by robots.txt", "expected"),
    ("Blocked by robots.txt", "url blocked by robots.txt", "technical"),
    ("Blocked due to other 4xx issue", "url blocked due to other 4xx issue", "technical"),
    ("Excluded by ‘noindex’ tag", "url marked 'noindex'", "technical"),
    ("Duplicate, Google chose different canonical than user", "duplicate, google chose different canonical", "quality"),
    ("Blocked due to access forbidden (403)", "blocked due to access forbidden (403)", "technical"),
    ("Not found (404)", "not found (404)", "technical"),
])
def test_page_indexing_reason_maps_to_its_own_bucket(reason, key, klass):
    assert icd.canonical_reason(reason) == key
    assert icd.REASONS[key][0] == klass


def test_indexed_though_blocked_is_not_summed_into_blocked_by_robots(tmp_path):
    folder = tmp_path / "export"
    folder.mkdir()
    with open(folder / "Critical issues.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Reason", "Source", "Validation", "Pages"])
        w.writerow(["Blocked by robots.txt", "Website", "Not Started", "30"])
        w.writerow(["Blocked due to other 4xx issue", "Website", "Not Started", "7"])
    with open(folder / "Non-critical issues.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Reason", "Source", "Validation", "Pages"])
        w.writerow(["Indexed, though blocked by robots.txt", "Website", "Not Started", "1,200"])
    reasons = icd.load_export(str(folder))["reasons"]
    assert reasons["url blocked by robots.txt"]["pages"] == 30
    assert reasons["indexed, though blocked by robots.txt"]["pages"] == 1_200
    assert reasons["url blocked due to other 4xx issue"]["pages"] == 7


# --- 8. conversion_reconcile: GA4 UI export with a comment block and a blank line ------

GA4_UI_EXPORT = """# ----------------------------------------
# Key events
# Account: Improvado
# Property: improvado.io - GA4
# ----------------------------------------
#
# All Users
# Start date: 20260101
# End date: 20260331
# ----------------------------------------

Year month,Key events
202601,410
202602,388
202603,"1,025"
"""


def test_ga4_ui_export_with_comment_block_and_blank_line_loads(tmp_path):
    path = tmp_path / "ga4.csv"
    path.write_text(GA4_UI_EXPORT, encoding="utf-8")
    assert cr.load_ga4(str(path)) == {"2026-01": 410, "2026-02": 388, "2026-03": 1025}


# --- 9. gsc_ai_import: locale separators and unparseable impressions -----------------

@pytest.mark.parametrize("raw,expected", [
    ("1,234", 1234), ("1.234", 1234), ("1 234", 1234), ("1 234", 1234), ("1 234", 1234),
    ("1.234.567", 1234567), ("1,234.0", 1234), ("1.234,0", 1234), ("987", 987), ("", 0),
    ("n/a", None), ("—", None),
])
def test_ai_report_impressions_in_every_locale(raw, expected):
    assert gsc_ai_import._parse_impressions(raw) == expected


def test_ai_report_counts_unparseable_impressions_instead_of_zeroing(tmp_path, capsys):
    path = tmp_path / "ai.csv"
    path.write_text("Top pages,Impressions\nhttps://x.com/a,1.234\nhttps://x.com/b,n/a\nhttps://x.com/c,1 000\n",
                    encoding="utf-8")
    result = gsc_ai_import.import_ai_csv(str(path))
    assert result["total_impressions"] == 2234
    assert result["row_count"] == 2
    assert result["unparseable_impressions"]["count"] == 1
    assert result["unparseable_impressions"]["rows"][0] == {"line": 3, "value": "n/a", "page": "https://x.com/b"}
    gsc_ai_import.print_human(result, 25)
    assert "Warning: 1 rows have an impressions value that is not a number" in capsys.readouterr().out


# --- 10. gsc_export: a failed sitemap fetch names its cause ---------------------------

def test_gsc_export_sitemap_fetch_error_is_surfaced(monkeypatch):
    import gsc_export
    import requests

    def refuse(url, **kwargs):
        raise requests.ConnectionError("Failed to resolve 'exmaple.com'")

    monkeypatch.setattr(gsc_export.requests, "get", refuse)
    with pytest.raises(SystemExit) as exc:
        gsc_export.urls_from_sitemap("https://exmaple.com/sitemap.xml", max_urls=10)
    assert "Failed to resolve 'exmaple.com'" in str(exc.value)


def test_gsc_export_broken_child_sitemap_warns_and_keeps_the_rest(monkeypatch, capsys):
    import gsc_export
    import requests
    bodies = {
        "https://x.com/sitemap.xml": "<sitemapindex><sitemap><loc>https://x.com/a.xml</loc></sitemap>"
                                     "<sitemap><loc>https://x.com/b.xml</loc></sitemap></sitemapindex>",
        "https://x.com/a.xml": "<urlset><url><loc>https://x.com/page</loc></url></urlset>",
    }

    class Resp:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    def get(url, **kwargs):
        if url not in bodies:
            raise requests.HTTPError("404 Client Error: Not Found for url: " + url)
        return Resp(bodies[url])

    monkeypatch.setattr(gsc_export.requests, "get", get)
    assert gsc_export.urls_from_sitemap("https://x.com/sitemap.xml", max_urls=10) == ["https://x.com/page"]
    assert "could not read child sitemap https://x.com/b.xml" in capsys.readouterr().err


# --- 11. GA4 credentials: opt-in login --ga4 ------------------------------------------

def test_login_ga4_flag_requests_the_analytics_scope(monkeypatch, capsys):
    seen = {}

    def fake_login(client_secrets=None, no_browser=False, token=None, ga4=False):
        seen["ga4"] = ga4
        return {"ok": True, "scopes": ga.login_scopes(ga4)}

    monkeypatch.setattr(ga, "login", fake_login)
    assert ga.main(["login", "--ga4"]) == 0
    assert seen["ga4"] is True
    assert json.loads(capsys.readouterr().out)["scopes"] == [
        "https://www.googleapis.com/auth/webmasters.readonly", "https://www.googleapis.com/auth/analytics.readonly"]
    assert ga.main(["login"]) == 0
    assert seen["ga4"] is False
    assert ga.login_scopes() == ga.GSC_SCOPES


def test_login_ga4_passes_both_scopes_to_the_flow(home, monkeypatch):
    flow_mod = pytest.importorskip("google_auth_oauthlib.flow")
    monkeypatch.setattr(ga, "BUNDLED_CLIENT_ID", "cid")
    monkeypatch.setattr(ga, "BUNDLED_CLIENT_SECRET", "cs")
    seen = {}

    class Creds:
        def to_json(self):
            return "{}"

    class Flow:
        def run_local_server(self, **kwargs):
            return Creds()

    def from_client_config(config, scopes):
        seen["scopes"] = scopes
        return Flow()

    monkeypatch.setattr(flow_mod.InstalledAppFlow, "from_client_config", staticmethod(from_client_config))
    monkeypatch.setattr(ga, "list_properties", lambda creds: [])
    out = ga.login(ga4=True)
    assert seen["scopes"] == ga.GSC_SCOPES + ga.GA4_SCOPES == out["scopes"]


def test_gsc_only_login_asked_for_ga4_says_login_ga4(home):
    saved_login(home, ga.GSC_SCOPES)
    with pytest.raises(ga.AuthError, match=r"google_auth\.py login --ga4"):
        ga.load_credentials(ga.GA4_SCOPES, token_env="GA4_CREDENTIALS")


def test_not_signed_in_for_ga4_says_login_ga4(home):
    with pytest.raises(ga.AuthError, match=r"Google Analytics[\s\S]*login --ga4"):
        ga.load_credentials(ga.GA4_SCOPES, token_env="GA4_CREDENTIALS")


def test_ga4_login_token_loads_for_ga4_and_keeps_both_scopes(home):
    pytest.importorskip("google.oauth2.credentials")
    saved_login(home, ga.GSC_SCOPES + ga.GA4_SCOPES)
    creds, source = ga.load_credentials(ga.GA4_SCOPES, token_env="GA4_CREDENTIALS")
    assert source["kind"] == "oauth_login"
    assert set(creds.scopes) == set(ga.GSC_SCOPES + ga.GA4_SCOPES)
    creds, _ = ga.load_credentials()  # the Search Console scripts still read the same token
    assert set(ga.GSC_SCOPES) <= set(creds.scopes)


def fake_ga4_library(monkeypatch):
    built = {}

    class BetaAnalyticsDataClient:
        def __init__(self, credentials=None):
            built["credentials"] = credentials

    data = types.ModuleType("google.analytics.data_v1beta")
    data.BetaAnalyticsDataClient = BetaAnalyticsDataClient
    typ = types.ModuleType("google.analytics.data_v1beta.types")
    for name in ("DateRange", "Dimension", "FilterExpression", "Filter", "Metric", "RunReportRequest"):
        setattr(typ, name, object)
    data.types = typ
    analytics = types.ModuleType("google.analytics")
    analytics.data_v1beta = data
    monkeypatch.setitem(sys.modules, "google.analytics", analytics)
    monkeypatch.setitem(sys.modules, "google.analytics.data_v1beta", data)
    monkeypatch.setitem(sys.modules, "google.analytics.data_v1beta.types", typ)
    return built


def test_ga4_client_falls_back_to_the_saved_google_auth_login(home, monkeypatch):
    import ga4_report
    built = fake_ga4_library(monkeypatch)
    monkeypatch.setattr(ga4_report, "REPO_ROOT", str(home / "skill"))  # no ga4-oauth-token.json there
    saved_login(home, ga.GSC_SCOPES + ga.GA4_SCOPES)
    creds = object()
    calls = []

    def fake_load(scopes=None, token_env="GSC_CREDENTIALS"):
        calls.append((scopes, token_env))
        return creds, {"kind": "oauth_login", "path": ga.token_path()}

    monkeypatch.setattr(ga, "load_credentials", fake_load)
    ga4_report._load_ga4_client("123")
    assert built["credentials"] is creds
    assert calls == [(["https://www.googleapis.com/auth/analytics.readonly"], "GA4_CREDENTIALS")]


def test_ga4_client_without_any_credentials_points_to_login_ga4(home, monkeypatch, capsys):
    import ga4_report
    fake_ga4_library(monkeypatch)
    monkeypatch.setattr(ga4_report, "REPO_ROOT", str(home / "skill"))
    with pytest.raises(SystemExit):
        ga4_report._load_ga4_client("123")
    msg = json.loads(capsys.readouterr().out)["error"]
    assert "google_auth.py login --ga4" in msg
    assert "GCP" not in msg and "Google Cloud" not in msg


def test_ga4_client_still_uses_ga4_credentials_token(home, monkeypatch):
    import ga4_report
    creds_mod = pytest.importorskip("google.oauth2.credentials")
    built = fake_ga4_library(monkeypatch)
    token = home / "ga4.json"
    token.write_text("{}")
    monkeypatch.setenv("GA4_CREDENTIALS", str(token))
    sentinel = types.SimpleNamespace(expired=False, refresh_token="r")
    monkeypatch.setattr(creds_mod.Credentials, "from_authorized_user_file",
                        classmethod(lambda cls, path, scopes=None: sentinel))
    ga4_report._load_ga4_client("123")
    assert built["credentials"] is sentinel


def test_google_analytics_data_is_in_both_package_lists():
    with open(os.path.join(ROOT, "requirements-gsc.txt"), encoding="utf-8") as fh:
        pinned = [line.strip() for line in fh if line.strip() and not line.startswith("#")]
    assert any(p.startswith("google-analytics-data") for p in pinned)
    assert any(p.startswith("google-analytics-data") for p in ga.GOOGLE_PACKAGES)


def test_api_tier_ga4_guidance_is_setup_then_login_ga4(home, monkeypatch):
    import google_api_tier
    monkeypatch.setattr(google_api_tier, "REPO_ROOT", str(home / "skill"))
    result = google_api_tier.detect_tier()
    ga4 = next(u for u in result["unavailable_apis"] if u["api"] == "ga4")
    assert "google_auth.py setup" in ga4["setup"] and "google_auth.py login --ga4" in ga4["setup"]
    assert "GCP" not in ga4["setup"] and "Create OAuth credentials" not in ga4["setup"]


def test_api_tier_counts_a_login_ga4_token_and_not_a_gsc_only_one(home, monkeypatch):
    import google_api_tier
    monkeypatch.setattr(google_api_tier, "REPO_ROOT", str(home / "skill"))
    saved_login(home, ga.GSC_SCOPES)
    assert "ga4" not in google_api_tier.detect_tier()["available_apis"]
    saved_login(home, ga.GSC_SCOPES + ga.GA4_SCOPES)
    assert "ga4" in google_api_tier.detect_tier()["available_apis"]


def test_ga4_token_in_the_skill_folder_is_gitignored():
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        assert "ga4-oauth-token.json" in {line.strip() for line in fh}
