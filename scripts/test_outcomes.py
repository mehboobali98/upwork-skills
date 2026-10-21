#!/usr/bin/env python3
"""Tests for outcomes.py. Run with: python3 test_outcomes.py"""
import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bidlog  # noqa: E402
import outcomes  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "pipeline")
AT = "2026-10-22T14:05+05:00"


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


def with_status(resp, status, reason=None):
    resp = copy.deepcopy(resp)
    resp["data"]["vendorProposal"]["status"] = dict({"status": status}, **({"reason": reason} if reason else {}))
    return resp


def filled(hired, wanted):
    job = fixture("job-filled.json")
    post = job["data"]["marketplaceJobPosting"]
    post["activityStat"]["jobActivity"]["totalHired"] = hired
    post["contractTerms"]["personsToHire"] = wanted
    return job


def row(job, proposal="", outcome="", outcome_at="", **more):
    return dict(job_id=job, proposal_id=proposal, outcome=outcome, outcome_at=outcome_at, title=f"Job {job}", **more)


def sheet(*rows):
    """A get_values response for the log, trailing empty cells left off as Sheets does."""
    values = [list(bidlog.COLUMNS)]
    for r in rows:
        cells = [str(r.get(c, "")) for c in bidlog.COLUMNS]
        while cells and cells[-1] == "":
            cells.pop()
        values.append(cells)
    return {"range": "Upwork!A1:AD20", "values": values}


class Rules(unittest.TestCase):
    def derive(self, resp, job=None):
        return outcomes.derive(outcomes.proposal_facts(resp), outcomes.job_fill(job) if job else None)

    def test_stated_statuses_win_over_a_filled_post(self):
        for status, want in (("Hired", "hired"), ("Offered", "offer"), ("Withdrawn", "withdrawn"),
                             ("Declined", "declined")):
            resp = with_status(fixture("proposal-sent.json"), status)
            self.assertEqual(self.derive(resp, fixture("job-filled.json")),
                             (want, 1, f"status {status}", "modified"), status)

    def test_archived_reasons(self):
        self.assertEqual(self.derive(fixture("proposal-archived.json")),
                         ("expired", 2, "archived, reason 85 Job Posting Expired", "modified"))
        cancelled = with_status(fixture("proposal-sent.json"), "Archived", {"id": "41", "reason": "Project was cancelled"})
        self.assertEqual(self.derive(cancelled)[0], "cancelled")
        other = with_status(fixture("proposal-sent.json"), "Archived", {"id": "12", "reason": "Something new"})
        self.assertEqual(self.derive(other)[:3], ("closed", 2, "archived, reason 12 Something new"))
        bare = with_status(fixture("proposal-sent.json"), "Archived")
        self.assertEqual(self.derive(bare)[:3], ("closed", 2, "archived, reason ?"))

    def test_a_filled_post_is_lost_even_with_a_room(self):
        self.assertEqual(self.derive(fixture("proposal-activated.json"), fixture("job-filled.json")),
                         ("lost", 3, "totalHired 1 of personsToHire 1", "check"))

    def test_persons_to_hire_zero_counts_as_one(self):
        self.assertEqual(self.derive(fixture("proposal-sent.json"), filled(1, 0))[0], "lost")
        self.assertEqual(self.derive(fixture("proposal-sent.json"), filled(0, 0))[0], "sent")
        self.assertEqual(self.derive(fixture("proposal-sent.json"), filled(1, 2))[0], "sent")

    def test_interview(self):
        self.assertEqual(self.derive(fixture("proposal-activated.json"), fixture("job-open.json")),
                         ("interview", 4, "status Activated", "modified"))
        room = fixture("proposal-viewed.json")
        room["room_id"] = "room_0000"
        self.assertEqual(self.derive(room, fixture("job-open.json"))[:3], ("interview", 4, "a message room"))

    def test_viewed_and_sent(self):
        self.assertEqual(self.derive(fixture("proposal-viewed.json"), fixture("job-open.json")),
                         ("viewed", 5, "viewedByClient", "modified"))
        self.assertEqual(self.derive(fixture("proposal-sent.json"), fixture("job-open.json")),
                         ("sent", 6, "status Accepted", "created"))
        pending = with_status(fixture("proposal-sent.json"), "Pending")
        self.assertEqual(self.derive(pending)[0], "sent")

    def test_without_the_job_rule_3_is_skipped(self):
        self.assertEqual(self.derive(fixture("proposal-activated.json"))[0], "interview")

    def test_unknown_status(self):
        with self.assertRaises(outcomes.OutcomeError):
            self.derive(with_status(fixture("proposal-sent.json"), "Mystery"))

    def test_responses_of_the_wrong_kind(self):
        for bad in ({"data": {}}, [], {"data": []}, "x"):
            with self.assertRaises(outcomes.OutcomeError, msg=bad):
                outcomes.proposal_facts(bad)
        for bad in ({"data": {}}, {"data": {"marketplaceJobPosting": {}}}, []):
            with self.assertRaises(outcomes.OutcomeError, msg=bad):
                outcomes.job_fill(bad)


