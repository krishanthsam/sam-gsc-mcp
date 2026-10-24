---
name: search-appearance-audit
title: Search Appearance Audit
description: Audit which rich results and SERP features (video, review snippets, FAQ, product, AMP...) your site appears with, how they perform, and which queries likely trigger them. Use for rich results, structured data impact or SERP feature questions.
---

# Search Appearance Audit

Google only allows `searchAppearance` as a dimension on its own (or with `date`), so this playbook joins the data in two steps.

## Steps

1. `get_search_analytics(dimensions="searchAppearance", row_limit=50, days=90)` → which appearances you get and their clicks/CTR.
2. For each appearance worth investigating, filter by it:
   `get_advanced_search_analytics(dimensions="query", filters=[{"dimension":"searchAppearance","operator":"equals","expression":"<APPEARANCE>"}], row_limit=200)`
   and the same with `dimensions="page"`.
3. Compare each appearance's CTR with the site average from `get_search_analytics(summary_only=true)`.
4. Validate markup on the top pages with `inspect_url_enhanced` → `rich_results.issues`.
5. Trend: `get_advanced_search_analytics(dimensions="date", filters=[searchAppearance filter])` to spot lost rich results after a site change.

## Output

| Appearance | Clicks | Impr. | CTR % vs site avg | Top pages | Markup issues |

## Notes

- Losing an appearance (CTR drop at stable position) is a common cause of traffic loss — see `diagnose-traffic-drop`.
- `ctr` is a percentage.
