#!/usr/bin/env python3
"""Tests for render_routine.py. Run with: python3 test_render_routine.py"""
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
import render_routine as rr  # noqa: E402
import routine_tools  # noqa: E402

ROOT = rr.PLUGIN_ROOT
EXAMPLE = os.path.join(ROOT, "templates", "profile.example.md")
TEMPLATE = os.path.join(ROOT, "templates", "routine-prompt.md")
REL = {"version": "9.9.9", "tag": "upwork-skills--v9.9.9", "repo": "https://github.com/example/upwork-skills"}
ALLOWED = [{"name": "Upwork", "match": "upwork", "allow": ["find_jobs", "get_profile"]}]
DRAFT = "---\nname: upwork-draft\ndescription: Use when drafting.\n---\n\n# Upwork draft\n\nOpen with their problem.\n"


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def between(text, begin, end):
    return text.split(begin + "\n", 1)[1].split(end, 1)[0]


class Windows(unittest.TestCase):
    def test_daily_list(self):
        self.assertEqual(rr.windows("0 9,14,18,22 * * *"), [
            "- fired between 09:00 and 14:00: screen posts since 22:00 the day before",
            "- fired between 14:00 and 18:00: screen posts since 09:00",
            "- fired between 18:00 and 22:00: screen posts since 14:00",
            "- fired between 22:00 and 09:00 the next day: screen posts since 18:00",
        ])

    def test_single_daily_time(self):
        self.assertEqual(rr.windows("30 6 * * *"),
                         ["- fired between 06:30 and 06:30 the next day: screen posts since 06:30 the day before"])

    def test_two_minutes_in_one_hour(self):
        self.assertEqual(rr.windows("0,30 9 * * *"), [
            "- fired between 09:00 and 09:30: screen posts since 09:30 the day before",
            "- fired between 09:30 and 09:00 the next day: screen posts since 09:00",
        ])

    def test_weekday_list(self):
        self.assertEqual(rr.windows("0 9 * * 1,4"), [
            "- fired between Mon 09:00 and Thu 09:00: screen posts since Thu 09:00 the week before",
            "- fired between Thu 09:00 and the next Mon 09:00: screen posts since Mon 09:00",
        ])

    def test_weekday_range_and_two_times(self):
        lines = rr.windows("0 9,18 * * 1-5")
        self.assertEqual(lines[0], "- fired between Mon 09:00 and Mon 18:00: screen posts since Fri 18:00 the week before")
        self.assertEqual(lines[1], "- fired between Mon 18:00 and Tue 09:00: screen posts since Mon 09:00")
        self.assertEqual(lines[2], "- fired between Tue 09:00 and Tue 18:00: screen posts since Mon 18:00")
        self.assertEqual(lines[9], "- fired between Fri 18:00 and the next Mon 09:00: screen posts since Fri 09:00")
        self.assertEqual(len(lines), 10)

    def test_seven_is_sunday(self):
        self.assertEqual(rr.windows("0 8 * * 7"),
                         ["- fired between Sun 08:00 and the next Sun 08:00: screen posts since Sun 08:00 the week before"])
        self.assertEqual(rr.windows("0 8 * * 0,7"), rr.windows("0 8 * * 0"))

    def test_every_hour_and_every_n_hours(self):
        self.assertEqual(rr.windows("0 */6 * * *"), [
            "- fired between 00:00 and 06:00: screen posts since 18:00 the day before",
            "- fired between 06:00 and 12:00: screen posts since 00:00",
            "- fired between 12:00 and 18:00: screen posts since 06:00",
            "- fired between 18:00 and 00:00 the next day: screen posts since 12:00",
        ])
        lines = rr.windows("15 * * * *")
        self.assertEqual(len(lines), 24)
        self.assertEqual(lines[0], "- fired between 00:15 and 01:15: screen posts since 23:15 the day before")
        self.assertEqual(rr.windows("0 */5 * * 1")[-1],
                         "- fired between Mon 20:00 and the next Mon 00:00: screen posts since Mon 15:00")

    def test_unsupported_crons(self):
        for expr in ("*/30 * * * *", "* 9 * * *", "0 */0 * * *", "0 9/2 * * *", "0 9 1 * *", "0 9 * 1 *",
                     "0 9 * * MON", "0 9 * *", "0 24 * * *", "60 9 * * *", "0 9 * * 8", "0 9-7 * * *",
                     "0 9,, * * *"):
            with self.assertRaises(rr.RenderError, msg=expr):
                rr.windows(expr)


