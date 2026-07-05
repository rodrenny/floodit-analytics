---
ticket: tickets/examples/ticket_003_vip_engagement_drop.md
status: needs-clarification
estimated_cost: n/a — design blocked on definitions below
---

# VIP engagement tracker

## Business question

Track engagement over time for our most valuable players, so a decline is
visible before the community feels it.

*(Stopping here per the ambiguity rule: three definitions below change the
model design, and guessing any of them would produce a confident-looking
table that answers a different question than yours.)*

## Verified during speccing (all queries capped)

One fact gathered so the questions below are concrete rather than
hypothetical: on the 7-day dev slice, **25 of 2,399 users (~1%) have any
`user_ltv.revenue` at all** (max $7.21 — this export has no purchase
events; LTV here is ad-revenue-derived). A spend-based VIP definition is
possible but covers a very small population. *(1 query, 55 MB scanned.)*

## Open questions

1. **Who is a VIP?** Pick one (or propose your own single sentence):
   a) users with any ad-revenue LTV (~1% of players — small but "paying");
   b) top 10% by lifetime playtime; c) top 10% by days active; d) players
   above an absolute threshold you name (e.g. ≥N sessions in their first
   week). The choice changes the model's grain and refresh logic —
   percentile definitions shift daily, absolute ones don't.
2. **What is "engagement" on the Monday deck?** One number per day per...
   what? Options: daily active VIPs, average session minutes per VIP,
   sessions per VIP, or days-since-last-seen distribution. Pick the one or
   two you'd actually act on.
3. **"Playing less" compared to what?** Their own prior 4 weeks? The same
   week last month? A fixed launch-era baseline? This decides whether the
   table carries the baseline column or the dashboard computes it.
4. **Population freeze:** once someone qualifies as VIP, do they stay VIP
   for the trend (cohort-style, cleaner for "are OUR best players
   leaving"), or can they drop out when their play drops (which makes the
   metric partially self-erasing)? Cohort-style is recommended.

Answer each in a sentence and this returns as a buildable spec within the
day. Sections below intentionally omitted until then.
