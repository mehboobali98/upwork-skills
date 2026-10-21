#!/usr/bin/env python3
"""Tests for facts.py. Run with: python3 test_facts.py"""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import facts  # noqa: E402

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
NOW = facts.parse_time("2026-10-20T19:43:28.951Z")
COACH = "2112569628814312909"
GERMANY = "2112631294964854278"
EN_DASH = "\u2013"


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


def row(job_id):
    return {r["id"]: r for r in load("rows.json")}[job_id]


def lane_of(title, skills=()):
    return facts.build(row={"id": "1", "title": title, "skills": list(skills)}, settings=SETTINGS, now=NOW)["lane"]


class FromJob(unittest.TestCase):
    def test_coach_post(self):
        f = facts.build(job=load("job-coach.json"), row=row(COACH), settings=SETTINGS, now=NOW)
        self.assertEqual(f["job_id"], COACH)
        self.assertFalse(f["applied"])
        self.assertEqual((f["client_hires"], f["client_feedback_count"], f["client_score"]), (19, 15, 5))
        self.assertEqual((f["client_spend"], f["client_hire_rate"], f["client_jobs_posted"]), (4436.24, 63, 30))
        self.assertEqual((f["client_gives_avg"], f["client_gives_min"]), (5.0, 5))
        self.assertFalse(f["same_title_active"])
        self.assertEqual((f["invites"], f["interviews"], f["hired"], f["offered"]), (4, 7, 0, 0))
        self.assertEqual((f["connects_cost"], f["connects_balance"], f["balance_after"]), (26, 50, 24))
        self.assertEqual((f["hourly_min"], f["hourly_max"], f["full_time"]), (80, 130, False))
        self.assertEqual((f["proposals"], f["proposals_label"], f["age_hours"]), (54, "54", 4.0))
        self.assertEqual((f["lane"], f["lane_skip_at_proposals"]), ("agent-tooling", 50))
        self.assertEqual((f["unmet_qualifications"], f["unmet_qualification_count"]), ([], 0))
        self.assertEqual((f["location_excluded"], f["location_preferred_elsewhere"]), (False, False))
        self.assertEqual((f["rate_floor"], f["available_hours"], f["min_balance"]), (25, 20, 10))

    def test_client_with_no_history(self):
        f = facts.build(job=load("job-no-history.json"), settings=SETTINGS, now=NOW)
        self.assertEqual((f["client_hires"], f["client_feedback_count"], f["client_spend"]), (0, 0, 0.0))
        self.assertIsNone(f["client_score"])
        self.assertIsNone(f["client_hire_rate"])
        self.assertIsNone(f["client_gives_min"])
        self.assertFalse(f["same_title_active"])
        self.assertEqual((f["contract_type"], f["fixed_budget"], f["full_time"]), ("FIXED", 250.0, False))
        self.assertIsNone(f["age_hours"])
        self.assertEqual(f["lane"], "other")

    def test_full_time_post(self):
        f = facts.build(job=load("job-full-time.json"), settings=SETTINGS, now=NOW)
        self.assertTrue(f["full_time"])
        self.assertEqual((f["hourly_max"], f["client_gives_min"]), (20, 5))
        self.assertFalse(f["same_title_active"])

    def test_same_title_ignores_case_and_punctuation(self):
        job = load("job-coach.json")
        job["client_work_history"]["open"].append(
            {"title": "claude code coach for a 5 person dev team: hands-on, about 8 hrs/week, 3 months!"})
        self.assertTrue(facts.build(job=job, settings=SETTINGS, now=NOW)["same_title_active"])

    def test_scores_the_client_gave(self):
        job = load("job-coach.json")
        job["client_work_history"]["closed"][0]["feedback_score"] = 2
        f = facts.build(job=job, settings=SETTINGS, now=NOW)
        self.assertEqual((f["client_gives_min"], f["client_gives_avg"]), (2, 4.0))

    def test_preferred_qualifications(self):
        job = load("job-coach.json")
        job["preferred_qualifications"].update(min_job_success_score=90, min_earnings="$1k+", rising_talent=True)
        f = facts.build(job=job, settings=SETTINGS, now=NOW)
        self.assertEqual(f["unmet_qualifications"], ["Job Success Score 90%+", "$1,000+ earned", "Rising Talent"])
        self.assertEqual(f["unmet_qualification_count"], 3)

    def test_locations(self):
        def where(job, settings=SETTINGS):
            f = facts.build(job=job, settings=settings, now=NOW)
            return f["location_excluded"], f["location_preferred_elsewhere"]

        job = load("job-location.json")
        self.assertEqual(where(job), (False, True))
        job["preferred_locations"]["location_required"] = True
        self.assertEqual(where(job), (True, False))
        job["preferred_locations"]["countries"] = ["Poland", "pakistan"]
        self.assertEqual(where(job), (False, False))

    def test_location_that_cant_be_told(self):
        job = load("job-location.json")
        self.assertEqual(facts.build(job=job, settings=dict(SETTINGS, country=None), now=NOW)["location_excluded"], None)
        job["preferred_locations"] = {"countries": [], "regions": ["Europe"], "location_required": True}
        self.assertEqual(facts.build(job=job, settings=SETTINGS, now=NOW)["location_excluded"], None)


