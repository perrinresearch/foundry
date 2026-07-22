# Foundry operating-model pilot

The first operating review uses two forms:

- PR-002 Waypoint: interactive application
- PR-004 Leading with Attention: static publication

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
6. If advanced, complete all release checks, deploy through the configured
   adapter, verify health, and record the post-ship metric.
7. Record time to first artifact, time to signal, operator minutes, agent
   runtime/cost, accepted evidence count, gate outcome, iteration count, and
   escaped defects.

The pilot is complete only when both forms have an auditable timeline from
intake through a decision. Manual interventions are logged during the pilot;
only repeated, deterministic handoffs become candidates for further automation.

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
