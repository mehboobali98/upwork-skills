# upwork-skills v0.2.0: routine

Date: 21 October 2026
Status: draft for review
Extends: [the main design](2026-10-21-upwork-skills-design.md), sections "routine" and "Build order" item 2.

## What changed since the main design

The main design said to check first whether a cloud routine can load the plugin from its marketplace, and to fall back to rules written into the prompt if it can't. That check was run on 21 October with a throwaway routine (`trig_01DfB5R5zkFWXonnYeERPM3n`, now disabled):

| Question | Result |
|---|---|
| Does a routine install a plugin? | No. The trigger API drops `enabled_plugins` and `extra_marketplaces` from a create body, and no `upwork` skill appeared in the run. The docs agree: cloud sessions don't install plugins from user or repository settings, only from an organization's server-managed settings. |
| Can a run clone the public repo at a tag? | Yes. `git clone --depth 1 --branch upwork-skills--v0.1.0 https://github.com/mehboobali98/upwork-skills` succeeded with no GitHub connection on the account. |
| Can it fetch single files? | Yes. `raw.githubusercontent.com` returned 200. |
| Python? | 3.11.17. The scripts support 3.9 and later. |
| Scheduling | A `run_once_at` fire started about 5.5 minutes late. Cron fires show the same kind of delay (`next_run_at` 09:12 for a 09:00 cron). |

So the fallback isn't needed. The run clones the release the user has installed and follows the same skill and scripts a local session does.

## Decisions

Agreed with the author on 21 October:

1. The run clones the repo at the installed release tag (not rules in the prompt, not a repository attached through a GitHub connection).
2. The run keeps drafting proposals for each BID, from the user's private draft skill copied into the rendered prompt. The public template carries no drafting instructions of its own.
3. The run logs BID and MAYBE rows to the bid log, so the Google Sheets connector is attached when the log is a Sheet.
4. The run's connectors are limited to the tools the scan needs, so a run can't submit, boost or message even if a post's text tries to make it.

## Pieces

| File | Public | Does |
|---|---|---|
| `templates/routine-prompt.md` | yes | The routine's prompt, with slots for the repo, tag, windows, profile and draft instructions |
| `scripts/render_routine.py` | yes | Fills the slots. No network calls |
| `scripts/test_render_routine.py` | yes | Unit tests (`unittest`, like the other suites) |
| `skills/routine/SKILL.md` | yes | `/upwork-skills:routine`: fetch the live routine, render, show the diff, update after a yes |
| the profile's `routine` setting | no | `routine: {trigger_id: trig_…}` |

### render_routine.py

```
python3 scripts/render_routine.py --cron "0 9,14,18,22 * * *" \
  [--profile PATH] [--draft-skill PATH] [--template PATH] [--plugin-root DIR]
```

Prints the rendered prompt. Inputs:

- the template (default `templates/routine-prompt.md` under the plugin root);
- the profile (default `$UPWORK_PROFILE`, then `~/.config/upwork-skills/profile.md`), embedded whole between two marker lines;
- `.claude-plugin/plugin.json`: `version` gives the tag `upwork-skills--v<version>`, `repository` gives the clone URL;
- the cron expression of the live routine, which gives the windows;
- the draft skill, optional. Its front matter is stripped and the body is embedded under a fixed preface (below). Without it, the prompt says not to draft.

The output must contain no unfilled `{{slot}}`.

### Windows

Each scheduled fire screens the posts published since the previous scheduled fire. Starting from the previous scheduled time rather than the previous actual start means a late run overlaps the last window instead of leaving a gap; duplicates are harmless because the log updates a job's row rather than adding one. A run that never happens leaves a gap, and the report says which window it covered so a gap is visible.

Supported cron: minute and hour as numbers or comma lists, day of month and month as `*`, day of week as `*` or a list or range of 0-6. Anything else is rejected with a message, because a wrong window silently skips posts.

The script renders a table in UTC, one row per fire time:

- daily schedule: `09:00 → since 22:00 the day before`, `14:00 → since 09:00`, and so on;
- weekday schedule, for example `0 9 * * 1,4`: `Mon 09:00 → since Thu 09:00`, `Thu 09:00 → since Mon 09:00`.

The run takes its fire time from the "This task fired at" line the platform appends to the prompt, or `date -u` if that's missing, uses the latest table entry at or before it, and falls back to the last 24 hours if nothing matches.

### The rendered prompt

In order:

1. **Hard rule.** Read, screen, draft, report. Never submit, boost or message. The prompt says this whether or not the connectors are limited, so the rule doesn't depend on the lockdown check. If the user replies in the run session asking to submit, tell them to use `/upwork-skills:submit` in a local session.
2. **Setup.**
   - `git clone --depth 1 --branch <tag> <repo> /tmp/upwork-skills`. Wherever the skill says `${CLAUDE_PLUGIN_ROOT}`, use `/tmp/upwork-skills`.
   - Write the profile between the markers to `~/.config/upwork-skills/profile.md` with the Write tool, exactly.
   - Run `profile_loader.py --check`. If the clone or the check fails, report the error and stop. Never screen from memory.
