# upwork-skills: design

Date: 21 October 2026
Status: draft for review

## Problem

The Upwork workflow runs in three places that disagree:

- A cloud routine scans Upwork four times a day with rules frozen in its prompt on 2 October (skip coaching posts, skip 30+ hours a week, suggest $25 to $35 an hour).
- Interactive sessions apply newer judgement. On 21 October two bids went to coaching posts at $85 and $40 an hour, both deliberate exceptions to the routine's rules.
- The reasoning behind those exceptions lives in a long running log of notes, not in rules a tool can apply.

Each new session rediscovers the rules, and the routine keeps applying the old ones.

## Goal

One place where the Upwork workflow is defined, used by interactive sessions and the scheduled routine alike, so a rule changed once changes everywhere. The generic part is a public Claude Code plugin; everything personal stays private.

Success looks like:

- the routine and a session reach the same verdict on the same post;
- changing a rule is one edit to a private profile plus a sync;
- every bid is logged with the signals it was judged on, so later outcomes can tune the rules;
- nothing spends Connects without the freelancer's explicit yes.

## Non-goals

- Automatic submission of any kind.
- Writing or editing the Upwork profile, portfolio or account settings.
- Supporting agency accounts or client-side (hiring) workflows.
- A hosted service. Everything runs inside Claude Code or a Claude Code routine.

## Users

- The author, with a private profile and a cloud routine.
- Any freelancer using Claude Code with the official Upwork connector (`mcp.upwork.com`), with their own profile and either a Google Sheet or a local CSV as the bid log.

## Public and private split

| Part | Where | Public |
|---|---|---|
| `screen`, `submit`, `pipeline`, `routine` skills | plugin repo | yes |
| Default rules, Jev question sets | plugin repo `rules/` | yes |
| Scripts (fixed rules, Jev client, CSV log, replay) | plugin repo `scripts/` | yes |
| Example profile, routine prompt template | plugin repo `templates/` | yes |
| The freelancer's profile (claims, rates, voice, overrides) | a private file the user names | no |
| Proposal drafting skill (`upwork-draft`) | user's own skills folder | no |
| Bid log | Google Sheet tab or local CSV | no |

The public repo is deliberately about screening, submitting safely and measuring outcomes, not about writing proposals. A repo that drafts cover letters sits one click from every proposal the author sends, so drafting stays private.

## Skills

### screen

Input: one job (link or numeric ID), or a time window ("scan").

Single job:

1. Fetch the posting with `find_jobs action=get`. Stop if `applied` is true.
2. Save the response to a temporary JSON file and run `scripts/fixed_rules.py` against it with the profile. Fixed rules are code, so the same post always gets the same answer. Examples: client has no hires or has never left feedback; `totalHired` or `totalOffered` above zero; an active client contract with the same title; preferred qualifications above Any that the profile can't meet; `location_required` excluding the freelancer's country; Connects cost as a share of the balance.
3. Judgement questions: lane, coaching ask, scope boundedness (1 to 5), red flags in `client_feedback` (scope creep, refund demands, non-payment, abuse), asks for something the profile can't claim. Jev answers these when `TYPESAFE_API_KEY` is set and the question is enabled for filtering (see Jev); otherwise Claude answers them.
4. Apply the rules with the profile's overrides. Output BID, MAYBE or SKIP with one line per rule that fired, the Connects cost and the balance after.
5. On BID or MAYBE, append a row to the bid log and offer to draft.

