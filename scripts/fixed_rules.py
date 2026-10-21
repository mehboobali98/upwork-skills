"""Screen an Upwork post against the profile's rules.

    fixed_rules.py --job job.json [--row row.json] [--answers answers.json] [--json]
    fixed_rules.py --rows rows.json [--json]

--job is a find_jobs action=get response and --row the post's search row,
which carries its posting time and proposal count. Fixed rules are code, so
the same post always gets the same verdict; judgement rules come back as
questions until --answers supplies them. --rows is a scan's first pass: the
fixed rules a search row can answer, SKIP or READ per post.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conditions  # noqa: E402
import facts  # noqa: E402
import profile_loader  # noqa: E402


class ScreenError(ValueError):
    pass


def screen(rules, f, answers=None):
    """The verdict, with every rule that fired, was overridden, is unknown or still asks a question."""
    answers = answers or {}
    _check_answers(rules, answers)
    out = {"fired": [], "overridden": [], "notes": [], "unknown": [], "pending": []}
    for rule in rules:
        hit = _hit(rule, f, answers, out)
        if not hit or not hit[0]:
            continue
        held, why = _override(rule, f, answers, out)
        if held is None:
            continue
        entry = {"id": rule["id"], "effect": rule["effect"], "detail": hit[1], "reason": rule["reason"]}
        if held:
            reason = (rule.get("override") or {}).get("reason", "")
            out["overridden"].append(dict(entry, why=why, override_reason=reason))
        elif rule["effect"] == "NOTE":
            out["notes"].append(entry)
        else:
            out["fired"].append(entry)
    out["verdict"] = _verdict(out)
    return out


def result(rules, f, answers=None):
    out = screen(rules, f, answers)
    out.update(job_id=f["job_id"], title=f["title"], url=f["url"], lane=f["lane"], facts=f)
    return out


def first_pass(rules, rows, settings, now=None):
    fixed = [rule for rule in rules if rule["kind"] == "fixed"]
    seen, out = set(), []
    for row in rows:
        f = facts.build(row=row, settings=settings, now=now)
        if f["job_id"] in seen:
            continue
        seen.add(f["job_id"])
        verdict = screen(fixed, f)
        out.append({
            "job_id": f["job_id"], "title": f["title"], "url": f["url"], "lane": f["lane"],
            "proposals": f["proposals_label"], "age_hours": f["age_hours"],
            "verdict": "SKIP" if verdict["verdict"] == "SKIP" else "READ",
            "skipped_by": [e["id"] for e in verdict["fired"] if e["effect"] == "SKIP"],
        })
    return out


def _check_answers(rules, answers):
    if not isinstance(answers, dict):
        raise ScreenError("answers must map question ids to {answer, why}")
    known = set()
    for rule in rules:
        if rule["kind"] == "judgement":
            known.add(rule["id"])
        if "ask" in (rule.get("override") or {}):
            known.add(rule["id"] + ".override")
    for key, given in answers.items():
        if key not in known:
            raise ScreenError(f"no question {key!r} to answer")
        if not isinstance(given, dict) or "answer" not in given:
            raise ScreenError(f'{key}: give {{"answer": ..., "why": ...}}')


def _hit(rule, f, answers, out):
    """(fires, detail), or None while it can't be told."""
    if rule["kind"] == "fixed":
        value, details = conditions.evaluate(rule["check"], f)
        if value is None:
            out["unknown"].append({"id": rule["id"], "detail": "; ".join(details)})
            return None
        return value, "; ".join(details)
    override = rule.get("override") or {}
    if "check" in override and conditions.evaluate(override["check"], f)[0]:
        return True, "not asked, since the override holds"
    given = answers.get(rule["id"])
    if given is None:
        out["pending"].append({"id": rule["id"], "ask": rule["ask"], "answer": rule["answer"]})
        if "ask" in override:
            out["pending"].append({"id": rule["id"] + ".override", "ask": override["ask"], "answer": "yes_no"})
        return None
    return _fires(rule, given["answer"]), given.get("why", "")


