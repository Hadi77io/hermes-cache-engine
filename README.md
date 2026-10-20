# hermes-cache-engine

**A Hermes Agent plugin that cuts token spend by clipping what enters context — without breaking provider prompt caching.**

Most "token savers" quietly make things worse: they rewrite old messages, which invalidates the provider prompt cache from that point on. `hermes-cache-engine` does the opposite. It measures first, touches only the mutable tail, and never rewrites the cached prefix.

```yaml
cache_engine:
  mode: report     # measure everything, change nothing (default)
```

---

## The problem (measured, not guessed)

On a real Hermes deployment using DeepSeek V4.1 Flash through OpenCode Go, seven days of traffic broke down like this:

| Bucket | Tokens | Cost | Share |
|---|---|---|---|
| **New input** (cache miss) | 34.6M | $10.38 | **53%** |
| **Output** | 3.7M | $4.46 | **23%** |
| Cache read | 488.8M | $2.93 | 15% |

Two conclusions that shaped this plugin:

1. **Killing the cache would raise the bill.** A cache miss costs **50×** a cache read ($0.30 vs $0.006 per million). Cache reads are the cheapest thing in the request — the goal is to *keep hitting them*, not to send less of them.
2. **The bill is new tokens.** What the model writes, plus what your tools dump into context. Four tools produced more than half of all context bytes: `read_file`, `terminal`, `execute_code`, `web_extract` — with `web_extract`, `skill_view`, `session_search` and `memory_recall` averaging **16k–27k characters per call**.

---

## What it does

Three rules, enforced at the `llm_request` middleware layer:

1. **Never touch the cached prefix.** Everything before the most recent user message is immutable. Editing history in the middle invalidates the cache from that point to the end of the context — the single most expensive mistake an agent can make.
2. **Clip oversized tool results to a budget.** Keep head (60%) + tail (40%), drop the middle, leave a pointer line with a content fingerprint and the exact number of omitted tokens. Head **and** tail, because exit codes and stack traces live at the edges.
3. **Report the savings, every call.** One JSONL line per request: calls, clipped results, tokens saved. No silent behaviour changes.

### Safe by default

`mode: report` computes exactly what it *would* save and mutates nothing. You get real numbers from your own workload before you enable anything:

```bash
tail -3 ~/.hermes/cache-engine/stats.jsonl
python -c "from hermes_cache_engine.engine import CacheEngine; from hermes_cache_engine.config import load_settings; print(CacheEngine(load_settings()).total_saved())"
```

Flip to `mode: enforce` when the numbers justify it.

---

## Install

```bash
git clone https://github.com/Hadi77io/hermes-cache-engine.git \
  ~/.hermes/plugins/hermes-cache-engine
```

Then in your Hermes config:

```yaml
plugins:
  enabled:
    - hermes-cache-engine

cache_engine:
  mode: report
  default_cap: 1200
  hard_cap: 6000
  head_ratio: 0.6
  chars_per_token: 3.0        # Arabic text is denser than English — tune this
  per_tool:
    web_extract: 900
    skill_view: 900
    session_search: 900
    memory_recall: 900
    read_file: 2000
```

Env overrides for quick experiments: `HERMES_CACHE_ENGINE_MODE=enforce`, `HERMES_CACHE_ENGINE_DEFAULT_CAP=800`.

---

## Design notes

- **Tool names are recovered from `tool_call_id`** by scanning the assistant turn that requested them, so caps work even when the wire format omits `name`.
- **Clamping is bounded**: `cap = min(per_tool[tool] or default_cap, hard_cap)`, never below 64 tokens.
- **Stats never break a request.** Every write is wrapped; the log is append-only JSONL.
- **Token estimates are configurable** (`chars_per_token`), because a fixed 4 chars/token lies badly for Arabic.

## Roadmap

- [x] v0.1 — tail-only clipping, per-tool caps, JSONL savings report
- [ ] v0.2 — `fetch_context(fingerprint, start, end)` retriever so clipped content stays reachable by choice
- [ ] v0.3 — delta reads: re-reading a file returns a unified diff plus a fingerprint, not the whole file
- [ ] v0.4 — prefix guard: hash the prefix each call and warn when something silently invalidates the cache
- [ ] v0.5 — budget allocator: fixed shares for system prompt / tool schemas / history / new content

## Development

```bash
make test          # or: python3 -m unittest discover -s tests -v
```

Ten tests, no dependencies beyond the standard library (Python 3.10+).

> CI note: the GitHub Actions workflow was removed because the repository owner's
> account is billing-locked for Actions. Re-add `.github/workflows/ci.yml` (single job,
> `python -m unittest discover -s tests -v`) once that is resolved.

---

## العربية

**بلغن لهيرمس يخفّض استهلاك التوكن عبر تقليم ما يدخل السياق، دون كسر الكاش.**

- **الوضع الآمن `report`:** يقيس كم توكن كان سيوفر — بلا أي تغيير في السلوك.
- **القاعدة الذهبية:** لا يُعدَّل أي محتوى قبل آخر رسالة مستخدم؛ لأن تعديل وسط التاريخ يمسح كاش المزوّد من نقطة التعديل لآخره، وكلفة الـcache miss أغلى 50 مرة.
- **التقليم:** رأس 60% + ذيل 40%، مع سطر مؤشر يحوي بصمة المحتوى وعدد التوكنات المحذوفة.

القياس على تشغيل حقيقي (7 أيام): **53% من الفاتورة إدخال جديد، 23% إخراج، 15% فقط كاش** — لذلك الهدف تقليل الجديد، لا تقليل الكاش.

## License

MIT © 2026 Hadi Aljurdi
