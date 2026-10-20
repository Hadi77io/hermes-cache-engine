#!/usr/bin/env python3
"""Measure what the clipper actually saves on real Hermes traffic.

Reads the local Hermes state.db read-only, replays real tool results and real
conversations through the plugin, and prints a markdown report.

    python3 scripts/cee_bench.py --days 7
    python3 scripts/cee_bench.py --days 7 --mode full   # includes cost estimate

Numbers produced here are the ones quoted in README.md. Re-run after any
change to caps — the point of the plugin is measured savings, not vibes.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hermes_cache_engine.clipper import clip, estimate_tokens  # noqa: E402
from hermes_cache_engine.config import Settings  # noqa: E402
from hermes_cache_engine.engine import CacheEngine, _mutable_from  # noqa: E402

# DeepSeek V4.1 Flash peak list prices, USD per million tokens (2026-10).
PRICE_IN_FRESH = 0.30
PRICE_CACHE_READ = 0.006
PRICE_OUT = 1.20


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def window_start(days: float) -> float:
    return time.time() - days * 86400


def traffic(conn, since: float) -> dict:
    row = conn.execute(
        """SELECT COUNT(*) calls,
                  COALESCE(SUM(input_tokens),0) inp,
                  COALESCE(SUM(cache_read_tokens),0) cache,
                  COALESCE(SUM(output_tokens),0) out,
                  COALESCE(SUM(api_call_count),0) apis
           FROM sessions WHERE started_at >= ?""",
        (since,),
    ).fetchone()
    return dict(row)


def tool_results(conn, since: float) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT tool_name, content FROM messages
           WHERE role='tool' AND timestamp >= ? AND content IS NOT NULL""",
        (since,),
    ).fetchall()


def measure_clipping(rows, settings: Settings) -> dict:
    per_tool = defaultdict(lambda: {"calls": 0, "chars": 0, "clipped": 0,
                                    "chars_kept": 0, "tokens_before": 0, "tokens_saved": 0})
    total_chars = total_saved = total_before = 0
    clipped_calls = 0
    elapsed = []

    for row in rows:
        body = row["content"] or ""
        if not body:
            continue
        tool = row["tool_name"] or "unknown"
        cap = settings.cap_for(tool)
        t0 = time.perf_counter()
        result = clip(body, cap_tokens=cap, head_ratio=settings.head_ratio,
                      chars_per_token=settings.chars_per_token)
        elapsed.append(time.perf_counter() - t0)

        bucket = per_tool[tool]
        bucket["calls"] += 1
        bucket["chars"] += len(body)
        bucket["tokens_before"] += result.tokens_before
        total_chars += len(body)
        total_before += result.tokens_before
        if result.changed:
            clipped_calls += 1
            bucket["clipped"] += 1
            bucket["tokens_saved"] += result.saved
            bucket["chars_kept"] += len(result.text)
            total_saved += result.saved

    return {
        "per_tool": per_tool,
        "chars": total_chars,
        "tokens_before": total_before,
        "tokens_saved": total_saved,
        "clipped_calls": clipped_calls,
        "calls": sum(b["calls"] for b in per_tool.values()),
        "median_us": statistics.median(elapsed) * 1e6 if elapsed else 0.0,
        "elapsed_s": sum(elapsed),
    }


