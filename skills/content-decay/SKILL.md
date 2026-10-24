---
name: content-decay
title: Content Decay (Refresh Candidates)
description: Find pages that are steadily losing clicks compared with earlier periods and pick the best candidates to refresh or update. Use for content refresh, decaying pages, old blog posts or "which pages should I update" questions.
---

# Content Decay

## Steps

1. Compare the last 3 months with the 3 months before:
   `compare_search_periods(period1_start=<90 days ago>, period1_end=<yesterday>, period2_start=<180 days ago>, period2_end=<91 days ago>, dimensions="page", limit=100)`.
2. Optional year-over-year check for seasonal sites: same 90 days one year earlier as period 2.
3. Keep pages from `top_losers` where `p2_clicks >= 30` and `click_pct <= -25`.
4. For each candidate, find which queries were lost:
   `compare_search_periods(..., dimensions="query", filters=[{"dimension":"page","operator":"equals","expression":"<page>"}], limit=10)`.
5. Check the page is still indexed and canonical: `check_url_status`.

## Prioritise

Score = lost clicks × (1 if position fell, 0.5 if only CTR fell). Highest first.

## Output

| Page | Clicks then → now | Change % | Position then → now | Main lost queries | Refresh action |

Refresh actions: update facts/dates/prices, add missing subtopics the lost queries ask about, improve title for CTR, re-promote with internal links, and request indexing after the update.
