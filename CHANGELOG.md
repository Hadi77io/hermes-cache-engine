# Changelog

## 0.1.0 — 2026-10-20
- `llm_request` middleware that clips oversized tool results (head 60% / tail 40%).
- Never rewrites anything before the last user message (prompt-cache safety).
- Per-tool caps with a hard ceiling; tool names resolved via `tool_call_id`.
- `report` mode (default, measures only) and `enforce` mode.
- JSONL savings log + `total_saved()` helper.
- 10 stdlib unit tests, GitHub Actions CI on Python 3.10–3.12.
