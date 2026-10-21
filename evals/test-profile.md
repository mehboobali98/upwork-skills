---
org_uid: "1000000000000000001"
country: Pakistan
timezone: Asia/Karachi
lanes:
  - name: rails
    title_terms: [Rails, Ruby]
    skills: [Ruby on Rails]
    skip_at_proposals: 20
  - name: agent-tooling
    title_terms: [Claude Code, AI agent]
    skills: [Claude Code]
    skip_at_proposals: 60
rates:
  floor_hourly: 25
  normal_hourly: [35, 45]
  above_normal_when: "The client's own range starts above the normal range."
  fixed: "At or a little under the budget when the scope fits."
availability:
  hours_per_week: 20
  slots: "Weekday evenings, Pakistan time."
connects:
  boost: none
  min_balance: 10
plan:
  name: Freelancer Plus
  renews: "2026-12-01"
qualifications:
  job_success_score: 0
  hours_worked: 0
  earnings: 0
  rising_talent: false
lacks:
  - Mobile apps
  - Kubernetes in production
  - Machine learning models
log:
  type: csv
  path: ~/upwork/bids.csv
rule_overrides:
  full-time:
    effect: MAYBE
    reason: "Full time is the freelancer's call for the right post, not an automatic skip."
---

# Upwork profile (eval)

A made-up profile for the `screen` eval suite. Nothing here describes a real
freelancer, and no skill reads this body during a screen.