class Times(unittest.TestCase):
    def test_raw_value_then_display_value(self):
        self.assertEqual(outcomes._time({"displayValue": "x", "rawValue": "1792570061662"}), "2026-10-21T08:07Z")
        self.assertEqual(outcomes._time({"displayValue": "2026-10-21T08:07:41.662Z"}), "2026-10-21T08:07Z")
        self.assertEqual(outcomes._time({"displayValue": "2026-10-21T13:07:41+05:00", "rawValue": None}),
                         "2026-10-21T08:07Z")
        self.assertIsNone(outcomes._time({}))
        self.assertIsNone(outcomes._time(None))


class Guards(unittest.TestCase):
    def test_step(self):
        cases = [
            ("", "sent", "sent"), ("", "lost", "lost"), ("sent", "sent", None), ("viewed", "sent", None),
            ("viewed", "interview", "interview"), ("offer", "viewed", None), ("interview", "lost", "lost"),
            ("offer", "lost", "lost"), ("lost", "viewed", None), ("lost", "lost", None),
            ("lost", "offer", "offer"), ("lost", "hired", "hired"), ("lost", "expired", None),
            ("sent", "expired", "expired"),
        ]
        for current, new, want in cases:
            self.assertEqual(outcomes.step(current, new), want, (current, new))


class Rows(unittest.TestCase):
    def test_short_rows_padded_and_numbered_from_the_header(self):
        rows = outcomes.sheet_rows(sheet(row("1", "11", "sent"), row("2")))
        self.assertEqual([n for n, _ in rows], [2, 3])
        self.assertEqual((rows[0][1]["outcome"], rows[0][1]["notes"], rows[1][1]["proposal_id"]), ("sent", "", ""))
        self.assertEqual(list(rows[1][1]), bidlog.COLUMNS)

    def test_blank_rows_keep_the_numbering(self):
        data = sheet(row("1", "11", "sent"))
        data["values"] += [[], ["", "2", "Job 2"] + [""] * 21 + ["12", "", "", "sent"]]
        rows = outcomes.sheet_rows(data)
        self.assertEqual([(n, r["job_id"]) for n, r in rows], [(2, "1"), (3, ""), (4, "2")])
        self.assertEqual([t["row"] for t in outcomes.todo(rows)], [2, 4])

    def test_values_array_alone(self):
        self.assertEqual(len(outcomes.sheet_rows(sheet(row("1"))["values"])), 1)

    def test_bad_header_and_no_values(self):
        for bad in ({"values": [["a", "b"], ["1", "2"]]}, {"values": []}, {}, {"range": "Upwork!A1:AD1"}):
            with self.assertRaises(outcomes.OutcomeError, msg=bad):
                outcomes.sheet_rows(bad)

    def test_todo_lists_rows_whose_outcome_can_change(self):
        rows = outcomes.sheet_rows(sheet(
            row("1", "11"), row("2", "12", "sent"), row("3", "13", "interview"), row("4", "14", "lost"),
            row("5", "15", "expired"), row("6", "", "skipped"), row("7"), row("8", " 18 ", " Viewed "),
            row("9", "19", "Expired"),
        ))
        self.assertEqual(outcomes.todo(rows), [
            {"row": 2, "job_id": "1", "proposal_id": "11", "outcome": ""},
            {"row": 3, "job_id": "2", "proposal_id": "12", "outcome": "sent"},
            {"row": 4, "job_id": "3", "proposal_id": "13", "outcome": "interview"},
            {"row": 5, "job_id": "4", "proposal_id": "14", "outcome": "lost"},
            {"row": 9, "job_id": "8", "proposal_id": "18", "outcome": "viewed"},
        ])


