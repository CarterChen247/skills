#!/usr/bin/env python3
"""Render a review-readiness report JSON into a self-contained HTML page.

Usage: render_report.py <report.json> <out.html> [--open]

All text from the JSON is HTML-escaped (it may quote untrusted PR content).
Inline `code` and **bold** are the only formatting applied.
Exits 2 with a list of problems if the JSON does not match the schema.
Standard library only.
"""
import html
import json
import re
import subprocess
import sys

READINESS = {"READY_FOR_REVIEW", "NEEDS_AUTHOR_INPUT"}
MERGE = {"APPROVE_CANDIDATE", "COMMENT", "REQUEST_CHANGES", "CONTINUE_REVIEW"}
OWNER = {"AUTHOR", "REVIEWER", "BOTH"}
MODES = {"triage", "full", "recheck"}
CATEGORIES = {"CONTEXT_GAP", "CODE_DEFECT", "VERIFICATION_GAP", "DESIGN_RISK", "REVIEW_INCOMPLETE"}
STATUSES = {"CONFIRMED", "HYPOTHESIS", "RESOLVED"}
CHECK = {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
GATE = {"PASS", "FAIL", "UNKNOWN"}
DELTA = {"RESOLVED", "STILL_OPEN", "CANNOT_VERIFY", "NEW"}
ACTION_LABEL = {
    "COMMENT": "Comment",
    "REQUEST_CHANGES": "Request changes",
    "APPROVE_CANDIDATE": "Approve, after you check the items in §8 yourself",
    "CONTINUE_REVIEW": "Don't submit a review yet: continue investigating",
}
SCORE_KEYS = [
    ("author_readiness", "Author Readiness"),
    ("change_quality", "Change Quality"),
    ("verification_confidence", "Verification Confidence"),
    ("operational_risk", "Operational Risk"),
]


# ---------- validation ----------

def validate(d):
    errs = []

    def need(obj, key, where, typ=None):
        if not isinstance(obj, dict) or key not in obj:
            errs.append(f"missing {where}.{key}")
            return None
        v = obj[key]
        if typ and v is not None and not isinstance(v, typ):
            errs.append(f"{where}.{key} should be {typ.__name__ if isinstance(typ, type) else typ}")
        return v

    def enum(v, allowed, where):
        if v is not None and v not in allowed:
            errs.append(f"{where}={v!r} not in {sorted(allowed)}")

    if d.get("schema") != "review-readiness/v2":
        errs.append("schema must be 'review-readiness/v2'")
    for k, t in [("repo", str), ("pr", int), ("title", str), ("mode", str), ("assessed_at", str),
                 ("head_sha", str), ("summary", list), ("issues", list), ("checklist", list),
                 ("comment_draft", str), ("why_action", list), ("would_change", list),
                 ("review_targets", list), ("verification_gaps", list), ("risk_paths", list)]:
        need(d, k, "root", t)
    enum(d.get("mode"), MODES, "mode")
    dec = need(d, "decision", "root", dict) or {}
    enum(dec.get("readiness"), READINESS, "decision.readiness")
    enum(dec.get("merge"), MERGE, "decision.merge")
    enum(dec.get("owner"), OWNER, "decision.owner")
    need(dec, "why", "decision", list)
    if d.get("mode") == "triage" and dec.get("merge") == "APPROVE_CANDIDATE":
        errs.append("triage can never be APPROVE_CANDIDATE")
    scores = need(d, "scores", "root", dict) or {}
    for k, _ in SCORE_KEYS:
        v = scores.get(k)
        if k == "change_quality" and v == "NOT_ASSESSED":
            continue
        if not isinstance(v, int) or not 1 <= v <= 10:
            errs.append(f"scores.{k} must be an integer 1-10" + (" or NOT_ASSESSED" if k == "change_quality" else ""))
    if scores.get("change_quality") == "NOT_ASSESSED" and dec.get("merge") == "APPROVE_CANDIDATE":
        errs.append("APPROVE_CANDIDATE requires an assessed Change Quality")
    ev = need(d, "score_evidence", "root", dict) or {}
    for k, _ in SCORE_KEYS:
        if not ev.get(k):
            errs.append(f"score_evidence.{k} is empty")
    gates = need(d, "gates", "root", dict) or {}
    for g in ["G1", "G2", "G3", "G4", "G5"]:
        gv = gates.get(g)
        if not isinstance(gv, dict):
            errs.append(f"gates.{g} must be {{result, evidence}}")
            continue
        enum(gv.get("result"), GATE, f"gates.{g}.result")
    for i, it in enumerate(d.get("issues") or []):
        w = f"issues[{i}]"
        for k in ["id", "category", "severity", "status", "owner", "summary", "evidence", "next_action"]:
            if not it.get(k):
                errs.append(f"missing {w}.{k}")
        enum(it.get("category"), CATEGORIES, f"{w}.category")
        enum(it.get("status"), STATUSES, f"{w}.status")
        enum(it.get("owner"), OWNER, f"{w}.owner")
        if it.get("category") == "CODE_DEFECT" and it.get("status") == "CONFIRMED":
            if not it.get("location") or not it.get("scenario"):
                errs.append(f"{w}: a CONFIRMED CODE_DEFECT needs location (file:line) and scenario")
        if (it.get("severity") or "").split(" ")[0] not in {"BLOCKER", "MAJOR", "MINOR"}:
            errs.append(f"{w}.severity must start with BLOCKER, MAJOR or MINOR")
    cl = d.get("checklist") or []
    if len(cl) != 12 or {c.get("group") for c in cl} != {"Author", "Quality", "Verify"}:
        errs.append("checklist must have the 12 standard items in groups Author / Quality / Verify")
    rp = d.get("risk_paths") or []
    cov = d.get("coverage") or {}
    n_in = sum(1 for p in rp if p.get("inspected"))
    if cov and (cov.get("inspected") != n_in or cov.get("total") != len(rp)):
        errs.append(f"coverage {cov.get('inspected')}/{cov.get('total')} does not match risk_paths ({n_in}/{len(rp)})")
    g4 = (gates.get("G4") or {}).get("result") if isinstance(gates.get("G4"), dict) else None
    if rp and g4 == "PASS" and n_in < len(rp):
        errs.append("G4 is PASS but not every risk path is inspected")
    if d.get("mode") == "triage" and g4 == "PASS":
        errs.append("G4 is always FAIL in triage")
    for k in d.get("low_evidence") or []:
        if k not in dict(SCORE_KEYS):
            errs.append(f"low_evidence key {k!r} is not a score dimension")
    for i, c in enumerate(cl):
        enum(c.get("status"), CHECK, f"checklist[{i}].status")
        if c.get("status") in ("PASS", "FAIL") and not c.get("evidence"):
            errs.append(f"checklist[{i}] {c.get('status')} needs evidence")
    delta = d.get("delta")
    if d.get("mode") == "recheck" and delta is None:
        errs.append("recheck needs delta (use {\"no_previous\": \"<path>\"} if none existed)")
    if isinstance(delta, dict):
        for i, r in enumerate(delta.get("rows") or []):
            enum(r.get("now"), DELTA, f"delta.rows[{i}].now")
    return errs


# ---------- rendering helpers ----------

def inline(s):
    """Escape, then allow `code` and **bold** only."""
    s = html.escape("" if s is None else str(s))
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def badge(value, kind):
    v = "" if value is None else str(value)
    return f'<span class="b {kind}-{html.escape(v.lower().replace("_", "-"))}">{html.escape(v.replace("_", " "))}</span>'


def ul(items, cls=""):
    items = [x for x in (items or []) if x]
    if not items:
        return '<p class="muted">None</p>'
    return f'<ul class="{cls}">' + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>"


def table(headers, rows, cls=""):
    if not rows:
        return '<p class="muted">None</p>'
    h = "".join(f"<th>{html.escape(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table></div>'


def section(num, title, inner, sid=None):
    sid = sid or f"s{num}"
    label = f'<span class="n">{num}</span>' if num else ""
    return f'<section id="{sid}"><h2>{label}{html.escape(title)}</h2>{inner}</section>'


def score_card(key, title, value, evidence, low):
    risk = key == "operational_risk"
    if value == "NOT_ASSESSED":
        num, bar, tone = '<span class="na">NOT ASSESSED</span>', "", "na"
    else:
        v = int(value)
        if risk:
            tone = "bad" if v >= 7 else "warn" if v >= 4 else "good"
        else:
            tone = "good" if v >= 7 else "warn" if v >= 4 else "bad"
        num = f'<span class="big">{v}</span><span class="of">/10</span>'
        bar = f'<div class="bar"><i class="t-{tone}" style="width:{v * 10}%"></i></div>'
    sub = '<div class="hint">higher = riskier</div>' if risk else ""
    lowtag = '<span class="b low">low evidence</span>' if low else ""
    return (f'<div class="card t-{tone}-edge"><div class="ct">{html.escape(title)} {lowtag}</div>'
            f'<div class="cv">{num}</div>{bar}{sub}<p class="ce">{inline(evidence)}</p></div>')


CSS = """
:root{--bg:#f7f7f5;--panel:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--code:#f0efeb;
--good:#1f7a4d;--good-bg:#e3f4ea;--warn:#9a6200;--warn-bg:#fdf1d8;--bad:#b42318;--bad-bg:#fde4e1;
--info:#1d5fae;--info-bg:#e2edfb;--na:#6b6b70;--na-bg:#ececea;--accent:#5b4bd6}
@media (prefers-color-scheme: dark){:root{--bg:#141416;--panel:#1d1d20;--ink:#ececef;--muted:#9a9aa2;--line:#2e2e33;
--code:#2a2a2f;--good:#5fd39a;--good-bg:#173527;--warn:#f0b54a;--warn-bg:#3a2c10;--bad:#ff7b6e;--bad-bg:#3d1a17;
--info:#7fb2ff;--info-bg:#172a45;--na:#a0a0a8;--na-bg:#2a2a2f;--accent:#9d92ff}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",
"Noto Sans TC",Helvetica,Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:28px 16px 64px}
header h1{font-size:22px;line-height:1.3;margin:0 0 6px}header .meta{color:var(--muted);font-size:13px}
header a{color:var(--accent)}
code{font:12.5px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--code);padding:1px 5px;border-radius:4px;
word-break:break-word}
section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:16px 0}
h2{font-size:16px;margin:0 0 12px;display:flex;align-items:center;gap:8px}
h2 .n{display:inline-grid;place-items:center;min-width:22px;height:22px;border-radius:6px;background:var(--code);
font-size:12px;color:var(--muted)}
.muted{color:var(--muted)}ul{margin:0;padding-left:20px}li{margin:3px 0}
.banner{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0 0}
.tile{border-radius:12px;padding:14px 16px;border:1px solid var(--line);background:var(--panel)}
.tile .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.tile .v{font-size:19px;font-weight:700;margin-top:4px}
.m-approve-candidate{background:var(--good-bg);border-color:var(--good);color:var(--good)}
.m-comment{background:var(--warn-bg);border-color:var(--warn);color:var(--warn)}
.m-continue-review{background:var(--info-bg);border-color:var(--info);color:var(--info)}
.m-request-changes{background:var(--bad-bg);border-color:var(--bad);color:var(--bad)}
.r-ready-for-review{background:var(--good-bg);border-color:var(--good);color:var(--good)}
.r-needs-author-input{background:var(--warn-bg);border-color:var(--warn);color:var(--warn)}
.tile .k{color:inherit;opacity:.8}
.why{margin-top:12px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.card{border:1px solid var(--line);border-top-width:4px;border-radius:10px;padding:12px 14px;background:var(--panel)}
.t-good-edge{border-top-color:var(--good)}.t-warn-edge{border-top-color:var(--warn)}
.t-bad-edge{border-top-color:var(--bad)}.t-na-edge{border-top-color:var(--na)}
.ct{font-size:13px;font-weight:600;color:var(--muted)}.cv{margin:6px 0}
.big{font-size:30px;font-weight:750}.of{color:var(--muted);margin-left:2px}.na{font-weight:700;color:var(--na)}
.bar{height:6px;border-radius:3px;background:var(--code);overflow:hidden}.bar i{display:block;height:100%}
.t-good{background:var(--good)}.t-warn{background:var(--warn)}.t-bad{background:var(--bad)}
.hint{font-size:11px;color:var(--muted);margin-top:4px}.ce{font-size:13px;margin:8px 0 0;color:var(--ink)}
.note{font-size:12px;color:var(--muted);margin-top:10px}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13.5px}
th{text-align:left;font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.03em;
border-bottom:1px solid var(--line);padding:6px 8px;white-space:nowrap}
td{border-bottom:1px solid var(--line);padding:8px;vertical-align:top}td:first-child{white-space:nowrap}tr:last-child td{border-bottom:0}
.b{display:inline-block;font-size:11.5px;font-weight:650;padding:1px 7px;border-radius:999px;white-space:nowrap;
border:1px solid transparent;background:var(--na-bg);color:var(--na)}
.c-context-gap{background:#efe9fd;color:#5b3fc4}.c-code-defect{background:var(--bad-bg);color:var(--bad)}
.c-verification-gap{background:var(--warn-bg);color:var(--warn)}.c-design-risk{background:var(--info-bg);color:var(--info)}
.c-review-incomplete{background:var(--na-bg);color:var(--na)}
@media (prefers-color-scheme: dark){.c-context-gap{background:#2b2348;color:#b9a8ff}}
.s-blocker{background:var(--bad);color:#fff}.s-major{background:var(--warn-bg);color:var(--warn);border-color:var(--warn)}
.s-minor{background:var(--na-bg);color:var(--na)}
.st-confirmed{background:var(--ink);color:var(--panel)}.st-hypothesis{background:transparent;color:var(--muted);
border:1px dashed var(--muted)}.st-resolved{background:var(--good-bg);color:var(--good)}
.k-pass{background:var(--good-bg);color:var(--good)}.k-fail{background:var(--bad-bg);color:var(--bad)}
.k-unknown{background:var(--na-bg);color:var(--na)}.k-not-applicable{background:transparent;color:var(--muted);
border-color:var(--line)}
.d-resolved{background:var(--good-bg);color:var(--good)}.d-still-open{background:var(--warn-bg);color:var(--warn)}
.d-cannot-verify,.d-new{background:var(--na-bg);color:var(--na)}
.low{background:var(--warn-bg);color:var(--warn);font-weight:600}
.o{font-size:12px;color:var(--muted)}
.finding{border-left:3px solid var(--bad);padding:6px 0 6px 12px;margin:10px 0}
.hyp{border-left:3px dashed var(--muted);padding:6px 0 6px 12px;margin:10px 0}
.finding h3,.hyp h3{font-size:14px;margin:0 0 4px}.kv{font-size:13.5px;margin:2px 0}.kv b{color:var(--muted);font-weight:600}
ol.targets{padding-left:22px}ol.targets li{margin:6px 0}
.action{font-size:18px;font-weight:700}
.draft{position:relative;background:var(--code);border-radius:10px;padding:14px 16px;white-space:pre-wrap;
font:13.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}
.copy{position:absolute;top:8px;right:8px;font:600 12px/1 -apple-system,sans-serif;padding:6px 10px;border-radius:6px;
border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer}
details{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin:16px 0}
summary{cursor:pointer;padding:14px 20px;font-weight:650}details>div{padding:0 20px 18px}
details h3{font-size:14px;margin:18px 0 8px}
.delta{border-color:var(--accent)}
table.ck{table-layout:fixed}table.ck th:nth-child(1){width:38%}table.ck th:nth-child(2){width:130px}
footer{color:var(--muted);font-size:12.5px;margin-top:20px}
@media (max-width:760px){.banner{grid-template-columns:1fr}.cards{grid-template-columns:1fr 1fr}}
@media (max-width:460px){.cards{grid-template-columns:1fr}.wrap{padding:18px 16px 48px}section{padding:14px}}
"""

JS = """
document.querySelectorAll('.copy').forEach(function(b){b.addEventListener('click',function(){
var t=document.getElementById(b.dataset.target).textContent;
function done(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy'},1500)}
if(navigator.clipboard){navigator.clipboard.writeText(t).then(done,function(){fallback(t);done()})}else{fallback(t);done()}});});
function fallback(t){var a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();
try{document.execCommand('copy')}catch(e){}document.body.removeChild(a)}
"""


def render(d):
    dec = d["decision"]
    scores, sev = d["scores"], d.get("score_evidence", {})
    low = set(d.get("low_evidence") or [])
    issues = d.get("issues") or []
    open_issues = [i for i in issues if i.get("status") != "RESOLVED"]
    size = d.get("size") or {}
    url = d.get("url")
    title_link = f'<a href="{html.escape(url)}">{html.escape(d["repo"])}#{d["pr"]}</a>' if url else \
        f'{html.escape(d["repo"])}#{d["pr"]}'
    meta = " · ".join(x for x in [
        f"Mode: <b>{html.escape(d['mode'])}</b>",
        f"Head: <code>{html.escape(d['head_sha'][:7])}</code>",
        f"Assessed: {html.escape(d['assessed_at'])}",
        (f"+{size.get('additions', '?')}/−{size.get('deletions', '?')} in {size.get('files', '?')} files"
         if size else ""),
    ] if x)
    out = []
    out.append(f'<header><h1>Review Readiness: {title_link}</h1><div class="meta">{inline(d["title"])}</div>'
               f'<div class="meta">{meta}</div>')
    m, r = dec["merge"], dec["readiness"]
    out.append('<div class="banner">'
               f'<div class="tile r-{r.lower().replace("_", "-")}"><div class="k">Review readiness</div>'
               f'<div class="v">{html.escape(r.replace("_", " "))}</div></div>'
               f'<div class="tile m-{m.lower().replace("_", "-")}"><div class="k">Merge recommendation</div>'
               f'<div class="v">{html.escape(m.replace("_", " "))}</div></div>'
               f'<div class="tile"><div class="k">Next owner</div><div class="v">{html.escape(dec["owner"])}</div></div>'
               '</div></header>')

    # 1 summary
    out.append(section(1, "PR summary", ul(d.get("summary"))))
    # 2 decision why
    out.append(section(2, "Why this decision", ul(dec.get("why"))))
    # delta (recheck)
    delta = d.get("delta")
    if isinstance(delta, dict):
        if delta.get("no_previous"):
            inner = f'<p>No previous assessment found at <code>{html.escape(delta["no_previous"])}</code>. ' \
                    'This is a fresh assessment, not a comparison.</p>'
        else:
            rows = [[f"<code>{inline(x.get('id'))}</code>", inline(x.get("was")), badge(x.get("now"), "d"),
                     inline(x.get("evidence"))] for x in delta.get("rows") or []]
            inner = (f'<p class="o">{inline(delta.get("prev_assessed_at"))} · '
                     f'<code>{inline((delta.get("prev_sha") or "")[:7])}</code> → '
                     f'<code>{inline(d["head_sha"][:7])}</code></p>'
                     + table(["Prev ID", "Was", "Now", "Evidence"], rows)
                     + "<h3>New evidence</h3>" + ul(delta.get("new_evidence"))
                     + "<h3>New risks</h3>" + ul(delta.get("new_risks"))
                     + f'<p><strong>Recommendation change:</strong> {inline(delta.get("change"))}</p>')
        out.append(section("Δ", "Since last assessment", inner, "delta").replace("<section ", '<section class="delta" ', 1))
    # 3 scorecard
    cards = "".join(score_card(k, t, scores.get(k), sev.get(k), k in low) for k, t in SCORE_KEYS)
    out.append(section(3, "Scorecard", f'<div class="cards">{cards}</div>'
                       '<p class="note">Four independent dimensions. They are never averaged, and hard gates '
                       'override them.</p>'))
    # 4 issues
    rows = [[f"<code>{inline(i['id'])}</code>", badge(i["category"], "c"), badge(i["severity"].split(" ")[0], "s")
             + (f' <span class="o">{inline(" ".join(i["severity"].split(" ")[1:]))}</span>'
                if " " in i["severity"] else ""),
             badge(i["status"], "st"), badge(i["owner"], "o"), inline(i["summary"])] for i in open_issues]
    out.append(section(4, "Issues", (f'<p>{inline(d.get("primary_classification"))}</p>'
                                     if d.get("primary_classification") else "")
                       + table(["ID", "Category", "Severity", "Status", "Owner", "Summary"], rows)))
    # 5 confirmed findings
    conf = [i for i in open_issues if i.get("status") == "CONFIRMED"
            and (i.get("category") == "CODE_DEFECT" or i.get("gate_fail"))]
    if conf:
        inner = "".join(
            f'<div class="finding"><h3><code>{inline(i["id"])}</code> {inline(i["summary"])}</h3>'
            + (f'<p class="kv"><b>Where</b> <code>{inline(i.get("location"))}</code></p>' if i.get("location") else "")
            + (f'<p class="kv"><b>Failure scenario</b> {inline(i.get("scenario"))}</p>' if i.get("scenario") else "")
            + f'<p class="kv"><b>Evidence</b> {inline(i.get("evidence"))}</p>'
            + f'<p class="kv"><b>Fix</b> {inline(i.get("fix") or i.get("next_action"))}</p></div>'
            for i in conf)
    else:
        cov = d.get("coverage") or {}
        inner = ('<p>No defects confirmed. This is <strong>not</strong> proof of correctness'
                 + (f' (coverage {cov.get("inspected")}/{cov.get("total")} risk paths)' if cov else "") + '.</p>')
    out.append(section(5, "Confirmed findings", inner))
    # 6 hypotheses
    hyps = [i for i in open_issues if i.get("status") == "HYPOTHESIS"]
    inner = "".join(
        f'<div class="hyp"><h3><code>{inline(i["id"])}</code> {inline(i["summary"])}</h3>'
        + (f'<p class="kv"><b>Where</b> <code>{inline(i.get("location"))}</code></p>' if i.get("location") else "")
        + f'<p class="kv"><b>Why plausible</b> {inline(i.get("evidence"))}</p>'
        + f'<p class="kv"><b>Confirm / refute</b> {inline(i.get("confirm_or_refute") or i.get("next_action"))}</p></div>'
        for i in hyps) or '<p class="muted">None</p>'
    out.append(section(6, "Unverified risks (hypotheses)", inner))
    # 7 verification gaps
    rows = [[inline(g.get("behavior")), inline(g.get("available")), inline(g.get("missing"))]
            for g in d.get("verification_gaps") or []]
    out.append(section(7, "Verification gaps", table(["Behavior / risk", "Evidence available", "Missing"], rows)))
    # 8 review targets
    tg = d.get("review_targets") or []
    inner = ('<ol class="targets">' + "".join(
        f'<li><code>{inline(t.get("location"))}</code>: {inline(t.get("why"))}</li>' for t in tg) + "</ol>") \
        if tg else '<p class="muted">None</p>'
    out.append(section(8, "Where you should look", inner))
    # 9 checklist
    groups = {}
    for c in d.get("checklist") or []:
        groups.setdefault(c.get("group", ""), []).append(c)
    inner = ""
    for g, items in groups.items():
        inner += f"<h3>{html.escape(g)}</h3>" + table(
            ["Item", "Status", "Evidence"],
            [[inline(c.get("item")), badge(c.get("status"), "k"), inline(c.get("evidence"))] for c in items], "ck")
    inner += '<p class="note">UNKNOWN means not established. It is not a failure.</p>'
    out.append(section(9, "Checklist", inner))
    # 10-13
    out.append(section(10, "Suggested GitHub review action", f'<p class="action">{html.escape(ACTION_LABEL[m])}</p>'))
    out.append(section(11, "Why this action", ul(d.get("why_action"))))
    out.append(section(12, "What would change the decision", ul(d.get("would_change"))))
    out.append(section(13, "Next responsible owner",
                       f'<p><strong>{html.escape(dec["owner"])}</strong>: {inline(d.get("next_owner_detail"))}</p>'))
    # 14 draft
    out.append(section(14, "Draft GitHub review comment (not posted)",
                       f'<div class="draft"><button class="copy" data-target="draft">Copy</button>'
                       f'<span id="draft">{html.escape(d.get("comment_draft", ""))}</span></div>'))

    # details
    det = []
    inv = d.get("evidence_inventory") or []
    det.append("<h3>Evidence inventory</h3>" + table(
        ["Source", "Item", "Detail"],
        [[badge(e.get("tag"), "tag"), inline(e.get("item")), inline(e.get("detail"))] for e in inv]))
    fm = d.get("file_map") or []
    det.append("<h3>File map</h3>" + table(["Class", "Files", "Notes"],
                                           [[inline(f.get("class")), inline(f.get("files")), inline(f.get("notes"))]
                                            for f in fm]))
    cov = d.get("coverage") or {}
    det.append(f"<h3>Coverage log: {cov.get('inspected', '?')} of {cov.get('total', '?')} risk paths</h3>" + table(
        ["", "Path", "Note"],
        [["✓" if p.get("inspected") else "—", f"<code>{inline(p.get('path'))}</code>", inline(p.get("note"))]
         for p in d.get("risk_paths") or []]))
    det.append("<h3>Hard gates</h3>" + table(
        ["Gate", "Result", "Evidence"],
        [[html.escape(g), badge((d["gates"][g] or {}).get("result"), "k"), inline((d["gates"][g] or {}).get("evidence"))]
         for g in ["G1", "G2", "G3", "G4", "G5"]]))
    for k, t in SCORE_KEYS:
        rows = (d.get("score_breakdown") or {}).get(k)
        if not rows:
            continue
        if k == "operational_risk":
            det.append(f"<h3>{t}: factors</h3>" + table(
                ["Factor", "Level", "Evidence / mitigation"],
                [[inline(x.get("factor")), inline(x.get("level")), inline(x.get("evidence"))] for x in rows]))
        else:
            det.append(f"<h3>{t}: breakdown</h3>" + table(
                ["Criterion", "Points", "Evidence"],
                [[inline(x.get("criterion")), f'{x.get("points")}/{x.get("max")}', inline(x.get("evidence"))]
                 for x in rows]))
    full = [[f"<code>{inline(i['id'])}</code>", badge(i["category"], "c"), inline(i["severity"]), badge(i["status"], "st"),
             inline(i.get("evidence")), inline(i.get("confidence")), inline(i.get("owner")), inline(i.get("next_action"))]
            for i in issues]
    det.append("<h3>All issues</h3>" + table(
        ["ID", "Category", "Severity", "Status", "Evidence", "Confidence", "Owner", "Next action"], full))
    det.append("<h3>Untrusted-content notes</h3>" + ul(d.get("untrusted_notes") or ["None observed."]))
    out.append('<details><summary>Details: evidence, coverage, gates, score breakdown</summary><div>'
               + "".join(det) + "</div></details>")
    nxt = d.get("next_command")
    out.append('<footer>Generated by /review-readiness. Read-only: nothing was posted to GitHub.'
               + (f" Next: <code>{inline(nxt)}</code>" if nxt else "") + "</footer>")

    page_title = f"Review Readiness {d['repo']}#{d['pr']}"
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{html.escape(page_title)}</title><style>{CSS}</style></head>"
            f"<body><div class=\"wrap\">{''.join(out)}</div><script>{JS}</script></body></html>")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 1
    with open(args[0], encoding="utf-8") as f:
        data = json.load(f)
    errs = validate(data)
    if errs:
        print("Report JSON is invalid:\n- " + "\n- ".join(errs), file=sys.stderr)
        return 2
    with open(args[1], "w", encoding="utf-8") as f:
        f.write(render(data))
    print(f"Wrote {args[1]}")
    if "--open" in argv:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        try:
            subprocess.run([opener, args[1]], check=False)
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
