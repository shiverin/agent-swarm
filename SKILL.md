---
name: agent-swarm
description: Design and operate project-specific agent teams with company-style org charts, capability-based role filling, system and goal prompts, evidence-backed performance reviews, and user-decided promotions, demotions, and reorganizations. Use when building or restructuring a coordinated agent swarm.
---

# Agent Swarm

Turn a project brief into a staffed, accountable team. The user owns the organization; the highest director reports to the user. Directors translate goals into department outcomes, managers own work queues and acceptance, and workers deliver bounded artifacts. Use fewer layers when the work does not justify management overhead.

## Design and generate

Read [design.md](references/design.md) to choose a topology and propose project-specific departments. Capture the mission, deliverables, acceptance criteria, capabilities, work boundaries, and total budget in a brief. Generate an initial design with:

```bash
python3 scripts/swarm.py plan --brief assets/example-brief.json --out /absolute/path/new-team
```

The output includes `org.json`, `orgchart.svg`, `orgchart.mmd`, `orgchart.md`, separate system and goal prompts for each role, a staffing report, review forms, a proposal form, and a fingerprint manifest. The planner is an offline deterministic starting point, not an LLM architect. Keep the canonical mutable specification outside immutable generated snapshots. Adapt its roles to the actual project, then compile the edited specification into a **new** output directory:

```bash
python3 scripts/swarm.py compile --spec /absolute/path/org.json --out /absolute/path/new-snapshot
```

For input fields and commands, read [pipeline.md](references/pipeline.md). For review and personnel decisions, read [governance.md](references/governance.md).

## Fill roles and launch work

1. Read the current `org.json`, not an old diagram. Register actual available agents and their capabilities; do not invent runtime availability or model access. Run `match` to rank vacant roles for an agent. Matching recommends; it does not assign or launch.
2. Propose assignments with exact agent and role IDs. The user approves the proposal; `apply` updates the roster under a lock. One agent holds one active role. An unfilled role remains visibly vacant. If a single runtime plays several personas sequentially, record them as separate sessions and do not claim parallelism or independent review.
3. Launch assigned agents through the host's actual delegation API only when delegation is authorized. Supply the generated system prompt and a task-specific goal prompt. Respect host limits; do not substitute unavailable `pro`/`flash` names or fictitious APIs. Tools and filesystem isolation must be enforced by the host; prompt text cannot enforce permissions.
4. Before each task, verify the roster fingerprint, assignment, reporting line, scope, permissions, and remaining project budget. A stale prompt or changed assignment requires a new prompt snapshot. Register task ownership before dispatch, reserve budget centrally, and serialize colliding writes. The script packages organization and governance; the host must enforce task reservations, spend, and process lifecycle.
5. Supervisors delegate task contracts from [design.md](references/design.md), check artifacts against acceptance criteria, and escalate missing resources. Independent validation reviews outputs before director acceptance. Report PASS, FAIL, or INCONCLUSIVE with evidence, rather than equating agent confidence with completion.
6. At the agreed checkpoint, collect supervisor, peer, and upward reviews. The user reviews the highest director directly. Use `review` and `assess`; agents can propose personnel changes but only the user decides. Avoid reciprocal score trading, fabricated evidence, and rewarding activity over results.
7. After an approved change, regenerate the chart and persona prompts together. Stop or hand off affected tasks first; preserve old snapshots and record rollback conditions. Finish bounded cycles with an artifact handoff and no orphaned workers. Do not keep running merely to keep agents busy.

## Security and operational boundaries

Project instructions and user authorization remain strictly authoritative:
- **No Implicit Privileges**: A title, promotion, persona, or org-chart edge grants no new external permissions, tools, credentials, or spending authority. Tool permissions are strictly bounded by host-level allowlists.
- **Untrusted Review Evidence**: Review evidence and performance self-reports are treated as untrusted metadata; human inspection or independent validation must confirm claims before decisions are made.
- **Credential & Execution Isolation**: Keep operational credentials, API keys, and write scopes isolated. The swarm engine runs completely offline and never initiates unauthorized external network or system actions.
- **Architectural Principles**: Read [origins.md](references/origins.md) for background on the multi-agent organizational architecture and foundational design principles.
