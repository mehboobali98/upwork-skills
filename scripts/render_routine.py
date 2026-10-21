"""Render the cloud routine's prompt from the template, the profile and the release.

    render_routine.py --cron "0 9,14,18,22 * * *" [--profile PATH]
        [--draft-skill PATH] [--template PATH] [--plugin-root DIR]

Prints the prompt. A routine can't install plugins, so the prompt has it clone
this repo at the tag of the installed version and follow the same skill and
scripts a local session does. Each scheduled fire screens the posts published
since the previous scheduled fire; the cron gives those windows. Each
scheduled day's first fire also runs the pipeline check.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_loader  # noqa: E402
import routine_tools  # noqa: E402

PLUGIN_ROOT = profile_loader.PLUGIN_ROOT
DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
PROFILE_BEGIN = "-----BEGIN UPWORK PROFILE-----"
PROFILE_END = "-----END UPWORK PROFILE-----"
DRAFT_BEGIN = "-----BEGIN DRAFT INSTRUCTIONS-----"
DRAFT_END = "-----END DRAFT INSTRUCTIONS-----"
DRAFT_PREFACE = (
    "For each BID, write the proposal by following the user's own drafting "
    "instructions between the two DRAFT INSTRUCTIONS lines below. In this run "
    "there is no evidence file and there are no past letters: use the "
    "profile's allowed claims, which carry their evidence IDs. Run "
    "`check_letter.py` from `/tmp/upwork-skills/scripts`. Put each draft in "
    "the report under its post instead of saving a file."
)
NO_DRAFT = "Don't draft. Say each BID is ready for a proposal."
SLOT = re.compile(r"\{\{(\w+)\}\}")


class RenderError(ValueError):
    pass


def _numbers(field, low, high, name, every=False):
    values = set()
    for part in field.split(","):
        step = re.fullmatch(r"\*(?:/(\d+))?", part) if every else None
        if step:
            n = int(step.group(1) or 1)
            if n < 1:
                raise RenderError(f"cron {name}: {part} steps by 0")
            values.update(range(low, high + 1, n))
        elif re.fullmatch(r"\d+-\d+", part):
            start, end = (int(x) for x in part.split("-"))
            if start > end:
                raise RenderError(f"cron {name}: {part} runs backwards")
            values.update(range(start, end + 1))
        elif re.fullmatch(r"\d+", part):
            values.add(int(part))
        else:
            raise RenderError(f"cron {name}: {part!r} isn't supported; use numbers, lists or ranges")
    for v in values:
        if not low <= v <= high:
            raise RenderError(f"cron {name}: {v} is outside {low}-{high}")
    return sorted(values)


def parse_cron(expr):
    """Return (minutes, hours, weekdays); weekdays is None for every day."""
    fields = expr.split()
    if len(fields) != 5:
        raise RenderError(f"cron {expr!r}: expected 5 fields")
    minute, hour, dom, month, dow = fields
    if dom != "*" or month != "*":
        raise RenderError("cron: day of month and month must be *")
    minutes = _numbers(minute, 0, 59, "minute")
    hours = _numbers(hour, 0, 23, "hour", every=True)
    weekdays = None if dow == "*" else sorted({d % 7 for d in _numbers(dow, 0, 7, "day of week")})
    return minutes, hours, weekdays


def windows(expr):
    """One line per scheduled fire: the span a late start can fall in, and the window to screen."""
    minutes, hours, weekdays = parse_cron(expr)
    times = [(h, m) for h in hours for m in minutes]
    lines = []
    if weekdays is None:
        last = len(times) - 1
        for i, (h, m) in enumerate(times):
            ph, pm = times[i - 1]
            nh, nm = times[(i + 1) % len(times)]
            until = f"{nh:02d}:{nm:02d}" + (" the next day" if i == last else "")
            since = f"{ph:02d}:{pm:02d}" + (" the day before" if i == 0 else "")
            lines.append(f"- fired between {h:02d}:{m:02d} and {until}: screen posts since {since}")
        return lines
    fires = [(d, h, m) for d in weekdays for (h, m) in times]
    last = len(fires) - 1
    for i, (d, h, m) in enumerate(fires):
        pd, ph, pm = fires[i - 1]
        nd, nh, nm = fires[(i + 1) % len(fires)]
        until = ("the next " if i == last else "") + f"{DAYS[nd]} {nh:02d}:{nm:02d}"
        since = f"{DAYS[pd]} {ph:02d}:{pm:02d}" + (" the week before" if i == 0 else "")
        lines.append(f"- fired between {DAYS[d]} {h:02d}:{m:02d} and {until}: screen posts since {since}")
    return lines


def pipeline_fires(expr):
    """When each scheduled day's first fire can start: the run that checks the pipeline."""
    minutes, hours, _ = parse_cron(expr)
    firsts = windows(expr)[:: len(hours) * len(minutes)]
    return " or ".join(line[len("- fired "):].split(": screen posts", 1)[0] for line in firsts)


