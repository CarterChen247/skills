#!/usr/bin/env python3
"""Render a pr-change-walkthrough / pr-risk-review Markdown report to a
self-contained interactive HTML page, and store both as the review cache.

Usage:
  render_report.py --kind walkthrough|risks --repo OWNER/REPO --pr N \
      --base MERGE_BASE_SHA --base-ref "main @ SHA" --head HEAD_SHA \
      [--skill-version 1] [--open] < report.md

Writes <dir>/<pr>-<kind>.md (with cache header) and <dir>/<pr>-<kind>.html,
where <dir> is <root>/<owner>/<repo> and <root> is $PR_REVIEW_DIR or ~/.cache/pr-review.
Stdlib only. Every piece of report text is HTML-escaped.
"""
import argparse
import datetime
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse

FIELDS = ["Before", "After", "Why it matters", "Status", "Scenario", "Impact",
          "Review Target", "How to Verify", "Evidence"]
META_KEYS = ["PR", "Base", "Head", "Analyzed Head", "Behavior basis", "Coverage"]
INLINE_LABELS = ["Also changed (not detailed)", "Other P2 candidates", "Unchanged",
                 "Unknowns", "Important Unknowns"]
CHECK_SECTIONS = ("review pointers", "human review priorities")

REF_RE = re.compile(
    r"(?P<path>[\w@+\-.]+(?:/[\w@+\-.\[\]]+)*\.[\w]+):L(?P<a>\d+)(?:-(?P<b>\d+))?"
    r"(?P<rev>\s*\((?:head|base)\))?")


class Ctx:
    def __init__(self, repo, head, base):
        self.repo, self.head, self.base = repo, head, base

    def link(self, path, a, b, rev):
        sha = self.base if rev and "base" in rev else self.head
        frag = f"#L{a}" + (f"-L{b}" if b else "")
        return (f"https://github.com/{self.repo}/blob/{sha}/"
                f"{urllib.parse.quote(path)}{frag}")


def inline(text, ctx):
    """Escape, then apply `code`, **bold** and evidence-ref links."""
    out, pos = [], 0
    for m in re.finditer(r"`([^`]+)`", text):
        out.append(_plain(text[pos:m.start()], ctx))
        out.append(f"<code>{_refs(html.escape(m.group(1)), m.group(1), ctx)}</code>")
        pos = m.end()
    out.append(_plain(text[pos:], ctx))
    return "".join(out)


def _plain(s, ctx):
    esc = html.escape(s)
    esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
    esc = re.sub(r"\bUNKNOWN\b", '<span class="tag unk">UNKNOWN</span>', esc)
    return _refs(esc, s, ctx)


def _refs(esc, raw, ctx):
    # Refs contain no HTML-special characters, so matching on escaped text is safe.
    def sub(m):
        if "/" not in m.group("path"):
            return m.group(0)  # bare file name: no reliable permalink
        url = ctx.link(m.group("path"), m.group("a"), m.group("b"), m.group("rev"))
        return f'<a class="ref" href="{html.escape(url)}" target="_blank" rel="noopener">{m.group(0)}</a>'
    return REF_RE.sub(sub, esc)


def parse(md):
    md = re.sub(r"^<!--.*?-->\s*", "", md, flags=re.S)
    doc = {"title": "", "meta": [], "sections": []}
    sec = card = None
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            continue
        if line.startswith("# "):
            doc["title"] = line[2:].strip()
            continue
        if line.startswith("## "):
            sec = {"title": line[3:].strip(), "blocks": []}
            doc["sections"].append(sec)
            card = None
            continue
        if sec is None:
            k, _, v = line.partition(":")
            if k.strip() in META_KEYS and v:
                doc["meta"].append((k.strip(), v.strip()))
            continue
        if line.startswith("### "):
            card = {"type": "card", "title": line[4:].strip(), "rows": [], "evidence": [], "text": []}
            sec["blocks"].append(card)
            continue
        if not line.strip():
            continue
        target = card if card is not None else None
        k, sep, v = line.partition(":")
        key = k.strip()
        if target is not None and sep and key in FIELDS:
            target["rows"].append([key, v.strip()])
            continue
        if card is None and sep and key in INLINE_LABELS:
            sec["blocks"].append({"type": "labeled", "label": key, "text": v.strip()})
            continue
        if sep and key in INLINE_LABELS and card is not None:
            # e.g. "Also changed (not detailed):" right after the last card
            card = None
            sec["blocks"].append({"type": "labeled", "label": key, "text": v.strip()})
            continue
        m_li = re.match(r"^\s*[-*]\s+(.*)", line)
        m_ol = re.match(r"^\s*\d+\.\s+(.*)", line)
        if target is not None and m_li and target["rows"] and target["rows"][-1][0] == "Evidence":
            target["evidence"].append(m_li.group(1))
            continue
        if target is not None:
            if target["rows"] and not (m_li or m_ol):
                target["rows"][-1][1] += " " + line.strip()
            else:
                target["text"].append(line.strip())
            continue
        if m_ol or m_li:
            sec["blocks"].append({"type": "ol" if m_ol else "li",
                                  "text": (m_ol or m_li).group(1)})
        else:
            sec["blocks"].append({"type": "p", "text": line.strip()})
    return doc


