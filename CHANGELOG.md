# Changelog

## 0.2.0

- **`routine`** keeps a scheduled Claude Code routine screening Upwork with the
  same rules as your sessions. Routines can't install plugins, so the prompt
  it renders (`scripts/render_routine.py`, `templates/routine-prompt.md`)
  clones this repo at the installed release and follows `screen`, with your
  profile and, if you have one, your private draft skill inside it. Each run
  screens the posts published since the previous scheduled run.
- The routine's connector tools are cut down to what a scan needs
  (`rules/routine-tools.yaml`, `scripts/routine_tools.py`), so a run can't
  submit, boost or message.
- New profile setting: `routine.trigger_id`.

## 0.1.0

First release.

- **`screen`** judges one Upwork post, or every new post in a time window,
  against default rules adjusted by the freelancer's profile. Fixed rules run
  as code (`scripts/fixed_rules.py`), so the same post always gets the same
  verdict; judgement rules come back as questions, answered with a one-line
  reason each. BID, MAYBE or SKIP, with the rule behind every reason.
- **`submit`** checks for an existing proposal or invitation, checks the text
  (`scripts/check_letter.py`), shows the exact preview with its Connects cost
  and the live boost bids, and submits only after an explicit yes.
- **Default rules** in `rules/defaults.yaml`, each with its reason and, where
  it has one, its override. A profile switches a rule off or changes it by id
  under `rule_overrides`.
- **Bid log** rows for a Google Sheet tab or a CSV (`scripts/bidlog.py`).
- `templates/profile.example.md` to start a profile from.
