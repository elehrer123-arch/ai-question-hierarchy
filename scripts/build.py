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
    """One entry per question: content/questions/<slug>.md, where <slug> must equal
    the question's slug in data/. Old URLs are preserved via redirect_from."""
    entries, errors = [], []
    for path in sorted(glob.glob(os.path.join(ROOT, "content", "questions", "*.md"))):
        meta, body = parse_front_matter(path)
        fname = os.path.splitext(os.path.basename(path))[0]
        for req in ("slug", "title", "status", "section", "question"):
            if not meta.get(req):
                errors.append(f"{path}: front matter missing '{req}'")
        if meta.get("slug") != fname:
            errors.append(f"{path}: slug {meta.get('slug')!r} != filename {fname!r}")
        qnum = meta.get("question")
        if qnum not in qindex:
            errors.append(f"{path}: question {qnum!r} is not a question number")
        elif qindex[qnum]["slug"] != meta.get("slug"):
            errors.append(f"{path}: slug {meta.get('slug')!r} != question {qnum}'s slug {qindex[qnum]['slug']!r}")
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
    qlink = (f'<a href="../../#q{qnum.replace(".", "-")}">{qnum} · {E(qindex[qnum]["t"])} — view in the map</a>')
    subsection = find_subsection(sections, qnum)
    crumb = f'Question {qnum} · {E(subsection["t"])}'
    subhref = f'../../#sub{subsection["id"].replace(".", "-")}'
    core_revised = meta.get("core_revised", meta.get("core_reviewed", "—"))
    review = meta.get("review", "Pending")
    dateline = (f'{meta["status"]} · editorial review {review.lower()}. '
                f'Core article last revised {core_revised}; evidence updated {meta.get("evidence_updated", "—")}.')
    mark = '<span class="cruxmark" title="Load-bearing crux">✱</span>' if meta.get("crux") else ""
    cruxnote = (f'<p class="cruxnote"><span class="cx">✱</span> Bears on the load-bearing crux: <em>{E(meta["crux"])}</em></p>'
                if meta.get("crux") else "")
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
def render_index(sections, overview_links):
    qcount = sum(len(su["qs"]) for s in sections for su in s["subs"])
    lcount = sum(len(q["links"]) for s in sections for su in s["subs"] for q in su["qs"])

    chain = []
    for i, s in enumerate(sections):
        if i:
            chain.append('<span class="arrow" aria-hidden="true">→</span>')
        chain.append(
            f'<a href="#s{s["id"]}" style="border-top:3px solid var(--c{s["id"]})">'
            f'<span class="cnum">{s["id"]}</span><span class="cname">{E(s["name"])}</span>'
            f'<span class="cq">{E(s["tag"])}</span></a>'
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
                f'<p class="subintro">{E(su["intro"])}</p>'
                f'<div class="qlist" id="{qlid}">'
            )
            for q in su["qs"]:
                qid = "q" + q["id"].replace(".", "-")
                qbid = "qbody" + q["id"].replace(".", "-")
                mark = (f'<span class="cruxmark" title="Load-bearing crux: {E(q["crux"])}">✱</span>'
                        if q.get("crux") else "")
                overviews = "".join(
                    f'<a class="entrylink" href="{E(href)}">Read the full entry →</a>'
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
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
    return qcount, lcount


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

    qcount, lcount = render_index(sections, overview_links)
    print(f"built index.html: {qcount} questions, {lcount} source links, {len(entries)} entry page(s)")
