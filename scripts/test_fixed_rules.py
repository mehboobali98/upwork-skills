#!/usr/bin/env python3
"""Tests for fixed_rules.py. Run with: python3 test_fixed_rules.py"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import facts  # noqa: E402
import fixed_rules  # noqa: E402
import profile_loader  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SETTINGS = {
    "country": "Pakistan",
    "lanes": [
        {"name": "rails", "title_terms": ["Rails", "Ruby"], "skills": ["Ruby on Rails"], "skip_at_proposals": 20},
        {"name": "agent-tooling", "title_terms": ["Claude Code", "AI agent"], "skills": ["Claude Code"], "skip_at_proposals": 50},
    ],
    "rates": {"floor_hourly": 25},
    "availability": {"hours_per_week": 20},
    "connects": {"min_balance": 10},
    "qualifications": {"job_success_score": 0, "hours_worked": 0, "earnings": 0, "rising_talent": False},
}
PROFILE = """---
country: Pakistan
lanes:
  - name: agent-tooling
    title_terms: [Claude Code]
    skip_at_proposals: 50
rates:
  floor_hourly: 25
availability:
  hours_per_week: 20
connects:
  min_balance: 10
---
"""
NOW = facts.parse_time("2026-10-20T19:43:28.951Z")
RULES = profile_loader.load_rules()
COACH = "2112569628814312909"
ANSWERS = {
    "coaching-ask": {"answer": True, "why": "A team wants a Claude Code coach."},
    "coaching-ask.override": {"answer": True, "why": "8 paid hours a week for 12 weeks, six listed outcomes."},
    "unbounded-scope": {"answer": 4, "why": "Six concrete outcomes after 12 weeks."},
    "client-red-flags": {"answer": False, "why": "Every review is 5 stars."},
    "outside-experience": {"answer": False, "why": "Claude Code setup and skills."},
    "unrelated-client-history": {"answer": True, "why": "Word templates, Excel and AutoCAD."},
    "unpaid-sample": {"answer": False, "why": "The trial is paid."},
}


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


def coach_row(proposals=12):
    row = {r["id"]: r for r in load("rows.json")}[COACH]
    return dict(row, proposal_count=proposals)


def coach_facts(proposals=12, **changes):
    f = facts.build(job=load("job-coach.json"), row=coach_row(proposals), settings=SETTINGS, now=NOW)
    f.update(changes)
    return f


def ids(entries):
    return [e["id"] for e in entries]


class Verdicts(unittest.TestCase):
    def test_judgement_questions_come_back_until_answered(self):
        out = fixed_rules.screen(RULES, coach_facts())
        self.assertEqual((out["verdict"], out["fired"], out["unknown"]), ("PENDING", [], []))
        self.assertEqual(ids(out["pending"]), [
            "coaching-ask", "coaching-ask.override", "unbounded-scope", "client-red-flags",
            "outside-experience", "unrelated-client-history", "unpaid-sample"])

    def test_answered_coach_post_is_a_maybe_with_its_override(self):
        out = fixed_rules.screen(RULES, coach_facts(), ANSWERS)
        self.assertEqual(out["verdict"], "MAYBE")
        self.assertEqual(ids(out["fired"]), ["unrelated-client-history"])
        self.assertEqual(ids(out["overridden"]), ["coaching-ask"])
        self.assertEqual(out["overridden"][0]["why"], ANSWERS["coaching-ask.override"]["why"])
        self.assertEqual(out["pending"], [])

    def test_missing_override_answer_stays_pending(self):
        answers = {k: v for k, v in ANSWERS.items() if k != "coaching-ask.override"}
        out = fixed_rules.screen(RULES, coach_facts(), answers)
        self.assertEqual((out["verdict"], ids(out["pending"])), ("PENDING", ["coaching-ask.override"]))

    def test_big_client_skips_the_coaching_question(self):
        out = fixed_rules.screen(RULES, coach_facts(client_spend=545000.0, client_feedback_count=65))
        self.assertNotIn("coaching-ask", ids(out["pending"]))
        self.assertEqual(ids(out["overridden"]), ["coaching-ask"])

    def test_fixed_skip_needs_no_answers(self):
        f = facts.build(job=load("job-no-history.json"), settings=SETTINGS, now=NOW)
        out = fixed_rules.screen(RULES, f)
        self.assertEqual(out["verdict"], "SKIP")
        self.assertEqual([e["id"] for e in out["fired"] if e["effect"] == "SKIP"],
                         ["client-never-hired", "client-never-reviews"])
        self.assertEqual(ids(out["unknown"]), ["harsh-rater", "dead-post", "crowded"])
        self.assertEqual(out["pending"], [])

    def test_report_keeps_one_full_stop_after_a_reason(self):
        answers = dict(ANSWERS)
        answers["outside-experience"] = {"answer": True, "why": "Needs vector infrastructure."}
        out = fixed_rules.result(RULES, coach_facts(), answers)
        self.assertIn("SKIP outside-experience: Needs vector infrastructure. A proposal", fixed_rules.render(out))

    def test_full_time_rule_follows_the_profile(self):
        f = facts.build(job=load("job-full-time.json"), settings=SETTINGS, now=NOW)
        out = fixed_rules.screen(RULES, f)
        self.assertEqual(out["verdict"], "SKIP")
        self.assertEqual({e["id"]: e["effect"] for e in out["fired"]},
                         {"rate-below-floor": "SKIP", "full-time": "SKIP", "off-lane": "MAYBE"})
        relaxed = profile_loader.load_rules({"rule_overrides": {"full-time": {"effect": "MAYBE", "reason": "His call."}}})
        out = fixed_rules.screen(relaxed, f)
        self.assertEqual({e["id"]: e["effect"] for e in out["fired"]},
                         {"rate-below-floor": "SKIP", "full-time": "MAYBE", "off-lane": "MAYBE"})

    def test_crowded_uses_the_lane_limit_and_tiers(self):
        self.assertIn("crowded", ids(fixed_rules.screen(RULES, coach_facts(proposals=50), ANSWERS)["fired"]))
        self.assertNotIn("crowded", ids(fixed_rules.screen(RULES, coach_facts(proposals=49), ANSWERS)["fired"]))
        for tier, crowded in (("20 to 50", True), ("15 to 20", False)):
            f = facts.build(row={"id": "9", "title": "Fix a Rails upgrade", "proposals_tier": tier}, settings=SETTINGS, now=NOW)
            self.assertEqual("crowded" in ids(fixed_rules.screen(RULES, f)["fired"]), crowded, tier)

    def test_low_hire_rate_spares_prolific_hirers(self):
        out = fixed_rules.screen(RULES, coach_facts(client_hire_rate=23, client_hires=217), ANSWERS)
        self.assertIn("low-hire-rate", ids(out["overridden"]))
        out = fixed_rules.screen(RULES, coach_facts(client_hire_rate=23, client_hires=40), ANSWERS)
        self.assertIn("low-hire-rate", ids(out["fired"]))

    def test_notes_do_not_change_the_verdict(self):
        answers = dict(ANSWERS)
        answers["unrelated-client-history"] = {"answer": False, "why": "Software work."}
        answers["unpaid-sample"] = {"answer": True, "why": "Asks for a sample recording."}
        out = fixed_rules.screen(RULES, coach_facts(), answers)
        self.assertEqual((out["verdict"], ids(out["notes"])), ("BID", ["unpaid-sample"]))

    def test_bad_answers(self):
        bad = [
            {"coaching-askk": {"answer": True}},
            {"unbounded-scope": {"answer": 7}},
            {"unbounded-scope": {"answer": 3.5}},
            {"coaching-ask": {"answer": "yes"}},
            {"coaching-ask": True},
            {"coaching-ask": {"answer": True}, "coaching-ask.override": {"answer": "yes"}},
        ]
        for answers in bad:
            with self.assertRaises(fixed_rules.ScreenError, msg=answers):
                fixed_rules.screen(RULES, coach_facts(), answers)


class FirstPass(unittest.TestCase):
    def test_rows(self):
        rows = load("rows.json")
        out = fixed_rules.first_pass(RULES, rows + rows[:1], SETTINGS, facts.parse_time("2026-10-20T20:00:00Z"))
        self.assertEqual([(r["job_id"], r["verdict"]) for r in out], [
            (COACH, "SKIP"), ("2112562681382316976", "READ"),
            ("2112473844631677510", "SKIP"), ("2112631294964854278", "SKIP")])
        self.assertEqual(out[0]["skipped_by"], ["crowded"])
        self.assertEqual(out[2]["skipped_by"], ["rate-below-floor", "full-time"])
        self.assertEqual(out[3]["skipped_by"], ["already-applied", "client-never-hired", "client-never-reviews"])

    def test_rows_without_an_id_are_all_kept(self):
        rows = load("rows.json")
        bare = [{k: v for k, v in row.items() if k != "id"} for row in rows[:2]]
        out = fixed_rules.first_pass(RULES, bare + rows[2:], SETTINGS, facts.parse_time("2026-10-20T20:00:00Z"))
        self.assertEqual([r["job_id"] for r in out], [None, None, "2112473844631677510", "2112631294964854278"])


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.profile = self.path("profile.md", PROFILE)

    def path(self, name, content):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content if isinstance(content, str) else json.dumps(content))
        return path

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = fixed_rules.main(["--profile", self.profile, *args])
        return code, out.getvalue()

    def test_job_as_json(self):
        code, text = self.run_main("--job", self.path("job.json", load("job-no-history.json")), "--json")
        self.assertEqual((code, json.loads(text)["verdict"]), (0, "SKIP"))

    def test_job_as_text(self):
        code, text = self.run_main("--job", self.path("job.json", load("job-no-history.json")))
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith("SKIP  Review of unfinished portfolio website"))
        self.assertIn("  SKIP client-never-reviews: client_feedback_count 0 == 0.", text)

    def test_answers_and_now(self):
        code, text = self.run_main(
            "--job", self.path("job.json", load("job-coach.json")),
            "--row", self.path("row.json", coach_row()),
            "--answers", self.path("answers.json", ANSWERS),
            "--now", "2026-10-20T19:43:28.951Z", "--json")
        out = json.loads(text)
        self.assertEqual((code, out["verdict"], out["facts"]["age_hours"]), (0, "MAYBE", 4.0))

    def test_rows(self):
        code, text = self.run_main("--rows", self.path("rows.json", load("rows.json")), "--json")
        self.assertEqual((code, len(json.loads(text))), (0, 4))

    def test_rows_take_no_job_options(self):
        rows = self.path("rows.json", load("rows.json"))
        for extra in (["--answers", self.path("answers.json", ANSWERS)], ["--lane", "rails"],
                      ["--row", self.path("row.json", coach_row())]):
            with self.assertRaises(SystemExit, msg=extra) as caught:
                self.run_main("--rows", rows, *extra)
            self.assertEqual(caught.exception.code, 2)

    def test_errors_exit_2(self):
        self.assertEqual(self.run_main("--job", "/nonexistent.json")[0], 2)
        self.assertEqual(self.run_main("--job", self.path("bad.json", "{"))[0], 2)
        self.assertEqual(self.run_main("--job", self.path("job.json", load("job-coach.json")), "--now", "soon")[0], 2)


if __name__ == "__main__":
    unittest.main()
