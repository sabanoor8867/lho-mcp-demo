"""A small chat page for the agent.

    python -m lho_demo.web        then open http://127.0.0.1:8000

One page, no extra dependencies (Starlette and Uvicorn come with the MCP
library). Each answer shows which tools were called and the SPARQL that ran,
so the user can check where every number comes from.
"""
from __future__ import annotations

import asyncio
import contextlib
import os

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from . import diagram
from .agent import Agent

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LHO knowledge-graph assistant</title>
<style>
  :root { --bg:#f4f6f1; --card:#ffffff; --ink:#1d2a24; --muted:#5d6b63; --accent:#2f6b4f; --on-accent:#ffffff;
          --line:#dbe2d8; --user:#e3efe8; --sky:#e6f0ea; --hill-far:#cfe0d2; --hill-near:#b5cfb9; --shape:#8fb39a; --sun:#f1d9a0; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) { --bg:#131815; --card:#1c2420; --ink:#e7ece8; --muted:#9aa89f; --accent:#7fc4a0; --on-accent:#10201a;
          --line:#2c3832; --user:#24332b; --sky:#161d19; --hill-far:#1c2822; --hill-near:#223128; --shape:#31463a; --sun:#3a3a2a; }
  }
  :root[data-theme="dark"] { --bg:#131815; --card:#1c2420; --ink:#e7ece8; --muted:#9aa89f; --accent:#7fc4a0; --on-accent:#10201a;
          --line:#2c3832; --user:#24332b; --sky:#161d19; --hill-far:#1c2822; --hill-near:#223128; --shape:#31463a; --sun:#3a3a2a; }
  __DIAGRAM_CSS__
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 system-ui, "Segoe UI", sans-serif; }
  /* The farm scene is drawn in the page itself (no image file), so it follows the theme. */
  .scene { position: fixed; left:0; right:0; bottom:60px; width:100%; height: 46vh; min-height: 240px; z-index:0; pointer-events:none; }
  main { position: relative; z-index:1; max-width: 820px; margin: 0 auto; padding: 20px 16px 130px; }
  header { display:flex; align-items:center; gap:12px; margin-bottom: 6px; }
  header .logo { width:46px; height:46px; flex:none; }
  header .titles { flex:1; min-width:0; }
  h1 { font-size: 1.3rem; margin: 0; line-height:1.2; }
  .tagline { color: var(--muted); font-size:.85rem; }
  #theme, #reset, #howbtn { flex:none; background:var(--card); color:var(--ink); border:1px solid var(--line); border-radius:999px;
    padding: 7px 12px; font: inherit; font-size:.85rem; cursor:pointer; }
  #theme:hover, #reset:hover, #howbtn:hover { border-color: var(--accent); }
  header { flex-wrap: wrap; }
  dialog#how { width: min(1040px, 96vw); max-height: 92vh; border:1px solid var(--line); border-radius:16px;
    background: var(--card); color: var(--ink); padding: 0; }
  dialog#how::backdrop { background: rgba(10, 20, 30, .55); }
  .how-head { position: sticky; top:0; display:flex; align-items:center; justify-content:space-between;
    padding: 14px 20px; background: var(--card); border-bottom:1px solid var(--line); }
  .how-head h2 { margin:0; font-size:1.15rem; }
  .how-head button { background:none; border:1px solid var(--line); color:var(--ink); border-radius:999px;
    padding:6px 12px; font:inherit; font-size:.85rem; cursor:pointer; }
  .how-body { padding: 16px 20px 22px; }
  .figure { overflow-x:auto; border:1px solid var(--line); border-radius:12px; background: var(--d-card); padding: 8px; }
  .diagram { display:block; width:100%; min-width: 760px; height:auto; }
  .how-body h3 { font-size:1rem; margin: 20px 0 8px; }
  .parts { display:grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 10px; }
  .part { border:1px solid var(--line); border-radius:10px; padding: 10px 12px; font-size:.9rem; }
  .part b { display:block; color: var(--d-border); margin-bottom: 2px; }
  .links { display:flex; flex-wrap:wrap; gap: 8px 18px; font-size:.92rem; }
  .links a { color: var(--d-border); }
  .sub { color: var(--muted); margin: 0 0 16px; font-size: .95rem; }
  .examples { display:flex; flex-wrap:wrap; gap:8px; margin-bottom: 20px; }
  .examples button { background:var(--card); color:var(--ink); border:1px solid var(--line); border-radius: 999px;
    padding: 6px 12px; font: inherit; font-size:.88rem; cursor:pointer; }
  .examples button:hover { border-color: var(--accent); }
  .examples button:disabled { opacity:.5; cursor: wait; }
  .msg { background:var(--card); border:1px solid var(--line); border-radius: 12px; padding: 12px 14px; margin: 10px 0; white-space: pre-wrap; }
  .msg.user { background:var(--user); margin-left: 15%; }
  .meta { color: var(--muted); font-size: .82rem; margin-top: 8px; }
  details { margin-top: 8px; font-size:.88rem; }
  summary { cursor:pointer; color: var(--accent); }
  pre { background: var(--bg); border:1px solid var(--line); border-radius:8px; padding:10px; overflow-x:auto; font-size:.8rem; white-space: pre-wrap; }
  .step { border-top:1px solid var(--line); margin-top:10px; padding-top:10px; white-space: normal; }
  .tool { font-weight:600; margin-bottom:6px; }
  .note { color: var(--muted); margin: 4px 0; }
  .step table { border-collapse: collapse; margin: 6px 0 10px; font-size:.85rem; display:block; overflow-x:auto; }
  .step th, .step td { border:1px solid var(--line); padding:4px 8px; text-align:left; }
  .step th { background: var(--bg); text-transform: capitalize; }
  .step td:not(:first-child) { font-variant-numeric: tabular-nums; }
  form { position: fixed; z-index:2; bottom:0; left:0; right:0; background: var(--bg); border-top:1px solid var(--line); padding: 12px 16px; }
  .row { max-width: 820px; margin: 0 auto; display:flex; gap:8px; }
  input { flex:1; padding: 12px; border-radius:10px; border:1px solid var(--line); background:var(--card); color:var(--ink); font: inherit; }
  form button { padding: 12px 18px; border:0; border-radius:10px; background:var(--accent); color:var(--on-accent); font: inherit; cursor:pointer; }
  form button:disabled { opacity:.5; cursor: wait; }
  @media (max-width: 520px) { .tagline { display:none; } .msg.user { margin-left: 6%; } }
