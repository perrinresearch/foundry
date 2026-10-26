# Foundry operating model

Version: 1.1  
Effective: 2026-08-06

Foundry turns a documented claim into a monitored release through four evidence
gates. Agents may draft work, run bounded tasks, and recommend decisions. A
human reviewer is accountable for every stage transition and release.

## Output forms

Projects declare one output form. Form selects portfolio kind, capture prompt
defaults, artifact kinds, evaluation rubric, and required release checks.

| Form | Portfolio kind | Typical artifacts | Primary eval path |
|------|----------------|-------------------|-------------------|
| `interactive` | `application` | application, repository, deployment preview | Web embed + personas |
| `static` | `blog` | document | Word add-in + personas |
| `physical` | `product` | design diagram, rendering, mockup, model_3d, prototype photo, BOM, cost estimate | Public survey page + vision personas |

Physical work stays flexible across electronics, mechanical, soft goods, and
packaged goods. Prefer a **mockup-first** minimum testable artifact (diagrams
and renderings) before committing to a full build.

## Quick capture

Ideas may be created with just a **ref** (project identifier) and **name**
(one-line description) to minimize capture friction. The full dossier is
required only at the point of advancing from `idea` to `prototype` via a gate
review. This allows solo developers and small teams to track early-stage
concepts without administrative overhead while preserving the evidence-gated
rigor for projects that mature into prototype work.

Projects created with minimal information will show gate blockers (e.g.,
"Missing hypothesis", "Missing customer/requestor") on the workflow view until
the dossier is completed.

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

For `physical`, success criteria should include how value will be tested from
the mockup package and a build-cost threshold for the next fidelity step.

Exit criteria: the claim is falsifiable, a customer/requestor is identified, the
first experiment is bounded, and the expected value justifies prototype WIP.

## Prototype gate: prototype to evaluation

Required evidence:

- experiment question, method, acceptance criteria, and end date
- immutable artifact reference (commit, document version, media URI, or URL)
- automated checks appropriate to the output form
- known limitations and material risks
- named evaluation audience and proposed rubric

For `physical`, the immutable artifact set is typically a mockup package
(diagrams/renderings, optional 3D print photos) with a completeness check.

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
- for `physical`: testability assessment (`can_test`, covered/untestable claims,
  missing artifact kinds)

Exit criteria: thresholds set before the campaign are met, evidence provenance
is complete, and a human reviewer approves the recommendation or documents an
override. Physical projects cannot advance when the packet reports
`can_test: false`.

## Ship gate

Required release checks are form-aware:

**interactive**

- security, privacy, licensing, accessibility
- customer/requestor acceptance
- backup/rollback, monitoring

**static**

- licensing, accessibility
- customer/requestor acceptance
- backup/rollback, monitoring

**physical**

- safety, cost justification, manufacturability/sourcing, regulatory (or N/A)
- customer/requestor acceptance
- backup/rollback (design package revision), monitoring (post-ship outcome metric)

Shared ship requirements for all forms:

- deployment target, immutable version, and release approver
- monitoring and post-ship success metric

Shipping creates a release record. Public portfolio publication follows an
approved release; setting a project stage alone is not publication approval.
Physical v1 ships via portfolio listing and/or an `external` adapter; there is
no manufacturing automation in Foundry.

## Agent execution

Foundry queues `AgentPrompt` work with claim leases. A WSL Cursor worker may
claim a prompt, run a **local** Cursor SDK agent against
`FOUNDRY_REPOS_ROOT/<repo_slug>` (or the claim `repo_cwd`), heartbeat the lease,
and complete with notes, runtime, cost, and artifact refs (branch/commit).

Capture prompts are form-aware: physical projects ask for a mockup package, not
a code artifact. Cursor remains a bounded executor, not a stage decision-maker.
Completing a prompt moves the task to `testing` for human review; it does not
advance the project stage.

## Work-in-progress limits

Initial limits are portfolio-wide and should be changed only in a documented
operating review:

- prototype: 5 active projects
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
