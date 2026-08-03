#!/usr/bin/env python3
"""Build the site from structured source data.

Source of truth:
  data/*.json             section data for the index (one file per section)
  content/cruxes/*.md     crux-overview entries (front-mattered Markdown)
  content/questions/*.md  question entries (same format; none yet)

Templates:  templates/index.html, templates/entry.html
Output:     index.html, cruxes/<slug>/index.html, questions/<slug>/index.html

Run from the repository root: python3 scripts/build.py
Requires: pip install markdown
Runs automatically on every push via .github/workflows/deploy.yml.
"""
import json, html, sys, os, glob, re
from urllib.parse import urlparse, quote_plus

REPO_ISSUES = "https://github.com/elehrer123-arch/ai-question-hierarchy/issues"

try:
    import markdown
except ImportError:
    sys.exit("Missing dependency: pip install markdown")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECTION_ORDER = ["trajectory", "safety", "economy", "power", "humanity"]

E = lambda s: html.escape(str(s), quote=True)


# ---------------------------------------------------------------- data
def load_sections():
    sections = []
    for name in SECTION_ORDER:
        with open(os.path.join(ROOT, "data", f"{name}.json"), encoding="utf-8") as f:
            sections.append(json.load(f))
    return sections


def question_index(sections):
    qs = {}
    for s in sections:
        for su in s["subs"]:
            for q in su["qs"]:
                qs[q["id"]] = q
    return qs


def validate(sections):
    errors = []
    ids, qids, slugs = set(), set(), set()
    for si, s in enumerate(sections, 1):
        if str(s.get("id")) != str(si):
            errors.append(f"section file order mismatch: expected id {si}, got {s.get('id')}")
        for su in s["subs"]:
            for q in su["qs"]:
                for field in ("id", "qid", "slug", "t", "q", "n", "links"):
                    if not q.get(field):
                        errors.append(f"{q.get('id', '?')}: missing field '{field}'")
                if q["id"] in ids: errors.append(f"duplicate number {q['id']}")
                if q.get("qid") in qids: errors.append(f"duplicate qid {q.get('qid')}")
                if q.get("slug") in slugs: errors.append(f"duplicate slug {q.get('slug')}")
                ids.add(q["id"]); qids.add(q.get("qid")); slugs.add(q.get("slug"))
                if not q["id"].startswith(su["id"] + "."):
                    errors.append(f"{q['id']} does not belong under subsection {su['id']}")
                for l in q.get("links", []):
                    if urlparse(l.get("u", "")).scheme not in ("http", "https"):
                        errors.append(f"{q['id']}: bad URL {l.get('u')!r}")
                    for field in ("t", "s"):
                        if not l.get(field):
                            errors.append(f"{q['id']}: link missing '{field}'")
    return errors


# ---------------------------------------------------------------- content entries
def parse_front_matter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{path}: missing front matter")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2).strip()


def load_entries(qindex):
    """One entry per question: content/questions/<slug>.md, joined to data/ by slug
    (the stable identifier). The display number is derived from data/, never stored
    in the entry file, so renumbering the map cannot orphan or mislabel an entry.
    Old URLs are preserved via redirect_from."""
    slug_to_qnum = {q["slug"]: qnum for qnum, q in qindex.items()}
    entries, errors = [], []
    for path in sorted(glob.glob(os.path.join(ROOT, "content", "questions", "*.md"))):
        meta, body = parse_front_matter(path)
        fname = os.path.splitext(os.path.basename(path))[0]
        for req in ("slug", "title", "status", "section"):
            if not meta.get(req):
                errors.append(f"{path}: front matter missing '{req}'")
        if meta.get("slug") != fname:
            errors.append(f"{path}: slug {meta.get('slug')!r} != filename {fname!r}")
        qnum = slug_to_qnum.get(meta.get("slug"))
        if qnum is None:
            errors.append(f"{path}: slug {meta.get('slug')!r} does not match any question slug in data/")
        if meta.get("question") and meta["question"] != qnum:
            errors.append(f"{path}: stale 'question: {meta['question']}' (slug resolves to {qnum}); "
                          f"remove the field — the number is derived from data/")
        redirects = [r.strip().strip("/") for r in meta.get("redirect_from", "").split(",") if r.strip()]
        entries.append({"folder": "questions", "meta": meta, "body": body,
                        "qnum": qnum, "redirects": redirects})
    return entries, errors


def crosslink(body, self_qnum, entry_slugs):
    """Turn bare question numbers in prose into links — to the question's entry
    page if one exists, otherwise to its anchor on the map."""
    def repl(m):
        num = m.group(1)
        if num == self_qnum:
            return num
        if num in entry_slugs:
            return f"[{num}](../{entry_slugs[num]}/)"
        return f"[{num}](../../#q{num.replace('.', '-')})"
    return re.sub(r"(?<![\w.#/\-\[])([1-5]\.\d{1,2}\.\d{1,2})(?![\w.\-\]])", repl, body)


def find_subsection(sections, qnum):
    for s in sections:
        for su in s["subs"]:
            for q in su["qs"]:
                if q["id"] == qnum:
                    return su
    return None


def render_entry(entry, qindex, sections, entry_slugs):
    meta, body = entry["meta"], entry["body"]
    body = crosslink(body, entry["qnum"], entry_slugs)
    md = markdown.Markdown(extensions=["toc", "tables"])
    body_html = md.convert(body)
    toc = "".join(
        f'<a href="#{t["id"]}">{E(t["name"])}</a>'
        for t in md.toc_tokens if t["level"] == 2
    )
    qnum = entry["qnum"]
    anchor = qnum.replace(".", "-")
    qlink = (f'<a href="../../#q{anchor}">{qnum} · {E(qindex[qnum]["t"])} — view on the map</a>'
             f' · <a href="../../browse/#q{anchor}">open in Browse</a>')
    subsection = find_subsection(sections, qnum)
    crumb = f'Question {qnum} · {E(subsection["t"])}'
    subhref = f'../../#{subsection["id"].replace(".", "-")}'
    core_revised = meta.get("core_revised", meta.get("core_reviewed", "—"))
    review = meta.get("review", "Pending")
    dateline = (f'{meta["status"]} · editorial review {review.lower()}. '
                f'Core article last revised {core_revised}; evidence updated {meta.get("evidence_updated", "—")}.')
    mark = ""
    cruxnote = ""
    scopenote = f'Scope: {E(meta.get("scope_short", ""))}' if meta.get("scope_short") else ""
    short_title = meta.get("short_title", meta["title"])
    cite = (f'“{E(meta["title"])}” <em>The Biggest Questions About AI</em>, '
            f'Elliott Lehrer (ed.), {meta.get("evidence_updated", "2026")}. {E(meta["status"])}.')
    issue_title = f'[{qnum} {meta["slug"]}] '
    issue_url = f'{REPO_ISSUES}/new?template=suggest-improvement.yml&title={quote_plus(issue_title)}'
    with open(os.path.join(ROOT, "templates", "entry.html"), encoding="utf-8") as f:
        tpl = f.read()
    out = (tpl.replace("__DATELINE__", E(dateline))
              .replace("__SHORT_TITLE__", E(short_title))
              .replace("__TITLE__", E(meta["title"]))
              .replace("__MARK__", mark)
              .replace("__CRUXNOTE__", cruxnote)
              .replace("__SCOPENOTE__", scopenote)
              .replace("__DESC__", E(meta.get("description", meta["title"])))
              .replace("__PATH__", f'{entry["folder"]}/{meta["slug"]}/')
              .replace("__SECTION__", E(meta["section"]))
              .replace("__CRUMB__", crumb)
              .replace("__SUBHREF__", subhref)
              .replace("__ROOT__", "../../")
              .replace("__STATUS__", E(meta["status"]))
              .replace("__AUTHOR__", E(meta.get("author", "—")))
              .replace("__EDITOR__", E(meta.get("editor", "—")))
              .replace("__REVIEW__", E(review))
              .replace("__CORE_REVISED__", E(core_revised))
              .replace("__EVIDENCE_UPDATED__", E(meta.get("evidence_updated", "—")))
              .replace("__SCOPE__", E(meta.get("scope", "—")))
              .replace("__CITE__", cite)
              .replace("__ISSUE_URL__", E(issue_url))
              .replace("__QLINK__", qlink)
              .replace("__TOC__", toc)
              .replace("__BODY__", body_html))
    # The question page at questions/<slug>/ is this entry's canonical home
    # (the analysis is embedded there). We only emit redirect stubs here.
    del out
    path = f'{entry["folder"]}/{meta["slug"]}/'
    for r in entry["redirects"]:
        depth = r.count("/") + 1
        target = "../" * depth + path
        rdir = os.path.join(ROOT, *r.split("/"))
        os.makedirs(rdir, exist_ok=True)
        with open(os.path.join(rdir, "index.html"), "w", encoding="utf-8") as f:
            f.write(
                f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
                f'<title>Moved: {E(meta["title"])}</title>'
                f'<link rel="canonical" href="https://elehrer123-arch.github.io/ai-question-hierarchy/{path}">'
                f'<meta http-equiv="refresh" content="0; url={target}"></head>'
                f'<body><p>This entry has moved to <a href="{target}">{E(meta["title"])}</a>.</p></body></html>'
            )
    return path


