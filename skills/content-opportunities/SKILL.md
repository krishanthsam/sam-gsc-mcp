---
name: content-opportunities
title: Content Opportunities
description: Find quick-win content optimisation targets — striking-distance queries (positions 4-20), high-impression low-CTR pages and content gaps. Use when asked for content ideas, quick wins, low-hanging fruit or optimisation opportunities.
---

# Content Opportunities

Three opportunity types, each with a different fix.

## Steps

1. Confirm the property with `list_properties`.
2. **Striking distance (improve existing pages)** —
   `find_striking_distance_keywords(days=28, min_position=4, max_position=20, min_impressions=50, limit=30)`.
   Ranked by an estimate of extra clicks if the query reached position 3.
3. **CTR gaps (rewrite titles/metas)** —
   `find_low_ctr_opportunities(days=28, max_position=5, max_ctr=2, min_impressions=100)`.
4. **Content gaps (new pages)** — question and comparison queries that land on a generic page:
   `get_advanced_search_analytics(dimensions="query,page", row_limit=5000, filters=[{"dimension":"query","operator":"includingRegex","expression":"(?i)^(how|what|why|which|best|top|vs|cost|price)\\b"}])`.
   Flag queries whose landing page is the homepage or a category page.
5. Group by page so one page gets one combined recommendation.

## Output format

| Type | Query | Page | Pos. | Impr. | CTR % | Est. gain | Action |

Then specific recommendations:
- **Striking distance:** exact-match the query in title/H1, add a section that answers it, add 2–3 internal links with the query as anchor.
- **CTR gap:** new title (benefit + number/year + brand), meta description with a clear reason to click, check for FAQ/HowTo schema.
- **Content gap:** brief for a new page (target query, intent, outline, internal links in/out).

## Notes

- "Est. gain" uses a generic CTR curve — use it to sort, not to promise traffic.
- `ctr` is a percentage; position: lower is better.
