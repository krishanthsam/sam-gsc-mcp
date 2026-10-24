---
name: intent-segmentation
title: Searchers vs Prompters
description: Segment queries into short keyword "searchers" and long conversational "prompters" (AI-style questions) to see whether your audience is shifting to natural-language search. Use for AI search behaviour, long-tail or conversational query analysis.
---

# Searchers vs Prompters

## Steps

1. `get_advanced_search_analytics(dimensions="query", row_limit=5000)` for the last 28 days.
2. Classify each query:
   - **Prompter** — 7+ words, or starts with/contains conversational triggers: how, why, what, can, should, is it, vs, compare, best way, explain, step by step, difference between.
   - **Searcher** — everything else (short keyword-style queries).
3. For each segment: query count, clicks, impressions, CTR, average position, average words per query.
4. Trend: repeat for the same 28 days last quarter (`start_date`/`end_date`) and compare the prompter share.

## Output

| Segment | Queries | Avg words | Clicks | Impr. | CTR % | Avg pos. |
plus the top 15 prompter queries and which page ranks for each.

## What to do with it

- Rising prompter share → write answer-first sections, FAQ blocks and clear H2 questions that mirror real queries.
- Prompters with high impressions and low CTR are often answered by AI Overviews — see the `citation-opportunities` skill.