# ---------------------------------------------------------------- index
def render_index(sections, overview_links, outdir="", legacy=False):
    qcount = sum(len(su["qs"]) for s in sections for su in s["subs"])
    lcount = sum(len(q["links"]) for s in sections for su in s["subs"] for q in su["qs"])

    chain = []
    for s in sections:
        chain.append(
            f'<a href="#s{s["id"]}" style="--cc:var(--c{s["id"]})">'
            f'<span class="chnum">{s["id"]}</span><span class="chname">{E(s["name"])}</span>'
            f'<span class="chq">{E(s["tag"])}</span></a>'
        )

    nav = []
    for s in sections:
        subs = "".join(
            f'<a href="#sub{su["id"].replace(".", "-")}">{su["id"]} {E(su["t"])}</a>'
            for su in s["subs"]
        )
        nav.append(
            f'<div class="navsec"><div class="navhead">'
            f'<a class="navlink" href="#s{s["id"]}"><span class="dot" style="background:var(--c{s["id"]})"></span>{s["id"]}. {E(s["name"])}</a>'
            f'<button class="navchev" aria-expanded="false" aria-label="Toggle section {s["id"]} subsections"><span>▶</span></button>'
            f'</div><div class="navsub">{subs}</div></div>'
        )

    content = []
    for s in sections:
        parts = [
            f'<section class="big" id="s{s["id"]}" style="--secc:var(--c{s["id"]});--secs:var(--c{s["id"]}s)">',
            f'<div class="sechead"><div class="secnum" aria-hidden="true">{s["id"]}</div><div class="sectitles">'
            f'<h2>{E(s["name"])}</h2><div class="secq">{E(s["tag"])}</div></div></div>',
            f'<p class="secintro">{E(s["intro"])}</p>',
        ]
        for su in s["subs"]:
            sid = "sub" + su["id"].replace(".", "-")
            qlid = "qlist" + su["id"].replace(".", "-")
            parts.append(
                f'<div class="sub" id="{sid}">'
                f'<h3 class="subh"><button class="subbtn" aria-expanded="false" aria-controls="{qlid}">'
                f'<span class="subid">{su["id"]}</span><span class="subtitle">{E(su["t"])}</span>'
                f'<span class="qcount">{len(su["qs"])} questions</span><span class="chev" aria-hidden="true"><span>▶</span></span>'
                f'</button></h3>'
                f'<div class="qlist" id="{qlid}">'
            )
            for q in su["qs"]:
                qid = "q" + q["id"].replace(".", "-")
                qbid = "qbody" + q["id"].replace(".", "-")
                mark = ""
                overviews = "".join(
                    f'<a class="entrylink" href="{E(("../" if legacy else "") + href)}">Read the full entry →</a>'
                    for (title, href) in overview_links.get(q["id"], [])
                )
                links = "".join(
                    f'<a href="{E(l["u"])}" target="_blank" rel="noopener">{E(l["t"])}'
                    f'<span class="lsrc">{E(l["s"])}{" · " + l["y"] if l.get("y") else ""}</span>'
                    f'<span class="ext" aria-hidden="true">↗</span></a>'
                    for l in q["links"]
                )
                parts.append(
                    f'<div class="q" id="{qid}" data-qid="{E(q["qid"])}" data-slug="{E(q["slug"])}">'
                    f'<h4 class="qh"><button class="qbtn" aria-expanded="false" aria-controls="{qbid}">'
                    f'<span class="qtxt"><span class="qover">{q["id"]} · {E(q["t"])}</span>'
                    f'<span class="qq">{E(q["q"])}{mark}</span></span>'
                    f'<span class="chev" aria-hidden="true"><span>▶</span></span>'
                    f'</button></h4>'
                    f'<div class="qbody" id="{qbid}">'
                    f'{overviews}'
                    f'<p class="qn">{E(q["n"])}</p>'
                    f'<div class="links">{links}</div>'
                    f'</div></div>'
                )
            parts.append("</div></div>")
        parts.append("</section>")
        content.append("".join(parts))

    with open(os.path.join(ROOT, "templates", "index.html"), encoding="utf-8") as f:
        tpl = f.read()
    out = (tpl.replace("__NAV__", "".join(nav))
              .replace("__CHAIN__", "".join(chain))
              .replace("__CONTENT__", "".join(content))
              .replace("__QCOUNT__", str(qcount))
              .replace("__LCOUNT__", str(lcount)))
    if legacy:
        out = out.replace('<link rel="canonical" href="https://elehrer123-arch.github.io/ai-question-hierarchy/">',
                          '<link rel="canonical" href="https://elehrer123-arch.github.io/ai-question-hierarchy/all/">'
                          '<meta name="robots" content="noindex">')
        out = out.replace('<main id="main">',
                          '<main id="main"><p style="font-size:12.5px;color:var(--ink3);border:1px solid var(--line);'
                          'border-radius:9px;padding:8px 12px;margin-bottom:18px">This is the classic one-page view. '
                          'The <a href="../">map</a> and <a href="../browse/">browse</a> views are the new front door.</p>')
    dest = os.path.join(ROOT, outdir) if outdir else ROOT
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
    return qcount, lcount


# ---------------------------------------------------------------- map, browse, poster
SECTION_NAMES = {"1": "Trajectory", "2": "Safety", "3": "Economy", "4": "Power", "5": "Humanity"}
SECTION_COLORS = {"1": "#3d6b9e", "2": "#b0524b", "3": "#3d8a6b", "4": "#7a5ba6", "5": "#a97729"}


def entry_excerpt(body):
    m = re.search(r"## The question\n\n(.+?)\n\n", body, re.S)
    if not m:
        return ""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", m.group(1))
    return text.replace("*", "").strip()


def render_map(sections, entry_map, recent=None):
    qcount = sum(len(su["qs"]) for s in sections for su in s["subs"])
    lcount = sum(len(q["links"]) for s in sections for su in s["subs"] for q in su["qs"])
    cols = []
    for s in sections:
        c = SECTION_COLORS[s["id"]]
        inner = [
            f'<button class="bsechead" data-s="{s["id"]}" aria-expanded="false">'
            f'<span class="bnum">{s["id"]}</span><span class="bname">{SECTION_NAMES[s["id"]]}</span></button>'
            f'<div class="btag">{E(s["tag"])}</div>'
        ]
        for su in s["subs"]:
            sub_anchor = su["id"].replace(".", "-")
            inner.append(f'<a class="bsub" id="b{sub_anchor}" data-sub="{su["id"]}" '
                         f'href="browse/#{sub_anchor}">{su["id"]} · {E(su["t"])}</a>')
            for q in su["qs"]:
                anchor = q["id"].replace(".", "-")
                star = ""
                _rq_x = (recent or {}).get("items", {}).get(q["id"]) or {}
                _stream_x = [f'{it.get("title","")} {it.get("author","")} {it.get("venue","")}'
                             for it in _rq_x.get("items", []) + _rq_x.get("ledger", [])]
                x = " ".join([q["id"], q["t"], q["q"], q["n"]] +
                             [l["t"] + " " + l["s"] for l in q["links"]] + _stream_x).lower()
                links = "".join(
                    f'<a href="{E(l["u"])}" target="_blank" rel="noopener">{E(l["t"])}'
                    f'<span class="lsrc">{E(l["s"])}{" · " + l["y"] if l.get("y") else ""}</span></a>'
                    for l in q["links"])
                ent = entry_map.get(q["id"])
                entlink = (f'<a class="bentry" href="questions/{ent["slug"]}/">Read the full entry →</a>'
                           if ent else "")
                rqe = (recent or {}).get("items", {}).get(q["id"])
                vol = ""
                if rqe:
                    _cut = window_cutoff(90)
                    n90 = sum(1 for it in rqe.get("items", []) + rqe.get("ledger", [])
                              if in_window(it.get("date", ""), _cut))
                    vol = ('<a class="vol" href="latest/?q=' + q['id'] + '" title="See these pieces on Latest">· ' + str(n90) + ' in 90d</a>')
                inner.append(
                    f'<div class="bq" id="n{anchor}" data-sec="{s["id"]}" data-sub="{su["id"]}" data-x="{E(x)}">'
                    f'<div class="bqrow"><button class="bqhead" aria-expanded="false"><span class="bqid">{q["id"]}</span>{E(q["t"])}{star}</button>{vol}</div>'
                    f'<p class="bqq">{E(q["q"])}</p>'
                    f'<div class="bqbody"><div class="bqin">'
                    f'<p class="bfull">{E(q["q"])}</p>'
                    f'<p class="bn">{E(q["n"])}</p>'
                    f'<div class="blinks">{links}</div>{entlink}'
                    f'<a class="bopen" href="questions/{q["slug"]}/">Question page →</a>'
                    f'<a class="bopen" href="browse/#q{anchor}">Open in Browse →</a>'
                    f'</div></div></div>')
        cols.append(f'<div class="bcol" data-s="{s["id"]}" style="--sc:{c}">'
                    f'<div class="binner">{"".join(inner)}</div></div>')
    with open(os.path.join(ROOT, "templates", "map.html"), encoding="utf-8") as f:
        tpl = f.read()
    tracked = len((recent or {}).get("items", {}))
    out = (tpl.replace("__COLS__", "".join(cols))
              .replace("__QCOUNT__", str(qcount))
              .replace("__LCOUNT__", str(lcount))
              .replace("__TRACKED__", str(tracked)))
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)