class FromRow(unittest.TestCase):
    def test_client_block_without_reviews_or_spend_means_none(self):
        f = facts.build(row=row(GERMANY), settings=SETTINGS, now=NOW)
        self.assertEqual((f["client_feedback_count"], f["client_spend"], f["client_score"]), (0, 0.0, None))
        self.assertEqual((f["proposals"], f["proposals_label"]), (20, "20 to 50"))
        self.assertEqual((f["fixed_budget"], f["contract_type"]), (250.0, "FIXED"))
        self.assertIsNone(f["client_hires"])

    def test_no_client_block_leaves_client_facts_unknown(self):
        f = facts.build(row={"id": "1", "title": "Rails bug"}, settings=SETTINGS, now=NOW)
        self.assertIsNone(f["client_feedback_count"])
        self.assertIsNone(f["client_spend"])
        self.assertFalse(f["applied"])
        self.assertEqual(f["lane"], "rails")

    def test_recommended_feed_rows_carry_hires(self):
        f = facts.build(row={"id": "1", "client": {"total_hires": 3, "total_reviews": 1}}, now=NOW)
        self.assertEqual(f["client_hires"], 3)
        self.assertIsNone(facts.build(row={"id": "1", "client": {"total_reviews": 1}}, now=NOW)["client_hires"])

    def test_dashboard_engagement_wording(self):
        self.assertTrue(facts.build(row={"id": "1", "engagement": "30+ hrs/week"}, now=NOW)["full_time"])
        self.assertFalse(facts.build(row={"id": "1", "engagement": "Less than 30 hrs/week"}, now=NOW)["full_time"])

    def test_job_response_wins_over_its_row(self):
        f = facts.build(job=load("job-coach.json"), row=dict(row(COACH), client={"total_reviews": 1}), now=NOW)
        self.assertEqual(f["client_feedback_count"], 15)


class Parsing(unittest.TestCase):
    def test_budgets(self):
        cases = {
            f"80.00{EN_DASH}130.00/hr": (80.0, 130.0, None),
            f"$80.00{EN_DASH}$130.00/hr": (80.0, 130.0, None),
            "$25.00+/hr": (25.0, None, None),
            "up to $30.00/hr": (None, 30.0, None),
            "$250.00": (None, None, 250.0),
            "$2,500.00": (None, None, 2500.0),
            None: (None, None, None),
        }
        for text, want in cases.items():
            self.assertEqual(facts.parse_budget(text), want, text)

    def test_money(self):
        self.assertEqual(facts.money("$4,436.24"), 4436.24)
        self.assertEqual(facts.money("$1k+"), 1000.0)
        self.assertEqual(facts.money("250.0"), 250.0)
        self.assertIsNone(facts.money("Any"))
        self.assertIsNone(facts.money(None))

    def test_times(self):
        base = facts.parse_time("2026-10-20T15:43:28Z")
        self.assertEqual(facts.parse_time("2026-10-20T15:43:28.951Z").microsecond, 951000)
        self.assertEqual(facts.parse_time("2026-10-20T20:43:28+05:00"), base)
        self.assertEqual(facts.parse_time("2026-10-20T20:43:28+0500"), base)
        self.assertEqual(facts.parse_time("2026-10-20T15:43Z"), base.replace(second=0))
        self.assertIsNone(facts.parse_time("yesterday"))
        self.assertIsNone(facts.parse_time("2026-13-40T00:00Z"))

    def test_tiers(self):
        for tier, low in facts.TIERS.items():
            self.assertEqual(facts.build(row={"id": "1", "proposals_tier": tier}, now=NOW)["proposals"], low)


class Lanes(unittest.TestCase):
    def test_title_terms_match_whole_words_and_plurals(self):
        self.assertEqual(lane_of("Need AI Agents built"), "agent-tooling")
        self.assertEqual(lane_of("Railsy thing"), "other")
        self.assertEqual(lane_of("Website fix", ["Claude Code"]), "agent-tooling")
        self.assertEqual(lane_of("Ruby on Rails app with Claude Code"), "rails")

    def test_named_lane(self):
        f = facts.build(row={"id": "1", "title": "Website fix"}, settings=SETTINGS, now=NOW, lane="rails")
        self.assertEqual((f["lane"], f["lane_skip_at_proposals"]), ("rails", 20))
        with self.assertRaises(ValueError):
            facts.build(row={"id": "1"}, settings=SETTINGS, now=NOW, lane="design")


class ScreenSkill(unittest.TestCase):
    def kept_keys(self):
        path = os.path.join(os.path.dirname(FIXTURES), "..", "skills", "screen", "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        listed = text.split("keeping only the keys the rules read:", 1)[1].split(", with", 1)[0]
        return re.findall(r"`(\w+)`", listed)

    def test_saved_job_keeps_every_key_the_rules_read(self):
        for name in ("job-location.json", "job-coach.json", "job-full-time.json", "job-no-history.json"):
            job = load(name)
            kept = {k: v for k, v in job.items() if k in self.kept_keys()}
            self.assertEqual(facts.build(job=kept, settings=SETTINGS, now=NOW),
                             facts.build(job=job, settings=SETTINGS, now=NOW), name)


if __name__ == "__main__":
    unittest.main()
