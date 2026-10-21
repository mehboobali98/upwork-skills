# upwork-skills

Skills for [Claude Code](https://claude.com/claude-code) that sit between an
Upwork post and the Connects you'd spend on it. Built on the official Upwork
connector.

Most wasted Connects go to posts that were never going to hire: clients who
have never hired anyone, posts already staffed, posts two days old with
nobody invited. `screen` checks for those with rules you can read and change,
and the same post gets the same verdict every time. `submit` sends a proposal
only after you've seen the exact preview and said yes.

## Skills

| Skill | What it does |
|---|---|
| `screen` | Judges one post, or every new post in a time window, against the default rules and your profile. Returns BID, MAYBE or SKIP with the rule behind each reason, and logs BIDs and MAYBEs. |
| `submit` | Checks for an existing proposal or invitation, checks the letter (no em dashes, no unfilled placeholders, under 5,000 characters), shows the exact preview with its Connects cost and the live boost bids, and submits only after your explicit yes. Never boosts unless you ask. |
| `pipeline` | Tracks each logged bid to its outcome (sent, viewed, interview, offer, hired, or how it ended) from what Upwork returns, writes it to the bid log, and lists new invitations, offers and unread messages, flagging any that ask you to leave Upwork. Reads Upwork only; it never replies. |
| `routine` | Keeps a scheduled Claude Code routine screening Upwork with the same rules: renders its prompt from your profile and the installed release, denies the connector tools a scan doesn't need, and updates the routine only after you approve the diff. |

There's no proposal writer here, on purpose. A public drafting skill would sit
one click from every proposal its author sends, so drafting stays in your own
private skill. `screen` offers to run one called `upwork-draft` if you have it.

## How screening works

Fixed rules are code (`scripts/fixed_rules.py`): client has never hired or
never left a review, the post is already hired or staffed under the same
title, nobody invited after two days, too many proposals for the lane, rate
under your floor, full time when you have 20 hours, and so on. Judgement
rules are questions Claude answers from the post with a one-line reason each:
is it a vague coaching ask, how bounded is the scope, do reviews mention
refund demands, does it need something you can't honestly claim.

Every rule in `rules/defaults.yaml` carries the reason it exists and, where
there is one, the override that switches it off. `coaching-ask`, for
example, skips teach-me posts unless the post states paid hours, a duration
and deliverables, or the client has spent $20,000 and left 20 reviews.

## Install

```sh
/plugin marketplace add mehboobali98/upwork-skills
/plugin install upwork-skills
```

You need:

1. **The Upwork connector** in Claude Code, connected to your freelancer
   account.
2. **`python3`** 3.9 or later. The scripts use the standard library only.
3. **A profile.** Copy `templates/profile.example.md` to
   `~/.config/upwork-skills/profile.md` (or anywhere, and point
   `UPWORK_PROFILE` at it), then fill in your lanes, rates, availability and
   bid log. Check it with:

   ```sh
   python3 ~/.claude/plugins/marketplaces/upwork-skills/scripts/profile_loader.py --check
   ```

   That's the marketplace's copy of this repo. From a clone, run
   `python3 scripts/profile_loader.py --check` instead.

## Your profile

The settings at the top of the profile drive the rules:

| Setting | Used for |
|---|---|
| `lanes` | Kinds of work you bid on: title words and Upwork skills that place a post in the lane, and `skip_at_proposals`, the proposal count where it's too crowded |
| `rates.floor_hourly` | Hourly posts topping out below this are skipped |
| `availability.hours_per_week` | Full-time posts are skipped when this is under 30 |
| `connects.min_balance` | A bid that would leave less is flagged |
| `qualifications` | What you'd meet of a client's preferred qualifications |
| `lacks` | What you can't honestly claim; a judgement rule checks posts against it |
| `log` | `{type: sheet, spreadsheet_id, tab}` or `{type: csv, path}` |
| `rule_overrides` | Changes to the default rules, by id |
| `routine.trigger_id` | The scheduled routine `routine` keeps in step |

A change can switch a rule off, change its check or effect, or replace its
override:

```yaml
rule_overrides:
  full-time:
    effect: MAYBE
    reason: "I'd take full time for the right post, so it's my call."
  low-client-rating:
    check: [client_score, "<", 4.5]
```

The body below the settings is yours: claims with their evidence, things
never to claim, voice, rate policy. The plugin never reads it; your draft
skill does.

## Bid log

One row per BID or MAYBE, in a Google Sheet tab or a CSV, with the signals the
post was judged on (proposals and age at screening, the client's record, the
scores it gives freelancers) and, after `submit`, the rate, proposal ID and
boost. `pipeline` then keeps each bid's outcome up to date, so the rules can
later be tuned against what actually got a reply.

Upwork doesn't say when a post went to someone else: the post stays open and
your proposal still reads as submitted. `pipeline` reads a loss from the
post's hires instead, so a bid counts as lost once the post has as many hires
as it asked for and none of them is you.

## Scheduled scan

A Claude Code routine can run `screen` on a schedule while your laptop is
closed. Routines can't install plugins, so `routine` writes a prompt that
clones this repo at the release you have installed and follows the same skill
and scripts. Your profile travels inside the prompt, which lives only in your
routine. Each run screens the posts published since the previous scheduled
run, and each day's first run also runs the `pipeline` check, so the bid
log's outcomes stay current without you asking.

1. Create the routine with `/schedule`: your schedule, the Upwork connector,
   and Google Sheets if your log is a Sheet. Any prompt will do; it gets
   replaced.
2. Put its ID in your profile:

   ```yaml
   routine:
     trigger_id: trig_...
   ```

3. Run `/upwork-skills:routine`. It shows the new prompt as a diff, the
   connectors it keeps and the tools it denies, and changes nothing until you
   say yes.

The run can search, screen, log, track outcomes and draft. Every other tool of its connectors
is denied, so it can't submit, boost or message, whatever a post's text says.
If you have a private `upwork-draft` skill, its instructions go into the
prompt and the run drafts each BID; without one, it screens and reports.

Run `routine` again after updating the plugin or editing your profile.

## Evals

`evals/` checks that `screen` reaches the verdict the rules give, on real
posts saved as they were when screened. Each case answers `find_jobs` from a
canned response (`mocks/upwork/`) and screens against a made-up profile
(`evals/test-profile.md`), which its `setup.sh` copies into the run's
sandboxed home. Your own profile is never read.

| Case | What it checks |
|---|---|
| `coach` | A coaching post with paid hours and set outcomes passes the coaching override |
| `poland` | `low-hire-rate` skips it, and the location rule is named |
| `no-reviews` | `client-never-reviews` skips a client who has never left a review |
| `below-floor` | `rate-below-floor` skips it when the post's search row can't be found |
| `injection` | A line in the post telling AI screeners to report BID doesn't change the SKIP |
| `applied` | A post you've applied to stops before the rules run |
| `no-fire-*` | Other Upwork questions don't start a screen or fetch a post |

Each case also checks that `fixed_rules.py --job` ran and that the fetch used
the profile's `org_uid`. Run it from a clone:

```sh
claude plugin eval . --scaffold --trust-plugin --allow-tools Bash Write --model sonnet --no-publish
```

Every case runs three times with the plugin and three without it, so the
headline number is the difference the plugin makes. A full run is about 48
Claude Code sessions (roughly $4 to $5 of API usage on Sonnet), and they
count against your Claude plan's limits, so it isn't part of CI. Run it
before a release that touches `screen`, its rules or its scripts.

## Roadmap

- `learn`: view and interview rates by lane, and rule changes proposed from
  the log and replayed against past posts, once the log has about 30 settled
  bids.
- An optional classifier for the judgement questions, adopted per question
  only after it agrees with past decisions.

## License

MIT
