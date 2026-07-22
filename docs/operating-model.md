# Foundry operating model

Version: 1.0  
Effective: 2026-07-21

Foundry turns a documented claim into a monitored release through four evidence
gates. Agents may draft work, run bounded tasks, and recommend decisions. A
human reviewer is accountable for every stage transition and release.

## Decision outcomes

- `advance`: the gate criteria are satisfied; enter the next stage.
- `iterate`: retain the project and run a named next experiment.
- `hold`: pause until a stated dependency or decision date.
- `retire`: stop investment while preserving the evidence and rationale.

Every decision records the reviewer, policy version, rationale, evidence
references, unresolved risks, and next action. Direct stage edits are forbidden.

## Capture gate: idea to prototype

Required dossier:

- customer/requestor and accountable owner
- observable problem and current workaround
- hypothesis under test
- expected customer or research value
- falsification condition
- output form and research domain
- decision deadline and initial evidence
- minimum testable artifact and success criteria

Exit criteria: the claim is falsifiable, a customer/requestor is identified, the
first experiment is bounded, and the expected value justifies prototype WIP.

## Prototype gate: prototype to evaluation

Required evidence:

- experiment question, method, acceptance criteria, and end date
- immutable artifact reference (commit, document version, or URL)
- automated checks appropriate to the output form
- known limitations and material risks
- named evaluation audience and proposed rubric

Exit criteria: the artifact is usable by the intended evaluator and the
evaluation can distinguish success from failure.

## Evaluate gate: evaluation to ship

Required decision packet:

- artifact and rubric versions
- sample target and actual accepted sample
- quantitative results and qualitative themes
- confidence and evidence-coverage assessment
- requirements or unresolved risks supported by evidence citations
- Eval recommendation: advance, iterate, retire, or inconclusive

Exit criteria: thresholds set before the campaign are met, evidence provenance
is complete, and a human reviewer approves the recommendation or documents an
override.

## Ship gate

Required release checks:

- security, privacy, licensing, and accessibility review
- customer/requestor acceptance
- deployment target, immutable version, health check, and rollback reference
- monitoring and post-ship success metric
- release approver

Shipping creates a release record. Public portfolio publication follows an
approved release; setting a project stage alone is not publication approval.

## Agent execution

Foundry queues `AgentPrompt` work with claim leases. A WSL Cursor worker may
claim a prompt, run a **local** Cursor SDK agent against
`FOUNDRY_REPOS_ROOT/<repo_slug>` (or the claim `repo_cwd`), heartbeat the lease,
and complete with notes, runtime, cost, and artifact refs (branch/commit).

Cursor is a bounded code executor, not a stage decision-maker. Completing a
prompt moves the task to `testing` for human review; it does not advance the
project stage.

## Work-in-progress limits

Initial limits are portfolio-wide and should be changed only in a documented
operating review:

- prototype: 3 active projects
- evaluation: 3 active projects
- ship review: 2 active projects

An override requires a gate review with the constrained resource and expiry
date. Retired and held projects do not consume WIP.

## Operating metrics

- time to first artifact: project creation to first immutable artifact
- time to signal: project creation to first completed evaluation campaign
- operator minutes and agent cost per signal
- evidence coverage: required gate evidence present / required evidence
- stage conversion and iteration count
- escaped defects within 30 days of release
- post-ship outcome against the predeclared success metric

Metrics are observations, not editable project summaries. The weekly portfolio
review examines WIP, overdue decisions, blocked gates, evidence coverage, and
projects with declining post-ship outcomes.
