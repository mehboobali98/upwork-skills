---
org_uid: "0000000000000000000"
country: Portugal
timezone: Europe/Lisbon
lanes:
  - name: django
    title_terms: [Django, Python backend]
    skills: [Django]
    skip_at_proposals: 20
  - name: data
    title_terms: [ETL, data pipeline, Airflow]
    skills: [Apache Airflow, ETL Pipeline]
    skip_at_proposals: 30
rates:
  floor_hourly: 30
  normal_hourly: [45, 60]
  above_normal_when: "The client's own range starts above the normal range."
  fixed: "At or a little under the budget when the scope fits."
availability:
  hours_per_week: 15
  slots: "Weekday evenings and Saturday mornings, Lisbon time."
connects:
  boost: none
  min_balance: 20
plan:
  name: Freelancer Basic
  renews: "2026-12-01"
qualifications:
  job_success_score: 0
  hours_worked: 0
  earnings: 0
  rising_talent: false
lacks:
  - Mobile apps
  - Frontend frameworks beyond Django templates
  - Kubernetes in production
  - Machine learning models
log:
  type: csv
  path: ~/upwork/bids.csv
rule_overrides:
  off-lane:
    effect: NOTE
drafts_dir: ~/upwork/drafts
evidence_file: ~/upwork/evidence.md
---

# Upwork profile

Private. Only the draft skill reads this part. Every claim names its evidence
in `evidence_file`; a claim without one never goes in a proposal.

## Allowed claims

- (EV-01) Moved a Django app from 2.2 to 4.2 with no downtime, upgrading the
  test suite alongside it.
- (EV-02) Built nightly Airflow pipelines that load supplier feeds into
  Postgres.

## Never claim

- Mobile work of any kind.
- Numbers that aren't in the evidence file.

## Voice

Short plain sentences, contractions, no em dashes. Open with the client's
problem in their words, use one or two proof points, and end with a question
or the first step.

## Portfolio projects

- 0000000000000000001: the Django upgrade case study.
