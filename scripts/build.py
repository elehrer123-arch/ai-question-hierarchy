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
    outdir = os.path.join(ROOT, entry["folder"], meta["slug"])
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
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
                x = " ".join([q["id"], q["t"], q["q"], q["n"]] +
                             [l["t"] + " " + l["s"] for l in q["links"]]).lower()
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
                    n90 = sum(1 for it in rqe.get("items", []) + rqe.get("ledger", [])
                              if it.get("date", "") >= "2026-05")
                    vol = '<span class="vol"> · ' + str(n90) + ' in 90d</span>'
                inner.append(
                    f'<div class="bq" id="n{anchor}" data-sec="{s["id"]}" data-sub="{su["id"]}" data-x="{E(x)}">'
                    f'<button class="bqhead" aria-expanded="false"><span class="bqid">{q["id"]}</span>{E(q["t"])}{star}{vol}</button>'
                    f'<p class="bqq">{E(q["q"])}</p>'
                    f'<div class="bqbody"><div class="bqin">'
                    f'<p class="bfull">{E(q["q"])}</p>'
                    f'<p class="bn">{E(q["n"])}</p>'
                    f'<div class="blinks">{links}</div>{entlink}'
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
        for field in ("tier", "reviewed", "moved"):
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
                          "crux": q.get("crux", ""), "slug": q["slug"], "links": q["links"]}
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




MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]