Scan: search the window (`smart_search mode=most_recent` from the window start, plus title and skill searches from the profile's lanes), drop duplicates and applied posts, run fixed rules on every row, run the Jev first pass on survivors if enabled, then read each remaining post in full and screen it. The report lists BIDs (with drafts when the private draft skill is installed) and one line per SKIP.

### submit

1. Check `list_freelancer_proposals` for an existing invitation or proposal on the job.
2. Ask whether to attach files.
3. Create the proposal preview. Show the exact cover letter, answers, rate, portfolio projects, Connects cost, balance after, and the live boost bids. No boost unless the user asks for one.
4. Confirm only after an explicit yes to that preview. If the screen verdict was SKIP, require the user to override it by name.
5. Read the stored proposal back (`terms.connectsBid`, rate) and update the bid log row.

If Claude Code's auto-mode classifier blocks the create call, stop and tell the user; an explicit instruction from them ("submit the X bid at $Y") is what clears it. Never work around the block.

### pipeline

`check`: dashboard, proposals (`viewedByClient`, status), each job's funnel (`invitesSent`, `totalInvitedToInterview`, `totalHired`, `totalOffered`), invitations, offers and message rooms. Updates each logged bid's outcome: sent, viewed, interview, hired, lost (client hired someone else or the post closed), expired. Messages are triaged (Jev when enabled) and any request to move off Upwork or be paid outside it is flagged at the top.

`learn` (on request, suggested monthly):

- view and interview rates by lane, proposals at submit, post age at submit, and Jev scope score;
- Connects spent per view and per interview, with a recommendation on the paid plan before its renewal date;
- proposed rule changes as a diff to the profile's overrides, each replayed with `scripts/replay.py` against logged posts to show which past verdicts would change.

`learn` never edits the profile. The user applies or rejects each change.

### routine

Renders `templates/routine-prompt.md` with the private profile, fetches the live routine with `RemoteTrigger get`, shows the diff, and updates it only after approval. The rendered prompt tells the routine to screen and draft only, never to submit.

### upwork-draft (private, not in the repo)

Lives in the user's skills folder, like the author's private `linkedin-post` skill. Reads the profile and the evidence file it points to. Writes the cover letter and screening answers from allowed claims only, with `[ASK <NAME>]` where evidence runs out; suggests a rate from the profile's rate policy and portfolio projects from `get_profile action=list_highlights`; checks em dashes and length; runs the Jev claim check if enabled; saves the draft to the folder the profile names.

## Rules

Default rules ship in `rules/defaults.yaml`. Each rule has:

- `id` (for example `client-never-reviews`, `coaching-ask`, `crowded-rails-post`);
- `kind`: `fixed` (checked by `fixed_rules.py`) or `judgement` (a question for Jev or Claude);
- `check`: the condition, as fields and thresholds for fixed rules or a question for judgement rules;
- `reason`: why the rule exists;
- `effect`: SKIP, MAYBE or a note;
- `override`: the condition under which the rule does not apply.

Example: `coaching-ask` skips coaching and tutoring posts, because a vague "teach me" ask from a low-spend client turns into unpaid hand-holding. Override: the post states paid hours, a duration and deliverables, or the client has spent $20,000 or more and given 20 or more reviews. The 21 October coach post passed on the first condition ($80 to $130 an hour, 8 hours a week for 12 weeks, six listed outcomes) and the mentor post on the second ($545,000 spent, 65 reviews).

The profile may switch any rule off, change its thresholds, or replace its override, by `id`. `learn` proposes changes in exactly this form.

## Profile

A Markdown file with a YAML settings block, at a path the user chooses. For the author: `job-search-agent/profile/upwork-profile.md`, added to that repo's `.gitignore` before the file is created, since that repo is public.

Settings block:

- `org_uid`, country, time zone;
- `lanes`: names and search terms (title and skill filters);
- `rates`: floor, normal range, when to go above it;
- `availability`: hours per week, slot policy;
- `connects`: boost policy (default none), minimum balance to keep;
- `plan`: name and renewal date;
- `log`: `{type: sheet, spreadsheet_id, tab}` or `{type: csv, path}`;
- `jev`: per-question `mode` (`off`, `log`, `filter`) and `claim_check` (default `false`);
- `rule_overrides`: by rule `id`;
- `drafts_dir` and `evidence_file` for the private draft skill.

Body: allowed claims (each tied to an evidence ID), never-claim list, voice rules. Only the private draft skill and the routine sync read the body.

## Bid log

One row per BID or MAYBE. SKIPs stay in reports only, which keeps the log small.

| Column | Filled at |
|---|---|
| `screened_at`, `job_id`, `title`, `url`, `lane`, `verdict`, `reasons` | screen |
| `proposals_at_screen`, `age_hours`, `connects_cost` | screen |
| `client_hires`, `client_feedback_count`, `client_score`, `client_gives_avg`, `client_spend`, `client_hire_rate` | screen |
| `invites`, `interviews`, `hired`, `offered` | screen |
| `jev_lane`, `jev_scope`, `jev_flags` | screen, when Jev is on |
| `rate`, `proposal_id`, `submitted_at`, `boost` | submit |
| `outcome`, `outcome_at`, `notes` | pipeline |

`client_gives_avg` is the average `feedback_score` the client gave freelancers across its closed contracts, since a harsh rater is the worst first review.

## Jev

Jev (TypeSafe AI, released 15 September 2026) answers predefined questions with probabilities and does not generate text. It is called with `POST https://api.typesafe.ai/v1/systemone`, a Bearer key, and a body of `model`, `state` and `questions`; question types used here are `noul` (yes/no), `choice` and `score`. There is no SDK or MCP server, so `scripts/jev.py` is a small HTTP client.

Uses:

- scan first pass: lane, coaching ask, scope score, feedback red flags, unclaimable asks;
- consistent signals in the bid log, so `learn` compares like with like;
- claim check on drafts: each sentence mapped to an allowed claim, "none" or "never-claim" (up to 255 options); flags only, never blocks. Off by default because it sends the private claims list to TypeSafe;
- message triage in `pipeline check`, including off-platform requests.

Never used for: the final verdict, rates, submitting, or any written text.

Each question runs in one of three modes: `off`; `log` (answers recorded, not acted on); `filter` (may skip a post on its own). A question moves to `filter` only after an evaluation against posts already screened by hand: it must agree with the human decision on at least 90% of clear-cut posts and must not skip any post that was bid on. The evaluation set starts with roughly 60 posts from the author's notes and is re-run as the bid log grows.

The key comes only from `TYPESAFE_API_KEY` in the environment (the shell locally, the routine's environment in the cloud). Nothing writes it to disk. Without a key, every judgement question falls back to Claude.

## Error handling

- Upwork MCP errors: report and stop; never retry a write.
- A preview that expires (about 15 minutes) is recreated, not confirmed.
- Jev unreachable or erroring: fall back to Claude for that run and say so in the report.
- Bid log unreachable: finish the screen, print the row, and tell the user it wasn't saved.
- Fixed-rule script errors: show the error and screen without fixed rules only if the user agrees.

## Testing

- `pytest` for `fixed_rules.py` against saved job JSON with client names removed, `jev.py` against a fake HTTP server, the CSV log, and `replay.py`.
- A skill eval checking `screen` verdicts on the saved jobs.
- CI on GitHub Actions, as in rmine-skills.
- The Jev evaluation above, kept private because the labelled set includes the author's decisions.

## Build order

1. v0.1.0: profile and default rules, `screen` without Jev, `submit`, the private `upwork-draft`, and the bid log tab.
2. v0.2.0: `routine`, switching the cloud scan to the profile. First check whether a cloud routine can load the plugin from its marketplace; if not, the rendered prompt carries the rules too.
3. v0.3.0: `pipeline check` and `learn`.
4. v0.4.0: Jev client, evaluation, `log` mode, then `filter` for the questions that pass.

Releases follow rmine-skills: version in `.claude-plugin/plugin.json`, a CHANGELOG entry, and an annotated tag made with `claude plugin tag`.

## Risks and open questions

- Whether a cloud routine can load a plugin from a marketplace (checked first in v0.2.0).
- Jev is a month old and its published speed and accuracy figures come from the vendor; the evaluation gate exists for this reason.
- The auto-mode classifier can block `manage_proposals` until the user gives an explicit instruction; `submit` treats that as expected.
- The Upwork MCP's `find_jobs search` has no date filter; scans rely on `smart_search` with `from_date` plus client-side filtering on `published_date`.
- The author needs a TypeSafe account before v0.4.0.