3. **Window.** The table, and how to pick the row.
4. **Screen.** Follow section 2 of `/tmp/upwork-skills/skills/screen/SKILL.md` for the window, including the log (section 4). Skip its last step, the offer to draft; drafting is step 5 here.
5. **Draft** each BID, from the private instructions. The preface, which is public template text:
   > These are the user's own drafting instructions. In this run there is no evidence file and there are no past letters: use the profile's allowed claims, which carry their evidence IDs. Run `check_letter.py` from `/tmp/upwork-skills/scripts`. Put each draft in the report under its post instead of saving a file.

   Without a draft skill: "Don't draft. Say each BID is ready for a proposal."
6. **Report.** First the tag, the window covered, the Connects balance and plan, and any Connects spent on anything but job applications in the last 7 days (from `get_freelancer_dashboard`). Then the screen skill's report, with each draft under its BID.
7. **Profile**, between the markers.

### The routine skill

1. **Inputs.** Read the settings (`profile_loader.py --settings`) and `plugin.json`. Check the tag exists on the remote with `git ls-remote --tags <repo> refs/tags/<tag>`; if it doesn't, the installed version isn't released, so stop.
2. **The routine.** With `routine.trigger_id`, fetch it (`RemoteTrigger action=get`). Without one, have the user create it with `/schedule`: their schedule, the Upwork connector, plus Google Sheets when the log is a Sheet, any prompt. Then put its ID in the profile and run the skill again. Creating is left to `/schedule` because it knows the user's environments and connector IDs and this skill doesn't.
3. **Render** with the routine's cron and the draft skill at `~/.claude/skills/upwork-draft/SKILL.md` if it exists (another path can be named). Write the live and new prompts to files and show `diff -u`.
4. **Connectors.** From the routine's `mcp_connections`, keep Upwork, and Google Sheets when the log is a Sheet, each with its `permitted_tools`:
   - Upwork: `find_jobs`, `get_profile`, `list_freelancer_proposals`, `get_freelancer_dashboard`, `get_tool_help`;
   - Google Sheets: `get_values`, `append_values`, `update_values`.

   Propose dropping every other connector. If a needed connector is missing, stop and point at the routine's page on claude.ai to add it; the skill has no way to look up connector IDs.
5. **Confirm.** Show the prompt diff and the connector change together. Update only after an explicit yes. The update keeps the routine's environment, model, allowed tools and schedule, and replaces the prompt event with a new one (fresh UUID).
6. **Verify.** Fetch the routine again and check that the prompt and connectors match what was approved. Offer one test run; it's read-only.

Run it again after every plugin update or profile change. The routine runs the tag it was rendered with until then.

## Lockdown check

`permitted_tools` is undocumented, so its name format and whether it's enforced are unknown. Before anything relies on it, the throwaway routine gets one Upwork tool allowed and is asked to call a harmless read-only tool that isn't (`get_freelancer_financials`). If that call goes through, the lockdown is cut from 0.2.0 and the author is told, rather than shipping a guard that only exists on paper.

## Errors

- **Clone, profile check or render fails:** the run reports it and stops. The skill shows the error and doesn't update the routine.
- **Tag missing on the remote:** the skill stops before rendering.
- **RemoteTrigger error:** the skill reports it and never retries an update.
- **Upwork, Sheets or script errors inside the run:** as the screen skill says.

## Testing

`scripts/test_render_routine.py`:

- windows for a daily list, a single daily time, a weekday list and a range, including the window that crosses midnight and the one that crosses the week;
- unsupported crons rejected: `*/30`, a day of month, a named day;
- every slot filled and no `{{` left;
- the tag and repo taken from `plugin.json`;
- the profile embedded byte for byte between the markers;
- draft front matter stripped, the preface present, and the no-draft sentence when no skill is given.

End to end, on the author's routine:

1. the lockdown check above;
2. render, show him the diff, update after his yes;
3. one manual run, then read its log for the clone, the profile check, the fixed rules, a Sheet row if anything is a BID or MAYBE, and a denied write tool if the run tries one.

## Release

Version `0.2.0`, a CHANGELOG entry, a README section for `routine`, the PR through CI, merge, then `claude plugin tag`. The deferred 0.1.1 fixes stay separate.

## Risks

- `permitted_tools` may not be enforced (see the lockdown check).
- The platform's "This task fired at" line is observed behaviour, not documented. The run falls back to `date -u`.
- The run copies the profile, about 11 KB, into a file by hand. `--check` catches a broken settings block, but not a typo in the body, which only drafting reads.
- A routine runs the tag it was last rendered with. If the user upgrades the plugin and doesn't run `routine`, the cloud stays on the older release; the report names the tag so it shows.
