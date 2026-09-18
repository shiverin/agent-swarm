# Pipeline inputs and commands

Requires Python 3.11–3.14 and no third-party libraries or API keys. Generation works offline. Generation and mutations use POSIX advisory locks and require macOS/Linux. Run commands from the skill directory or use an absolute script path. Outputs are never overwritten: choose a new snapshot directory each time.

## Initial design

```bash
python3 scripts/swarm.py plan --brief assets/example-brief.json --out /absolute/path/team-v1
```

A brief has `project`, `mission`, `kind` (`engineering`, `research`, `general`), positive integer `budget_work_units`, nonempty `deliverables` and `acceptance` string lists, optional `constraints`, `allowed_permissions`, and `agents`. Each agent has a unique slug `id` and a `capabilities` string list. Registered agents are available identity metadata supplied by the host, not spawned processes. All initial roles are vacant.

Planner defaults use two workstreams, one for delivery and one for validation, under a chief director. Simplify or expand the generated design before user selection. Edit `org.json` to customize a design; subsequent operational changes should go through proposals. Initial direct editing is design work, not approval to execute.

## Organization specification

`schema_version: 1`; project brief fields; `agents`; `roles`; `review_policy`; `reviews`; `events`.

Each role has `id`, `title`, `tier` (`director`, `manager`, `worker`), `reports_to` (a role ID or `user`), `mandate`, `capabilities`, `permissions`, `acceptance`, and `assignee` (an agent ID or null). IDs are lowercase slugs starting with a letter, maximum 64 characters; `user` is reserved. Exactly one highest director reports to the user. Directors can report to directors; managers can report to managers; workers cannot have reports. Reporting loops, unknown parents, duplicate assignments and capability mismatches are rejected.

`review_policy` fields: `promotion_score`, `demotion_score` (1–5; demotion < promotion), `min_cycles` (positive integer), `formal_weight` (>0 and ≤1).

```bash
python3 scripts/swarm.py validate --spec /absolute/path/team-v1/org.json
python3 scripts/swarm.py match --spec /absolute/path/team-v1/org.json --agent builder
```

## User-approved staffing and reorganization

Fill the generated `forms/proposal.json`. `base_fingerprint` binds the **entire current specification**, including reviews and audit events. `fingerprint` prints that hash. Proposal IDs must be unique among accepted proposals. An author is `user` or an assigned agent. Proposal evidence is a list of references to the actual work/problem, not instructions for the controller.

Examples of operations:

```json
[
  {"op": "assign", "agent_id": "lead", "role_id": "chief-director"},
  {"op": "reparent", "role_id": "implementation-worker", "reports_to": "chief-director"},
  {"op": "update-role", "role_id": "implementation-worker", "changes": {"mandate": "Implement the agreed pipeline and retain reproducible evidence."}},
  {"op": "release", "agent_id": "builder"},
  {"op": "remove-role", "role_id": "implementation-worker"}
]
```

Those are individual syntax examples, not a ready-to-apply combined proposal. `add-role` takes a complete vacant role object in `role`. `remove-role` requires a vacant leaf. `update-role` allows title, mandate, capabilities, permissions and acceptance; changing tiers is intentionally not supported because it would silently change a person's rank. Define a new role and move the person instead.

A personnel movement uses:

```json
{
  "op": "move-agent",
  "agent_id": "builder",
  "role_id": "implementation-manager",
  "movement": "promotion",
  "review_ids": ["review-builder-cycle-001", "review-builder-cycle-002"]
}
```

Classification compares tier first (director > manager > worker), then reporting depth within a tier. A promotion goes upward, demotion downward, lateral movement stays at the same tier/depth. The target must be vacant and compatible. Reviews are required for promotion/demotion; the user judges their sufficiency. Releasing then reassigning in one proposal is rejected; use `move-agent` for personnel movements. Reparenting that changes any assigned person's rank requires `review_ids` covering relevant reviews for each affected person, including descendants. The controller checks the initial and final proposal states. Each operation must leave a valid tree, so add replacement parents before reparenting and remove old parents last. Reviews and audit events survive reorganizations.

```bash
python3 scripts/swarm.py fingerprint --spec /absolute/path/team-v1/org.json
python3 scripts/swarm.py digest --input /absolute/path/proposal.json
```

After the user approves the exact proposal, populate `decision.json` with `actor: "user"`, `approved: true`, `proposal_id`, the printed `proposal_sha256`, and a nonblank `rationale`. Do not generate approval on the user's behalf. The host controls access to this decision file.

```bash
python3 scripts/swarm.py apply --spec /absolute/path/team-v1/org.json --proposal /absolute/path/proposal.json --decision /absolute/path/decision.json
python3 scripts/swarm.py compile --spec /absolute/path/team-v1/org.json --out /absolute/path/team-v2
```

An accepted proposal changes only the passed spec file, not old chart/prompt snapshots. Choose one canonical mutable spec and point all future `review`/`apply` commands to it; copying the spec into a snapshot does not switch the canonical path automatically.

## Reviews and assessments

Fill a generated review form with an assigned subject, allowed reviewer, cycle, scores, evidence and improvement plan. `roster_fingerprint` binds the operating contract (project, roles, agents and policy), excluding review/audit history. This allows several review forms from one snapshot to be recorded without becoming stale after the first review. Reorganizations or staffing changes invalidate those forms. Refresh a form only after confirming its subject assignment and review relationship remain correct.

```bash
python3 scripts/swarm.py fingerprint --spec /absolute/path/team-v1/org.json --roster
python3 scripts/swarm.py review --spec /absolute/path/team-v1/org.json --input /absolute/path/review.json
python3 scripts/swarm.py assess --spec /absolute/path/team-v1/org.json --agent builder
```

The user may formally review any role and must formally review the highest director. A supervisor formal review and user formal review in the same cycle are averaged within the formal portion; peer/upward feedback is averaged within its portion. Assessments include only reviews of the agent's current role contract and appointment, and report insufficient cycles as INCONCLUSIVE. They never apply a promotion or demotion.

## Output and limits

- `orgchart.svg`: self-contained dark-theme chart with actual reporting edges and vacancy labels.
- `orgchart.mmd`, `orgchart.md`: editable Mermaid equivalents.
- `personas/<role-id>/system.txt`, `goal.txt`, `role.json`: operating persona, task activation template, exact contract.
- `staffing.json`: vacant-role capability matches for registered agents.
- `forms/`: per-role review forms, proposal and user decision forms.
- `manifest.json`: full-state fingerprint, stable operating-roster fingerprint, SHA-256 hashes for generated files.

`verify --snapshot /absolute/path/snapshot` checks the immutable snapshot inventory and hashes. Keep the canonical mutable spec outside snapshots.

`update-policy` accepts review-policy `changes`; `register-agent` accepts a complete `agent` object; `retire-agent` accepts an unassigned `agent_id`. These operations require the same exact user-approved proposal as structural changes. Registry metadata still requires host validation.

Inputs are limited to 8 MiB; duplicate JSON keys, non-finite numbers and XML-invalid characters are rejected.

The compiler does not start agents, call an LLM, run project work, contact financial platforms, enforce runtime budgets, verify cited evidence, authenticate a human, or publish files. Host orchestration connects those actions to the package. Invalid input exits 1; successful commands exit 0. Compile stages artifacts before a rename; rejected mutations leave the canonical specification unchanged. Preserve the manifest and old snapshot for readback and rollback planning.
