# Changelog

## 0.2.3

- The routine's prompt now spells out the per-post screen: every READ post
  from the first pass gets `fixed_rules.py --job` with its own `job.json`,
  and its judgement questions answered, before it gets a verdict. A rehearsal
  with 58 rows fetched the 12 READ posts and then judged them by eye, so no
  job-level rule ran and no question was answered. Run `/upwork-skills:routine`
  again after updating.

## 0.2.2

- The routine's prompt now tells the run to do all the work in its own
  session. A rehearsal with an eleven-hour window handed the row compiling to
  a subagent, ended its turn to wait, and never wrote a report. Run
  `/upwork-skills:routine` again after updating.

## 0.2.1

- The routine's window lines now give each scheduled slot's range and the
  time to screen from, for example "fired between 09:00 and 14:00: screen
  posts since 22:00 the day before". The old "09:00: posts since 22:00" named
  two times, and a run that started at 10:33 screened from 09:00 instead of
  22:00. Run `/upwork-skills:routine` again after updating.

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