def _parse_reviewed(s):
    m = re.match(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", s or "")
    if not m or m.group(1) not in MONTH_NAMES:
        return ""
    return f"{m.group(3)}-{MONTH_NAMES.index(m.group(1))+1:02d}-{int(m.group(2)):02d}"


def render_latest(sections, recent, cutoff="2026-05"):
    """Render latest/index.html and latest/feed.xml from stream data.

    Shows every selected and ledger item published on/after `cutoff`
    (same cutoff as the map's 90-day volume lens, so counts reconcile).
    Month sections, newest first; day-precision items sort before
    month-only ones within a month.
    """
    qmeta = {}
    for s in sections:
        for su in s["subs"]:
            for q in su["qs"]:
                qmeta[q["id"]] = {"t": q["t"], "sec": s["id"]}

    rows = []
    max_reviewed = ""
    for qid_disp, entry in recent["items"].items():
        rv = _parse_reviewed(entry.get("reviewed", ""))
        if rv > max_reviewed:
            max_reviewed = rv
        for it, sel in [(i, True) for i in entry.get("items", [])] +                        [(i, False) for i in entry.get("ledger", [])]:
            if it["date"][:7] >= cutoff:
                rows.append({"d": it["date"], "sel": sel, "q": qid_disp,
                             "qt": qmeta[qid_disp]["t"], "sec": qmeta[qid_disp]["sec"],
                             "title": it["title"], "author": it["author"],
                             "venue": it["venue"], "url": it["url"],
                             "kind": it.get("kind", ""), "note": it.get("note", "")})

    # newest month first; within a month, day-precision (desc) before month-only
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

    body = []
    for m, items in months:
        body.append(f'<h2 class="mh">{month_h(m)} <span class="mc">({len(items)})</span></h2>')
        for r in items:
            anchor = "q" + r["q"].replace(".", "-")
            note = f'<div class="lnote">{E(r["note"])}</div>' if (r["sel"] and r["note"]) else ""
            kind = f'<span class="lkind">{E(r["kind"])}</span>' if r["kind"] else ""
            body.append(
                f'<article class="li{"" if r["sel"] else " lg"}" data-s="{r["sec"]}">'
                f'<div class="ld">{day_h(r["d"])}</div>'
                f'<div class="lb"><a class="lt" href="{E(r["url"])}" rel="noopener">{E(r["title"])}</a>'
                f'<div class="lm">{E(r["author"])} · {E(r["venue"])} {kind}</div>{note}'
                f'<a class="lq" href="../browse/#{anchor}" style="color:var(--c{r["sec"]})">'
                f'&rarr; {r["q"]} {E(r["qt"])}</a></div></article>')

    html = LATEST_TEMPLATE
    html = (html.replace("__BODY__", "\n".join(body))
                .replace("__SECLINE__", secline)
                .replace("__COUNT__", str(len(rows)))
                .replace("__REVIEWED__", E(max_rev_h)))
    outdir = os.path.join(ROOT, "latest")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # RSS: 60 most recent entries
    def rfc822(d):
        dd = d if len(d) == 10 else d + "-01"
        y, mo, day = int(dd[:4]), int(dd[5:7]), int(dd[8:10])
        import calendar
        wd = calendar.weekday(y, mo, day)
        return (f"{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][wd]}, {day:02d} "
                f"{MONTH_NAMES[mo-1][:3]} {y} 00:00:00 GMT")

    def X(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    rss_items = []
    for r in rows[:60]:
        desc = X(r["note"]) if r["note"] else f'{X(r["author"])} · {X(r["venue"])}'
        rss_items.append(
            f"<item><title>{X(r['title'])}</title><link>{X(r['url'])}</link>"
            f"<guid isPermaLink=\"true\">{X(r['url'])}</guid>"
            f"<pubDate>{rfc822(r['d'])}</pubDate>"
            f"<category>{X(r['q'] + ' ' + r['qt'])}</category>"
            f"<description>{desc}</description></item>")
    rss = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
           "<rss version=\"2.0\"><channel>"
           "<title>The Biggest Questions About AI — Latest</title>"
           "<link>https://elehrer123-arch.github.io/ai-question-hierarchy/latest/</link>"
           "<description>Substantive recent pieces observed by our reviews, "
           "across all 127 questions.</description>"
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
.meta{font-size:12.5px;color:var(--ink3);margin:0 0 18px}
.meta a{color:var(--ink2)}
.fbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
.fsec{border:1px solid var(--line);background:var(--panel);border-radius:16px;
padding:4px 11px 4px 8px;font-size:12px;color:var(--ink2);cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.fsec[aria-pressed="false"]{opacity:.38}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.fsel{margin-left:auto;font-size:12px;color:var(--ink3);display:inline-flex;gap:5px;align-items:center;cursor:pointer}
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
.note{margin-top:30px;border-top:1px solid var(--line);padding-top:12px;
font-size:12.5px;color:var(--ink2);line-height:1.55;max-width:620px}
</style></head><body>
<div class="wrap">
<header><a class="home" href="../">The Biggest Questions About&nbsp;AI</a>
<nav class="switch" aria-label="View switch"><a href="../">Map</a> · <a href="../browse/">Browse</a> · <b style="color:var(--ink)">Latest</b></nav></header>
<h1>Latest</h1>
<p class="lede">Substantive recent pieces our reviews found across all 127 questions — newest first, each linked to the question it belongs to.</p>
<p class="meta">__COUNT__ pieces since May 2026 · drawn from reviews through __REVIEWED__ · what our reviews observed, not a census of discussion · <a href="feed.xml">RSS</a></p>
<div class="fbar">__SECLINE__<label class="fsel"><input type="checkbox" id="selonly"> Selected only</label></div>
__BODY__
<div class="note">Pieces appear here when a review verifies them and judges that they advance one of the map&#39;s questions — whether selected for the question&#39;s page or noted in its ledger. Publication dates are shown where sources provide them; pieces with month-only dates appear at the end of their month. Discovery runs weekly across our source registry, aggregators, and editor submissions; full reviews of each question run on their own cadence.</div>
</div>
<script>
document.querySelectorAll('.fsec').forEach(b=>b.addEventListener('click',()=>{
  const on=b.getAttribute('aria-pressed')==='true';
  b.setAttribute('aria-pressed',on?'false':'true');
  const active=new Set([...document.querySelectorAll('.fsec[aria-pressed="true"]')].map(x=>x.dataset.s));
  document.querySelectorAll('.li').forEach(li=>{li.style.display=active.has(li.dataset.s)?'':'none';});
  document.querySelectorAll('.mh').forEach(h=>{
    let n=0,el=h.nextElementSibling;
    while(el&&!el.classList.contains('mh')){if(el.classList.contains('li')&&el.style.display!=='none'&&(!document.body.classList.contains('selonly')||!el.classList.contains('lg')))n++;el=el.nextElementSibling;}
    h.style.display=n?'':'none';});
}));
document.getElementById('selonly').addEventListener('change',e=>{
  document.body.classList.toggle('selonly',e.target.checked);});
</script>
</body></html>"""


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
            f'.wrap{{overflow:auto}}svg{{display:block;margin:0 auto;max-width:1120px;min-width:760px;width:100%}}</style>'
            f'</head><body><a class="home" href="../">← The Biggest Questions About AI</a>'
            f'<h1>The whole map in one circle</h1>'
            f'<p>All {qn} questions by their short labels. Hover any label for the full question; click to open it in '
            f'<a href="../browse/">Browse</a>. <a href="map.svg" download>Download as SVG</a>.</p>'
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
    if recent_errors:
        print("RECENT VALIDATION FAILED:", file=sys.stderr)
        for e in recent_errors:
            print("  -", e, file=sys.stderr)
        sys.exit(1)

    render_map(sections, entry_map, recent)
    render_browse(sections, entry_map, recent, debates)
    render_poster(sections)
    latest_n = render_latest(sections, recent)
    qcount, lcount = render_index(sections, overview_links, outdir="all", legacy=True)
    print(f"built map (index.html), browse/, latest/ ({latest_n} pieces + RSS), poster/, all/: {qcount} questions, "
          f"{lcount} source links, {len(entries)} entry page(s)")