def render(doc, kind, ctx, key, generated):
    h = []
    for sec in doc["sections"]:
        checklist = sec["title"].lower() in CHECK_SECTIONS
        body, items = [], 0
        for b in sec["blocks"]:
            if b["type"] == "card":
                body.append(render_card(b, ctx, f"c{len(body)}-{sec['title']}"))
            elif b["type"] == "labeled":
                body.append(f'<p class="labeled"><strong>{html.escape(b["label"])}:</strong> {inline(b["text"], ctx)}</p>')
            elif b["type"] in ("ol", "li") and checklist:
                items += 1
                cid = html.escape(f"i{items}-{sec['title']}")
                body.append(f'<label class="check"><input type="checkbox" data-id="{cid}"><span>{inline(b["text"], ctx)}</span></label>')
            elif b["type"] in ("ol", "li"):
                body.append(f'<p class="li">• {inline(b["text"], ctx)}</p>')
            else:
                cls = "flow" if "→" in b["text"] else ""
                body.append(f'<p class="{cls}">{inline(b["text"], ctx)}</p>')
        sid = re.sub(r"\W+", "-", sec["title"].lower())
        h.append(f'<section id="{sid}"><details open><summary><h2>{html.escape(sec["title"])}</h2></summary>{"".join(body)}</details></section>')

    prios = sorted({c["prio"] for c in _cards(doc, ctx)} - {None})
    filt = ""
    if prios:
        btns = "".join(f'<button data-p="{p}" class="on {p.lower()}">{p}</button>' for p in prios)
        filt = f'<div class="filters">Show: {btns}<button id="hide-done">Hide checked</button></div>'
    meta = "".join(f"<div><dt>{html.escape(k)}</dt><dd>{inline(v, ctx)}</dd></div>" for k, v in doc["meta"])
    title = html.escape(doc["title"] or ("PR Risk Review" if kind == "risks" else "PR Change Walkthrough"))
    return TEMPLATE.format(
        title=title, meta=meta, filters=filt, body="".join(h),
        key=json.dumps(key).replace("<", "\\u003c"), generated=html.escape(generated),
        progress='<span id="progress"></span>')


def _cards(doc, ctx):
    for sec in doc["sections"]:
        for b in sec["blocks"]:
            if b["type"] == "card":
                m = re.match(r"(P[012])\b", b["title"])
                yield {"prio": m.group(1) if m else None}


