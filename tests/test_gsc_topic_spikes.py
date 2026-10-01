"""gsc_insights.py --topic-spikes: which topics jumped, and whether people or machines moved them.

Rows are real queries from a B2B SaaS client audit (Aug 18-31 vs Sep 2-15 2026). On the full
28,768 rows the analysis finds the ad-fraud topic (36 queries, 1,836 -> 1,052,907 impressions,
1 click: machine-suspect) and a news topic the report never mentioned ('astra' / 'claude fable':
105 queries, 0 -> 13,089 impressions, 268 clicks: real interest).
"""

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import gsc_insights as gi  # noqa: E402

FRAUD_POST = "https://acme-analytics.example/blog/best-ad-fraud-detection-software"
AD_FRAUD = "https://acme-analytics.example/blog/ad-fraud"
NEWS = "https://acme-analytics.example/blog/claude-fable-5-1"
BLOG = "https://acme-analytics.example/blog/looker-studio"


def row(query, clicks, impressions, position, page=BLOG):
    return {"query": query, "page": page, "clicks": clicks, "impressions": impressions,
            "ctr": clicks / impressions if impressions else 0.0, "position": position}


BEFORE = [
    row("ad fraud detection software", 0, 921, 4.0, FRAUD_POST),
    row("ad fraud", 2, 7_158, 9.0, AD_FRAUD),
    row("click fraud detection", 0, 186, 12.0, AD_FRAUD),
    row("looker studio", 40, 30_000, 7.5),
    row("acme", 401, 772, 1.4),
]
AFTER = [
    row("ad fraud detection software", 0, 237_872, 2.1, FRAUD_POST),
    row("ad fraud", 1, 191_486, 5.5, AD_FRAUD),
    row("ad fraud protection platform", 0, 77_830, 2.7, FRAUD_POST),
    row("mrc accredited fraud detection", 0, 7_384, 8.3, FRAUD_POST),   # alone: P ~ 6e-4, stays human per query
    row("click fraud detection", 0, 66_320, 8.7, AD_FRAUD),
    row("click fraud software", 0, 31_289, 8.2, AD_FRAUD),
    row("click fraud prevention tool", 0, 2_100, 9.0, AD_FRAUD),
    # 'ad' then covers more impressions than 'fraud', as on the real data, so the first pass
    # takes the ad queries and leaves the click-fraud ones as a second cluster to merge.
    row("ad verification software", 0, 107_639, 10.2, AD_FRAUD),
    row("ott ad verification", 0, 2_000, 9.5, AD_FRAUD),
    row("astra fable launch", 90, 4_100, 6.0, NEWS),
    row("claude fable 5.1 astra", 110, 5_200, 5.5, NEWS),
    row("astra fable benchmark", 68, 3_789, 7.0, NEWS),
    row("looker studio", 37, 38_056, 7.1),
    row("acme", 321, 800, 1.5),
]


def spikes(after=AFTER, before=BEFORE):
    return gi.topic_spikes(after, before, gi.classify_queries(after))


def test_fraud_is_one_machine_suspect_topic_across_ad_and_click_fraud():
    result = spikes()
    fraud = [i for i in result["_all"] if "fraud" in i["topic"]]
    assert len(fraud) == 1
    topic = fraud[0]
    assert topic["verdict"] == "machine-suspect"
    assert topic["queries"] == 9
    assert topic["clicks"] == {"before": 2, "now": 1}
    assert {p["page"] for p in topic["pages"]} == {FRAUD_POST, AD_FRAUD}


def test_news_topic_with_clicks_is_real_interest():
    news = next(i for i in spikes()["_all"] if "astra" in i["topic"][0] or "fable" in i["topic"])
    assert news["verdict"] == "real interest"
    assert news["impressions"]["before"] == 0 and news["clicks"]["now"] == 268
    assert news["pages"][0]["page"] == NEWS


def test_steady_queries_are_not_topics():
    assert all("looker" not in " ".join(i["topic"]) for i in spikes()["_all"])


def test_real_interest_needs_clicks_at_the_human_floor():
    # 25 clicks on 42k impressions at position 9: up from 3, not impossible for people (P ~ 0.004),
    # but below the 42 clicks the floor CTR expects. Unclear, not real interest (the Acme
    # 'data / analytic' topic: 3 -> 11 clicks on 42k impressions).
    before = [row(f"data product analytics {i}", 1 if i < 3 else 0, 100, 9.0) for i in range(10)]
    after = [row(f"data product analytics {i}", 5 if i < 5 else 0, 4_200, 9.0) for i in range(10)]
    topic = gi.topic_spikes(after, before, gi.classify_queries(after))["_all"][0]
    assert topic["clicks"] == {"before": 3, "now": 25}
    assert topic["human_click_test"]["expected_at_floor"] == 42.0
    assert topic["verdict"] == "unclear"


def test_the_leftover_fraud_query_is_set_aside_through_its_topic():
    dataset = {"windows": {"current": ["2026-09-02", "2026-09-15"]},
               "query_page": {"rows": AFTER}, "query_page_previous": {"rows": BEFORE}, "pages": {}}
    alone = gi.classify_queries([r for r in AFTER if r["query"] == "mrc accredited fraud detection"])
    assert alone["mrc accredited fraud detection"]["label"] == "human"
    out = gi.analyse(dataset, {"human_basis", "topic_spikes"})
    items = {i["query"]: i for i in out["human_basis"]["items"]}
    assert items["mrc accredited fraud detection"]["reasons"] == ["spike_topic"]
    assert out["human_basis"]["reasons"]["spike_topic"]["queries"] >= 1
    assert "_members" not in out["topic_spikes"]["items"][0] and "_all" not in out["topic_spikes"]


def test_findings_name_both_kinds():
    dataset = {"windows": {"current": ["2026-09-02", "2026-09-15"]},
               "query_page": {"rows": AFTER}, "query_page_previous": {"rows": BEFORE}, "pages": {}}
    codes = {i["code"]: i for i in gi.analyse(dataset, {"topic_spikes"})["issues"]}
    assert codes["topic_spike_non_human"]["lane"] == "Decision"
    assert FRAUD_POST in codes["topic_spike_non_human"]["urls"]
    assert codes["topic_spike_real_interest"]["kind"] == "opportunity"
    assert "268 clicks" in codes["topic_spike_real_interest"]["finding"]


def test_without_a_previous_window_it_says_not_measured():
    out = gi.analyse({"query_page": {"rows": AFTER}, "pages": {}}, {"topic_spikes"})
    assert out["topic_spikes"]["status"] == "not measured"


@pytest.mark.parametrize("query,terms", [
    ("Best Ad Fraud Detection Tools 2026", {"ad", "fraud", "detection", "tool", "ad fraud", "fraud detection", "detection tool"}),
    ("what is looker studio", {"looker", "studio", "looker studio"}),
])
def test_terms(query, terms):
    assert gi._terms(query) == terms
