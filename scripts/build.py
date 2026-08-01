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
from urllib.parse import urlparse

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
    entries, errors = [], []
    for kind, folder in (("crux", "cruxes"), ("question", "questions")):
        for path in sorted(glob.glob(os.path.join(ROOT, "content", folder, "*.md"))):
            meta, body = parse_front_matter(path)
            fname = os.path.splitext(os.path.basename(path))[0]
            for req in ("slug", "title", "status", "section"):
                if not meta.get(req):
                    errors.append(f"{path}: front matter missing '{req}'")
            if meta.get("slug") != fname:
                errors.append(f"{path}: slug {meta.get('slug')!r} != filename {fname!r}")
            bears = [b.strip() for b in meta.get("bears_on", "").split(",") if b.strip()]
            for b in bears:
                if b not in qindex:
                    errors.append(f"{path}: bears_on {b} is not a question number")
            entries.append({"kind": kind, "folder": folder, "meta": meta, "body": body, "bears": bears})
    return entries, errors


def render_entry(entry, qindex):
    meta, body = entry["meta"], entry["body"]
    md = markdown.Markdown(extensions=["toc", "tables"])
    body_html = md.convert(body)
    toc = "".join(
        f'<a href="#{t["id"]}">{E(t["name"])}</a>'
        for t in md.toc_tokens if t["level"] == 2
    )
    bears = "".join(
        f'<a href="../../#q{b.replace(".", "-")}">{b} {E(qindex[b]["t"])}</a>'
        for b in entry["bears"]
    )
    crumb = f'{"Crux overview" if entry["kind"] == "crux" else "Question entry"} · {SECTION_ORDER[int(meta["section"]) - 1].capitalize()}'
    with open(os.path.join(ROOT, "templates", "entry.html"), encoding="utf-8") as f:
        tpl = f.read()
    out = (tpl.replace("__TITLE__", E(meta["title"]))
              .replace("__DESC__", E(meta.get("description", meta["title"])))
              .replace("__PATH__", f'{entry["folder"]}/{meta["slug"]}/')
              .replace("__SECTION__", E(meta["section"]))
              .replace("__CRUMB__", E(crumb))
              .replace("__ROOT__", "../../")
              .replace("__STATUS__", E(meta["status"]))
              .replace("__CORE_REVIEWED__", E(meta.get("core_reviewed", "—")))
              .replace("__EVIDENCE_UPDATED__", E(meta.get("evidence_updated", "—")))
              .replace("__SCOPE__", E(meta.get("scope", "—")))
              .replace("__BEARS__", bears)
              .replace("__TOC__", toc)
              .replace("__BODY__", body_html))
    outdir = os.path.join(ROOT, entry["folder"], meta["slug"])
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
    return f'{entry["folder"]}/{meta["slug"]}/'


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
                cruxline = (f'<div class="cruxline"><b>✱ Load-bearing crux:</b> {E(q["crux"])}</div>'
                            if q.get("crux") else "")
                overviews = "".join(
                    f'<a class="entrylink" href="{E(href)}">Read the crux overview: “{E(title)}” →</a>'
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
                    f'{cruxline}{overviews}'
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

    overview_links = {}
    for entry in entries:
        path = render_entry(entry, qindex)
        for b in entry["bears"]:
            overview_links.setdefault(b, []).append((entry["meta"]["title"], path))
        print(f"built {path}")

    qcount, lcount = render_index(sections, overview_links)
    print(f"built index.html: {qcount} questions, {lcount} source links, {len(entries)} entry page(s)")
