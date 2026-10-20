import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hermes_cache_engine.config import Settings
from hermes_cache_engine.engine import CacheEngine, _mutable_from, _tool_names


def settings(tmp, mode="report"):
    return Settings(mode=mode, default_cap=100, stats_path=os.path.join(tmp, "stats.jsonl"))


def big(n=20_000):
    return "A" * n


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _request(self, tool_body):
        return {"messages": [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "function": {"name": "web_extract", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "prefix body " * 10},
            {"role": "user", "content": "newest turn"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c2", "function": {"name": "web_extract", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c2", "content": tool_body},
        ]}

    def test_report_mode_changes_nothing(self):
        request = self._request(big())
        before = json.dumps(request, sort_keys=True)
        result = CacheEngine(settings(self.tmp, "report")).on_llm_request(request=request)
        self.assertIsNone(result)
        self.assertEqual(before, json.dumps(request, sort_keys=True))

    def test_enforce_returns_middleware_contract(self):
        # The runner only honours {"request": {...}}; anything else is dropped silently.
        result = CacheEngine(settings(self.tmp, "enforce")).on_llm_request(
            request=self._request(big()))
        self.assertIsInstance(result, dict)
        self.assertIsInstance(result.get("request"), dict)
        self.assertIsInstance(result["request"].get("messages"), list)

    def test_enforce_clips_only_after_last_user_message(self):
        request = self._request(big())
        result = CacheEngine(settings(self.tmp, "enforce")).on_llm_request(request=request)
        msgs = result["request"]["messages"]
        self.assertEqual(msgs[2]["content"], "prefix body " * 10)  # cached prefix untouched
        self.assertIn("omitted", msgs[5]["content"])
        self.assertLess(len(msgs[5]["content"]), len(big()))
        # the caller's own request object is never mutated
        self.assertEqual(request["messages"][5]["content"], big())

    def test_stats_are_written(self):
        engine = CacheEngine(settings(self.tmp, "report"))
        engine.on_llm_request(request=self._request(big()))
        self.assertGreater(engine.total_saved(), 0)

    def test_no_change_returns_none(self):
        self.assertIsNone(
            CacheEngine(settings(self.tmp, "enforce")).on_llm_request(
                request={"messages": [{"role": "user", "content": "hi"}]}))

    def test_ignores_foreign_payloads(self):
        engine = CacheEngine(settings(self.tmp, "enforce"))
        self.assertIsNone(engine.on_llm_request())
        self.assertIsNone(engine.on_llm_request(request={"input": "not a chat payload"}))

    def test_mutable_boundary(self):
        msgs = [{"role": "user"}, {"role": "tool"}, {"role": "assistant"}]
        self.assertEqual(_mutable_from(msgs), 1)
        self.assertEqual(_mutable_from([{"role": "tool"}]), 0)

    def test_tool_name_mapping(self):
        msgs = [{"role": "assistant", "tool_calls": [
            {"id": "x", "function": {"name": "terminal"}}]}]
        self.assertEqual(_tool_names(msgs), {"x": "terminal"})


if __name__ == "__main__":
    unittest.main()
