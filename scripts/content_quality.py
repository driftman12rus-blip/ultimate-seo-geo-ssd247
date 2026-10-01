#!/usr/bin/env python3
"""Deterministic content quality checks for E-E-A-T and AI-pattern risks."""

from __future__ import annotations

import argparse
import json
import re
import sys

from bs4 import BeautifulSoup

from fetch_page import fetch_page


FILLER_PHRASES = (
    "in today's digital landscape",
    "it is important to note",
    "delve into",
    "unlock the power",
    "game-changer",
    "comprehensive guide",
    "look no further",
    "seamlessly",
)

UNSUPPORTED_CLAIM_RE = re.compile(
    r"\b(\d+(?:\.\d+)?%|\d+x|\d{4}|study|research|survey|report|according to)\b",
    re.IGNORECASE,
)

# Text that matches UNSUPPORTED_CLAIM_RE without being a claim. On one live site
# (2026-09-29) all 15 hits were these: the phone number's last four digits,
# review dates, "© 2026", "Last updated: ..." and "since 2019".
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}\b")
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
          r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
DATE_RE = re.compile(
    r"\b(?:" + _MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"      # March 15, 2026
    r"|\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r",?\s+\d{4}"           # 15 March 2026
    r"|" + _MONTH + r",?\s+\d{4}"                                     # March 2026
    r"|\d{4}-\d{2}-\d{2}"                                             # 2026-03-15
    r"|\d{1,2}/\d{1,2}/\d{2,4}"                                        # 3/15/2026
    r"|(?:19|20)\d{2}(?!\s*%)(?!x\b)"                                   # a bare year
    r")\b",
    re.IGNORECASE,
)
BOILERPLATE_SENTENCE_RE = re.compile(
    r"©|&copy;|\bcopyright\b|\ball rights reserved\b|\b(?:last\s+)?(?:updated|modified|reviewed)\s*(?:on)?\s*:",
    re.IGNORECASE,
)
CHROME_SELECTOR = "header, nav, footer, [role=banner], [role=navigation], [role=contentinfo]"
BLOCK_TAGS = ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "dt", "dd", "blockquote",
              "figcaption", "caption", "div", "section", "article", "aside", "main", "br", "tr", "summary")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'“(\[A-Z0-9])")
CLAIM_EXAMPLES = 3


def _claim_sentences(html: str) -> list[str]:
    """Sentences in the page's own content that state a number, a study or a source.

    Header, nav and footer are left out, and so are tel: links, phone numbers,
    dates, copyright and "last updated" lines: none of them is a claim a
    citation could support. One sentence counts once however many hits it has.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    for tag in soup.select(CHROME_SELECTOR):
        tag.decompose()
    for a in soup.select('a[href^="tel:"], a[href^="TEL:"]'):
        a.decompose()
    for el in soup.find_all(BLOCK_TAGS):
        el.insert_before("\n")
        el.insert_after("\n")
    sentences = []
    for line in soup.get_text(" ").split("\n"):
        line = " ".join(line.split())
        for sentence in _SENTENCE_SPLIT.split(line):
            if not sentence or BOILERPLATE_SENTENCE_RE.search(sentence):
                continue
            stripped = DATE_RE.sub(" ", PHONE_RE.sub(" ", sentence))
            if UNSUPPORTED_CLAIM_RE.search(stripped):
                sentences.append(sentence)
    return sentences


def _clip(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _html_to_text(html: str) -> tuple[str, BeautifulSoup]:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text, soup


def analyze_html(html: str, url: str = "") -> dict:
    text, soup = _html_to_text(html)
    lower = text.lower()
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    word_count = len(words)
    filler_hits = [phrase for phrase in FILLER_PHRASES if phrase in lower]
    author_present = bool(
        soup.select_one('[rel="author"], .author, .byline, [class*="author"], [itemprop="author"]')
    )
    date_present = bool(
        soup.find("time")
        or soup.select_one('[datetime], [class*="date"], [itemprop="datePublished"], [property="article:published_time"]')
    )
    outbound_sources = [
        a.get("href", "")
        for a in soup.find_all("a", href=True)
        if a.get("href", "").startswith(("http://", "https://")) and (not url or url not in a.get("href", ""))
    ]
    claims = _claim_sentences(html)
    claim_count = len(claims)
    citation_gap = max(0, claim_count - len(outbound_sources))

    issues = []
    recommendations = []
    score = 100

    if word_count < 300:
        score -= 20
        issues.append({
            "severity": "warning",
            "finding": "Page has very little extractable main content",
            "fix": "Add useful first-hand detail, examples, proof, or task-completion copy where appropriate.",
        })
    if filler_hits:
        score -= min(25, len(filler_hits) * 5)
        issues.append({
            "severity": "warning",
            "finding": f"Filler or generic AI-style phrasing detected: {', '.join(filler_hits[:5])}",
            "fix": "Replace generic phrasing with specific observations, concrete examples, and source-backed claims.",
        })
        recommendations.append("Rewrite generic filler phrases into specific, experience-backed statements.")
    if claim_count and citation_gap:
        score -= min(25, citation_gap * 3)
        issues.append({
            "severity": "warning",
            "finding": f"{citation_gap} claim(s) appear to need stronger citation support",
            "evidence": (f"{claim_count} sentence(s) state a figure, study or source; {len(outbound_sources)} "
                         "outbound link(s) on the page. For example: "
                         + " | ".join(f"\"{_clip(c)}\"" for c in claims[:CLAIM_EXAMPLES])),
            "fix": "Add primary-source links near statistics, dates, studies, or market claims.",
        })
    if not author_present:
        score -= 10
        issues.append({
            "severity": "info",
            "finding": "No clear author/byline signal detected",
            "fix": "Add author or reviewer attribution on editorial content where relevant.",
        })
    if not date_present:
        score -= 5
        issues.append({
            "severity": "info",
            "finding": "No publication or updated date detected",
            "fix": "Add visible publication or updated dates for informational content.",
        })

    return {
        "url": url,
        "score": max(0, score),
        "word_count": word_count,
        "filler_phrases": filler_hits,
        "claim_count": claim_count,
        "claim_examples": [_clip(c) for c in claims[:CLAIM_EXAMPLES]],
        "outbound_source_count": len(outbound_sources),
        "citation_gap": citation_gap,
        "author_present": author_present,
        "date_present": date_present,
        "issues": issues,
        "recommendations": recommendations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check deterministic content quality signals")
    parser.add_argument("url_or_file", help="URL or local HTML file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.url_or_file.startswith(("http://", "https://")):
        fetched = fetch_page(args.url_or_file, timeout=20)
        if fetched.get("error"):
            print(json.dumps({"error": fetched["error"]}) if args.json else fetched["error"])
            return 1
        html = fetched.get("content", "")
        data = analyze_html(html, args.url_or_file)
    else:
        with open(args.url_or_file, encoding="utf-8", errors="ignore") as f:
            data = analyze_html(f.read(), args.url_or_file)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"Content Quality Score: {data['score']}/100")
        for issue in data["issues"]:
            print(f"- {issue['severity'].upper()}: {issue['finding']} Fix: {issue['fix']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

