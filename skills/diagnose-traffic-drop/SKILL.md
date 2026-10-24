---
name: diagnose-traffic-drop
title: Diagnose a Traffic Drop
description: Find when a Google search traffic drop started, which segment lost traffic (queries, pages, device, country, rich results) and the most likely cause (indexing, rankings or SERP changes). Use when traffic, clicks or impressions fell.
---

# Diagnose a Traffic Drop

## Steps

1. **Shape** — `get_performance_overview(days=90)`: when did it start, was it sudden or gradual, did clicks, impressions or both fall? Ignore the last 2 days (data still filling).
   For a very recent drop use `get_hourly_performance(days=7)`.
2. **Matched windows** — pick the drop window and an equal-length baseline right before it.
3. **Segment one dimension at a time** with `compare_search_periods(period1=drop, period2=baseline, dimensions=X, limit=30)`
   for X = `page`, `query`, `device`, `country`. Note where the losses concentrate.
4. **Brand vs non-brand** — `get_brand_vs_nonbrand` for both windows (brand loss = demand/reputation; non-brand loss = SEO).
5. **SERP features** — `get_search_analytics(dimensions="searchAppearance")` for both windows.
6. **Indexing** — `get_index_coverage(urls=<top losing pages>)` and `get_sitemaps` for errors.

## Classify the cause

| Pattern | Likely cause | Next check |
|---|---|---|
| Impressions ↓, position stable | Pages dropped out of the index / fewer queries | `get_index_coverage`, robots.txt, noindex, canonicals |
| Position ↓ across many queries | Algorithm update or quality issue | Compare dates with Google update history; check affected page types |
| Position ↓ on a few pages | Competitor, content change, lost links | Page history, `get_search_by_page_query` |
| CTR ↓, position stable | SERP feature change (AI Overview, ads, lost rich result) | `searchAppearance`, manual SERP check |
| One device/country only | Technical/regional issue | Mobile rendering, hreflang, CDN/geo blocks |
| Whole site, sudden, all metrics | Tracking/property issue or manual action | Search Console Manual actions, Security issues |

## Output

Drop summary (dates, % change), the losing segment with numbers, most likely cause, evidence, and a fix plan.
