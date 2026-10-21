---
name: routine
description: Use when the user wants their scheduled Upwork scan (a Claude Code cloud routine) brought in line with their current profile and rules, after editing the profile or updating this plugin, or asks to set up, sync, check or lock down that routine.
---

# Routine

Keeps a cloud routine that scans Upwork in step with the profile and the
installed release. A routine can't install plugins, so its prompt clones this
repo at the installed release's tag and follows the same `screen` skill and
scripts a local session does. This skill renders that prompt, limits the
routine's connector tools, shows what would change, and updates the routine
only after the user's explicit yes.

It never creates or deletes a routine, and never changes its schedule, model
or on/off state.

Keep the files below in a scratch directory (the session's scratchpad if it
has one, else `mktemp -d`).

## 1. Inputs

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/profile_loader.py" --check
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/profile_loader.py" --settings
```

From the settings you need `routine.trigger_id` and `log`. The user can name
another trigger ID for this run, for example a test routine.

Read `name`, `version` and `repository` from
`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. The release tag is
`<name>--v<version>`. Check that it's published, since the routine clones it:

```sh
git ls-remote --tags <repository> refs/tags/<tag>
```

No output means this version isn't released (a local checkout ahead of its
last tag, say). Stop and say so.

## 2. The routine

Without a trigger ID, stop and tell the user to create the routine with
`/schedule`: their schedule, the Upwork connector, Google Sheets as well when
the log is a Sheet, and any prompt, since this skill replaces it. Then add to
the profile's settings and run this skill again:

```yaml
routine:
  trigger_id: trig_...
```

With one, fetch it: `RemoteTrigger` with `action=get`. From the response you
need:

- `cron_expression`. A routine with `run_once_at` and no cron has no windows
  to render: stop and say so.
- `job_config.ccr.environment_id` and `job_config.ccr.session_context`.
- `mcp_connections`.
- The prompt, `job_config.ccr.events[0].data.message.content`. Write it,
  exactly, to `live-prompt.md`. Keep this file until the user is happy with
  the updated routine; it's how to roll back.

## 3. Render

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render_routine.py" --cron "<cron_expression>" \
  --draft-skill ~/.claude/skills/upwork-draft/SKILL.md > new-prompt.md
diff -u live-prompt.md new-prompt.md
```

Pass `--draft-skill` only when that file exists, or with the path the user
names. Its instructions are copied into the routine's prompt and nowhere
else. Without one, the routine screens and reports but doesn't draft.

## 4. Connectors and tools

Keep the connection whose `name` contains `upwork`, and the one containing
`sheets` when `log.type` is `sheet`. Propose removing every other connection:
the deny list below covers only these two, so any other connector would give
the run all its tools. If a needed connection is missing, stop and tell the
user to add it on the routine's page at https://claude.ai/code/routines and
run this skill again. This skill can't look up connector IDs.

A connection's `permitted_tools` isn't enforced; the routine's
`session_context.disallowed_tools` is. So for each kept connection, list every
tool you can see from that connector in this session, deferred ones included,
one per line, in `<name>-tools.txt` (names like
`mcp__claude_ai_Upwork__upwork__find_jobs`), and run:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/routine_tools.py" --connection <name> <name>-tools.txt
```

If you can't see a kept connector's tools in this session, stop and say so:
an empty list would deny nothing, and the script refuses one.

`<name>` is the connection's `name` on the routine, such as `Upwork` or
`Google_Sheets`; the cloud names a tool `mcp__<name>__<tool>`. The script
prints the tools to deny. The new `disallowed_tools` is both lists together,
plus any entry already there that isn't for these two connectors. If the
script warns that an allowed tool wasn't listed, the connector has changed:
show the warning.

## 5. Confirm

Show the user, together:

- the prompt diff (on a first sync, say it replaces the whole prompt and
  walk through the new one's sections instead);
- the release tag the routine will clone;
- the connections kept and removed;
- the tools denied: how many, and the write tools by name (anything that
  submits, boosts, messages, uploads, or changes a profile, contract or
  sheet).

Update only after an explicit yes. Make a fresh UUID with
`python3 -c "import uuid; print(uuid.uuid4())"` and call `RemoteTrigger` with
`action=update` and this body:

```json
{
  "mcp_connections": [{"connector_uuid": "...", "name": "...", "url": "..."}],
  "job_config": {"ccr": {
    "environment_id": "<unchanged>",
    "session_context": {"...": "unchanged, with disallowed_tools replaced"},
    "events": [{"data": {
      "uuid": "<the new UUID>", "session_id": "", "type": "user",
      "parent_tool_use_id": null,
      "message": {"role": "user", "content": "<new-prompt.md, exactly>"}
    }}]
  }}
}
```

An update that includes `job_config` replaces all of it, so carry the
environment and every other session setting over unchanged. List each kept
connection with its `connector_uuid`, `name` and `url` as the routine had
them. If the update fails, report the error and stop; never retry it.

## 6. Verify

Fetch the routine again. Write its prompt to `stored-prompt.md` and run
`diff new-prompt.md stored-prompt.md`, which should print nothing, and check
that the connections and `disallowed_tools` are what the user approved.

Offer one test run (`RemoteTrigger` with `action=run`, which works even on a
disabled routine). It screens the current window and logs any BID or MAYBE,
but it can't submit. If they want it, read the run with `list_runs` and
`get_run_log` once it finishes, and check the clone, the profile check, the
report's opening lines and its tools line.

Remind the user to run this skill again after updating the plugin or editing
the profile. Until then the routine keeps the release and profile it was
rendered with.

## Errors

- A script error: show it and stop before changing the routine.
- A `RemoteTrigger` error: report it and stop. Never retry an update.
- The rendered prompt rejected as too long: say so, and offer to render it
  without the draft skill.
