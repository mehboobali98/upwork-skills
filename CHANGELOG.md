# Changelog

## 0.3.0

- New skill, `pipeline`. `scripts/outcomes.py` tracks each logged bid to
  its outcome (sent, viewed, interview, offer, hired, lost, expired,
  cancelled, closed, withdrawn or declined) from the proposal and its post,
  and writes only the log's `outcome` and `outcome_at`. Upwork never marks a
  proposal lost, and a filled post can stay open for weeks, so a loss is read
  from the post's hires. An outcome never moves back, and only an offer or a
  hire replaces `lost`. The skill also lists new invitations, offers and
  unread messages, flags any that ask you to leave Upwork, be paid outside
  it or work unpaid, and lists proposals the log has no row for.
- `submit` writes `outcome=sent` with the submit time, so a new row is never
  blank. The `submit` range is now `X:AC`.
- The scheduled scan runs the `pipeline` check on each day's first run,
  after screening, with the tools it already had. Run `/upwork-skills:routine`
  again after updating.

## 0.2.6

- A scan screens its READ posts in one batch: `fixed_rules.py --jobs DIR
  --rows rows.json --out results` reads every saved `<job id>.json`, finds
  each post's row by ID, and ends with one answers template, keyed by job
  ID, for the questions still open. Filled in and passed back with
  `--answers`, it gives the final verdicts, BIDs first, and `--out` writes
  each post's result for the bid log. Live runs with 12 or more READ posts
  skipped the four steps per post that 0.2.3 spelled out and judged by eye;
  runs with 6 or 7 followed them. The batch is two commands for any number
  of posts. Run `/upwork-skills:routine` again after updating.

## 0.2.5

- `screen` keeps `preferred_locations` when it saves a post as `job.json`.
  0.2.4 taught the rules to read it, but the skill's list of keys to keep
  still dropped it, so a screen never reached the location rules. A test now
  trims each saved post to the skill's list and checks the rules see the
  same facts as with the full response.

## 0.2.4

- **The location rules work.** `location-excluded` and
  `location-preferred-elsewhere` read a shape no real response has: Upwork
  returns `preferred_locations` as `{countries, location_required}` beside
  `preferred_qualifications`, not inside it. Both rules were silently false
  on every post. A post that names places other than countries, or a profile
  without `country`, now reports the rules as unknown. New fixture
  `job-location.json`, trimmed from a real Poland-only post.
- A profile saved with a UTF-8 byte-order mark now loads.
- The settings the rules read must be numbers: `rates.floor_hourly`,
  `availability.hours_per_week`, `connects.min_balance` and the
  `qualifications` figures. A value like `floor_hourly: "$25"` used to load
  and leave its rule unknown on every post; now the profile check names it.
  `country` must be text and `qualifications.rising_talent` true or false.
- `fixed_rules.py --rows` refuses `--row`, `--answers` and `--lane`, which it
  used to ignore. A first pass runs only the fixed rules.
- The first pass keeps every search row without a job ID. It used to keep the
  first one and drop the rest as duplicates.
- The routine's cron hours can be `*` or `*/n`, as in `0 */6 * * *`.
- A `repository` in `plugin.json` that isn't a string gets its own error,
  instead of "plugin.json has no repository".
- The `routine` skill says its connection names match in any case, and the
  README's profile check works from an installed plugin.

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
