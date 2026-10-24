---
name: keyword-cannibalization
title: Keyword Cannibalization Check
description: Detect keyword cannibalization — queries where two or more of your pages compete for the same rankings — and recommend which page to keep. Use when asked about competing pages, keyword overlap, duplicate intent or cannibalization.
---

# Keyword Cannibalization Check

Find queries where several pages from the same site split impressions and clicks, then pick a primary page for each.

## Steps

1. Confirm the property with `list_properties`.
2. Run `find_keyword_cannibalization(days=28, min_impressions=20, min_share=10, limit=20)`.
   - It groups `query + page` rows and keeps queries where at least two pages each hold ≥10% of the query's impressions.
   - Manual alternative: `get_advanced_search_analytics(dimensions="query,page", row_limit=5000)` and group rows by `query`.
3. For the 5 highest-impression conflicts, call `get_search_by_page_query` for every competing page to see whether the pages target different intents overall.
4. Decide per conflict:
   - **Same intent, one clearly stronger** → 301-redirect or merge the weaker page into the primary.
   - **Same intent, both valuable** → merge content into one page; keep the URL with more links/clicks.
   - **Different intent** → differentiate titles/H1s and add an internal link from the secondary to the primary using the query as anchor.
   - **Homepage vs inner page** → de-optimise the homepage for the term; link to the inner page.

## Output format

| Query | Severity | Primary page | Competing page(s) | Clicks / Impr. / Pos. each | Fix |

Then a prioritised action list (high severity first).

## Notes

- Severity: high ≥ 1,000 total impressions, medium ≥ 200, low otherwise.
- Sitelinks, brand queries and very broad head terms naturally show several pages — don't "fix" those.
- Re-check 4–6 weeks after changes with `compare_search_periods(dimensions="query,page")`.
