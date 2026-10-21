#!/usr/bin/env python3
"""Tests for bidlog.py. Run with: python3 test_bidlog.py"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bidlog  # noqa: E402

JOB = "2112569628814312909"
FACTS = {
    "job_id": JOB, "title": "Claude Code coach",
    "url": f"https://www.upwork.com/jobs/~02{JOB}?utm_campaign=x",
    "lane": "agent-tooling", "proposals_label": "12", "age_hours": 4.0, "connects_cost": 26,
    "client_hires": 19, "client_feedback_count": 15, "client_score": 5, "client_gives_avg": 5.0,
    "client_spend": 4436.24, "client_hire_rate": 63,
    "invites": 4, "interviews": 7, "hired": 0, "offered": None,
}
RESULT = {
    "verdict": "MAYBE", "facts": FACTS,
    "fired": [{"id": "unrelated-client-history", "effect": "MAYBE"}],
    "overridden": [{"id": "coaching-ask", "effect": "SKIP"}],
}
AT = "2026-10-21T14:05+05:00"


class Layout(unittest.TestCase):
    def test_columns_and_ranges(self):
        self.assertEqual(len(bidlog.COLUMNS), 30)
        self.assertEqual(bidlog.RANGES, {"screen": "A:T", "submit": "X:AA", "all": "A:AD"})
        self.assertEqual([bidlog.letter(i) for i in (0, 25, 26, 29)], ["A", "Z", "AA", "AD"])


class Rows(unittest.TestCase):
    def test_row_from_a_screen(self):
        row = bidlog.row_from_result(RESULT, AT)
        self.assertEqual(list(row), bidlog.COLUMNS)
        self.assertEqual(row["url"], f"https://www.upwork.com/jobs/~02{JOB}")
        self.assertEqual(row["reasons"], "MAYBE unrelated-client-history; override coaching-ask")
        self.assertEqual((row["offered"], row["rate"], row["client_spend"], row["hired"]), ("", "", 4436.24, 0))

    def test_pending_is_not_logged(self):
        with self.assertRaises(ValueError):
            bidlog.row_from_result(dict(RESULT, verdict="PENDING"), AT)


class Csv(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.csv = os.path.join(self.dir, "bids.csv")

    def test_rescreen_updates_screen_columns_and_keeps_the_rest(self):
        bidlog.upsert_csv(self.csv, bidlog.row_from_result(RESULT, AT))
        bidlog.update_csv(self.csv, JOB, {"rate": "40", "proposal_id": "1000000000000000001"})
        later = dict(RESULT, verdict="BID", fired=[], overridden=[])
        bidlog.upsert_csv(self.csv, bidlog.row_from_result(later, "2026-10-21T15:00+05:00"))
        rows = bidlog.read_csv(self.csv)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["verdict"], rows[0]["screened_at"], rows[0]["rate"], rows[0]["proposal_id"]),
                         ("BID", "2026-10-21T15:00+05:00", "40", "1000000000000000001"))

    def test_upsert_creates_the_log_folder(self):
        path = os.path.join(self.dir, "upwork", "bids.csv")
        bidlog.upsert_csv(path, bidlog.row_from_result(RESULT, AT))
        self.assertEqual([r["job_id"] for r in bidlog.read_csv(path)], [JOB])

    def test_another_job_appends(self):
        bidlog.upsert_csv(self.csv, bidlog.row_from_result(RESULT, AT))
        other = dict(RESULT, facts=dict(FACTS, job_id="1"))
        bidlog.upsert_csv(self.csv, bidlog.row_from_result(other, AT))
        self.assertEqual([r["job_id"] for r in bidlog.read_csv(self.csv)], [JOB, "1"])

    def test_update_refuses_unknown_columns_and_jobs(self):
        bidlog.upsert_csv(self.csv, bidlog.row_from_result(RESULT, AT))
        for job_id, changes in ((JOB, {"rat": "1"}), (JOB, {"job_id": "2"}), ("999", {"rate": "1"})):
            with self.assertRaises(ValueError, msg=(job_id, changes)):
                bidlog.update_csv(self.csv, job_id, changes)

    def test_foreign_header_is_refused(self):
        with open(self.csv, "w", encoding="utf-8") as fh:
            fh.write("a,b\n1,2\n")
        with self.assertRaises(ValueError):
            bidlog.read_csv(self.csv)


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.result = os.path.join(self.dir, "screen.json")
        with open(self.result, "w", encoding="utf-8") as fh:
            json.dump(RESULT, fh)
        self.csv = os.path.join(self.dir, "bids.csv")

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = bidlog.main(list(args))
        return code, out.getvalue()

    def test_row_prints_values_and_ranges(self):
        code, text = self.run_main("row", "--result", self.result, "--at", AT)
        data = json.loads(text)
        self.assertEqual((code, data["values"][1], data["ranges"]["submit"]), (0, JOB, "X:AA"))
        self.assertEqual(len(data["values"]), 30)

    def test_upsert_and_update(self):
        self.assertEqual(self.run_main("upsert", "--csv", self.csv, "--result", self.result, "--at", AT)[0], 0)
        self.assertEqual(self.run_main("update", "--csv", self.csv, "--job-id", JOB,
                                       "--set", "rate=85", "--set", "boost=0")[0], 0)
        row = bidlog.read_csv(self.csv)[0]
        self.assertEqual((row["rate"], row["boost"]), ("85", "0"))

    def test_bad_input_exits_2(self):
        self.assertEqual(self.run_main("update", "--csv", self.csv, "--job-id", JOB, "--set", "rate")[0], 2)
        self.assertEqual(self.run_main("update", "--csv", self.csv, "--job-id", JOB)[0], 2)
        self.assertEqual(self.run_main("row", "--result", "/nonexistent.json")[0], 2)


if __name__ == "__main__":
    unittest.main()
