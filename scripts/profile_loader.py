"""Load a freelancer profile and the screening rules it adjusts.

    profile_loader.py [--profile PATH] [--rules PATH] --check
    profile_loader.py [--profile PATH] --settings

A profile is Markdown that opens with YAML settings between two '---' lines;
the body after them holds the private claims, which only the draft skill
reads. The profile is $UPWORK_PROFILE if set, else
~/.config/upwork-skills/profile.md.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conditions  # noqa: E402
import facts  # noqa: E402
import miniyaml  # noqa: E402

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RULES = os.path.join(PLUGIN_ROOT, "rules", "defaults.yaml")
RULE_KEYS = {"id", "kind", "check", "ask", "answer", "fires_when", "effect", "reason", "override"}
CHANGE_KEYS = {"off", "check", "ask", "fires_when", "effect", "reason", "override"}
OVERRIDE_KEYS = {"check", "ask", "reason"}
KINDS = {"fixed", "judgement"}
EFFECTS = {"SKIP", "MAYBE", "NOTE"}
NUMBER_SETTINGS = {
    "rates": ("floor_hourly",),
    "availability": ("hours_per_week",),
    "connects": ("min_balance",),
    "qualifications": ("job_success_score", "hours_worked", "earnings"),
}


class ProfileError(ValueError):
    pass


def default_path():
    return os.path.expanduser(os.environ.get("UPWORK_PROFILE") or "~/.config/upwork-skills/profile.md")


def split_front_matter(text):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ProfileError("a profile starts with a '---' line, then its settings")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "".join(lines[1:i]), "".join(lines[i + 1:])
    raise ProfileError("the profile's settings have no closing '---' line")


def load_profile(path=None):
    path = os.path.expanduser(path or default_path())
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    try:
        settings_text, body = split_front_matter(text)
        settings = miniyaml.loads(settings_text, first_line=2)
        _check_settings(settings)
    except ValueError as e:
        raise ProfileError(f"{path}: {e}") from None
    return {"path": path, "settings": settings, "body": body}


def load_rules(settings=None, path=DEFAULT_RULES):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        doc = miniyaml.loads(text)
    except miniyaml.YamlError as e:
        raise ProfileError(f"{path}: {e}") from None
    rules = doc.get("rules") if isinstance(doc, dict) else None
    if not isinstance(rules, list):
        raise ProfileError(f"{path}: expected a 'rules' list")
    by_id = {}
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
            raise ProfileError(f"{path}: every rule needs an id")
        if rule["id"] in by_id:
            raise ProfileError(f"{path}: duplicate rule id {rule['id']!r}")
        by_id[rule["id"]] = rule
    for rule_id, change in ((settings or {}).get("rule_overrides") or {}).items():
        if rule_id not in by_id:
            raise ProfileError(f"rule_overrides: no rule named {rule_id!r}")
        if not isinstance(change, dict) or not change or set(change) - CHANGE_KEYS:
            raise ProfileError(f"rule_overrides.{rule_id}: change only {', '.join(sorted(CHANGE_KEYS))}")
        by_id[rule_id] = {**by_id[rule_id], **change}
    merged = []
    for rule in by_id.values():
        if rule.get("off"):
            continue
        rule = {k: v for k, v in rule.items() if k != "off"}
        check_rule(rule)
        merged.append(rule)
    return merged


def check_rule(rule):
    rid = rule["id"]
    extra = set(rule) - RULE_KEYS
    if extra:
        raise ProfileError(f"rule {rid}: unknown keys {', '.join(sorted(extra))}")
    if rule.get("kind") not in KINDS:
        raise ProfileError(f"rule {rid}: kind must be fixed or judgement")
    if rule.get("effect") not in EFFECTS:
        raise ProfileError(f"rule {rid}: effect must be SKIP, MAYBE or NOTE")
    if not isinstance(rule.get("reason"), str) or not rule["reason"]:
        raise ProfileError(f"rule {rid}: needs a reason")
    try:
        if rule["kind"] == "fixed":
            if "check" not in rule:
                raise ProfileError(f"rule {rid}: a fixed rule needs a check")
            conditions.validate(rule["check"], f"rule {rid}.check", facts.FACT_NAMES)
        else:
            _check_question(rule)
        override = rule.get("override")
        if override is not None:
            if not isinstance(override, dict) or set(override) - OVERRIDE_KEYS or not {"check", "ask"} & set(override):
                raise ProfileError(f"rule {rid}: an override has a check, an ask, or both, and a reason")
            if "check" in override:
                conditions.validate(override["check"], f"rule {rid}.override.check", facts.FACT_NAMES)
            if "ask" in override and not isinstance(override["ask"], str):
                raise ProfileError(f"rule {rid}: override.ask must be a question")
    except conditions.ConditionError as e:
        raise ProfileError(str(e)) from None


def _check_question(rule):
    rid, want = rule["id"], rule.get("fires_when")
    if not isinstance(rule.get("ask"), str) or not rule["ask"]:
        raise ProfileError(f"rule {rid}: a judgement rule needs an ask")
    if rule.get("answer") == "yes_no":
        if not isinstance(want, bool):
            raise ProfileError(f"rule {rid}: fires_when must be true or false")
    elif rule.get("answer") == "score":
        if not (isinstance(want, list) and len(want) == 2 and want[0] in conditions.OPS
                and isinstance(want[1], (int, float)) and not isinstance(want[1], bool)):
            raise ProfileError(f"rule {rid}: fires_when must be [op, number]")
    else:
        raise ProfileError(f"rule {rid}: answer must be yes_no or score")


def _check_settings(settings):
    if not isinstance(settings, dict):
        raise ProfileError("settings must be 'key: value' lines")
    names = set()
    for lane in settings.get("lanes") or []:
        if not isinstance(lane, dict) or not isinstance(lane.get("name"), str):
            raise ProfileError("every lane needs a name")
        if lane["name"] in names or lane["name"] == "other":
            raise ProfileError(f"lane name {lane['name']!r} is taken")
        names.add(lane["name"])
        for key in ("title_terms", "skills"):
            if not isinstance(lane.get(key) or [], list):
                raise ProfileError(f"lane {lane['name']}: {key} must be a list")
        cap = lane.get("skip_at_proposals")
        if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 1):
            raise ProfileError(f"lane {lane['name']}: skip_at_proposals must be a whole number above 0")
    if not isinstance(settings.get("rule_overrides") or {}, dict):
        raise ProfileError("rule_overrides must map rule ids to changes")
    if not isinstance(settings.get("country") or "", str):
        raise ProfileError("country must be a country's name")
    for section, keys in NUMBER_SETTINGS.items():
        values = settings.get(section)
        if values is None:
            continue
        if not isinstance(values, dict):
            raise ProfileError(f"{section} must be 'key: value' lines")
        for key in keys:
            value = values.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ProfileError(f"{section}.{key} must be a number, not {value!r}")
    rising = (settings.get("qualifications") or {}).get("rising_talent")
    if rising is not None and not isinstance(rising, bool):
        raise ProfileError("qualifications.rising_talent must be true or false")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a profile, or print its settings as JSON.")
    ap.add_argument("--profile")
    ap.add_argument("--rules", default=DEFAULT_RULES)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--settings", action="store_true")
    args = ap.parse_args(argv)
    try:
        profile = load_profile(args.profile)
        rules = load_rules(profile["settings"], args.rules)
    except (OSError, ValueError) as e:
        print(f"profile_loader: {e}", file=sys.stderr)
        return 2
    settings = profile["settings"]
    if args.settings:
        print(json.dumps(settings, indent=2))
        return 0
    changes = settings.get("rule_overrides") or {}
    off = sorted(k for k, v in changes.items() if v.get("off"))
    lanes = ", ".join(lane["name"] for lane in settings.get("lanes") or []) or "none"
    print(f"profile OK: {profile['path']}")
    print(f"{len(rules)} rules in use, {len(changes)} changed by the profile"
          + (f", switched off: {', '.join(off)}" if off else ""))
    print(f"lanes: {lanes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
