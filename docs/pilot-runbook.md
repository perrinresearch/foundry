# Foundry operating-model pilot

The operating review covers three forms:

- PR-002 Waypoint: interactive application
- PR-004 Leading with Attention: static publication
- A physical product pilot (mockup-first): `physical` form, portfolio kind `product`

For each pilot:

1. Complete the project dossier and record the baseline operator minutes already
   spent moving information between systems.
2. Approve the Capture gate. Confirm Foundry creates one bounded experiment,
   task, and agent prompt.
3. Register an immutable artifact and its automated check result.
4. Open an Eval campaign with the artifact version, audience, rubric, sample
   target, and success threshold fixed before collection.
5. Reconcile the decision packet into Foundry and conduct the human Evaluate
   gate review.
6. If advanced, complete all **form-aware** release checks, deploy through the
   configured adapter, verify health, and record the post-ship metric.
7. Record time to first artifact, time to signal, operator minutes, agent
   runtime/cost, accepted evidence count, gate outcome, iteration count, and
   escaped defects.

The pilot is complete only when all three forms have an auditable timeline from
intake through a decision. Manual interventions are logged during the pilot;
only repeated, deterministic handoffs become candidates for further automation.

## Physical form checklist (mockup-first)

1. Create the project with `form: physical`. Set dossier MTA to a mockup
   package (design diagrams, renderings; optional 3D print photos later).
2. Capture gate: confirm the agent prompt asks for a mockup package with value
   claims and a rough build-cost band.
3. Register immutable artifacts with kinds such as `design_diagram`,
   `rendering`, `mockup`, `model_3d`, or `prototype_photo`.
4. Open an Eval campaign. Share the public survey URL for human feedback.
5. Run persona evaluation grounded on diagrams/images/model previews.
6. Reconcile the decision packet and confirm it includes a **testability**
   assessment (`can_test`, covered/untestable claims).
7. Evaluate gate: do not advance if `can_test` is false; iterate the mockup
   package instead.
8. Ship with physical release checks: safety, cost justification,
   manufacturability, regulatory, customer acceptance, backup/rollback,
   monitoring. Publish to the portfolio as kind `product` when approved.

## Cursor execution pilot (bounded coding)

For a single Waypoint coding prompt on WSL:

1. Deploy Foundry with `FOUNDRY_REPOS_ROOT` set so claim payloads include
   `repo_slug` / `repo_cwd` (workers also fall back to `project_repos.json`).
2. From `~/perrinresearch/agents`, configure `.env` (`FOUNDRY_*`, `CURSOR_API_KEY`).
3. Run `python -m src.pilot_waypoint` (or `--dry-run` to exercise claim/complete
   without calling Cursor).
4. Review the completed prompt and task (`testing`) in Foundry; do not auto-advance
   project stage.
5. Record operator minutes, diff acceptability, escaped defects, and Cursor cost
   from `var/cursor_pilot_waypoint.json`.
