# The recent-thinking stream — editorial policy

Decided August 2, 2026 (editor + Claude). This is the policy autonomous sweeps run
against; the editor spot-checks and anything flagged gets corrected.

## The product

For every covered question: the smallest set of recent material needed to understand
where the debate stands and what recently moved it — selected, dated, briefly
explained, and placed in the map. Curated recent thinking, not embedded social media.
Inputs are platform-agnostic (papers, lab and institutional publications, essays and
Substacks, verified social posts, podcasts and interviews, policy documents, original
reporting). Tweets and Substacks are inputs, not the product.

## Page anatomy (question pages in Browse)

1. Question, framing, entry teaser — unchanged.
2. **What has moved** — dated, plain-register, attributed: how the debate moved,
   shown ABOVE the entry teaser. Prefer 2–4 scannable bullets, each traceable to
   items below; a paragraph is acceptable for simple updates. This is the synthesis
   layer; the items are its evidence. Carries "reviewed <date>".
3. **The debate** — position columns, ONLY where a question genuinely has camps
   (a per-question editorial judgment recorded in data/debates.json). Core sources
   and recent items sit together under the position they argue for. Meta-layers
   that apply across camps — measurement/method, policy and institutional
   responses — are LANES: full-width strips below the columns, never rendered as
   parallel positions. Column labels must never claim more than the evidence does
   (capability evidence is not labor-market evidence). Questions without real
   camps get a single selected list ("Recent thinking").
4. Honest empty state — a covered question with nothing new says so: "No
   contribution since the last review met the inclusion threshold."

## Selection

- Significance-based, not window-based: the most recent 3–8 significant items,
  regardless of date. "Recent" means recently relevant, not merely newly published.
- Quality bar per item: adds evidence, a distinct argument, a forecast update, a
  substantive response, or represents an important position unusually well.
  Not news churn, not explainers.
- No global author whitelist — expertise is question-specific. Portfolio checks per
  page: are the serious positions represented; is one network overrepresented; is
  fame substituting for strength; does each item add something the rest don't?
- Influential-vs-correct: statements included because of who holds them (lab
  leaders, officials) are labeled as such in the note, in words.
- Engagement is never an inclusion criterion.

## Display

- Native cards only; no third-party embed scripts. Short excerpts, always linked,
  never mirrored.
- Display text must do work the title can't. Quote and note are BOTH shown when
  both exist: the quote is the author's words; the note is the curation — why this
  item belongs here — and is the differentiated value. Every item carries at least
  one (build-enforced). Format kind is displayed on every card.
- Prose over schema: format kind (paper/essay/post/report/interview) is the only
  formal label. Type, viewpoint, and role live in the note.

## Discovery

Sweeps do not rely on web search. Three channels, in order:
1. **Registry enumeration** — every feed in data/sources.json is walked item-by-item
   since the last review. Coverage is complete within the registry; growing the
   registry is an editorial act (it is the editor's reading graph).
2. **Aggregator mining** — comprehensive discourse roundups (Zvi, AI News, and
   similar) are read to recover X threads and long-tail posts, with links to the
   originals.
3. **Editor inbox** — links the editor sends enter the next sweep's candidate pool
   with priority. This is the primary X channel: the editor sees the feed; the
   sweep cannot.

## Verification (absolute)

No item ships unless its URL was fetched and its content checked during the sweep.
Verbatim quotes come from the fetched content. Exception for X posts, which cannot
be fetched directly: they may be included only when a fetchable secondary source
(an aggregator) quotes or substantively describes the specific post — the item then
carries a visible "via" attribution and its quote comes from the secondary source's
quotation. Never reconstructed from memory. Deleted or unreachable sources are
dropped or flagged at the next sweep.

## Dates

Exact dates (YYYY-MM-DD) preferred for new items; month precision (YYYY-MM) is
accepted for existing ones. Chronology, replies, and archival reconstruction all
get easier with days.

## Cadence

Tiers, recorded per question in data/recent.json:
- high: reviewed every 2–4 weeks
- medium: every 2–3 months
- slow: twice yearly
Every covered page shows its reviewed date. A stale "recent" section is worse than
none; if the cadence can't be held, shrink coverage rather than let pages rot.

## Structure

- Items map to ONE primary question (keyed by permanent qid). No secondary tags
  until real duplication pressure appears.
- Old items roll off as significance fades; an archive tier gets built only when
  there is something real to archive.
- Deferred deliberately: global "Latest" page, filterable lists, type-label
  taxonomy, analytics.

## The risks this policy exists to manage

Fame bias, platform bias, recency bias, feedification, maintenance debt, and
selection without synthesis. The "What has moved" paragraph is the answer to the
last; the reviewed-date and tier system to the second-to-last; the portfolio
checks to the first two.
