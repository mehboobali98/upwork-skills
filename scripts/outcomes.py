"""Track each logged bid to its outcome.

    outcomes.py todo (--rows log.json | --csv bids.csv)
    outcomes.py decide (--rows log.json | --csv bids.csv) --proposals DIR --jobs DIR
        [--listed FILE ...] [--at TIME] [--apply]

--rows is the Sheets get_values response for <tab>!A:AD, or its values
array; --csv is a log kept as a file. todo prints the rows whose outcome can
still change. decide reads each one's proposal (list_freelancer_proposals
action=get, saved as DIR/<proposal id>.json) and job (find_jobs action=get,
DIR/<job id>.json) and prints each outcome change with the cells to write.
--listed takes saved list_freelancer_proposals list responses and reports
the proposals the log has no row for. With --csv, --apply writes the changes.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bidlog  # noqa: E402
import facts  # noqa: E402

PROGRESS = ["sent", "viewed", "interview", "offer"]
TRACKED = {"", "lost", *PROGRESS}
STATUSES = {"Accepted", "Pending", "Activated", "Archived", "Hired", "Offered", "Withdrawn", "Declined"}
BY_STATUS = {"Hired": "hired", "Offered": "offer", "Withdrawn": "withdrawn", "Declined": "declined"}
ARCHIVED = {"85": "expired", "41": "cancelled"}


class OutcomeError(ValueError):
    pass


def sheet_rows(data):
    """(Sheet row number, row) pairs from a get_values response or its values array."""
    values = data.get("values") if isinstance(data, dict) else data
    if not isinstance(values, list) or not values:
        raise OutcomeError("no values: save the get_values response for <tab>!A:AD")
    if [str(c) for c in values[0]] != bidlog.COLUMNS:
        raise OutcomeError("the log's header doesn't match the bid log's columns")
    rows = []
    for n, cells in enumerate(values[1:], start=2):
        cells = ["" if c is None else str(c) for c in cells]
        cells += [""] * (len(bidlog.COLUMNS) - len(cells))
        rows.append((n, dict(zip(bidlog.COLUMNS, cells))))
    return rows


def csv_rows(path):
    if not os.path.exists(path):
        raise OutcomeError(f"{path}: there's no bid log there")
    return [(n, {c: row.get(c) or "" for c in bidlog.COLUMNS})
            for n, row in enumerate(bidlog.read_csv(path), start=2)]


def tracked(rows):
    """Rows with a proposal whose outcome can still change. Only lost is inferred, so it stays open."""
    return [(n, r) for n, r in rows if r["proposal_id"].strip() and _outcome(r) in TRACKED]


def _outcome(row):
    return row["outcome"].strip().lower()


def todo(rows):
    return [{"row": n, "job_id": r["job_id"].strip(), "proposal_id": r["proposal_id"].strip(),
             "outcome": _outcome(r)} for n, r in tracked(rows)]


def _time(stamp):
    """An auditDetails time as ISO 8601 UTC to the minute, or None."""
    stamp = stamp if isinstance(stamp, dict) else {}
    try:
        when = datetime.fromtimestamp(int(stamp.get("rawValue")) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        when = facts.parse_time(stamp.get("displayValue"))
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ") if when else None


def proposal_facts(resp):
    data = resp.get("data") if isinstance(resp, dict) else None
    p = data.get("vendorProposal") if isinstance(data, dict) else None
    if not isinstance(p, dict):
        raise OutcomeError("not a list_freelancer_proposals get response")
    status = p.get("status") or {}
    reason = status.get("reason") or {}
    audit = p.get("auditDetails") or {}
    return {
        "status": status.get("status"),
        "reason_id": str(reason.get("id") or ""),
        "reason": reason.get("reason") or "",
        "viewed": p.get("viewedByClient") is True,
        "room": bool(resp.get("room_id")),
        "created": _time(audit.get("createdDateTime")),
        "modified": _time(audit.get("modifiedDateTime")),
    }


def job_fill(resp):
    """(totalHired, personsToHire) from a find_jobs get response, whole or trimmed."""
    data = resp.get("data") if isinstance(resp, dict) else None
    post = data.get("marketplaceJobPosting") if isinstance(data, dict) else None
    if not isinstance(post, dict):
        raise OutcomeError("not a find_jobs get response")
    hired = ((post.get("activityStat") or {}).get("jobActivity") or {}).get("totalHired")
    wanted = (post.get("contractTerms") or {}).get("personsToHire")
    if not isinstance(hired, int) or not isinstance(wanted, int):
        raise OutcomeError("the job has no totalHired or personsToHire")
    return hired, wanted


def derive(p, fill):
    """(outcome, rule, detail, time source) from the first rule that matches."""
    s = p["status"]
    if s not in STATUSES:
        raise OutcomeError(f"unknown proposal status {s!r}")
    if s in BY_STATUS:
        return BY_STATUS[s], 1, f"status {s}", "modified"
    if s == "Archived":
        reason = f"reason {p['reason_id'] or '?'} {p['reason']}".strip()
        return ARCHIVED.get(p["reason_id"], "closed"), 2, f"archived, {reason}", "modified"
    if fill is not None and fill[0] >= max(fill[1], 1):
        return "lost", 3, f"totalHired {fill[0]} of personsToHire {fill[1]}", "check"
    if s == "Activated" or p["room"]:
        return "interview", 4, "status Activated" if s == "Activated" else "a message room", "modified"
    if p["viewed"]:
        return "viewed", 5, "viewedByClient", "modified"
    return "sent", 6, f"status {s}", "created"


def step(current, new):
    """The outcome to write over current, or None to leave the row."""
    if current == "lost":
        return new if new in ("offer", "hired") else None
    if new == current:
        return None
    if current in PROGRESS and new in PROGRESS and PROGRESS.index(new) < PROGRESS.index(current):
        return None
    return new


def unlogged(rows, listed):
    """Listed proposals the log has no row for, with the row of a logged job that lacks its proposal ID."""
    known = {r["proposal_id"].strip() for _, r in rows}
    open_jobs = {r["job_id"].strip(): n for n, r in rows if not r["proposal_id"].strip()}
    found = {}
    for resp in listed:
        data = resp.get("data") if isinstance(resp, dict) else None
        page = data.get("vendorProposals") if isinstance(data, dict) else None
        if not isinstance(page, dict):
            raise OutcomeError("--listed: not a list_freelancer_proposals list response")
        for edge in page.get("edges") or []:
            node = (edge or {}).get("node") or {}
            pid = str(node.get("id") or "")
            if not pid or pid in known or pid in found:
                continue
            job = node.get("marketplaceJobPosting") or {}
            jid = str(job.get("id") or "")
            found[pid] = {"proposal_id": pid, "job_id": jid, "title": (job.get("content") or {}).get("title"),
                          "status": (node.get("status") or {}).get("status"), "row": open_jobs.get(jid)}
    return list(found.values())


def decide(rows, proposals, jobs, listed=(), at=None):
    at = at or bidlog.now()
    first, last = bidlog.RANGES["pipeline"].split(":")
    out = {"changes": [], "errors": [], "unlogged": unlogged(rows, listed), "unchanged": 0}
    for n, row in tracked(rows):
        pid, jid = row["proposal_id"].strip(), row["job_id"].strip()
        ref = {"row": n, "job_id": jid, "proposal_id": pid}
        if not pid.isdigit():
            out["errors"].append({**ref, "error": f"proposal_id {pid!r} isn't an Upwork ID; store it as text"})
            continue
        try:
            p = proposal_facts(_read(os.path.join(proposals, f"{pid}.json")))
        except (OSError, ValueError) as e:
            out["errors"].append({**ref, "error": f"proposal: {e}"})
            continue
        try:
            fill, job_error = job_fill(_read(os.path.join(jobs, f"{jid}.json"))), None
        except (OSError, ValueError) as e:
            fill, job_error = None, str(e)
        try:
            new, rule, detail, source = derive(p, fill)
        except OutcomeError as e:
            out["errors"].append({**ref, "error": str(e)})
            continue
        if job_error and rule >= 3:
            out["errors"].append({**ref, "error": f"job: {job_error}; rule 3 not checked"})
        current = _outcome(row)
        to = step(current, new)
        if to is None and new == current == "sent" and not row["outcome_at"].strip():
            to = "sent"
        if to is None:
            out["unchanged"] += 1
            continue
        when = at if source == "check" else (p[source] or at)
        out["changes"].append({**ref, "title": row["title"], "from": current, "to": to, "at": when,
                               "evidence": f"rule {rule}: {detail}", "cells": f"{first}{n}:{last}{n}",
                               "values": [to, when]})
    return out


def apply_csv(path, changes):
    rows = bidlog.read_csv(path)
    for c in changes:
        i = c["row"] - 2
        if not 0 <= i < len(rows) or rows[i]["job_id"] != c["job_id"]:
            raise OutcomeError(f"row {c['row']} isn't job {c['job_id']} any more; run decide again")
        rows[i].update({"outcome": c["to"], "outcome_at": c["at"]})
    bidlog.write_csv(path, rows)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Track each logged bid to its outcome.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("todo", "decide"):
        cmd = sub.add_parser(name)
        log = cmd.add_mutually_exclusive_group(required=True)
        log.add_argument("--rows", help="the Sheets get_values response for <tab>!A:AD")
        log.add_argument("--csv", help="the bid log, kept as a CSV")
        if name == "decide":
            cmd.add_argument("--proposals", required=True, help="a directory of <proposal id>.json get responses")
            cmd.add_argument("--jobs", required=True, help="a directory of <job id>.json find_jobs get responses")
            cmd.add_argument("--listed", action="append", default=[], help="a saved list response; repeatable")
            cmd.add_argument("--at", help="the check's time, ISO 8601 (default: now)")
            cmd.add_argument("--apply", action="store_true", help="with --csv, write the changes")
    args = ap.parse_args(argv)
    try:
        rows = csv_rows(os.path.expanduser(args.csv)) if args.csv else sheet_rows(_read(args.rows))
        if args.cmd == "todo":
            print(json.dumps(todo(rows), indent=2))
            return 0
        if args.apply and not args.csv:
            raise OutcomeError("--apply writes a CSV log; write a Sheet's changes with the Sheets connector")
        if args.at and facts.parse_time(args.at) is None:
            raise OutcomeError(f"--at {args.at!r} isn't an ISO time")
        out = decide(rows, args.proposals, args.jobs, [_read(f) for f in args.listed], args.at)
        if args.apply:
            apply_csv(os.path.expanduser(args.csv), out["changes"])
        print(json.dumps(out, indent=2))
        return 0
    except (OSError, ValueError) as e:
        print(f"outcomes: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
