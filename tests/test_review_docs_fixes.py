"""Pins for documentation facts that drifted away from the code.

Each test derives the true value from the repo (the script matrix, the
procedures directory, robots_checker.py, report.css) and fails when a doc
states something else, so the same drift cannot come back silently.
"""

import glob
import json
import os
import re
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from robots_checker import AI_CRAWLER_ROLES  # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _g(*parts, recursive=False):
    return sorted(glob.glob(os.path.join(ROOT, *parts), recursive=recursive))


# Every file a reader or a marketplace listing sees.
PUBLIC_DOCS = (
    [os.path.join(ROOT, n) for n in ("AGENTS.md", "SKILL.md", "README.md", "GEMINI.md")]
    + _g("references", "**", "*.md", recursive=True)
    + _g("agents", "*.md")
    + _g("extensions", "**", "*.md", recursive=True)
    + _g("chatgpt", "*.md")
    + _g("chatgpt", "*.txt")
    + [
        os.path.join(ROOT, ".claude-plugin", "marketplace.json"),
        os.path.join(ROOT, "plugins", "ultimate-seo-geo", ".claude-plugin", "plugin.json"),
        os.path.join(ROOT, "plugins", "ultimate-seo-geo", "README.md"),
        os.path.join(ROOT, ".github", "copilot-instructions.md"),
    ]
)


def _lines():
    for path in PUBLIC_DOCS:
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                yield os.path.relpath(path, ROOT), n, line


# --- script counts ------------------------------------------------------------


def matrix_scripts():
    """Scripts named in a table cell of references/audit-script-matrix.md."""
    names = set()
    for line in _read("references", "audit-script-matrix.md").splitlines():
        if not line.startswith("|"):
            continue
        for cell in line.strip().strip("|").split("|")[:3]:
            m = re.fullmatch(r"`([\w-]+\.py)`", cell.strip())
            if m:
                names.add(m.group(1))
    return names


def test_matrix_scripts_exist():
    names = matrix_scripts()
    assert len(names) > 40, "matrix parse found too few scripts; did the table layout change?"
    missing = sorted(n for n in names if not os.path.isfile(os.path.join(ROOT, "scripts", n)))
    assert not missing, f"audit-script-matrix.md lists scripts that do not exist: {missing}"


# "45 CLI tools", "all **45** CLI tools", "56 bundled scripts", "35 diagnostic scripts"
SCRIPT_COUNT = re.compile(
    r"(?<![\w.,])\*{0,2}(\d+)\*{0,2}\s+(?:(?:bundled|diagnostic|audit|Python|CLI)\s+)*(?:scripts|CLI tools)\b"
)


def test_stated_script_counts_match_the_matrix():
    expected = len(matrix_scripts())
    wrong = [
        f"{doc}:{n} says {m.group(1)}, matrix lists {expected}"
        for doc, n, line in _lines()
        for m in SCRIPT_COUNT.finditer(line)
        if int(m.group(1)) != expected
    ]
    assert not wrong, "stale script counts (prefer no number at all):\n  " + "\n  ".join(wrong)


@pytest.mark.parametrize(
    "stale",
    ["(45 CLI tools)", "All **45** CLI tools", "56 scripts;", "56 bundled scripts", "all 24 scripts",
     "all 27 scripts eligible", "35 scripts available", "all 35 diagnostic scripts"],
)
def test_the_count_check_catches_the_old_wording(stale):
    m = SCRIPT_COUNT.search(stale)
    assert m and int(m.group(1)) != len(matrix_scripts())


# --- procedure range ------------------------------------------------------------


def procedure_count():
    return len(_g("references", "procedures", "[0-9][0-9]-*.md"))


PROC_RANGE = re.compile(r"§\s?1\s?[–-]\s?§\s?(\d+)")


def test_procedure_ranges_match_the_directory():
    last = procedure_count()
    assert last >= 26
    wrong = [
        f"{doc}:{n} says §1–§{m.group(1)}, procedures/ has {last}"
        for doc, n, line in _lines()
        for m in PROC_RANGE.finditer(line)
        if int(m.group(1)) != last
    ]
    assert not wrong, "procedure ranges out of date:\n  " + "\n  ".join(wrong)