def render_card(c, ctx, cid):
    m = re.match(r"(P[012])\b\s*[—-]?\s*(.*)", c["title"])
    prio = m.group(1) if m else None
    title = m.group(2) if m else c["title"]
    status = next((v for k, v in c["rows"] if k == "Status"), "")
    st = (re.match(r"[A-Z]+", status) or [""])[0]
    badges = ""
    if prio:
        badges += f'<span class="badge {prio.lower()}">{prio}</span>'
    if st:
        badges += f'<span class="badge st-{st.lower()}">{html.escape(st)}</span>'
    rows = "".join(
        f'<div class="row"><dt>{html.escape(k)}</dt><dd>{inline(v, ctx)}</dd></div>'
        for k, v in c["rows"] if k not in ("Status", "Evidence") and v)
    if st and status.strip() != st:
        rows = f'<div class="row"><dt>Status</dt><dd>{inline(status, ctx)}</dd></div>' + rows
    ev = ""
    if c["evidence"] or any(k == "Evidence" and v for k, v in c["rows"]):
        inline_ev = [v for k, v in c["rows"] if k == "Evidence" and v]
        lis = "".join(f"<li>{inline(e, ctx)}</li>" for e in inline_ev + c["evidence"])
        ev = f'<div class="row"><dt>Evidence</dt><dd><ul class="ev">{lis}</ul></dd></div>'
    extra = "".join(f"<p>{inline(t, ctx)}</p>" for t in c["text"])
    cid = html.escape(cid)
    return (f'<article class="card" data-p="{prio or ""}" data-id="{cid}">'
            f'<header><label class="check"><input type="checkbox" data-id="{cid}"></label>'
            f'<h3>{badges}<span>{inline(title, ctx)}</span></h3></header>'
            f'<dl>{rows}{ev}</dl>{extra}</article>')


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#fafaf9;--fg:#1c1917;--mute:#78716c;--card:#fff;--line:#e7e5e4;--code:#f5f5f4;
--p0:#b91c1c;--p1:#c2410c;--p2:#a16207;--ok:#15803d;--hyp:#7c3aed;--unk:#57534e;--link:#1d4ed8}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0c0a09;--fg:#e7e5e4;--mute:#a8a29e;--card:#1c1917;
--line:#292524;--code:#292524;--p0:#f87171;--p1:#fb923c;--p2:#facc15;--ok:#4ade80;--hyp:#c4b5fd;--unk:#a8a29e;--link:#93c5fd}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:880px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:22px;margin:0 0 12px}}
dl.meta{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:6px 20px;margin:0 0 16px;
padding:12px 14px;background:var(--card);border:1px solid var(--line);border-radius:10px}}
dl.meta dt{{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}}
dl.meta dd{{margin:0;overflow-wrap:anywhere}}
.filters{{position:sticky;top:0;z-index:2;background:var(--bg);padding:8px 0;display:flex;gap:6px;align-items:center;flex-wrap:wrap;color:var(--mute)}}
.filters button{{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:999px;padding:3px 12px;cursor:pointer;opacity:.45}}
.filters button.on{{opacity:1;font-weight:600}}
#progress{{margin-left:auto;color:var(--mute);font-size:13px}}
section{{margin-top:18px}}
summary{{cursor:pointer;list-style:none}} summary::-webkit-details-marker{{display:none}}
summary h2{{display:inline;font-size:17px}} summary h2::before{{content:"▾ ";color:var(--mute)}}
details:not([open]) summary h2::before{{content:"▸ "}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}}
.card.done{{opacity:.5}}
.card header{{display:flex;gap:10px;align-items:flex-start}}
.card h3{{margin:0;font-size:15.5px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
.card dl{{margin:8px 0 0 28px}} .row{{margin:6px 0}}
.row dt{{font-size:12px;font-weight:600;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}}
.row dd{{margin:0}}
ul.ev{{margin:2px 0;padding-left:18px}}
.badge{{font-size:11.5px;font-weight:700;padding:1px 8px;border-radius:999px;border:1px solid currentColor}}
.badge.p0,.filters .p0{{color:var(--p0)}} .badge.p1,.filters .p1{{color:var(--p1)}} .badge.p2,.filters .p2{{color:var(--p2)}}
.st-confirmed{{color:var(--ok)}} .st-hypothesis{{color:var(--hyp)}} .st-unknown{{color:var(--unk)}}
.tag.unk{{font-size:12px;font-weight:700;color:var(--unk);border:1px dashed var(--unk);border-radius:4px;padding:0 4px}}
code{{background:var(--code);padding:1px 5px;border-radius:4px;font-size:13px;overflow-wrap:anywhere}}
a.ref{{color:var(--link);text-decoration:none;font-family:ui-monospace,Menlo,monospace;font-size:13px}} a.ref:hover{{text-decoration:underline}}
p.flow{{font-family:ui-monospace,Menlo,monospace;font-size:13px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;overflow-x:auto}}
label.check{{display:flex;gap:10px;align-items:flex-start;margin:6px 0;cursor:pointer}}
label.check input{{margin-top:4px;width:16px;height:16px;flex:none}}
label.check:has(input:checked) span{{text-decoration:line-through;opacity:.6}}
footer{{margin-top:32px;color:var(--mute);font-size:12.5px}}
</style></head><body><main>
<h1>{title}</h1>
<dl class="meta">{meta}</dl>
<div class="filters" id="bar">{filters}{progress}</div>
{body}
<footer>Generated {generated}. This report guides human attention; it is not an approval decision. Checkbox state is saved in this browser only.</footer>
</main>
<script>
(function(){{
  var KEY="pr-review:"+{key}, state={{}};
  try{{state=JSON.parse(localStorage.getItem(KEY)||"{{}}")}}catch(e){{}}
  var boxes=[].slice.call(document.querySelectorAll("input[type=checkbox][data-id]"));
  var hideDone=false, off={{}};
  function save(){{try{{localStorage.setItem(KEY,JSON.stringify(state))}}catch(e){{}}}}
  function apply(){{
    var done=0;
    boxes.forEach(function(b){{
      b.checked=!!state[b.dataset.id]; if(b.checked)done++;
      var card=b.closest(".card"); if(card)card.classList.toggle("done",b.checked);
    }});
    document.querySelectorAll(".card").forEach(function(c){{
      var p=c.dataset.p, chk=c.querySelector("input");
      c.style.display=(p&&off[p])||(hideDone&&chk&&chk.checked)?"none":"";
    }});
    var pr=document.getElementById("progress");
    if(pr&&boxes.length)pr.textContent=done+" / "+boxes.length+" checked";
  }}
  boxes.forEach(function(b){{b.addEventListener("change",function(){{state[b.dataset.id]=b.checked;save();apply();}})}});
  document.querySelectorAll(".filters button[data-p]").forEach(function(btn){{
    btn.addEventListener("click",function(){{var p=btn.dataset.p;off[p]=!off[p];btn.classList.toggle("on",!off[p]);apply();}});
  }});
  var hd=document.getElementById("hide-done");
  if(hd)hd.addEventListener("click",function(){{hideDone=!hideDone;hd.classList.toggle("on",hideDone);apply();}});
  apply();
}})();
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=["walkthrough", "risks"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--base", required=True, help="merge-base SHA")
    ap.add_argument("--base-ref", default="", help='e.g. "main @ <baseRefOid>"')
    ap.add_argument("--head", required=True)
    ap.add_argument("--skill-version", default="1")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()

    if not re.fullmatch(r"[\w.-]+/[\w.-]+", a.repo):
        sys.exit("render_report: --repo must be OWNER/REPO")
    for name in ("base", "head"):
        if not re.fullmatch(r"[0-9a-f]{7,40}", getattr(a, name)):
            sys.exit(f"render_report: --{name} must be a commit SHA")

    md = sys.stdin.read()
    if not md.strip():
        sys.exit("render_report: empty report on stdin")
    md = re.sub(r"^\s*<!--\s*pr-review-cache.*?-->\s*", "", md, flags=re.S)

    owner, repo = a.repo.split("/")
    root = os.environ.get("PR_REVIEW_DIR") or os.path.expanduser("~/.cache/pr-review")
    out_dir = os.path.join(root, owner, repo)
    os.makedirs(out_dir, exist_ok=True)
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    skill = "pr-change-walkthrough" if a.kind == "walkthrough" else "pr-risk-review"
    header = (f"<!-- pr-review-cache\nrepo: {a.repo}\npr: {a.pr}\nbase_ref: {a.base_ref}\n"
              f"base: {a.base}\nhead: {a.head}\ngenerated: {generated}\n"
              f"skill: {skill}\nskill_version: {a.skill_version}\n-->\n")

    stem = os.path.join(out_dir, f"{a.pr}-{a.kind}")
    with open(stem + ".md", "w", encoding="utf-8") as f:
        f.write(header + md.lstrip())
    ctx = Ctx(a.repo, a.head, a.base)
    key = f"{a.repo}#{a.pr}@{a.head[:12]}:{a.kind}"
    with open(stem + ".html", "w", encoding="utf-8") as f:
        f.write(render(parse(md), a.kind, ctx, key, generated))

    print(stem + ".html")
    print(stem + ".md")
    if a.open:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        try:
            subprocess.run([opener, stem + ".html"], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


if __name__ == "__main__":
    main()
