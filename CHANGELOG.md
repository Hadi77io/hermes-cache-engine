# Changelog

## 0.2.0 — 2026-10-20
- **Fixed the middleware contract**: the callback now returns `{"request": {...}}`
  as the runner requires. The 0.1.0 signature (`payload`) never received the
  request at all, so `enforce` mode silently did nothing on a live gateway.
- Copy-on-write: the incoming request object is no longer mutated in place.
- Returns `None` when nothing changed, so clean requests add no trace entries.
- Added `scripts/cee_bench.py` — replays real `state.db` traffic, reports savings
  per tool and proves prefix invariance by replaying whole conversations.
- README: measured numbers from 100 days / 49,829 tool results, generated chart.
- 13 tests (was 10).

## 0.1.0 — 2026-10-20
- `llm_request` middleware that clips oversized tool results (head 60% / tail 40%).
- Never rewrites anything before the last user message (prompt-cache safety).
- Per-tool caps with a hard ceiling; tool names resolved via `tool_call_id`.
- `report` mode (default, measures only) and `enforce` mode.
- JSONL savings log + `total_saved()` helper.
- 10 stdlib unit tests.