def strip_front_matter(text):
    if text.lstrip("﻿").startswith("---"):
        try:
            return profile_loader.split_front_matter(text.lstrip("﻿"))[1]
        except profile_loader.ProfileError:
            raise RenderError("the draft skill opens a '---' block it never closes") from None
    return text


def _block(begin, text, end, what):
    if begin in text or end in text:
        raise RenderError(f"the {what} contains a {begin.strip('-')} or {end.strip('-')} line")
    if not text.endswith("\n"):
        text += "\n"
    return f"{begin}\n{text}{end}"


def drafting(draft_text):
    if draft_text is None:
        return NO_DRAFT
    body = strip_front_matter(draft_text).strip("\n") + "\n"
    return DRAFT_PREFACE + "\n\n" + _block(DRAFT_BEGIN, body, DRAFT_END, "draft skill")


def release(plugin_root):
    with open(os.path.join(plugin_root, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    for key in ("name", "version", "repository"):
        if not manifest.get(key):
            raise RenderError(f"plugin.json has no {key}")
        if not isinstance(manifest[key], str):
            raise RenderError(f"plugin.json: {key} must be a string, not {json.dumps(manifest[key])}")
    return {
        "version": manifest["version"],
        "tag": f"{manifest['name']}--v{manifest['version']}",
        "repo": manifest["repository"],
    }


def allowed_tools(entries):
    return "\n".join(f"- {e['name']}: {', '.join(e['allow'])}" for e in entries)


def render(template, profile_text, rel, cron, allowed, draft_text=None):
    values = {
        "version": rel["version"],
        "tag": rel["tag"],
        "repo": rel["repo"],
        "windows": "\n".join(windows(cron)),
        "pipeline_fires": pipeline_fires(cron),
        "allowed_tools": allowed_tools(allowed),
        "drafting": drafting(draft_text),
        "profile": _block(PROFILE_BEGIN, profile_text, PROFILE_END, "profile"),
    }

    def fill(match):
        name = match.group(1)
        if name not in values:
            raise RenderError(f"the template has an unknown slot {{{{{name}}}}}")
        return values[name]

    return SLOT.sub(fill, template)


def _read(path):
    with open(os.path.expanduser(path), encoding="utf-8") as fh:
        return fh.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print the cloud routine's prompt.")
    ap.add_argument("--cron", required=True, help="the routine's cron expression, in UTC")
    ap.add_argument("--profile", help="default: $UPWORK_PROFILE, then ~/.config/upwork-skills/profile.md")
    ap.add_argument("--draft-skill", help="a private drafting skill to copy into the prompt")
    ap.add_argument("--plugin-root", default=PLUGIN_ROOT)
    ap.add_argument("--template")
    args = ap.parse_args(argv)
    template = args.template or os.path.join(args.plugin_root, "templates", "routine-prompt.md")
    try:
        profile = profile_loader.load_profile(args.profile)
        with open(profile["path"], encoding="utf-8-sig") as fh:
            profile_text = fh.read()
        draft_text = _read(args.draft_skill) if args.draft_skill else None
        allowed = routine_tools.load_allowed(os.path.join(args.plugin_root, "rules", "routine-tools.yaml"))
        prompt = render(_read(template), profile_text, release(args.plugin_root), args.cron, allowed, draft_text)
    except (OSError, ValueError) as e:
        print(f"render_routine: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