</style></head><body>
<svg class="scene" viewBox="0 0 1200 400" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
  <rect width="1200" height="400" fill="var(--bg)"/>
  <circle cx="985" cy="120" r="46" fill="var(--sun)"/>
  <!-- surveillance network: laboratories linked without moving the data -->
  <g stroke="var(--shape)" stroke-width="1.5" fill="none" opacity=".55">
    <path d="M150 110 L290 70 L430 125 L290 70 L360 30 M150 110 L250 160 L430 125 M610 90 L740 60 L830 120 M430 125 L610 90"/>
  </g>
  <g fill="var(--shape)" opacity=".8">
    <circle cx="150" cy="110" r="6"/><circle cx="290" cy="70" r="7"/><circle cx="430" cy="125" r="6"/>
    <circle cx="360" cy="30" r="5"/><circle cx="250" cy="160" r="5"/><circle cx="610" cy="90" r="6"/>
    <circle cx="740" cy="60" r="5"/><circle cx="830" cy="120" r="6"/>
  </g>
  <path d="M0 260 C 180 200, 360 215, 560 250 S 960 205, 1200 245 L1200 400 L0 400 Z" fill="var(--hill-far)"/>
  <!-- barn and silo -->
  <g fill="var(--shape)">
    <rect x="812" y="212" width="26" height="62" rx="12"/>
    <path d="M850 236 L850 280 L940 280 L940 236 L895 204 Z"/>
  </g>
  <rect x="884" y="250" width="22" height="30" fill="var(--hill-far)"/>
  <path d="M0 305 C 220 255, 420 290, 640 300 S 1010 262, 1200 292 L1200 400 L0 400 Z" fill="var(--hill-near)"/>
  <!-- cattle -->
  <g fill="var(--shape)">
    <g transform="translate(250 268)">
      <rect x="0" y="0" width="62" height="30" rx="12"/><rect x="54" y="-8" width="24" height="20" rx="8"/>
      <rect x="6" y="24" width="7" height="22" rx="3"/><rect x="20" y="24" width="7" height="22" rx="3"/>
      <rect x="38" y="24" width="7" height="22" rx="3"/><rect x="50" y="24" width="7" height="22" rx="3"/>
      <path d="M58 -8 l-4 -8 l8 5 Z M74 -8 l4 -8 l-8 5 Z"/>
    </g>
    <g transform="translate(420 282) scale(.8)">
      <rect x="0" y="0" width="62" height="30" rx="12"/><rect x="-16" y="-8" width="24" height="20" rx="8"/>
      <rect x="6" y="24" width="7" height="22" rx="3"/><rect x="20" y="24" width="7" height="22" rx="3"/>
      <rect x="38" y="24" width="7" height="22" rx="3"/><rect x="50" y="24" width="7" height="22" rx="3"/>
      <path d="M-12 -8 l-4 -8 l8 5 Z M4 -8 l4 -8 l-8 5 Z"/>
    </g>
    <g transform="translate(1010 270) scale(.9)">
      <rect x="0" y="0" width="62" height="30" rx="12"/><rect x="54" y="6" width="24" height="20" rx="8"/>
      <rect x="6" y="24" width="7" height="22" rx="3"/><rect x="20" y="24" width="7" height="22" rx="3"/>
      <rect x="38" y="24" width="7" height="22" rx="3"/><rect x="50" y="24" width="7" height="22" rx="3"/>
    </g>
  </g>
  <!-- fence -->
  <g stroke="var(--shape)" stroke-width="3" opacity=".7">
    <path d="M560 318 L800 306 M560 332 L800 320 M570 308 L570 344 M630 305 L630 341 M690 302 L690 338 M750 299 L750 335"/>
  </g>
  <path d="M0 352 C 300 330, 700 350, 1200 336 L1200 400 L0 400 Z" fill="var(--hill-near)" opacity=".9"/>
