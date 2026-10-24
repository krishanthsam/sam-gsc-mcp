---
name: seo-weekly-report
title: SEO Weekly Report
description: Build a complete weekly or monthly SEO performance report from Google Search Console. Use when asked for a site summary, performance overview, weekly/monthly report or "how is my site doing".
---

# SEO Weekly Report

A repeatable performance report: snapshot, change vs the previous period, alerts, winners/losers and next actions.

## Steps

1. Confirm the property with `list_properties` (skip if a default `GSC_SITE_URL` is set).
2. `get_site_summary(period_days=28)` → totals for this period and the previous one, plus % changes.
   Use `period_days=7` for a true week-over-week report.
3. `compare_search_periods(dimensions="query", limit=30)` → biggest query movers.
   Flag any query whose clicks fell by more than 20% (`click_pct < -20`) and had at least 20 clicks before.
4. `compare_search_periods(dimensions="page", limit=20)` → biggest page movers.
5. `get_search_analytics(dimensions="query", row_limit=10)` and `get_search_analytics(dimensions="page", row_limit=10)` → top performers.
6. `get_search_analytics(dimensions="device", row_limit=5)` and `dimensions="country", row_limit=5` → audience mix.
7. `find_striking_distance_keywords(limit=10)` → quick wins for next week.
8. `get_sitemaps` → mention any sitemap with errors.

## Output format

```
# SEO report — <property> — <start> to <end>

## Snapshot
| Metric | This period | Previous | Change |
| Clicks | ... | ... | +x% |
| Impressions | ... |
| CTR | ... % | ... % | +x pts |
| Avg position | ... | ... | ↑/↓ |

## Alerts            (queries/pages down >20%, sitemap errors)
## Winners           (top 5 gainers)
## Top queries & pages
## Quick wins        (striking-distance table)
## Next actions      (3–5 bullets, most impactful first)
```

## Interpretation notes

- `ctr` is already a percentage. `position` is an average — **lower is better**; a "position_change" > 0 means rankings improved.
- Data for the last 1–3 days is still filling in; never call a 1-day dip in the final days a "drop".
- Impressions up + CTR down usually means you're ranking for more (broader) queries, not a problem by itself.
