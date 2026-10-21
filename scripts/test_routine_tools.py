#!/usr/bin/env python3
"""Tests for routine_tools.py. Run with: python3 test_routine_tools.py"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import routine_tools as rt  # noqa: E402

UPWORK = [f"mcp__claude_ai_Upwork__upwork__{t}" for t in (
    "find_jobs", "get_profile", "list_freelancer_proposals", "get_freelancer_dashboard",
    "get_tool_help", "manage_proposals", "boost_profile", "send_message")]
SHEETS = [f"mcp__claude_ai_Google_Sheets__{t}" for t in (
    "get_values", "append_values", "update_values", "batch_clear_values", "update_spreadsheet")]


class Names(unittest.TestCase):
    def test_server_tool(self):
        self.assertEqual(rt.server_tool("mcp__claude_ai_Upwork__upwork__find_jobs"), "upwork__find_jobs")
        self.assertEqual(rt.server_tool("mcp__claude_ai_Google_Sheets__get_values"), "get_values")
        self.assertEqual(rt.server_tool("  mcp__Upwork__upwork__find_jobs\n"), "upwork__find_jobs")

    def test_not_a_tool_name(self):
        for name in ("find_jobs", "mcp__Upwork", "mcp____find_jobs", "tool__Upwork__x"):
            with self.assertRaises(rt.ToolsError, msg=name):
                rt.server_tool(name)


class DenyList(unittest.TestCase):
    def setUp(self):
        self.entries = rt.load_allowed()

    def test_upwork(self):
        allow = rt.entry_for("Upwork", self.entries)["allow"]
        deny, missing = rt.deny_list("Upwork", UPWORK, allow)
        self.assertEqual(deny, [
            "mcp__Upwork__upwork__boost_profile",
            "mcp__Upwork__upwork__manage_proposals",
            "mcp__Upwork__upwork__send_message",
        ])
        self.assertEqual(missing, [])

    def test_sheets(self):
        allow = rt.entry_for("Google_Sheets", self.entries)["allow"]
        deny, _ = rt.deny_list("Google_Sheets", SHEETS, allow)
        self.assertEqual(deny, ["mcp__Google_Sheets__batch_clear_values", "mcp__Google_Sheets__update_spreadsheet"])

    def test_duplicates_and_blank_lines(self):
        deny, _ = rt.deny_list("Upwork", UPWORK + UPWORK + ["", "  "], ["find_jobs"])
        self.assertEqual(len(deny), len(set(deny)))
        self.assertEqual(len(deny), len(UPWORK) - 1)

    def test_allowed_tool_not_listed(self):
        _, missing = rt.deny_list("Upwork", UPWORK[:1], ["find_jobs", "get_profile"])
        self.assertEqual(missing, ["get_profile"])

    def test_connection_name(self):
        with self.assertRaises(rt.ToolsError):
            rt.deny_list("Google Sheets", SHEETS, ["get_values"])

    def test_no_matching_entry(self):
        with self.assertRaises(rt.ToolsError):
            rt.entry_for("Gmail", self.entries)


class Allowed(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, text):
        path = os.path.join(self.dir, "tools.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_shipped_file(self):
        names = [e["name"] for e in rt.load_allowed()]
        self.assertEqual(names, ["Upwork", "Google Sheets"])

    def test_bad_files(self):
        for text in ("connectors: []\n", "other: 1\n", "connectors:\n  - name: X\n    match: x\n"):
            with self.assertRaises(rt.ToolsError, msg=text):
                rt.load_allowed(self.write(text))


class Main(unittest.TestCase):
    def test_prints_json_and_warns(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as fh:
            fh.write("\n".join(UPWORK[:1] + UPWORK[5:]) + "\n")
        self.addCleanup(os.remove, fh.name)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rt.main(["--connection", "Upwork", fh.name])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue()), [
            "mcp__Upwork__upwork__boost_profile",
            "mcp__Upwork__upwork__manage_proposals",
            "mcp__Upwork__upwork__send_message",
        ])
        self.assertIn("get_profile is allowed but wasn't in the list", err.getvalue())

    def test_unknown_connection(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = rt.main(["--connection", "Gmail", os.devnull])
        self.assertEqual(code, 2)
        self.assertIn("routine_tools:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
