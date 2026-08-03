# Weekly discovery pass

This document is the standalone procedure for the weekly discovery run. It is
written so that a fresh session with no prior context can execute it from a
clone of this repository alone. It supplements — never replaces —
`docs/stream-policy.md`, which remains the binding editorial policy.

## Job

Find substantive new pieces published in the **last 7 days** that advance any
of the map's questions, verify them, and add them to the stream data so the
Latest page stays current. This is *discovery plus verification only*: full
reviews of each question (re-selection, "What changed" revisions, tier changes,
window recomputation) happen on the per-question cadence in the stream policy,
not weekly.

## Procedure

1. **Setup.** Clone the repo. `pip install markdown --break-system-packages`.
   Read `docs/stream-policy.md` (binding), `data/sources.json` (the discovery
   registry), and skim `data/recent.json` for what is already carried.
2. **Enumerate, don't search.** Go through every feed in `data/sources.json`
   (aggregators first — they recover the X-thread discourse) for items
   published in the last 7 days. Targeted web searches may supplement but
   never replace enumeration.
3. **Qualify.** A piece qualifies if a thoughtful reader tracking one of the
   127 questions would want to know it exists: new evidence, a new argument, a
   serious rebuttal, a measurement, a well-reported development. Quality of
   thought over fame of author. Not: routine product news, incremental model
   releases, low-effort takes.
4. **Verify — absolute rule.** Fetch every candidate URL. Confirm it exists
   and that author, venue, and date are right. Extract a verbatim quote and/or
   write a 1–2 sentence note. X posts only via a fetchable secondary source
   (record it in `via`). Drop anything unverifiable. Never fabricate.
5. **Dates.** Store full `YYYY-MM-DD` publication dates whenever the source
   shows one; month-only (`YYYY-MM`) only when a day is genuinely
   unascertainable. Also stamp every new item with a unique `"rid"`
   (short slug of title + year, e.g. `r_time_horizon_1_1_2026`) and `"added": "YYYY-MM-DD"`
   (the run date) — the Latest page sorts by publication date, but the RSS
   feed sorts by added date so retrospective additions still reach
   subscribers.
6. **Merge.** Add each verified piece to its **one** primary question in
   `data/recent.json` (the one-place rule): into `ledger` by default. Only
   place a piece directly into `items` (selected) when it is unambiguously
   significant — a major report, a primary document in a running fight, a
   result the question's framing turns on — and then keep the existing
   selection untouched otherwise. Do not rewrite `moved`, `tier`, `reviewed`,
   or `window` — those belong to full reviews. Dedup against every existing
   URL in the file. Append one JSON line per new item to
   `data/history.jsonl` (append-only — never edit or remove existing lines):
   `{"event":"observed","rid":...,"url":...,"qid":...,"state":"tracked","published":...,"added":...,"on":<run date>}`.
7. **Build and check.** Run `python3 scripts/build.py`. It validates the data
   and rebuilds the site including `latest/`. Fix any validation errors.
8. **Publish or report.** If a push credential is available, commit
   (`Weekly discovery: <date>`) and push. If not, end with a concise report
   listing every added piece (title, author, venue, date, URL, target
   question) so the editor can apply it in an attended session. Never include
   any credential in any output.

## Scale expectations

A typical week yields roughly 5–25 qualifying pieces across the whole map.
Zero is a legitimate answer for a quiet week; padding is worse than silence.
