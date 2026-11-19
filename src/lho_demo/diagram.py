"""The architecture diagram: one SVG, used by the chat page and by the README.

    python -m lho_demo.diagram      writes docs/architecture.svg

In the chat page the colours are CSS variables, so the diagram follows the
light and dark theme. The exported file has the light colours written in.
"""
from __future__ import annotations

import re

from .config import ROOT

# Colours of the exported file (the chat page defines the same names in CSS).
LIGHT = {
    "--d-card": "#ffffff", "--d-ink": "#16283a", "--d-soft": "#52667a", "--d-border": "#2a6fb0",
    "--d-dark-1": "#2f7cc4", "--d-dark-2": "#123a66", "--d-mid": "#3f86cb", "--d-on": "#ffffff",
    "--d-go": "#123a66", "--d-back": "#2e75b6", "--d-check": "#123a66", "--d-show": "#2e75b6",
    "--d-chip": "#dce9f5", "--d-chip-ink": "#123a66", "--d-ok-bg": "#eaf2fb", "--d-ok-line": "#9cc2e5",
    "--d-legend": "#f4f8fc",
}
DARK = {
    "--d-card": "#17222e", "--d-ink": "#e6eef6", "--d-soft": "#9db2c6", "--d-border": "#5b9bd8",
    "--d-dark-1": "#2f7cc4", "--d-dark-2": "#123a66", "--d-mid": "#3f86cb", "--d-on": "#ffffff",
    "--d-go": "#a9cdf5", "--d-back": "#5b9bd8", "--d-check": "#a9cdf5", "--d-show": "#5b9bd8",
    "--d-chip": "#24405c", "--d-chip-ink": "#d6e6f7", "--d-ok-bg": "#1b2c3f", "--d-ok-line": "#3f6a99",
    "--d-legend": "#1b2733",
}

STEPS = [
    ("go", "The user asks a question in the chat page."),
    ("go", "The agent sends the question and the list of tools to the language model."),
    ("back", "The model does not answer from memory. It chooses a tool and the filters."),
    ("go", "The agent calls that tool on the MCP server."),
    ("go", "The server finds the ontology terms for the user's words and runs a SPARQL query."),
    ("back", "The result goes back to the model."),
    ("check", "The model writes the answer. Every number in it is checked against the results."),
    ("show", "The answer is shown with its trace: the tool call, the result and the query."),
]

PARTS = [
    ("Chat page", "One web page. It sends the question to the agent and shows the answer with its trace."),
    ("Agent", "The loop that connects everything. It passes the question to the model, runs the tools "
              "the model asks for, and checks the numbers in the final answer."),
    ("Language model", "An open-source model (qwen2.5:7b) that runs on this computer with Ollama. "
                       "It decides which tool to call and writes the answer. No data leave the machine."),
    ("MCP server", "Offers five read-only tools through the Model Context Protocol, an open standard. "
                   "The model passes plain words; the server builds the query, so the model never writes SPARQL."),
    ("Knowledge graph", "The Livestock Health Ontology (LHO V1.5) plus one graph per laboratory with synthetic "
                        "test records (six cattle laboratories, two pig laboratories). The ontology gives the words their meaning: \"bacteria\", \"kweek\" "
                        "and \"BRSV\" are all found through its labels and class hierarchy."),
    ("Number check", "Every number in an answer must appear in a tool result. If not, the model gets one "
                     "chance to correct it; otherwise the answer is withheld."),
]

LINKS = [
    ("Livestock Health Ontology on BioPortal", "https://bioportal.bioontology.org/ontologies/LHO"),
    ("LHO persistent address", "https://www.purl.org/decide/LiveStockHealthOnto/LHO"),
    ("Model Context Protocol", "https://modelcontextprotocol.io"),
]


def _legend() -> str:
    lines = []
    for number, (kind, text) in enumerate(STEPS, start=1):
        y = 446 + (number - 1) * 19
        lines.append(f'<text x="38" y="{y}" class="n {kind}">{number}:</text>'
                     f'<text x="62" y="{y}" class="t">{text}</text>')
    return "\n    ".join(lines)