class Drafting(unittest.TestCase):
    def test_no_draft_skill(self):
        self.assertEqual(rr.drafting(None), rr.NO_DRAFT)

    def test_front_matter_stripped_and_preface_added(self):
        text = rr.drafting(DRAFT)
        self.assertTrue(text.startswith(rr.DRAFT_PREFACE))
        body = between(text, rr.DRAFT_BEGIN, rr.DRAFT_END)
        self.assertEqual(body, "# Upwork draft\n\nOpen with their problem.\n")
        self.assertNotIn("description:", text)

    def test_byte_order_mark_and_no_front_matter(self):
        self.assertIn("# Upwork draft", rr.drafting("﻿" + DRAFT))
        self.assertNotIn("name:", rr.drafting("﻿" + DRAFT))
        self.assertIn("Just text.", rr.drafting("Just text.\n"))

    def test_unclosed_front_matter(self):
        with self.assertRaises(rr.RenderError):
            rr.drafting("---\nname: x\n# no closing line\n")

    def test_marker_inside_the_skill(self):
        with self.assertRaises(rr.RenderError):
            rr.drafting("text\n" + rr.DRAFT_END + "\n")


class Render(unittest.TestCase):
    def setUp(self):
        self.profile = read(EXAMPLE)
        self.prompt = rr.render(read(TEMPLATE), self.profile, REL, "0 9,14,18,22 * * *", ALLOWED, DRAFT)

    def test_every_slot_filled(self):
        self.assertNotIn("{{", self.prompt)
        self.assertNotIn("}}", self.prompt)

    def test_release_and_clone_line(self):
        self.assertIn("git clone --depth 1 --branch upwork-skills--v9.9.9 https://github.com/example/upwork-skills /tmp/upwork-skills", self.prompt)
        self.assertIn("upwork-skills 9.9.9", self.prompt)

    def test_profile_embedded_byte_for_byte(self):
        self.assertEqual(between(self.prompt, rr.PROFILE_BEGIN, rr.PROFILE_END), self.profile)
        self.assertTrue(self.prompt.rstrip("\n").endswith(rr.PROFILE_END))

    def test_profile_without_final_newline(self):
        prompt = rr.render("{{profile}}", "a: 1", REL, "0 9 * * *", ALLOWED)
        self.assertEqual(prompt, f"{rr.PROFILE_BEGIN}\na: 1\n{rr.PROFILE_END}")

    def test_profile_holding_a_marker(self):
        with self.assertRaises(rr.RenderError):
            rr.render("{{profile}}", "x\n" + rr.PROFILE_END + "\n", REL, "0 9 * * *", ALLOWED)

    def test_slot_text_in_the_profile_is_left_alone(self):
        prompt = rr.render("{{profile}}", "note: {{tag}}\n", REL, "0 9 * * *", ALLOWED)
        self.assertIn("note: {{tag}}", prompt)

    def test_run_stays_in_one_session(self):
        self.assertIn("Don't start subagents, forks or background tasks", self.prompt)
        self.assertIn("don't end your turn until the report is written", self.prompt)

    def test_read_posts_run_the_job_rules_in_one_batch(self):
        self.assertIn("python3 /tmp/upwork-skills/scripts/fixed_rules.py --jobs jobs --rows rows.json --out results", self.prompt)
        self.assertIn("--answers answers.json", self.prompt)
        self.assertIn("never from the row or the post alone", self.prompt)
        self.assertNotIn("--job job.json", self.prompt)

    def test_setup_resolves_the_home_directory(self):
        self.assertIn("echo $HOME", self.prompt)
        self.assertIn("$HOME/.config/upwork-skills/profile.md", self.prompt)

    def test_windows_drafting_and_tools(self):
        self.assertIn("- fired between 09:00 and 14:00: screen posts since 22:00 the day before", self.prompt)
        self.assertIn('the time after "since"', self.prompt)
        self.assertIn(rr.DRAFT_PREFACE, self.prompt)
        self.assertIn("- Upwork: find_jobs, get_profile", self.prompt)

    def test_without_a_draft_skill(self):
        prompt = rr.render(read(TEMPLATE), self.profile, REL, "0 9 * * *", ALLOWED)
        self.assertIn(rr.NO_DRAFT, prompt)
        self.assertNotIn(rr.DRAFT_BEGIN, prompt)

    def test_unknown_slot(self):
        with self.assertRaises(rr.RenderError):
            rr.render("{{nope}}", self.profile, REL, "0 9 * * *", ALLOWED)

    def test_shipped_tools_list(self):
        prompt = rr.render(read(TEMPLATE), self.profile, REL, "0 9 * * *", routine_tools.load_allowed())
        self.assertIn("- Upwork: find_jobs, get_profile, list_freelancer_proposals, get_freelancer_dashboard, get_tool_help", prompt)
        self.assertIn("- Google Sheets: get_values, append_values, update_values", prompt)


