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
   python3 scripts/profile_loader.py --check
   ```

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
boost. Outcomes come later, so the rules can be tuned against what actually
got a reply.

## Roadmap

- 0.2: run the screen as a scheduled Claude Code routine from the same
  profile.
- 0.3: `pipeline`, which tracks views, interviews and hires per bid, and
  `learn`, which proposes rule changes from the log and replays them against
  past posts.
- 0.4: an optional classifier for the judgement questions, adopted per
  question only after it agrees with past decisions.

## License

MIT