class Decide(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.proposals = os.path.join(self.dir, "proposals")
        self.jobs = os.path.join(self.dir, "jobs")
        os.makedirs(self.proposals)
        os.makedirs(self.jobs)

    def put(self, folder, name, data):
        with open(os.path.join(folder, f"{name}.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def decide(self, *rows, listed=()):
        return outcomes.decide(outcomes.sheet_rows(sheet(*rows)), self.proposals, self.jobs, listed, AT)

    def test_changes_carry_cells_values_and_evidence(self):
        self.put(self.proposals, "11", fixture("proposal-viewed.json"))
        self.put(self.jobs, "1", fixture("job-open.json"))
        self.put(self.proposals, "13", fixture("proposal-sent.json"))
        self.put(self.jobs, "3", fixture("job-filled.json"))
        out = self.decide(row("1", "11", "sent"), row("2", "", "skipped"), row("3", "13"), row("4", "14", "expired"))
        self.assertEqual(out["changes"], [
            {"row": 2, "job_id": "1", "proposal_id": "11", "title": "Job 1", "from": "sent", "to": "viewed",
             "at": "2026-10-21T08:07Z", "evidence": "rule 5: viewedByClient", "cells": "AB2:AC2",
             "values": ["viewed", "2026-10-21T08:07Z"]},
            {"row": 4, "job_id": "3", "proposal_id": "13", "title": "Job 3", "from": "", "to": "lost",
             "at": AT, "evidence": "rule 3: totalHired 1 of personsToHire 1", "cells": "AB4:AC4",
             "values": ["lost", AT]},
        ])
        self.assertEqual((out["errors"], out["unlogged"], out["unchanged"]), ([], [], 0))

    def test_a_sent_row_gets_its_submit_time_once(self):
        self.put(self.proposals, "11", fixture("proposal-sent.json"))
        self.put(self.jobs, "1", fixture("job-open.json"))
        out = self.decide(row("1", "11", "sent"))
        self.assertEqual([(c["to"], c["at"]) for c in out["changes"]], [("sent", "2026-10-21T20:18Z")])
        out = self.decide(row("1", "11", "sent", "2026-10-22T01:18+05:00"))
        self.assertEqual((out["changes"], out["unchanged"]), ([], 1))

    def test_a_lost_row_moves_only_to_offer_or_hired(self):
        self.put(self.proposals, "11", fixture("proposal-activated.json"))
        self.put(self.jobs, "1", fixture("job-filled.json"))
        out = self.decide(row("1", "11", "lost"))
        self.assertEqual((out["changes"], out["unchanged"]), ([], 1))
        self.put(self.proposals, "11", with_status(fixture("proposal-activated.json"), "Offered"))
        out = self.decide(row("1", "11", "lost"))
        self.assertEqual([(c["from"], c["to"], c["at"]) for c in out["changes"]], [("lost", "offer", "2026-10-21T07:45Z")])

    def test_a_mangled_proposal_id_is_an_error(self):
        out = self.decide(row("1", "2.11300207842544E+18", "sent"))
        self.assertEqual(len(out["errors"]), 1)
        self.assertIn("isn't an Upwork ID", out["errors"][0]["error"])
        self.assertEqual(out["changes"], [])

    def test_a_capitalised_outcome_is_read_as_lower_case(self):
        self.put(self.proposals, "11", fixture("proposal-viewed.json"))
        self.put(self.jobs, "1", fixture("job-open.json"))
        out = self.decide(row("1", "11", "Interview"))
        self.assertEqual((out["changes"], out["unchanged"]), ([], 1))

    def test_no_move_back(self):
        self.put(self.proposals, "11", fixture("proposal-viewed.json"))
        self.put(self.jobs, "1", fixture("job-open.json"))
        out = self.decide(row("1", "11", "interview"))
        self.assertEqual((out["changes"], out["unchanged"]), ([], 1))

    def test_settled_rows_are_never_read(self):
        out = self.decide(row("1", "11", "expired"), row("2", "12", "hired"), row("3", "", "skipped"))
        self.assertEqual(out, {"changes": [], "errors": [], "unlogged": [], "unchanged": 0})

    def test_a_missing_proposal_is_an_error(self):
        out = self.decide(row("1", "11", "sent"))
        self.assertEqual(len(out["errors"]), 1)
        self.assertEqual(out["errors"][0]["row"], 2)
        self.assertTrue(out["errors"][0]["error"].startswith("proposal: "))
        self.assertEqual((out["changes"], out["unchanged"]), ([], 0))

    def test_a_missing_job_skips_rule_3_and_says_so(self):
        self.put(self.proposals, "11", fixture("proposal-viewed.json"))
        out = self.decide(row("1", "11", "sent"))
        self.assertEqual([c["to"] for c in out["changes"]], ["viewed"])
        self.assertEqual(len(out["errors"]), 1)
        self.assertTrue(out["errors"][0]["error"].startswith("job: "))
        self.assertTrue(out["errors"][0]["error"].endswith("; rule 3 not checked"))

    def test_an_archived_proposal_needs_no_job(self):
        self.put(self.proposals, "11", fixture("proposal-archived.json"))
        out = self.decide(row("1", "11", "sent"))
        self.assertEqual([(c["to"], c["at"]) for c in out["changes"]], [("expired", "2026-09-13T23:20Z")])
        self.assertEqual(out["errors"], [])

    def test_an_unknown_status_is_an_error(self):
        self.put(self.proposals, "11", with_status(fixture("proposal-sent.json"), "Mystery"))
        self.put(self.jobs, "1", fixture("job-open.json"))
        out = self.decide(row("1", "11", "sent"))
        self.assertEqual([e["error"] for e in out["errors"]], ["unknown proposal status 'Mystery'"])
        self.assertEqual(out["changes"], [])

    def test_check_time_defaults_to_now(self):
        self.put(self.proposals, "11", fixture("proposal-sent.json"))
        self.put(self.jobs, "1", fixture("job-filled.json"))
        out = outcomes.decide(outcomes.sheet_rows(sheet(row("1", "11", "sent"))), self.proposals, self.jobs)
        self.assertRegex(out["changes"][0]["at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[+-]\d{2}:\d{2}$")

    def test_unlogged_proposals(self):
        listed = fixture("listed-archived.json")
        out = self.decide(row("2000000000000000004", "1000000000000000004", "expired"),
                          row("2000000000000000008", "", "skipped"), listed=[listed, listed])
        self.assertEqual(out["unlogged"], [
            {"proposal_id": "1000000000000000009", "job_id": "2000000000000000009",
             "title": "Need a Ruby on Rails developer", "status": "Archived", "row": None},
            {"proposal_id": "1000000000000000008", "job_id": "2000000000000000008",
             "title": "Rails developer for a live platform", "status": "Archived", "row": 3},
        ])

    def test_a_listed_file_of_the_wrong_kind(self):
        with self.assertRaises(outcomes.OutcomeError):
            self.decide(row("1"), listed=[{"data": {}}])


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.proposals = os.path.join(self.dir, "proposals")
        self.jobs = os.path.join(self.dir, "jobs")
        os.makedirs(self.proposals)
        os.makedirs(self.jobs)
        for folder, name, data in ((self.proposals, "11", fixture("proposal-viewed.json")),
                                   (self.jobs, "1", fixture("job-open.json"))):
            with open(os.path.join(folder, f"{name}.json"), "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        self.rows = os.path.join(self.dir, "log.json")
        with open(self.rows, "w", encoding="utf-8") as fh:
            json.dump(sheet(row("1", "11", "sent"), row("2", "", "skipped")), fh)
        self.csv = os.path.join(self.dir, "bids.csv")
        full = [dict(dict.fromkeys(bidlog.COLUMNS, ""), **r) for r in
                (row("1", "11", "sent", verdict="BID", rate="85", notes="keep me"), row("2", "", "skipped"))]
        bidlog.write_csv(self.csv, full)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = outcomes.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def decide_args(self, *log):
        return ("decide", *log, "--proposals", self.proposals, "--jobs", self.jobs, "--at", AT)

    def test_todo(self):
        code, out, err = self.run_main("todo", "--rows", self.rows)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), [{"row": 2, "job_id": "1", "proposal_id": "11", "outcome": "sent"}])
        code, out, _ = self.run_main("todo", "--csv", self.csv)
        self.assertEqual((code, len(json.loads(out))), (0, 1))

    def test_decide_on_a_sheet_prints_the_changes(self):
        code, out, err = self.run_main(*self.decide_args("--rows", self.rows))
        self.assertEqual(code, 0, err)
        self.assertEqual([(c["cells"], c["values"]) for c in json.loads(out)["changes"]],
                         [("AB2:AC2", ["viewed", "2026-10-21T08:07Z"])])

    def test_apply_writes_only_the_outcome_columns(self):
        before = bidlog.read_csv(self.csv)
        code, _, err = self.run_main(*self.decide_args("--csv", self.csv), "--apply")
        self.assertEqual(code, 0, err)
        after = bidlog.read_csv(self.csv)
        self.assertEqual((after[0]["outcome"], after[0]["outcome_at"]), ("viewed", "2026-10-21T08:07Z"))
        for name in bidlog.COLUMNS:
            if name not in ("outcome", "outcome_at"):
                self.assertEqual(after[0][name], before[0][name], name)
        self.assertEqual(after[1], before[1])

    def test_a_second_run_changes_nothing(self):
        self.assertEqual(self.run_main(*self.decide_args("--csv", self.csv), "--apply")[0], 0)
        code, out, err = self.run_main(*self.decide_args("--csv", self.csv), "--apply")
        self.assertEqual(code, 0, err)
        self.assertEqual((json.loads(out)["changes"], json.loads(out)["unchanged"]), ([], 1))

    def test_apply_refuses_a_row_that_moved(self):
        changes = [{"row": 2, "job_id": "999", "to": "viewed", "at": AT}]
        with self.assertRaises(outcomes.OutcomeError):
            outcomes.apply_csv(self.csv, changes)
        with self.assertRaises(outcomes.OutcomeError):
            outcomes.apply_csv(self.csv, [{"row": 9, "job_id": "1", "to": "viewed", "at": AT}])

    def test_bad_input_exits_2(self):
        with open(self.rows, encoding="utf-8") as fh:
            before = fh.read()
        for args in (self.decide_args("--rows", self.rows) + ("--apply",),
                     ("decide", "--rows", self.rows, "--proposals", self.proposals, "--jobs", self.jobs, "--at", "soon"),
                     ("todo", "--csv", os.path.join(self.dir, "none.csv")),
                     ("todo", "--rows", os.path.join(self.dir, "none.json"))):
            code, out, err = self.run_main(*args)
            self.assertEqual((code, out), (2, ""), args)
            self.assertTrue(err.startswith("outcomes: "), err)
        with open(self.rows, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)


if __name__ == "__main__":
    unittest.main()