class Release(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        os.makedirs(os.path.join(self.dir, ".claude-plugin"))

    def write(self, manifest):
        with open(os.path.join(self.dir, ".claude-plugin", "plugin.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)

    def test_tag_from_name_and_version(self):
        self.write({"name": "upwork-skills", "version": "0.2.0", "repository": "https://github.com/x/y"})
        self.assertEqual(rr.release(self.dir), {"version": "0.2.0", "tag": "upwork-skills--v0.2.0", "repo": "https://github.com/x/y"})

    def test_missing_repository(self):
        self.write({"name": "upwork-skills", "version": "0.2.0"})
        with self.assertRaises(rr.RenderError):
            rr.release(self.dir)

    def test_repository_that_is_not_a_url(self):
        self.write({"name": "upwork-skills", "version": "0.2.0",
                    "repository": {"type": "git", "url": "https://github.com/x/y"}})
        with self.assertRaises(rr.RenderError) as caught:
            rr.release(self.dir)
        self.assertIn("repository must be a string", str(caught.exception))

    def test_shipped_manifest(self):
        rel = rr.release(ROOT)
        self.assertEqual(rel["tag"], f"upwork-skills--v{rel['version']}")
        self.assertTrue(rel["repo"].startswith("https://github.com/"))


class Main(unittest.TestCase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rr.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_prints_the_prompt(self):
        code, out, err = self.run_main("--cron", "0 9 * * 1,4", "--profile", EXAMPLE)
        self.assertEqual(code, 0, err)
        self.assertIn("- fired between Mon 09:00 and Thu 09:00: screen posts since Thu 09:00 the week before", out)
        self.assertIn(rr.NO_DRAFT, out)
        self.assertEqual(between(out, rr.PROFILE_BEGIN, rr.PROFILE_END), read(EXAMPLE))

    def test_with_a_draft_skill(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(DRAFT)
        self.addCleanup(os.remove, fh.name)
        code, out, _ = self.run_main("--cron", "0 9 * * *", "--profile", EXAMPLE, "--draft-skill", fh.name)
        self.assertEqual(code, 0)
        self.assertIn("Open with their problem.", out)

    def test_profile_with_a_byte_order_mark(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".md", delete=False) as fh:
            fh.write(codecs.BOM_UTF8 + read(EXAMPLE).encode("utf-8"))
        self.addCleanup(os.remove, fh.name)
        code, out, err = self.run_main("--cron", "0 9 * * *", "--profile", fh.name)
        self.assertEqual(code, 0, err)
        self.assertEqual(between(out, rr.PROFILE_BEGIN, rr.PROFILE_END), read(EXAMPLE))

    def test_bad_cron(self):
        code, out, err = self.run_main("--cron", "*/30 * * * *", "--profile", EXAMPLE)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("render_routine: cron minute", err)

    def test_missing_profile(self):
        code, _, err = self.run_main("--cron", "0 9 * * *", "--profile", "/nonexistent/profile.md")
        self.assertEqual(code, 2)
        self.assertIn("render_routine:", err)


if __name__ == "__main__":
    unittest.main()
