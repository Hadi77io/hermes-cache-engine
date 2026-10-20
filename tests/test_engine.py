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

    def _payload(self, tool_body, mode):
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
        payload = self._payload(big(), "report")
        before = json.dumps(payload, sort_keys=True)
        CacheEngine(settings(self.tmp, "report")).on_llm_request(payload)
        self.assertEqual(before, json.dumps(payload, sort_keys=True))

    def test_enforce_clips_only_after_last_user_message(self):
        payload = self._payload(big(), "enforce")
        CacheEngine(settings(self.tmp, "enforce")).on_llm_request(payload)
        msgs = payload["messages"]
        self.assertEqual(msgs[2]["content"], "prefix body " * 10)  # cached prefix untouched
        self.assertIn("omitted", msgs[5]["content"])
        self.assertLess(len(msgs[5]["content"]), len(big()))

    def test_stats_are_written(self):
        payload = self._payload(big(), "report")
        engine = CacheEngine(settings(self.tmp, "report"))
        engine.on_llm_request(payload)
        self.assertGreater(engine.total_saved(), 0)

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
