"""Bid log rows: one per BID or MAYBE, kept in a Google Sheet tab or a CSV.

    bidlog.py row --result screen.json [--at TIME]
    bidlog.py upsert --csv bids.csv --result screen.json [--at TIME]
    bidlog.py update --csv bids.csv --job-id ID --set rate=40 --set proposal_id=2112...

row prints the columns, values and Sheet ranges for the Sheets connector to
write; upsert and update keep a CSV for a log without a Sheet. A re-screened
post updates its row's screen columns and keeps what submit and pipeline wrote.
"""
import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import datetime

COLUMNS = [
    "screened_at", "job_id", "title", "url", "lane", "verdict", "reasons",
    "proposals_at_screen", "age_hours", "connects_cost",
    "client_hires", "client_feedback_count", "client_score", "client_gives_avg",
    "client_spend", "client_hire_rate",
    "invites", "interviews", "hired", "offered",
    "jev_lane", "jev_scope", "jev_flags",
    "rate", "proposal_id", "submitted_at", "boost",
    "outcome", "outcome_at", "notes",
]
SCREEN = COLUMNS[: COLUMNS.index("offered") + 1]
FROM_FACTS = [
    "client_hires", "client_feedback_count", "client_score", "client_gives_avg",
    "client_spend", "client_hire_rate", "invites", "interviews", "hired", "offered",
]


def letter(index):
    name, index = "", index + 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


RANGES = {
    "screen": f"A:{letter(len(SCREEN) - 1)}",
    "submit": f"{letter(COLUMNS.index('rate'))}:{letter(COLUMNS.index('outcome_at'))}",
    "pipeline": f"{letter(COLUMNS.index('outcome'))}:{letter(COLUMNS.index('outcome_at'))}",
    "all": f"A:{letter(len(COLUMNS) - 1)}",
}


def row_from_result(out, at):
    if out.get("verdict") not in ("BID", "MAYBE", "SKIP"):
        raise ValueError("answer the screen's pending questions before logging it")
    f = out["facts"]
    reasons = [f"{e['effect']} {e['id']}" for e in out["fired"]]
    reasons += [f"override {e['id']}" for e in out["overridden"]]
    row = dict.fromkeys(COLUMNS)
    row.update({
        "screened_at": at, "job_id": f["job_id"], "title": f["title"],
        "url": (f["url"] or "").split("?")[0], "lane": f["lane"], "verdict": out["verdict"],
        "reasons": "; ".join(reasons), "proposals_at_screen": f["proposals_label"],
        "age_hours": f["age_hours"], "connects_cost": f["connects_cost"],
    })
    row.update({name: f[name] for name in FROM_FACTS})
    return {k: ("" if v is None else v) for k, v in row.items()}


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"{path}: its header doesn't match the bid log's columns")
        return list(reader)


def write_csv(path, rows):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def upsert_csv(path, row):
    rows = read_csv(path)
    for existing in rows:
        if existing["job_id"] == str(row["job_id"]):
            existing.update({name: row[name] for name in SCREEN})
            break
    else:
        rows.append(dict(row))
    write_csv(path, rows)


def update_csv(path, job_id, changes):
    bad = sorted((set(changes) - set(COLUMNS)) | ({"job_id"} & set(changes)))
    if bad:
        raise ValueError(f"can't set {', '.join(bad)}")
    rows = read_csv(path)
    for existing in rows:
        if existing["job_id"] == str(job_id):
            existing.update(changes)
            write_csv(path, rows)
            return
    raise ValueError(f"no row for job {job_id}; screen it first")


def _pair(text):
    name, sep, value = text.partition("=")
    if not sep or not name:
        raise ValueError(f"--set {text!r}: use COLUMN=VALUE")
    return name, value


def now():
    return datetime.now().astimezone().isoformat(timespec="minutes")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bid log rows for a Google Sheet or a CSV.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("row", "upsert"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--result", required=True, help="fixed_rules.py --json output")
        cmd.add_argument("--at", help="screen time, ISO 8601 (default: now)")
        if name == "upsert":
            cmd.add_argument("--csv", required=True)
    update = sub.add_parser("update")
    update.add_argument("--csv", required=True)
    update.add_argument("--job-id", required=True)
    update.add_argument("--set", action="append", default=[], metavar="COLUMN=VALUE")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "update":
            changes = dict(_pair(text) for text in args.set)
            if not changes:
                raise ValueError("pass at least one --set COLUMN=VALUE")
            update_csv(os.path.expanduser(args.csv), args.job_id, changes)
            return 0
        with open(args.result, encoding="utf-8") as fh:
            row = row_from_result(json.load(fh), args.at or now())
        if args.cmd == "upsert":
            upsert_csv(os.path.expanduser(args.csv), row)
            return 0
        print(json.dumps({"columns": COLUMNS, "values": [row[c] for c in COLUMNS], "ranges": RANGES}, indent=2))
        return 0
    except (OSError, ValueError) as e:
        print(f"bidlog: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
