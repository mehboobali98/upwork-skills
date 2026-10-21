#!/usr/bin/env python3
"""Tests for profile_loader.py. Run with: python3 test_profile_loader.py"""
import codecs
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_loader  # noqa: E402

EXAMPLE = os.path.join(profile_loader.PLUGIN_ROOT, "templates", "profile.example.md")


class FrontMatter(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, text):
        path = os.path.join(self.dir, "profile.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_split(self):
        self.assertEqual(profile_loader.split_front_matter("---\na: 1\n---\n# Body\n"), ("a: 1\n", "# Body\n"))

    def test_missing_lines(self):
        for text in ("a: 1\n", "---\na: 1\n"):
            with self.assertRaises(profile_loader.ProfileError, msg=text):
                profile_loader.split_front_matter(text)

    def test_errors_name_the_file_and_line(self):
        path = self.write("---\na: 1\na: 2\n---\nbody\n")
        with self.assertRaises(profile_loader.ProfileError) as caught:
            profile_loader.load_profile(path)
        self.assertIn("line 3", str(caught.exception))
        self.assertIn(path, str(caught.exception))

    def test_default_path(self):
        old = os.environ.pop("UPWORK_PROFILE", None)
        try:
            self.assertTrue(profile_loader.default_path().endswith(os.path.join(".config", "upwork-skills", "profile.md")))
            os.environ["UPWORK_PROFILE"] = "/tmp/p.md"
            self.assertEqual(profile_loader.default_path(), "/tmp/p.md")
        finally:
            os.environ.pop("UPWORK_PROFILE", None)
            if old is not None:
                os.environ["UPWORK_PROFILE"] = old

    def test_lane_settings_are_checked(self):
        bad = [
            "lanes:\n  - skills: [x]\n",
            "lanes:\n  - name: a\n  - name: a\n",
            "lanes:\n  - name: other\n",
            "lanes:\n  - name: a\n    skip_at_proposals: 0\n",
            "lanes:\n  - name: a\n    title_terms: Rails\n",
        ]
        for settings in bad:
            with self.assertRaises(profile_loader.ProfileError, msg=settings):
                profile_loader.load_profile(self.write(f"---\n{settings}---\n"))

    def test_byte_order_mark_is_ignored(self):
        path = os.path.join(self.dir, "profile.md")
        with open(EXAMPLE, "rb") as src, open(path, "wb") as fh:
            fh.write(codecs.BOM_UTF8 + src.read())
        self.assertEqual(profile_loader.load_profile(path)["settings"]["country"], "Portugal")

    def test_rule_settings_are_checked(self):
        bad = [
            'rates:\n  floor_hourly: "$25"\n',
            "availability:\n  hours_per_week: twenty\n",
            "connects:\n  min_balance: true\n",
            "qualifications:\n  job_success_score: 90%\n",
            "qualifications:\n  rising_talent: no thanks\n",
            "rates: 25\n",
            "country: 7\n",
        ]
        for settings in bad:
            with self.assertRaises(profile_loader.ProfileError, msg=settings):
                profile_loader.load_profile(self.write(f"---\n{settings}---\n"))

    def test_string_threshold_is_named(self):
        with self.assertRaises(profile_loader.ProfileError) as caught:
            profile_loader.load_profile(self.write('---\nrates:\n  floor_hourly: "$25"\n---\n'))
        self.assertIn("rates.floor_hourly must be a number, not '$25'", str(caught.exception))


class Rules(unittest.TestCase):
    def test_defaults_load_and_are_unique(self):
        rules = profile_loader.load_rules()
        ids = [r["id"] for r in rules]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("coaching-ask", ids)
        self.assertTrue(all(r["reason"] for r in rules))

    def test_profile_changes_a_rule(self):
        rules = profile_loader.load_rules({"rule_overrides": {"full-time": {"effect": "MAYBE", "reason": "His call."}}})
        rule = next(r for r in rules if r["id"] == "full-time")
        self.assertEqual((rule["effect"], rule["reason"], rule["kind"]), ("MAYBE", "His call.", "fixed"))

    def test_profile_switches_a_rule_off(self):
        ids = [r["id"] for r in profile_loader.load_rules({"rule_overrides": {"off-lane": {"off": True}}})]
        self.assertNotIn("off-lane", ids)

    def test_profile_replaces_a_threshold(self):
        rules = profile_loader.load_rules({"rule_overrides": {"low-client-rating": {"check": ["client_score", "<", 4.5]}}})
        self.assertEqual(next(r for r in rules if r["id"] == "low-client-rating")["check"], ["client_score", "<", 4.5])

    def test_bad_changes_are_refused(self):
        bad = [
            {"no-such-rule": {"off": True}},
            {"full-time": {"kind": "judgement"}},
            {"full-time": {"effect": "BLOCK"}},
            {"full-time": {"check": ["clinet_hires", "==", 0]}},
            {"coaching-ask": {"fires_when": "yes"}},
            {"unbounded-scope": {"fires_when": ["<=", "two"]}},
            {"low-hire-rate": {"override": {"reason": "no condition"}}},
            {"full-time": {}},
        ]
        for change in bad:
            with self.assertRaises(profile_loader.ProfileError, msg=change):
                profile_loader.load_rules({"rule_overrides": change})

    def test_override_can_be_removed(self):
        rules = profile_loader.load_rules({"rule_overrides": {"low-hire-rate": {"override": None}}})
        self.assertIsNone(next(r for r in rules if r["id"] == "low-hire-rate")["override"])

    def test_example_profile_loads(self):
        profile = profile_loader.load_profile(EXAMPLE)
        profile_loader.load_rules(profile["settings"])
        self.assertIn("Allowed claims", profile["body"])
        self.assertEqual(profile["settings"]["org_uid"], "0000000000000000000")


class Cli(unittest.TestCase):
    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = profile_loader.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_check(self):
        code, out, _ = self.run_main("--profile", EXAMPLE, "--check")
        self.assertEqual(code, 0)
        self.assertIn("profile OK", out)
        self.assertIn("lanes: django, data", out)

    def test_settings(self):
        code, out, _ = self.run_main("--profile", EXAMPLE, "--settings")
        self.assertEqual((code, json.loads(out)["log"]["type"]), (0, "csv"))

    def test_missing_profile(self):
        code, _, err = self.run_main("--profile", "/nonexistent/profile.md", "--check")
        self.assertEqual(code, 2)
        self.assertIn("profile_loader:", err)


if __name__ == "__main__":
    unittest.main()
