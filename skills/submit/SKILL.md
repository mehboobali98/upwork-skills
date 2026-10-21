---
name: submit
description: Use when the user wants to send, submit or apply with an Upwork proposal, or says to bid on a post at a given rate. Checks for an existing proposal or invitation, shows the exact preview with its Connects cost, and submits only after the user's explicit yes to that preview.
---

# Submit

Sends one Upwork proposal. It's the only skill in the plugin that spends
Connects, so it moves slowly on purpose: nothing goes out until the user has
seen the exact preview and said yes to it.

## Never

- Submit without an explicit yes to the preview being confirmed. Approving a
  draft is not a yes to a preview.
- Add a boost the user didn't ask for, or choose its size for them.
- Retry a write that failed, or confirm a preview the user hasn't seen.
- Work around Claude Code's auto-mode classifier. If it blocks
  `manage_proposals`, stop and tell the user. An explicit instruction from
  them, such as "submit the Rails upgrade bid at $40", is what clears it.

## 0. What you need

The job ID, the cover letter, answers to any screening questions, and the
hourly rate or fixed amount. They usually come from a draft; ask for
anything missing.

Look up the job's row in the bid log, and screen the post first if it has
none. If the verdict is SKIP, ask the user to override it by naming the rules
that skipped it, and record that override in the row's `notes` at step 6.

## 1. Existing proposal or invitation

Call `list_freelancer_proposals` with `action=invitations` and again with
`action=list`. If there's an invitation for this job, use `manage_proposals
action=accept_invitation` with its `invitation_uid` in place of `create`. If
a proposal already exists, stop: Upwork refuses a second.

## 2. Check the text

Save the letter and each answer as text files and run:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_letter.py" letter.txt answer-1.txt answer-2.txt
```

Fix every problem it reports (em dashes, `[ASK …]` placeholders, text over
5,000 characters) before going on. A placeholder is filled with the user's
answer, never a guess.

## 3. Attachments and portfolio

Ask whether to attach files. The question is required even when the answer
is no. For files, use `start_attachment_upload` with `context=proposals` and
pass the returned `file_uid`s as `attachments`. Suggest portfolio projects
from `get_profile action=list_highlights` that match the post, and let the
user choose.

## 4. Preview

Call `manage_proposals action=create` with `job_reference` (the numeric job
ID), `cover_letter`, `charged_amount`, `answers`, and the chosen
`portfolio_project_ids`, `certificate_ids` and `attachments`. Fixed-price
posts also take `payment_mode`, and `milestones` when paid by milestone; ask
when the first call says they're needed.

Show the user, exactly:

- the cover letter and every answer, as they'll be sent;
- the rate or amount, and for fixed price the payment mode;
- the portfolio projects and files attached;
- `connects_cost`, `connects_balance` and the balance after;
- any `unmet_preferred_qualifications`;
- the boost block: `current_top_bids`, `recommended_connects` and
  `max_boost_connects`. No boost unless the user asks, at an amount they
  choose within those bounds.

Then ask for a yes to this preview.

## 5. Confirm

On an explicit yes, call `confirm_preview`. A preview lasts about 15 minutes.
If it has expired, create it again, show what changed (the Connects cost and
the top bids can move) and ask again. If confirmation refuses a boost because
the bids moved, show the bids to beat and ask for a new amount or none.

## 6. Read it back and log it

Call `list_freelancer_proposals action=get` on the new proposal and report
the stored rate (`terms.chargeRate`), the boost (`terms.connectsBid`) and the
Connects balance after.

Then update the job's bid log row: `rate`, `proposal_id`, `submitted_at`
(now, ISO 8601 with its offset) and `boost` (0 for none). For a Sheet, find
the job in `<tab>!B:B` and update `<tab>!X<n>:AA<n>` (the `submit` range from
`bidlog.py row`), plus `<tab>!AD<n>` for a SKIP override note. For a CSV:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bidlog.py" update --csv <path> --job-id <job id> \
  --set rate=<rate> --set proposal_id=<proposal id> --set submitted_at=<time> --set boost=<n>
```

If the log can't be updated, say so and print the values.