SVG = f"""<svg class="diagram" viewBox="0 0 1000 600" role="img"
     aria-label="How the assistant works: user, chat page, agent, language model, MCP server, knowledge graph">
  <defs>
    <linearGradient id="d-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--d-dark-1)"/><stop offset="1" stop-color="var(--d-dark-2)"/>
    </linearGradient>
    <marker id="d-go" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M0 0 L10 5 L0 10 Z" fill="var(--d-go)"/></marker>
    <marker id="d-back" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M0 0 L10 5 L0 10 Z" fill="var(--d-back)"/></marker>
    <marker id="d-check" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M0 0 L10 5 L0 10 Z" fill="var(--d-check)"/></marker>
    <marker id="d-show" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M0 0 L10 5 L0 10 Z" fill="var(--d-show)"/></marker>
  </defs>
  <style>
    .diagram text {{ font-family: system-ui, "Segoe UI", Arial, sans-serif; }}
    .diagram .title {{ font-size: 19px; font-weight: 700; fill: var(--d-on); }}
    .diagram .sub {{ font-size: 13.5px; fill: var(--d-on); opacity: .92; }}
    .diagram .plain {{ font-size: 16px; font-weight: 700; fill: var(--d-ink); }}
    .diagram .blue {{ font-size: 16px; font-weight: 700; fill: var(--d-border); }}
    .diagram .small {{ font-size: 12.5px; fill: var(--d-soft); }}
    .diagram .chip {{ font-size: 14px; font-weight: 600; fill: var(--d-chip-ink); }}
    .diagram .lab {{ font-size: 12.5px; font-weight: 600; fill: var(--d-on); }}
    .diagram .n {{ font-size: 15px; font-weight: 700; }}
    .diagram .t {{ font-size: 14px; fill: var(--d-ink); }}
    .diagram .go {{ fill: var(--d-go); }} .diagram .back {{ fill: var(--d-back); }}
    .diagram .check {{ fill: var(--d-check); }} .diagram .show {{ fill: var(--d-show); }}
    .diagram .a {{ fill: none; stroke-width: 2.2; }}
    .diagram .a.go {{ stroke: var(--d-go); stroke-dasharray: 2 4; marker-end: url(#d-go); }}
    .diagram .a.solid {{ stroke: var(--d-go); marker-end: url(#d-go); }}
    .diagram .a.back {{ stroke: var(--d-back); stroke-dasharray: 9 6; marker-end: url(#d-back); }}
    .diagram .a.check {{ stroke: var(--d-check); marker-end: url(#d-check); }}
    .diagram .a.show {{ stroke: var(--d-show); marker-end: url(#d-show); }}
    .diagram .ico {{ fill: none; stroke: var(--d-on); stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }}
  </style>

  <!-- User -->
  <rect x="20" y="52" width="130" height="112" rx="14" fill="var(--d-card)" stroke="var(--d-border)" stroke-width="2.5"/>
  <g fill="none" stroke="var(--d-border)" stroke-width="3" stroke-linecap="round">
    <circle cx="85" cy="88" r="13"/><path d="M60 128 C 62 108, 108 108, 110 128"/>
  </g>
  <text x="85" y="152" text-anchor="middle" class="plain">User</text>

  <!-- Chat page -->
  <rect x="195" y="52" width="160" height="112" rx="14" fill="var(--d-mid)"/>
  <g class="ico"><rect x="247" y="68" width="56" height="42" rx="6"/><path d="M247 80 H303 M255 74 h.1 M262 74 h.1 M258 92 h34 M258 101 h22"/></g>
  <text x="275" y="136" text-anchor="middle" class="title" style="font-size:17px">Chat page</text>
  <text x="275" y="154" text-anchor="middle" class="sub">question and answer</text>

  <!-- Agent -->
  <rect x="420" y="40" width="210" height="136" rx="16" fill="url(#d-grad)"/>
  <g transform="translate(525 82)">
    <g fill="var(--d-on)">
      <rect x="-4" y="-21" width="8" height="9" rx="1.5"/><rect x="-4" y="-21" width="8" height="9" rx="1.5" transform="rotate(45)"/>
      <rect x="-4" y="-21" width="8" height="9" rx="1.5" transform="rotate(90)"/><rect x="-4" y="-21" width="8" height="9" rx="1.5" transform="rotate(135)"/>
      <rect x="-4" y="-21" width="8" height="9" rx="1.5" transform="rotate(180)"/><rect x="-4" y="-21" width="8" height="9" rx="1.5" transform="rotate(225)"/>
      <rect x="-4" y="-21" width="8" height="9" rx="1.5" transform="rotate(270)"/><rect x="-4" y="-21" width="8" height="9" rx="1.5" transform="rotate(315)"/>
    </g>
    <circle r="11" fill="none" stroke="var(--d-on)" stroke-width="6"/>
  </g>
  <text x="525" y="132" text-anchor="middle" class="title">Agent</text>
  <text x="525" y="153" text-anchor="middle" class="sub">runs the tools, checks the answer</text>

  <!-- Language model -->
  <rect x="740" y="40" width="240" height="136" rx="16" fill="url(#d-grad)"/>
  <rect x="752" y="52" width="74" height="112" rx="6" fill="var(--d-card)"/>
  <g fill="none" stroke="var(--d-border)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
    <rect x="770" y="89" width="38" height="38" rx="6"/><rect x="781" y="100" width="16" height="16" rx="2"/>
    <path d="M779 89 v-9 M789 89 v-9 M799 89 v-9 M779 127 v9 M789 127 v9 M799 127 v9 M770 98 h-9 M770 108 h-9 M770 118 h-9 M808 98 h9 M808 108 h9 M808 118 h9"/>
  </g>
  <text x="903" y="92" text-anchor="middle" class="title" style="font-size:17px">Language model</text>
  <text x="903" y="116" text-anchor="middle" class="sub">qwen2.5:7b in Ollama</text>
  <text x="903" y="135" text-anchor="middle" class="sub">open source, runs locally</text>

  <!-- MCP server -->
  <rect x="420" y="262" width="210" height="124" rx="14" fill="var(--d-mid)"/>
  <g class="ico"><rect x="499" y="276" width="52" height="16" rx="4"/><rect x="499" y="297" width="52" height="16" rx="4"/>
    <path d="M507 284 h.1 M507 305 h.1 M525 313 v9 M511 322 h28"/></g>
  <text x="525" y="350" text-anchor="middle" class="title">MCP server</text>
  <text x="525" y="371" text-anchor="middle" class="sub">5 read-only tools</text>

  <!-- Knowledge graph -->
  <rect x="720" y="232" width="260" height="222" rx="14" fill="var(--d-card)" stroke="var(--d-border)" stroke-width="2.5"/>
  <text x="736" y="259" class="blue">Knowledge graph (RDF)</text>
  <rect x="736" y="272" width="228" height="52" rx="8" fill="var(--d-chip)"/>
  <g transform="translate(743 279) scale(0.79)">
    <circle cx="24" cy="24" r="24" fill="var(--d-dark-2)"/>
    <path d="M22 12 L40 18 M22 12 L7 31 M22 12 L18 26 M22 12 L24 36 M22 12 L37 30 M40 18 L18 26 M40 18 L37 30 M40 18 L24 36 M40 18 L7 31 M7 31 L18 26 M7 31 L24 36 M18 26 L24 36 M37 30 L24 36" stroke="#ffffff" stroke-width="1.5" stroke-linecap="round" fill="none"/>
    <g fill="#ffffff"><circle cx="22" cy="12" r="2.6"/><circle cx="40" cy="18" r="3.6"/><circle cx="7" cy="31" r="2.4"/><circle cx="18" cy="26" r="2.6"/><circle cx="37" cy="30" r="3.2"/><circle cx="24" cy="36" r="4.8"/></g>
  </g>
  <text x="790" y="296" class="chip">LHO ontology V1.5</text>
  <text x="790" y="314" class="small" style="fill:var(--d-chip-ink)">meaning of the words</text>
  <g>
    <rect x="736.0" y="336" width="52" height="34" rx="7" fill="var(--d-mid)"/><text x="762.0" y="358" text-anchor="middle" class="lab">Lab 1</text>
    <rect x="794.7" y="336" width="52" height="34" rx="7" fill="var(--d-mid)"/><text x="820.7" y="358" text-anchor="middle" class="lab">Lab 2</text>
    <rect x="853.4" y="336" width="52" height="34" rx="7" fill="var(--d-mid)"/><text x="879.4" y="358" text-anchor="middle" class="lab">Lab 3</text>
    <rect x="912.1" y="336" width="52" height="34" rx="7" fill="var(--d-mid)"/><text x="938.1" y="358" text-anchor="middle" class="lab">Lab 4</text>
    <rect x="736.0" y="378" width="52" height="34" rx="7" fill="var(--d-mid)"/><text x="762.0" y="400" text-anchor="middle" class="lab">Lab 5</text>
    <rect x="794.7" y="378" width="52" height="34" rx="7" fill="var(--d-mid)"/><text x="820.7" y="400" text-anchor="middle" class="lab">Lab 6</text>
    <rect x="853.4" y="378" width="52" height="34" rx="7" fill="var(--d-dark-2)"/><text x="879.4" y="400" text-anchor="middle" class="lab">Lab 7</text>
    <rect x="912.1" y="378" width="52" height="34" rx="7" fill="var(--d-dark-2)"/><text x="938.1" y="400" text-anchor="middle" class="lab">Lab 8</text>
  </g>
  <text x="850" y="436" text-anchor="middle" class="small">synthetic records: labs 1-6 cattle, 7-8 pigs</text>

  <!-- Number check -->
  <rect x="195" y="262" width="160" height="124" rx="14" fill="var(--d-ok-bg)" stroke="var(--d-ok-line)" stroke-width="2"/>
  <g fill="none" stroke="var(--d-check)" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M275 276 l22 8 v16 c0 14 -10 22 -22 27 c-12 -5 -22 -13 -22 -27 v-16 Z"/><path d="M265 301 l8 8 l13 -15"/>
  </g>
  <text x="275" y="352" text-anchor="middle" class="plain" style="fill:var(--d-check)">Number check</text>
  <text x="275" y="371" text-anchor="middle" class="small">no invented numbers</text>

  <!-- Arrows -->
  <path class="a solid" d="M152 92 H193"/><text x="172" y="84" text-anchor="middle" class="n go">1</text>
  <path class="a solid" d="M357 92 H418"/><text x="387" y="84" text-anchor="middle" class="n go">1</text>
  <path class="a go" d="M632 84 H738"/><text x="685" y="75" text-anchor="middle" class="n go">2</text>
  <path class="a back" d="M738 132 H634"/><text x="685" y="153" text-anchor="middle" class="n back">3</text>
  <path class="a go" d="M495 178 V260"/><text x="481" y="224" text-anchor="middle" class="n go">4</text>
  <path class="a back" d="M555 260 V180"/><text x="570" y="224" text-anchor="middle" class="n back">6</text>
  <path class="a go" d="M632 306 H718"/><text x="675" y="297" text-anchor="middle" class="n go">5</text>
  <path class="a back" d="M718 344 H634"/><text x="675" y="365" text-anchor="middle" class="n back">6</text>
  <path class="a check" d="M424 170 L353 264"/><text x="374" y="212" text-anchor="middle" class="n check">7</text>
  <path class="a show" d="M275 260 V166"/><text x="259" y="218" text-anchor="middle" class="n show">8</text>
  <path class="a show" d="M193 132 H154"/><text x="173" y="153" text-anchor="middle" class="n show">8</text>

  <!-- Steps -->
  <rect x="20" y="420" width="660" height="170" rx="6" fill="var(--d-legend)" stroke="var(--d-soft)" stroke-width="1.5" stroke-dasharray="7 5"/>
    {_legend()}
</svg>"""


def export(path=ROOT / "docs" / "architecture.svg") -> None:
    """Write the diagram as a standalone file with the light colours."""
    svg = SVG.replace('<svg class="diagram"', '<svg xmlns="http://www.w3.org/2000/svg" class="diagram"', 1)
    svg = re.sub(r"var\((--d-[a-z0-9-]+)\)", lambda m: LIGHT[m.group(1)], svg)
    svg = svg.replace("</defs>", '</defs>\n  <rect width="1000" height="600" fill="#ffffff"/>', 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    export()