def load_recent(qindex):
    path = os.path.join(ROOT, "data", "recent.json")
    if not os.path.exists(path):
        return {"swept": "", "items": {}}, []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    errors = []
    qid_to_id = {q["qid"]: q["id"] for q in qindex.values()}
    by_id = {}
    for qid, entry in data.get("questions", {}).items():
        if qid not in qid_to_id:
            errors.append(f"recent.json: unknown qid {qid!r}")
            continue
        _rids_here = {it.get("rid") for it in entry.get("items", [])}
        _mv = entry.get("moved")
        for _st in (_mv if isinstance(_mv, list) else [_mv]):
            if isinstance(_st, dict):
                for _rf in _st.get("refs", []):
                    if _rf not in _rids_here:
                        errors.append(f"recent.json {qid}: moved ref {_rf!r} is not a featured item")
        for field in ("tier", "swept", "moved"):
            if not entry.get(field):
                errors.append(f"recent.json {qid}: missing '{field}'")
        if entry.get("tier") not in ("high", "medium", "slow"):
            errors.append(f"recent.json {qid}: bad tier {entry.get('tier')!r}")
        for it in entry.get("items", []):
            for field in ("title", "author", "venue", "date", "url"):
                if not it.get(field):
                    errors.append(f"recent.json {qid}: item missing '{field}'")
            if not it.get("quote") and not it.get("note"):
                errors.append(f"recent.json {qid}: item needs a quote or a note ({it.get('url')})")
            if urlparse(it.get("url", "")).scheme not in ("http", "https"):
                errors.append(f"recent.json {qid}: bad URL {it.get('url')!r}")
            if not re.match(r"^\d{4}-\d{2}(-\d{2})?$", it.get("date", "")):
                errors.append(f"recent.json {qid}: bad date {it.get('date')!r} (want YYYY-MM)")
        for it in entry.get("ledger", []):
            for field in ("title", "author", "venue", "date", "url"):
                if not it.get(field):
                    errors.append(f"recent.json {qid} ledger: item missing '{field}'")
            if urlparse(it.get("url", "")).scheme not in ("http", "https"):
                errors.append(f"recent.json {qid} ledger: bad URL {it.get('url')!r}")
        by_id[qid_to_id[qid]] = entry

    # global integrity checks
    from datetime import date as _d
    def _valid_day(ds):
        try:
            if len(ds) == 10:
                _d(int(ds[:4]), int(ds[5:7]), int(ds[8:10]))
            else:
                _d(int(ds[:4]), int(ds[5:7]), 1)
            return True
        except ValueError:
            return False
    seen_urls = {}
    seen_rids = {}
    for qid, entry in data.get("questions", {}).items():
        for kind, lst in (("items", entry.get("items", [])), ("ledger", entry.get("ledger", []))):
            for it in lst:
                u = (it.get("url") or "").rstrip("/")
                if u in seen_urls:
                    errors.append(f"duplicate URL across stream: {u} ({seen_urls[u]} and {qid})")
                else:
                    seen_urls[u] = qid
                _rid = it.get("rid")
                if _rid:
                    if _rid in seen_rids:
                        errors.append(f"duplicate rid: {_rid} ({seen_rids[_rid]} and {qid})")
                    else:
                        seen_rids[_rid] = qid
                if not it.get("added"):
                    errors.append(f"recent.json {qid}: item missing 'added' ({u})")
                if not it.get("rid"):
                    errors.append(f"recent.json {qid}: item missing 'rid' ({u})")
                elif not re.match(r"^\d{4}-\d{2}-\d{2}$", it["added"]) or not _valid_day(it["added"]):
                    errors.append(f"recent.json {qid}: bad added date {it.get('added')!r}")
                if it.get("date") and not _valid_day(it["date"]):
                    errors.append(f"recent.json {qid}: non-calendar date {it['date']!r}")
    return {"swept": data.get("swept", ""), "items": by_id}, errors


def load_debates(qindex):
    path = os.path.join(ROOT, "data", "debates.json")
    if not os.path.exists(path):
        return {}, []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    errors = []
    qid_to_id = {q["qid"]: q["id"] for q in qindex.values()}
    by_id = {}
    for qid, deb in data.items():
        if qid not in qid_to_id:
            errors.append(f"debates.json: unknown qid {qid!r}")
            continue
        poles = {p["k"] for p in deb.get("poles", [])}
        for idx, k in deb.get("canon", {}).items():
            if k != "_frame" and k not in poles:
                errors.append(f"debates.json {qid}: canon[{idx}] -> unknown pole {k!r}")
        by_id[qid_to_id[qid]] = {"poles": deb["poles"], "canon": deb.get("canon", {})}
    return by_id, errors


def render_browse(sections, entry_map, recent=None, debates=None):
    data = []
    for s in sections:
        data.append({"id": s["id"], "name": SECTION_NAMES[s["id"]], "tag": s["tag"], "intro": s["intro"],
                     "subs": [{"id": su["id"], "t": su["t"], "qs": [
                         {"id": q["id"], "t": q["t"], "q": q["q"], "n": q["n"],
                          "crux": q.get("crux", ""), "slug": q["slug"], "links": q["links"],
                          "sx": " ".join(
                              f'{it.get("title","")} {it.get("author","")} {it.get("venue","")}'
                              for it in ((recent or {"items": {}})["items"].get(q["id"]) or {}).get("items", [])
                              + ((recent or {"items": {}})["items"].get(q["id"]) or {}).get("ledger", []))}
                         for q in su["qs"]]} for su in s["subs"]]})
    entry_json = {qnum: {"href": f'../questions/{e["slug"]}/', "title": e["title"],
                         "status": e["status"], "excerpt": e["excerpt"]}
                  for qnum, e in entry_map.items()}
    with open(os.path.join(ROOT, "templates", "browse.html"), encoding="utf-8") as f:
        tpl = f.read()
    recent = recent or {"swept": "", "items": {}}
    out = (tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
              .replace("__ENTRY__", json.dumps(entry_json, ensure_ascii=False))
              .replace("__RECENT__", json.dumps(recent["items"], ensure_ascii=False))
              .replace("__SWEPT__", json.dumps(recent["swept"]))
              .replace("__DEBATES__", json.dumps(debates or {}, ensure_ascii=False)))
    outdir = os.path.join(ROOT, "browse")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)





from datetime import date as _date, timedelta as _timedelta

def window_cutoff(days=90):
    """Rolling cutoff (build date - days) as YYYY-MM-DD.

    Month-only item dates are compared as their first day, so a piece can
    fall out of the window early but never stays in it late (conservative:
    recency is never overstated). The window rolls forward at build time;
    weekly discovery builds keep it fresh.
    """
    return (_date.today() - _timedelta(days=days)).isoformat()


def in_window(d, cutoff):
    return (d if len(d) == 10 else d + "-01") >= cutoff


MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]