def test_skill_procedure_index_lists_every_file():
    skill = _read("SKILL.md")
    missing = [
        os.path.basename(p) for p in _g("references", "procedures", "[0-9][0-9]-*.md")
        if f"references/procedures/{os.path.basename(p)}" not in skill
    ]
    assert not missing, f"SKILL.md procedure index lacks: {missing}"


# --- FAQPage stance (D-016) -----------------------------------------------------


def test_full_site_audit_example_is_not_a_faqpage_rich_result_finding():
    text = _read("references", "procedures", "02-full-site-audit.md")
    assert "Missing FAQPage" not in text
    assert "eligible for AI Overview extraction" not in text


def test_industry_templates_point_to_the_faqpage_decision_tree():
    text = _read("references", "industry-templates.md")
    assert "FAQPage" in text
    assert "May 7, 2026" in text and "references/schema-types.md" in text


# --- llms.txt stance ------------------------------------------------------------


def test_competitor_analysis_does_not_sell_llms_txt_as_an_indexing_signal():
    text = _read("references", "procedures", "08-competitor-analysis.md")
    assert "clearer indexing signal" not in text
    row = next(l for l in text.splitlines() if l.startswith("| llms.txt presence"))
    assert "Non-Google AI hygiene only" in row and "not a scored gap" in row


def test_gemini_eval_does_not_list_llms_txt_as_a_gemini_lever():
    evals = json.loads(_read("evals", "evals.json"))
    evals = evals["evals"] if isinstance(evals, dict) else evals
    expected = next(e for e in evals if e["id"] == 12)["expected_output"]
    assert "optimization: llms.txt" not in expected
    assert "Google ignores llms.txt" in expected


# --- AI crawler table <-> robots_checker ----------------------------------------


def _doc_crawler_rows():
    text = _read("references", "ai-search-geo.md")
    section = text.split("### AI Crawler Management", 1)[1]
    rows = {}
    for line in section.splitlines():
        if line.startswith("| Crawler") or line.startswith("|---"):
            continue
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows[cells[0]] = cells[2]
    return rows


def _role_of(doc_role):
    r = doc_role.lower()
    if r.startswith("search"):
        return "search"
    if r.startswith("user"):
        return "user"
    return "training"


def test_every_documented_crawler_is_checked_with_the_same_role():
    rows = _doc_crawler_rows()
    assert "cohere-ai" in rows
    missing = sorted(set(rows) - set(AI_CRAWLER_ROLES))
    assert not missing, f"ai-search-geo.md lists crawlers robots_checker.py does not check: {missing}"
    mismatched = {c: (rows[c], AI_CRAWLER_ROLES[c]) for c in rows if _role_of(rows[c]) != AI_CRAWLER_ROLES[c]}
    assert not mismatched, f"doc role vs AI_CRAWLER_ROLES differ: {mismatched}"


def test_cohere_is_a_training_crawler_and_does_not_move_ai_search_access():
    import generate_report

    assert AI_CRAWLER_ROLES["cohere-ai"] == "training"
    rob = {"status": 200, "ai_crawler_status": {"cohere-ai": "fully blocked"}}
    assert generate_report._ai_search_access_score(rob) == 100


# --- report accent --------------------------------------------------------------


def test_accent_help_names_the_real_default():
    css = _read("references", "report-template", "report.css")
    default = re.search(r"--accent:\s*(#[0-9A-Fa-f]{6})", css).group(1)
    src = _read("scripts", "generate_report.py")
    help_text = re.search(r'"--accent",[^)]*help="([^"]*)"', src).group(1)
    assert "teal" not in help_text.lower()
    assert default.lower() in help_text.lower()


# --- documented-commands coverage -------------------------------------------------


def test_documented_command_check_covers_extension_and_chatgpt_docs():
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import test_documented_commands as tdc

    covered = {os.path.relpath(p, ROOT) for p in tdc.DOC_FILES}
    for rel in ("extensions/dataforseo/README.md", "extensions/firecrawl/README.md", "agents/PARALLEL-AUDIT.md",
                "chatgpt/README.md", "chatgpt/instructions.txt", "README.md", "GEMINI.md"):
        assert rel in covered, f"test_documented_commands.py does not scan {rel}"
