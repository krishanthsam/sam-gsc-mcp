---
name: citation-opportunities
title: Citation Opportunities (AI Overviews & Snippets)
description: Find pages that rank at the very top but earn few clicks — often because Google answers on the results page via AI Overviews or featured snippets — and suggest ways to win the click. Use for AI Overview impact, zero-click searches or "high rank, low clicks" questions.
---

# Citation Opportunities

When a page ranks ~#1 with very low CTR, Google is usually satisfying the searcher on the SERP using your content. You are a "silent reference".

## Steps

1. `find_low_ctr_opportunities(days=28, max_position=1.5, max_ctr=1.0, min_impressions=20, limit=50)`.
   Rows labelled `silent reference` are the targets.
2. For context, `get_search_analytics(dimensions="searchAppearance", row_limit=50)` shows which SERP features your site appears in.
3. Group the targets by page and check each query manually in Google (AI Overview? featured snippet? People Also Ask?).

## Recommendations

- Add a **click trigger** the SERP can't show: calculator, template, downloadable checklist, comparison table, pricing, case study, video.
- Put the quick answer early (to keep the citation) but make the title promise more depth ("+ free template", "with examples").
- Add relevant structured data (FAQ, HowTo, Product, Review) where it is genuinely applicable.
- Track with `compare_search_periods(dimensions="query", filters=[page filter])` after 4–6 weeks.

## Output

| Page | Query | Pos. | Impr. | CTR % | Expected CTR % | Lost clicks est. | Suggested click trigger |