</svg>
<main>
<header>
  <svg class="logo" viewBox="0 0 48 48" role="img" aria-label="LHO ontology logo">
    <!-- an ontology as a network of linked terms, on the blue of the architecture diagram -->
    <defs><clipPath id="logo-clip"><circle cx="24" cy="24" r="24"/></clipPath></defs>
    <circle cx="24" cy="24" r="24" fill="#1d5fa8"/>
    <path d="M10 44 L48 6 L48 48 L14 48 Z" fill="#164b87" clip-path="url(#logo-clip)"/>
    <path d="M22 12 L40 18 M22 12 L7 31 M22 12 L18 26 M22 12 L24 36 M22 12 L37 30 M40 18 L18 26 M40 18 L37 30 M40 18 L24 36 M40 18 L7 31 M7 31 L18 26 M7 31 L24 36 M18 26 L24 36 M37 30 L24 36" stroke="#ffffff" stroke-width="1.3" stroke-linecap="round" fill="none"/>
    <g fill="#ffffff"><circle cx="22" cy="12" r="2.6"/><circle cx="40" cy="18" r="3.6"/><circle cx="7" cy="31" r="2.4"/><circle cx="18" cy="26" r="2.6"/><circle cx="37" cy="30" r="3.2"/><circle cx="24" cy="36" r="4.8"/></g>
  </svg>
  <div class="titles">
    <h1>LHO knowledge-graph assistant</h1>
    <div class="tagline">Livestock Health Ontology · livestock disease surveillance</div>
  </div>
  <button id="howbtn" type="button">How it works</button>
  <button id="reset" type="button" title="Forget the earlier questions and start again">New chat</button>
  <button id="theme" type="button" aria-label="Switch between light and dark">Dark</button>
</header>
<p class="sub">Ask about synthetic laboratory test records for cattle (six laboratories) and pigs (two laboratories), 2019 to 2025.
Answers come from the knowledge graph through MCP tools, not from the model's memory. Follow-up questions use the last three questions as context. Model: <span id="model">__MODEL__</span>.</p>
<div class="examples" id="examples"></div>
<div id="chat"></div>
</main>
<dialog id="how" aria-labelledby="how-title">
  <div class="how-head"><h2 id="how-title">How it works</h2><button id="how-close" type="button">Close</button></div>
  <div class="how-body">
    <div class="figure">__DIAGRAM_SVG__</div>
    <h3>What each part does</h3>
    <div class="parts">__DIAGRAM_PARTS__</div>
    <h3>Links</h3>
    <div class="links">__DIAGRAM_LINKS__</div>
  </div>
