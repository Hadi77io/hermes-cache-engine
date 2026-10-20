#!/usr/bin/env python3
"""Render assets/savings.svg from a cee_bench --json dump.

The chart is generated, never hand-drawn: numbers in the README and the picture
next to them come from the same measurement file.

    python3 scripts/cee_bench.py --days 100 --json > docs/measured-100d.json
    python3 scripts/make_assets.py docs/measured-100d.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "savings.svg"

W, ROW, TOP, BAR_X, BAR_W = 880, 34, 118, 210, 470
COLORS = ["#a78bfa", "#8b5cf6", "#7c3aed", "#22d3ee", "#06b6d4", "#38bdf8", "#818cf8", "#c084fc"]


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main() -> int:
    data = json.load(open(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs/measured-100d.json"))
    tools = sorted(data["per_tool"].items(), key=lambda kv: -kv[1]["tokens_saved"])[:8]
    peak = max(b["tokens_saved"] for _, b in tools) or 1

    height = TOP + ROW * len(tools) + 62
    rows = []
    for index, (tool, b) in enumerate(tools):
        y = TOP + index * ROW
        pct = b["tokens_saved"] / b["tokens_before"] * 100 if b["tokens_before"] else 0
        width = max(6, b["tokens_saved"] / peak * BAR_W)
        color = COLORS[index % len(COLORS)]
        rows.append(f'''
  <g>
    <text x="40" y="{y + 15}" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="13" fill="#8b9dc3">{esc(tool)[:26]}</text>
    <rect x="{BAR_X}" y="{y}" width="{BAR_W}" height="20" rx="10" fill="#1b2437"/>
    <rect x="{BAR_X}" y="{y}" width="{width:.1f}" height="20" rx="10" fill="{color}" opacity="0.92"/>
    <text x="{BAR_X + BAR_W + 16}" y="{y + 15}" font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,Arial" font-size="13" fill="#e2e8f0">{pct:.0f}%<tspan fill="#64748b"> · {b["tokens_saved"]/1000:.0f}k tok</tspan></text>
  </g>''')

    clip = data["clip"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}" role="img" aria-label="Measured token savings per tool">
  <defs>
    <linearGradient id="head" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#a78bfa"/><stop offset="100%" stop-color="#22d3ee"/>
    </linearGradient>
    <linearGradient id="card" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0d1117"/><stop offset="100%" stop-color="#111a2b"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{height}" rx="18" fill="url(#card)"/>
  <rect x="0" y="0" width="{W}" height="5" rx="2" fill="url(#head)"/>
  <text x="40" y="52" font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,Arial" font-size="20" font-weight="600" fill="#f8fafc">Measured on {clip["calls"]:,} real tool results</text>
  <text x="40" y="78" font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,Arial" font-size="13" fill="#94a3b8">{data["days"]:.0f} days of live traffic · {clip["clipped_calls"]:,} results clipped ({clip["clipped_calls"]/clip["calls"]*100:.0f}%) · {clip["tokens_saved"]/1e6:.1f}M tokens never sent</text>
  <text x="40" y="98" font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,Arial" font-size="12" fill="#64748b">share of each tool's own output bytes removed, estimated at 3 chars/token</text>
{"".join(rows)}
  <text x="40" y="{height - 26}" font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,Arial" font-size="12" fill="#64748b">bars = tokens saved · total {clip["tokens_saved"]/1e6:.1f}M tok = {clip["tokens_saved"]/clip["tokens_before"]*100:.0f}% of all tool content</text>
</svg>
'''
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT} ({len(svg)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