def _override(rule, f, answers, out):
    """(True, why) when the override holds, (None, '') while its question is unanswered."""
    override = rule.get("override") or {}
    if "check" in override:
        value, details = conditions.evaluate(override["check"], f)
        if value:
            return True, "; ".join(details)
    if "ask" in override:
        key = rule["id"] + ".override"
        given = answers.get(key)
        if given is None:
            out["pending"].append({"id": key, "ask": override["ask"], "answer": "yes_no"})
            return None, ""
        if not isinstance(given["answer"], bool):
            raise ScreenError(f"{key}: answer true or false")
        if given["answer"]:
            return True, given.get("why", "")
    return False, ""


def _fires(rule, answer):
    want = rule["fires_when"]
    if rule["answer"] == "yes_no":
        if not isinstance(answer, bool):
            raise ScreenError(f"{rule['id']}: answer true or false")
        return answer == want
    if isinstance(answer, bool) or not isinstance(answer, int) or not 1 <= answer <= 5:
        raise ScreenError(f"{rule['id']}: answer a whole number from 1 to 5")
    op, target = want
    return conditions.OPS[op](answer, target)


def _verdict(out):
    effects = {e["effect"] for e in out["fired"]}
    if "SKIP" in effects:
        return "SKIP"
    if out["pending"]:
        return "PENDING"
    if "MAYBE" in effects:
        return "MAYBE"
    return "BID"


def render(out):
    f = out["facts"]
    lines = [
        f"{out['verdict']}  {f['title']}  (job {f['job_id']}, lane {f['lane']})",
        f"  {_val(f['proposals_label'])} proposals, {_val(f['age_hours'])} h old, "
        f"{_val(f['connects_cost'])} Connects of {_val(f['connects_balance'])}, {_val(f['balance_after'])} after",
    ]
    lines += [f"  {e['effect']} {e['id']}: {e['detail']}. {e['reason']}" for e in out["fired"]]
    lines += [f"  override {e['id']}: {e['why']}. {e['override_reason']}".rstrip() for e in out["overridden"]]
    lines += [f"  NOTE {e['id']}: {e['reason']}" for e in out["notes"]]
    lines += [f"  unknown {e['id']}: {e['detail']}" for e in out["unknown"]]
    lines += [f"  ask {q['id']} ({q['answer']}): {q['ask']}" for q in out["pending"]]
    return "\n".join(lines)


def render_rows(rows):
    lines = []
    for r in rows:
        line = (f"{r['verdict']:4}  {r['title']}  (job {r['job_id']}, {r['lane']}, "
                f"{_val(r['proposals'])} proposals, {_val(r['age_hours'])} h)")
        if r["skipped_by"]:
            line += ": " + ", ".join(r["skipped_by"])
        lines.append(line)
    return "\n".join(lines)


def _val(value):
    return "?" if value is None else str(value)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Screen an Upwork post against the profile's rules.")
    ap.add_argument("--job", help="find_jobs action=get response, as JSON")
    ap.add_argument("--row", help="the post's search row, as JSON")
    ap.add_argument("--rows", help="a list of search rows, for a scan's first pass")
    ap.add_argument("--answers", help="answers to the judgement questions, as JSON")
    ap.add_argument("--lane", help="screen in this lane instead of the matched one")
    ap.add_argument("--profile")
    ap.add_argument("--rules", default=profile_loader.DEFAULT_RULES)
    ap.add_argument("--now", help="ISO time to measure post age from (default: now)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if bool(args.job) == bool(args.rows):
        ap.error("pass --job or --rows")
    try:
        now = facts.parse_time(args.now) if args.now else None
        if args.now and now is None:
            raise ScreenError(f"--now {args.now!r} isn't an ISO time")
        profile = profile_loader.load_profile(args.profile)
        rules = profile_loader.load_rules(profile["settings"], args.rules)
        if args.rows:
            out = first_pass(rules, _read(args.rows), profile["settings"], now)
            print(json.dumps(out, indent=2) if args.json else render_rows(out))
            return 0
        f = facts.build(job=_read(args.job), row=_read(args.row) if args.row else None,
                        settings=profile["settings"], now=now, lane=args.lane)
        out = result(rules, f, _read(args.answers) if args.answers else None)
    except (OSError, ValueError) as e:
        print(f"fixed_rules: {e}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2) if args.json else render(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