</dialog>
<form id="form"><div class="row">
  <input id="q" autocomplete="off" placeholder="Ask a question, in English or Dutch" required>
  <button id="send">Ask</button>
</div></form>
<script>
const examples = ["How many BRSV tests were positive in 2024?", "Which pathogen has the highest positivity rate?",
  "What is the positivity rate of bacterial pathogens in beef cattle?", "Hoeveel testen met kweek waren positief?",
  "What percentage of pig samples were positive for PRRS?", "What is PI3?",
  "How many tests were positive for Salmonella?"];
const chat = document.getElementById("chat"), form = document.getElementById("form"),
      input = document.getElementById("q"), send = document.getElementById("send");
for (const text of examples) {
  const b = document.createElement("button"); b.type = "button"; b.textContent = text;
  b.onclick = () => { if (busy) return; input.value = text; form.requestSubmit(); };
  document.getElementById("examples").appendChild(b);
}
// Light and dark: follows the system setting until the user chooses, then remembers the choice.
const root = document.documentElement, themeButton = document.getElementById("theme");
function currentTheme() {
  return root.dataset.theme || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function showTheme() { themeButton.textContent = currentTheme() === "dark" ? "Light" : "Dark"; }
try { const saved = localStorage.getItem("lho-theme"); if (saved) root.dataset.theme = saved; } catch (e) {}
const asked = new URLSearchParams(location.search).get("theme");      // ?theme=light or ?theme=dark
if (asked === "light" || asked === "dark") root.dataset.theme = asked;
showTheme();
themeButton.onclick = () => {
  root.dataset.theme = currentTheme() === "dark" ? "light" : "dark";
  try { localStorage.setItem("lho-theme", root.dataset.theme); } catch (e) {}
  showTheme();
};
const how = document.getElementById("how");
document.getElementById("howbtn").onclick = () => how.showModal();
document.getElementById("how-close").onclick = () => how.close();
how.onclick = (event) => { if (event.target === how) how.close(); };   // click outside closes it
if (new URLSearchParams(location.search).has("how")) how.showModal();   // ?how opens the diagram directly
document.getElementById("reset").onclick = () => {
  if (busy) return;
  history.length = 0; document.getElementById("chat").replaceChildren();
};
function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
function table(rows) {
  const t = el("table"), head = el("tr");
  const columns = Object.keys(rows[0]);
  for (const c of columns) head.appendChild(el("th", c.replace(/_/g, " ")));
  t.appendChild(head);
  for (const row of rows) {
    const tr = el("tr");
    for (const c of columns) tr.appendChild(el("td", row[c] === null ? "" : String(row[c])));
    t.appendChild(tr);
  }
  return t;
}
function renderStep(step) {
  const wrap = el("div", undefined, "step");
  const args = Object.entries(step.arguments || {}).filter(([, v]) => v !== "" && v !== null)
    .map(([k, v]) => `${k} = ${v}`).join(", ");
  wrap.appendChild(el("div", `Tool: ${step.tool}` + (args ? ` (${args})` : ""), "tool"));
  let result = null;
  try { result = JSON.parse(step.result); } catch (e) {}
  if (result && typeof result === "object") {
    if (result.error) wrap.appendChild(el("div", "Tool error: " + result.error, "note"));
    const summary = {};
    for (const [k, v] of Object.entries(result))
      if (v === null || typeof v !== "object") summary[k] = v;
    if (result.filters && typeof result.filters === "object")
      summary.filters = Object.entries(result.filters).map(([k, v]) => `${k}: ${v}`).join("; ");
    if (result.overall) Object.assign(summary, {"overall tested": result.overall.tested,
      "overall positive": result.overall.positive, "overall positivity percent": result.overall.positivity_percent});
    delete summary.error;
    if (Object.keys(summary).length)
      wrap.appendChild(table(Object.entries(summary).map(([k, v]) => ({field: k.replace(/_/g, " "), value: v}))));
    for (const key of ["rows", "matches", "values"])
      if (Array.isArray(result[key]) && result[key].length) wrap.appendChild(table(result[key]));
    const rest = {};
    for (const [k, v] of Object.entries(result))
      if (v !== null && typeof v === "object" && !["rows", "matches", "values", "filters", "overall"].includes(k)) rest[k] = v;
    if (Object.keys(rest).length) wrap.appendChild(el("pre", JSON.stringify(rest, null, 2)));
  } else {
    wrap.appendChild(el("pre", step.result));
  }
  if (step.sparql) {
    const d = el("details"); d.appendChild(el("summary", "SPARQL query that ran"));
    d.appendChild(el("pre", step.sparql)); wrap.appendChild(d);
  }
  return wrap;
}
function add(cls, text) {
  const d = document.createElement("div"); d.className = "msg " + cls; d.textContent = text;
  chat.appendChild(d); d.scrollIntoView({behavior: "smooth", block: "end"}); return d;
}
const history = [];                     // the last turns of this tab
let busy = false;                       // the local model answers one question at a time
function setBusy(state) {
  busy = state; send.disabled = state;
  for (const b of document.querySelectorAll("#examples button")) b.disabled = state;
}
form.onsubmit = async (event) => {
  event.preventDefault();
  const question = input.value.trim(); if (!question || busy) return;
  add("user", question); input.value = ""; setBusy(true);
  const box = add("bot", "Looking it up in the graph (a local model can take a minute)...");
  try {
    const response = await fetch("/ask", {method: "POST", headers: {"Content-Type": "application/json"},
                                          body: JSON.stringify({question, history})});
    const data = await response.json();
    box.textContent = data.answer || data.error;
    if (data.steps) {
      const meta = document.createElement("div"); meta.className = "meta";
      meta.textContent = `${data.steps.length} tool call(s), ${data.seconds} s` + (data.grounded ? "" : ", numbers NOT verified");
      box.appendChild(meta);
      const details = document.createElement("details");
      const summary = document.createElement("summary"); summary.textContent = "How this was answered";
      details.appendChild(summary);
      for (const step of data.steps) details.appendChild(renderStep(step));
      box.appendChild(details);
      history.push({question, answer: data.answer, steps: data.steps});   // remembered for follow-ups
      if (history.length > 3) history.shift();
    }
  } catch (error) { box.textContent = "Error: " + error; }
  setBusy(false); input.focus();
};
</script></body></html>"""

_agent: Agent | None = None
_lock = asyncio.Lock()          # a local model answers one question at a time


def _vars(colours: dict[str, str]) -> str:
    return " ".join(f"{name}:{value};" for name, value in colours.items())


DIAGRAM_CSS = (
    f":root {{ {_vars(diagram.LIGHT)} }}\n"
    f"  @media (prefers-color-scheme: dark) {{ :root:not([data-theme=\"light\"]) {{ {_vars(diagram.DARK)} }} }}\n"
    f"  :root[data-theme=\"dark\"] {{ {_vars(diagram.DARK)} }}"
)
PAGE = (PAGE.replace("__DIAGRAM_CSS__", DIAGRAM_CSS)
        .replace("__DIAGRAM_SVG__", diagram.SVG)
        .replace("__DIAGRAM_PARTS__", "".join(
            f'<div class="part"><b>{name}</b>{text}</div>' for name, text in diagram.PARTS))
        .replace("__DIAGRAM_LINKS__", "".join(
            f'<a href="{url}" target="_blank" rel="noopener">{name}</a>' for name, url in diagram.LINKS)))


async def index(request: Request) -> HTMLResponse:
    return HTMLResponse(PAGE.replace("__MODEL__", _agent.model_name if _agent else "not loaded"))


async def ask(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        question = str(body.get("question", "")).strip()
        turns = body.get("history") or []
    except Exception:
        return JSONResponse({"error": "Send JSON such as {\"question\": \"...\"}."}, status_code=400)
    if not question or len(question) > 500:
        return JSONResponse({"error": "The question must have 1 to 500 characters."}, status_code=400)
    async with _lock:
        result = await _agent.ask(question, history=[t for t in turns if isinstance(t, dict)])
    return JSONResponse(result)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    global _agent
    async with Agent() as agent:
        _agent = agent
        yield
    _agent = None


app = Starlette(routes=[Route("/", index), Route("/ask", ask, methods=["POST"])], lifespan=lifespan)


def main() -> None:
    uvicorn.run(app, host=os.environ.get("LHO_HOST", "127.0.0.1"), port=int(os.environ.get("LHO_PORT", "8000")))


if __name__ == "__main__":
    main()