def verify_prefix(conn, since: float, settings: Settings) -> dict:
    """Replay real conversations in enforce mode; assert the prefix is byte-identical."""
    sessions = conn.execute(
        """SELECT DISTINCT session_id FROM messages
           WHERE timestamp >= ? AND role='tool'""",
        (since,),
    ).fetchall()
    engine = CacheEngine(Settings(**{**settings.__dict__, "mode": "enforce",
                                     "stats_path": os.devnull}))
    checked_msgs = changed_prefix = 0
    sessions_checked = 0

    for (sid,) in sessions:
        rows = conn.execute(
            """SELECT role, content, tool_calls, tool_call_id, tool_name
               FROM messages WHERE session_id=? ORDER BY id""",
            (sid,),
        ).fetchall()
        messages = []
        for r in rows:
            msg = {"role": r["role"], "content": r["content"]}
            if r["tool_call_id"]:
                msg["tool_call_id"] = r["tool_call_id"]
            if r["tool_name"]:
                msg["name"] = r["tool_name"]
            if r["tool_calls"]:
                try:
                    msg["tool_calls"] = json.loads(r["tool_calls"])
                except Exception:
                    pass
            messages.append(msg)
        if len(messages) < 2:
            continue

        boundary = _mutable_from(messages)
        before = json.dumps(messages[:boundary], sort_keys=True, ensure_ascii=False)
        payload = {"messages": [dict(m) for m in messages]}
        engine.on_llm_request(request=payload)
        after = json.dumps(payload["messages"][:boundary], sort_keys=True, ensure_ascii=False)
        checked_msgs += boundary
        sessions_checked += 1
        if before != after:
            changed_prefix += 1

    return {"sessions": sessions_checked, "prefix_messages": checked_msgs,
            "prefix_changed": changed_prefix}


def fmt(n: float) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return f"{n:.0f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.expanduser("~/state.db"))
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    since = window_start(args.days)
    conn = connect(os.path.expanduser(args.db))
    settings = Settings()  # ship defaults; that is what the README quotes

    rows = tool_results(conn, since)
    if not rows:
        print(f"no tool messages in the last {args.days} days", file=sys.stderr)
        return 1

    t = traffic(conn, since)
    m = measure_clipping(rows, settings)
    p = verify_prefix(conn, since, settings)

    dollars = m["tokens_saved"] / 1_000_000 * PRICE_IN_FRESH
    share = m["tokens_saved"] / t["inp"] * 100 if t["inp"] else 0.0

    if args.json:
        print(json.dumps({
            "days": args.days, "traffic": t,
            "clip": {k: v for k, v in m.items() if k != "per_tool"},
            "per_tool": m["per_tool"], "prefix": p,
            "usd_saved_fresh_input": round(dollars, 2),
        }, indent=2, ensure_ascii=False))
        return 0

    print(f"# Measured — last {args.days:g} days\n")
    print(f"- API calls: **{t['apis']:,}** · sessions: {conn.execute('SELECT COUNT(*) FROM sessions WHERE started_at>=?', (since,)).fetchone()[0]:,}")
    print(f"- fresh input: **{fmt(t['inp'])}** tok · cache read **{fmt(t['cache'])}** "
          f"({t['cache']/(t['inp']+t['cache'] or 1)*100:.1f}%) · output {fmt(t['out'])} tok")
    print(f"- tool results: **{m['calls']:,}** calls · {fmt(m['chars'])} chars "
          f"(≈{fmt(m['tokens_before'])} tok at {settings.chars_per_token:g} ch/tok)\n")

    print("| tool | calls | chars | est tok | clipped | saved tok | saved |")
    print("|---|---|---|---|---|---|---|")
    for tool, b in sorted(m["per_tool"].items(), key=lambda kv: -kv[1]["tokens_saved"])[:12]:
        pct = b["tokens_saved"] / b["tokens_before"] * 100 if b["tokens_before"] else 0
        print(f"| `{tool}` | {b['calls']:,} | {fmt(b['chars'])} | {fmt(b['tokens_before'])} "
              f"| {b['clipped']:,} | {fmt(b['tokens_saved'])} | {pct:.0f}% |")

    print(f"\n**Total saved: {fmt(m['tokens_saved'])} tok "
          f"({m['tokens_saved']/max(1,m['tokens_before'])*100:.1f}% of tool content, "
          f"{share:.1f}% of fresh input) ≈ ${dollars:.2f}**")
    print(f"**Clipped {m['clipped_calls']:,}/{m['calls']:,} results "
          f"({m['clipped_calls']/max(1,m['calls'])*100:.0f}%)**")
    print(f"**Prefix invariance: {p['prefix_changed']} changed / {p['prefix_messages']:,} "
          f"prefix messages across {p['sessions']:,} sessions**")
    print(f"**Overhead: {m['median_us']:.0f} µs median per result "
          f"({m['elapsed_s']:.1f}s for {m['calls']:,} results)**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
