# DataForSEO Extension

Live SERP data, keyword research, backlink profiles, on-page analysis, and AI visibility tracking.

## What It Enables

- Live backlink data: pull it through the MCP server, export to CSV, and feed it to `backlink_analyzer.py --source csv`
- Live SERP analysis for any keyword
- Keyword volume, difficulty, and intent classification
- AI visibility checking (LLM mentions of your brand)
- Competitor backlink gap analysis with live data

## Setup

1. Create an account at [dataforseo.com](https://dataforseo.com/)
2. Run the install script for your platform:

```bash
# Any platform (sets env vars)
bash extensions/dataforseo/install-generic.sh

# Claude Code (configures MCP server)
bash extensions/dataforseo/install-claude.sh

# Cursor (configures MCP server)
bash extensions/dataforseo/install-cursor.sh
```

## Verification

`backlink_analyzer.py` has no live DataForSEO source (`--source` is `csv`, `gsc` or `sample`). Pull backlinks through the DataForSEO MCP server, save them as CSV (columns such as `source_url`, `anchor_text`, `domain_rating`), then run:

```bash
python scripts/backlink_analyzer.py --source csv --input dataforseo-backlinks.csv --target-url https://example.com --json
```
