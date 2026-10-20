"""The middleware itself: clip only the mutable tail, never the cached prefix."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Mapping

from .clipper import clip, estimate_tokens
from .config import Settings

ROLE_TOOL = "tool"


def _tool_names(messages: list[Mapping[str, Any]]) -> dict[str, str]:
    """Map tool_call_id -> tool name from the assistant turn that requested it."""
    names: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for call in msg.get("tool_calls") or []:
            if not isinstance(call, Mapping):
                continue
            fn = call.get("function") or {}
            if call.get("id") and fn.get("name"):
                names[str(call["id"])] = str(fn["name"])
    return names


def _mutable_from(messages: list[Mapping[str, Any]]) -> int:
    """Everything before the last user message is cached prefix: never touch it.

    Rewriting a message in the middle of history invalidates the provider prompt
    cache from that point on, which costs far more than the bytes saved.
    """
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            return index + 1
    return 0


class CacheEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    # ---- reporting -------------------------------------------------------
    def _log(self, record: Mapping[str, Any]) -> None:
        try:
            path = os.path.expanduser(self.settings.stats_path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(dict(record), ensure_ascii=False) + "\n")
        except Exception:
            pass  # stats must never break a request

    def total_saved(self) -> int:
        path = os.path.expanduser(self.settings.stats_path)
        total = 0
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        total += int(json.loads(line).get("saved_tokens") or 0)
                    except Exception:
                        continue
        except FileNotFoundError:
            return 0
        return total

    # ---- middleware ------------------------------------------------------
    def on_llm_request(self, payload: Any, **kwargs: Any) -> Any:
        """``llm_request`` middleware: measure, and optionally rewrite, tool results."""
        messages = payload.get("messages") if isinstance(payload, Mapping) else None
        if not isinstance(messages, list) or not messages:
            return payload

        enforce = str(self.settings.mode).lower() == "enforce"
        names = _tool_names(messages)
        start = _mutable_from(messages)

        saved_total = 0
        clipped_count = 0
        for msg in messages[start:]:
            if not isinstance(msg, dict) or msg.get("role") != ROLE_TOOL:
                continue
            body = msg.get("content")
            if not isinstance(body, str) or not body:
                continue
            tool_name = msg.get("name") or names.get(str(msg.get("tool_call_id", "")))
            result = clip(
                body,
                cap_tokens=self.settings.cap_for(tool_name),
                head_ratio=self.settings.head_ratio,
                chars_per_token=self.settings.chars_per_token,
            )
            if not result.changed:
                continue
            clipped_count += 1
            saved_total += result.saved
            if enforce:
                msg["content"] = result.text

        if clipped_count:
            self._log({
                "ts": round(time.time(), 3),
                "mode": "enforce" if enforce else "report",
                "clipped": clipped_count,
                "saved_tokens": saved_total,
                "calls": len(messages),
            })
        return payload