def _parse_reviewed(s):
    m = re.match(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", s or "")
    if not m or m.group(1) not in MONTH_NAMES:
        return ""
    return f"{m.group(3)}-{MONTH_NAMES.index(m.group(1))+1:02d}-{int(m.group(2)):02d}"


def render_latest(sections, recent, cutoff=None):
    """Render latest/index.html and latest/feed.xml from stream data.

    Page: every selected and ledger item published on/after `cutoff`
    (same cutoff as the map's 90-day volume lens), month sections newest
    first, day-precision items before an "Earlier in <month>" group.
    RSS: ordered by when we ADDED the item (so retrospective additions
    still reach subscribers), pubDate = added date.
    """
    cutoff = cutoff or window_cutoff(90)
    qmeta = {}
    for s in sections:
        for su in s["subs"]:
            for q in su["qs"]:
                qmeta[q["id"]] = {"t": q["t"], "sec": s["id"], "slug": q["slug"]}

    rows = []
    max_reviewed = ""
    for qid_disp, entry in recent["items"].items():
        rv = _parse_reviewed(entry.get("swept", ""))
        if rv > max_reviewed:
            max_reviewed = rv
        for it, sel in [(i, True) for i in entry.get("items", [])] + \
                       [(i, False) for i in entry.get("ledger", [])]:
            if in_window(it["date"], cutoff):
                rows.append({"d": it["date"], "added": it.get("added", ""), "sel": sel,
                             "q": qid_disp, "qt": qmeta[qid_disp]["t"],
                             "sec": qmeta[qid_disp]["sec"],
                             "slug": qmeta[qid_disp]["slug"], "rid": it.get("rid", ""),
                             "title": it["title"], "author": it["author"],
                             "venue": it["venue"], "url": it["url"],
                             "kind": it.get("kind", ""), "note": it.get("note", "")})

    rows.sort(key=lambda r: (r["d"][:7], len(r["d"]), r["d"], r["sel"]), reverse=True)
    months = []
    for r in rows:
        m = r["d"][:7]
        if not months or months[-1][0] != m:
            months.append((m, []))
        months[-1][1].append(r)

    max_rev_h = ""
    if max_reviewed:
        y, mo, dd = max_reviewed.split("-")
        max_rev_h = f"{MONTH_NAMES[int(mo)-1]} {int(dd)}, {int(y)}"

    def month_h(m):
        y, mo = m.split("-")
        return f"{MONTH_NAMES[int(mo)-1]} {y}"

    def day_h(d):
        if len(d) == 10:
            return f"{MONTH_NAMES[int(d[5:7])-1][:3]} {int(d[8:10])}"
        return "—"

    secline = "".join(
        f'<button class="fsec" data-s="{sid}" aria-pressed="true">'
        f'<span class="dot" style="background:var(--c{sid})"></span>{SECTION_NAMES[sid]}</button>'
        for sid in "12345")

    def _lbyline(r):
        a, v = r["author"].strip(), r["venue"].strip()
        al, vl = a.lower(), v.lower()
        if al == vl or al.startswith(vl) or vl.startswith(al):
            return E(a if len(a) >= len(v) else v)
        return f'{E(a)} · {E(v)}'

    body = []
    for m, items in months:
        body.append(f'<h2 class="mh">{month_h(m)} <span class="mc">({len(items)})</span></h2>')
        shown_earlier = False
        for r in items:
            if len(r["d"]) == 7 and not shown_earlier:
                body.append(f'<h3 class="emh">Earlier in {month_h(m).split(" ")[0]} '
                            f'<span class="mc">(day not stated by source)</span></h3>')
                shown_earlier = True
            anchor = "q" + r["q"].replace(".", "-")
            note = f'<div class="lnote">{E(r["note"])}</div>' if (r["sel"] and r["note"]) else ""
            kind = f'<span class="lkind">{E(r["kind"])}</span>' if r["kind"] else ""
            feat = ("" if r["sel"] else
                    '<span class="ltrk" title="Tracked, not featured on the question page">also tracked</span>')
            addm = ""
            if r.get("added") and r["added"][:7] != r["d"][:7]:
                addm = (f'<span class="ladd">Added {MONTH_NAMES[int(r["added"][5:7])-1][:3]} '
                        f'{int(r["added"][8:10])}</span>')
            search = E(f'{r["title"]} {r["author"]} {r["venue"]} {r["q"]} {r["qt"]}'.lower())
            body.append(
                f'<article class="li{"" if r["sel"] else " lg"}" data-s="{r["sec"]}" '
                f'data-q="{r["q"]}" data-search="{search}">'
                f'<div class="ld">{day_h(r["d"])}</div>'
                f'<div class="lb"><a class="lt" href="{E(r["url"])}" rel="noopener">{E(r["title"])}</a>'
                f'<div class="lm">{_lbyline(r)} {kind}{feat}{addm}</div>{note}'
                f'<a class="lq" href="../questions/{E(r["slug"])}/" style="color:var(--c{r["sec"]})">'
                f'&rarr; {r["q"]} {E(r["qt"])}</a></div></article>')

    qnames = {r["q"]: r["qt"] for r in rows}
    html = LATEST_TEMPLATE
    html = (html.replace("__BODY__", "\n".join(body))
                .replace("__SECLINE__", secline)
                .replace("__COUNT__", str(len(rows)))
                .replace("__QNAMES__", json.dumps(qnames, ensure_ascii=False))
                .replace("__REVIEWED__", E(max_rev_h)))
    outdir = os.path.join(ROOT, "latest")
    os.makedirs(outdir, exist_ok=True)
    html = html.replace("</body>", analytics_snippet() + "</body>")
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # RSS: ordered by added date (newest additions first), pubDate = added.
    def rfc822(d):
        dd = d if len(d) == 10 else d + "-01"
        y, mo, day = int(dd[:4]), int(dd[5:7]), int(dd[8:10])
        import calendar
        wd = calendar.weekday(y, mo, day)
        return (f"{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][wd]}, {day:02d} "
                f"{MONTH_NAMES[mo-1][:3]} {y} 00:00:00 GMT")

    def X(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    rss_rows = sorted(rows, key=lambda r: (r.get("added") or r["d"], r["d"]), reverse=True)[:60]
    rss_items = []
    for r in rss_rows:
        pub = r.get("added") or r["d"]
        desc = X(r["note"]) if r["note"] else f'{X(r["author"])} · {X(r["venue"])}'
        pubd = f' (published {r["d"]})' if r["d"][:7] != pub[:7] else ""
        qpage = f"https://elehrer123-arch.github.io/ai-question-hierarchy/questions/{r['slug']}/"
        guid = f"{qpage}#{r['rid']}" if r.get("rid") else r['url']
        qline = f" — On question {X(r['q'])} {X(r['qt'])}: {qpage}"
        featline = " Featured on the question page." if r["sel"] else ""
        rss_items.append(
            f"<item><title>{X(r['title'])}</title><link>{X(r['url'])}</link>"
            f"<guid isPermaLink=\"true\">{X(guid)}</guid>"
            f"<pubDate>{rfc822(pub)}</pubDate>"
            f"<category>{X(r['q'] + ' ' + r['qt'])}</category>"
            f"<description>{desc}{X(pubd)}{qline}{featline}</description></item>")
    rss = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
           "<rss version=\"2.0\"><channel>"
           "<title>The Biggest Questions About AI — Latest</title>"
           "<link>https://elehrer123-arch.github.io/ai-question-hierarchy/latest/</link>"
           "<description>Substantive recent pieces observed by our reviews, "
           "across all 127 questions. Ordered by when items were added.</description>"
           + "".join(rss_items) + "</channel></rss>")
    with open(os.path.join(outdir, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(rss)
    return len(rows)


LATEST_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Latest — The Biggest Questions About AI</title>
<meta name="description" content="Substantive recent pieces on the biggest open questions about AI, newest first.">
<link rel="alternate" type="application/rss+xml" title="Latest — The Biggest Questions About AI" href="feed.xml">
<style>
:root{--bg:#faf9f6;--panel:#fff;--ink:#1d1c1a;--ink2:#514d45;--ink3:#6f6b5f;--line:#e4e1d8;
--c1:#3d6b9e;--c2:#b0524b;--c3:#3d8a6b;--c4:#7a5ba6;--c5:#a97729;
--serif:Georgia,'Times New Roman',serif}
@media (prefers-color-scheme:dark){:root{--bg:#191817;--panel:#211f1d;--ink:#f2f0ea;--ink2:#c3c0b4;--ink3:#8f8b7e;--line:#33312d;
--c1:#6f9bc9;--c2:#c97a74;--c3:#63a586;--c4:#a08ac4;--c5:#c29a55}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:26px 20px 60px}
header{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:4px}
.home{font-family:var(--serif);font-size:16px;color:var(--ink);text-decoration:none}
.switch{margin-left:auto;font-size:13px;color:var(--ink3)}
.switch a{color:var(--ink2);text-decoration:none}
h1{font-family:var(--serif);font-weight:400;font-size:30px;margin:18px 0 6px}
.lede{color:var(--ink2);font-size:14.5px;line-height:1.5;max-width:620px;margin:0 0 4px}
.meta{font-size:12.5px;color:var(--ink3);margin:0 0 3px}
.meta b{color:var(--ink2);font-weight:600}
.meta2{font-size:12px;color:var(--ink3);margin:0 0 20px;max-width:560px;line-height:1.5}
.meta a{color:var(--ink2)}
.fbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
.fsec{border:1px solid var(--line);background:var(--panel);border-radius:16px;
padding:4px 11px 4px 8px;font-size:12px;color:var(--ink2);cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.fsec[aria-pressed="false"]{opacity:.38}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.fsel{margin-left:auto;font-size:12.5px;color:var(--ink2);display:inline-flex;gap:6px;align-items:center;cursor:pointer;white-space:nowrap}
.mh{font-family:var(--serif);font-weight:400;font-size:19px;margin:26px 0 4px;
border-bottom:1px solid var(--line);padding-bottom:6px}
.mc{color:var(--ink3);font-size:13px}
.li{display:flex;gap:14px;padding:11px 0;border-bottom:1px solid var(--line)}
.ld{flex:0 0 44px;font-size:11.5px;color:var(--ink3);padding-top:3px;font-variant-numeric:tabular-nums}
.lb{flex:1;min-width:0}
.lt{font-size:15px;color:var(--ink);text-decoration:none;line-height:1.35}
.lt:hover{text-decoration:underline}
.lm{font-size:12px;color:var(--ink3);margin-top:2px}
.lkind{border:1px solid var(--line);border-radius:9px;padding:0 6px;font-size:10.5px;margin-left:4px}
.lnote{font-size:13px;color:var(--ink2);line-height:1.45;margin-top:4px;max-width:600px}
.lq{display:inline-block;font-size:12px;text-decoration:none;margin-top:5px}
.lq:hover{text-decoration:underline}
.lg .lt{color:var(--ink2)}
.lg{opacity:.92}
body.selonly .lg{display:none}
.emh{font-size:12px;color:var(--ink3);font-weight:600;letter-spacing:.04em;text-transform:uppercase;margin:14px 0 0;padding:6px 0 0}
.fbar2{margin:8px 0 4px}
.srch{border:1px solid var(--line);background:var(--panel);border-radius:18px;padding:7px 14px;font-size:13px;color:var(--ink);width:100%;max-width:340px}
.srch:focus{outline:1px solid var(--ink3)}
.qpill{display:none;align-items:center;gap:8px;margin:2px 0 10px;font-size:12.5px;color:var(--ink2)}
.qpill.on{display:flex}
.qpill button{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:1px 9px;font-size:11.5px;cursor:pointer;color:var(--ink2)}
.ltrk{color:var(--ink3);font-size:10.5px;margin-left:7px;white-space:nowrap;font-style:italic}
.ladd{color:var(--ink3);font-size:10.5px;margin-left:7px;white-space:nowrap;border:1px solid var(--line);border-radius:9px;padding:0 6px}
.rescount{font-size:12px;color:var(--ink3);margin:0 0 10px}
.empty{display:none;border:1px solid var(--line);border-radius:10px;padding:18px;margin-top:14px;font-size:13.5px;color:var(--ink2);line-height:1.55}
.empty.on{display:block}
.empty button{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:2px 10px;font-size:12px;cursor:pointer;color:var(--ink2);margin-top:8px}
.note{margin-top:30px;border-top:1px solid var(--line);padding-top:12px;
font-size:12.5px;color:var(--ink2);line-height:1.55;max-width:620px}
</style></head><body>
<div class="wrap">
<header><a class="home" href="../">The Biggest Questions About&nbsp;AI</a>
<nav class="switch" aria-label="View switch"><a href="../">Map</a> · <a href="../browse/">Browse</a> · <b style="color:var(--ink)">Latest</b></nav></header>
<h1>Latest</h1>
<p class="lede">Substantive recent pieces, newest first — each linked to the question it belongs to.</p>
<p class="meta"><b>__COUNT__ pieces</b> from the last 90 days · updated __REVIEWED__ · <a href="feed.xml">RSS</a></p>
<p class="meta2">Tracked from the sources this project monitors — not a census of everything published. <a href="../methodology/">How this works</a></p>
<div class="fbar">__SECLINE__<label class="fsel"><input type="checkbox" id="selonly"> Featured only</label></div><div class="fbar2"><input class="srch" id="srch" type="search" placeholder="Search a title, author, or question…" aria-label="Search"></div><div class="qpill" id="qpill"><span id="qpilltext"></span><button id="qclear">clear ×</button></div><p class="rescount" id="rescount"></p><div class="empty" id="empty">No tracked pieces match these filters.<br><button id="resetall">Reset filters</button></div>
__BODY__
<div class="note">Pieces appear here when the project verifies them and judges that they advance one of the map&#39;s questions — whether selected for the question&#39;s page or noted in its ledger. Publication dates are shown where sources provide them; pieces with month-only dates appear at the end of their month. Discovery runs weekly across our source registry, aggregators, and editor submissions; full reviews of each question run on their own cadence.</div>
</div>
<script>
const QNAMES=__QNAMES__;
const ALL=[...document.querySelectorAll('.li')];
const state={secs:new Set(['1','2','3','4','5']),sel:false,q:'',txt:''};

function syncURL(){
  const p=new URLSearchParams();
  if(state.q)p.set('q',state.q);
  if(state.txt)p.set('s',state.txt);
  if(state.sel)p.set('featured','1');
  if(state.secs.size!==5)p.set('sec',[...state.secs].sort().join(''));
  const qs=p.toString();
  history.replaceState(null,'',qs?location.pathname+'?'+qs:location.pathname);
}

function apply(write){
  const toks=state.txt?state.txt.split(/\s+/).filter(Boolean):[];
  let shown=0;
  ALL.forEach(li=>{
    let show=state.secs.has(li.dataset.s);
    if(show&&state.sel&&li.classList.contains('lg'))show=false;
    if(show&&state.q&&li.dataset.q!==state.q)show=false;
    if(show&&toks.length&&!toks.every(t=>li.dataset.search.includes(t)))show=false;
    li.style.display=show?'':'none';
    if(show)shown++;
  });
  // month + earlier-group headings reflect visible counts
  document.querySelectorAll('.mh').forEach(h=>{
    let n=0,el=h.nextElementSibling;
    while(el&&!el.classList.contains('mh')){
      if(el.classList.contains('li')&&el.style.display!=='none')n++;
      el=el.nextElementSibling;}
    h.style.display=n?'':'none';
    const c=h.querySelector('.mc'); if(c)c.textContent='('+n+')';
  });
  document.querySelectorAll('.emh').forEach(h=>{
    let n=0,el=h.nextElementSibling;
    while(el&&!el.classList.contains('mh')&&!el.classList.contains('emh')){
      if(el.classList.contains('li')&&el.style.display!=='none')n++;
      el=el.nextElementSibling;}
    h.style.display=n?'':'none';});
  // question pill
  const pill=document.getElementById('qpill');
  if(state.q){document.getElementById('qpilltext').textContent=
    'Showing '+state.q+' · '+(QNAMES[state.q]||'');pill.classList.add('on');}
  else pill.classList.remove('on');
  // result count + empty state
  const filtered=state.q||state.txt||state.sel||state.secs.size!==5;
  document.getElementById('rescount').textContent=
    filtered?shown+' of '+ALL.length+' pieces shown':'';
  document.getElementById('empty').classList.toggle('on',shown===0);
  if(shown===0&&(state.txt||state.q))window.dispatchEvent(
    new CustomEvent('bq:emptysearch',{detail:state.txt||state.q}));
  if(write!==false)syncURL();
}

document.querySelectorAll('.fsec').forEach(b=>b.addEventListener('click',()=>{
  const on=b.getAttribute('aria-pressed')==='true';
  b.setAttribute('aria-pressed',on?'false':'true');
  if(on)state.secs.delete(b.dataset.s);else state.secs.add(b.dataset.s);
  apply();}));
document.getElementById('selonly').addEventListener('change',e=>{state.sel=e.target.checked;apply();});
document.getElementById('srch').addEventListener('input',e=>{state.txt=e.target.value.trim().toLowerCase();apply();});
document.getElementById('qclear').addEventListener('click',()=>{state.q='';apply();});
document.getElementById('resetall').addEventListener('click',()=>{
  state.q='';state.txt='';state.sel=false;state.secs=new Set(['1','2','3','4','5']);
  document.getElementById('srch').value='';
  document.getElementById('selonly').checked=false;
  document.querySelectorAll('.fsec').forEach(b=>b.setAttribute('aria-pressed','true'));
  apply();});

// restore state from URL
const P=new URLSearchParams(location.search);
const pq=P.get('q'); if(pq&&QNAMES[pq])state.q=pq;
const ps=P.get('s'); if(ps){state.txt=ps.toLowerCase();document.getElementById('srch').value=ps;}
if(P.get('featured')==='1'){state.sel=true;document.getElementById('selonly').checked=true;}
const psec=P.get('sec');
if(psec&&/^[1-5]+$/.test(psec)){
  state.secs=new Set(psec.split(''));
  document.querySelectorAll('.fsec').forEach(b=>
    b.setAttribute('aria-pressed',state.secs.has(b.dataset.s)?'true':'false'));
}
apply(false);
</script>
</body></html>"""




METHODOLOGY_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Methodology — The Biggest Questions About AI</title>
<meta name="description" content="How this site is made: discovery sources, the inclusion threshold, featured versus tracked pieces, the role of AI, human review status, and corrections.">
<style>
:root{--bg:#faf9f6;--panel:#fff;--ink:#1d1c1a;--ink2:#514d45;--ink3:#6f6b5f;--line:#e4e1d8;--gold:#a97729;
--serif:Georgia,'Times New Roman',serif}
@media (prefers-color-scheme:dark){:root{--bg:#191817;--panel:#211f1d;--ink:#f2f0ea;--ink2:#c3c0b4;--ink3:#8f8b7e;--line:#33312d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:680px;margin:0 auto;padding:26px 20px 60px}
header{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.home{font-family:var(--serif);font-size:16px;color:var(--ink);text-decoration:none}
.switch{margin-left:auto;font-size:13px;color:var(--ink3)}
.switch a{color:var(--ink2);text-decoration:none}
h1{font-family:var(--serif);font-weight:400;font-size:30px;margin:18px 0 10px}
h2{font-family:var(--serif);font-weight:400;font-size:20px;margin:26px 0 6px}
p{font-size:14.5px;line-height:1.62;color:var(--ink2);margin:0 0 12px}
strong{color:var(--ink)}
a{color:var(--ink2)}
.upd{font-size:12.5px;color:var(--ink3)}
</style></head><body><div class="wrap">
<header><a class="home" href="../">The Biggest Questions About&nbsp;AI</a>
<nav class="switch"><a href="../">Map</a> · <a href="../browse/">Browse</a> · <a href="../latest/">Latest</a></nav></header>
<h1>Methodology</h1>
<p class="upd">Updated __TODAY__.</p>

<h2>What this site is</h2>
<p>A map of __QCOUNT__ open questions about AI, each with a short framing of the live debate,
curated sources, and a maintained record of substantive recent discussion. The taxonomy — the
sections, the questions, what is included and deliberately left out — is the editor&#39;s.</p>

<h2>Where pieces come from</h2>
<p>Discovery runs over a fixed registry of publications, researchers, and aggregators
(listed in the site&#39;s public repository), supplemented by targeted search and editor
submissions. It is deliberately bounded: counts and coverage describe <strong>what the project
monitors, not everything posted online</strong>. Discovery runs weekly; full reviews of each
question run on their own cadence — faster for fast-moving questions.</p>

<h2>What gets included</h2>
<p>A piece is tracked when it would matter to a thoughtful reader following that question:
new evidence, a distinct argument, a serious rebuttal, a measurement, a well-reported
development. Quality of thought over fame of author. Every tracked piece is fetched and
verified — the piece exists, the author, venue, and date are right — before it appears
anywhere. Social-media posts are included only via a verifiable secondary source.</p>

<h2>Featured versus tracked</h2>
<p>Each question&#39;s page features a small set of pieces, organized editorially; the rest of
what crossed the threshold appears under &ldquo;Additional relevant discussion&rdquo; and in
<a href="../latest/">Latest</a>. Featuring reflects significance, author diversity, and the
shape of the debate — not a verdict that other pieces failed.</p>

<h2>The role of AI, honestly</h2>
<p>This is an AI-assisted publication. Discovery, verification, and first-draft synthesis
(including each question&#39;s &ldquo;What changed&rdquo; note) are performed by AI — Claude — operating
under a written editorial policy, with the editor directing and spot-checking. Every question
page shows two dates: <strong>latest sweep</strong> (when the AI pipeline last fully reviewed it) and its
<strong>editorial review</strong> status. &ldquo;Editorial review pending&rdquo; means a human editor has not yet
examined that page&#39;s selections and synthesis line by line; pages flip to
&ldquo;editor-approved&rdquo; as that happens. One question (3.2.1) additionally carries a long-form
entry with its own review status.</p>

<h2>Volume counts</h2>
<p>The optional discussion-volume numbers (&ldquo;N in 90d&rdquo;) count tracked substantive pieces
in a rolling 90-day window — one count per piece, assigned to one primary question. They are
a lens on where attention is concentrating within the monitored sources, not a measure of
total online discussion, and counts across broad and narrow questions are not perfectly
comparable.</p>

<h2>Corrections</h2>
<p>Disagree with a framing, spot a stale claim, or know a piece we missed?
<a href="https://github.com/elehrer123-arch/ai-question-hierarchy/issues/new?template=suggest-improvement.yml">Suggest a source or correction</a>.
The main criterion for additions: what does this add that the existing material doesn&#39;t?</p>
</div></body></html>"""


def render_methodology(qcount):
    today = _date.today()
    today_h = f"{MONTH_NAMES[today.month-1]} {today.day}, {today.year}"
    out = METHODOLOGY_HTML.replace("__TODAY__", today_h).replace("__QCOUNT__", str(qcount))
    out = out.replace("</body>", analytics_snippet() + "</body>")
    outdir = os.path.join(ROOT, "methodology")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)




def entry_embed(entry, qindex, sections, entry_slugs):
    """Render an entry's body for embedding under its question brief."""
    meta, body = entry["meta"], entry["body"]
    body = crosslink(body, entry["qnum"], entry_slugs)
    md = markdown.Markdown(extensions=["toc", "tables"])
    body_html = md.convert(body)
    core_revised = meta.get("core_revised", meta.get("core_reviewed", "—"))
    review = meta.get("review", "Pending")
    dateline = (f'{meta["status"]} · editorial review {review.lower()}. '
                f'Core article last revised {core_revised}; evidence updated '
                f'{meta.get("evidence_updated", "—")}.')
    cite = (f'“{E(meta["title"])}” <em>The Biggest Questions About AI</em>, '
            f'Elliott Lehrer (ed.), {meta.get("evidence_updated", "2026")}. '
            f'{E(meta["status"])}.')
    toc = "".join(f'<a href="#{t["id"]}">{E(t["name"])}</a>'
                  for t in md.toc_tokens if t["level"] == 2)
    return {"title": meta["title"], "html": body_html, "dateline": dateline,
            "cite": cite, "toc": toc, "author": meta.get("author", "—"),
            "editor": meta.get("editor", "—"), "scope": meta.get("scope", ""),
            "status": meta.get("status", "")}


def render_question_pages(sections, entry_map_full, recent, debates):
    """Static permanent page per question: /questions/<slug>/."""
    base = "https://elehrer123-arch.github.io/ai-question-hierarchy"
    _cut = window_cutoff(90)
    n_pages = 0
    for s in sections:
        c = SECTION_COLORS[s["id"]]
        for su in s["subs"]:
            qs = su["qs"]
            for qi, q in enumerate(qs):
                disp = q["id"]
                anchor = disp.replace(".", "-")
                rq = recent["items"].get(disp)
                deb = debates.get(disp) if debates else None

                # --- status + what-changed
                status_html = ""
                if rq:
                    apv = rq.get("approved")
                    status = (f'editor-approved {E(apv)}' if apv
                              else '<span class="rvpend">editorial review pending</span>')
                    anchor2 = (f'since {E(rq["prev_swept"])}' if rq.get("prev_swept")
                               else E(rq.get("window", "")))
                    moved = rq.get("moved")
                    items_m = moved if isinstance(moved, list) else [moved]
                    chs = []
                    _by_rid = {it["rid"]: it for it in rq.get("items", [])}
                    for i, mvi in enumerate(items_m):
                        t0 = mvi.get("t") if isinstance(mvi, dict) else None
                        b = mvi.get("b") if isinstance(mvi, dict) else mvi
                        rfs = mvi.get("refs", []) if isinstance(mvi, dict) else []
                        sup = ""
                        if rfs:
                            links = "".join(
                                f'<a href="#{E(rd)}" title="{E(_by_rid[rd]["author"])} — '
                                f'{E(_by_rid[rd]["title"])}">{j+1}</a>'
                                for j, rd in enumerate(rfs) if rd in _by_rid)
                            sup = f'<span class="evd">Evidence: {links}</span>'
                        chs.append(f'<div class="ch"><div class="chn">0{i+1}</div>'
                                   + (f'<div class="cht">{E(t0)}</div>' if t0 else '')
                                   + f'<p class="chb">{E(b)}{sup}</p></div>')
                    status_html = (
                        f'<div class="moved" style="--sc:{c}">'
                        f'<div class="mvh">What changed</div>'
                        f'<div class="mvf">{anchor2}{" · " if anchor2 else ""}'
                        f'swept {E(rq["swept"])} · {status}</div>'
                        f'{"".join(chs)}</div>')

                # --- featured items (grouped by debate poles where configured)
                def _hdate(d):
                    mo = MONTH_NAMES[int(d[5:7]) - 1][:3]
                    return f'{int(d[8:10])} {mo} {d[:4]}' if len(d) == 10 else f'{mo} {d[:4]}'

                def _byline(it):
                    a, v = it["author"].strip(), it["venue"].strip()
                    al, vl = a.lower(), v.lower()
                    if al == vl or al.startswith(vl) or vl.startswith(al):
                        return E(a if len(a) >= len(v) else v)
                    return f'{E(a)} · {E(v)}'

                def item_card(it):
                    kind = f'<span class="pk">{E(it.get("kind",""))}</span>' if it.get("kind") else ''
                    via = (f' · via <a href="{E(it["via"]["u"])}">{E(it["via"]["t"])}</a>'
                           if it.get("via") else '')
                    quote = (f'<blockquote>{E(it["quote"])}</blockquote>'
                             if it.get("quote") else '')
                    note = f'<p class="rnote">{E(it["note"])}</p>' if it.get("note") else ''
                    return (f'<article class="rec" id="{E(it["rid"])}">'
                            f'<div class="rtop"><span class="rauth">{_byline(it)}</span>'
                            f' · {_hdate(it["date"])} {kind}{via}</div>'
                            f'<a class="rtt" href="{E(it["url"])}" rel="noopener">{E(it["title"])}</a>'
                            f'{quote}{note}</article>')

                feat_html = ""
                if rq and rq.get("items"):
                    items = rq["items"]
                    led = rq.get("ledger", [])
                    qual = len(items) + len(led)
                    _cnt = (f'{len(items)} featured from {qual} tracked' if led
                            else f'{len(items)} piece' + ('s' if len(items) != 1 else ''))
                    head = (f'<div class="rh">Recent thinking</div>'
                            f'<div class="rhm">{_cnt}'
                            f'{" · " + E(rq["window"]) if rq.get("window") else ""}'
                            f' · <a href="../../latest/?q={disp}">all {qual} chronologically →</a></div>')
                    groups_html = []
                    if deb:
                        assigned = set()
                        for p in deb["poles"]:
                            sub_items = [it for it in items if it.get("pos") == p["k"]]
                            if not sub_items:
                                continue
                            assigned.update(id(it) for it in sub_items)
                            hue = p.get("hue", c)
                            groups_html.append(
                                f'<section class="gsec" style="--kc:{hue}">'
                                f'<div class="glab">{E(p["label"])}</div>'
                                f'<p class="gclaim">{E(p.get("claim",""))}</p>'
                                + "".join(item_card(it) for it in sub_items) + '</section>')
                        rest = [it for it in items if id(it) not in assigned]
                        if rest:
                            groups_html.append(
                                '<section class="gsec"><div class="glab">Also featured</div>'
                                + "".join(item_card(it) for it in rest) + '</section>')
                    else:
                        groups_html.append("".join(item_card(it) for it in items))
                    feat_html = head + "".join(groups_html)
                    if led:
                        rowsl = "".join(
                            f'<div class="ledrow" id="{E(it["rid"])}">'
                            f'<a href="{E(it["url"])}" rel="noopener">{E(it["title"])}</a>'
                            f'<span class="ledm"> — {_byline(it)} · {_hdate(it["date"])}</span></div>'
                            for it in led)
                        feat_html += (f'<details class="leddet"><summary>Additional relevant '
                                      f'discussion ({len(led)})</summary>{rowsl}</details>')

                # --- foundational reading
                canon = "".join(
                    f'<a class="fnd" href="{E(l["u"])}" rel="noopener">{E(l["t"])}'
                    f'<span class="lsrc">{E(l.get("s",""))}{" · " + l["y"] if l.get("y") else ""}</span></a>'
                    for l in q["links"])
                canon_html = (f'<details class="leddet" open><summary>Foundational reading '
                              f'({len(q["links"])})</summary>{canon}</details>') if q["links"] else ""

                # --- embedded full analysis
                emb = entry_map_full.get(disp)
                analysis_html = ""
                if emb:
                    toc_html = (f'<nav class="atoc" aria-label="Analysis contents">'
                                f'<span>Contents</span>{emb["toc"]}</nav>'
                                if emb.get("toc") else "")
                    scope_html = (f'<p class="ascope"><strong>Scope:</strong> {E(emb["scope"])}</p>'
                                  if emb.get("scope") else "")
                    analysis_html = (
                        f'<section class="analysis"><hr class="asep">'
                        f'<div class="rh">Full analysis</div>'
                        f'<h2 class="atitle">{E(emb["title"])}</h2>'
                        f'<p class="adate">{E(emb["dateline"])}<br>'
                        f'Written by {E(emb["author"])} · edited by {E(emb["editor"])}</p>'
                        f'{scope_html}{toc_html}'
                        f'<div class="abody">{emb["html"]}</div>'
                        f'<p class="acite">Cite: {emb["cite"]}</p></section>')

                # --- neighbors
                prevq = qs[qi-1] if qi > 0 else None
                nextq = qs[qi+1] if qi < len(qs)-1 else None
                nav = '<div class="pn2">'
                if prevq:
                    nav += (f'<a href="../{E(prevq["slug"])}/"><small>Previous</small>'
                            f'{prevq["id"]} {E(prevq["t"])}</a>')
                if nextq:
                    nav += (f'<a class="nx" href="../{E(nextq["slug"])}/"><small>Next</small>'
                            f'{nextq["id"]} {E(nextq["t"])}</a>')
                nav += '</div>'

                issue_url = (f'{REPO_ISSUES}/new?template=suggest-improvement.yml&title='
                             + quote_plus(f'[{disp} {q["slug"]}] '))
                desc = q["q"][:155].rsplit(" ", 1)[0] + ("…" if len(q["q"]) > 155 else "")
                page_url = f'{base}/questions/{q["slug"]}/'

                html = QPAGE_TEMPLATE
                html = (html
                    .replace("__PTITLE__", E(f'{q["t"]} — The Biggest Questions About AI'))
                    .replace("__DESC__", E(desc))
                    .replace("__URL__", page_url)
                    .replace("__SC__", c)
                    .replace("__CRUMB__",
                             f'<a href="../../">The map</a> · {s["id"]} {SECTION_NAMES[s["id"]]}'
                             f' · <a href="../../browse/#{su["id"].replace(".", "-")}">'
                             f'{su["id"]} {E(su["t"])}</a>')
                    .replace("__QID__", disp)
                    .replace("__SHORT__", E(q["t"]))
                    .replace("__QUESTION__", E(q["q"]))
                    .replace("__FRAMING__", E(q.get("n", "")))
                    .replace("__STATUS__", status_html)
                    .replace("__FEATURED__", feat_html)
                    .replace("__CANON__", canon_html)
                    .replace("__ANALYSIS__", analysis_html)
                    .replace("__NAV__", nav)
                    .replace("__MAPHREF__", f'../../#q{anchor}')
                    .replace("__BROWSEHREF__", f'../../browse/#q{anchor}')
                    .replace("__ISSUE__", E(issue_url)))
                outdir = os.path.join(ROOT, "questions", q["slug"])
                os.makedirs(outdir, exist_ok=True)
                html = html.replace("</body>", analytics_snippet() + "</body>")
                with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
                    f.write(html)
                n_pages += 1
    return n_pages


def render_sitemap(sections):
    base = "https://elehrer123-arch.github.io/ai-question-hierarchy"
    today = _date.today().isoformat()
    urls = [f"{base}/", f"{base}/browse/", f"{base}/latest/",
            f"{base}/methodology/", f"{base}/poster/"]
    for s in sections:
        for su in s["subs"]:
            for q in su["qs"]:
                urls.append(f'{base}/questions/{q["slug"]}/')
    body = "".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                + body + '</urlset>')
    return len(urls)


QPAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__PTITLE__</title>
<meta name="description" content="__DESC__">
<link rel="canonical" href="__URL__">
<meta property="og:title" content="__PTITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:type" content="article">
<meta property="og:url" content="__URL__">
<style>
:root{--bg:#faf9f6;--panel:#fff;--ink:#1d1c1a;--ink2:#514d45;--ink3:#6f6b5f;--line:#e4e1d8;--gold:#a97729;--sc:__SC__;
--serif:'Charter','Iowan Old Style',Georgia,serif}
@media (prefers-color-scheme:dark){:root{--bg:#191817;--panel:#211f1d;--ink:#f2f0ea;--ink2:#c3c0b4;--ink3:#8f8b7e;--line:#33312d}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:700px;margin:0 auto;padding:24px 20px 60px}
header{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.home{font-family:var(--serif);font-size:15.5px;color:var(--ink);text-decoration:none;font-weight:700}
.switch{margin-left:auto;font-size:13px;color:var(--ink3)}
.switch a{color:var(--ink2);text-decoration:none}
.crumb{font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:var(--sc);margin:22px 0 6px}
.crumb a{color:inherit;text-decoration:none}
.crumb b{color:var(--ink2);font-weight:600}
h1{font-family:var(--serif);font-weight:400;font-size:27px;line-height:1.25;margin:2px 0 8px}
.qq{font-family:var(--serif);font-size:17px;font-style:italic;line-height:1.45;color:var(--ink2);margin:0 0 14px}
.qn{font-size:14.5px;color:var(--ink2);line-height:1.6;margin:0 0 8px}
.quiet{font-size:12.5px;color:var(--ink3);margin:10px 0 18px}
.quiet a{color:var(--ink2)}
.moved{border-top:2px solid var(--sc);background:color-mix(in srgb,var(--sc) 3.5%,transparent);border-radius:0 0 10px 10px;padding:11px 14px;margin:20px 0 8px}
.mvh{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3);font-weight:600;margin-bottom:5px}
.mvf{font-size:11.5px;color:var(--ink3);margin:1px 0 9px}
.rvpend{color:var(--gold)}
.ch{display:flex;gap:10px;margin:7px 0}
.chn{font-size:11px;color:var(--ink3);font-variant-numeric:tabular-nums;padding-top:2px}
.cht{font-weight:600;font-size:13.5px;margin-bottom:2px}
.chb{font-size:13.5px;line-height:1.55;margin:0}
.evd{display:block;margin-top:6px;font-size:11px;color:var(--ink3);letter-spacing:.02em}
.evd a{display:inline-block;min-width:17px;height:17px;line-height:17px;text-align:center;border:1px solid var(--line);border-radius:50%;color:var(--ink2);text-decoration:none;margin-left:4px;font-size:10px}
.evd a:hover{border-color:var(--sc);color:var(--sc)}
.rec:target{outline:2px solid var(--sc);outline-offset:3px}
.rh{font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:var(--ink3);margin:24px 0 4px;font-weight:600}
.rhm{font-size:12.5px;color:var(--ink3);margin-bottom:12px}
.rhm a{color:var(--ink2)}
.gsec{border-left:3px solid var(--kc,var(--line));padding:2px 0 2px 12px;margin:14px 0}
.glab{font-size:11px;letter-spacing:.1em;text-transform:uppercase;font-weight:700;color:var(--kc,var(--ink2))}
.gclaim{font-family:var(--serif);font-style:italic;font-size:12.5px;color:var(--ink2);margin:2px 0 8px}
.rec{border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:11px 14px;margin-bottom:9px}
.rtop{font-size:12px;color:var(--ink3);margin-bottom:3px}
.rauth{color:var(--ink);font-size:12.5px}
.pk{border:1px solid var(--line);border-radius:10px;padding:0 7px;font-size:10px;color:var(--ink3)}
.rtt{font-size:14.5px;color:var(--ink);text-decoration:none;line-height:1.4}
.rtt:hover{text-decoration:underline}
blockquote{font-family:var(--serif);font-size:13px;font-style:italic;color:var(--ink2);border-left:2px solid var(--line);margin:7px 0 4px;padding:0 0 0 10px;line-height:1.5}
.rnote{font-size:13px;color:var(--ink2);line-height:1.5;margin:5px 0 0}
.leddet{margin:14px 0}
.leddet summary{cursor:pointer;font-size:12.5px;color:var(--ink2)}
.ledrow{font-size:13px;padding:5px 0;border-bottom:1px solid var(--line)}
.ledrow a{color:var(--ink);text-decoration:none}
.ledrow a:hover{text-decoration:underline}
.ledm{color:var(--ink3);font-size:12px}
.fnd{display:block;border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:8px 11px;margin:6px 0;text-decoration:none;color:var(--ink);font-size:13px;line-height:1.4}
.lsrc{display:block;font-size:11px;color:var(--ink3);margin-top:1px}
.analysis .asep{border:0;border-top:1px solid var(--line);margin:28px 0 4px}
.atitle{font-family:var(--serif);font-weight:400;font-size:22px;margin:4px 0 4px}
.adate{font-size:12px;color:var(--ink3);margin:0 0 12px}
.ascope{font-size:12.5px;color:var(--ink2);line-height:1.5;margin:0 0 12px}
.atoc{border:1px solid var(--line);border-radius:10px;padding:10px 13px;margin:0 0 18px;font-size:12.5px}
.atoc span{display:block;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3);margin-bottom:5px}
.atoc a{display:block;color:var(--ink2);text-decoration:none;padding:2px 0;line-height:1.35}
.atoc a:hover{color:var(--ink);text-decoration:underline}
.abody{font-family:var(--serif);font-size:15px;line-height:1.65;color:var(--ink)}
.abody h2{font-family:var(--serif);font-size:19px;margin:22px 0 8px}
.abody a{color:var(--ink2)}
.acite{font-size:12px;color:var(--ink3);border-top:1px solid var(--line);padding-top:10px;margin-top:18px}
.pn2{display:flex;justify-content:space-between;gap:14px;border-top:1px solid var(--line);margin-top:30px;padding-top:14px}
.pn2 a{font-size:13px;color:var(--ink2);text-decoration:none;max-width:47%;line-height:1.4}
.pn2 a:hover{color:var(--ink)}
.pn2 .nx{text-align:right;margin-left:auto}
.pn2 small{display:block;font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3)}
footer{border-top:1px solid var(--line);margin-top:26px;padding-top:12px;font-size:12px;color:var(--ink3);line-height:1.6}
footer a{color:var(--ink2)}
</style></head><body><div class="wrap">
<header><a class="home" href="../../">The Biggest Questions About&nbsp;AI</a>
<nav class="switch" aria-label="View switch"><a href="../../">Map</a> · <a href="../../browse/">Browse</a> · <a href="../../latest/">Latest</a></nav></header>
<div class="crumb">__CRUMB__ · <b>__QID__</b></div>
<h1>__SHORT__</h1>
<p class="qq">__QUESTION__</p>
<p class="qn">__FRAMING__</p>
<p class="quiet"><a href="__MAPHREF__">View on the map →</a> · <a href="__BROWSEHREF__">Open in Browse →</a></p>
__STATUS__
__FEATURED__
__CANON__
__ANALYSIS__
__NAV__
<footer>This is the permanent page for question __QID__. <a href="../../methodology/">Methodology</a> ·
<a href="__ISSUE__">Suggest a source or correction</a></footer>
</div></body></html>"""





def analytics_snippet():
    """Return the analytics <script> block, or '' when disabled.

    Config lives in data/analytics.json and is off by default. Nothing is
    emitted unless an operator explicitly enables it, so the built site is
    tracker-free until then.
    """
    path = os.path.join(ROOT, "data", "analytics.json")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("enabled") or not cfg.get("goatcounter_code"):
        return ""
    code = cfg["goatcounter_code"]
    empty = """
<script>window.addEventListener('bq:emptysearch',function(e){
  if(window.goatcounter&&window.goatcounter.count)window.goatcounter.count(
    {path:'/_search-no-results/'+encodeURIComponent((e.detail||'').slice(0,60)),
     title:'search with no results',event:true});});</script>""" if cfg.get("track_empty_searches") else ""
    return (f'<script data-goatcounter="https://{code}.goatcounter.com/count" '
            f'async src="//gc.zgo.at/count.js"></script>{empty}')


def render_poster(sections):
    import math
    qn = sum(len(su["qs"]) for s in sections for su in s["subs"])
    CX, CY = 560, 568
    r1, r2, r3 = 124, 244, 336
    gap = math.radians(3.2)
    avail = 2 * math.pi - 5 * gap

    def pol(r, t):
        return (CX + r * math.cos(t), CY + r * math.sin(t))

    def P(r, t):
        x, y = pol(r, t)
        return f"{x:.1f},{y:.1f}"

    B = "../browse/"
    svg = [f'<circle cx="{CX}" cy="{CY}" r="46" fill="#1d1c1a"/>'
           f'<text x="{CX}" y="{CY-4}" fill="#fff" font-size="13" font-weight="700" text-anchor="middle" '
           f'font-family="Georgia,serif">The map</text>'
           f'<text x="{CX}" y="{CY+13}" fill="#cfcabd" font-size="9.5" text-anchor="middle">{qn} questions</text>']
    theta = -math.pi / 2
    for s in sections:
        c = SECTION_COLORS[s["id"]]
        nq = sum(len(su["qs"]) for su in s["subs"])
        span = avail * nq / qn
        s0, s1 = theta, theta + span
        smid = (s0 + s1) / 2
        qa, i = {}, 0
        for su in s["subs"]:
            for q in su["qs"]:
                qa[q["id"]] = s0 + span * (i + 0.5) / nq
                i += 1
        x1, y1 = pol(48, smid); x2, y2 = pol(r1 - 30, smid)
        svg.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                   f'stroke="{c}" stroke-width="2.2" opacity=".55"/>')
        for su in s["subs"]:
            ua = sum(qa[q["id"]] for q in su["qs"]) / len(su["qs"])
            svg.append(f'<path d="M {P(r1+24,smid)} C {P(r1+78,smid)} {P(r2-64,ua)} {P(r2-7,ua)}" '
                       f'fill="none" stroke="{c}" stroke-width="1.4" opacity=".45"/>')
            dx, dy = pol(r2, ua)
            deg = math.degrees(ua) % 360
            flip = 90 < deg < 270
            rot = deg + 180 if flip else deg
            xoff = -26 if flip else 9
            svg.append(f'<a href="{B}#{su["id"].replace(".","-")}"><title>{E(su["t"])}</title>'
                       f'<circle cx="{dx:.1f}" cy="{dy:.1f}" r="4" fill="{c}"/>'
                       f'<text transform="translate({dx:.1f},{dy:.1f}) rotate({rot:.1f})" x="{xoff}" y="-5" '
                       f'font-size="9" font-weight="700" fill="{c}">{su["id"]}</text></a>')
            for q in su["qs"]:
                t = qa[q["id"]]
                svg.append(f'<path d="M {P(r2+6,ua)} C {P(r2+56,ua)} {P(r3-46,t)} {P(r3-5,t)}" '
                           f'fill="none" stroke="{c}" stroke-width="1" opacity=".33"/>')
                lx, ly = pol(r3, t)
                deg = math.degrees(t) % 360
                flip = 90 < deg < 270
                rot = deg + 180 if flip else deg
                anchor = "end" if flip else "start"
                crux = ""
                svg.append(f'<a href="{B}#q{q["id"].replace(".","-")}"><title>{E(q["id"]+" · "+q["q"])}</title>'
                           f'<text transform="translate({lx:.1f},{ly:.1f}) rotate({rot:.1f})" text-anchor="{anchor}" '
                           f'font-size="10.5" fill="#514d45">{E(q["t"])}{crux}</text></a>')
        px, py = pol(r1, smid)
        name = f'{s["id"]} {SECTION_NAMES[s["id"]]}'
        w = len(name) * 7.6 + 22
        svg.append(f'<a href="{B}#{s["id"]}"><rect x="{px-w/2:.1f}" y="{py-13:.1f}" width="{w:.1f}" height="26" '
                   f'rx="13" fill="{c}"/><text x="{px:.1f}" y="{py+4:.1f}" fill="#fff" font-size="12" '
                   f'font-weight="700" text-anchor="middle">{E(name)}</text></a>')
        theta = s1 + gap
    body = "".join(svg)
    svg_doc = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 1136" '
               f'font-family="-apple-system,Helvetica,Arial,sans-serif">'
               f'<rect width="1120" height="1136" fill="#faf9f6"/>{body}</svg>')
    outdir = os.path.join(ROOT, "poster")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "map.svg"), "w", encoding="utf-8") as f:
        f.write(svg_doc)
    page = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f'<title>Poster — The Biggest Questions About AI</title>'
            f'<link rel="canonical" href="https://elehrer123-arch.github.io/ai-question-hierarchy/poster/">'
            f'<style>body{{background:#faf9f6;color:#1d1c1a;font-family:-apple-system,Helvetica,Arial,sans-serif;'
            f'padding:22px 18px 60px}}a.home{{font-family:Georgia,serif;font-weight:700;color:#1d1c1a;'
            f'text-decoration:none;font-size:15px}}h1{{font-family:Georgia,serif;font-size:24px;margin:14px 0 4px}}'
            f'p{{color:#514d45;font-size:13.5px;max-width:620px}}p a{{color:#514d45}}'
            f'.wrap{{overflow:auto}}svg{{display:block;margin:0 auto;max-width:1120px;min-width:760px;width:100%}}'f'.topbar{{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}}'f'.switch{{margin-left:auto;font-size:13px;color:#6f6b5f}}.switch a{{color:#514d45;text-decoration:none}}'f'@media (prefers-color-scheme:dark){{body{{background:#191817;color:#f2f0ea}}a.home{{color:#f2f0ea}}'f'p{{color:#c3c0b4}}p a{{color:#c3c0b4}}.switch a{{color:#c3c0b4}}}}</style>'
            f'</head><body><div class="topbar"><a class="home" href="../">The Biggest Questions About AI</a>'
            f'<nav class="switch"><a href="../">Map</a> · <a href="../browse/">Browse</a> · '
            f'<a href="../latest/">Latest</a></nav></div>'
            f'<h1>The whole map in one circle</h1>'
            f'<p>All {qn} questions in one circle. Tap or click any label to open its question page; '
            f'hover (on a pointer device) shows the full question. '
            f'<a href="map.svg" download>Download as SVG</a>.</p>'
            f'<div class="wrap">{svg_doc}</div></body></html>')
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    sections = load_sections()
    errors = validate(sections)
    qindex = question_index(sections)
    entries, entry_errors = load_entries(qindex)
    errors += entry_errors
    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        sys.exit(1)

    entry_slugs = {e["qnum"]: e["meta"]["slug"] for e in entries}
    overview_links = {}
    for entry in entries:
        path = render_entry(entry, qindex, sections, entry_slugs)
        overview_links.setdefault(entry["qnum"], []).append((entry["meta"]["title"], path))
        print(f"built {path}")

    entry_map = {}
    for e in entries:
        entry_map[e["qnum"]] = {"slug": e["meta"]["slug"], "title": e["meta"].get("short_title", e["meta"]["title"]),
                                "status": e["meta"]["status"], "excerpt": entry_excerpt(e["body"])}

    recent, recent_errors = load_recent(qindex)
    debates, debate_errors = load_debates(qindex)
    recent_errors += debate_errors
    # pos classifications must reference a real pole; debates canon idx must be in range
    _qid_by_disp = {q["id"]: q for q in qindex.values()}
    for disp, entry in recent["items"].items():
        dcfg = debates.get(disp)
        poles = {p["k"] for p in dcfg["poles"]} if dcfg else set()
        for it in entry.get("items", []) + entry.get("ledger", []):
            if it.get("pos") and it["pos"] not in poles:
                recent_errors.append(f"{disp}: pos {it['pos']!r} has no matching debate pole")
    for disp, dcfg in (debates or {}).items():
        qq = _qid_by_disp.get(disp)
        ncanon = len(qq["links"]) if qq else 0
        for idx in (dcfg.get("canon") or {}):
            if not idx.isdigit() or int(idx) >= ncanon:
                recent_errors.append(f"debates {disp}: canon index {idx} out of range (canon has {ncanon})")
    if recent_errors:
        print("RECENT VALIDATION FAILED:", file=sys.stderr)
        for e in recent_errors:
            print("  -", e, file=sys.stderr)
        sys.exit(1)

    render_map(sections, entry_map, recent)
    render_browse(sections, entry_map, recent, debates)
    render_poster(sections)
    entry_embeds = {e["qnum"]: entry_embed(e, qindex, sections, entry_slugs) for e in entries}
    qp_n = render_question_pages(sections, entry_embeds, recent, debates)
    sm_n = render_sitemap(sections)
    latest_n = render_latest(sections, recent)
    render_methodology(sum(len(su["qs"]) for s in sections for su in s["subs"]))
    qcount, lcount = render_index(sections, overview_links, outdir="all", legacy=True)
    print(f"built map (index.html), browse/, latest/ ({latest_n} pieces + RSS), {qp_n} question pages, sitemap ({sm_n} URLs), poster/, all/: {qcount} questions, "
          f"{lcount} source links, {len(entries)} entry page(s)")
